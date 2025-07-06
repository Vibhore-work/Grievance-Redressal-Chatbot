from flask import Flask, render_template, request, jsonify, send_from_directory, session
import os
import json
import re 
from dotenv import load_dotenv
import tempfile 
import uuid 
import shutil 

load_dotenv()

# Import from config_web
from core_logic.config_web import (
    OPENAI_API_KEY, 
    CHATBOT_MODE_GRIEVANCE, 
    # CHATBOT_MODE_SCHEME_FINDER, # Not used in this simplified version yet
    TRANSCRIPTION_MODEL,
    TTS_MODEL # Import TTS_MODEL
)
from core_logic.chatbot_web import WebChatbot as GrievanceChatbot
from core_logic.mappings_web import LANGUAGES, get_voice_for_language, get_tts_instruction_for_language

app = Flask(__name__)
app.secret_key = os.urandom(24) 

# --- Directory for TTS Audio Files ---
TTS_AUDIO_DIR = os.path.join(app.root_path, 'tts_audio_files')
os.makedirs(TTS_AUDIO_DIR, exist_ok=True)
# ---

# --- OpenAI Client Initialization (once) ---
openai_client = None
if OPENAI_API_KEY and OPENAI_API_KEY != "your-api-key-here":
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"Global OpenAI client initialized with key ending: ...{OPENAI_API_KEY[-4:] if OPENAI_API_KEY and len(OPENAI_API_KEY) > 4 else '****'}")
else:
    print("WARNING: OPENAI_API_KEY not configured. LLM, Transcription, and TTS features will fail.")

# --- Helper to get or create a unique session ID ---
def get_user_session_id():
    if '_user_session_id' not in session:
        session['_user_session_id'] = uuid.uuid4().hex
    return session['_user_session_id']

# --- Bot Instance Management ---
def get_grievance_bot_for_session():
    user_sid = get_user_session_id()
    bot_key = f"grievance_bot_{user_sid}"
    if not hasattr(app, 'active_bots'):
        app.active_bots = {}
    
    if bot_key not in app.active_bots:
        print(f"Creating new GrievanceChatbot for session key: {bot_key}")
        app.active_bots[bot_key] = GrievanceChatbot(client=openai_client)
    return app.active_bots[bot_key]

# --- Static files for forms ---
@app.route('/form_static/<path:filename>')
def form_static(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

# --- Main Grievance Page ---
@app.route('/')
def index():
    session.pop('active_bot_type', None) 
    return render_template('index.html')

@app.route('/init_grievance_chat', methods=['POST'])
def init_grievance_chat():
    session['active_bot_type'] = CHATBOT_MODE_GRIEVANCE
    user_sid = get_user_session_id() 
    bot_key = f"grievance_bot_{user_sid}"

    if not hasattr(app, 'active_bots'):
        app.active_bots = {}
    
    print(f"Initializing new GrievanceChatbot for session key: {bot_key}")
    current_bot = GrievanceChatbot(client=openai_client)
    app.active_bots[bot_key] = current_bot
    
    initial_bot_response = current_bot.start_session() 
    bot_text_response = initial_bot_response["bot_response"]
    language_code = initial_bot_response["language"] # e.g. 'en', 'hi'
    
    audio_url = None
    if bot_text_response and openai_client:
        try:
            voice = get_voice_for_language(language_code)
            tts_instructions = get_tts_instruction_for_language(language_code)
            
            # Generate speech using OpenAI TTS
            speech_response_openai = openai_client.audio.speech.create(
                model=TTS_MODEL,
                voice=voice,
                input=bot_text_response,
                # The 'instructions' parameter is not standard for tts-1, but gpt-4o-mini-tts might use it.
                # For tts-1, it's more about the voice and input language.
                # If using gpt-4o-mini-tts, you can add: instructions=tts_instructions
                response_format="mp3" 
            )
            audio_filename = f"tts_{uuid.uuid4().hex}.mp3"
            audio_filepath = os.path.join(TTS_AUDIO_DIR, audio_filename)
            speech_response_openai.stream_to_file(audio_filepath)
            audio_url = f"/get_tts_audio/{audio_filename}"
            print(f"TTS audio generated for init: {audio_filepath}")
        except Exception as e:
            print(f"Error generating TTS for initial message: {e}")

    return jsonify({
        "bot_response": bot_text_response,
        "language": language_code, 
        "history": current_bot.get_conversation_history(),
        "audio_url": audio_url # Add audio URL to response
    })

# --- Shared message endpoint ---
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    user_message = data.get('message')
    user_stated_language_code = data.get('language') 
    
    active_bot_type = session.get('active_bot_type')
    current_bot = None

    if active_bot_type == CHATBOT_MODE_GRIEVANCE: 
        current_bot = get_grievance_bot_for_session() 
    else:
        print("Warning: active_bot_type not in session for /send_message. Defaulting to grievance bot.")
        session['active_bot_type'] = CHATBOT_MODE_GRIEVANCE 
        current_bot = get_grievance_bot_for_session()
        if not user_message: 
             return jsonify({"error": "Chat session not properly initialized. Please refresh page."}), 400

    if not current_bot: 
        return jsonify({"error": "Chatbot instance could not be created or retrieved."}), 500
    if not user_message: 
        return jsonify({"error": "No message provided"}), 400
    
    bot_turn_response = current_bot.process_user_turn(user_message, user_stated_language=user_stated_language_code)
    
    bot_text_response = bot_turn_response.get("bot_response")
    language_code = bot_turn_response.get("language", "en") # Default to 'en'
    
    final_json_response = bot_turn_response.copy() # Start with all data from bot (action, form_url etc.)
    final_json_response["audio_url"] = None

    if bot_text_response and openai_client:
        try:
            voice = get_voice_for_language(language_code)
            # tts_instructions = get_tts_instruction_for_language(language_code) # For gpt-4o-mini-tts
            
            speech_response_openai = openai_client.audio.speech.create(
                model=TTS_MODEL,
                voice=voice,
                input=bot_text_response,
                # instructions=tts_instructions, # If using a model that supports it well
                response_format="mp3"
            )
            audio_filename = f"tts_{uuid.uuid4().hex}.mp3"
            audio_filepath = os.path.join(TTS_AUDIO_DIR, audio_filename)
            speech_response_openai.stream_to_file(audio_filepath)
            
            final_json_response["audio_url"] = f"/get_tts_audio/{audio_filename}"
            print(f"TTS audio generated: {audio_filepath}")
        except Exception as e:
            print(f"Error generating TTS for bot response: {e}")
            # Fallback: client will use browser TTS if audio_url is null
    
    return jsonify(final_json_response)

# --- Endpoint for Serving TTS Audio ---
@app.route('/get_tts_audio/<filename>')
def get_tts_audio(filename):
    # Basic security: prevent directory traversal
    if ".." in filename or filename.startswith("/"):
        return "Invalid filename", 400
    try:
        return send_from_directory(TTS_AUDIO_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        print(f"TTS audio file not found: {filename}")
        return "Audio file not found", 404


# --- Endpoint for Speech-to-Text ---
@app.route('/transcribe_audio', methods=['POST'])
def transcribe_audio_route():
    if not openai_client:
        return jsonify({"error": "OpenAI client not initialized. Cannot transcribe."}), 500
    if 'audio_file' not in request.files:
        return jsonify({"error": "No audio file part in the request"}), 400
    file = request.files['audio_file']
    if file.filename == '':
        return jsonify({"error": "No selected audio file"}), 400

    language_hint = request.form.get('language', 'en') 
    if language_hint not in LANGUAGES.values(): 
        print(f"Warning: Invalid language hint '{language_hint}' for STT. Defaulting to 'en'.")
        language_hint = 'en'

    temp_audio_path = None
    debug_audio_path = None 
    try:
        debug_audio_dir = os.path.join(app.root_path, 'debug_audio')
        os.makedirs(debug_audio_dir, exist_ok=True)
        
        temp_dir = tempfile.gettempdir()
        original_filename = file.filename or "audio.webm" 
        extension = os.path.splitext(original_filename)[1]
        if not extension: 
            mimetype = file.mimetype 
            if mimetype == 'audio/webm': extension = '.webm'
            elif mimetype == 'audio/ogg': extension = '.ogg'
            elif mimetype == 'audio/wav': extension = '.wav'
            else: extension = '.webm' 

        unique_filename_base = f"user_audio_{uuid.uuid4().hex}"
        temp_audio_path = os.path.join(temp_dir, f"{unique_filename_base}{extension}")
        
        debug_audio_path = os.path.join(debug_audio_dir, f"{unique_filename_base}{extension}")
        file.save(temp_audio_path) # Save to temp path first
        shutil.copy2(temp_audio_path, debug_audio_path) # Then copy for debugging
        print(f"Audio saved temporarily to: {temp_audio_path}, size: {os.path.getsize(temp_audio_path)} bytes")
        print(f"DEBUGGING: Audio copy saved to: {debug_audio_path}")

        with open(temp_audio_path, "rb") as audio_file_to_transcribe:
            transcription_response = openai_client.audio.transcriptions.create(
                model=TRANSCRIPTION_MODEL, 
                file=audio_file_to_transcribe,
                language=language_hint, 
                response_format="json" 
            )
        transcript_text = transcription_response.text
        print(f"Transcription successful. Language hint: {language_hint}, Text: {transcript_text}")
        return jsonify({"transcript": transcript_text})
    except Exception as e:
        print(f"Error during transcription: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception as e:
                print(f"Error deleting temporary STT audio file {temp_audio_path}: {e}")

# --- Grievance Form Routes ---
@app.route('/forms/<form_name>')
def serve_form(form_name):
    if not re.match(r"^[a-zA-Z0-9_]+$", form_name): return "Invalid form name", 400
    form_file = f'{form_name}_form.html'
    template_path = os.path.join(app.template_folder, form_file)
    if os.path.exists(template_path): return render_template(form_file)
    return "Form not found", 404

@app.route('/submit_grievance', methods=['POST'])
def submit_grievance_form_route():
    try:
        form_data = request.get_json(force=True) 
        submissions_dir = os.path.join(app.root_path, 'submissions')
        os.makedirs(submissions_dir, exist_ok=True)
        submission_file_path = os.path.join(submissions_dir, 'grievances.json')
        try:
            with open(submission_file_path, 'r') as f: submissions = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): submissions = []
        submissions.append(form_data)
        with open(submission_file_path, 'w') as f: json.dump(submissions, f, indent=2)
        return jsonify({"message": "Form submitted successfully via main app!"}), 200
    except Exception as e:
        print(f"Error processing form submission: {e}"); return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5050)
