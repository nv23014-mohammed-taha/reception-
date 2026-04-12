import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re

# Google Calendar
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle

st.set_page_config(page_title="Clinic System", layout="wide")

# ================= LANGUAGE =================
lang = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

# ================= PATH =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "hospital_management.db")

# ================= AI CLIENT =================
mistral_client = None
if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])

# ================= DATABASE =================
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
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

def try_booking(name, phone, doc, slot):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT id FROM appointments WHERE doc_id=? AND slot=?",
            (doc, slot)
        )
        if cursor.fetchone():
            return False, "Slot already taken"

        cursor.execute(
            "INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?,?,?,?)",
            (name.lower().strip(), phone, doc, slot)
        )

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()

def cancel_booking(name, doc):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM appointments WHERE patient_name=? AND doc_id=?",
        (name.lower().strip(), doc)
    )

    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

init_db()

# ================= DOCTORS =================
DOCTOR_LIST = {
    "1": {"en": "Dr. Faisal (Cardiology)", "ar": "د. فيصل"},
    "2": {"en": "Dr. Mariam (Pediatrics)", "ar": "د. مريم"},
    "3": {"en": "Dr. Yousef (Orthopedics)", "ar": "د. يوسف"},
    "4": {"en": "Dr. Noura (Dermatology)", "ar": "د. نورة"},
    "5": {"en": "Dr. Khalid (Surgery)", "ar": "د. خالد"}
}

# ================= WHATSAPP =================
def send_whatsapp(phone, name, doctor, slot, reminder=False):
    try:
        client = Client(
            st.secrets["TWILIO_ACCOUNT_SID"],
            st.secrets["TWILIO_AUTH_TOKEN"]
        )

        if lang == "العربية":
            msg = f"""
{'تذكير ⏰' if reminder else 'تم تأكيد الموعد ✅'}

{name}

👨‍⚕️ {doctor}
📅 {slot}
"""
        else:
            msg = f"""
{'Reminder ⏰' if reminder else 'Appointment Confirmed ✅'}

{name}

👨‍⚕️ {doctor}
📅 {slot}
"""

        client.messages.create(
            body=msg,
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )

        return True

    except Exception as e:
        return str(e)

# ================= GOOGLE CALENDAR =================
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_calendar_service():
    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("calendar", "v3", credentials=creds)

def create_event(name, doctor, slot):
    try:
        service = get_calendar_service()

        start = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        end = start + timedelta(minutes=30)

        event = {
            "summary": f"Appointment: {name}",
            "description": doctor,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Bahrain"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Bahrain"},
        }

        service.events().insert(calendarId="primary", body=event).execute()
        return True

    except Exception as e:
        return str(e)

# ================= REMINDERS =================
def send_reminders():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    now = datetime.now()
    one_hour = now + timedelta(hours=1)

    for _, row in df.iterrows():
        try:
            t = datetime.strptime(row["slot"], "%Y-%m-%d %H:%M")

            if now <= t <= one_hour:
                doctor = DOCTOR_LIST[row["doc_id"]]["en"]

                send_whatsapp(
                    row["phone"],
                    row["patient_name"],
                    doctor,
                    row["slot"],
                    reminder=True
                )
        except:
            pass

# run reminders once per session
if "reminder_run" not in st.session_state:
    send_reminders()
    st.session_state.reminder_run = True

# ================= UI =================
chat_tab, admin_tab = st.tabs(["Chat", "Dashboard"])

# ================= CHAT =================
with chat_tab:
    st.title("Clinic AI Assistant")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if user := st.chat_input("Type here"):
        st.session_state.chat_history.append({"role": "user", "content": user})

        system = f"""
You are a clinic receptionist.

Rules:
- Always require phone number
- Format:
[BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]
[CANCEL: Name, DocID]

Doctors: {DOCTOR_LIST}
"""

        res = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": system}] + st.session_state.chat_history
        )

        reply = res.choices[0].message.content
        st.markdown(reply)

        # BOOKING
        b = re.search(r"\[BOOKING:(.*?)\]", reply)
        if b:
            name, phone, doc, slot = [x.strip() for x in b.group(1).split(",")]

            ok, err = try_booking(name, phone, doc, slot)

            if ok:
                doctor = DOCTOR_LIST[doc]["en"]

                send_whatsapp(phone, name, doctor, slot)
                create_event(name, doctor, slot)

                st.success("Booked + WhatsApp + Calendar ✅")
                st.balloons()
            else:
                st.warning(err)

        # CANCEL
        c = re.search(r"\[CANCEL:(.*?)\]", reply)
        if c:
            name, doc = [x.strip() for x in c.group(1).split(",")]

            if cancel_booking(name, doc):
                st.success("Cancelled")
            else:
                st.warning("Not found")

        st.session_state.chat_history.append({"role": "assistant", "content": reply})

# ================= DASHBOARD =================
with admin_tab:
    st.subheader("Dashboard")

    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric("Total Appointments", len(df))

        for id, doc in DOCTOR_LIST.items():
            sub = df[df["doc_id"] == id]

            with st.expander(f"{doc['en']} ({len(sub)})"):
                st.table(sub)

        if st.button("Clear All"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()

        st.download_button(
            "Download DB",
            data=open(DB_NAME, "rb"),
            file_name="clinic.db"
        )

    else:
        st.info("No appointments yet")
