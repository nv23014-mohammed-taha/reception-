import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re
import tempfile
from openai import OpenAI
from streamlit_audiorecorder import audiorecorder

st.set_page_config(page_title="Clinic System", layout="wide")

language = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hospital_management.db")

ai_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"]) if "MISTRAL_API_KEY" in st.secrets else None
voice_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def setup_database():
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            phone TEXT,
            doc_id TEXT,
            slot TEXT,
            UNIQUE(doc_id, slot)
        )
    """)
    conn.commit()
    conn.close()


setup_database()


DOCTORS = {
    "1": {"en": "Dr. Faisal Al-Mahmood (Cardiology)", "ar": "د. فيصل المحمود (القلب)"},
    "2": {"en": "Dr. Mariam Al-Sayed (Pediatrics)", "ar": "د. مريم السيد (أطفال)"},
    "3": {"en": "Dr. Yousef Al-Haddad (Orthopedics)", "ar": "د. يوسف الحداد (عظام)"},
    "4": {"en": "Dr. Noura Al-Khalifa (Dermatology)", "ar": "د. نورة الخليفة (جلدية)"},
    "5": {"en": "Dr. Khalid Al-Fares (Plastic Surgery)", "ar": "د. خالد الفارس (تجميل)"},
    "6": {"en": "Dr. Sara Al-Ansari (OB-GYN)", "ar": "د. سارة الأنصاري (نساء وولادة)"},
    "7": {"en": "Dr. Jasim Al-Ghanem (Urology)", "ar": "د. جاسم الغانم (مسالك)"},
    "8": {"en": "Dr. Layla Al-Mulla (Neurology)", "ar": "د. ليلى الملا (أعصاب)"},
    "9": {"en": "Dr. Hassan Ibrahim (Ophthalmology)", "ar": "د. حسن إبراهيم (عيون)"},
    "10": {"en": "Dr. Ahmed Al-Aali (General Medicine)", "ar": "د. أحمد العالي (طب عام)"}
}


DOCTOR_SCHEDULE = {
    "1": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "2": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "3": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "4": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "5": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "6": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "7": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "8": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "9": {"start": 9, "end": 18, "days": [0,1,2,3,4]},
    "10": {"start": 9, "end": 18, "days": [0,1,2,3,4]}
}


def is_future(slot):
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
    except:
        return False


def doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        s = DOCTOR_SCHEDULE.get(doc_id)

        if not s:
            return True

        if dt.weekday() not in s["days"]:
            return False

        if dt.hour < s["start"] or dt.hour >= s["end"]:
            return False

        return True
    except:
        return False


def next_slots(slot):
    try:
        base = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        return [(base + timedelta(minutes=30 * i)).strftime("%Y-%m-%d %H:%M") for i in range(1, 4)]
    except:
        return []


def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        name = name.strip().lower()
        cur.execute("BEGIN IMMEDIATE")

        if not is_future(slot):
            return False, "Pick a future time."

        if not doctor_available(doc_id, slot):
            return False, f"Doctor not available. Try: {', '.join(next_slots(slot))}"

        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot))
        if cur.fetchone():
            return False, f"Slot taken. Try: {', '.join(next_slots(slot))}"

        cur.execute(
            "INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?,?,?,?)",
            (name, phone, doc_id, slot)
        )

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()


def cancel_appointment(name, doc_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name.strip().lower(), doc_id))
    conn.commit()
    conn.close()
    return True


def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(
            st.secrets["TWILIO_ACCOUNT_SID"],
            st.secrets["TWILIO_AUTH_TOKEN"]
        )

        client.messages.create(
            body=f"Appointment Confirmed\n{name}\n{doctor}\n{slot}",
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
        return True
    except:
        return False


# ================= VOICE FEATURE (FIXED) =================

def transcribe_audio(audio_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_file.read())
        path = tmp.name

    with open(path, "rb") as f:
        result = voice_client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    return result.text


# ================= UI =================

st.sidebar.title("Tools")

if os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as f:
        st.sidebar.download_button("Download Database", f, file_name="clinic_data.db")


chat_tab, admin_tab = st.tabs(["Chat Assistant", "Admin Dashboard"])


with chat_tab:
    st.title("Clinic Assistant")

    if "history" not in st.session_state:
        st.session_state.history = []

    # VOICE RECORD BUTTON
    st.subheader("Voice Input")
    audio = audiorecorder("Tap to record", "Recording...")

    voice_text = None
    if len(audio) > 0:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            audio.export(tmp.name, format="wav")

            with open(tmp.name, "rb") as f:
                voice_text = voice_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f
                ).text

        st.success("Transcribed")
        st.write(voice_text)

    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("How can I help you?")

    if voice_text:
        user_msg = voice_text

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})
        st.chat_message("user").markdown(user_msg)

        now = datetime.now()

        system_prompt = f"""
You are a clinic receptionist.
Today is {now.strftime("%A %Y-%m-%d")}.
Return booking in format:
[BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]
Doctors: {DOCTORS}
"""

        response = ai_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": system_prompt}] + st.session_state.history
        )

        reply = response.choices[0].message.content

        st.chat_message("assistant").markdown(reply)

        match = re.search(r"\[BOOKING:(.*?)\]", reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]

            if len(parts) == 4:
                name, phone, doc, slot = parts

                if "2023" in slot:
                    slot = slot.replace("2023", str(now.year))

                ok, err = book_appointment(name, phone, doc, slot)

                if ok:
                    st.success("Booked successfully")
                    send_whatsapp(phone, name, DOCTORS[doc]["en"], slot)
                else:
                    st.warning(err)

        cancel = re.search(r"\[CANCEL:(.*?)\]", reply)
        if cancel:
            name, doc = [x.strip() for x in cancel.group(1).split(",")]
            cancel_appointment(name, doc)

        st.session_state.history.append({"role": "assistant", "content": reply})


with admin_tab:
    st.subheader("Appointments")

    conn = db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if len(df):
        st.metric("Total", len(df))

        for doc_id, doc in DOCTORS.items():
            sub = df[df["doc_id"] == doc_id]
            with st.expander(doc["en"]):
                st.dataframe(sub)
    else:
        st.info("No bookings found")
