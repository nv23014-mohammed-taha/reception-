# ai_receptionist_mistral.py

import streamlit as st
import sqlite3
import dateparser
import json
from mistralai.client import MistralClient

# --- SETUP ---
st.title("🤖 AI Healthcare Receptionist (Smart AI Version)")

client = MistralClient(api_key=st.secrets["MISTRAL_API_KEY"])

# --- DATABASE ---
conn = sqlite3.connect("appointments.db", check_same_thread=False)
c = conn.cursor()

c.execute("CREATE TABLE IF NOT EXISTS doctors (id INTEGER PRIMARY KEY, name TEXT)")
c.execute("""
CREATE TABLE IF NOT EXISTS appointments (
id INTEGER PRIMARY KEY,
patient_name TEXT,
doctor_name TEXT,
date TEXT,
time TEXT)
""")
conn.commit()

# Insert doctors
if c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
    c.executemany("INSERT INTO doctors (name) VALUES (?)",
                  [("Dr. Ahmed",), ("Dr. Sara",), ("Dr. Khalid",)])
    conn.commit()

# --- STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Show chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- AI FUNCTION ---
def extract_info(user_input):
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

# --- HELPER ---
def parse_datetime(date_text, time_text):
    dt = dateparser.parse(f"{date_text} {time_text}", languages=["en", "ar"])
    if dt:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    return None, None

# --- CHAT ---
if prompt := st.chat_input("Type here..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    data = extract_info(prompt)

    intent = data.get("intent", "general")
    name = data.get("name")
    doctor = data.get("doctor")
    date = data.get("date")
    time = data.get("time")

    # --- BOOKING ---
    if intent == "book":

        if not name:
            response = "What's your name?"
        elif not date or not time:
            response = "Please provide date and time."
        else:
            parsed_date, parsed_time = parse_datetime(date, time)

            if parsed_date and parsed_time:
                c.execute(
                    "INSERT INTO appointments (patient_name, doctor_name, date, time) VALUES (?, ?, ?, ?)",
                    (name, doctor or "Any Doctor", parsed_date, parsed_time)
                )
                conn.commit()

                response = f"""
✅ Appointment Confirmed!

👤 {name}  
👨‍⚕️ {doctor or "Assigned Doctor"}  
📅 {parsed_date}  
⏰ {parsed_time}
"""
            else:
                response = "I couldn't understand the date/time."

    # --- RESCHEDULE ---
    elif intent == "reschedule":
        response = "Rescheduling feature coming soon."

    # --- CANCEL ---
    elif intent == "cancel":
        response = "Cancellation feature coming soon."

    else:
        response = "I can help with booking. Try: 'Book me with Dr Sara tomorrow at 5pm'"

    with st.chat_message("assistant"):
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
