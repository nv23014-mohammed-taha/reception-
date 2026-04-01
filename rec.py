import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & MISTRAL SETUP ---
st.set_page_config(page_title="NCST AI Clinic", layout="wide", page_icon="🏥")

try:
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
except Exception:
    st.error("Missing MISTRAL_API_KEY in Streamlit Secrets!")
    st.stop()

# --- 2. DATABASE ENGINE ---
def init_db():
    conn = sqlite3.connect('hospital_management.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY, patient_name TEXT, doc_id TEXT, slot TEXT)''')
    conn.commit()
    conn.close()

def check_and_book(patient_name, doc_id, requested_slot):
    conn = sqlite3.connect('hospital_management.db')
    c = conn.cursor()
    c.execute("SELECT * FROM appointments WHERE doc_id=? AND slot=?", (doc_id, requested_slot))
    if c.fetchone():
        try:
            dt_obj = datetime.strptime(requested_slot, "%Y-%m-%d %H:%M")
            alt_slot = (dt_obj + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        except: alt_slot = "another time"
        conn.close()
        return False, alt_slot
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
        with st.chat_message("user"): st.markdown(prompt)

        sys_prompt = f"Receptionist mode. Doctors: {DOCTORS}. End bookings with: [BOOKING: Name, ID, Time]"
        
        with st.chat_message("assistant"):
            response = client.chat.complete(model="mistral-large-latest", 
                                            messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages)
            msg = response.choices[0].message.content
            st.markdown(msg)
            
            if "[BOOKING:" in msg:
                data = msg.split("[BOOKING:")[1].split("]")[0].split(",")
                success, alt = check_and_book(data[0].strip(), data[1].strip(), data[2].strip())
                if success: st.success("✅ Appointment Saved!")
                else: st.warning(f"❌ Slot Taken! Try {alt}")
            
            st.session_state.messages.append({"role": "assistant", "content": msg})

# --- TAB 2: INTEGRATED DASHBOARD ---
with tab_dash:
    st.title("👨‍⚕️ Doctor Schedules")
    
    conn = sqlite3.connect('hospital_management.db')
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        col_metric, col_table = st.columns([1, 3])
        col_metric.metric("Total Patients", len(df))
        
        # Grouping by Doctor
        for d_id, d_info in DOCTORS.items():
            doc_df = df[df['doc_id'] == d_id]
            with st.expander(f"{d_info['en']} - ({len(doc_df)} Patients)"):
                if not doc_df.empty:
                    st.table(doc_df[['patient_name', 'slot']].rename(columns={'patient_name':'Patient', 'slot':'Time'}))
                else:
                    st.write("No patients today.")
        
        st.divider()
        if st.button("🗑️ Clear All Records"):
            conn = sqlite3.connect('hospital_management.db')
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("The clinic schedule is currently empty.")
