# ai_receptionist_mistral.py
import streamlit as st
import sqlite3
import dateparser
import json
from mistral_sdk import MistralClient

# --- 1. STREAMLIT SETUP ---
st.set_page_config(page_title="🤖 AI Healthcare Receptionist", page_icon="🤖")
st.title("🤖 AI Healthcare Receptionist")
st.markdown("Supports **booking appointments** with doctors and automatically handles **English & Arabic dates**.")

# --- 2. MISTRAL AI SETUP ---
# Make sure to add your API key in Streamlit secrets as:
# [MISTRAL_API_KEY] = "your_key_here"
client = MistralClient(api_key=st.secrets["MISTRAL_API_KEY"])

# --- 3. DATABASE SETUP ---
conn = sqlite3.connect("appointments.db", check_same_thread=False)
c = conn.cursor()

# Doctors table
c.execute("""
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
)
""")

# Appointments table
c.execute("""
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    doctor_name TEXT,
    date TEXT,
    time TEXT
)
""")
conn.commit()

# Add default doctors if empty
if c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
    c.executemany("INSERT INTO doctors (name) VALUES (?)", 
                  [("Dr. Ahmed",), ("Dr. Sara",), ("Dr. Khalid",)])
    conn.commit()

# --- 4. SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 5. HELPER FUNCTIONS ---
def extract_info(user_input):
    """
    Ask Mistral AI to extract structured info: intent, name, doctor, date, time.
    Returns a dictionary.
    """
    prompt = f"""
You are a smart AI healthcare receptionist.
Extract the following from the message:
- intent (book, reschedule, cancel, general)
- patient name
- doctor name
- date
- time

Return ONLY JSON like:
{{
"intent": "",
"name": "",
"doctor": "",
"date": "",
"time": ""
}}

User: {user_input}
"""
    response = client.chat(
        model="mistral-small",
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        return json.loads(response.choices[0].message.content)
    except:
        return {"intent": "general"}

def parse_datetime(date_text, time_text):
    """
    Convert English or Arabic date/time text into standard YYYY-MM-DD and HH:MM.
    """
    dt = dateparser.parse(f"{date_text} {time_text}", languages=["en", "ar"])
    if dt:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    return None, None

def list_doctors():
    """
    Return list of all doctor names from DB.
    """
    return [row[0] for row in c.execute("SELECT name FROM doctors").fetchall()]

# --- 6. DISPLAY CHAT HISTORY ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 7. CHAT INPUT HANDLER ---
if prompt := st.chat_input("Type your message here..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Extract structured info from Mistral AI
    data = extract_info(prompt)
    intent = data.get("intent", "general")
    name = data.get("name")
    doctor = data.get("doctor")
    date = data.get("date")
    time = data.get("time")

    # --- BOOKING LOGIC ---
    if intent == "book":
        # Ask for missing info interactively
        if not name:
            response = "What's your name?"
        elif not date or not time:
            response = "Please provide date and time for your appointment."
        else:
            parsed_date, parsed_time = parse_datetime(date, time)
            if parsed_date and parsed_time:
                # Assign doctor automatically if not provided
                if not doctor:
                    doctor_list = list_doctors()
                    doctor = doctor_list[0] if doctor_list else "Any Doctor"

                c.execute(
                    "INSERT INTO appointments (patient_name, doctor_name, date, time) VALUES (?, ?, ?, ?)",
                    (name, doctor, parsed_date, parsed_time)
                )
                conn.commit()

                response = f"""
✅ Appointment Confirmed!

👤 Patient: {name}  
👨‍⚕️ Doctor: {doctor}  
📅 Date: {parsed_date}  
⏰ Time: {parsed_time}
"""
            else:
                response = "I couldn't understand the date/time. Please try again in English or Arabic."

    # --- RESCHEDULE / CANCEL LOGIC ---
    elif intent == "reschedule":
        response = "Rescheduling feature coming soon."
    elif intent == "cancel":
        response = "Cancellation feature coming soon."

    # --- GENERAL / FALLBACK ---
    else:
        response = "I can help you book an appointment. Try: 'Book me with Dr Sara tomorrow at 5pm'"

    # Display AI response
    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
