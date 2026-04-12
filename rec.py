import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime
import os
import urllib.parse

st.set_page_config(page_title="Clinic Management", layout="wide")

lang = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Create table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            doc_id TEXT,
            slot TEXT,
            phone TEXT,
            UNIQUE(doc_id, slot)
        )
    ''')
    
    # FIX: Check if 'phone' column exists (to avoid the "no column named phone" error)
    cursor.execute("PRAGMA table_info(appointments)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'phone' not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN phone TEXT")
    
    conn.commit()
    conn.close()

def show_whatsapp_button(phone, message):
    encoded_msg = urllib.parse.quote(message)
    clean_phone = "".join(filter(str.isdigit, phone))
    url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
    
    st.markdown(f"""
        <div style="text-align: center; margin: 10px 0;">
            <a href="{url}" target="_blank">
                <button style="background-color: #25D366; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%;">
                    📲 Send WhatsApp Confirmation
                </button>
            </a>
        </div>
    """, unsafe_allow_html=True)

def try_booking(name, doc, slot, phone):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        name = name.replace("Patient:", "").strip()
        cursor.execute("INSERT INTO appointments (patient_name, doc_id, slot, phone) VALUES (?,?,?,?)",
                       (name, doc, slot, phone))
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, "Slot already taken"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def cancel_booking(name, doc):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        name = name.replace("Patient:", "").strip()
        cursor.execute("DELETE FROM appointments WHERE patient_name LIKE ? AND doc_id=?", (f"%{name}%", doc))
        success = cursor.rowcount > 0
        conn.commit()
        return success
    finally:
        conn.close()

init_db()

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

# --- SIDEBAR TOOLS ---
st.sidebar.title("Tools / أدوات")
if os.path.exists(DB_NAME):
    with open(DB_NAME, "rb") as f:
        st.sidebar.download_button(
            label="Download Database 📥" if lang == "English" else "تحميل قاعدة البيانات",
            data=f,
            file_name="hospital_management.db",
            mime="application/octet-stream"
        )

chat_tab, admin_tab = st.tabs(["Chat", "Dashboard"] if lang == "English" else ["الدردشة", "لوحة التحكم"])

with chat_tab:
    st.title("Clinic Assistant" if lang == "English" else "مساعد العيادة")
    current_date = datetime.now().strftime("%A, %B %d, %Y")

    conn = get_db_connection()
    booked_df = pd.read_sql_query("SELECT doc_id, slot FROM appointments", conn)
    conn.close()
    schedule = booked_df.to_string(index=False) if not booked_df.empty else "none"

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Type here..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        system_instruction = f"""
        Receptionist. Today: {current_date}. Year: 2026.
        Docs: {DOCTOR_LIST}. Busy: {schedule}.
        MANDATORY: Ask for Name and Phone. 
        Use tags: [BOOKING: Name, DocID, YYYY-MM-DD HH:MM, Phone] or [CANCEL: Name, DocID]
        """

        with st.chat_message("assistant"):
            try:
                response = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
                )
                ai_response = response.choices[0].message.content
                st.markdown(ai_response)

                if "[BOOKING:" in ai_response:
                    data = ai_response.split("[BOOKING:")[1].split("]")[0].split(",")
                    if len(data) >= 4:
                        name, d_id, slot, phone = [x.strip() for x in data]
                        success, err = try_booking(name, d_id, slot, phone)
                        if success:
                            st.success("Booking saved!")
                            show_whatsapp_button(phone, f"Confirmed! {name}, appt with {DOCTOR_LIST[d_id]['en']} at {slot}.")
                            st.rerun()

                if "[CANCEL:" in ai_response:
                    data = ai_response.split("[CANCEL:")[1].split("]")[0].split(",")
                    if len(parts := [p.strip() for p in data]) >= 2:
                        if cancel_booking(parts[0], parts[1]):
                            st.error("Deleted.")
                            st.rerun()

                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
            except Exception as e:
                st.error(f"Error: {e}")

with admin_tab:
    st.subheader("Interactive Staff Dashboard")
    conn = get_db_connection()
    data = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not data.empty:
        # INTERACTIVE METRICS: Showing how many patients per doctor
        cols = st.columns(3)
        total_patients = len(data)
        st.sidebar.metric("Total Patients", total_patients)

        for id, info in DOCTOR_LIST.items():
            doc_data = data[data['doc_id'] == id]
            doc_name = info["en"] if lang == "English" else info["ar"]
            
            with st.expander(f"👨‍⚕️ {doc_name} — ({len(doc_data)} Patients)"):
                if not doc_data.empty:
                    st.table(doc_data[['patient_name', 'slot', 'phone']])
                else:
                    st.write("No appointments.")

        if st.button("Clear All Bookings"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("No bookings yet.")
