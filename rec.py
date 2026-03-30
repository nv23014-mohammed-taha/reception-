# --- 3. PREDICTION + SMART RESPONSE SYSTEM ---

import dateparser

def get_intent_and_confidence(text):
    probs = model.predict_proba([text])[0]
    confidence = max(probs)
    intent = model.classes_[probs.argmax()]
    return intent, confidence

# Conversation state
if "stage" not in st.session_state:
    st.session_state.stage = "start"
if "appointment_data" not in st.session_state:
    st.session_state.appointment_data = {}

# Helper: extract date/time automatically
def extract_datetime(text):
    dt = dateparser.parse(text)
    return dt

# React to user input
if prompt := st.chat_input("How can I help you today?"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent, confidence = get_intent_and_confidence(prompt)

    # 🔥 PRIORITY: CONTINUE FLOW (ignore intent if mid-process)
    if st.session_state.stage != "start":

        if st.session_state.stage == "get_name":
            st.session_state.appointment_data["name"] = prompt
            response = "Great. What date would you like?"
            st.session_state.stage = "get_date"

        elif st.session_state.stage == "get_date":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.appointment_data["date"] = dt.strftime("%Y-%m-%d")
                response = "Nice. What time works best for you?"
                st.session_state.stage = "get_time"
            else:
                response = "I couldn’t understand the date. Please say something like 'tomorrow' or 'March 25'."

        elif st.session_state.stage == "get_time":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.appointment_data["time"] = dt.strftime("%H:%M")

                data = st.session_state.appointment_data
                response = f"""
✅ Appointment Confirmed!

👤 Name: {data['name']}  
📅 Date: {data['date']}  
⏰ Time: {data['time']}  

You're all set. Anything else I can help with?
"""
                st.session_state.stage = "start"
                st.session_state.appointment_data = {}
            else:
                response = "Please provide a valid time like '5 PM' or '14:30'."

    # --- START NEW FLOW ---
    else:
        if confidence < 0.6:
            response = "I'm not fully sure I understood. Do you want to book, reschedule, or ask something else?"

        elif "Appointment" in intent:
            response = "Sure! Let's book your appointment. What's your name?"
            st.session_state.stage = "get_name"

        elif "Reschedule" in intent:
            response = "Sure, I can help reschedule your appointment. Please provide your booking ID."

        else:
            response = "I can help with booking, rescheduling, or general questions. What do you need?"

    # Display assistant response
    with st.chat_message("assistant"):
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
