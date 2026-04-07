import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Clinic page", layout="wide")

lang = st.sidebar.selectbox("language / اللغة", ["English", "العربية"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            doc_id TEXT,
            slot TEXT,
            UNIQUE(doc_id, slot)
        )
    ''')

    conn.commit()
    conn.close()

def try_booking(name, doc, slot):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        name = name.replace("Patient:", "").strip()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("SELECT id FROM appointments WHERE doc_id=? AND slot=?", (doc, slot))
        if cursor.fetchone():
            return False, "slot already taken"

        cursor.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)",
                       (name, doc, slot))

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()

def cancel_booking(name, doc):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        name = name.replace("Patient:", "").strip()
        cursor.execute("DELETE FROM appointments WHERE patient_name LIKE ? AND doc_id=?",
                       (f"%{name}%", doc))

        conn.commit()
        return cursor.rowcount > 0

    except:
        return False

    finally:
        conn.close()

init_db()

DOCTOR_LIST = {
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

text = {
    "title": "clinic assistant" if lang == "English" else "مساعد العيادة",
    "input": "type here" if lang == "English" else "اكتب هنا",
    "dashboard": "appointments" if lang == "English" else "المواعيد",
    "clear": "clear all" if lang == "English" else "حذف الكل",
    "empty": "no bookings yet" if lang == "English" else "لا توجد مواعيد",
}

st.sidebar.title("tools" if lang == "English" else "أدوات")

if os.path.exists(DB_NAME):
    with open(DB_NAME, "rb") as f:
        st.sidebar.download_button(
            label="download db" if lang == "English" else "تحميل قاعدة البيانات",
            data=f,
            file_name="hospital_management.db"
        )

chat_tab, admin_tab = st.tabs(
    ["chat", "dashboard"] if lang == "English" else ["الدردشة", "لوحة التحكم"]
)

with chat_tab:
    st.title(text["title"])

    current_date = datetime.now().strftime("%A, %B %d, %Y")

    conn = get_db_connection()
    booked_df = pd.read_sql_query("SELECT doc_id, slot FROM appointments", conn)
    conn.close()

    schedule = booked_df.to_string(index=False) if not booked_df.empty else "none"

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input(text["input"]):
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        system_instruction = f"""
        you are a clinic receptionist
        respond in {"Arabic" if lang == "العربية" else "English"}

        today: {current_date}
        doctors: {DOCTOR_LIST}
        busy slots: {schedule}

        use:
        [BOOKING: Name, DocID, YYYY-MM-DD HH:MM]
        [CANCEL: Name, DocID]
        """

        with st.chat_message("assistant"):
            try:
                response = mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
                )

                ai_response = response.choices[0].message.content
                st.markdown(ai_response)

                if "[CANCEL:" in ai_response:
                    data = ai_response.split("[CANCEL:")[1].split("]")[0]
                    parts = [p.strip() for p in data.split(",")]

                    if len(parts) >= 2:
                        if cancel_booking(parts[0], parts[1]):
                            st.error("removed" if lang == "English" else "تم الحذف")
                        else:
                            st.warning("not found" if lang == "English" else "غير موجود")

                if "[BOOKING:" in ai_response:
                    data = ai_response.split("[BOOKING:")[1].split("]")[0]
                    parts = [p.strip() for p in data.split(",")]

                    if len(parts) >= 3:
                        success, err = try_booking(parts[0], parts[1], parts[2])

                        if success:
                            st.success("booking added" if lang == "English" else "تم الحجز")
                            st.balloons()
                        else:
                            st.warning(f"failed: {err}")

                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})

            except Exception as err:
                st.error(f"error: {err}")

with admin_tab:
    st.subheader(text["dashboard"])

    conn = get_db_connection()
    data = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not data.empty:
        st.metric("total bookings", len(data))

        for id, info in DOCTOR_LIST.items():
            df = data[data['doc_id'] == id]
            name = info["en"] if lang == "English" else info["ar"]

            with st.expander(f"{name} ({len(df)})"):
                if not df.empty:
                    st.table(df[['patient_name', 'slot']])

        if st.button(text["clear"]):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()

    else:
        st.info(text["empty"])
