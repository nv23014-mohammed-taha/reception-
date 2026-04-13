import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re

st.set_page_config(page_title="Clinic System", layout="wide")

language = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hospital_management.db")

ai_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"]) if "MISTRAL_API_KEY" in st.secrets else None


def db_connection():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL;")
    return connection


def setup_database():
    connection = db_connection()
    cursor = connection.cursor()
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
    connection.commit()
    connection.close()


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


def valid_time(slot):
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
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

        if not valid_time(slot):
            return False, "You cannot book past or current time slots."

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
        name = name.strip().lower()
        cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name, doc_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(st.secrets["TWILIO_ACCOUNT_SID"], st.secrets["TWILIO_AUTH_TOKEN"])
        message = f"Appointment Confirmed \n\nHello {name}\n {doctor}\n {slot}"
        client.messages.create(
            body=message,
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
        return True
    except:
        return False


st.sidebar.title("Tools")

if os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as f:
        st.sidebar.download_button("📥 Download Database", f, file_name="clinic_data.db")


chat_tab, admin_tab = st.tabs(["Chat Assistant", "Admin Dashboard"])


with chat_tab:
    st.title("Clinic Assistant")

    now = datetime.now()
    today = now.strftime("%A, %Y-%m-%d")

    if "history" not in st.session_state:
        st.session_state.history = []

    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("How can I help you?")

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        system_prompt = f"""
You are a clinic receptionist. Today is {today}.
All bookings must be for {now.year}.
Format: [BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]
Doctors: {DOCTORS}
"""

        response = ai_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": system_prompt}] + st.session_state.history
        )

        reply = response.choices[0].message.content

        with st.chat_message("assistant"):
            st.markdown(reply)

        booking = re.search(r"\[BOOKING:(.*?)\]", reply)
        if booking:
            data = [x.strip() for x in booking.group(1).split(",")]
            if len(data) == 4:
                name, phone, doc, slot = data

                if "2023" in slot:
                    slot = slot.replace("2023", str(now.year))

                ok, err = book_appointment(name, phone, doc, slot)

                if ok:
                    st.success(f"Booked for {slot}")
                    send_whatsapp(phone, name, DOCTORS[doc]["en"], slot)
                    st.balloons()
                else:
                    st.warning(err)

        cancel = re.search(r"\[CANCEL:(.*?)\]", reply)
        if cancel:
            name, doc = [x.strip() for x in cancel.group(1).split(",")]
            if cancel_appointment(name, doc):
                st.success("Cancelled successfully")
            else:
                st.warning("Not found")

        st.session_state.history.append({"role": "assistant", "content": reply})


with admin_tab:
    st.subheader("Current Appointments")

    conn = db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric("Total Bookings", len(df))

        for doc_id, doc in DOCTORS.items():
            subset = df[df["doc_id"] == doc_id]

            with st.expander(f"{doc['en']} ({len(subset)})"):
                if not subset.empty:
                    st.table(subset[["patient_name", "phone", "slot"]])
                else:
                    st.write("No appointments")

        if st.button("Clear All Data"):
            conn = db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()

    else:
        st.info("No bookings found")

DOCTOR_SCHEDULE = {
    "1": {"start": 9, "end": 17, "days": [0,1,2,3,4]},
    "2": {"start": 10, "end": 16, "days": [0,1,2,3,4]},
    "3": {"start": 9, "end": 15, "days": [0,1,2,3,4]},
    "4": {"start": 11, "end": 18, "days": [0,1,2,3,4]},
    "5": {"start": 12, "end": 20, "days": [0,1,2,3,4]},
    "6": {"start": 9, "end": 14, "days": [0,1,2,3,4]},
    "7": {"start": 10, "end": 17, "days": [0,1,2,3,4]},
    "8": {"start": 9, "end": 16, "days": [0,1,2,3,4]},
    "9": {"start": 9, "end": 17, "days": [0,1,2,3,4]},
    "10": {"start": 8, "end": 14, "days": [0,1,2,3,4]}
}

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

tz = ZoneInfo("Asia/Bahrain")


def is_doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        dt = dt.replace(tzinfo=tz)

        s = DOCTOR_SCHEDULE.get(doc_id)
        if not s:
            return True

        if dt.weekday() not in s["days"]:
            return False

        if dt.hour < s["start"] or dt.hour >= s["end"]:
            return False

        if "break" in s:
            b1, b2 = s["break"]
            if b1 <= dt.hour < b2:
                return False

        return True

    except:
        return False


def next_valid_slots(doc_id, slot):
    try:
        base = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        base = base.replace(tzinfo=tz)

        out = []
        step = 30

        for i in range(1, 7):
            t = base + timedelta(minutes=step * i)
            t_str = t.strftime("%Y-%m-%d %H:%M")

            if is_doctor_available(doc_id, t_str):
                out.append(t_str)

            if len(out) == 3:
                break

        return out

    except:
        return []


def is_valid_future_time(slot):
    try:
        now = datetime.now(tz)
        t = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        t = t.replace(tzinfo=tz)

        return t > now

    except:
        return False


def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur = conn.cursor()

    try:
        name = name.strip().lower()
        cur.execute("BEGIN IMMEDIATE")

        if not is_valid_future_time(slot):
            return False, "Pick a future time."

        if not is_doctor_available(doc_id, slot):
            alt = next_valid_slots(doc_id, slot)
            return False, f"Doctor not available. Try {', '.join(alt) if alt else 'something else'}"

        cur.execute(
            "SELECT 1 FROM appointments WHERE doc_id=? AND slot=?",
            (doc_id, slot)
        )

        if cur.fetchone():
            alt = next_valid_slots(doc_id, slot)
            return False, f"Already booked. Try {', '.join(alt)}"

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
