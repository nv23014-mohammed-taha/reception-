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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctor_schedule (
            doc_id TEXT PRIMARY KEY,
            start_hour INTEGER,
            end_hour INTEGER
        )
    """)

    conn.commit()
    conn.close()


setup_database()


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

DEFAULT_SCHEDULE = {"start": 9, "end": 18}


def get_schedule(doc_id):
    conn = db_connection()
    cur = conn.cursor()

    cur.execute("SELECT start_hour, end_hour FROM doctor_schedule WHERE doc_id=?", (doc_id,))
    row = cur.fetchone()

    if row:
        conn.close()
        return {"start": row[0], "end": row[1]}

    cur.execute("INSERT OR IGNORE INTO doctor_schedule VALUES (?,?,?)",
                (doc_id, DEFAULT_SCHEDULE["start"], DEFAULT_SCHEDULE["end"]))
    conn.commit()
    conn.close()

    return DEFAULT_SCHEDULE


def is_future(slot):
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
    except:
        return False


def doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        s = get_schedule(doc_id)
        return dt.weekday() < 5 and s["start"] <= dt.hour < s["end"]
    except:
        return False


def next_slots(slot):
    base = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    return [(base + timedelta(minutes=30*i)).strftime("%Y-%m-%d %H:%M") for i in range(1,4)]


def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        name = name.lower().strip()
        cur.execute("BEGIN IMMEDIATE")

        if not is_future(slot):
            return False, "Pick future time"

        if not doctor_available(doc_id, slot):
            return False, "Doctor unavailable"

        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot))
        if cur.fetchone():
            return False, "Slot taken"

        cur.execute("INSERT INTO appointments VALUES(NULL,?,?,?,?)",
                    (name, phone, doc_id, slot))

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
    cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?",
                (name.lower().strip(), doc_id))
    conn.commit()
    conn.close()
    return True


def reschedule_appointment(name, doc_id, new_slot):
    conn = db_connection()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM appointments WHERE patient_name=? AND doc_id=?",
                (name.lower().strip(), doc_id))

    if not cur.fetchone():
        return False, "Not found"

    if not doctor_available(doc_id, new_slot):
        return False, "Doctor unavailable"

    cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?",
                (doc_id, new_slot))

    if cur.fetchone():
        return False, "Slot taken"

    cur.execute("UPDATE appointments SET slot=? WHERE patient_name=? AND doc_id=?",
                (new_slot, name.lower().strip(), doc_id))

    conn.commit()
    conn.close()
    return True, None


def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(st.secrets["TWILIO_ACCOUNT_SID"],
                        st.secrets["TWILIO_AUTH_TOKEN"])

        msg = f"""🏥 Appointment Confirmed
{name}
{doctor}
{slot}"""

        client.messages.create(
            body=msg,
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
    except:
        pass


def transcribe_audio(audio_bytes):
    r = sr.Recognizer()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
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


st.sidebar.title("Navigation")

if os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as f:
        st.sidebar.download_button("Download Database", f, file_name="clinic_data.db")


chat_tab, admin_tab = st.tabs(
    ["Chat Assistant", "Administration Panel"] if language == "English"
    else ["المساعد", "لوحة الإدارة"]
)


with chat_tab:

    st.title("Clinic Assistant" if language == "English" else "مساعد العيادة")

    if "history" not in st.session_state:
        st.session_state.history = []

    audio = st.audio_input("🎤 Speak" if language == "English" else "🎤 تحدث")

    if audio:
        txt = transcribe_audio(audio.getvalue())
        st.session_state["voice_pending"] = txt

    user_msg = st.chat_input("Type..." if language == "English" else "اكتب هنا")

    if not user_msg and st.session_state.get("voice_pending"):
        user_msg = st.session_state.pop("voice_pending")

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})

        system_prompt = f"""
BOOK [BOOKING: name, phone, doc_id, slot]
CANCEL [CANCEL: name, doc_id]
RESCHEDULE [RESCHEDULE: name, doc_id, slot]

Doctors: {DOCTORS}
"""

        if ai_client:
            res = ai_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": system_prompt}]
                + st.session_state.history
            )
            reply = res.choices[0].message.content
        else:
            reply = "AI off"

        st.chat_message("assistant").markdown(reply)

        b = re.search(r"\[BOOKING:(.*?)\]", reply)
        if b:
            n,p,d,s = [x.strip() for x in b.group(1).split(",")]
            ok,_ = book_appointment(n,p,d,s)
            if ok:
                send_whatsapp(p,n,DOCTORS[d]["en"],s)

        c = re.search(r"\[CANCEL:(.*?)\]", reply)
        if c:
            n,d = [x.strip() for x in c.group(1).split(",")]
            cancel_appointment(n,d)

        r = re.search(r"\[RESCHEDULE:(.*?)\]", reply)
        if r:
            n,d,s = [x.strip() for x in r.group(1).split(",")]
            reschedule_appointment(n,d,s)

        st.session_state.history.append({"role": "assistant", "content": reply})


with admin_tab:

    st.subheader("Administration Panel" if language == "English" else "لوحة الإدارة")

    conn = db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    st.metric("Total Appointments", len(df))

    if st.button("⬇ Download Database"):
        with open(DB_PATH, "rb") as f:
            st.download_button("Download DB File", f, file_name="clinic_data.db")

    st.markdown("### Doctor Schedule" if language=="English" else "### جدول الأطباء")

    doc = st.selectbox("Doctor", list(DOCTORS.keys()), format_func=lambda x: DOCTORS[x][language=="ar" and "ar" or "en"])

    s = get_schedule(doc)

    start = st.number_input("Start", 0, 23, s["start"])
    end = st.number_input("End", 0, 23, s["end"])

    if st.button("Save"):
        conn = db_connection()
        cur = conn.cursor()
        cur.execute("REPLACE INTO doctor_schedule VALUES (?,?,?)", (doc, start, end))
        conn.commit()
        conn.close()
        st.success("Updated")

    for d in DOCTORS:
        with st.expander(DOCTORS[d]["en"]):
            st.dataframe(df[df["doc_id"] == d])
