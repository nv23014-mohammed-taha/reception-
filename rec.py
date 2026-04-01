# robust_receptionist.py
import pandas as pd
import os
import glob
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import kagglehub
import dateparser
import sqlite3

# --- 1. DATA & MODEL SETUP ---
st.title("🤖 AI Healthcare Receptionist")
st.markdown("Local NLP model trained on clinical call data. Supports Arabic & English dates.")

# Download dataset from Kaggle
path = kagglehub.dataset_download("ammarshafiq/healthcare-appointment-booking-calls-dataset")
csv_files = glob.glob(os.path.join(path, "*.csv"))

if csv_files:
    df = pd.read_csv(csv_files[0])
    df = df[['Transcription', 'Action']].dropna()
    if len(df) == 0:
        st.warning("Dataset is empty. Model will not work properly.")
    model = make_pipeline(TfidfVectorizer(), MultinomialNB())
    model.fit(df['Transcription'], df['Action'])
else:
    st.warning("Dataset not found. Using fallback (intent detection may fail).")
    model = None

# --- 2. DATABASE SETUP ---
conn = sqlite3.connect("appointments.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    specialty TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    doctor_id INTEGER,
    date TEXT,
    time TEXT,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
)
""")
conn.commit()

# Add sample doctors if table empty
if c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
    c.executemany("INSERT INTO doctors (name, specialty) VALUES (?, ?)",
                  [("Dr. Ahmed", "General"),
                   ("Dr. Sara", "Dermatology"),
                   ("Dr. Khalid", "Cardiology")])
    conn.commit()

# --- 3. SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "stage" not in st.session_state:
    st.session_state.stage = "start"
if "appointment_data" not in st.session_state:
    st.session_state.appointment_data = {}

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. HELPER FUNCTIONS ---
def get_intent_and_confidence(text):
    if model:
        try:
            probs = model.predict_proba([text])[0]
            confidence = max(probs)
            intent = model.classes_[probs.argmax()]
        except Exception:
            # fallback if predict_proba fails
            intent = model.predict([text])[0]
            confidence = 1.0
    else:
        intent = "General"
        confidence = 1.0
    return intent, confidence

def extract_datetime(text):
    dt = dateparser.parse(text, languages=["en", "ar"])
    return dt

def available_doctors(date, time):
    booked_ids = [row[0] for row in c.execute(
        "SELECT doctor_id FROM appointments WHERE date=? AND time=?", (date, time)
    ).fetchall()]
    all_doctors = c.execute("SELECT id, name FROM doctors").fetchall()
    free_docs = [(doc_id, name) for doc_id, name in all_doctors if doc_id not in booked_ids]
    return free_docs

# --- 5. CHAT INPUT HANDLER ---
if prompt := st.chat_input("How can I help you today?"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent, confidence = get_intent_and_confidence(prompt)

    # CONTINUE FLOW IF MID-APPOINTMENT
    if st.session_state.stage != "start":

        if st.session_state.stage == "get_name":
            st.session_state.appointment_data["patient_name"] = prompt
            response = "Great. What date would you like for your appointment?"
            st.session_state.stage = "get_date"

        elif st.session_state.stage == "get_date":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.appointment_data["date"] = dt.strftime("%Y-%m-%d")
                response = "Got it. What time works best for you?"
                st.session_state.stage = "get_time"
            else:
                response = "I couldn’t understand the date. Please say something like 'tomorrow' or 'March 25' (English or Arabic)."

        elif st.session_state.stage == "get_time":
            dt = extract_datetime(prompt)
            if dt:
                st.session_state.appointment_data["time"] = dt.strftime("%H:%M")
                date = st.session_state.appointment_data["date"]
                time = st.session_state.appointment_data["time"]
                free_docs = available_doctors(date, time)
                if free_docs:
                    doc_id, doc_name = free_docs[0]
                    st.session_state.appointment_data["doctor_id"] = doc_id
                    c.execute("INSERT INTO appointments (patient_name, doctor_id, date, time) VALUES (?, ?, ?, ?)",
                              (st.session_state.appointment_data["patient_name"], doc_id, date, time))
                    conn.commit()
                    response = f"""
✅ Appointment Confirmed!

👤 Patient: {st.session_state.appointment_data['patient_name']}  
👨‍⚕️ Doctor: {doc_name}  
📅 Date: {date}  
⏰ Time: {time}  

Anything else I can help with?
"""
                    st.session_state.stage = "start"
                    st.session_state.appointment_data = {}
                else:
                    response = "Sorry, no doctors are available at that date and time. Please choose another slot."
            else:
                response = "Please provide a valid time like '5 PM' or '14:30'."

    # START NEW FLOW
    else:
        if confidence < 0.6:
            response = "I’m not sure I understood. Do you want to book, reschedule, or ask something else?"

        elif "Appointment" in intent:
            response = "Sure! Let's book your appointment. What's your name?"
            st.session_state.stage = "get_name"

        elif "Reschedule" in intent:
            response = "Sure, I can help reschedule your appointment. Please provide your booking ID."

        else:
            response = "I can help with booking, rescheduling, or general questions. What do you need?"

    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
