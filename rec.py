import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import os
import re
import tempfile
import hashlib
import speech_recognition as sr
from fpdf import FPDF
from mistralai import Mistral

st.set_page_config(page_title="AlShifa Clinic", page_icon="🏥", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=DM+Sans:wght@300;400;500&display=swap');

:root {
    --bg: #F7F3EE;
    --text: #1A1410;
    --accent: #C9A84C;
    --accent-soft: #E8D5A3;
    --secondary: #8C7B6B;
    --card: #FFFFFF;
    --border-color: #E8E0D5;
}

html, body, [data-testid="stAppViewContainer"] { 
    background-color: var(--bg) !important; 
    font-family: 'DM Sans', sans-serif !important; 
    color: var(--text) !important; 
}

header, footer, #MainMenu { visibility: hidden; }
.main .block-container { padding: 0 !important; max-width: 100% !important; }

.navbar { 
    background: var(--text); 
    padding: 1.5rem 3rem; 
    display: flex; 
    align-items: center; 
    justify-content: space-between; 
}

.brand { 
    font-family: 'Cormorant Garamond', serif; 
    font-size: 1.75rem; 
    font-weight: 600; 
    color: var(--accent); 
    letter-spacing: 0.02em; 
}

.brand span { color: #fff; font-weight: 300; }

.tabs-nav [data-baseweb="tab-list"] { 
    background: transparent !important; 
    border-bottom: 1px solid var(--border-color) !important; 
    padding: 0 3rem !important; 
}

.tabs-nav [data-baseweb="tab"] { 
    font-size: 0.75rem !important; 
    letter-spacing: 0.12em !important; 
    text-transform: uppercase !important; 
    color: var(--secondary) !important; 
    padding: 1.25rem 1.5rem !important; 
    background: transparent !important; 
}

.tabs-nav [aria-selected="true"] { 
    color: var(--text) !important; 
    border-bottom-color: var(--accent) !important; 
}

.hero { text-align: center; padding: 4rem 1rem 2rem; }
.hero h1 { 
    font-family: 'Cormorant Garamond', serif; 
    font-size: 3rem; 
    font-weight: 300; 
    margin-bottom: 0.5rem; 
}

.stButton button { 
    background: var(--text) !important; 
    color: var(--accent) !important; 
    border-radius: 2px !important; 
    font-size: 0.7rem !important; 
    letter-spacing: 0.15em !important; 
    text-transform: uppercase !important; 
    padding: 0.75rem 2rem !important; 
    transition: all 0.2s ease;
}

.stButton button:hover { opacity: 0.9; transform: translateY(-1px); }

.stTextInput input, .stSelectbox select, .stNumberInput input { 
    border: 1px solid var(--border-color) !important; 
    background: white !important; 
    border-radius: 2px !important;
}

.metric-card [data-testid="stMetricValue"] { 
    font-family: 'Cormorant Garamond', serif !important; 
    font-size: 3rem !important; 
    font-weight: 300 !important; 
}

.heading { 
    font-family: 'Cormorant Garamond', serif; 
    font-size: 1.5rem; 
    font-weight: 300; 
    margin: 2.5rem 0 1rem; 
    padding-bottom: 0.5rem; 
    border-bottom: 1px solid var(--border-color); 
}

.location-box { 
    background: white; 
    border: 1px solid var(--border-color); 
    padding: 1.5rem; 
    margin: 1rem 0; 
    display: flex; 
    gap: 1rem; 
}

.maps-link { 
    display: inline-block; 
    margin-top: 0.5rem; 
    padding: 0.4rem 1rem; 
    background: var(--text); 
    color: var(--accent) !important; 
    font-size: 0.65rem; 
    text-transform: uppercase; 
    text-decoration: none !important; 
}
</style>
""", unsafe_allow_html=True)

DB_PATH = "hospital_management.db"
CLINIC_NAME = "AlShifa Clinic"
CLINIC_ADDR = "Building 115, Block 945, Street 4504, Awali, Al-Janubiyah, Bahrain"
MAPS_URL = "https://maps.google.com/?q=Building+115+Block+945+Street+4504+Awali+Bahrain"

DOCTORS = {
    "1":  {"name": "Dr. Faisal Al-Mahmood", "field": "Cardiology"},
    "2":  {"name": "Dr. Mariam Al-Sayed",   "field": "Pediatrics"},
    "3":  {"name": "Dr. Yousef Al-Haddad",  "field": "Orthopedics"},
    "4":  {"name": "Dr. Noura Al-Khalifa",  "field": "Dermatology"},
    "5":  {"name": "Dr. Khalid Al-Fares",   "field": "General Medicine"},
    "6":  {"name": "Dr. Sara Al-Ansari",    "field": "Gynecology"},
    "7":  {"name": "Dr. Jasim Al-Ghanem",   "field": "Neurology"},
    "8":  {"name": "Dr. Layla Al-Mulla",    "field": "Ophthalmology"},
    "9":  {"name": "Dr. Hassan Ibrahim",    "field": "ENT"},
    "10": {"name": "Dr. Ahmed Al-Aali",     "field": "Psychiatry"},
}

@st.cache_resource
def connect_ai():
    key = st.secrets.get("MISTRAL_API_KEY")
    return Mistral(api_key=key) if key else None

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT, phone TEXT, doc_id TEXT, slot TEXT,
            status TEXT DEFAULT 'confirmed',
            UNIQUE(doc_id, slot))""")
        
        info = conn.execute("PRAGMA table_info(appointments)").fetchall()
        if 'status' not in [c[1] for c in info]:
            conn.execute("ALTER TABLE appointments ADD COLUMN status TEXT DEFAULT 'confirmed'")
            
        conn.execute("""CREATE TABLE IF NOT EXISTS schedules (
            doc_id TEXT PRIMARY KEY, start_h INTEGER, end_h INTEGER)""")

def fetch_schedule(doc_id):
    with get_db() as conn:
        row = conn.execute("SELECT start_h, end_h FROM schedules WHERE doc_id=?", (doc_id,)).fetchone()
        if row: return {"start": row[0], "end": row[1]}
        conn.execute("INSERT OR IGNORE INTO schedules VALUES (?,?,?)", (doc_id, 9, 18))
        return {"start": 9, "end": 18}

def validate_booking(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        if dt <= datetime.now(): return False, "Time must be in the future"
        
        sched = fetch_schedule(doc_id)
        if not (dt.weekday() < 5 and sched["start"] <= dt.hour < sched["end"]):
            return False, "Doctor is not available at this time"
            
        with get_db() as conn:
            if conn.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot)).fetchone():
                return False, "This slot is already booked"
        return True, None
    except:
        return False, "Invalid date/time format"

def save_booking(name, phone, doc_id, slot):
    ok, msg = validate_booking(doc_id, slot)
    if not ok: return False, msg
    
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?,?,?,?)",
                (name.lower().strip(), phone, doc_id, slot)
            )
        return True, None
    except Exception as e:
        return False, str(e)

def remove_booking(name, doc_id):
    with get_db() as conn:
        conn.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name.lower().strip(), doc_id))

def update_booking(name, doc_id, slot):
    ok, msg = validate_booking(doc_id, slot)
    if not ok: return False, msg
    
    with get_db() as conn:
        cursor = conn.execute("UPDATE appointments SET slot=? WHERE patient_name=? AND doc_id=?", 
                           (slot, name.lower().strip(), doc_id))
        if cursor.rowcount == 0: return False, "Appointment not found"
    return True, None

def create_receipt(name, doctor, slot):
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Helvetica", 'B', 22)
    pdf.set_text_color(26, 20, 16)
    pdf.cell(0, 20, CLINIC_NAME.upper(), ln=True, align='C')
    
    pdf.set_font("Helvetica", '', 10)
    pdf.set_text_color(140, 123, 107)
    pdf.cell(0, 5, "EXCELLENCE IN HEALTHCARE - BAHRAIN", ln=True, align='C')
    pdf.ln(15)
    
    pdf.set_font("Helvetica", 'B', 14)
    pdf.set_text_color(201, 168, 76)
    pdf.cell(0, 10, "APPOINTMENT CONFIRMATION", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", '', 12)
    pdf.set_text_color(26, 20, 16)
    
    details = [
        ("Patient", name.title()),
        ("Practitioner", doctor),
        ("Date & Time", slot),
        ("Location", CLINIC_ADDR)
    ]
    
    for label, val in details:
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(40, 10, f"{label}:", 0)
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, 10, val, 0, 1)
    
    pdf.ln(20)
    pdf.set_font("Helvetica", 'I', 10)
    pdf.set_text_color(140, 123, 107)
    pdf.multi_cell(0, 6, "Kindly arrive 10 minutes prior to your session. For any changes, please use our digital assistant.", align='C')
    
    return pdf.output(dest='S').encode('latin-1')

init_db()
ai = connect_ai()

if "session" not in st.session_state:
    st.session_state.session = {"user": None, "history": [], "name": "Guest", "phone": ""}

def sign_out():
    st.session_state.session = {"user": None, "history": [], "name": "Guest", "phone": ""}
    st.rerun()

st.markdown(f"""
<div class="navbar">
    <div class="brand">AlShifa <span>Clinic</span></div>
    <div style="font-size:0.7rem; color:var(--secondary);">{f'ACTIVE: {st.session_state.session["user"].upper()}' if st.session_state.session["user"] else ''}</div>
</div>
""", unsafe_allow_html=True)

if not st.session_state.session["user"]:
    st.markdown("<div style='height:4rem'></div>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown('<div class="hero"><h1>Welcome</h1><p style="color:var(--secondary)">Please identify yourself to proceed</p></div>', unsafe_allow_html=True)
        
        t1, t2, t3 = st.tabs(["Patient", "Staff", "Guest"])
        
        with t1:
            n = st.text_input("Full Name", placeholder="e.g. Sara Ahmed")
            p = st.text_input("Phone Number", placeholder="+973 ...")
            if st.button("Enter as Patient", use_container_width=True):
                if n.strip():
                    st.session_state.session.update({"user": "patient", "name": n.strip(), "phone": p.strip()})
                    st.rerun()
                else: st.error("Name is required")
                
        with t2:
            pw = st.text_input("Access Key", type="password")
            if st.button("Staff Login", use_container_width=True):
                if hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(b"admin123").hexdigest():
                    st.session_state.session["user"] = "admin"
                    st.rerun()
                else: st.error("Invalid key")
                
        with t3:
            st.markdown("<p style='font-size:0.8rem; color:var(--secondary); margin: 1rem 0;'>Browse our services and doctors. Login required for bookings.</p>", unsafe_allow_html=True)
            if st.button("Continue as Guest", use_container_width=True):
                st.session_state.session["user"] = "guest"
                st.rerun()
    st.stop()

if st.button("Sign Out", key="logout"): sign_out()

if st.session_state.session["user"] == "admin":
    st.markdown('<div style="padding: 2rem 3rem">', unsafe_allow_html=True)
    st.markdown('<div class="heading">Clinic Dashboard</div>', unsafe_allow_html=True)
    
    with get_db() as conn:
        all_appts = pd.read_sql_query("SELECT * FROM appointments ORDER BY slot", conn)
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total", len(all_appts))
    m2.metric("Today", len(all_appts[all_appts['slot'].str.startswith(datetime.now().strftime("%Y-%m-%d"))]))
    m3.metric("Staff", len(DOCTORS))
    
    st.markdown('<div class="heading">Current Appointments</div>', unsafe_allow_html=True)
    if all_appts.empty: st.info("No records found")
    else: st.dataframe(all_appts, use_container_width=True)
    
    st.markdown('<div class="heading">Staff Management</div>', unsafe_allow_html=True)
    ca, cb = st.columns([1, 2])
    with ca:
        d_id = st.selectbox("Select Practitioner", list(DOCTORS.keys()), format_func=lambda x: f"{DOCTORS[x]['name']} ({DOCTORS[x]['field']})")
        curr = fetch_schedule(d_id)
        s_h = st.number_input("Start Hour", 0, 23, curr["start"])
        e_h = st.number_input("End Hour", 0, 23, curr["end"])
        if st.button("Update Hours"):
            if s_h < e_h:
                with get_db() as conn:
                    conn.execute("REPLACE INTO schedules VALUES (?,?,?)", (d_id, s_h, e_h))
                st.success("Updated")
            else: st.error("Invalid range")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

doc_str = "\n".join([f"ID {k}: {v['name']} ({v['field']})" for k, v in DOCTORS.items()])
PROMPT = f"""You are a helpful concierge at {CLINIC_NAME} in Bahrain.
Address: {CLINIC_ADDR}
Maps: {MAPS_URL}
Hours: Sun-Thu, 9am-6pm.

Our Doctors:
{doc_str}

User: {st.session_state.session['name']}
Phone: {st.session_state.session['phone']}
Role: {st.session_state.session['user']}

Instructions:
- Be professional and warm.
- To book, confirm doctor and time, then use: [BOOKING: name, phone, doc_id, YYYY-MM-DD HH:MM]
- To cancel: [CANCEL: name, doc_id]
- To reschedule: [RESCHEDULE: name, doc_id, YYYY-MM-DD HH:MM]
- If a guest wants to book, politely ask them to login.
- Current date: {datetime.now().strftime('%A, %B %d, %Y')}
"""

if not st.session_state.session["history"]:
    st.markdown(f'<div class="hero"><h1>Hello, {st.session_state.session["name"]}</h1><p style="color:var(--secondary)">How can we assist you today?</p></div>', unsafe_allow_html=True)

for m in st.session_state.session["history"]:
    st.chat_message(m["role"]).write(m["content"])

audio = st.audio_input("Voice Input")
if audio:
    r = sr.Recognizer()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio.read())
        path = f.name
    try:
        with sr.AudioFile(path) as src:
            text = r.recognize_google(r.record(src))
            st.session_state.voice_data = text
    except: pass
    finally: os.unlink(path)
    st.rerun()

user_input = st.chat_input("Type your message...") or st.session_state.pop("voice_data", None)

if user_input:
    st.session_state.session["history"].append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)
    
    if ai:
        res = ai.chat.complete(model="mistral-large-latest", messages=[{"role": "system", "content": PROMPT}] + st.session_state.session["history"])
        raw_reply = res.choices[0].message.content
    else:
        raw_reply = "AI assistant is currently offline."
        
    clean_reply = re.sub(r'\[.*?\]', '', raw_reply).strip()
    st.chat_message("assistant").write(clean_reply)
    st.session_state.session["history"].append({"role": "assistant", "content": raw_reply})
    
    if "[BOOKING:" in raw_reply:
        match = re.search(r"\[BOOKING:(.*?)\]", raw_reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) == 4:
                n, p, d, s = parts
                if d not in DOCTORS:
                    d = next((k for k, v in DOCTORS.items() if v["name"].lower() in d.lower()), d)
                
                success, err = save_booking(n, p, d, s)
                if success:
                    st.success(f"Confirmed: {DOCTORS[d]['name']} at {s}")
                    pdf = create_receipt(n, f"{DOCTORS[d]['name']} ({DOCTORS[d]['field']})", s)
                    st.download_button("Download Receipt", pdf, f"Receipt_{n}.pdf", "application/pdf")
                else: st.error(err)
                
    if "[CANCEL:" in raw_reply:
        match = re.search(r"\[CANCEL:(.*?)\]", raw_reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) == 2:
                remove_booking(parts[0], parts[1])
                st.info("Appointment removed.")
                
    if "[RESCHEDULE:" in raw_reply:
        match = re.search(r"\[RESCHEDULE:(.*?)\]", raw_reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) == 3:
                success, err = update_booking(parts[0], parts[1], parts[2])
                if success:
                    st.success("Rescheduled successfully.")
                    pdf = create_receipt(parts[0], DOCTORS[parts[1]]['name'], parts[2])
                    st.download_button("Download New Receipt", pdf, f"Updated_Receipt_{parts[0]}.pdf", "application/pdf")
                else: st.error(err)
