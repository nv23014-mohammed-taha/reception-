import streamlit as st
from mistralai.client import Mistral
from st_supabase_connection import SupabaseConnection
from datetime import datetime
import pandas as pd

# --- 1. INITIALIZE CONNECTIONS ---
st.set_page_config(page_title="NCST Clinic Pro", layout="wide")

try:
    # Connects using the secrets we defined above
    st_supabase = st.connection("supabase", type=SupabaseConnection)
    client = Mistral(api_key=st.secrets["MISTRAL_API_KEY"])
except Exception as e:
    st.error("Connection Error: Check your secrets.toml file!")
    st.stop()

# --- 2. DOCTOR DIRECTORY ---
DOCTORS = {
    "1": "Dr. Faisal (Cardiology)",
    "2": "Dr. Mariam (Pediatrics)",
    "3": "Dr. Yousef (Orthopedics)",
    "10": "Dr. Ahmed (General)"
}

# --- 3. CORE LOGIC FUNCTIONS ---
def is_slot_free(doc_id, slot):
    """Check Supabase Cloud for existing bookings."""
    res = st_supabase.table("appointments").select("*").eq("doc_id", doc_id).eq("slot", slot).execute()
    return len(res.data) == 0

def save_booking(name, doc_id, slot):
    """Insert the booking into the cloud database."""
    data = {"patient_name": name, "doc_id": doc_id, "slot": slot}
    st_supabase.table("appointments").insert(data).execute()

# --- 4. THE INTERFACE ---
tab_chat, tab_admin = st.tabs(["💬 Patient Booking", "📊 Clinic Admin"])

with tab_chat:
    st.title("🏥 NCST Smart Receptionist")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("I'd like to book an appointment..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        # AI Instruction
        sys_prompt = f"Medical receptionist. Doctors: {DOCTORS}. Sun-Thu 8-5. Confirm with: [BOOK: Name, DocID, YYYY-MM-DD HH:MM]"
        
        with st.chat_message("assistant"):
            response = client.chat.complete(model="mistral-large-latest", 
                                            messages=[{"role": "system", "content": sys_prompt}] + st.session_state.messages)
            msg = response.choices[0].message.content
            st.markdown(msg)
            
            # Action logic if AI confirms booking
            if "[BOOK:" in msg:
                try:
                    # Extracting data from the AI tag
                    raw = msg.split("[BOOK:")[1].split("]")[0].split(",")
                    p_name, d_id, p_slot = [i.strip() for i in raw]
                    
                    if is_slot_free(d_id, p_slot):
                        save_booking(p_name, d_id, p_slot)
                        st.success(f"Successfully booked {p_name} in the cloud!")
                        st.balloons()
                    else:
                        st.warning("That slot is already taken in our database!")
                except Exception as e:
                    st.error("Error parsing booking tag.")

            st.session_state.messages.append({"role": "assistant", "content": msg})

with tab_admin:
    st.title("👨‍⚕️ Management Dashboard")
    # Fetch all data from Supabase
    all_data = st_supabase.table("appointments").select("*").execute()
    
    if all_data.data:
        df = pd.DataFrame(all_data.data)
        st.subheader("Current Appointments")
        st.dataframe(df[['patient_name', 'doc_id', 'slot']], use_container_width=True)
    else:
        st.info("The database is currently empty.")
