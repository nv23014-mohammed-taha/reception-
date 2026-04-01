import streamlit as st
import sqlite3
from mistralai.models.chat_completion import ChatMessage
from datetime import datetime
# NEW VERSION (v2.x)
from mistralai import Mistral

# Note the change to 'Mistral' and the use of 'api_key' argument
client = Mistral(api_key="ORN8aRA54fNrTef0wJtgz768alJlPYJ5")

# When sending messages, you can now use simple dictionaries 
# or the new 'UserMessage' / 'SystemMessage' classes.

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('hospital.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY, patient_name TEXT, doctor_name TEXT, date TEXT)''')
    # Pre-populate doctors if needed
    doctors = ["Dr. Smith (Cardiology)", "Dr. Laila (Pediatrics)", "Dr. Omar (General)"]
    conn.commit()
    conn.close()
    return doctors

doctors_list = init_db()

# --- STREAMLIT UI ---
st.set_page_config(page_title="AI Medical Receptionist", page_icon="🏥")
st.title("🏥 Smart Healthcare Receptionist")
st.markdown("---")

# Sidebar for Admin View
with st.sidebar:
    st.header("Admin: Today's Bookings")
    conn = sqlite3.connect('hospital.db')
    bookings = conn.execute("SELECT * FROM appointments").fetchall()
    for b in bookings:
        st.write(f"📌 {b[1]} with {b[2]} on {b[3]}")
    conn.close()

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am your medical assistant. How can I help you book an appointment today? \n\n مرحباً! أنا مساعدك الطبي. كيف يمكنني مساعدتك في حجز موعد اليوم؟"}
    ]

# Display Chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- CHAT LOGIC ---
if prompt := st.chat_input("Type here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Prepare context for Mistral
    system_instruction = f"""
    You are a helpful medical receptionist. 
    Available Doctors: {', '.join(doctors_list)}.
    Your task:
    1. Identify the patient's name, doctor choice, and date.
    2. If information is missing, ask for it politely in the language the user used (English or Arabic).
    3. Once you have Name, Doctor, and Date, confirm the booking clearly.
    """
    
    mistral_msgs = [ChatMessage(role="system", content=system_instruction)] + \
                   [ChatMessage(role=m["role"], content=m["content"]) for m in st.session_state.messages]

    with st.chat_message("assistant"):
        response_stream = client.chat_stream(model="mistral-large-latest", messages=mistral_msgs)
        placeholder = st.empty()
        full_response = ""
        
        for chunk in response_stream:
            full_response += chunk.choices[0].delta.content or ""
            placeholder.markdown(full_response + "▌")
        placeholder.markdown(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

    # --- SIMPLE EXTRACTION (Concept) ---
    # In a production app, you would use Mistral's 'Tool Use' / Function Calling 
    # to automatically trigger the database insert here.
