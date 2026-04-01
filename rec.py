# final_receptionist_zip_safe.py

import pandas as pd
import os
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import dateparser
import sqlite3
import zipfile
import json

st.title("🤖 AI Healthcare Receptionist")

dataset_zip = "archive (8).zip"  # your file

model = None

# --- SAFE ZIP LOADING ---
if os.path.exists(dataset_zip):
    try:
        with zipfile.ZipFile(dataset_zip, 'r') as zip_ref:
            file_list = zip_ref.namelist()

            json_files = [f for f in file_list if f.endswith(".json")]
            csv_files = [f for f in file_list if f.endswith(".csv")]

            # 🔥 PRIORITY: JSON
            if json_files:
                with zip_ref.open(json_files[0]) as f:
                    data = json.load(f)
                    df = pd.DataFrame(data)

            elif csv_files:
                with zip_ref.open(csv_files[0]) as f:
                    df = pd.read_csv(f)

            else:
                st.error("No valid data file inside ZIP.")
                df = None

            if df is not None:
                # AUTO DETECT COLUMNS
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

                    model = make_pipeline(TfidfVectorizer(), MultinomialNB())
                    model.fit(df["text"], df["label"])

                    st.success("✅ Model trained from ZIP!")
                else:
                    st.warning("Could not detect columns.")
            else:
                model = None

    except zipfile.BadZipFile:
        st.error("❌ ZIP file is corrupted or invalid.")
        model = None

else:
    st.error("ZIP file not found.")

# --- DATABASE ---
conn = sqlite3.connect("appointments.db", check_same_thread=False)
c = conn.cursor()

c.execute("CREATE TABLE IF NOT EXISTS doctors (id INTEGER PRIMARY KEY, name TEXT)")
c.execute("""
CREATE TABLE IF NOT EXISTS appointments (
id INTEGER PRIMARY KEY,
patient_name TEXT,
doctor_id INTEGER,
date TEXT,
time TEXT)
""")

conn.commit()

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

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- FUNCTIONS ---
def get_intent(text):
    t = text.lower()

    # 🔥 ALWAYS WORK fallback
    if "book" in t or "appointment" in t:
        return "Appointment"
    if "reschedule" in t:
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
        (date, time)).fetchall()]

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
                response = "Enter a valid date."

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

                    response = f"✅ Booked with {doc_name} on {d['date']} at {d['time']}"
                    st.session_state.stage = "start"
                    st.session_state.data = {}
                else:
                    response = "No doctors available."

            else:
                response = "Enter a valid time."

    else:
        if intent == "Appointment":
            st.session_state.stage = "name"
            response = "What's your name?"

        else:
            response = "Say 'book appointment' to start."

    with st.chat_message("assistant"):
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
