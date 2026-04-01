import streamlit as st
from mistralai.client import Mistral
import sqlite3
from datetime import datetime, timedelta

# --- 1. SETUP & CLIENT ---
# Ensure MISTRAL_API_KEY is in your Streamlit Secrets
try:
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
except Exception:
    st.error("API Key missing! Add MISTRAL_API_KEY to your Streamlit Secrets.")
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
    # Conflict Check
    c.execute("SELECT * FROM appointments WHERE doc_id=? AND slot=?", (doc_id, requested_slot))
    if c.fetchone():
        try:
            dt_obj = datetime.strptime(requested_slot, "%Y-%m-%d %H:%M")
            alt_slot = (dt_obj + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        except:
            alt_slot = "another time"
        conn.close()
        return False, alt_slot
    
    # Insert Booking
    c.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)", 
              (patient_name, doc_id, requested_slot))
    conn.commit()
    conn.close()
    return True, None

init_db()

# --- 3. EXPANDED DOCTOR DIRECTORY ---
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

# --- 4. CHAT INTERFACE ---
st.set_page_config(page_title="NCST AI Clinic", page_icon="🏥")
st.title("🏥 Smart AI Medical Receptionist")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display History
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# User Input
if prompt := st.chat_input("How can I help? / كيف يمكنني مساعدتك؟"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # System Instructions
    sys_prompt = f"""
    You are a professional medical receptionist. 
    DOCTOR DIRECTORY: {DOCTORS}
    
    YOUR GOAL:
    1. Help users find the right doctor based on symptoms.
    2. Collect: [Patient Name], [Doctor ID], and [Time in YYYY-MM-DD HH:MM].
    3. Once you have all 3 pieces of info, you MUST write this exact hidden tag at the END:
       [BOOKING: Name, ID, Time]
    4. Respond in the user's language (English/Arabic).
    """

    with st.chat_message("assistant"):
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages
        )
        msg_content = response.choices[0].message.content
        st.markdown(msg_content)
        
        # --- HIDDEN TRIGGER LOGIC ---
        if "[BOOKING:" in msg_content:
            try:
                # Parse the tag: [BOOKING: Name, ID, Time]
                raw_data = msg_content.split("[BOOKING:")[1].split("]")[0].split(",")
                p_name = raw_data[0].strip()
                d_id = raw_data[1].strip()
                t_val = raw_data[2].strip()
                
                success, alt = check_and_book(p_name, d_id, t_val)
                
                if success:
                    st.success(f"✅ Confirmed: {p_name} booked with ID {d_id} at {t_val}")
                else:
                    st.warning(f"⚠️ Conflict! That slot is taken. Suggesting {alt} instead.")
            except:
                st.error("Error processing booking format.")

        st.session_state.messages.append({"role": "assistant", "content": msg_content})
