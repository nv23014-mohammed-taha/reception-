

Start free trial

Share
pasted_content.txt
Text · 30.42 KB
ownloadable appointment receipt (PDF lets do this insted of whatsapp and also remove teh whatsapp fetuere nd this is the error Booking failed: table appointments has no column named status fix them
Lite
I've received your request. I will fix the "status" column error in your database, remove the WhatsApp feature, and implement a downloadable PDF appointment receipt. Let me start by analyzing your project files.
I analyzed the source code, which includes WhatsApp messaging, database handling, and appointment management. Next, I'll identify the "status" column error and plan removal of WhatsApp features.

I have applied initial fixes and added the PDF receipt feature to the app. Next steps involve reviewing the code to identify the 'status' column error and plan its correction.

Lite
I have completed the requested updates for the AlShifa Clinic app.
Key Improvements:
Database Fix: I added a check in the setup_database function to ensure the status column exists in the appointments table. This resolves the "table appointments has no column named status" error.
WhatsApp Removal:
Removed the twilio import and all send_wa related helper functions.
Updated the UI labels from "WhatsApp Number" to "Phone Number".
Cleaned up the AI system prompt and action tags to stop generating WhatsApp-related instructions.
PDF Appointment Receipt:
Integrated the fpdf library to generate professional PDF receipts.
Added a "Download Appointment Receipt (PDF)" button that appears immediately after a successful booking or rescheduling.
The receipt includes the clinic name, patient details, doctor information, and appointment time.
You can download the updated source code from the attachment below. Make sure you have fpdf installed in your environment (pip install fpdf).
clinic_app_fixed.py
Code · 28.30 KB
View all files in this task
Task completed
How was this result?
Suggested follow-ups




clinic_app_fixed.py
from mistralai import Mistral
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os, re, tempfile, hashlib
import speech_recognition as sr
from fpdf import FPDF

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="AlShifa Clinic", page_icon="🏥", layout="wide")

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300&family=DM+Sans:wght@300;400;500&display=swap');

:root {
    --cream: #F7F3EE;
    --dark: #1A1410;
    --gold: #C9A84C;
    --gold-light: #E8D5A3;
    --muted: #8C7B6B;
    --surface: #FFFFFF;
    --border: #E8E0D5;
}

html, body, .stApp { background-color: var(--cream) !important; font-family: 'DM Sans', sans-serif !important; color: var(--dark) !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none; }

.clinic-header { background: var(--dark); padding: 24px 48px; display: flex; align-items: center; justify-content: space-between; }
.clinic-logo { font-family: 'Cormorant Garamond', serif; font-size: 26px; font-weight: 600; color: var(--gold); letter-spacing: 0.05em; }
.clinic-logo span { color: #fff; font-weight: 300; }
.clinic-tagline { font-size: 10px; color: var(--muted); letter-spacing: 0.15em; text-transform: uppercase; margin-top: 2px; }

.stTabs [data-baseweb="tab-list"] { background: transparent !important; border-bottom: 1px solid var(--border) !important; gap: 0 !important; padding: 0 48px !important; }
.stTabs [data-baseweb="tab"] { font-family: 'DM Sans', sans-serif !important; font-size: 12px !important; letter-spacing: 0.1em !important; text-transform: uppercase !important; color: var(--muted) !important; padding: 16px 24px !important; border-radius: 0 !important; border-bottom: 2px solid transparent !important; background: transparent !important; }
.stTabs [aria-selected="true"] { color: var(--dark) !important; border-bottom-color: var(--gold) !important; font-weight: 500 !important; }

.chat-welcome { text-align: center; padding: 52px 0 32px; }
.chat-welcome h2 { font-family: 'Cormorant Garamond', serif; font-size: 40px; font-weight: 300; color: var(--dark); margin-bottom: 10px; }
.chat-welcome p { color: var(--muted); font-size: 14px; line-height: 1.7; }

.stButton button { background: var(--dark) !important; color: var(--gold) !important; border: none !important; border-radius: 4px !important; font-family: 'DM Sans', sans-serif !important; font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.1em !important; text-transform: uppercase !important; padding: 12px 28px !important; }
.stButton button:hover { background: #2A2018 !important; }

.stTextInput input, .stSelectbox select, .stNumberInput input { border: 1px solid var(--border) !important; border-radius: 4px !important; font-family: 'DM Sans', sans-serif !important; font-size: 14px !important; background: white !important; color: var(--dark) !important; }
.stTextInput input:focus { border-color: var(--gold) !important; box-shadow: 0 0 0 2px rgba(201,168,76,0.15) !important; }

[data-testid="stMetricValue"] { font-family: 'Cormorant Garamond', serif !important; font-size: 44px !important; font-weight: 300 !important; color: var(--dark) !important; }
[data-testid="stMetricLabel"] { font-size: 10px !important; color: var(--muted) !important; letter-spacing: 0.1em !important; text-transform: uppercase !important; }

.section-title { font-family: 'Cormorant Garamond', serif; font-size: 24px; font-weight: 300; color: var(--dark); margin: 36px 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.admin-wrap { padding: 36px 48px; }

.location-card { background: white; border: 1px solid var(--border); border-radius: 4px; padding: 18px 22px; margin: 10px 0; display: flex; align-items: flex-start; gap: 14px; }
.location-icon { font-size: 22px; }
.location-text h4 { font-family: 'Cormorant Garamond', serif; font-size: 17px; font-weight: 400; color: var(--dark); margin: 0 0 3px; }
.location-text p { font-size: 12px; color: var(--muted); margin: 0; line-height: 1.5; }
.maps-btn { display: inline-block; margin-top: 8px; padding: 5px 14px; background: var(--dark); color: var(--gold) !important; border-radius: 100px; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; text-decoration: none !important; font-weight: 500; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--cream); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
BASE_DIR    = os.getcwd()
DB_PATH     = os.path.join(BASE_DIR, "hospital_management.db")
CLINIC_NAME = "AlShifa Clinic"
CLINIC_ADDR = "Building 115, Block 945, Street 4504, Awali, Al-Janubiyah, Bahrain"
MAPS_LINK   = "https://maps.google.com/?q=Building+115+Block+945+Street+4504+Awali+Bahrain"
ADMIN_HASH  = hashlib.sha256(b"admin123").hexdigest()

DOCTORS = {
    "1":  {"en": "Dr. Faisal Al-Mahmood", "specialty": "Cardiology",    "ar": "د. فيصل المحمود"},
    "2":  {"en": "Dr. Mariam Al-Sayed",   "specialty": "Pediatrics",    "ar": "د. مريم السيد"},
    "3":  {"en": "Dr. Yousef Al-Haddad",  "specialty": "Orthopedics",   "ar": "د. يوسف الحداد"},
    "4":  {"en": "Dr. Noura Al-Khalifa",  "specialty": "Dermatology",   "ar": "د. نورة الخليفة"},
    "5":  {"en": "Dr. Khalid Al-Fares",   "specialty": "General",       "ar": "د. خالد الفارس"},
    "6":  {"en": "Dr. Sara Al-Ansari",    "specialty": "Gynecology",    "ar": "د. سارة الأنصاري"},
    "7":  {"en": "Dr. Jasim Al-Ghanem",   "specialty": "Neurology",     "ar": "د. جاسم الغانم"},
    "8":  {"en": "Dr. Layla Al-Mulla",    "specialty": "Ophthalmology", "ar": "د. ليلى الملا"},
    "9":  {"en": "Dr. Hassan Ibrahim",    "specialty": "ENT",           "ar": "د. حسن إبراهيم"},
    "10": {"en": "Dr. Ahmed Al-Aali",     "specialty": "Psychiatry",    "ar": "د. أحمد العالي"},
}
DEFAULT_SCHEDULE = {"start": 9, "end": 18}

# ─── AI client ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_ai_client():
    if "MISTRAL_API_KEY" in st.secrets:
        return Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
    return None

ai_client = get_ai_client()

# ─── Database ─────────────────────────────────────────────────────────────────
def db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def setup_database():
    conn = db_connection(); cur = conn.cursor()
    # Create table if not exists
    cur.execute("""CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT, phone TEXT, doc_id TEXT, slot TEXT,
        UNIQUE(doc_id, slot))""")
    
    # Check if 'status' column exists, if not, add it
    cur.execute("PRAGMA table_info(appointments)")
    columns = [col[1] for col in cur.fetchall()]
    if 'status' not in columns:
        cur.execute("ALTER TABLE appointments ADD COLUMN status TEXT DEFAULT 'confirmed'")
        
    cur.execute("""CREATE TABLE IF NOT EXISTS doctor_schedule (
        doc_id TEXT PRIMARY KEY, start_hour INTEGER, end_hour INTEGER)""")
    conn.commit(); conn.close()

setup_database()

# ─── Appointment helpers ──────────────────────────────────────────────────────
def get_schedule(doc_id):
    conn = db_connection(); cur = conn.cursor()
    cur.execute("SELECT start_hour, end_hour FROM doctor_schedule WHERE doc_id=?", (doc_id,))
    row = cur.fetchone()
    if row: conn.close(); return {"start": row[0], "end": row[1]}
    cur.execute("INSERT OR IGNORE INTO doctor_schedule VALUES (?,?,?)",
                (doc_id, DEFAULT_SCHEDULE["start"], DEFAULT_SCHEDULE["end"]))
    conn.commit(); conn.close(); return DEFAULT_SCHEDULE

def is_future(slot):
    try: return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
    except: return False

def doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        s  = get_schedule(doc_id)
        return dt.weekday() < 5 and s["start"] <= dt.hour < s["end"]
    except: return False

def book_appointment(name, phone, doc_id, slot):
    name = name.lower().strip()
    if not is_future(slot):
        return False, "Please pick a future time"
    if not doctor_available(doc_id, slot):
        return False, "Doctor unavailable at that time"
    conn = db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot))
        if cur.fetchone():
            return False, "That slot is already taken"
        cur.execute(
            "INSERT INTO appointments (patient_name, phone, doc_id, slot, status) VALUES (?,?,?,?,'confirmed')",
            (name, phone, doc_id, slot)
        )
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def cancel_appointment(name, doc_id):
    conn = db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name.lower().strip(), doc_id))
    conn.commit(); conn.close(); return True

def reschedule_appointment(name, doc_id, new_slot):
    conn = db_connection(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM appointments WHERE patient_name=? AND doc_id=?", (name.lower().strip(), doc_id))
    if not cur.fetchone(): conn.close(); return False, "Appointment not found"
    if not doctor_available(doc_id, new_slot): conn.close(); return False, "Doctor unavailable"
    cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, new_slot))
    if cur.fetchone(): conn.close(); return False, "Slot already taken"
    cur.execute("UPDATE appointments SET slot=? WHERE patient_name=? AND doc_id=?",
                (new_slot, name.lower().strip(), doc_id))
    conn.commit(); conn.close(); return True, None

# ─── PDF Generation ───────────────────────────────────────────────────────────
def generate_receipt_pdf(name, doctor, slot):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(26, 20, 16) # --dark
    pdf.cell(0, 15, CLINIC_NAME, ln=True, align='C')
    
    pdf.set_font("Arial", '', 10)
    pdf.set_text_color(140, 123, 107) # --muted
    pdf.cell(0, 5, "Excellence in Healthcare - Bahrain", ln=True, align='C')
    pdf.ln(10)
    
    # Receipt Title
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(201, 168, 76) # --gold
    pdf.cell(0, 10, "APPOINTMENT RECEIPT", ln=True, align='C')
    pdf.ln(10)
    
    # Details
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(26, 20, 16)
    
    def add_row(label, value):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(50, 10, label, 0)
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, value, 0, 1)

    add_row("Patient Name:", name.title())
    add_row("Doctor:", doctor)
    add_row("Date & Time:", slot)
    add_row("Location:", CLINIC_ADDR)
    
    pdf.ln(15)
    pdf.set_font("Arial", 'I', 10)
    pdf.set_text_color(140, 123, 107)
    pdf.multi_cell(0, 5, "Please arrive 10 minutes before your scheduled time. If you need to cancel or reschedule, please contact us through the assistant.", align='C')
    
    # Footer
    pdf.set_y(-30)
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 10, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 0, 'C')
    
    return pdf.output(dest='S').encode('latin-1')

# ─── Audio ────────────────────────────────────────────────────────────────────
def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes); path = tmp.name
    try:
        with sr.AudioFile(path) as src: audio = r.record(src)
        return r.recognize_google(audio)
    except: return "Could not understand audio"
    finally: os.unlink(path)

# ─── Session state ────────────────────────────────────────────────────────────
for k, v in [("role", None), ("history", []), ("patient_name", "Guest"), ("patient_phone", "")]:
    if k not in st.session_state: st.session_state[k] = v

# ─── Header ───────────────────────────────────────────────────────────────────
role_badge = f"🟢 {st.session_state.role.title()}" if st.session_state.role else ""
st.markdown(f"""
<div class="clinic-header">
    <div>
        <div class="clinic-logo">AlShifa <span>Clinic</span></div>
        <div class="clinic-tagline">Excellence in Healthcare · Bahrain</div>
    </div>
    <div style="font-size:12px;color:#6B5B4E;letter-spacing:0.05em;">{role_badge}</div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  LOGIN SCREEN
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.role is None:
    st.markdown("<div style='height:56px'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;margin-bottom:36px;">
            <div style="font-family:'Cormorant Garamond',serif;font-size:48px;font-weight:300;color:#1A1410;line-height:1.1;">Welcome</div>
            <div style="font-size:13px;color:#8C7B6B;margin-top:8px;">Select how you'd like to continue</div>
        </div>""", unsafe_allow_html=True)

        tab_a, tab_p, tab_g = st.tabs(["Administrator", "Patient Login", "Guest"])

        with tab_a:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            pw = st.text_input("Password", type="password", key="admin_pw", placeholder="Enter admin password")
            if st.button("Sign In as Administrator", use_container_width=True, key="admin_btn"):
                if hashlib.sha256(pw.encode()).hexdigest() == ADMIN_HASH:
                    st.session_state.role = "admin"; st.rerun()
                else: st.error("Incorrect password")
            st.caption("Default password: `admin123`")

        with tab_p:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            pname  = st.text_input("Your Name", key="p_name", placeholder="e.g. Ahmed Al-Rashid")
            pphone = st.text_input("Phone Number", key="p_phone", placeholder="+973 XXXX XXXX")
            if st.button("Continue as Patient", use_container_width=True, key="patient_btn"):
                if pname.strip():
                    st.session_state.role = "patient"
                    st.session_state.patient_name  = pname.strip()
                    st.session_state.patient_phone = pphone.strip()
                    st.rerun()
                else: st.error("Please enter your name")

        with tab_g:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:13px;color:#8C7B6B;line-height:1.7;margin-bottom:18px;'>Browse doctors, get suggestions, and explore — you'll need to register to book an appointment.</div>", unsafe_allow_html=True)
            if st.button("Continue as Guest", use_container_width=True, key="guest_btn"):
                st.session_state.role = "guest"; st.rerun()
    st.stop()

# ─── Sign out ─────────────────────────────────────────────────────────────────
_, col_out = st.columns([8, 1])
with col_out:
    if st.button("Sign Out"):
        for k in ["role","history","patient_name","patient_phone","voice_pending"]:
            st.session_state.pop(k, None)
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.role == "admin":
    st.markdown("<div class='admin-wrap'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Administration Panel</div>", unsafe_allow_html=True)

    # Always read fresh from DB — never cache this
    if st.button("🔄 Refresh"):
        st.rerun()

    conn = db_connection()
    df   = pd.read_sql_query("SELECT * FROM appointments ORDER BY slot", conn)
    conn.close()

    today    = datetime.now().strftime("%Y-%m-%d")
    today_df = df[df["slot"].str.startswith(today)] if not df.empty else df

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Total Appointments", len(df))
    with c2: st.metric("Today", len(today_df))
    with c3: st.metric("Doctors", len(DOCTORS))

    # Raw database view — always shown so you can verify data
    st.markdown("<div class='section-title'>All Appointments (Raw)</div>", unsafe_allow_html=True)
    if df.empty:
        st.info("No appointments in database. DB path: " + DB_PATH)
    else:
        st.dataframe(df, use_container_width=True)

    st.markdown("<div class='section-title'>By Doctor</div>", unsafe_allow_html=True)
    if not df.empty:
        search   = st.text_input("Filter by patient name", placeholder="Search…")
        filtered = df[df["patient_name"].str.contains(search.lower(), na=False)] if search else df
        for d in DOCTORS:
            doc_df = filtered[filtered["doc_id"] == d]
            with st.expander(f"{DOCTORS[d]['en']} · {DOCTORS[d]['specialty']} ({len(doc_df)})"):
                if doc_df.empty: st.write("No appointments.")
                else: st.dataframe(doc_df[["patient_name","phone","slot","status"]], use_container_width=True)

    st.markdown("<div class='section-title'>Doctor Schedules</div>", unsafe_allow_html=True)
    col_a, col_b = st.columns([1, 2])
    with col_a:
        doc   = st.selectbox("Doctor", list(DOCTORS.keys()), format_func=lambda x: f"{DOCTORS[x]['en']} · {DOCTORS[x]['specialty']}")
        s     = get_schedule(doc)
        start = st.number_input("Start Hour", 0, 23, s["start"])
        end   = st.number_input("End Hour",   0, 23, s["end"])
        if st.button("Save Schedule"):
            if start >= end: st.error("Start must be before end.")
            else:
                conn = db_connection(); cur = conn.cursor()
                cur.execute("REPLACE INTO doctor_schedule VALUES (?,?,?)", (doc, start, end))
                conn.commit(); conn.close(); st.success("Saved.")

    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            st.download_button("⬇ Download Database", f, file_name="clinic.db")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT (patient / guest)
# ═══════════════════════════════════════════════════════════════════════════════
patient_name  = st.session_state.patient_name
patient_phone = st.session_state.patient_phone

doctor_list = "\n".join(f"ID {k}: {v['en']} — {v['specialty']}" for k, v in DOCTORS.items())

SYSTEM_PROMPT = f"""You are the warm, knowledgeable assistant for {CLINIC_NAME}, a premium clinic in Bahrain.
Help patients book, cancel, reschedule appointments, suggest the right doctor based on symptoms, and answer clinic questions.

Clinic: {CLINIC_NAME}
Address: {CLINIC_ADDR}
Google Maps: {MAPS_LINK}
Hours: Sunday–Thursday 9 AM–6 PM. Closed Fri & Sat.

Doctors:
{doctor_list}

Current patient:
- Name: {patient_name}
- Phone: {patient_phone}
- Role: {st.session_state.role}

RULES:
1. Be warm and conversational like a concierge, not robotic.
2. If someone describes symptoms, suggest the right doctor and explain why (briefly).
3. To book: confirm doctor + date + time first, then output the BOOKING tag.
4. If no phone on file for a patient, ask for it before placing the BOOKING tag.
5. For location requests, include the address in your message and link to Google Maps.
6. Never suggest times in the past or outside working hours (Sun-Thu 9-18).
7. For guests: give suggestions freely but explain they need to log in as Patient to book.
8. Today is {datetime.now().strftime('%A, %d %B %Y')}.

ACTION TAGS (one per action, on its own line):
[BOOKING: patient_name, phone, doc_id, YYYY-MM-DD HH:MM]
[CANCEL: patient_name, doc_id]
[RESCHEDULE: patient_name, doc_id, YYYY-MM-DD HH:MM]
"""

# Welcome
if not st.session_state.history:
    hour = datetime.now().hour
    tod  = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    st.markdown(f"""
    <div class="chat-welcome">
        <h2>Good {tod}, {patient_name} 👋</h2>
        <p>I'm your AlShifa Clinic assistant.<br>
        I can help you book appointments, find the right doctor, or answer any questions.</p>
    </div>
    <div style="text-align:center;margin-bottom:32px;">
        <span style="display:inline-block;background:white;border:1px solid #E8E0D5;border-radius:100px;padding:7px 16px;font-size:13px;color:#1A1410;margin:4px;">📅 Book an appointment</span>
        <span style="display:inline-block;background:white;border:1px solid #E8E0D5;border-radius:100px;padding:7px 16px;font-size:13px;color:#1A1410;margin:4px;">🩺 Which doctor should I see?</span>
        <span style="display:inline-block;background:white;border:1px solid #E8E0D5;border-radius:100px;padding:7px 16px;font-size:13px;color:#1A1410;margin:4px;">📍 Clinic location</span>
        <span style="display:inline-block;background:white;border:1px solid #E8E0D5;border-radius:100px;padding:7px 16px;font-size:13px;color:#1A1410;margin:4px;">🕐 Working hours</span>
    </div>
    """, unsafe_allow_html=True)

# Render history
for msg in st.session_state.history:
    st.chat_message(msg["role"]).markdown(msg["content"])

# Voice
audio = st.audio_input("🎙 Speak")
if audio:
    text = transcribe_audio(audio)
    st.session_state.voice_pending = text
    st.rerun()

# Input
user_msg = st.chat_input(f"Message {CLINIC_NAME} assistant…")
if not user_msg and st.session_state.get("voice_pending"):
    user_msg = st.session_state.pop("voice_pending")

if user_msg:
    st.session_state.history.append({"role": "user", "content": user_msg})
    st.chat_message("user").markdown(user_msg)

    if ai_client:
        try:
            res   = ai_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.history,
            )
            reply = res.choices[0].message.content
        except Exception as e:
            reply = f"⚠️ AI error: {e}"
    else:
        reply = "⚠️ AI not configured. Add MISTRAL_API_KEY to Streamlit secrets."

    # Clean reply for display (remove action tags)
    visible = re.sub(r'\[(BOOKING|CANCEL|RESCHEDULE)[^\]]*\]', '', reply).strip()
    st.chat_message("assistant").markdown(visible)
    st.session_state.history.append({"role": "assistant", "content": reply})

    # ── Actions ───────────────────────────────────────────────────────────────
    b = re.search(r"\[BOOKING:(.*?)\]", reply)
    if b:
        parts = [x.strip() for x in b.group(1).split(",")]
        if len(parts) == 4:
            n, p, d, s = parts
            if d not in DOCTORS:
                d_found = next((k for k, v in DOCTORS.items()
                                if v["en"].lower() in d.lower() or d.lower() in v["en"].lower()), None)
                if d_found: d = d_found
                else:
                    st.error(f"⚠️ Could not identify doctor '{d}'. Please try again.")
                    d = None
            if (not p or p in ["phone", "N/A", ""]) and patient_phone: p = patient_phone
            if (not n or n in ["patient_name", "N/A", ""]) and patient_name != "Guest": n = patient_name

            if d:
                ok, err = book_appointment(n, p, d, s)
                if ok:
                    doc_name = DOCTORS[d]["en"]
                    specialty = DOCTORS[d]["specialty"]
                    st.success(
                        f"✅ **Appointment Confirmed**\n\n"
                        f"- **Patient:** {n.title()}\n"
                        f"- **Doctor:** {doc_name} · {specialty}\n"
                        f"- **Date & Time:** {s}\n"
                    )
                    
                    # PDF Receipt
                    pdf_bytes = generate_receipt_pdf(n, f"{doc_name} ({specialty})", s)
                    st.download_button(
                        label="📄 Download Appointment Receipt (PDF)",
                        data=pdf_bytes,
                        file_name=f"AlShifa_Receipt_{n.replace(' ', '_')}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error(f"Booking failed: {err}")

    c = re.search(r"\[CANCEL:(.*?)\]", reply)
    if c:
        parts = [x.strip() for x in c.group(1).split(",")]
        if len(parts) == 2:
            n, d = parts
            if n in ["patient_name", "N/A", ""] and patient_name != "Guest": n = patient_name
            cancel_appointment(n, d)
            st.info(f"Appointment for **{n.title()}** has been cancelled.")

    r = re.search(r"\[RESCHEDULE:(.*?)\]", reply)
    if r:
        parts = [x.strip() for x in r.group(1).split(",")]
        if len(parts) == 3:
            n, d, s = parts
            if n in ["patient_name", "N/A", ""] and patient_name != "Guest": n = patient_name
            ok, err = reschedule_appointment(n, d, s)
            if ok:
                st.success(f"✅ Rescheduled **{n.title()}** to {s}.")
                # PDF Receipt for reschedule
                doc_name = DOCTORS.get(d, {}).get("en", d)
                specialty = DOCTORS.get(d, {}).get("specialty", "")
                pdf_bytes = generate_receipt_pdf(n, f"{doc_name} ({specialty})", s)
                st.download_button(
                    label="📄 Download Updated Receipt (PDF)",
                    data=pdf_bytes,
                    file_name=f"AlShifa_Rescheduled_{n.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
            else:
                st.error(f"Reschedule failed: {err}")
