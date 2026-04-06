import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime
import os
import time

st.set_page_config(page_title="Clinic page", layout="wide")

# ---- styling + effects ----
st.markdown("""
<style>
/* smooth fade */
.fade-in {
    animation: fadeIn 0.6s ease-in;
}
@keyframes fadeIn {
    from {opacity: 0; transform: translateY(10px);}
    to {opacity: 1; transform: translateY(0);}
}

/* button hover */
.stButton>button {
    border-radius: 10px;
    transition: all 0.2s ease;
}
.stButton>button:hover {
    transform: scale(1.05);
}

/* card look */
.block-container {
    padding-top: 2rem;
}
section[data-testid="stSidebar"] {
    background-color: #f1f5f9;
}

/* success glow */
.success-box {
    animation: pop 0.4s ease;
}
@keyframes pop {
    0% {transform: scale(0.9);}
    100% {transform: scale(1);}
}
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'hospital_management.db')

if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
else:
    st.error("missing api key")
    st.stop()

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
    "1": {"en": "Dr. Faisal Al-Mahmood (Cardiology)"},
    "2": {"en": "Dr. Mariam Al-Sayed (Pediatrics)"},
    "3": {"en": "Dr. Yousef Al-Haddad (Orthopedics)"},
    "4": {"en": "Dr. Noura Al-Khalifa (Dermatology)"},
    "5": {"en": "Dr. Khalid Al-Fares (Plastic Surgery)"},
    "6": {"en": "Dr. Sara Al-Ansari (OB-GYN)"},
    "7": {"en": "Dr. Jasim Al-Ghanem (Urology)"},
    "8": {"en": "Dr. Layla Al-Mulla (Neurology)"},
    "9": {"en": "Dr. Hassan Ibrahim (Ophthalmology)"},
    "10": {"en": "Dr. Ahmed Al-Aali (General Medicine)"}
}

# sidebar
st.sidebar.title("🛠 tools")

if os.path.exists(DB_NAME):
    with open(DB_NAME, "rb") as f:
        st.sidebar.download_button("⬇️ download db", f, "hospital_management.db")

chat_tab, admin_tab = st.tabs(["💬 assistant", "📊 dashboard"])

# -------- CHAT --------
with chat_tab:
    st.title("🏥 Clinic Assistant")
    st.caption("AI receptionist with live booking")

    current_date = datetime.now().strftime("%A, %B %d, %Y")

    conn = get_db_connection()
    booked_df = pd.read_sql_query("SELECT doc_id, slot FROM appointments", conn)
    conn.close()

    schedule = booked_df.to_string(index=False) if not booked_df.empty else "none"

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(f'<div class="fade-in">{msg["content"]}</div>', unsafe_allow_html=True)

    if user_input := st.chat_input("type your request..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        system_instruction = f"""
        you are a clinic receptionist
        today: {current_date}

        doctors: {DOCTOR_LIST}
        busy slots: {schedule}

        use:
        [BOOKING: Name, DocID, YYYY-MM-DD HH:MM]
        [CANCEL: Name, DocID]
        """

        with st.chat_message("assistant"):
            try:
                with st.spinner("thinking..."):
                    time.sleep(1)  # fake delay for realism

                    response = mistral_client.chat.complete(
                        model="mistral-large-latest",
                        messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
                    )

                ai_response = response.choices[0].message.content

                # typing effect
                placeholder = st.empty()
                typed = ""
                for char in ai_response:
                    typed += char
                    placeholder.markdown(typed)
                    time.sleep(0.01)

                # cancel
                if "[CANCEL:" in ai_response:
                    data = ai_response.split("[CANCEL:")[1].split("]")[0]
                    parts = [p.strip() for p in data.split(",")]

                    if len(parts) >= 2:
                        if cancel_booking(parts[0], parts[1]):
                            st.toast("appointment removed")
                        else:
                            st.warning("not found")

                # booking
                if "[BOOKING:" in ai_response:
                    data = ai_response.split("[BOOKING:")[1].split("]")[0]
                    parts = [p.strip() for p in data.split(",")]

                    if len(parts) >= 3:
                        success, err = try_booking(parts[0], parts[1], parts[2])

                        if success:
                            st.markdown('<div class="success-box">', unsafe_allow_html=True)
                            st.success("booking confirmed ✅")
                            st.balloons()
                        else:
                            st.warning(f"failed: {err}")

                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})

            except Exception as err:
                st.error(f"error: {err}")

# -------- DASHBOARD --------
with admin_tab:
    st.subheader("📅 appointments overview")

    conn = get_db_connection()
    data = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not data.empty:
        col1, col2 = st.columns(2)
        col1.metric("total bookings", len(data))
        col2.metric("doctors active", data['doc_id'].nunique())

        st.divider()

        for id, info in DOCTOR_LIST.items():
            df = data[data['doc_id'] == id]

            with st.expander(f"👨‍⚕️ {info['en']} ({len(df)})"):
                if not df.empty:
                    st.dataframe(df[['patient_name', 'slot']], use_container_width=True)

        if st.button("🗑 clear all"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("no bookings yet")
