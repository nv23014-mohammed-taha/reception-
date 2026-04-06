import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & MISTRAL SETUP ---
st.set_page_config(page_title="NCST AI Clinic", layout="wide", page_icon="🏥")

# Accessing the API Key safely from Streamlit Secrets
if "MISTRAL_API_KEY" in st.secrets:
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
else:
    st.error("Missing MISTRAL_API_KEY in Streamlit Secrets!")
    st.stop()

# --- 2. DATABASE ENGINE (With Race-Condition Protection) ---
DB_FILE = 'hospital_management.db'

def init_db():
    """Initializes the database with a Unique Constraint to prevent double-booking."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  patient_name TEXT, 
                  doc_id TEXT, 
                  slot TEXT,
                  UNIQUE(doc_id, slot))''')
    conn.commit()
    conn.close()

def check_and_book(patient_name, doc_id, requested_slot):
    """Uses a 'BEGIN IMMEDIATE' transaction to lock the database during the check/write phase."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT id FROM appointments WHERE doc_id=? AND slot=?", (doc_id, requested_slot))
        
        if c.fetchone():
            dt_obj = datetime.strptime(requested_slot, "%Y-%m-%d %H:%M")
            alt_slot = (dt_obj + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            conn.rollback()
            return False, alt_slot
        
        c.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)", 
                  (patient_name, doc_id, requested_slot))
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "This slot was just taken by another patient!"
    except Exception as e:
        conn.rollback()
        return False, f"System Error: {e}"
    finally:
        conn.close()

init_db()

# --- 3. DOCTOR DIRECTORY ---
DOCTORS = {
    "1": {"en": "Dr. Faisal Al-Mahmood (Cardiology)", "ar": "فيصل المحمود (قلب)"},
    "2": {"en": "Dr. Mariam Al-Sayed (Pediatrics)", "ar": "مريم السيد (أطفال)"},
    "3": {"en": "Dr. Yousef Al-Haddad (Orthopedics)", "ar": "يوسف الحداد (عظام)"},
    "4": {"en": "Dr. Noura Al-Khalifa (Dermatology)", "ar": "نورة الخليفة (جلدية)"},
    "5": {"en": "Dr. Khalid Al-Fares (Plastic Surgery)", "ar": "خالد الفارس (تجميل)"},
    "6": {"en": "Dr. Sara Al-Ansari (OB-GYN)", "ar": "سارة الأنصاري (نساء وولادة)"},
    "7": {"en": "Dr. Jasim Al-Ghanem (Urology)", "ar": "جاسم الغانم (مسالك)"},
    "8": {"en": "Dr. Layla Al-Mulla (Neurology)", "ar": "ليلى الملا (أعصاب)"},
    "9": {"en": "Dr. Hassan Ibrahim (Ophthalmology)", "ar": "حسن إبراهيم (عيون)"},
    "10": {"en": "Dr. Ahmed Al-Aali (General Medicine)", "ar": "أحمد العالي (طب عام)"}
}

# --- 4. NAVIGATION TABS ---
tab_chat, tab_dash = st.tabs(["💬 Patient Chat", "📊 Admin Dashboard"])

# --- TAB 1: CHAT INTERFACE ---
with tab_chat:
    st.title("🏥 NCST Smart AI Receptionist")

    # --- NEW: LIVE CONTEXT INJECTION ---
    # This fetches current bookings to tell the AI what is taken
    conn = sqlite3.connect(DB_FILE)
    current_bookings = pd.read_sql_query("SELECT doc_id, slot FROM appointments", conn)
    conn.close()
    
    booked_list = current_bookings.to_string(index=False) if not current_bookings.empty else "None"
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("How can I help you today?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): 
            st.markdown(prompt)

        # Updated System Prompt with LIVE data
        sys_prompt = f"""
        You are a medical receptionist for NCST AI Clinic. 
        Available Doctors: {DOCTORS}. 

        CRITICAL: The following slots are ALREADY BOOKED. Do NOT confirm these:
        {booked_list}

        If a patient asks for a booked slot, tell them it's taken and suggest the next hour.
        When they confirm a valid time, end with: [BOOKING: Name, DoctorID, YYYY-MM-DD HH:MM]
        """
        
        with st.chat_message("assistant"):
            try:
                response = client.chat.complete(
                    model="mistral-large-latest", 
                    messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages
                )
                msg = response.choices[0].message.content
                st.markdown(msg)
                
                if "[BOOKING:" in msg:
                    try:
                        raw_data = msg.split("[BOOKING:")[1].split("]")[0]
                        data = [item.strip() for item in raw_data.split(",")]
                        
                        if len(data) >= 3:
                            p_name, d_id, p_time = data[0], data[1], data[2]
                            success, alt = check_and_book(p_name, d_id, p_time)
                            
                            if success:
                                st.success(f"✅ Appointment saved for {p_name}!")
                                st.balloons()
                            else:
                                st.warning(f"❌ That slot is already in the database. Suggested: {alt}")
                    except Exception as e:
                        st.error(f"Error parsing booking: {e}")
                
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except Exception as e:
                st.error(f"Mistral API Error: {e}")

# --- TAB 2: ADMIN DASHBOARD ---
with tab_dash:
    st.title("👨‍⚕️ Management Dashboard")
    
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric("Total Appointments", len(df))
        for d_id, d_info in DOCTORS.items():
            doc_df = df[df['doc_id'] == d_id]
            with st.expander(f"{d_info['en']} - ({len(doc_df)} Patients)"):
                if not doc_df.empty:
                    display_df = doc_df[['patient_name', 'slot']].rename(
                        columns={'patient_name':'Patient Name', 'slot':'Appointment Time'}
                    )
                    st.table(display_df)
                else:
                    st.write("No appointments yet.")
        
        st.divider()
        if st.button("🗑️ Reset Clinic Database"):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("The schedule is currently clear.")
