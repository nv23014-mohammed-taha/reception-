import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os, re, tempfile
import speech_recognition as sr
import matplotlib.pyplot as plt

st.set_page_config(page_title="Clinic System", layout="wide")

language = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

def t(en, ar):
    return ar if language == "العربية" else en


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hospital_management.db")

ai_client = None
if "MISTRAL_API_KEY" in st.secrets:
    ai_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])


# ================= DATABASE =================
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
            status TEXT DEFAULT 'pending',
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


# ================= DOCTORS =================
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


# ================= VALIDATION =================
def valid_input(name, phone):
    if not name or len(name.strip()) < 3:
        return False, "Invalid name"

    if not re.match(r"^\+?973?\d{8}$", phone):
        return False, "Invalid phone number"

    return True, None


# ================= SCHEDULE =================
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


def doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        s = get_schedule(doc_id)
        return dt.weekday() < 5 and s["start"] <= dt.hour < s["end"]
    except:
        return False


def is_future(slot):
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
    except:
        return False


# ================= BOOKING =================
def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        valid, err = valid_input(name, phone)
        if not valid:
            return False, err

        if not is_future(slot):
            return False, "Pick future time"

        if not doctor_available(doc_id, slot):
            return False, "Doctor unavailable"

        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot))
        if cur.fetchone():
            return False, "Slot taken"

        cur.execute("INSERT INTO appointments VALUES(NULL,?,?,?,?,?)",
                    (name.strip(), phone, doc_id, slot, "pending"))

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()


# ================= WHATSAPP =================
def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(st.secrets["TWILIO_ACCOUNT_SID"],
                        st.secrets["TWILIO_AUTH_TOKEN"])

        client.messages.create(
            body=f"🏥 Appointment Confirmed\n{name}\n{doctor}\n{slot}",
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
    except:
        pass


# ================= UI =================
chat_tab, admin_tab = st.tabs(["Chat", "Administration"])


# ================= CHAT =================
with chat_tab:
    st.title("Clinic Assistant")

    if "history" not in st.session_state:
        st.session_state.history = []

    user_msg = st.chat_input("Type message")

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})

        system_prompt = """
        You are a clinic assistant.

        RULES:
        - NEVER book without name AND phone
        - If missing info → ASK USER
        - Booking format:
        [BOOKING: name, phone, doctor_id, YYYY-MM-DD HH:MM]
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
            ok,err = book_appointment(n,p,d,s)
            if ok:
                st.success("Booking pending approval")
            else:
                st.warning(err)

        st.session_state.history.append({"role": "assistant", "content": reply})


# ================= ADMIN =================
with admin_tab:
    st.subheader("Admin Panel")

    conn = db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    # Clean bad data
    df = df[df["patient_name"].notna()]
    df = df[df["phone"].notna()]

    st.metric("Total Appointments", len(df))

    # ===== Approval System =====
    st.markdown("### Pending Approvals")

    pending = df[df["status"] == "pending"]

    for i, row in pending.iterrows():
        col1, col2, col3 = st.columns([3,1,1])

        with col1:
            st.write(f"{row['patient_name']} | {row['slot']}")

        with col2:
            if st.button(f"Approve {row['id']}"):
                conn = db_connection()
                cur = conn.cursor()

                # enforce schedule again
                if not doctor_available(row["doc_id"], row["slot"]):
                    st.error("Doctor not available anymore")
                else:
                    cur.execute("UPDATE appointments SET status='approved' WHERE id=?", (row['id'],))
                    conn.commit()

                    send_whatsapp(
                        row["phone"],
                        row["patient_name"],
                        DOCTORS[row["doc_id"]]["en"],
                        row["slot"]
                    )

                conn.close()
                st.rerun()

        with col3:
            if st.button(f"Reject {row['id']}"):
                conn = db_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM appointments WHERE id=?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()

    # ===== Schedule Editor =====
    st.markdown("### Doctor Schedule")

    doc = st.selectbox("Doctor", list(DOCTORS.keys()),
                       format_func=lambda x: DOCTORS[x]["en"])

    s = get_schedule(doc)

    start = st.number_input("Start Hour", 0, 23, s["start"])
    end = st.number_input("End Hour", 0, 23, s["end"])

    if st.button("Save Schedule"):
        conn = db_connection()
        cur = conn.cursor()
        cur.execute("REPLACE INTO doctor_schedule VALUES (?,?,?)", (doc, start, end))
        conn.commit()
        conn.close()
        st.success("Updated")

    # ===== Schedule Viewer =====
    st.markdown("### Current Schedule")

    for d in DOCTORS:
        s = get_schedule(d)
        st.write(f"{DOCTORS[d]['en']} → {s['start']}:00 - {s['end']}:00")

    # ===== Display Appointments =====
    st.markdown("### Appointments")

    for d in DOCTORS:
        with st.expander(DOCTORS[d]["en"]):
            approved = df[(df["doc_id"] == d) & (df["status"] == "approved")]
            pending = df[(df["doc_id"] == d) & (df["status"] == "pending")]

            st.write("Approved")
            st.dataframe(approved)

            st.write("Pending")
            st.dataframe(pending)

    # ===== Analytics =====
    st.markdown("### Analytics")

    if not df.empty:
        st.bar_chart(df["doc_id"].value_counts())

        df["date"] = pd.to_datetime(df["slot"])
        daily = df.groupby(df["date"].dt.date).size()
        st.line_chart(daily)

        st.write(df["status"].value_counts())
