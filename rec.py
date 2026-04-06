import streamlit as st
from mistralai.client import Mistral
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Clinic page", layout="wide")

if "MISTRAL_API_KEY" in st.secrets:
    mistral_client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
else:
    st.error("Hey, you forgot to add the MISTRAL_API_KEY to your secrets!")
    st.stop()

DB_NAME = 'hospital_management.db'


def get_db_connection():
    """Helper to handle the connection with a timeout for concurrent users."""
    return sqlite3.connect(DB_NAME, check_same_thread=False, timeout=10)

def init_db():
    """Build the table if it doesn't exist. Added a UNIQUE constraint to stop double-booking."""
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

def try_booking(name, doc_id, time_slot):
    """The core logic for checking availability and saving the record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        
    
        cursor.execute("SELECT id FROM appointments WHERE doc_id=? AND slot=?", (doc_id, time_slot))
        
        if cursor.fetchone():
            orig_time = datetime.strptime(time_slot, "%Y-%m-%d %H:%M")
            suggested_time = (orig_time + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            conn.rollback()
            return False, suggested_time
        
    
        cursor.execute("INSERT INTO appointments (patient_name, doc_id, slot) VALUES (?,?,?)", 
                       (name, doc_id, time_slot))
        conn.commit()
        return True, None
        
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "Someone just beat you to this slot!"
    except Exception as e:
        conn.rollback()
        return False, f"Unexpected error: {e}"
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


chat_tab, admin_tab = st.tabs(["💬 Virtual Receptionist", "📊 Staff Dashboard"])


with chat_tab:
    st.title("🏥 Welcome to the Clinic page")
    st.info("I can help you find a doctor and book your visit.")

    # Fetch live bookings so the AI actually knows what's taken
    conn = get_db_connection()
    booked_df = pd.read_sql_query("SELECT doc_id, slot FROM appointments", conn)
    conn.close()
    
    # Simple string for the AI to read
    live_schedule = booked_df.to_string(index=False) if not booked_df.empty else "The schedule is totally clear."

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display the conversation
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("Tell me which doctor or specialty you need..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"): 
            st.markdown(user_input)


        system_instruction = f"""
        You are a friendly receptionist at  AI Clinic. 
        Docs available: {DOCTOR_LIST}. 

        IMPORTANT: These times are ALREADY BOOKED. Do not offer them:
        {live_schedule}

        If they want a booked slot, say it's full and offer the next available time.
        Once confirmed, you MUST include this hidden tag: [BOOKING: Name, DocID, YYYY-MM-DD HH:MM]
        """
        
        with st.chat_message("assistant"):
            try:
                response = mistral_client.chat.complete(
                    model="mistral-large-latest", 
                    messages=[{"role": "system", "content": system_instruction}] + st.session_state.chat_history
                )
                ai_response = response.choices[0].message.content
                st.markdown(ai_response)
                
                if "[BOOKING:" in ai_response:
                    try:
                        # Parsing the tag [BOOKING: Name, ID, Time]
                        data_str = ai_response.split("[BOOKING:")[1].split("]")[0]
                        parts = [p.strip() for p in data_str.split(",")]
                        
                        if len(parts) >= 3:
                            name, d_id, t_slot = parts[0], parts[1], parts[2]
                            is_ok, suggestion = try_booking(name, d_id, t_slot)
                            
                            if is_ok:
                                st.success(f"Got it! Appointment for {name} is in the system.")
                                st.balloons()
                            else:
                                st.warning(f"Wait, that slot just filled up. Maybe try {suggestion}?")
                    except Exception:
                        st.error("I had trouble reading the booking format. Can you repeat that?")
                
                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
            except Exception as err:
                st.error(f"Mistral had an issue: {err}")

with admin_tab:
    st.subheader("Current Appointments")
    
    conn = get_db_connection()
    all_data = pd.read_sql_query("SELECT * FROM appointments", conn)
    conn.close()

    if not all_data.empty:
        # Show a summary metric
        st.metric("Total Bookings", len(all_data))
        
        # Organize by doctor for easier reading
        for id, info in DOCTOR_LIST.items():
            doc_filter = all_data[all_data['doc_id'] == id]
            with st.expander(f"{info['en']} ({len(doc_filter)})"):
                if not doc_filter.empty:
                    clean_df = doc_filter[['patient_name', 'slot']].rename(
                        columns={'patient_name': 'Patient Name', 'slot': 'Time Slot'}
                    )
                    st.table(clean_df)
                else:
                    st.caption("No appointments for this doctor yet.")
        
        st.write("---")
        if st.button("Clear All Data (Danger Zone)"):
            conn = get_db_connection()
            conn.execute("DELETE FROM appointments")
            conn.commit()
            conn.close()
            st.rerun()
    else:
        st.info("No one has booked anything yet. Switch to the chat to start!")
