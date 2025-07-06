// script.js
document.addEventListener('DOMContentLoaded', () => {
    const chatHistory = document.getElementById('chatHistory');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const micButton = document.getElementById('micButton');
    const micStatus = document.getElementById('micStatus');
    const grievanceFormFrame = document.getElementById('grievanceFormFrame');
    const formStatus = document.getElementById('formStatus');

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    // chatbotCurrentLanguage is for browser's synthesis, not directly used if backend TTS works
    // let chatbotCurrentLanguage = 'en-US'; 
    let currentBotLanguageCode = 'en'; // For STT hint & backend TTS language context

    // --- Audio Playback for Backend TTS ---
    let currentBotAudio = null; // To manage the audio object

    const playBackendAudio = (audioUrl) => {
        if (currentBotAudio) {
            currentBotAudio.pause(); // Stop any currently playing audio
        }
        currentBotAudio = new Audio(audioUrl);
        currentBotAudio.play()
            .catch(error => console.error("Error playing backend audio:", error));
    };

    // --- Web Speech API (Speech Synthesis for bot responses - FALLBACK ONLY) ---
    const speakWithBrowser = (text, lang = 'en-US') => {
        if ('speechSynthesis' in window) {
            if (speechSynthesis.speaking) {
                speechSynthesis.cancel();
            }
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = lang;
            const voices = speechSynthesis.getVoices();
            let selectedVoice = voices.find(voice => voice.lang === lang && voice.default);
            if (!selectedVoice) {
                selectedVoice = voices.find(voice => voice.lang === lang);
            }
            if (selectedVoice) {
                utterance.voice = selectedVoice;
            }
            speechSynthesis.speak(utterance);
        } else {
            console.warn('Browser speech synthesis not supported.');
        }
    };

    if ('speechSynthesis' in window && speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = () => {
            console.log("Browser speech synthesis voices loaded.");
        };
    }


    const addMessageToHistory = (text, sender, audioUrl = null) => {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender === 'user' ? 'user-msg' : 'bot-msg', 'break-words');
        messageDiv.textContent = text;
        chatHistory.appendChild(messageDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        if (sender === 'bot') {
            if (audioUrl) {
                playBackendAudio(audioUrl);
            } else {
                // Fallback to browser TTS if no audio_url (e.g., error in backend TTS)
                console.warn("No audio_url from backend, falling back to browser TTS for bot message.");
                const browserLang = mapLangCodeToBrowserTTS(currentBotLanguageCode);
                speakWithBrowser(text, browserLang);
            }
        }
    };
    
    const mapLangCodeToBrowserTTS = (langCode) => {
        const mapping = {
            "en": "en-US", "hi": "hi-IN", "ta": "ta-IN", "mr": "mr-IN", "kn": "kn-IN",
        };
        return mapping[langCode.toLowerCase()] || langCode; 
    };
    
    const updateChatbotLanguage = (langCode) => {
        currentBotLanguageCode = langCode; 
        console.log(`Chatbot language context updated to: '${currentBotLanguageCode}'`);
    };


    const initializeChat = async () => {
        let initUrl = '/init_grievance_chat'; 
        if (window.location.pathname.includes('/schemes')) { 
            initUrl = '/init_scheme_chat';
        }

        try {
            const response = await fetch(initUrl, { method: 'POST' });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            
            chatHistory.innerHTML = '';
            
            // For init, history messages won't have audio_url, they are just text history
            if (data.history && data.history.length > 0) {
                data.history.forEach(msg => {
                     // Only add text for past history, no audio playback
                     const messageDiv = document.createElement('div');
                     messageDiv.classList.add('message', msg.role === 'user' ? 'user-msg' : 'bot-msg', 'break-words');
                     messageDiv.textContent = msg.content;
                     chatHistory.appendChild(messageDiv);
                });
                chatHistory.scrollTop = chatHistory.scrollHeight;
            }
            
            // Handle the initial bot response (greeting)
            if(data.bot_response) {
                 if (data.language) { 
                    updateChatbotLanguage(data.language);
                 }
                 addMessageToHistory(data.bot_response, 'bot', data.audio_url); // Pass audio_url
            }
            userInput.focus();
        } catch (error) {
            console.error('Error initializing chat:', error);
            addMessageToHistory('Error initializing chat. Please refresh.', 'bot'); // No audio for this error
        }
    };
    

    const sendMessage = async (messageText) => {
        if (!messageText.trim()) return;

        addMessageToHistory(messageText, 'user'); // User message has no audio_url
        userInput.value = '';

        try {
            const response = await fetch('/send_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageText, language: currentBotLanguageCode }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorData.detail || errorData.error || "Failed to get response"}`);
            }
            
            const data = await response.json();

            if (data.bot_response) {
                if (data.language) { 
                    updateChatbotLanguage(data.language);
                }
                // Add bot message to history, with audio_url if present
                addMessageToHistory(data.bot_response, 'bot', data.audio_url);
            }

            // Handle actions like loading forms
            if (data.action === 'LOAD_FORM' && data.form_url) {
                formStatus.textContent = `Loading ${data.form_type || 'grievance'} form...`;
                grievanceFormFrame.src = data.form_url;

                grievanceFormFrame.onload = () => {
                    formStatus.textContent = `${data.form_type || 'Grievance'} form loaded.`;
                    if (data.form_data && Object.keys(data.form_data).length > 0) {
                        grievanceFormFrame.contentWindow.postMessage({
                            type: 'PREFILL_FORM',
                            payload: data.form_data
                        }, window.location.origin);
                        formStatus.textContent += ' Form data pre-filled.';
                    }
                };
            } else if (data.action === 'FORM_SUBMITTED') {
                formStatus.textContent = `Form submission confirmed. Thank you!`;
                grievanceFormFrame.src = 'about:blank';
            } else if (data.action === 'END_CONVERSATION') {
                formStatus.textContent = "Conversation ended.";
            }

        } catch (error) {
            console.error('Error sending message:', error);
            // For error messages from JS side, use browser TTS or just text
            const browserLang = mapLangCodeToBrowserTTS(currentBotLanguageCode);
            speakWithBrowser(`Error: ${error.message || 'Could not connect to the bot.'}`, browserLang);
            addMessageToHistory(`Error: ${error.message || 'Could not connect to the bot.'}`, 'bot');
        }
    };

    // --- MediaRecorder Setup for STT ---
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        micButton.addEventListener('click', () => {
            if (!isRecording) {
                startRecording();
            } else {
                stopRecording();
            }
        });
    } else {
        console.error('getUserMedia not supported!');
        micButton.disabled = true;
        micStatus.textContent = 'Microphone not supported.';
    }

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mimeTypes = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/wav', 'audio/mp4', 'audio/webm'];
            let selectedMimeType = mimeTypes.find(type => MediaRecorder.isTypeSupported(type)) || 'audio/webm';
            
            mediaRecorder = new MediaRecorder(stream, { mimeType: selectedMimeType });
            mediaRecorder.onstart = () => {
                audioChunks = []; isRecording = true;
                micStatus.textContent = 'Listening... Click mic to stop.';
                micButton.classList.add('bg-red-600', 'hover:bg-red-700');
                micButton.classList.remove('bg-green-600', 'hover:bg-green-700');
            };
            mediaRecorder.ondataavailable = event => { audioChunks.push(event.data); };
            mediaRecorder.onstop = async () => {
                isRecording = false;
                micStatus.textContent = 'Processing...';
                micButton.classList.remove('bg-red-600', 'hover:bg-red-700');
                micButton.classList.add('bg-green-600', 'hover:bg-green-700');
                const audioBlob = new Blob(audioChunks, { type: selectedMimeType });
                audioChunks = [];
                if (stream) stream.getTracks().forEach(track => track.stop());
                if (audioBlob.size === 0) {
                    micStatus.textContent = "No audio. Click mic to speak."; return;
                }
                const formData = new FormData();
                formData.append('audio_file', audioBlob, 'user_audio.' + selectedMimeType.split('/')[1].split(';')[0]);
                formData.append('language', currentBotLanguageCode);
                try {
                    micStatus.textContent = 'Transcribing...';
                    const response = await fetch('/transcribe_audio', { method: 'POST', body: formData });
                    if (!response.ok) {
                        const errData = await response.json().catch(() => ({ error: "Transcription failed" }));
                        throw new Error(errData.error || `Service error: ${response.status}`);
                    }
                    const data = await response.json();
                    if (data.transcript) {
                        userInput.value = data.transcript; sendMessage(data.transcript);
                        micStatus.textContent = 'Click mic to speak';
                    } else if (data.error) { throw new Error(data.error); }
                    else { micStatus.textContent = 'No transcript. Try again.'; }
                } catch (error) {
                    console.error('Error transcribing audio:', error);
                    micStatus.textContent = `Transcription Error. Try again.`;
                    addMessageToHistory(`STT Error: ${error.message}`, 'bot'); // No audio for this error
                }
            };
            mediaRecorder.start();
        } catch (err) {
            console.error('Mic error:', err);
            micStatus.textContent = 'Mic access denied or error.';
        }
    }
    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
    }

    sendButton.addEventListener('click', () => sendMessage(userInput.value));
    userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(userInput.value); });
    initializeChat();
    window.addEventListener('message', (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data && event.data.type === 'FORM_SUBMITTED_IN_IFRAME') {
            formStatus.textContent = `Form submitted: ${event.data.payload.message}`;
            // For this system message, use browser TTS or just text
            addMessageToHistory(`The ${event.data.payload.formType || 'grievance'} form has been submitted.`, 'bot');
            grievanceFormFrame.src = 'about:blank';
        }
    });
});
