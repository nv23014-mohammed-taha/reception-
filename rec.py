import streamlit as st
from mistralai.client import Mistral
from st_supabase_connection import SupabaseConnection
from datetime import datetime, timedelta

# --- 1. CONFIG & STYLING ---
st.set_page_config(page_title="NCST AI Clinic PRO", layout="wide", page_icon="🏥")

# Professional UI Styling
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .stChatFloatingInputContainer { background-color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SECURE CLIENT INITIALIZATION ---
try:
    # Connect to Supabase Cloud Database
    conn = st.connection("supabase", type=SupabaseConnection)
    # Connect to Mistral AI
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.info("Ensure SUPABASE_URL, SUPABASE_KEY, and MISTRAL_API_KEY are in your Secrets.")
    st.stop()

# --- 3. DATABASE CONTROLLER (CRUD Operations) ---
class ClinicDB:
    @staticmethod
    def get_appointments():
        # Fetch data from the cloud
        return conn.table("appointments").select("*").execute()

    @staticmethod
    def check_availability(doc_id, slot_str):
        # Professional check for double-booking
        response = conn.table("appointments") \
            .select("*") \
            .eq("doc_id", doc_id) \
            .eq("slot", slot_str) \
            .execute()
        return len(response.data) == 0

    @staticmethod
    def create_appointment(name, doc_id, slot_str):
        # Insert data into the cloud
        data = {"patient_name": name, "doc_id": doc_id, "slot": slot_str}
        return conn.table("appointments").insert(data).execute()

    @staticmethod
    def clear_all():
        # Admin function to wipe records
        return conn.table("appointments").delete().neq("id", 0).execute()

# --- 4. CLINIC LOGIC & DOCTORS ---
DOCTORS = {
    "1": {"name": "Dr. Faisal Al-Mahmood", "dept": "Cardiology"},
    "2": {"name": "Dr. Mariam Al-Sayed", "dept": "Pediatrics"},
    "3": {"name": "Dr. Yousef Al-Haddad", "dept": "Orthopedics"},
    "10": {"name": "Dr. Ahmed Al-Aali", "dept": "General Medicine"}
}

def validate_time(slot_str):
    try:
        dt = datetime.strptime(slot_str, "%Y-%m-%d %H:%M")
        if dt.weekday() in [4, 5]: return False, "weekends (Fri-Sat)"
        if not (8 <= dt.hour < 17): return False, "working hours (08:00-17:00)"
        return True, dt
    except:
        return False, "format (YYYY-MM-DD HH:MM)"

# --- 5. UI NAVIGATION ---
tab_chat, tab_admin = st.tabs(["💬 AI Patient Portal", "👨‍⚕️ Staff Dashboard"])

with tab_chat:
    st.title("🏥 Smart Receptionist")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("How can I help you today?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        sys_prompt = f"You are a medical receptionist. Doctors: {DOCTORS}. Clinic: Sun-Thu, 8am-5pm. Format: [BOOK: Name, DocID, YYYY-MM-DD HH:MM]"
        
        with st.chat_message("assistant"):
            response = client.chat.complete(model="mistral-large-latest", 
                                            messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages)
            msg = response.choices[0].message.content
            st.markdown(msg)
            
            if "[BOOK:" in msg:
                try:
                    raw = msg.split("[BOOK:")[1].split("]")[0].split(",")
                    name, d_id, t_str = [i.strip() for i in raw]
                    
                    is_valid, result = validate_time(t_str)
                    if is_valid:
                        if ClinicDB.check_availability(d_id, t_str):
                            ClinicDB.create_appointment(name, d_id, t_str)
                            st.success(f"✅ Confirmed for {name}!")
                            st.balloons()
                        else:
                            st.warning("❌ This slot is already booked.")
                    else:
                        st.error(f"❌ Outside {result}")
                except Exception as e:
                    st.error("Format error in booking.")

            st.session_state.messages.append({"role": "assistant", "content": msg})

with tab_admin:
    st.title("📊 Clinic Operations")
    data = ClinicDB.get_appointments()
    
    if data.data:
        df = pd.DataFrame(data.data)
        st.metric("Total Patients Today", len(df))
        
        # Professional Table View
        df['Doctor'] = df['doc_id'].map(lambda x: DOCTORS.get(x, {}).get('name', 'N/A'))
        st.dataframe(df[['patient_name', 'Doctor', 'slot']], use_container_width=True)
        
        if st.sidebar.button("🗑️ Reset Clinic Data"):
            ClinicDB.clear_all()
            st.rerun()
    else:
        st.info("No appointments currently in the cloud database.")
