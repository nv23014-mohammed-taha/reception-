import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os, re, tempfile
import speech_recognition as sr

st.set_page_config(page_title="Clinic System", layout="wide")

language = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hospital_management.db")

ai_client = None
if "MISTRAL_API_KEY" in st.secrets:
    ai_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])


# ---------------- DB ----------------
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


# ---------------- DOCTORS ----------------
DOCTORS = {
    "1": {"en": "Dr. Faisal Al-Mahmood (Cardiology)", "ar": "د. فيصل المحمود"},
    "2": {"en": "Dr. Mariam Al-Sayed (Pediatrics)", "ar": "د. مريم السيد"},
    "3": {"en": "Dr. Yousef Al-Haddad (Orthopedics)", "ar": "د. يوسف الحداد"},
    "4": {"en": "Dr. Noura Al-Khalifa (Dermatology)", "ar": "د. نورة الخليفة"},
    "5": {"en": "Dr. Khalid Al-Fares", "ar": "د. خالد الفارس"},
    "6": {"en": "Dr. Sara Al-Ansari", "ar": "د. سارة الأنصاري"},
    "7": {"en": "Dr. Jasim Al-Ghanem", "ar": "د. جاسم الغانم"},
    "8": {"en": "Dr. Layla Al-Mulla", "ar": "د. ليلى الملا"},
    "9": {"en": "Dr. Hassan Ibrahim", "ar": "د. حسن إبراهيم"},
    "10": {"en": "Dr. Ahmed Al-Aali", "ar": "د. أحمد العالي"}
}

DOCTOR_SCHEDULE = {str(i): {"start":9,"end":18,"days":[0,1,2,3,4]} for i in range(1,11)}


# ---------------- LOGIC ----------------
def is_future(slot):
    try:
        return datetime.strptime(slot,"%Y-%m-%d %H:%M") > datetime.now()
    except:
        return False


def doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot,"%Y-%m-%d %H:%M")
        s = DOCTOR_SCHEDULE[doc_id]

        if dt.weekday() not in s["days"]:
            return False
        if dt.hour < s["start"] or dt.hour >= s["end"]:
            return False

        return True
    except:
        return False


def next_slots(slot):
    try:
        base = datetime.strptime(slot,"%Y-%m-%d %H:%M")
        return [(base + timedelta(minutes=30*i)).strftime("%Y-%m-%d %H:%M") for i in range(1,4)]
    except:
        return []


# ---------------- CORE ----------------
def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        name = name.lower().strip()
        cur.execute("BEGIN IMMEDIATE")

        if not is_future(slot):
            return False,"Pick future time"

        if not doctor_available(doc_id,slot):
            return False,f"Doctor busy. Try {next_slots(slot)}"

        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?",(doc_id,slot))
        if cur.fetchone():
            return False,"Slot already taken"

        cur.execute("INSERT INTO appointments VALUES(NULL,?,?,?,?)",(name,phone,doc_id,slot))
        conn.commit()

        return True,None

    except Exception as e:
        conn.rollback()
        return False,str(e)

    finally:
        conn.close()


def cancel_appointment(name, doc_id):
    conn = db_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?",
                (name.lower().strip(),doc_id))

    conn.commit()
    conn.close()

    return True


def reschedule_appointment(name, doc_id, new_slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        name = name.lower().strip()

        # check exists
        cur.execute("SELECT * FROM appointments WHERE patient_name=? AND doc_id=?",
                    (name,doc_id))
        if not cur.fetchone():
            return False,"No booking found"

        # check new slot
        if not doctor_available(doc_id,new_slot):
            return False,"Doctor unavailable"

        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?",
                    (doc_id,new_slot))
        if cur.fetchone():
            return False,"New slot taken"

        cur.execute("UPDATE appointments SET slot=? WHERE patient_name=? AND doc_id=?",
                    (new_slot,name,doc_id))

        conn.commit()
        return True,None

    except Exception as e:
        conn.rollback()
        return False,str(e)

    finally:
        conn.close()


def send_whatsapp(phone,name,doctor,slot):
    try:
        client = Client(st.secrets["TWILIO_ACCOUNT_SID"],
                        st.secrets["TWILIO_AUTH_TOKEN"])

        client.messages.create(
            body=f"Appointment Confirmed\n{name}\n{doctor}\n{slot}",
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
    except:
        pass


# ---------------- VOICE ----------------
def transcribe_audio(audio_bytes):
    r = sr.Recognizer()

    with tempfile.NamedTemporaryFile(delete=False,suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        path = tmp.name

    with sr.AudioFile(path) as src:
        audio = r.record(src)

    try:
        text = r.recognize_google(audio, language="ar-SA" if language=="العربية" else "en-US")
    except:
        text = "Could not understand"

    os.unlink(path)
    return text


# ---------------- UI ----------------
st.sidebar.title("Tools")

if os.path.exists(DB_PATH):
    with open(DB_PATH,"rb") as f:
        st.sidebar.download_button("Download DB",f,"clinic.db")

chat_tab, admin_tab = st.tabs(["Chat","Admin"])


with chat_tab:

    st.title("Clinic Assistant")

    if "history" not in st.session_state:
        st.session_state.history = []

    audio = st.audio_input("🎤 Speak")

    if audio:
        txt = transcribe_audio(audio.getvalue())
        st.session_state["voice_pending"] = txt
        st.write("You said:",txt)

    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Type...")

    if not user_msg and st.session_state.get("voice_pending"):
        user_msg = st.session_state.pop("voice_pending")

    if user_msg:
        st.session_state.history.append({"role":"user","content":user_msg})
        st.chat_message("user").markdown(user_msg)

        now = datetime.now()

        system_prompt = f"""
You are receptionist.

BOOK: [BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]
CANCEL: [CANCEL: Name, DocID]
RESCHEDULE: [RESCHEDULE: Name, DocID, YYYY-MM-DD HH:MM]

Doctors: {DOCTORS}
"""

        if ai_client:
            res = ai_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role":"system","content":system_prompt}] + st.session_state.history
            )
            reply = res.choices[0].message.content
        else:
            reply = "AI not working"

        st.chat_message("assistant").markdown(reply)

        # BOOK
        m = re.search(r"\[BOOKING:(.*?)\]",reply)
        if m:
            name,phone,doc,slot = [x.strip() for x in m.group(1).split(",")]
            ok,err = book_appointment(name,phone,doc,slot)
            if ok:
                st.success("Booked")
                send_whatsapp(phone,name,DOCTORS[doc]["en"],slot)
            else:
                st.warning(err)

        # CANCEL
        c = re.search(r"\[CANCEL:(.*?)\]",reply)
        if c:
            name,doc = [x.strip() for x in c.group(1).split(",")]
            cancel_appointment(name,doc)
            st.success("Cancelled")

        # RESCHEDULE
        r = re.search(r"\[RESCHEDULE:(.*?)\]",reply)
        if r:
            name,doc,new_slot = [x.strip() for x in r.group(1).split(",")]
            ok,err = reschedule_appointment(name,doc,new_slot)
            if ok:
                st.success("Rescheduled")
            else:
                st.warning(err)

        st.session_state.history.append({"role":"assistant","content":reply})


with admin_tab:
    st.subheader("Appointments")

    conn = db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments",conn)
    conn.close()

    if len(df):
        st.metric("Total",len(df))

        for d_id,doc in DOCTORS.items():
            with st.expander(doc["en"]):
                st.dataframe(df[df["doc_id"]==d_id])
    else:
        st.info("No bookings yet")
