import streamlit as st
from mistralai.client import Mistral
from twilio.rest import Client
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import re
import base64
# ================= PATCH: FIX TIME + RULES =================

CURRENT_YEAR = 2026


def normalize_slot(slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        if dt.year != CURRENT_YEAR:
            dt = dt.replace(year=CURRENT_YEAR)
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return slot


# ================= PATCH: DOCTOR SCHEDULE =================
# Add AFTER your DOCTORS dictionary (replace old schedule)

DOCTOR_SCHEDULE = {
    str(i): {
        "start": 8,
        "end": 21,
        "days": [6, 0, 1, 2, 3]  # Sunday–Thursday
    }
    for i in range(1, 11)
}


# ================= PATCH: STRICT BOOKING RULE =================
# INSIDE book_appointment() REPLACE validation part with this:

def booking_validation_patch(cur, doc_id, slot):

    # normalize slot year fix
    slot = normalize_slot(slot)

    # future check
    if not is_future(slot):
        return False, "Pick a future time"

    # doctor schedule check
    if not doctor_available(doc_id, slot):
        return False, "Doctor not available at this time"

    # STRONG OVERLAP PROTECTION
    cur.execute(
        "SELECT 1 FROM appointments WHERE doc_id=? AND slot=?",
        (doc_id, slot)
    )

    if cur.fetchone():
        return False, "This doctor is already booked at this time"

    return True, slot


# ================= PATCH: SAFE SLOT FIX =================
def safe_next_slots(slot):
    try:
        slot = normalize_slot(slot)
        base = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        return [
            (base + timedelta(minutes=30 * i)).strftime("%Y-%m-%d %H:%M")
            for i in range(1, 4)
        ]
    except:
        return []


# ================= PATCH: UI AESTHETIC (OPTIONAL) =================
st.markdown("""
<style>
.main {
    background-color: #0f1115;
}
h1 {
    text-align: center;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.stTabs [data-baseweb="tab"] {
    font-size: 15px;
}
div[data-testid="stExpander"] {
    border-radius: 14px;
    border: 1px solid #2a2a2a;
    background: #161a22;
    padding: 5px;
}
</style>
""", unsafe_allow_html=True)
st.set_page_config(page_title="Clinic System", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hospital_management.db")

language = st.sidebar.selectbox("Language / اللغة", ["English", "Arabic"])


ai_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"]) if "MISTRAL_API_KEY" in st.secrets else None


def db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def setup_database():
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            phone TEXT,
            doc_id TEXT,
            slot TEXT,
            UNIQUE(doc_id, slot)
        )
    """)
    conn.commit()
    conn.close()


setup_database()


DOCTORS = {
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


def t(text_en, text_ar):
    return text_ar if language == "Arabic" else text_en


def db():
    return db_connection()


def is_future(slot):
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
    except:
        return False


def next_slots(slot):
    try:
        base = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        return [(base + timedelta(minutes=30*i)).strftime("%Y-%m-%d %H:%M") for i in range(1,4)]
    except:
        return []


def book_appointment(name, phone, doc_id, slot):
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")

        if not is_future(slot):
            return False, "Invalid time"

        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot))
        if cur.fetchone():
            return False, f"Slot taken. Try {', '.join(next_slots(slot))}"

        cur.execute(
            "INSERT INTO appointments (patient_name, phone, doc_id, slot) VALUES (?,?,?,?)",
            (name.strip().lower(), phone, doc_id, slot)
        )

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()


def cancel_appointment(name, doc_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?", (name.strip().lower(), doc_id))
    conn.commit()
    conn.close()
    return True


def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(st.secrets["TWILIO_ACCOUNT_SID"], st.secrets["TWILIO_AUTH_TOKEN"])
        client.messages.create(
            body=f"Appointment Confirmed\n{name}\n{doctor}\n{slot}",
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
        return True
    except Exception as e:
        st.error(str(e))
        return False


# ---------------- VOICE (CLICK TO RECORD) ----------------
def audio_recorder():
    st.markdown("### Voice Input")

    audio_html = """
    <button onclick="startRecording()">Start Recording</button>
    <button onclick="stopRecording()">Stop</button>

    <script>
    let recorder;
    let chunks = [];

    async function startRecording() {
        let stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(stream);

        recorder.ondataavailable = e => chunks.push(e.data);

        recorder.onstop = async () => {
            let blob = new Blob(chunks, { type: 'audio/wav' });
            let reader = new FileReader();
            reader.readAsDataURL(blob);
            reader.onloadend = () => {
                window.parent.postMessage(reader.result, "*");
            };
        };

        recorder.start();
    }

    function stopRecording() {
        recorder.stop();
    }
    </script>
    """

    st.components.v1.html(audio_html, height=120)


# ---------------- UI ----------------

chat_tab, admin_tab = st.tabs(
    [t("Chat Assistant", "مساعد العيادة"), t("Admin Dashboard", "لوحة التحكم")]
)


with chat_tab:
    st.title(t("Clinic Assistant", "مساعد العيادة"))

    if "history" not in st.session_state:
        st.session_state.history = []

    audio_recorder()

    user_msg = st.chat_input(t("Type here...", "اكتب هنا..."))

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})

        system_prompt = f"""
You are a clinic receptionist.
Reply ONLY in this format if booking:
[BOOKING: Name, Phone, DocID, YYYY-MM-DD HH:MM]

Doctors:
{DOCTORS}
"""

        if ai_client:
            response = ai_client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "system", "content": system_prompt}]
                + st.session_state.history
            )
            reply = response.choices[0].message.content
        else:
            reply = "AI not configured"

        st.chat_message("assistant").markdown(reply)

        match = re.search(r"\[BOOKING:(.*?)\]", reply)

        if match:
            parts = [p.strip() for p in match.group(1).split(",")]

            if len(parts) == 4:
                name, phone, doc, slot = parts
                ok, err = book_appointment(name, phone, doc, slot)

                if ok:
                    send_whatsapp(phone, name, DOCTORS[doc]["en"], slot)
                    st.success("Booked")
                else:
                    st.warning(err)

        st.session_state.history.append({"role": "assistant", "content": reply})


# ---------------- ADMIN (RESTORED ORIGINAL STYLE) ----------------
with admin_tab:
    st.subheader(t("Current Appointments", "المواعيد الحالية"))

    conn = db()
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not df.empty:
        st.metric(t("Total Bookings", "إجمالي الحجوزات"), len(df))

        for doc_id, doc in DOCTORS.items():
            sub = df[df["doc_id"] == doc_id]

            with st.expander(doc["en"] if language == "English" else doc["ar"]):
                if not sub.empty:
                    st.table(sub[["patient_name", "phone", "slot"]])
                else:
                    st.write(t("No appointments", "لا توجد مواعيد"))
    else:
        st.info(t("No bookings found", "لا توجد حجوزات"))
