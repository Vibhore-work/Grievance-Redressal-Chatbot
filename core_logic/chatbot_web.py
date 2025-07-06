import os
import json
import re
import random

# Assuming config_web.py and mappings_web.py are in the same directory (core_logic)
# Ensure GRIEVANCE_CATEGORIES in config_web.py has detailed "field_descriptions"
# similar to what was in terminalchatbot.txt for optimal data extraction.
from .config_web import GRIEVANCE_CATEGORIES, OPENAI_API_KEY, CHAT_MODEL, MAX_HISTORY_TURNS, TEMPERATURE, MAX_RESPONSE_TOKENS, LANG_DETECTION_MODEL
from .mappings_web import get_language_code, get_voice_for_language, map_browser_lang_to_chat_lang, LANGUAGES
from .detector_web import detect_language_web

class WebChatbot:
    def __init__(self, client=None, default_language="english"):
        self.client = client 
        self.default_language = default_language.lower() # e.g., "english", "hindi"
        self.language_code = get_language_code(self.default_language) # e.g., "en", "hi"
        
        self.grievance_category = None
        self.form_data = {}
        self.conversation_stage = "understanding" 
        self.conversation_history = []
        
        print(f"WebChatbot initialized. Default language: {self.default_language}, Code: {self.language_code}")
        if not self.client and OPENAI_API_KEY and OPENAI_API_KEY != "your-api-key-here":
             from openai import OpenAI
             self.client = OpenAI(api_key=OPENAI_API_KEY)
             print("OpenAI client initialized in WebChatbot.")
        elif not self.client:
            print("WebChatbot: OpenAI client NOT initialized. LLM calls will be simulated or fail.")

    def reset_conversation(self):
        """Resets the conversation state to initial values."""
        self.grievance_category = None
        self.form_data = {}
        self.conversation_stage = "understanding"
        self.conversation_history = []
        self.default_language = "english" 
        self.language_code = get_language_code(self.default_language)
        print("WebChatbot conversation reset.")

    def start_session(self):
        """Starts or restarts a chat session, returning the initial greeting."""
        self.reset_conversation()
        greeting = self._get_localized_string("initial_greeting")
        self.add_to_history("assistant", greeting)
        return {"bot_response": greeting, "language": self.language_code}
        
    def get_conversation_history(self):
        """Returns the current conversation history."""
        return self.conversation_history

    def add_to_history(self, role, content):
        """Adds a message to the conversation history, managing its size."""
        self.conversation_history.append({"role": role, "content": content})
        max_history = MAX_HISTORY_TURNS * 2 
        if len(self.conversation_history) > max_history:
            self.conversation_history = self.conversation_history[-max_history:]

    def update_language(self, new_language_name):
        """
        Updates the chatbot's language settings.
        new_language_name should be one of the keys in LANGUAGES (e.g., "english", "hindi").
        """
        normalized_new_language = new_language_name.lower()
        if normalized_new_language in LANGUAGES: 
            if normalized_new_language != self.default_language:
                print(f"LANGUAGE UPDATE: Switching from {self.default_language} to {normalized_new_language}")
                self.default_language = normalized_new_language
                self.language_code = get_language_code(self.default_language)
                print(f"Chatbot language changed to {self.default_language} (code: {self.language_code})")
            else:
                print(f"LANGUAGE NOTE: Language already set to {self.default_language}.")
        else:
            print(f"Warning: Attempted to switch to unsupported language name: {new_language_name}. Current language '{self.default_language}' maintained.")

    def process_user_turn(self, user_text, user_stated_language=None):
        """
        Processes a single turn of user input.
        user_stated_language is the language code (e.g., 'en', 'hi') of the user's input,
        passed from frontend (which gets it from the previous bot response's language).
        """
        if not user_text:
            return {"bot_response": self._get_localized_string("audio_capture_error"), "language": self.language_code}

        self.add_to_history("user", user_text)
        print(f"USER SAID (lang hint: {user_stated_language if user_stated_language else 'None'}): {user_text}")

        current_chat_lang_name_context = self.default_language
        if user_stated_language: 
            current_chat_lang_name_context = map_browser_lang_to_chat_lang(user_stated_language) 

        if self.client:
            detected_user_lang_name = detect_language_web(user_text, current_chat_lang_name_context, self.client)
            print(f"Detected user text language as: '{detected_user_lang_name}' (hint was '{current_chat_lang_name_context}')")
            self.update_language(detected_user_lang_name) 
        else: 
            if user_stated_language:
                 self.update_language(map_browser_lang_to_chat_lang(user_stated_language))

        if user_text.lower() in ["exit", "quit", "stop", "bye", "goodbye"]:
            farewell = self._get_localized_string("farewell_messages") 
            self.add_to_history("assistant", farewell)
            return {"bot_response": farewell, "action": "END_CONVERSATION", "language": self.language_code}

        bot_response_text = ""
        action_data = {"language": self.language_code} 

        if self.conversation_stage == "understanding":
            bot_response_text = self._get_llm_response() 
            category_match = re.search(r"GRIEVANCE_CATEGORY:\s*([\w-]+)", bot_response_text)
            if category_match:
                extracted_category_raw = category_match.group(1)
                extracted_category = extracted_category_raw.lower().strip()
                if extracted_category in GRIEVANCE_CATEGORIES:
                    self.grievance_category = extracted_category
                    self.conversation_stage = "categorizing"
                    self.form_data = {} 
                    bot_response_text = bot_response_text.replace(category_match.group(0), "").strip()
                    print(f"DEBUG: Category '{self.grievance_category}' identified by LLM. Stage -> categorizing.")
                else:
                    print(f"DEBUG: LLM extracted category '{extracted_category}' which is NOT IN defined GRIEVANCE_CATEGORIES.")
            else:
                print(f"DEBUG: LLM response in 'understanding' did not contain GRIEVANCE_CATEGORY marker. Response: {bot_response_text}")


        elif self.conversation_stage == "categorizing":
            if self._is_affirmative(user_text): 
                self.conversation_stage = "collecting"
                print(f"DEBUG: User confirmed category '{self.grievance_category}'. Stage -> collecting.")
                bot_response_text = self._get_llm_response() 
            elif self._is_negative(user_text): 
                denial_response = self._get_localized_string("category_denied_re_understand", category=self.grievance_category or "the current")
                self.grievance_category = None
                self.conversation_stage = "understanding"
                self.form_data = {} 
                print(f"DEBUG: User denied category. Stage -> understanding.")
                bot_response_text = denial_response + " " + self._get_llm_response() 
            else: 
                print(f"DEBUG: User response in 'categorizing' ('{user_text}') not clearly affirmative/negative. Assuming implicit consent/data provision. Stage -> collecting.")
                self.conversation_stage = "collecting"
                bot_response_text = self._get_llm_response()


        elif self.conversation_stage == "collecting":
            bot_response_text = self._get_llm_response() 
            # If _get_llm_response (due to READY_TO_CONFIRM) changed stage to "form_filling",
            # bot_response_text is already the transition message.
            # The action_data for LOAD_FORM will be handled by the "form_filling" block below.

        elif self.conversation_stage == "confirming": # This stage is now less central for full confirmation
            print(f"DEBUG: Processing 'confirming' stage (likely for minor clarification). User text: '{user_text}'")
            llm_interpretation_response = self._get_llm_response() 

            if "USER_CONFIRMED_FORM_DATA" in llm_interpretation_response: # If LLM confirms a specific point
                print("DEBUG: LLM signaled USER_CONFIRMED_FORM_DATA (in confirming stage).")
                # This path would typically mean a specific field was confirmed, not the whole form.
                # For full form, we now go directly to 'form_filling' from 'collecting'.
                # If by some logic we end up here and it means "all data is final", transition to form_filling.
                self.conversation_stage = "form_filling" 
                bot_response_text = self._get_localized_string("direct_to_form_filling_prompt",
                                                              category_readable=(self.grievance_category.replace("_", " ") if self.grievance_category else "the"))
                # Action data for LOAD_FORM will be built in the form_filling block below.
            
            elif "USER_WANTS_TO_UPDATE_DATA" in llm_interpretation_response:
                print("DEBUG: LLM signaled USER_WANTS_TO_UPDATE_DATA. Reverting to collecting.")
                self.conversation_stage = "collecting" 
                self.form_data = {} # Reset form data for fresh collection of all fields
                bot_response_text = self._get_localized_string("update_information_prompt")
                bot_response_text += " " + self._get_llm_response() # Get a new prompt for collecting
            
            else: # LLM didn't output a clear marker, so its response is a re-prompt to the user.
                print("DEBUG: LLM is re-prompting for confirmation (response was unclear or not a marker).")
                bot_response_text = llm_interpretation_response
        
        elif self.conversation_stage == "form_filling":
            # This stage is now entered directly from 'collecting' if data is complete,
            # or from 'confirming' if that path was taken for a specific clarification.
            
            # If bot_response_text is already set by the transition (e.g. from collecting to form_filling)
            # we use that. Otherwise, it's a subsequent turn in form_filling (e.g., user submitted or asked a question).
            if not bot_response_text: # This means it's a subsequent turn *within* an already active form_filling stage
                if "submit" in user_text.lower() or "done" in user_text.lower() or self._is_affirmative(user_text): 
                    bot_response_text = self._get_localized_string("form_submitted_successfully") 
                    self.conversation_stage = "submitted" 
                    action_data.update({"action": "FORM_SUBMITTED"})
                else: # User might be asking a question while form is displayed, or providing unprompted info
                      # For a demo, a simple re-prompt might be enough. A more complex system would use LLM.
                    bot_response_text = self._get_localized_string("form_filling_prompt") 
            
            # Prepare LOAD_FORM action data if this is the *first time* we enter 'form_filling' for this grievance
            # This ensures the form is loaded when we transition into this stage.
            # The 'action' key in action_data might not be set if we came from 'collecting' via _get_llm_response
            # or if we came from 'confirming' where action_data wasn't fully built for LOAD_FORM.
            is_load_form_action_needed = "action" not in action_data or action_data.get("action") != "LOAD_FORM"
            
            if is_load_form_action_needed and self.grievance_category and self.form_data:
                category_info = GRIEVANCE_CATEGORIES.get(self.grievance_category)
                if category_info and category_info.get("form_url"):
                    action_data.update({ 
                        "action": "LOAD_FORM", "form_type": self.grievance_category,
                        "form_url": category_info["form_url"], "form_data": self.form_data
                    })
                    print(f"DEBUG: LOAD_FORM action prepared/confirmed. Category: {self.grievance_category}, Form URL: {category_info['form_url']}")
                    # The bot_response_text (e.g., "Great, I'll prepare the form...") should have been set during the stage transition.
                else:
                    err_msg = self._get_localized_string("internal_form_details_error") 
                    self.add_to_history("assistant", err_msg) 
                    self.reset_conversation() # Reset fully on such an error
                    bot_response_text = err_msg 
                    print(f"DEBUG: Error finding form details for category '{self.grievance_category}'. Resetting to understanding.")
            elif is_load_form_action_needed: # Grievance category or form_data missing
                print(f"DEBUG: Entered 'form_filling' without grievance_category or form_data properly set up for LOAD_FORM. Resetting.")
                self.reset_conversation()
                bot_response_text = self._get_localized_string("unhandled_stage_error")

        elif self.conversation_stage == "submitted":
            if self._is_negative(user_text) or user_text.lower() in ["exit", "quit", "stop", "bye", "goodbye"]:
                 bot_response_text = self._get_localized_string("farewell_messages")
                 action_data.update({"action": "END_CONVERSATION"})
            else: 
                self.reset_conversation() 
                self.add_to_history("user", user_text) # Add user's new query
                if self.client: 
                    detected_user_lang_name = detect_language_web(user_text, self.default_language, self.client) 
                    self.update_language(detected_user_lang_name)
                # Start a new interaction from 'understanding' stage
                bot_response_text = self._get_llm_response() # This will use the 'understanding' prompt
                action_data["language"] = self.language_code # Ensure language is set for the new turn
        else:
            print(f"Warning: Reached unhandled conversation stage: {self.conversation_stage}")
            bot_response_text = self._get_localized_string("unhandled_stage_error")
            self.reset_conversation()
            if self.client:
                detected_user_lang_name = detect_language_web(user_text, self.default_language, self.client)
                self.update_language(detected_user_lang_name)
            action_data["language"] = self.language_code

        self.add_to_history("assistant", bot_response_text)
        
        # Ensure action_data always has the current language code
        if "language" not in action_data:
            action_data["language"] = self.language_code
        
        response_payload = {"bot_response": bot_response_text}
        response_payload.update(action_data) 
        
        print(f"BOT RESPONSE (lang: {self.language_code}, stage: {self.conversation_stage}): {bot_response_text}")
        print(f"PAYLOAD TO CLIENT: {json.dumps(response_payload, indent=2, ensure_ascii=False)}")
        return response_payload

    def _get_system_prompt(self):
        language = self.default_language 
        language_instruction = f"RESPONSE LANGUAGE DIRECTIVE: Your response MUST be entirely in {language}. No other languages are permitted in your output. Adhere strictly to {language} for all text."

        if self.conversation_stage == "understanding":
            # ... (no changes to understanding prompt)
            understanding_prompt = f"""{language_instruction}
You are a highly skilled multilingual grievance assistant for citizens, set to respond in {language}.
Your primary goal is to accurately understand the user's grievance and categorize it into one of the following: {', '.join(GRIEVANCE_CATEGORIES.keys())}.

Category Guidelines:
- **infrastructure**: Issues related to physical structures and facilities (e.g., bad roads, damaged public buildings, problems with *existing* water pipe quality/supply regularity, electricity outages due to faulty lines).
- **corruption**: Issues involving bribery, misuse of public office or funds by officials.
- **funds**: Problems related to government financial schemes, scholarships, grants (e.g., non-disbursal, application issues).
- **government_service**: Issues with the *process* of obtaining or using a specific government service (e.g., problems applying for an Aadhar card, delays in passport issuance, disputes over utility bills if not a physical infrastructure failure, issues with a government office's responsiveness for a service).
  - For **water-related issues**:
    - If about quality, quantity, or timing/regularity of water from an *existing connection* (e.g., "dirty water", "no water supply", "water comes at wrong time"): Categorize as **infrastructure**.
    - If about *applying for a new water connection, billing disputes, meter problems, or customer service interactions* regarding water: Categorize as **government_service** (with service_type: 'water_connection').

Interaction Flow:
1. Be empathetic and understanding.
2. Ask clarifying questions ONLY if absolutely necessary to determine the category.
3. Once you are reasonably sure of the category based on the guidelines, identify it.
4. CRITICAL: At the end of your response where you identify the category, you MUST include the marker "GRIEVANCE_CATEGORY:[category_name_lowercase_underscored]". Example for {language}: "It sounds like an issue with the quality of water from your tap. GRIEVANCE_CATEGORY:infrastructure" or "It seems you are having trouble with your passport application. GRIEVANCE_CATEGORY:government_service".
5. Do not offer to file the form or collect detailed data at this stage. Your focus is solely on understanding and categorizing the grievance.
Remember to respond ONLY in {language}.
"""
            return understanding_prompt

        elif self.conversation_stage == "categorizing":
            # ... (no changes to categorizing prompt)
            if not self.grievance_category or self.grievance_category not in GRIEVANCE_CATEGORIES:
                print("DEBUG: _get_system_prompt for 'categorizing' but no valid category. Reverting to 'understanding'.")
                self.conversation_stage = "understanding" 
                return self._get_system_prompt() 
            
            category_details = GRIEVANCE_CATEGORIES[self.grievance_category]
            fields_list = category_details.get("required_fields", [])
            fields_str = ", ".join([f.replace("_", " ") for f in fields_list]) if fields_list else self._get_localized_string("some_specific_details_placeholder")
            
            return f"""{language_instruction}
You are a helpful grievance assistant, responding in {language}.
The system believes the user's issue is a '{self.grievance_category}' grievance.
1. Confirm this category with the user in a natural way.
2. Briefly explain that to file this type of complaint, you'll need to collect information like: {fields_str}.
3. Ask the user if they would like to proceed with providing these details for the '{self.grievance_category}' form.
4. Respond ONLY with this confirmation and question. Do not ask for any data yet.
Example (if {language} is English): "Okay, that sounds like an infrastructure problem. To file a report, I'll need details such as your address, a description of the issue, and its location. Would you like to proceed with this?"
"""
        elif self.conversation_stage == "collecting":
            # ... (no changes to collecting prompt)
            if not self.grievance_category or self.grievance_category not in GRIEVANCE_CATEGORIES:
                self.conversation_stage = "understanding"; return self._get_system_prompt()

            category_details = GRIEVANCE_CATEGORIES[self.grievance_category]
            required_fields = category_details.get("required_fields", [])
            
            collected_fields_info = []
            missing_fields_info = []
            current_form_data = self.form_data 
            for field in required_fields:
                field_readable = field.replace('_',' ')
                if field in current_form_data and str(current_form_data.get(field,"")).strip(): 
                    collected_fields_info.append(f"{field_readable}: '{current_form_data[field]}'")
                else:
                    if field == 'other_service' and current_form_data.get('service_type') != 'other':
                        continue 
                    missing_fields_info.append(field_readable)
            
            collected_str = "; ".join(collected_fields_info) if collected_fields_info else self._get_localized_string("none_confirmed_placeholder")
            missing_str = ", ".join(missing_fields_info) if missing_fields_info else self._get_localized_string("all_collected_placeholder") 
            user_latest_message = self.conversation_history[-1]["content"] if self.conversation_history and self.conversation_history[-1]["role"] == "user" else ""

            return f"""{language_instruction}
You are a helpful grievance assistant, responding in {language}, helping the user file a '{self.grievance_category}' grievance.
Your task is to collect the remaining necessary information based on the user's latest response: "{user_latest_message}"
Required fields for '{self.grievance_category}': {', '.join(f.replace('_',' ') for f in required_fields)}.
System's current understanding of collected data:
- Collected so far: {collected_str}
- Fields the system thinks are still needed (prioritize these): {missing_str}

Guidelines:
1. Analyze the user's latest response ("{user_latest_message}"). If it provides data for any *missing* fields (from "Fields the system thinks are still needed"), acknowledge it.
2. Ask for the next one or two *missing* pieces of information conversationally.
3. If "Fields the system thinks are still needed" is empty (or says "{self._get_localized_string('all_collected_placeholder')}"), it means all required data appears to be collected. In this case, end your response with the exact phrase "READY_TO_CONFIRM". This marker is CRITICAL. Do not ask for confirmation yourself, just use the marker.
4. Keep responses concise and suitable for voice.
Example for asking (if {language} is English): "Thanks for providing your name. Next, could you please tell me your email address?"
Example when all data seems collected (if {language} is English): "Great, I think I have all the details. READY_TO_CONFIRM"
"""
        elif self.conversation_stage == "confirming": # This prompt is for minor clarifications, not full summary.
            # ... (no changes to confirming prompt, its role is now for specific field clarifications if needed)
            user_response_to_summary = ""
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                user_response_to_summary = self.conversation_history[-1]["content"]

            summary_presented_by_bot = ""
            if len(self.conversation_history) > 1 and self.conversation_history[-2]["role"] == "assistant":
                summary_presented_by_bot = self.conversation_history[-2]["content"] # This would be a specific question, not full data.
            
            return f"""{language_instruction}
You are an assistant helping a user confirm a specific detail for a '{self.grievance_category}' grievance, responding in {language}.
You previously asked the user to clarify something like: "{summary_presented_by_bot}"
The user has now responded with: "{user_response_to_summary}"

Your task is to interpret the user's response ("{user_response_to_summary}") regarding that specific point:
1. If the user's response clearly confirms the detail you asked about, then respond with ONLY the marker: "USER_CONFIRMED_FORM_DATA". (This implies the specific point is confirmed, allowing collection to continue).
2. If the user's response indicates the detail is incorrect or they want to change it, then respond with ONLY the marker: "USER_WANTS_TO_UPDATE_DATA". (This implies the specific point needs re-collection).
3. If the user's response is unclear, ask them again to clarify that specific point.

IMPORTANT:
- If you output a marker, that marker MUST be the ONLY content in your response.
- If you are re-prompting, just provide the re-prompt text.
"""

        elif self.conversation_stage == "form_filling":
             # ... (no changes to form_filling prompt)
             return f"""{language_instruction}
You are an assistant helping a user who is currently viewing a '{self.grievance_category}' form, responding in {language}.
The user might ask questions about the form or indicate they have submitted it.
1. If they ask a question, try to answer it based on general knowledge or ask them to refer to the form's labels.
2. If they indicate they have submitted the form (e.g., "I submitted it", "I'm done"), acknowledge this.
3. Keep responses brief and helpful.
"""
        return f"{language_instruction} You are a helpful assistant. Your current stage is {self.conversation_stage}. Please respond naturally in {language}."

    def _get_llm_response(self):
        if not self.client:
            print("LLM client not available. Returning placeholder/simulated response.")
            # ... (simulation logic can remain, but READY_TO_CONFIRM simulation needs adjustment)
            if self.conversation_stage == "understanding":
                sim_response = self._get_localized_string("initial_greeting")
                if self.conversation_history and "पानी" in self.conversation_history[-1]['content'] and ("क्वालिटी" in self.conversation_history[-1]['content'] or "समय" in self.conversation_history[-1]['content']):
                    self.grievance_category = "infrastructure" 
                    self.conversation_stage = "categorizing" 
                    sim_response = self._get_localized_string("category_identified_prompt", category="infrastructure") + " GRIEVANCE_CATEGORY:infrastructure"
                elif self.conversation_history and "infrastructure" in self.conversation_history[-1]['content'].lower():
                    self.grievance_category = "infrastructure"
                    self.conversation_stage = "categorizing" 
                    sim_response = self._get_localized_string("category_identified_prompt", category="infrastructure") + " GRIEVANCE_CATEGORY:infrastructure"
                return sim_response
            elif self.conversation_stage == "categorizing":
                 return self._get_localized_string("category_confirmation_prompt", category=self.grievance_category or "general")
            elif self.conversation_stage == "collecting":
                category_info = GRIEVANCE_CATEGORIES.get(self.grievance_category, {})
                required_fields = category_info.get("required_fields", [])
                missing_fields = [f for f in required_fields if f not in self.form_data or not str(self.form_data.get(f,"")).strip()]
                if not missing_fields: 
                    # Simulate READY_TO_CONFIRM path for non-LLM
                    if self._check_critical_data_present_simulated(): # New simulated check
                        self.conversation_stage = "form_filling"
                        return self._get_localized_string("direct_to_form_filling_prompt", 
                                                          category_readable=(self.grievance_category.replace("_", " ") if self.grievance_category else "the"))
                    else:
                        # If critical data is still missing in simulation, ask for it.
                        # This part of simulation needs to be robust or simply ask for the first missing field.
                        return self._get_localized_string("ask_for_field_prompt", field_name=missing_fields[0].replace("_"," ") if missing_fields else "details")

                else:
                    return self._get_localized_string("ask_for_field_prompt", field_name=missing_fields[0].replace("_"," ")) + " If that's all, say READY_TO_CONFIRM" # Old sim text, less relevant now
            elif self.conversation_stage == "confirming":
                last_user_msg = self.conversation_history[-1]["content"].lower().strip().rstrip('.,!?;')
                if "yes" in last_user_msg or "correct" in last_user_msg or "हाँ" in last_user_msg:
                    return "USER_CONFIRMED_FORM_DATA"
                elif "no" in last_user_msg or "wrong" in last_user_msg or "नहीं" in last_user_msg:
                    return "USER_WANTS_TO_UPDATE_DATA"
                else:
                    return self._get_localized_string("simulated_confirmation_reprompt") 
            return f"Simulated response for stage {self.conversation_stage} in {self.default_language}."

        system_prompt = self._get_system_prompt()
        messages = [{"role": "system", "content": system_prompt}] + self.conversation_history

        print(f"--- Sending to LLM (model: {CHAT_MODEL}, lang: {self.default_language}, stage: {self.conversation_stage}) ---")
        try:
            response = self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=TEMPERATURE if self.conversation_stage != "confirming" else 0.2, 
                max_tokens=MAX_RESPONSE_TOKENS
            )
            assistant_response = response.choices[0].message.content.strip()
            print(f"LLM Raw Response: {assistant_response}")

            if "READY_TO_CONFIRM" in assistant_response and self.conversation_stage == "collecting":
                print("DEBUG: LLM indicated READY_TO_CONFIRM.")
                llm_pre_submission_text = assistant_response.replace("READY_TO_CONFIRM", "").strip()
                
                # Attempt to finalize data and check if ready for submission
                ready_for_submission = self._finalize_data_and_check_readiness() 

                if ready_for_submission:
                    self.conversation_stage = "form_filling" # Transition stage
                    bot_response_text = self._get_localized_string("direct_to_form_filling_prompt",
                                                                  category_readable=(self.grievance_category.replace("_", " ") if self.grievance_category else "the"))
                    # Prepend LLM's text if any (e.g., "Okay, I have your email.")
                    final_response = f"{llm_pre_submission_text} {bot_response_text}".strip() if llm_pre_submission_text else bot_response_text
                    return final_response
                else:
                    # Critical data is missing, stay in 'collecting' stage.
                    # LLM might have said READY_TO_CONFIRM prematurely, or extraction failed.
                    # The next call to _get_llm_response in 'collecting' stage should ask for missing fields.
                    response_if_not_ready = self._get_localized_string("llm_error_collecting_after_ready_but_missing", category=self.grievance_category or "details")
                    if llm_pre_submission_text:
                         return f"{llm_pre_submission_text} {response_if_not_ready}".strip()
                    return response_if_not_ready
            
            # _create_confirmation_message() is no longer called here.
            # The 'confirming' stage (if hit for minor clarifications) will handle its own LLM response interpretation.
            return assistant_response

        except Exception as e:
            print(f"Error calling LLM API: {e}")
            if self.conversation_stage == "collecting":
                return self._get_localized_string("llm_error_collecting")
            return self._get_localized_string("llm_error_general")

    def _check_critical_data_present_simulated(self):
        """ Simulation helper for non-LLM mode to check if critical data is present """
        if not self.grievance_category or self.grievance_category not in GRIEVANCE_CATEGORIES:
            return False
        category_info = GRIEVANCE_CATEGORIES.get(self.grievance_category, {})
        required_fields = category_info.get("required_fields", [])
        if not required_fields: return True # No fields, so ready

        for req_field in required_fields:
            if req_field == 'other_service' and self.form_data.get('service_type') != 'other':
                continue
            if not str(self.form_data.get(req_field, "")).strip():
                print(f"SIM_DEBUG: Missing simulated field {req_field}")
                return False # Missing a required field in simulation
        print("SIM_DEBUG: All simulated critical fields present.")
        return True

    def _finalize_data_and_check_readiness(self):
        """
        Extracts form data using LLM and checks if all critical fields are present.
        Returns True if all critical data is present, False otherwise.
        Updates self.form_data.
        """
        print("DEBUG: Attempting to extract all form data via LLM for final check...")
        extracted_data = self._extract_dynamic_form_data_llm() 

        if not extracted_data or not isinstance(extracted_data, dict):
            print("DEBUG: LLM Data extraction failed or yielded non-dict. Cannot proceed to submission.")
            return False 

        for key, value in extracted_data.items():
            if str(value).strip(): 
                 self.form_data[key] = value
            elif key not in self.form_data: 
                 self.form_data[key] = "" 

        print(f"DEBUG: Form data after LLM extraction attempt: {self.form_data}")

        category_info = GRIEVANCE_CATEGORIES.get(self.grievance_category, {})
        required_fields = category_info.get("required_fields", [])
        
        if not required_fields: 
            print(f"DEBUG: No required fields defined for category '{self.grievance_category}'. Assuming ready.")
            return True

        missing_critical_fields = False
        for req_field in required_fields:
            is_critical = True 
            if req_field == 'other_service':
                service_type_value = self.form_data.get('service_type', "").strip()
                if service_type_value != 'other':
                    is_critical = False 
            
            current_value = self.form_data.get(req_field)
            if is_critical and (current_value is None or str(current_value).strip() == ""):
                print(f"DEBUG: Critical field '{req_field}' missing or empty after LLM extraction.")
                missing_critical_fields = True
                break 
        
        if not missing_critical_fields:
            print(f"DEBUG: All critical data appears present for category '{self.grievance_category}'. Ready for form filling.")
            return True 
        else:
            print("DEBUG: Critical data still missing. Cannot proceed to form filling yet.")
            return False


    def _extract_dynamic_form_data_llm(self):
        # ... (no changes to _extract_dynamic_form_data_llm)
        if not self.client:
            print("LLM client not available for data extraction. Simulating extraction.")
            sim_data = {}
            if self.grievance_category and self.grievance_category in GRIEVANCE_CATEGORIES:
                for field in GRIEVANCE_CATEGORIES[self.grievance_category].get("required_fields", []):
                    sim_data[field] = self.form_data.get(field, f"Simulated {field}")
            return sim_data

        if not self.grievance_category or self.grievance_category not in GRIEVANCE_CATEGORIES:
            print(f"Error: Cannot extract dynamic form data. Invalid/missing category: {self.grievance_category}")
            return {}

        category_info = GRIEVANCE_CATEGORIES[self.grievance_category]
        required_fields = category_info.get("required_fields", [])
        field_descriptions = category_info.get("field_descriptions", {}) 
        if not required_fields: 
            print(f"Warning: No required fields defined for category {self.grievance_category} for extraction.")
            return {}

        field_prompt_parts = []
        for field in required_fields:
            description = field_descriptions.get(field, f"Extract the user's {field.replace('_', ' ')} from the conversation. If not mentioned, use an empty string.")
            field_prompt_parts.append(f"- \"{field}\": {description}") 
        
        fields_to_extract_prompt_str = "\n".join(field_prompt_parts)
        language_context = self.default_language 
        
        conversation_text_for_extraction = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in self.conversation_history]
        )

        extraction_prompt = f"""Analyze the entire conversation history provided below.
The conversation is in {language_context}. The user is filing a '{self.grievance_category}' grievance.

Conversation History:
{conversation_text_for_extraction}
---
Based *only* on the conversation history above, extract the values for the following fields.
Adhere to specific formatting instructions or value mappings given in each field's description.
If a value for a field was not clearly provided by the user, or is ambiguous according to its description, use an empty string "" for that field's value.
Do NOT invent or assume any information not present in the conversation.
Do NOT include a 'declaration' field in the output JSON.

Fields to extract (ensure keys in JSON are exactly these field names):
{fields_to_extract_prompt_str}

Respond with ONLY a valid JSON object where keys are the field names (e.g., "full_name", "email") and values are the extracted user inputs (as strings).
Example of expected JSON output (content will vary based on conversation): {{"full_name": "Jane Doe", "email": "jane@example.com", "issue_duration": "one_to_four_weeks"}}
"""
        
        print(f"DEBUG: Sending extraction prompt to LLM for category '{self.grievance_category}'.")

        try:
            response = self.client.chat.completions.create(
                model=CHAT_MODEL, 
                messages=[{"role": "user", "content": extraction_prompt}], 
                temperature=0.1, 
                max_tokens=1024, 
                response_format={"type": "json_object"} 
            )
            
            json_text = response.choices[0].message.content.strip()
            print(f"DEBUG: LLM raw output for extraction: {json_text}")
            
            try:
                extracted_data = json.loads(json_text)
            except json.JSONDecodeError as json_e: 
                print(f"DEBUG: Initial JSON parsing failed: {json_e}. Attempting regex fallback.")
                match = re.search(r"\{[\s\S]*\}", json_text) 
                if match:
                    try:
                        extracted_data = json.loads(match.group(0))
                        print("DEBUG: Successfully parsed JSON using regex fallback for extraction.")
                    except json.JSONDecodeError as final_json_e:
                        print(f"DEBUG: Regex fallback for JSON parsing also failed: {final_json_e}. Returning empty for fields.")
                        return {field: "" for field in required_fields} 
                else:
                    print("DEBUG: No JSON object found in LLM output via regex. Returning empty for fields.")
                    return {field: "" for field in required_fields}

            final_data = {field: extracted_data.get(field, "") for field in required_fields}
            print(f"DEBUG: Dynamically extracted data by LLM for confirmation: {final_data}")
            return final_data
            
        except Exception as e:
            print(f"An unexpected error occurred during LLM call for dynamic form data extraction: {e}")
            return {field: "" for field in required_fields} 


    def _create_confirmation_message(self):
        # This method is no longer central to the main flow for form submission,
        # as we are bypassing the full verbal confirmation.
        # It might be used if a specific, minor clarification is needed.
        if self.conversation_stage != "confirming":
            print(f"DEBUG: _create_confirmation_message called when stage is '{self.conversation_stage}' (not 'confirming'). This is unexpected if bypassing full confirm.")
            # Fallback or error handling might be needed if this is hit unexpectedly.
            # For now, let it proceed if called, but it shouldn't be for the full summary.
            # return self._get_llm_response() # This could lead to a loop.

        if not self.form_data:
            print("DEBUG: _create_confirmation_message called for 'confirming' stage, but self.form_data is empty.")
            # This implies an issue if we're trying to confirm something specific.
            self.conversation_stage = "collecting" # Revert to collect if data is missing
            return self._get_llm_response()

        details_summary_parts = []
        category_info = GRIEVANCE_CATEGORIES.get(self.grievance_category, {})
        # For a specific clarification, we wouldn't list ALL fields.
        # This method's original purpose was for the full summary.
        # If used for specific field clarification, it would need to be adapted or a new method created.
        # For now, keeping its original structure for full summary, though it shouldn't be called for that.
        required_fields = category_info.get("required_fields", []) 

        for field in required_fields: 
            value = self.form_data.get(field) 
            field_readable = field.replace("_", " ").capitalize()
            value_readable = f"'{value}'" if str(value).strip() else self._get_localized_string("not_provided_placeholder")
            details_summary_parts.append(f"{field_readable} as {value_readable}")
        
        details_string = "; ".join(details_summary_parts) if details_summary_parts else self._get_localized_string("no_details_collected_placeholder")
        category_readable = (self.grievance_category.replace("_", " ") if self.grievance_category 
                             else self._get_localized_string("default_grievance_name"))
        
        confirmation_prompt = self._get_localized_string("confirmation_summary", category_readable=category_readable, details_string=details_string)
        print(f"DEBUG: Generated confirmation message (likely for specific clarification, not full summary): {confirmation_prompt}")
        return confirmation_prompt

    def _get_localized_string(self, key, **kwargs):
        current_lang = self.default_language if self.default_language in LANGUAGES else "english"
        strings = {
            "initial_greeting": {
                "english": "Hello! I'm your virtual assistant. I can help you file a grievance about infrastructure, corruption, government services, or funding problems. What issue are you facing today?",
                "hindi": "नमस्ते! मैं आपका वर्चुअल सहायक हूँ। मैं आपको बुनियादी ढाँचे, भ्रष्टाचार, सरकारी सेवाओं, या धन संबंधी समस्याओं के बारे में शिकायत दर्ज करने में मदद कर सकता हूँ। आज आप किस समस्या का सामना कर रहे हैं?",
                "tamil": "வணக்கம்! நான் உங்கள் மெய்நிகர் உதவியாளர். உள்கட்டமைப்பு, ஊழல், அரசாங்க சேவைகள் அல்லது நிதிப் பிரச்சனைகள் பற்றிய புகாரைப் பதிவு செய்ய நான் உங்களுக்கு உதவ முடியும். இன்று நீங்கள் என்ன சிக்கலை எதிர்கொள்கிறீர்கள்?",
                "marathi": "नमस्कार! मी तुमचा व्हर्च्युअल सहाय्यक आहे. पायाभूत सुविधा, भ्रष्टाचार, सरकारी सेवा किंवा निधी समस्यांबद्दल तक्रार दाखल करण्यास मी तुम्हाला मदत करू शकेन. आज तुम्हाला कोणती समस्या भेडसावत आहे?",
                "kannada": "ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ ವರ್ಚುವಲ್ ಸಹಾಯಕ. ಮೂಲಸೌಕರ್ಯ, ಭ್ರಷ್ಟಾಚಾರ, ಸರ್ಕಾರಿ ಸೇವೆಗಳು ಅಥವಾ ಹಣಕಾಸಿನ ಸಮಸ್ಯೆಗಳ ಕುರಿತು ದೂರನ್ನು ದಾಖಲಿಸಲು ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ಇಂದು ನೀವು ಯಾವ ಸಮಸ್ಯೆಯನ್ನು ಎದುರಿಸುತ್ತಿದ್ದೀರಿ?"
            },
            "farewell_messages": { 
                "english": ["Goodbye! Have a great day.", "Thanks for chatting. Take care!", "It was nice talking to you. Goodbye!"],
                "hindi": ["अलविदा! आपका दिन शुभ हो।", "बातचीत के लिए धन्यवाद। अपना ख्याल रखना!", "आपसे बात करके अच्छा लगा। अलविदा!"],
            },
            "audio_capture_error": {
                "english": "It seems there was an issue with capturing your audio or I didn't understand. Let's try that again. Could you please repeat?",
                "hindi": "लगता है आपकी आवाज़ पकड़ने में कोई समस्या हुई या मुझे समझ नहीं आया। चलिए फिर से प्रयास करते हैं। क्या आप दोहरा सकते हैं?",
            },
            "submitting_form": { # This string is more for the point when form is being loaded by bot
                "english": "Great! I'll prepare this form for you now. Please review the details on the right and submit it.",
                "hindi": "बहुत बढ़िया! मैं अब आपके लिए यह फ़ॉर्म तैयार करूँगा। कृपया दाईं ओर विवरणों की समीक्षा करें और इसे जमा करें।",
            },
            "direct_to_form_filling_prompt": { # New string
                "english": "Great, I believe I have all the necessary details for your {category_readable} grievance. I'll prepare the form for you to review and submit.",
                "hindi": "बहुत बढ़िया, मुझे लगता है कि आपकी {category_readable} शिकायत के लिए मेरे पास सभी आवश्यक विवरण हैं। मैं आपके लिए फॉर्म तैयार करूँगा ताकि आप समीक्षा करके जमा कर सकें।"
            },
            "form_submitted_successfully": {
                "english": "Your grievance has been noted as submitted. Is there anything else I can help you with today?",
                "hindi": "आपकी शिकायत जमा कर दी गई है। क्या मैं आज आपकी कोई और मदद कर सकता हूँ?",
            },
             "form_filling_prompt": {
                "english": "Please continue filling the form on the right. Let me know if you have questions or when you're done and have submitted it.",
                "hindi": "कृपया दाईं ओर दिए गए फ़ॉर्म को भरते रहें। यदि आपके कोई प्रश्न हैं या जब आप भर चुके हों और जमा कर चुके हों तो मुझे बताएं।",
            },
            "update_information_prompt": {
                "english": "No problem. Let's update your information. What would you like to change or provide first?",
                "hindi": "कोई बात नहीं। चलिए आपकी जानकारी अपडेट करते हैं। आप सबसे पहले क्या बदलना या प्रदान करना चाहेंगे?",
            },
            "category_denied_re_understand": { 
                "english": "My apologies. If '{category}' is not the right category, let's try to understand the issue again.",
                "hindi": "क्षमा करें। यदि '{category}' सही श्रेणी नहीं है, तो चलिए समस्या को फिर से समझने का प्रयास करते हैं।",
            },
            "unhandled_stage_error": {
                "english": "I seem to have lost my place. Let's start over. What issue are you facing?",
                "hindi": "मैं अपनी जगह भूल गया लगता हूँ। चलिए फिर से शुरू करते हैं। आप किस समस्या का सामना कर रहे हैं?",
            },
            "internal_form_details_error": {
                 "english": "Internal error: Form details not found for this category. I'll have to restart our conversation.",
                 "hindi": "आंतरिक त्रुटि: इस श्रेणी के लिए फ़ॉर्म विवरण नहीं मिला। मुझे हमारी बातचीत पुनः आरंभ करनी होगी।"
            },
            "not_provided_placeholder": {"english": "[not provided]", "hindi": "[नहीं बताया गया]", "tamil": "[வழங்கப்படவில்லை]", "marathi": "[प्रदान केलेले नाही]", "kannada": "[ಒದಗಿಸಲಾಗಿಲ್ಲ]"},
            "no_details_collected_placeholder": {"english": "no details collected yet", "hindi": "अभी तक कोई विवरण एकत्र नहीं किया गया है"},
            "default_grievance_name": {"english": "grievance", "hindi": "शिकायत"},
            "some_specific_details_placeholder": {"english": "some specific details", "hindi": "कुछ विशिष्ट विवरण"},
            "none_confirmed_placeholder": {"english": "None explicitly confirmed yet by system", "hindi": "सिस्टम द्वारा अभी तक स्पष्ट रूप से कुछ भी पुष्टि नहीं की गई है"},
            "all_collected_placeholder": {"english": "All seem to be mentioned or collected!", "hindi": "सभी का उल्लेख या संग्रह किया गया लगता है!"},
            "confirmation_summary": { # This is the old summary prompt, less likely to be used for full summary now.
                "english": "Okay, I have the following details for your {category_readable} complaint: {details_string}. Is all this information correct?",
                "hindi": "ठीक है, आपकी {category_readable} शिकायत के लिए मेरे पास ये विवरण हैं: {details_string}। क्या यह सभी जानकारी सही है?",
            },
            "llm_error_collecting": {
                "english": "I'm having a bit of trouble processing that. Could you please repeat or rephrase the last piece of information?",
                "hindi": "मुझे इसे संसाधित करने में थोड़ी परेशानी हो रही है। क्या आप कृपया अंतिम जानकारी दोहरा सकते हैं या उसे दूसरे शब्दों में कह सकते हैं?",
            },
            "llm_error_collecting_after_ready_but_missing": { 
                "english": "It seems I still need a few more details for the {category} form before we can proceed. Could we go over what's missing?",
                "hindi": "लगता है {category} फॉर्म के लिए आगे बढ़ने से पहले मुझे अभी भी कुछ और विवरण चाहिए। क्या हम जो गायब है उस पर बात कर सकते हैं?"
            },
            "llm_error_general": {
                "english": "I'm having some technical difficulties at the moment. Please try again in a short while.",
                "hindi": "मुझे अभी कुछ तकनीकी दिक्कतें आ रही हैं। कृपया थोड़ी देर में पुनः प्रयास करें।",
            },
            "category_identified_prompt": {"english": "Okay, I think this is about {category}.", "hindi": "ठीक है, मुझे लगता है कि यह {category} के बारे में है।"},
            "category_confirmation_prompt": {"english": "Is {category} the correct area for your grievance? We'll need some details if so.", "hindi": "क्या {category} आपकी शिकायत के लिए सही क्षेत्र है? यदि हाँ तो हमें कुछ विवरण चाहिए होंगे।"},
            "ask_for_field_prompt": {"english": "Could you please provide your {field_name}?", "hindi": "क्या आप कृपया अपना {field_name} बता सकते हैं?"},
            "simulated_confirmation_reprompt": {"english": "Is this information correct? Please say yes or no. (Simulated)", "hindi": "क्या यह जानकारी सही है? कृपया हाँ या नहीं कहें। (नकली)"}
        }
        
        lang_specific_message_set = strings.get(key, {})
        message_or_list = lang_specific_message_set.get(current_lang, 
                                                       lang_specific_message_set.get("english", f"[[UNTRANSLATED_KEY_{key.upper()}]]"))
        
        final_message = random.choice(message_or_list) if isinstance(message_or_list, list) and message_or_list else \
                        message_or_list if isinstance(message_or_list, str) else f"[[INVALID_TYPE_FOR_KEY_{key.upper()}]]"

        try:
            safe_kwargs = kwargs.copy()
            if 'category' not in safe_kwargs and '{category}' in final_message: # General category fallback
                safe_kwargs['category'] = self.grievance_category or self._get_localized_string("default_grievance_name")
            if 'category_readable' not in safe_kwargs and '{category_readable}' in final_message:
                 safe_kwargs['category_readable'] = (self.grievance_category.replace("_", " ") if self.grievance_category 
                                                     else self._get_localized_string("default_grievance_name"))

            return final_message.format(**safe_kwargs)
        except KeyError as e: 
            print(f"Warning: Missing kwarg {e} for localized string key '{key}', lang '{current_lang}'. Message: '{final_message}'")
            return final_message


    def _is_affirmative(self, text):
        # ... (no changes to _is_affirmative)
        text_lower = text.lower().strip().rstrip('.,!?;') 
        
        affirmative_terms_map = {
            "english": ["yes", "yeah", "yep", "correct", "right", "sure", "ok", "okay", "alright", "perfect", "sounds good", "looks good", "that's right", "proceed", "continue", "affirmative", "indeed", "certainly", "please do", "go ahead", "absolutely", "fine", "good", "great", "positive"],
            "hindi": ["हाँ", "जी हाँ", "ठीक है", "सही है", "आगे बढ़ें", "जारी रखें", "हाँ जी", "सही", "हाँजी", "जी", "बेशक", "ज़रूर", "अच्छा", "बहुत अच्छा", "सकारात्मक"],
            "tamil": ["ஆம்", "சரி", "சரியானது", "தொடரவும்", "நிச்சயமாக", "கண்டிப்பாக", "நல்லது"],
            "marathi": ["होय", "बरोबर", "ठीक आहे", "पुढे जा", "नक्कीच", "नक्की", "चालेल", "उत्तम"],
            "kannada": ["ಹೌದು", "ಸರಿ", "ಸರಿಯಾಗಿದೆ", "ಮುಂದುವರಿಸಿ", "ಖಂಡಿತ", "ಖಂಡಿತವಾಗಿ", "ಒಳ್ಳೆಯದು"]
        }
        terms_to_check = set(affirmative_terms_map.get(self.default_language, []) + affirmative_terms_map.get("english", []))
        
        if text_lower in terms_to_check:
            print(f"DEBUG: Affirmative match on exact term '{text_lower}' for lang '{self.default_language}'")
            return True
            
        for term in terms_to_check:
            if text_lower.startswith(term + " "):
                print(f"DEBUG: Affirmative match on phrase starting with '{term}' in '{text_lower}' for lang '{self.default_language}'")
                return True
        return False

    def _is_negative(self, text):
        # ... (no changes to _is_negative)
        text_lower = text.lower().strip().rstrip('.,!?;')

        negative_terms_map = {
            "english": ["no", "nope", "not", "incorrect", "wrong", "don't", "do not", "stop", "cancel", "negative", "not right", "that's not it", "don t", "never", "bad", "false"],
            "hindi": ["नहीं", "गलत", "सही नहीं", "मत करो", "रुको", "रद्द करें", "नहीं जी", "ना", "नहींजी", "कभी नहीं", "खराब", "असत्य"],
            "tamil": ["இல்லை", "தவறு", "சரியல்ல", "வேண்டாம்", "நிறுத்து", "ஒருபோதும் இல்லை", "மோசமான"],
            "marathi": ["नाही", "चुकीचे", "बरोबर नाही", "थांबा", "रद्द करा", "कधीच नाही", "वाईट"],
            "kannada": ["ಇಲ್ಲ", "ತಪ್ಪು", "ಸರಿಯಿಲ್ಲ", "ಬೇಡ", "ನಿಲ್ಲಿಸಿ", "ರದ್ದುಮಾಡಿ", "ಎಂದಿಗೂ ಇಲ್ಲ", "ಕೆಟ್ಟದು"]
        }
        terms_to_check = set(negative_terms_map.get(self.default_language, []) + negative_terms_map.get("english", []))

        if text_lower in terms_to_check:
            print(f"DEBUG: Negative match on exact term '{text_lower}' for lang '{self.default_language}'")
            return True

        for term in terms_to_check:
            if text_lower.startswith(term + " "):
                print(f"DEBUG: Negative match on phrase starting with '{term}' in '{text_lower}' for lang '{self.default_language}'")
                return True
        return False
