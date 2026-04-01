# final_receptionist.py
import pandas as pd
import os
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import dateparser
import sqlite3
import zipfile

# --- 1. UI ---
st.title("🤖 AI Healthcare Receptionist")
st.markdown("Supports booking with English & Arabic dates.")

# --- 2. LOAD DATA FROM ZIP ONLY ---
dataset_zip = "healthcare-appointment-booking-calls-dataset.zip"

model = None

if os.path.exists(dataset_zip):
    with zipfile.ZipFile(dataset_zip, 'r') as zip_ref:
        csv_files = [f for f in zip_ref.namelist() if f.endswith(".csv")]
        if csv_files:
            with zip_ref.open(csv_files[0]) as f:
                df = pd.read_csv(f)
                df = df[['Transcription', 'Action']].dropna()

                if len(df) > 0:
                    model = make_pipeline(TfidfVectorizer(), MultinomialNB())
                    model.fit(df['Transcription'], df['Action'])
                    st.success("✅ Model loaded successfully!")
                else:
                    st.error("Dataset is empty.")
        else:
            st.error("No CSV found in ZIP.")
else:
    st.error("ZIP file not found.")

# --- 3. DATABASE ---
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

# Add doctors
if c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
    c.executemany("INSERT INTO doctors (name) VALUES (?)",
                  [("Dr. Ahmed",), ("Dr. Sara",), ("Dr. Khalid",)])
    conn.commit()

# --- 4. STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "stage" not in st.session_state:
    st.session_state.stage = "start"
if "data" not in st.session_state:
    st.session_state.data = {}

# Show chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 5. FUNCTIONS ---
def get_intent(text):
    if model:
        return model.predict([text])[0]
    return "General"

def extract_datetime(text):
    return dateparser.parse(text, languages=["en", "ar"])

def get_available_doctor(date, time):
    booked = [r[0] for r in c.execute(
        "SELECT doctor_id FROM appointments WHERE date=? AND time=?", (date, time)
    ).fetchall()]

    doctors = c.execute("SELECT id, name FROM doctors").fetchall()

    for doc_id, name in doctors:
        if doc_id not in booked:
            return doc_id, name
    return None, None

# --- 6. CHAT ---
if prompt := st.chat_input("Type here..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent = get_intent(prompt)

    # 🔥 CONTINUE FLOW FIRST
    if st.session_state.stage != "start":

        if st.session_state.stage == "name":
            st.session_state.data["name"] = prompt
            st.session_state.stage = "date"
            response = "What date?"

        elif st.session_state.stage == "date":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.data["date"] = dt.strftime("%Y-%m-%d")
                st.session_state.stage = "time"
                response = "What time?"
            else:
                response = "Please give a valid date (e.g. tomorrow)."

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
                    response = "No doctors available. Choose another time."
            else:
                response = "Please give a valid time."

    # 🔥 START FLOW
    else:
        if "Appointment" in intent or "book" in prompt.lower():
            st.session_state.stage = "name"
            response = "Let's book. What's your name?"

        elif "Reschedule" in intent:
            response = "Rescheduling not implemented yet."

        else:
            response = "I can help with booking. Try saying 'book appointment'."

    # Display response
    with st.chat_message("assistant"):
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
