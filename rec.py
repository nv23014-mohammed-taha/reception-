import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime
import os
import urllib.parse # Used to format the WhatsApp message for the web link

st.set_page_config(page_title="Clinic page", layout="wide")

lang = st.sidebar.selectbox("language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Updated: Added a 'phone' column to store patient numbers
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
    conn.commit()
    conn.close()

# --- WHATSAPP AUTOMATION HELPER ---
def show_whatsapp_button(phone, message):
    """Creates a clickable WhatsApp button for the confirmation/reminder."""
    encoded_msg = urllib.parse.quote(message)
    # Clean the phone number (keep only digits)
    clean_phone = "".join(filter(str.isdigit, phone))
    url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
    
    st.markdown(f"""
        <div style="text-align: center; margin: 10px 0;">
            <a href="{url}" target="_blank">
                <button style="background-color: #25D366; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%;">
                    📲 Send WhatsApp Confirmation/Reminder
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
        cursor.execute("DELETE FROM appointments WHERE patient_name LIKE ? AND doc_id=?",
                       (f"%{name}%", doc))
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

text = {
    "title": "Clinic Assistant" if lang == "English" else "مساعد العيادة",
    "input": "Type here..." if lang == "English" else "اكتب هنا...",
    "dashboard": "Appointments" if lang == "English" else "المواعيد",
    "clear": "Clear All" if lang == "English" else "حذف الكل",
    "empty": "No bookings yet" if lang == "English" else "لا توجد مواعيد",
}

chat_tab, admin_tab = st.tabs(["Chat", "Dashboard"] if lang == "English" else ["الدردشة", "لوحة التحكم"])

with chat_tab:
    st.title(text["title"])
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

    if user_input := st.chat_input(text["input"]):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # AI INSTRUCTION: Must ask for phone number now
        system_instruction = f"""
        you are a clinic receptionist. respond in {"Arabic" if lang == "العربية" else "English"}.
        today: {current_date} (Year 2026).
        doctors: {DOCTOR_LIST}
        busy slots: {schedule}

        RULES:
        1. If booking, you MUST ask for the patient's Name AND Phone number.
        2. use: [BOOKING: Name, DocID, YYYY-MM-DD HH:MM, Phone]
        3. use: [CANCEL: Name, DocID]
        """

        with st.chat_message("assistant"):
            try:
                response = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
                )
                ai_response = response.choices[0].message.content
                st.markdown(ai_response)

                # Process Cancellation
                if "[CANCEL:" in ai_response:
                    data = ai_response.split("[CANCEL:")[1].split("]")[0]
                    parts = [p.strip() for p in data.split(",")]
                    if len(parts) >= 2:
                        if cancel_booking(parts[0], parts[1]):
                            st.error("Booking removed." if lang == "English" else "تم حذف الموعد")
                            st.rerun() # Refresh to clear dashboard
                        else:
                            st.warning("Not found.")

                # Process Booking
                if "[BOOKING:" in ai_response:
                    data = ai_response.split("[BOOKING:")[1].split("]")[0]
                    parts = [p.strip() for p in data.split(",")]
                    if len(parts) >= 4:
                        name, d_id, slot, phone = parts[0], parts[1], parts[2], parts[3]
                        success, err = try_booking(name, d_id, slot, phone)
                        if success:
                            st.success("Confirmed!" if lang == "English" else "تم الحجز")
                            
                            # CREATE WHATSAPP MESSAGE
                            doc_name = DOCTOR_LIST[d_id]["en"] if lang == "English" else DOCTOR_LIST[d_id]["ar"]
                            msg = f"Hello {name}! 🏥 Your appointment with {doc_name} is set for {slot}. See you soon!"
                            if lang == "العربية":
                                msg = f"مرحباً {name}! 🏥 موعدك مع {doc_name} في {slot}. نراك قريباً!"
                            
                            show_whatsapp_button(phone, msg)
                            st.balloons()
                        else:
                            st.warning(f"Failed: {err}")

                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
            except Exception as e:
                st.error(f"Error: {e}")

with admin_tab:
    st.subheader(text["dashboard"])
    conn = get_db_connection()
    data = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not data.empty:
        for id, info in DOCTOR_LIST.items():
            df = data[data['doc_id'] == id]
            name = info["en"] if lang == "English" else info["ar"]
            with st.expander(f"{name} ({len(df)})"):
                if not df.empty:
                    # Added phone column to dashboard table
                    st.table(df[['patient_name', 'slot', 'phone']])

        if st.button(text["clear"]):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info(text["empty"])
