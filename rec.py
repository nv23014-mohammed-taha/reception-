import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re

st.set_page_config(page_title="Clinic page", layout="wide")

lang = st.sidebar.selectbox("language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

# ================= MISTRAL =================
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            phone TEXT,
            doc_id TEXT,
            slot TEXT,
            UNIQUE(doc_id, slot)
        )
    ''')

    conn.commit()
    conn.close()

def try_booking(name, phone, doc, slot):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        name = name.strip().lower()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("SELECT id FROM appointments WHERE doc_id=? AND slot=?", (doc, slot))
        if cursor.fetchone():
            return False, "slot already taken"

        cursor.execute(
            "INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?,?,?,?)",
            (name, phone, doc, slot)
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

    try:
        name = name.strip().lower()
        cursor.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name, doc))
        conn.commit()
        return cursor.rowcount > 0
    except:
        return False
    finally:
        conn.close()

init_db()

# ================= WHATSAPP =================
def send_whatsapp_confirmation(phone, name, doctor, slot, reminder=False):
    try:
        client = Client(
            st.secrets["TWILIO_ACCOUNT_SID"],
            st.secrets["TWILIO_AUTH_TOKEN"]
        )

        if lang == "العربية":
            message = f"""
{'تذكير ⏰' if reminder else 'تم تأكيد موعدك ✅'}

مرحباً {name}

👨‍⚕️ {doctor}
📅 {slot}
"""
        else:
            message = f"""
{'Reminder ⏰' if reminder else 'Your appointment is confirmed ✅'}

Hello {name}

👨‍⚕️ {doctor}
📅 {slot}
"""

        client.messages.create(
            body=message,
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )

        return True

    except Exception as e:
        return str(e)

# ================= REMINDERS =================
def send_reminders():
    conn = get_db_connection()
    cursor = conn.cursor()

    now = datetime.now()
    one_hour_later = now + timedelta(hours=1)

    cursor.execute("SELECT patient_name, phone, doc_id, slot FROM appointments")
    rows = cursor.fetchall()

    for name, phone, doc, slot in rows:
        try:
            appointment_time = datetime.strptime(slot, "%Y-%m-%d %H:%M")

            if now <= appointment_time <= one_hour_later:
                doctor_name = DOCTOR_LIST[doc]["en"]
                send_whatsapp_confirmation(phone, name, doctor_name, slot, reminder=True)
        except:
            pass

    conn.close()

if "last_reminder_check" not in st.session_state:
    send_reminders()
    st.session_state.last_reminder_check = datetime.now()

# ================= DOCTORS =================
DOCTOR_LIST = {
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

# ================= SIDEBAR =================
st.sidebar.title("Tools")

if os.path.exists(DB_NAME):
    with open(DB_NAME, "rb") as f:
        st.sidebar.download_button(
            label="Download DB",
            data=f,
            file_name="hospital_management.db"
        )

# ================= TABS =================
chat_tab, admin_tab = st.tabs(["Chat", "Dashboard"])

# ================= CHAT =================
with chat_tab:
    st.title("Clinic Assistant")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Type here"):
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            system_instruction = f"""
You are a clinic receptionist.

Rules:
- ALWAYS ask for phone number before booking

Format:
[BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]
[CANCEL: Name, DocID]

Doctors: {DOCTOR_LIST}
"""

            response = mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
            )

            ai_response = response.choices[0].message.content
            st.markdown(ai_response)

            # BOOKING
            match = re.search(r"\[BOOKING:(.*?)\]", ai_response)
            if match:
                parts = [p.strip() for p in match.group(1).split(",")]

                if len(parts) >= 4:
                    name, phone, doc, slot = parts

                    success, err = try_booking(name, phone, doc, slot)

                    if success:
                        doctor_name = DOCTOR_LIST[doc]["en"]
                        send_whatsapp_confirmation(phone, name, doctor_name, slot)

                        st.success("Booked + WhatsApp sent ✅")
                        st.balloons()
                    else:
                        st.warning(err)

            # CANCEL
            match = re.search(r"\[CANCEL:(.*?)\]", ai_response)
            if match:
                parts = [p.strip() for p in match.group(1).split(",")]
                if len(parts) >= 2:
                    if cancel_booking(parts[0], parts[1]):
                        st.success("Cancelled")
                    else:
                        st.warning("Not found")

            st.session_state.chat_history.append({"role": "assistant", "content": ai_response})

# ================= DASHBOARD =================
with admin_tab:
    st.subheader("Appointments Dashboard")

    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric("Total Bookings", len(df))

        for id, info in DOCTOR_LIST.items():
            doc_df = df[df["doc_id"] == id]
            name = info["en"]

            with st.expander(f"{name} ({len(doc_df)})"):
                if not doc_df.empty:
                    st.table(doc_df[["patient_name", "phone", "slot"]])

        if st.button("Clear All"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()

    else:
        st.info("No bookings yet")
