import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
from openai import OpenAI
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re

st.set_page_config(page_title="Clinic System", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hospital_management.db")

language = st.sidebar.selectbox("Language / اللغة", ["English", "Arabic"])

ai_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"]) if "MISTRAL_API_KEY" in st.secrets else None
voice_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"]) if "OPENAI_API_KEY" in st.secrets else None


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


def valid_phone(phone):
    return phone.startswith("+") and len(phone) >= 8


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
        return [(base + timedelta(minutes=30*i)).strftime("%Y-%m-%d %H:%M") for i in range(1,4)]
    except:
        return []


def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        name = name.strip().lower()
        cur.execute("BEGIN IMMEDIATE")

        if not valid_phone(phone):
            return False, "Invalid phone number"

        if not is_future(slot):
            return False, "Pick a future time"

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
    try:
        cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name.strip().lower(), doc_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(
            st.secrets["TWILIO_ACCOUNT_SID"],
            st.secrets["TWILIO_AUTH_TOKEN"]
        )

        msg = f"Appointment Confirmed\n{name}\n{doctor}\n{slot}"

        res = client.messages.create(
            body=msg,
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )

        st.write("WhatsApp SID:", res.sid)
        return True

    except Exception as e:
        st.error(f"WhatsApp Error: {e}")
        return False


def transcribe_audio(audio_file):
    try:
        result = voice_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
        return result.text
    except Exception as e:
        st.error(f"Voice Error: {e}")
        return None


st.sidebar.title("Clinic Tools")


chat_tab, admin_tab = st.tabs(["Chat Assistant", "Admin Dashboard"])


with chat_tab:
    st.markdown("<h1 style='text-align:center;'>Clinic Assistant System</h1>", unsafe_allow_html=True)
    st.markdown("---")

    if "history" not in st.session_state:
        st.session_state.history = []

    st.subheader("Voice Input")

    audio = st.file_uploader("Upload voice (mp3/wav/m4a)", type=["mp3", "wav", "m4a"])

    voice_text = None

    if audio and voice_client:
        st.audio(audio)
        voice_text = transcribe_audio(audio)
        if voice_text:
            st.info(voice_text)

    text_input = st.chat_input("Type or use voice...")

    user_msg = voice_text if voice_text else text_input

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})
        st.chat_message("user").markdown(user_msg)

        now = datetime.now()

        system_prompt = f"""
You are a strict clinic receptionist AI.
Return ONLY:
[BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]

If unclear, ask questions.
Doctors: {DOCTORS}
"""

        if ai_client:
            response = ai_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": system_prompt}] + st.session_state.history
            )
            reply = response.choices[0].message.content
        else:
            reply = "AI not configured"

        st.chat_message("assistant").markdown(reply)

        match = re.search(r"\[BOOKING:(.*?)\]", reply)

        if match:
            parts = [p.strip() for p in match.group(1).split(",")]

            if len(parts) == 4:
                name, phone, doc, slot = parts

                ok, err = book_appointment(name, phone, doc, slot)

                if ok:
                    st.success("Appointment booked successfully")
                    send_whatsapp(phone, name, DOCTORS[doc]["en"], slot)
                else:
                    st.warning(err)

        cancel = re.search(r"\[CANCEL:(.*?)\]", reply)

        if cancel:
            name, doc = [x.strip() for x in cancel.group(1).split(",")]

            if cancel_appointment(name, doc):
                st.success("Appointment cancelled")
            else:
                st.warning("Not found")

        st.session_state.history.append({"role": "assistant", "content": reply})


with admin_tab:
    st.subheader("Appointments Dashboard")

    conn = db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if len(df):
        st.metric("Total Appointments", len(df))
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No appointments found")
