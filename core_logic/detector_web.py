# Placeholder for language detection logic
# In a real scenario, this would use an NLP library or an API (like OpenAI's)

from .mappings_web import LANGUAGES # To know which languages are supported
from .config_web import LANG_DETECTION_MODEL # OpenAI model for language detection

def detect_language_web(text, current_language_name, client=None):
    """
    Detect the language of the provided text using OpenAI or a simple heuristic.
    
    Args:
        text (str): The text to detect language from.
        current_language_name (str): Current language name being used by the chatbot (e.g., "english").
        client (OpenAI, optional): OpenAI client instance.
        
    Returns:
        str: Detected language name (e.g., "english", "hindi").
    """
    if not text or len(text.split()) < 2: # Too short to reliably detect
        return current_language_name

    if client:
        try:
            # Construct a prompt for the LLM
            # List supported languages clearly for the model
            supported_language_names = list(LANGUAGES.keys())
            lang_prompt = (
                f"What language is the following text in? Respond with ONLY ONE of these language names: "
                f"{', '.join(supported_language_names)}.\n\nText: \"{text}\""
            )
            
            response = client.chat.completions.create(
                model=LANG_DETECTION_MODEL,
                messages=[{"role": "user", "content": lang_prompt}],
                temperature=0, # For deterministic output
                max_tokens=10  # Expecting just the language name
            )
            
            detected_lang_name_from_llm = response.choices[0].message.content.strip().lower()

            # Validate if the LLM's response is one of the supported languages
            if detected_lang_name_from_llm in LANGUAGES:
                print(f"LLM detected language: {detected_lang_name_from_llm} for text: '{text[:50]}...'")
                return detected_lang_name_from_llm
            else:
                print(f"LLM detected unsupported language '{detected_lang_name_from_llm}'. Falling back or staying with current.")
                # Fallback or stick to current if LLM output is not a supported language name
                # For now, let's stick to current if LLM gives an odd response
                # A more robust solution might try a heuristic if LLM fails validation.

        except Exception as e:
            print(f"Error during LLM language detection: {e}. Falling back to heuristic or current language.")
            # Fallthrough to heuristic if API call fails
    
    # Simple heuristic fallback (if no client or LLM fails)
    # This is very basic and primarily for non-Latin scripts.
    # You'd want a more robust local library for offline detection if needed.
    if any(0x0900 <= ord(char) <= 0x097F for char in text): # Devanagari (Hindi, Marathi)
        # Could be Hindi or Marathi. Need more context or a better heuristic.
        # For simplicity, if Devanagari detected, and current is not Hindi/Marathi, prefer Hindi.
        if current_language_name not in ["hindi", "marathi"]:
            return "hindi" 
    elif any(0x0B80 <= ord(char) <= 0x0BFF for char in text): # Tamil script
        if current_language_name != "tamil":
            return "tamil"
    elif any(0x0C80 <= ord(char) <= 0x0CFF for char in text): # Kannada script
        if current_language_name != "kannada":
            return "kannada"
            
    # If no strong signal from heuristics, stick to current language
    return current_language_name

