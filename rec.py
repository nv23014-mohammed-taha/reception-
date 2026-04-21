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

st.set_page_config(page_title="Clinic Reception", layout="wide")

# --- basic styling ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=DM+Sans:wght@300;400;500&display=swap');

:root {
    --bg: #F7F3EE;
    --text: #1A1410;
    --accent: #C9A84C;
    --secondary: #8C7B6B;
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
}

.brand span { color: #fff; font-weight: 300; }

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
}

.stTextInput input, .stSelectbox select, .stNumberInput input {
    border: 1px solid var(--border-color) !important;
    background: white !important;
    border-radius: 2px !important;
}

.heading {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.5rem;
    font-weight: 300;
    margin: 2.5rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
}
</style>
""", unsafe_allow_html=True)


# --- clinic info and doctors ---

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


# --- ai setup ---

@st.cache_resource
def connect_ai():
    api_key = st.secrets.get("MISTRAL_API_KEY")
    if api_key:
        return Mistral(api_key=api_key)
    return None


# --- database functions ---

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = get_db()
    
    # create appointments table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            phone TEXT,
            doc_id TEXT,
            slot TEXT,
            status TEXT DEFAULT 'confirmed',
            UNIQUE(doc_id, slot)
        )
    """)

    # add status column if it's missing (for older databases)
    columns = conn.execute("PRAGMA table_info(appointments)").fetchall()
    column_names = [col[1] for col in columns]
    if "status" not in column_names:
        conn.execute("ALTER TABLE appointments ADD COLUMN status TEXT DEFAULT 'confirmed'")

    # create schedules table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            doc_id TEXT PRIMARY KEY,
            start_h INTEGER,
            end_h INTEGER
        )
    """)

    conn.commit()
    conn.close()


def get_schedule(doc_id):
    conn = get_db()
    row = conn.execute("SELECT start_h, end_h FROM schedules WHERE doc_id=?", (doc_id,)).fetchone()
    
    if row:
        conn.close()
        return {"start": row[0], "end": row[1]}
    
    # no schedule found, use default 9-6
    conn.execute("INSERT OR IGNORE INTO schedules VALUES (?, ?, ?)", (doc_id, 9, 18))
    conn.commit()
    conn.close()
    return {"start": 9, "end": 18}


def check_booking_valid(doc_id, slot):
    try:
        slot_time = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    except:
        return False, "Invalid date/time format"

    if slot_time <= datetime.now():
        return False, "Time must be in the future"

    schedule = get_schedule(doc_id)
    is_weekday = slot_time.weekday() < 5  # 0=Mon, 4=Fri
    is_in_hours = schedule["start"] <= slot_time.hour < schedule["end"]

    if not is_weekday or not is_in_hours:
        return False, "Doctor is not available at this time"

    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot)
    ).fetchone()
    conn.close()

    if existing:
        return False, "This slot is already booked"

    return True, None


def save_booking(name, phone, doc_id, slot):
    valid, error = check_booking_valid(doc_id, slot)
    if not valid:
        return False, error

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?, ?, ?, ?)",
            (name.lower().strip(), phone, doc_id, slot)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def cancel_booking(name, doc_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM appointments WHERE patient_name=? AND doc_id=?",
        (name.lower().strip(), doc_id)
    )
    conn.commit()
    conn.close()


def reschedule_booking(name, doc_id, new_slot):
    valid, error = check_booking_valid(doc_id, new_slot)
    if not valid:
        return False, error

    conn = get_db()
    cursor = conn.execute(
        "UPDATE appointments SET slot=? WHERE patient_name=? AND doc_id=?",
        (new_slot, name.lower().strip(), doc_id)
    )
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return False, "Appointment not found"

    return True, None


# --- pdf receipt ---

def make_receipt(patient_name, doctor_name, slot):
    pdf = FPDF()
    pdf.add_page()

    # clinic name header
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(26, 20, 16)
    pdf.cell(0, 20, CLINIC_NAME.upper(), ln=True, align="C")

    # subtitle
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(140, 123, 107)
    pdf.cell(0, 5, "EXCELLENCE IN HEALTHCARE - BAHRAIN", ln=True, align="C")
    pdf.ln(15)

    # confirmation heading
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(201, 168, 76)
    pdf.cell(0, 10, "APPOINTMENT CONFIRMATION", ln=True, align="C")
    pdf.ln(10)

    # details rows
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(26, 20, 16)

    rows = [
        ("Patient", patient_name.title()),
        ("Practitioner", doctor_name),
        ("Date & Time", slot),
        ("Location", CLINIC_ADDR),
    ]

    for label, value in rows:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(40, 10, f"{label}:", 0)
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 10, value, 0, 1)

    # footer note
    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(140, 123, 107)
    pdf.multi_cell(0, 6, "Kindly arrive 10 minutes prior to your session. For any changes, please use our digital assistant.", align="C")

    return pdf.output(dest="S").encode("latin-1")


# --- app startup ---

init_db()
ai = connect_ai()

# set up session state on first load
if "session" not in st.session_state:
    st.session_state.session = {
        "user": None,
        "history": [],
        "name": "Guest",
        "phone": ""
    }


def sign_out():
    st.session_state.session = {
        "user": None,
        "history": [],
        "name": "Guest",
        "phone": ""
    }
    st.rerun()


# --- navbar ---

active_user = st.session_state.session["user"]
active_label = f"ACTIVE: {active_user.upper()}" if active_user else ""

st.markdown(f"""
<div class="navbar">
    <div class="brand">AlShifa <span>Clinic</span></div>
    <div style="font-size:0.7rem; color:var(--secondary);">{active_label}</div>
</div>
""", unsafe_allow_html=True)


# --- login screen ---

if not st.session_state.session["user"]:
    st.markdown("<div style='height:4rem'></div>", unsafe_allow_html=True)

    _, center_col, _ = st.columns([1, 1.2, 1])
    with center_col:
        st.markdown("""
            <div class="hero">
                <h1>Welcome</h1>
                <p style="color:var(--secondary)">Please identify yourself to proceed</p>
            </div>
        """, unsafe_allow_html=True)

        tab_patient, tab_staff, tab_guest = st.tabs(["Patient", "Staff", "Guest"])

        with tab_patient:
            name_input = st.text_input("Full Name", placeholder="e.g. Sara Ahmed")
            phone_input = st.text_input("Phone Number", placeholder="+973 ...")
            if st.button("Enter as Patient", use_container_width=True):
                if name_input.strip():
                    st.session_state.session["user"] = "patient"
                    st.session_state.session["name"] = name_input.strip()
                    st.session_state.session["phone"] = phone_input.strip()
                    st.rerun()
                else:
                    st.error("Name is required")

        with tab_staff:
            password_input = st.text_input("Access Key", type="password")
            if st.button("Staff Login", use_container_width=True):
                entered_hash = hashlib.sha256(password_input.encode()).hexdigest()
                correct_hash = hashlib.sha256(b"admin123").hexdigest()
                if entered_hash == correct_hash:
                    st.session_state.session["user"] = "admin"
                    st.rerun()
                else:
                    st.error("Invalid key")

        with tab_guest:
            st.markdown("<p style='font-size:0.8rem; color:var(--secondary); margin: 1rem 0;'>Browse our services and doctors. Login required for bookings.</p>", unsafe_allow_html=True)
            if st.button("Continue as Guest", use_container_width=True):
                st.session_state.session["user"] = "guest"
                st.rerun()

    st.stop()


# sign out button (shown on all pages after login)
if st.button("Sign Out", key="logout"):
    sign_out()


# --- admin dashboard ---

if st.session_state.session["user"] == "admin":
    st.markdown('<div style="padding: 2rem 3rem">', unsafe_allow_html=True)
    st.markdown('<div class="heading">Clinic Dashboard</div>', unsafe_allow_html=True)

    conn = get_db()
    all_appointments = pd.read_sql_query("SELECT * FROM appointments ORDER BY slot", conn)
    conn.close()

    today_str = datetime.now().strftime("%Y-%m-%d")
    todays_count = len(all_appointments[all_appointments["slot"].str.startswith(today_str)])

    col1, col2, col3 = st.columns(3)
    col1.metric("Total", len(all_appointments))
    col2.metric("Today", todays_count)
    col3.metric("Staff", len(DOCTORS))

    st.markdown('<div class="heading">Appointment Records</div>', unsafe_allow_html=True)

    if all_appointments.empty:
        st.info("No records found")
    else:
        # add doctor name and specialty columns for display
        display_df = all_appointments.copy()
        display_df["Doctor"] = display_df["doc_id"].apply(lambda x: DOCTORS.get(x, {}).get("name", "Unknown"))
        display_df["Specialty"] = display_df["doc_id"].apply(lambda x: DOCTORS.get(x, {}).get("field", "Unknown"))
        st.dataframe(display_df[["patient_name", "phone", "Doctor", "Specialty", "slot", "status"]], use_container_width=True)

        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as f:
                st.download_button("Download Records Database", f, "clinic_records.db", "application/octet-stream")

    st.markdown('<div class="heading">Staff Management</div>', unsafe_allow_html=True)

    left_col, _ = st.columns([1, 2])
    with left_col:
        doctor_id = st.selectbox(
            "Select Practitioner",
            list(DOCTORS.keys()),
            format_func=lambda x: f"{DOCTORS[x]['name']} ({DOCTORS[x]['field']})"
        )
        current_schedule = get_schedule(doctor_id)
        start_hour = st.number_input("Start Hour", 0, 23, current_schedule["start"])
        end_hour = st.number_input("End Hour", 0, 23, current_schedule["end"])

        if st.button("Update Hours"):
            if start_hour < end_hour:
                conn = get_db()
                conn.execute("REPLACE INTO schedules VALUES (?, ?, ?)", (doctor_id, start_hour, end_hour))
                conn.commit()
                conn.close()
                st.success("Updated")
            else:
                st.error("Start hour must be before end hour")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# --- patient/guest chat ---

# build doctor list string for the AI prompt
doctor_list = ""
for doc_id, info in DOCTORS.items():
    doctor_list += f"ID {doc_id}: {info['name']} ({info['field']})\n"

SYSTEM_PROMPT = f"""You are a helpful receptionist at {CLINIC_NAME} in Bahrain.
Address: {CLINIC_ADDR}
Maps: {MAPS_URL}
Hours: Sun-Thu, 9am-6pm.

Our Doctors:
{doctor_list}

User: {st.session_state.session['name']}
Phone: {st.session_state.session['phone']}
Role: {st.session_state.session['user']}

Instructions:
- Be professional and warm.
- To book, confirm doctor and time, then use: [BOOKING: name, phone, doc_id, YYYY-MM-DD HH:MM]
- To cancel: [CANCEL: name, doc_id]
- To reschedule: [RESCHEDULE: name, doc_id, YYYY-MM-DD HH:MM]
- If a guest wants to book, politely ask them to login first.
- Current date: {datetime.now().strftime('%A, %B %d, %Y')}
"""

# show welcome message on first load
if not st.session_state.session["history"]:
    st.markdown(f"""
        <div class="hero">
            <h1>Hello, {st.session_state.session['name']}</h1>
            <p style="color:var(--secondary)">How can we assist you today?</p>
        </div>
    """, unsafe_allow_html=True)

# show chat history
for message in st.session_state.session["history"]:
    st.chat_message(message["role"]).write(message["content"])


# --- voice input ---

voice_audio = st.audio_input("Voice Input")

if voice_audio:
    # save audio to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_file.write(voice_audio.read())
        temp_path = temp_file.name

    try:
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)
            transcribed = recognizer.recognize_google(audio_data)

            # only store if it's a new recording (avoid duplicates on rerun)
            last_voice = st.session_state.get("last_voice", "")
            if transcribed and transcribed != last_voice:
                st.session_state.voice_data = transcribed
                st.session_state.last_voice = transcribed
    except:
        pass
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


# --- handle user message ---

typed_input = st.chat_input("Type your message...")
voice_input = st.session_state.pop("voice_data", None)
user_input = typed_input or voice_input

if user_input:
    # add user message to history and show it
    st.session_state.session["history"].append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)

    # get AI response
    if ai:
        all_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.session["history"]
        response = ai.chat.complete(model="mistral-large-latest", messages=all_messages)
        raw_reply = response.choices[0].message.content
    else:
        raw_reply = "AI assistant is currently offline."

    # remove command tags before showing to user
    clean_reply = re.sub(r'\[.*?\]', '', raw_reply).strip()
    st.chat_message("assistant").write(clean_reply)

    # save the raw reply (with tags) to history so AI keeps context
    st.session_state.session["history"].append({"role": "assistant", "content": raw_reply})

    # --- handle booking command ---
    if "[BOOKING:" in raw_reply:
        match = re.search(r"\[BOOKING:(.*?)\]", raw_reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) == 4:
                pt_name, pt_phone, doc_id, slot = parts

                # if AI gave a doctor name instead of ID, find the ID
                if doc_id not in DOCTORS:
                    for k, v in DOCTORS.items():
                        if v["name"].lower() in doc_id.lower():
                            doc_id = k
                            break

                success, error = save_booking(pt_name, pt_phone, doc_id, slot)
                if success:
                    doctor_info = DOCTORS[doc_id]
                    st.success(f"Confirmed: {doctor_info['name']} at {slot}")
                    receipt = make_receipt(pt_name, f"{doctor_info['name']} ({doctor_info['field']})", slot)
                    st.download_button("Download Receipt", receipt, f"Receipt_{pt_name}.pdf", "application/pdf")
                else:
                    st.error(error)

    # --- handle cancel command ---
    if "[CANCEL:" in raw_reply:
        match = re.search(r"\[CANCEL:(.*?)\]", raw_reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) == 2:
                cancel_booking(parts[0], parts[1])
                st.info("Appointment removed.")

    # --- handle reschedule command ---
    if "[RESCHEDULE:" in raw_reply:
        match = re.search(r"\[RESCHEDULE:(.*?)\]", raw_reply)
        if match:
            parts = [p.strip() for p in match.group(1).split(",")]
            if len(parts) == 3:
                success, error = reschedule_booking(parts[0], parts[1], parts[2])
                if success:
                    doctor_info = DOCTORS[parts[1]]
                    st.success("Rescheduled successfully.")
                    receipt = make_receipt(parts[0], doctor_info["name"], parts[2])
                    st.download_button("Download New Receipt", receipt, f"Updated_Receipt_{parts[0]}.pdf", "application/pdf")
                else:
                    st.error(error)
