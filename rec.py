import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os

st.set_page_config(page_title="Clinic page", layout="wide")

# Database Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
else:
    st.error("Hey, you forgot to add the MISTRAL_API_KEY to your secrets!")
    st.stop()

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False, timeout=10)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            patient_name TEXT, 
            doc_id TEXT, 
            slot TEXT,
            UNIQUE(doc_id, slot)
        )
    ''')
    conn.commit()
    conn.close()

def try_booking(name, doc_id, time_slot):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT id FROM appointments WHERE doc_id=? AND slot=?", (doc_id, time_slot))
        
        if cursor.fetchone():
            orig_time = datetime.strptime(time_slot, "%Y-%m-%d %H:%M")
            suggested_time = (orig_time + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            conn.rollback()
            return False, suggested_time
        
        cursor.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)", 
                       (name, doc_id, time_slot))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

init_db()

DOCTOR_LIST = {
    "1": {"en": "Dr. Faisal Al-Mahmood (Cardiology)"},
    "2": {"en": "Dr. Mariam Al-Sayed (Pediatrics)"},
    "3": {"en": "Dr. Yousef Al-Haddad (Orthopedics)"},
    "4": {"en": "Dr. Noura Al-Khalifa (Dermatology)"},
    "5": {"en": "Dr. Khalid Al-Fares (Plastic Surgery)"},
    "6": {"en": "Dr. Sara Al-Ansari (OB-GYN)"},
    "7": {"en": "Dr. Jasim Al-Ghanem (Urology)"},
    "8": {"en": "Dr. Layla Al-Mulla (Neurology)"},
    "9": {"en": "Dr. Hassan Ibrahim (Ophthalmology)"},
    "10": {"en": "Dr. Ahmed Al-Aali (General Medicine)"}
}

# --- SIDEBAR FOR DATABASE DOWNLOAD ---
st.sidebar.title("🛠️ Developer Tools")
if os.path.exists(DB_NAME):
    with open(DB_NAME, "rb") as f:
        st.sidebar.download_button(
            label="📥 Download Database (.db)",
            data=f,
            file_name="hospital_management.db",
            mime="application/octet-stream"
        )
else:
    st.sidebar.warning("No database file found yet.")

chat_tab, admin_tab = st.tabs(["💬 Virtual Receptionist", "📊 Staff Dashboard"])

with chat_tab:
    st.title("🏥 Welcome to the Clinic")
    
    # Get current time to fix the 2024 vs 2026 issue
    current_date_str = datetime.now().strftime("%A, %B %d, %Y")

    conn = get_db_connection()
    booked_df = pd.read_sql_query("SELECT doc_id, slot FROM appointments", conn)
    conn.close()
    live_schedule = booked_df.to_string(index=False) if not booked_df.empty else "No bookings yet."

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("How can I help you today?"):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Added "Today's Date" to the instruction so the AI knows it is 2026
        system_instruction = f"""
        You are a friendly receptionist at AI Clinic. 
        TODAY'S DATE: {current_date_str} (The year is 2026).
        Docs available: {DOCTOR_LIST}. 

        IMPORTANT: These times are ALREADY BOOKED:
        {live_schedule}

        If they want a booked slot, suggest another time.
        Once confirmed, you MUST include this tag: [BOOKING: Name, DocID, YYYY-MM-DD HH:MM]
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
                    try:
                        data_str = ai_response.split("[BOOKING:")[1].split("]")[0]
                        parts = [p.strip() for p in data_str.split(",")]
                        if len(parts) >= 3:
                            name, d_id, t_slot = parts[0], parts[1], parts[2]
                            is_ok, suggestion = try_booking(name, d_id, t_slot)
                            if is_ok:
                                st.success(f"Confirmed! {name} is booked for {t_slot}.")
                                st.balloons()
                            else:
                                st.warning(f"That slot is taken. Suggest {suggestion} instead.")
                    except Exception as e:
                        st.error(f"Format error: {e}")
                
                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
            except Exception as err:
                st.error(f"API Error: {err}")

with admin_tab:
    st.subheader("Current Appointments")
    conn = get_db_connection()
    all_data = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not all_data.empty:
        st.metric("Total Bookings", len(all_data))
        for id, info in DOCTOR_LIST.items():
            doc_filter = all_data[all_data['doc_id'] == id]
            with st.expander(f"{info['en']} ({len(doc_filter)})"):
                if not doc_filter.empty:
                    st.table(doc_filter[['patient_name', 'slot']])
        
        if st.button("Clear All Data"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("No bookings yet.")
