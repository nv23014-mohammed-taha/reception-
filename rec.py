# final_receptionist_json.py

import pandas as pd
import os
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import dateparser
import sqlite3
import json

# --- UI ---
st.title("🤖 AI Healthcare Receptionist")

# --- LOAD JSON DATA ---
json_path = "archive (8).json"   # ← your file name

model = None

if os.path.exists(json_path):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        df = pd.DataFrame(data)

        # 🔥 AUTO-DETECT COLUMNS
        text_col = None
        label_col = None

        for col in df.columns:
            if "text" in col.lower() or "transcription" in col.lower():
                text_col = col
            if "action" in col.lower() or "label" in col.lower():
                label_col = col

        if text_col and label_col:
            df = df[[text_col, label_col]].dropna()
            df.columns = ["text", "label"]

            if len(df) > 0:
                model = make_pipeline(TfidfVectorizer(), MultinomialNB())
                model.fit(df["text"], df["label"])
                st.success("✅ Model trained from JSON!")
            else:
                st.error("Dataset is empty.")
        else:
            st.warning("⚠️ Could not detect columns automatically. Using fallback mode.")
            model = None

    except Exception as e:
        st.error(f"Error loading JSON: {e}")
        model = None
else:
    st.error("JSON file not found.")

# --- DATABASE ---
conn = sqlite3.connect("appointments.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    doctor_id INTEGER,
    date TEXT,
    time TEXT
)
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
if "stage" not in st.session_state:
    st.session_state.stage = "start"
if "data" not in st.session_state:
    st.session_state.data = {}

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- FUNCTIONS ---
def get_intent(text):
    # 🔥 fallback keywords ALWAYS WORK
    text_lower = text.lower()

    if "book" in text_lower or "appointment" in text_lower:
        return "Appointment"
    if "reschedule" in text_lower:
        return "Reschedule"

    if model:
        try:
            return model.predict([text])[0]
        except:
            return "General"

    return "General"

def extract_datetime(text):
    return dateparser.parse(text, languages=["en", "ar"])

def get_available_doctor(date, time):
    booked = [r[0] for r in c.execute(
        "SELECT doctor_id FROM appointments WHERE date=? AND time=?",
        (date, time)
    ).fetchall()]

    doctors = c.execute("SELECT id, name FROM doctors").fetchall()

    for doc_id, name in doctors:
        if doc_id not in booked:
            return doc_id, name

    return None, None

# --- CHAT ---
if prompt := st.chat_input("Type here..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent = get_intent(prompt)

    # 🔥 CONTINUE FLOW
    if st.session_state.stage != "start":

        if st.session_state.stage == "name":
            st.session_state.data["name"] = prompt
            st.session_state.stage = "date"
            response = "What date would you like?"

        elif st.session_state.stage == "date":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.data["date"] = dt.strftime("%Y-%m-%d")
                st.session_state.stage = "time"
                response = "What time?"
            else:
                response = "Please enter a valid date (e.g. tomorrow)."

        elif st.session_state.stage == "time":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.data["time"] = dt.strftime("%H:%M")

                d = st.session_state.data
                doc_id, doc_name = get_available_doctor(d["date"], d["time"])

                if doc_id:
                    c.execute(
                        "INSERT INTO appointments (patient_name, doctor_id, date, time) VALUES (?, ?, ?, ?)",
                        (d["name"], doc_id, d["date"], d["time"])
                    )
                    conn.commit()

                    response = f"""
✅ Appointment Confirmed!

👤 {d['name']}  
👨‍⚕️ {doc_name}  
📅 {d['date']}  
⏰ {d['time']}
"""
                    st.session_state.stage = "start"
                    st.session_state.data = {}
                else:
                    response = "No doctors available. Try another time."
            else:
                response = "Please enter a valid time."

    # 🔥 START FLOW
    else:
        if intent == "Appointment":
            st.session_state.stage = "name"
            response = "Let's book your appointment. What's your name?"

        elif intent == "Reschedule":
            response = "Rescheduling not implemented yet."

        else:
            response = "I can help with booking. Try saying 'book appointment'."

    with st.chat_message("assistant"):
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
