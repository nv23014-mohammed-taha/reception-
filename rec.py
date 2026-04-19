from mistralai import Mistral
from twilio.rest import Client
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os, re, tempfile
import speech_recognition as sr

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Clinic System", layout="wide")

language = st.sidebar.selectbox("Language / اللغة", ["English", "العربية"])

def t(en, ar):
    return ar if language == "العربية" else en

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "hospital_management.db")

# ─── AI client (cached) ───────────────────────────────────────────────────────
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
    conn = db_connection()
    cur  = conn.cursor()
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctor_schedule (
            doc_id TEXT PRIMARY KEY,
            start_hour INTEGER,
            end_hour INTEGER
        )
    """)
    conn.commit()
    conn.close()

setup_database()

# ─── Data ─────────────────────────────────────────────────────────────────────
DOCTORS = {
    "1":  {"en": "Dr. Faisal Al-Mahmood (Cardiology)",  "ar": "د. فيصل المحمود"},
    "2":  {"en": "Dr. Mariam Al-Sayed (Pediatrics)",    "ar": "د. مريم السيد"},
    "3":  {"en": "Dr. Yousef Al-Haddad (Orthopedics)",  "ar": "د. يوسف الحداد"},
    "4":  {"en": "Dr. Noura Al-Khalifa (Dermatology)",  "ar": "د. نورة الخليفة"},
    "5":  {"en": "Dr. Khalid Al-Fares",                 "ar": "د. خالد الفارس"},
    "6":  {"en": "Dr. Sara Al-Ansari",                  "ar": "د. سارة الأنصاري"},
    "7":  {"en": "Dr. Jasim Al-Ghanem",                 "ar": "د. جاسم الغانم"},
    "8":  {"en": "Dr. Layla Al-Mulla",                  "ar": "د. ليلى الملا"},
    "9":  {"en": "Dr. Hassan Ibrahim",                  "ar": "د. حسن إبراهيم"},
    "10": {"en": "Dr. Ahmed Al-Aali",                   "ar": "د. أحمد العالي"},
}

DEFAULT_SCHEDULE = {"start": 9, "end": 18}

# ─── Schedule helpers ─────────────────────────────────────────────────────────
def get_schedule(doc_id):
    conn = db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT start_hour, end_hour FROM doctor_schedule WHERE doc_id=?", (doc_id,))
    row  = cur.fetchone()
    if row:
        conn.close()
        return {"start": row[0], "end": row[1]}
    cur.execute("INSERT OR IGNORE INTO doctor_schedule VALUES (?,?,?)",
                (doc_id, DEFAULT_SCHEDULE["start"], DEFAULT_SCHEDULE["end"]))
    conn.commit()
    conn.close()
    return DEFAULT_SCHEDULE

def is_future(slot):
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M") > datetime.now()
    except:
        return False

def doctor_available(doc_id, slot):
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
        s  = get_schedule(doc_id)
        return dt.weekday() < 5 and s["start"] <= dt.hour < s["end"]
    except:
        return False

# ─── Appointment actions ──────────────────────────────────────────────────────
def book_appointment(name, phone, doc_id, slot):
    conn = db_connection()
    cur  = conn.cursor()
    try:
        name = name.lower().strip()
        cur.execute("BEGIN IMMEDIATE")
        if not is_future(slot):
            return False, "Pick future time"
        if not doctor_available(doc_id, slot):
            return False, "Doctor unavailable"
        cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, slot))
        if cur.fetchone():
            return False, "Slot taken"
        cur.execute("INSERT INTO appointments VALUES(NULL,?,?,?,?)",
                    (name, phone, doc_id, slot))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def cancel_appointment(name, doc_id):
    conn = db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE patient_name=? AND doc_id=?",
                (name.lower().strip(), doc_id))
    conn.commit()
    conn.close()
    return True

def reschedule_appointment(name, doc_id, new_slot):
    conn = db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT 1 FROM appointments WHERE patient_name=? AND doc_id=?",
                (name.lower().strip(), doc_id))
    if not cur.fetchone():
        conn.close()
        return False, "Not found"
    if not doctor_available(doc_id, new_slot):
        conn.close()
        return False, "Doctor unavailable"
    cur.execute("SELECT 1 FROM appointments WHERE doc_id=? AND slot=?", (doc_id, new_slot))
    if cur.fetchone():
        conn.close()
        return False, "Slot taken"
    cur.execute("UPDATE appointments SET slot=? WHERE patient_name=? AND doc_id=?",
                (new_slot, name.lower().strip(), doc_id))
    conn.commit()
    conn.close()
    return True, None

# ─── WhatsApp ─────────────────────────────────────────────────────────────────
def send_whatsapp(phone, name, doctor, slot):
    try:
        client = Client(
            st.secrets["TWILIO_ACCOUNT_SID"],
            st.secrets["TWILIO_AUTH_TOKEN"]
        )
        client.messages.create(
            body=f"🏥 Appointment Confirmed\nName: {name}\nDoctor: {doctor}\nSlot: {slot}",
            from_=st.secrets["TWILIO_WHATSAPP_NUMBER"],
            to=f"whatsapp:{phone}"
        )
    except Exception as e:
        st.warning(f"WhatsApp notification failed: {e}")

# ─── Audio ────────────────────────────────────────────────────────────────────
def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        path = tmp.name
    try:
        with sr.AudioFile(path) as src:
            audio = r.record(src)
        return r.recognize_google(audio)
    except:
        return "Could not understand audio"
    finally:
        os.unlink(path)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title(t("Navigation", "التنقل"))
if os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as f:
        st.sidebar.download_button(
            t("Download Database", "تحميل قاعدة البيانات"),
            f, file_name="clinic.db"
        )

# ─── Tabs ─────────────────────────────────────────────────────────────────────
chat_tab, admin_tab = st.tabs([t("Chat", "المحادثة"), t("Administration", "الإدارة")])

# ─── Chat tab ─────────────────────────────────────────────────────────────────
with chat_tab:
    st.title(t("Clinic Assistant", "مساعد العيادة"))

    if "history" not in st.session_state:
        st.session_state.history = []

    # Render existing history
    for msg in st.session_state.history:
        st.chat_message(msg["role"]).markdown(msg["content"])

    audio = st.audio_input(t("Speak", "تحدث"))
    if audio:
        st.session_state["voice_pending"] = transcribe_audio(audio.getvalue())

    user_msg = st.chat_input(t("Type message", "اكتب رسالة"))
    if not user_msg and st.session_state.get("voice_pending"):
        user_msg = st.session_state.pop("voice_pending")

    if user_msg:
        st.session_state.history.append({"role": "user", "content": user_msg})
        st.chat_message("user").markdown(user_msg)

        doctor_list = "\n".join(f"{k}: {v['en']}" for k, v in DOCTORS.items())
        system_prompt = f"""You are a clinic appointment assistant.
Doctors work Sunday–Thursday, 9 AM–6 PM only. Never suggest past times.

Available doctors:
{doctor_list}

To book output:       [BOOKING: patient_name, phone, doc_id, YYYY-MM-DD HH:MM]
To cancel output:     [CANCEL: patient_name, doc_id]
To reschedule output: [RESCHEDULE: patient_name, doc_id, YYYY-MM-DD HH:MM]
"""

        if ai_client:
            try:
                res   = ai_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "system", "content": system_prompt}]
                             + st.session_state.history,
                )
                reply = res.choices[0].message.content
            except Exception as e:
                reply = f"AI error: {e}"
        else:
            reply = t(
                "⚠️ AI not configured. Add MISTRAL_API_KEY to Streamlit secrets.",
                "⚠️ الذكاء الاصطناعي غير مفعّل. أضف MISTRAL_API_KEY إلى الأسرار."
            )

        st.chat_message("assistant").markdown(reply)
        st.session_state.history.append({"role": "assistant", "content": reply})

        # Action parsing
        b = re.search(r"\[BOOKING:(.*?)\]", reply)
        if b:
            parts = [x.strip() for x in b.group(1).split(",")]
            if len(parts) == 4:
                n, p, d, s = parts
                ok, err = book_appointment(n, p, d, s)
                if ok:
                    send_whatsapp(p, n, DOCTORS.get(d, {}).get("en", d), s)
                    st.success(t(f"Booked for {n}!", f"تم الحجز لـ {n}!"))
                else:
                    st.error(t(f"Booking failed: {err}", f"فشل الحجز: {err}"))

        c = re.search(r"\[CANCEL:(.*?)\]", reply)
        if c:
            parts = [x.strip() for x in c.group(1).split(",")]
            if len(parts) == 2:
                n, d = parts
                cancel_appointment(n, d)
                st.info(t(f"Cancelled for {n}.", f"تم الإلغاء لـ {n}."))

        r = re.search(r"\[RESCHEDULE:(.*?)\]", reply)
        if r:
            parts = [x.strip() for x in r.group(1).split(",")]
            if len(parts) == 3:
                n, d, s = parts
                ok, err = reschedule_appointment(n, d, s)
                if ok:
                    st.success(t(f"Rescheduled for {n}.", f"تمت إعادة الجدولة لـ {n}."))
                else:
                    st.error(t(f"Reschedule failed: {err}", f"فشلت إعادة الجدولة: {err}"))

# ─── Admin tab ────────────────────────────────────────────────────────────────
with admin_tab:
    st.subheader(t("Administration Panel", "لوحة الإدارة"))

    conn = db_connection()
    df   = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    st.metric(t("Total Appointments", "إجمالي المواعيد"), len(df))

    st.markdown("### " + t("Doctor Schedule Editor", "تعديل جدول الأطباء"))

    doc = st.selectbox(
        t("Select Doctor", "اختر الطبيب"),
        list(DOCTORS.keys()),
        format_func=lambda x: DOCTORS[x]["en"]
    )

    s     = get_schedule(doc)
    start = st.number_input(t("Start Hour", "بداية الدوام"), 0, 23, s["start"])
    end   = st.number_input(t("End Hour",   "نهاية الدوام"), 0, 23, s["end"])

    if st.button(t("Save Schedule", "حفظ الجدول")):
        if start >= end:
            st.error(t("Start must be before end.", "يجب أن تكون البداية قبل النهاية."))
        else:
            conn = db_connection()
            cur  = conn.cursor()
            cur.execute("REPLACE INTO doctor_schedule VALUES (?,?,?)", (doc, start, end))
            conn.commit()
            conn.close()
            st.success(t("Schedule updated!", "تم تحديث الجدول!"))

    st.markdown("### " + t("All Appointments", "كل المواعيد"))

    if df.empty:
        st.info(t("No appointments yet.", "لا توجد مواعيد بعد."))
    else:
        for d in DOCTORS:
            doc_df = df[df["doc_id"] == d]
            with st.expander(f"{DOCTORS[d]['en']} ({len(doc_df)})"):
                if doc_df.empty:
                    st.write(t("No appointments.", "لا توجد مواعيد."))
                else:
                    st.dataframe(doc_df, use_container_width=True)
