import os

# OpenAI API Key - IMPORTANT: Set this in your environment variables for security
# or replace "your-api-key-here" directly if this is for local testing only.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "your-api-key-here")

# OpenAI models (Ensure these are up-to-date with available models)
TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
CHAT_MODEL = "gpt-4.1-2025-04-14"
TTS_MODEL = "gpt-4o-mini-tts"
LANG_DETECTION_MODEL = "gpt-3.5-turbo"

CHATBOT_MODE_GRIEVANCE = "grievance"
CHATBOT_MODE_SCHEME_FINDER = "scheme_finder"

# Maximum conversation history turns to store (each turn is user + bot)
MAX_HISTORY_TURNS = 10 # Reduced for web context perhaps, adjust as needed

# Max tokens for chat response from LLM
MAX_RESPONSE_TOKENS = 180 # Adjust based on desired response length

# LLM temperature (0.0 to 2.0) - lower is more deterministic, higher is more creative
TEMPERATURE = 0.7

# Grievance Categories and their details
# IMPORTANT: form_url should now point to the routes in your Flask app (e.g., /forms/infrastructure)
# The 'required_fields' and 'field_descriptions' are crucial for the LLM data extraction.
GRIEVANCE_CATEGORIES = {
    "infrastructure": {
        "form_url": "/forms/infrastructure", # Updated for local Flask app
        "required_fields": [
            "full_name", "email", "mobile", "address", "issue_description",
            "issue_location", "issue_duration"
        ],
        "field_descriptions": {
            "full_name": "The user's full name.",
            "email": "The user's email address.",
            "mobile": "The user's mobile phone number.",
            "address": "The user's complete address where the issue is, or their contact address.",
            "issue_description": "A detailed description of the infrastructure problem (e.g., 'water leakage', 'potholes on road').",
            "issue_location": "The exact location of the infrastructure issue (e.g., 'Main Street, near City Hall', 'Sector 5, Block B'). If not explicitly provided, try to infer from the address or ask again if critical and missing.",
            "issue_duration": """How long the issue has been present. Map the user's description to one of these exact HTML option values: "less_than_week", "one_to_four_weeks", "one_to_six_months", "six_to_twelve_months", "more_than_year". If unsure or no match, use an empty string."""
        }
    },
    "corruption": {
        "form_url": "/forms/corruption", # Updated
        "required_fields": [
            "full_name", "email", "mobile", "department", "official_name",
            "incident_date", "incident_details", "witnesses"
        ],
        "field_descriptions": {
            "full_name": "The complainant's full name.",
            "email": "The complainant's email address.",
            "mobile": "The complainant's mobile number.",
            "department": "The government department or agency involved in the corruption.",
            "official_name": "Name(s) of the official(s) involved, if known. Can be multiple names.",
            "incident_date": "The date when the corruption incident occurred. Format as DD/MM/YYYY.",
            "incident_details": "A detailed description of the corruption incident.",
            "witnesses": "Names or details of any witnesses to the incident, if applicable. Can be multiple names or a description."
        }
    },
    "funds": {
        "form_url": "/forms/funds", # Updated
        "required_fields": [
            "full_name", "email", "mobile", "scheme_name", "application_date",
            "amount_requested", "purpose", "current_status", "issue_details"
        ],
         "field_descriptions": {
            "full_name": "The applicant's full name.",
            "email": "The applicant's email address.",
            "mobile": "The applicant's mobile number.",
            "scheme_name": "The name of the government scheme, program, or fund.",
            "application_date": "The date of application for the funds. Format as DD/MM/YYYY.",
            "amount_requested": "The amount of funds requested or expected (in Rupees). Extract as a number.",
            "purpose": "The purpose for which the funds were requested or are to be used.",
            "current_status": """The current status of the application or fund disbursement. Map to one of these exact HTML option values: "not_applied", "application_submitted", "application_under_review", "application_approved", "partial_funds", "application_rejected", "other". If unsure or no match, use an empty string.""",
            "issue_details": "A description of the specific issue the user is facing regarding the funds."
        }
    },
    "government_service": {
        "form_url": "/forms/govt_service", # Updated
        "required_fields": [
            "full_name", "email", "mobile", "service_type", "other_service", 
            "application_number", "application_date", "issue_details", "prior_followup"
        ],
        "field_descriptions": {
            "full_name": "The applicant's full name.",
            "email": "The applicant's email address.",
            "mobile": "The applicant's mobile number.",
            "service_type": """The type of government service. Map to one of these exact HTML option values: "aadhar", "pan", "voter_id", "passport", "driving_license", "birth_certificate", "death_certificate", "income_certificate", "caste_certificate", "property_registration", "water_connection", "electricity_connection", "other". If unsure or no match, use an empty string.""",
            "other_service": "If service_type is extracted as 'other', collect the specific service name here. Otherwise, leave empty.",
            "application_number": "The application or reference number, if any.",
            "application_date": "The date of application for the service. Format as DD/MM/YYYY.",
            "issue_details": "A detailed description of the issue faced with the government service.",
            "prior_followup": """Whether the user has previously followed up on this issue and how. Map to one of these exact HTML option values: "no", "phone", "email", "visit", "multiple". If unsure or no match, use an empty string."""
        }
    }
}

# Audio recording parameters (less relevant if using browser's Web Speech API for STT)
# FORMAT = pyaudio.paInt16 # Example, if using PyAudio
# CHANNELS = 1
# RATE = 16000 # Common rate for STT
# CHUNK = 1024
# RECORD_SECONDS = 20 # Max recording time for a single utterance via backend

# --- Sanity check for API key ---
if OPENAI_API_KEY == "your-api-key-here":
    print("*********************************************************************")
    print("WARNING: OpenAI API key is not set in core_logic/config_web.py.")
    print("The application might not work correctly with LLM-dependent features.")
    print("Please set your OPENAI_API_KEY environment variable or update the config file.")
    print("*********************************************************************")

