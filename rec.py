import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & MISTRAL SETUP ---
st.set_page_config(page_title="NCST AI Clinic", layout="wide", page_icon="🏥")

# Accessing the API Key safely
if "MISTRAL_API_KEY" in st.secrets:
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
else:
    st.error("Missing MISTRAL_API_KEY in Streamlit Secrets!")
    st.stop()

# --- 2. DATABASE ENGINE ---
def init_db():
    conn = sqlite3.connect('hospital_management.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_name TEXT, doc_id TEXT, slot TEXT)''')
    conn.commit()
    conn.close()

def check_and_book(patient_name, doc_id, requested_slot):
    conn = sqlite3.connect('hospital_management.db', check_same_thread=False)
    c = conn.cursor()
    
    # Check if slot is taken for that specific doctor
    c.execute("SELECT * FROM appointments WHERE doc_id=? AND slot=?", (doc_id, requested_slot))
    if c.fetchone():
        try:
            dt_obj = datetime.strptime(requested_slot, "%Y-%m-%d %H:%M")
            alt_slot = (dt_obj + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        except: 
            alt_slot = "another time"
        conn.close()
        return False, alt_slot
    
    # Insert new record
    c.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)", 
              (patient_name, doc_id, requested_slot))
    conn.commit()
    conn.close()
    return True, None

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
    st.title("🏥 Smart AI Receptionist")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("How can I help?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): 
            st.markdown(prompt)

        # Updated System Prompt for better formatting consistency
        sys_prompt = f"""
        You are a medical receptionist for NCST AI Clinic. 
        Available Doctors: {DOCTORS}. 
        Help patients book appointments. When they confirm a doctor and a time, 
        you MUST end your response with exactly this tag: 
        [BOOKING: Name, DoctorID, YYYY-MM-DD HH:MM]
        Example: [BOOKING: Ahmed Ali, 1, 2026-05-15 10:00]
        """
        
        with st.chat_message("assistant"):
            try:
                response = client.chat.complete(
                    model="mistral-large-latest", 
                    messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages
                )
                msg = response.choices[0].message.content
                st.markdown(msg)
                
                # Logic to catch the booking tag
                if "[BOOKING:" in msg:
                    try:
                        # Extract and clean the data
                        raw_data = msg.split("[BOOKING:")[1].split("]")[0]
                        data = [item.strip() for item in raw_data.split(",")]
                        
                        if len(data) >= 3:
                            p_name, d_id, p_time = data[0], data[1], data[2]
                            success, alt = check_and_book(p_name, d_id, p_time)
                            
                            if success:
                                st.success(f"✅ Appointment saved for {p_name}!")
                                st.rerun() # Refresh to update the Dashboard immediately
                            else:
                                st.warning(f"❌ That time is taken. Suggested: {alt}")
                    except Exception as e:
                        st.error(f"Error processing booking data: {e}")
                
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except Exception as e:
                st.error(f"Mistral API Error: {e}")

# --- TAB 2: INTEGRATED DASHBOARD ---
with tab_dash:
    st.title("👨‍⚕️ Doctor Schedules")
    
    conn = sqlite3.connect('hospital_management.db', check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric("Total Appointments", len(df))
        
        # Grouping by Doctor for a cleaner look
        for d_id, d_info in DOCTORS.items():
            doc_df = df[df['doc_id'] == d_id]
            with st.expander(f"{d_info['en']} - ({len(doc_df)} Patients)"):
                if not doc_df.empty:
                    # Clean up the display table
                    display_df = doc_df[['patient_name', 'slot']].rename(
                        columns={'patient_name':'Patient Name', 'slot':'Appointment Time'}
                    )
                    st.table(display_df)
                else:
                    st.write("No patients scheduled.")
        
        st.divider()
        if st.button("🗑️ Clear All Records"):
            conn = sqlite3.connect('hospital_management.db')
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("The clinic schedule is currently empty. Try booking an appointment in the chat!")
