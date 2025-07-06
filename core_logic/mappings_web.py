# Language and voice mappings for the voice chatbot

# Mapping from common language names to ISO 639-1 codes (or similar)
# Used by the chatbot logic internally
LANGUAGES = {
    "english": "en",
    "hindi": "hi",
    "tamil": "ta",
    "marathi": "mr",
    "kannada": "kn"
    # Add more as needed
}

# Mapping from browser language tags (like 'en-US') to your internal language names
BROWSER_LANG_TO_CHAT_LANG = {
    "en-us": "english", "en-gb": "english", "en-au": "english",
    "en-ca": "english", "en-in": "english", "en": "english",
    "hi-in": "hindi", "hi": "hindi",
    "ta-in": "tamil", "ta-lk": "tamil", "ta": "tamil",
    "mr-in": "marathi", "mr": "marathi",
    "kn-in": "kannada", "kn": "kannada"
}


# Voice mapping for backend TTS (OpenAI TTS voice names)
# These are some of the 11 available voices.
# 'alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer'
# While voices are optimized for English, they can speak other languages.
# The 'instructions' parameter in the TTS API can also be used for nuances.
VOICE_MAPPING = {
    "en": "nova",    # A common, clear English voice
    "hi": "onyx",    # Onyx can sound good for Hindi
    "ta": "shimmer", # Shimmer is another option
    "mr": "alloy",   # Alloy is a versatile voice
    "kn": "echo"     # Echo is another option
    # You can experiment with these for best results in different languages.
    # For non-English, the primary factor is the input text's language.
    # The voice choice then adds a certain character/timbre.
}

# Language-specific instructions for TTS (Optional, can be used with `instructions` parameter in TTS API)
# For gpt-4o-mini-tts, the `instructions` parameter can guide tone, accent etc.
# For simpler models like tts-1, this might have less effect.
# For now, we will pass these as a simple prompt/instruction if the model supports it.
LANGUAGE_TTS_INSTRUCTIONS = {
    "en": "Speak clearly in a helpful and neutral English tone.",
    "hi": "Speak clearly in a helpful and neutral Hindi tone.",
    "ta": "Speak clearly in a helpful and neutral Tamil tone.",
    "mr": "Speak clearly in a helpful and neutral Marathi tone.",
    "kn": "Speak clearly in a helpful and neutral Kannada tone."
}

def get_language_code(language_name):
    """Get language code from language name (e.g., "english" -> "en")."""
    return LANGUAGES.get(language_name.lower(), "en") # Default to English

def get_voice_for_language(language_code):
    """Get appropriate OpenAI TTS voice for a language code for backend TTS."""
    return VOICE_MAPPING.get(language_code.lower(), "nova") # Default to Nova

def get_tts_instruction_for_language(language_code):
    """Get language-specific TTS instruction for backend TTS."""
    return LANGUAGE_TTS_INSTRUCTIONS.get(language_code.lower(), "Speak naturally and clearly.")

def map_browser_lang_to_chat_lang(browser_lang_tag):
    """Maps a browser language tag (e.g., 'en-US') to the chatbot's internal language name (e.g., 'english')."""
    if not browser_lang_tag:
        return "english" 
    
    primary_tag = browser_lang_tag.split('-')[0].lower()
    full_tag_lower = browser_lang_tag.lower()

    if full_tag_lower in BROWSER_LANG_TO_CHAT_LANG:
        return BROWSER_LANG_TO_CHAT_LANG[full_tag_lower]
    if primary_tag in BROWSER_LANG_TO_CHAT_LANG: 
        return BROWSER_LANG_TO_CHAT_LANG[primary_tag]
        
    for name, code in LANGUAGES.items():
        if primary_tag == code:
            return name
            
    print(f"Warning: Browser language tag '{browser_lang_tag}' not mapped. Defaulting to English.")
    return "english" 
