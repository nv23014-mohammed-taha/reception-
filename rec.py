import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re

# ================= APP SETUP =================
st.set_page_config(page_title="Clinic System", layout="wide")

lang = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

# ================= AI (MISTRAL) =================
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

init_db()

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

# ================= TIME LOGIC =================
def is_valid_future_time(slot):
    try:
        appointment_time = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        return appointment_time > datetime.now()
    except:
        return False

def suggest_alternative_times(slot):
    try:
        base = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        return [(base + timedelta(minutes=30 * i)).strftime("%Y-%m-%d %H:%M") for i in range(1, 4)]
    except:
        return []

# ================= BOOKING & CANCEL =================
def try_booking(name, phone, doc, slot):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        name = name.strip().lower()
        cursor.execute("BEGIN IMMEDIATE")
        
        if not is_valid_future_time(slot):
            return False, "You cannot book past or current time slots."

        cursor.execute("SELECT id FROM appointments WHERE doc_id=? AND slot=?", (doc, slot))
        if cursor.fetchone():
            return False, f"Slot taken. Try: {', '.join(suggest_alternative_times(slot))}"

        cursor.execute("INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?,?,?,?)", (name, phone, doc, slot))
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
    except: return False
    finally: conn.close()

# ================= WHATSAPP =================
def send_whatsapp_confirmation(phone, name, doctor, slot):
    try:
        client = Client(st.secrets["TWILIO_ACCOUNT_SID"], st.secrets["TWILIO_AUTH_TOKEN"])
        msg = f"Appointment Confirmed ✅\n\nHello {name}\n👨‍⚕️ {doctor}\n📅 {slot}"
        client.messages.create(body=msg, from_=st.secrets["TWILIO_WHATSAPP_NUMBER"], to=f"whatsapp:{phone}")
        return True
    except: return False

# ================= SIDEBAR TOOLS =================
st.sidebar.title("Tools")
if os.path.exists(DB_NAME):
    with open(DB_NAME, "rb") as f:
        st.sidebar.download_button(label="📥 Download Database", data=f, file_name="clinic_data.db")

# ================= TABS =================
chat_tab, admin_tab = st.tabs(["Chat Assistant", "Admin Dashboard"])

# ================= CHAT =================
with chat_tab:
    st.title("Clinic Assistant")
    
    now = datetime.now()
    today_str = now.strftime("%A, %Y-%m-%d")
    current_year = now.year

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if user_input := st.chat_input("How can I help you?"):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)

        system_instruction = f"""
        You are a clinic receptionist. Today is {today_str}.
        RULES:
        - All bookings MUST be in the year {current_year} (unless specified).
        - Format: [BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]
        - Doctors: {DOCTOR_LIST}
        """

        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
        )

        ai_reply = response.choices[0].message.content
        with st.chat_message("assistant"): st.markdown(ai_reply)

        # Parsing Booking
        if b_match := re.search(r"\[BOOKING:(.*?)\]", ai_reply):
            parts = [p.strip() for p in b_match.group(1).split(",")]
            if len(parts) == 4:
                name, phone, doc, slot = parts
                if "2023" in slot: slot = slot.replace("2023", str(current_year))
                
                ok, err = try_booking(name, phone, doc, slot)
                if ok:
                    st.success(f"Confirmed for {slot}!")
                    send_whatsapp_confirmation(phone, name, DOCTOR_LIST[doc]["en"], slot)
                    st.balloons()
                else: st.warning(err)

        # Parsing Cancel
        if c_match := re.search(r"\[CANCEL:(.*?)\]", ai_reply):
            parts = [p.strip() for p in c_match.group(1).split(",")]
            if len(parts) == 2:
                if cancel_booking(parts[0], parts[1]): st.success("Cancelled successfully.")
                else: st.warning("Appointment not found.")

        st.session_state.chat_history.append({"role": "assistant", "content": ai_reply})

# ================= DASHBOARD =================
with admin_tab:
    st.subheader("Current Appointments")
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric("Total Bookings", len(df))
        for id, info in DOCTOR_LIST.items():
            doc_df = df[df["doc_id"] == id]
            with st.expander(f"{info['en']} ({len(doc_df)})"):
                if not doc_df.empty: st.table(doc_df[["patient_name", "phone", "slot"]])
                else: st.write("No appointments.")
        
        if st.button("🗑️ Clear All Data"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("No bookings found in the database.")
