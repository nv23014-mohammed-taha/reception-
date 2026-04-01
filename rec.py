import streamlit as st
from mistralai.client import Mistral
import sqlite3
from datetime import datetime, timedelta

# --- 1. INITIALIZE MISTRAL ---
try:
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
except Exception:
    st.error("Please add MISTRAL_API_KEY to Streamlit Secrets.")
    st.stop()

# --- 2. DATABASE LOGIC (CONFLICT DETECTION) ---
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
    
    # Check if this doctor is busy at this exact time
    c.execute("SELECT * FROM appointments WHERE doc_id=? AND slot=?", (doc_id, requested_slot))
    existing = c.fetchone()
    
    if existing:
        # CONFLICT! Suggest 1 hour later
        dt_obj = datetime.strptime(requested_slot, "%Y-%m-%d %H:%M")
        alt_slot = (dt_obj + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        conn.close()
        return False, alt_slot
    
    # SUCCESS! Book the latest request
    c.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)", 
              (patient_name, doc_id, requested_slot))
    conn.commit()
    conn.close()
    return True, None

init_db()

# --- 3. THE FULL DOCTOR DIRECTORY ---
DOCTORS = {
    "1": {"en": "Dr. Faisal Al-Mahmood (Cardiology)", "ar": "فيصل المحمود (قلب)"},
    "2": {"en": "Dr. Mariam Al-Sayed (Pediatrics)", "ar": "مريم السيد (أطفال)"},
    "3": {"en": "Dr. Yousef Al-Haddad (Orthopedics)", "ar": "يوسف الحداد (عظام)"},
    "4": {"en": "Dr. Noura Al-Khalifa (Dermatology)", "ar": "نورة الخليفة (جلدية)"},
    "5": {"en": "Dr. Khalid Al-Fares (Plastic Surgery)", "ar": "خالد الفارس (جراحة تجميل)"},
    "6": {"en": "Dr. Sara Al-Ansari (OB-GYN / Gynecology)", "ar": "سارة الأنصاري (نساء وولادة)"},
    "7": {"en": "Dr. Jasim Al-Ghanem (Urology)", "ar": "جاسم الغانم (مسالك بولية)"},
    "8": {"en": "Dr. Layla Al-Mulla (Neurology)", "ar": "ليلى الملا (مخ وأعصاب)"},
    "9": {"en": "Dr. Hassan Ibrahim (Ophthalmology)", "ar": "حسن إبراهيم (عيون)"},
    "10": {"en": "Dr. Ahmed Al-Aali (General Medicine)", "ar": "أحمد العالي (طب عام)"}
}

# --- 4. STREAMLIT UI ---
st.set_page_config(page_title="NCST Smart Clinic", page_icon="🏥")
st.title("🏥 AI Healthcare Receptionist")

# Sidebar for Schedule Visibility
with st.sidebar:
    st.header("Doctor Directory / الدليل الطبي")
    for id, info in DOCTORS.items():
        st.write(f"**ID {id}:** {info['en']}")
    
    st.divider()
    st.subheader("Current Bookings")
    conn = sqlite3.connect('hospital_management.db')
    res = conn.execute("SELECT patient_name, slot FROM appointments").fetchall()
    for r in res:
        st.caption(f"📅 {r[1]} - {r[0]}")
    conn.close()

# Chat Logic
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("How can I help? / كيف يمكنني مساعدتك؟"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Mistral Processing
    sys_prompt = f"""
    You are a professional medical receptionist. 
    DOCTORS: {DOCTORS}
    
    CRITICAL RULES:
    1. If the user asks for Plastic Surgery, recommend Dr. Khalid (ID 5).
    2. If they ask for Gynecology/Gynaecology, recommend Dr. Sara (ID 6).
    3. You must collect: Patient Name, Doctor ID, and Time (Format: YYYY-MM-DD HH:MM).
    4. Speak in the user's language (English or Arabic).
    """

    with st.chat_message("assistant"):
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages
        )
        msg = response.choices[0].message.content
        st.markdown(msg)
        st.session_state.messages.append({"role": "assistant", "content": msg})
