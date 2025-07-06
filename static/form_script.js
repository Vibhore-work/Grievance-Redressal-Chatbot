/**
 * form_script.js
 * This script runs inside the iframed grievance forms.
 * It handles:
 * 1. Listening for 'PREFILL_FORM' messages from the parent window to populate form fields.
 * 2. Submitting the form data to the backend API ('/submit_grievance').
 * 3. Sending a 'FORM_SUBMITTED_IN_IFRAME' message back to the parent window upon successful submission.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Attempt to find the form on the page. Most of your forms use id="govForm".
    const form = document.getElementById('govForm') || document.querySelector('form');
    const pageFormType = identifyFormType(); // Identify form type based on URL or specific fields

    if (form) {
        console.log(`Form Script: Initialized for form type: ${pageFormType}. Waiting for prefill or submission.`);

        form.addEventListener('submit', function(event) {
            event.preventDefault(); // Prevent default HTML form submission
            console.log('Form Script: Submission initiated by user.');

            const formData = new FormData(this);
            const formDataObject = {};

            // Convert FormData to a plain object
            // Handle multi-selects and checkboxes correctly if necessary
            formData.forEach((value, key) => {
                if (formDataObject.hasOwnProperty(key)) {
                    if (!Array.isArray(formDataObject[key])) {
                        formDataObject[key] = [formDataObject[key]];
                    }
                    formDataObject[key].push(value);
                } else {
                    // For checkboxes not checked, FormData doesn't include them.
                    // If you need to send 'false' or 'off', you might need to handle them differently
                    // by checking all input[type=checkbox] elements.
                    // For now, only checked values are sent by FormData.
                    formDataObject[key] = value;
                }
            });
            
            // Ensure declaration checkbox value is 'True' or 'False' string if it exists
            // The backend Python script for form filling (automate.py) expected "True" for declaration.
            if (form.querySelector('input[name="declaration"]')) {
                const declarationCheckbox = form.querySelector('input[name="declaration"]');
                formDataObject["declaration"] = declarationCheckbox.checked ? "True" : "False";
            }


            console.log('Form Script: Form data collected:', formDataObject);

            // Submit the form data to the main application's backend
            fetch('/submit_grievance', { // Ensure this endpoint is correct in your Flask app
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formDataObject),
            })
            .then(response => {
                if (!response.ok) {
                    // Try to get error message from response body
                    return response.json().then(errData => {
                        throw new Error(errData.error || `Network response was not ok: ${response.status}`);
                    }).catch(() => {
                        // If parsing error data fails, throw generic error
                        throw new Error(`Network response was not ok: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                console.log('Form Script: Submission successful:', data);
                alert('Form submitted successfully!'); // User feedback within iframe

                // Notify the parent window (main chat interface) about the submission
                if (window.parent && window.parent !== window) {
                    window.parent.postMessage({
                        type: 'FORM_SUBMITTED_IN_IFRAME',
                        payload: {
                            message: data.message || 'Form submitted.',
                            formType: pageFormType, // Send identified form type
                            formData: formDataObject // Optionally send submitted data back
                        }
                    }, '*'); // IMPORTANT: In production, specify the parent window's origin instead of '*'
                }
            })
            .catch(error => {
                console.error('Form Script: Error during form submission:', error);
                alert(`There was an error submitting the form: ${error.message}. Please try again.`);
            });
        });
    } else {
        console.error('Form Script: No form element found on this page.');
    }

    // Listen for messages from the parent window (e.g., to pre-fill the form)
    window.addEventListener('message', (event) => {
        // IMPORTANT: Add origin check for security in production!
        // Example: if (event.origin !== 'http://your-main-app-domain.com') return;
        console.log('Form Script: Message received from parent:', event.data);

        if (event.data && event.data.type === 'PREFILL_FORM' && event.data.payload) {
            const formDataToPrefill = event.data.payload;
            console.log('Form Script: Attempting to prefill form with data:', formDataToPrefill);
            prefillForm(formDataToPrefill);
        }
    });

    /**
     * Prefills the form fields based on the provided data object.
     * @param {object} data - An object where keys are field names and values are the data to fill.
     */
    function prefillForm(data) {
        if (!form) return;

        for (const fieldName in data) {
            if (data.hasOwnProperty(fieldName)) {
                const value = data[fieldName];
                // Try to find element by name. Your forms mostly use name attributes.
                const elements = form.querySelectorAll(`[name="${fieldName}"]`);

                if (elements.length > 0) {
                    elements.forEach(element => {
                        const tagName = element.tagName.toLowerCase();
                        const type = element.type ? element.type.toLowerCase() : '';

                        console.log(`Form Script: Prefilling field '${fieldName}', Tag: '${tagName}', Type: '${type}', Value: '${value}'`);

                        if (tagName === 'select') {
                            // Attempt to select by value. If value is an array, try each.
                            const valuesToSelect = Array.isArray(value) ? value : [value];
                            let optionSet = false;
                            for (const val of valuesToSelect) {
                                for (let i = 0; i < element.options.length; i++) {
                                    if (element.options[i].value === String(val)) {
                                        element.selectedIndex = i;
                                        optionSet = true;
                                        break;
                                    }
                                }
                                if (optionSet) break;
                            }
                             if (!optionSet) { // Fallback: try to match by text content if value match fails
                                for (const val of valuesToSelect) {
                                    for (let i = 0; i < element.options.length; i++) {
                                        if (element.options[i].text === String(val)) {
                                            element.selectedIndex = i;
                                            optionSet = true;
                                            break;
                                        }
                                    }
                                     if (optionSet) break;
                                }
                            }
                            if (optionSet) {
                                console.log(`Form Script: Set select '${fieldName}' to '${value}'`);
                                // Trigger change event for any dependent JS (like showing 'other_service' field)
                                element.dispatchEvent(new Event('change', { bubbles: true }));
                            } else {
                                console.warn(`Form Script: Option '${value}' not found for select '${fieldName}'.`);
                            }

                        } else if (tagName === 'textarea') {
                            element.value = value;
                        } else if (tagName === 'input') {
                            if (type === 'checkbox') {
                                // Value can be boolean true/false or string "true"/"false", "on"/"off", "1"/"0"
                                element.checked = (
                                    String(value).toLowerCase() === 'true' ||
                                    String(value).toLowerCase() === 'on' ||
                                    String(value) === '1' ||
                                    value === true // handles boolean true
                                );
                            } else if (type === 'radio') {
                                // For radio buttons, check the one whose value matches
                                if (element.value === String(value)) {
                                    element.checked = true;
                                }
                            } else if (type === 'file') {
                                console.warn(`Form Script: Prefilling file input '${fieldName}' is not directly possible for security reasons. Value was: '${value}'`);
                                // You can't programmatically set the value of a file input.
                                // You could display the filename as text next to it if needed.
                            }
                            else { // text, email, tel, date, number, etc.
                                element.value = value;
                            }
                        } else {
                            console.warn(`Form Script: Unhandled element tag '${tagName}' for field '${fieldName}'.`);
                        }
                    });
                } else {
                    console.warn(`Form Script: Form field with name "${fieldName}" not found in this form.`);
                }
            }
        }
        console.log('Form Script: Prefill attempt complete.');
    }

    /**
     * Tries to identify the type of form currently loaded in the iframe.
     * This can be based on the URL or presence of unique field names.
     * @returns {string} A string representing the form type (e.g., "infrastructure", "corruption").
     */
    function identifyFormType() {
        const path = window.location.pathname.toLowerCase();
        if (path.includes("infrastructure")) return "infrastructure";
        if (path.includes("corruption")) return "corruption";
        if (path.includes("funds")) return "funds";
        if (path.includes("govt_service")) return "government_service";

        // Fallback: check for unique field names if URL is not distinctive
        if (form) {
            if (form.querySelector('[name="issue_location"]')) return "infrastructure";
            if (form.querySelector('[name="official_name"]')) return "corruption";
            if (form.querySelector('[name="scheme_name"]')) return "funds";
            if (form.querySelector('[name="service_type"]')) return "government_service";
        }
        return "unknown_form"; // Default if type cannot be identified
    }

    // Special handling for forms like 'govt_service_form.html' that might have dynamic fields
    // e.g., showing 'other_service' text input when 'service_type' select is 'other'.
    // This ensures that if prefill sets 'service_type' to 'other', the dependent field becomes visible.
    const serviceTypeSelect = document.getElementById('service_type');
    if (serviceTypeSelect) {
        serviceTypeSelect.addEventListener('change', function() {
            const otherDiv = document.getElementById('other_service_div'); // As in govt_service_form.html
            const otherInput = document.getElementById('other_service');
            if (otherDiv && otherInput) {
                if (this.value === 'other') {
                    otherDiv.style.display = 'block';
                    otherInput.required = true;
                } else {
                    otherDiv.style.display = 'none';
                    otherInput.required = false;
                    otherInput.value = ''; // Clear if not 'other'
                }
            }
        });
        // Trigger change event once at load, in case prefill already set it to 'other'
        // but prefillForm might run after this specific event listener is attached.
        // The prefillForm function now also dispatches a change event for selects.
    }

});
