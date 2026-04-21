import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="Doctor Schedules", layout="wide")

DOCTORS = {
    "1": "Dr. Faisal Al-Mahmood (Cardiology)",
    "2": "Dr. Mariam Al-Sayed (Pediatrics)",
    "3": "Dr. Yousef Al-Haddad (Orthopedics)",
    "4": "Dr. Noura Al-Khalifa (Dermatology)",
    "5": "Dr. Khalid Al-Fares (Plastic Surgery)",
    "6": "Dr. Sara Al-Ansari (OB-GYN)",
    "7": "Dr. Jasim Al-Ghanem (Urology)",
    "8": "Dr. Layla Al-Mulla (Neurology)",
    "9": "Dr. Hassan Ibrahim (Ophthalmology)",
    "10": "Dr. Ahmed Al-Aali (General Medicine)"
}

st.title("Hospital Operations Dashboard")
st.markdown("---")

def get_data():
    conn = sqlite3.connect('hospital_management.db')
    df = pd.read_sql_query("SELECT patient_name, doc_id, slot FROM appointments", conn)
    conn.close()
    return df

df = get_data()

st.header("Individual Doctor Schedules")

if not df.empty:
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Summary")
        st.metric("Total Appointments", len(df))
        st.write("Select a doctor to view their specific day.")
    with col2:
        for doc_id, doc_name in DOCTORS.items():
            doc_appointments = df[df['doc_id'] == doc_id]
            with st.expander(f"{doc_name} ({len(doc_appointments)} Patients)"):
                if not doc_appointments.empty:
                    display_df = doc_appointments[['patient_name', 'slot']].rename(
                        columns={'patient_name': 'Patient Name', 'slot': 'Time'}
                    )
                    st.table(display_df)
                else:
                    st.info("No appointments scheduled for this doctor.")
else:
    st.info("No data available yet. Please book an appointment through the AI Chat.")
st.divider()
if st.button("Reset All Hospital Data"):
    conn = sqlite3.connect('hospital_management.db')
    conn.execute("DELETE FROM appointments")
    conn.commit()
    conn.close()
    st.success("All records cleared.")
    st.rerun()
    # Add this to the bottom of Dashboard.py
with open("hospital_management.db", "rb") as f:
    st.download_button(
        label="Download Database File (.db)",
        data=f,
        file_name="hospital_data_backup.db",
        mime="application/x-sqlite3"
    )
