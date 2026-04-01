import streamlit as st
from mistralai.client import Mistral  # <--- Corrected Import
import sqlite3

# Initialize Client
# Best practice: Use Streamlit secrets for your API Key
api_key = ORN8aRA54fNrTef0wJtgz768alJlPYJ5
client = Mistral(api_key=api_key)

st.title("🏥 AI Healthcare Receptionist")

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("How can I help? / كيف يمكنني مساعدتك؟"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call Mistral v2.x API
    with st.chat_message("assistant"):
        # The new method is .chat.complete
        response = client.chat.complete(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": "You are a medical receptionist. Speak English and Arabic."},
                *st.session_state.messages
            ]
        )
        
        answer = response.choices[0].message.content
        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
