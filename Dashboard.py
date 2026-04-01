import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="Clinic Dashboard", page_icon="📊")

st.title("📋 Confirmed Appointments")
st.markdown("---")

def get_appointments():
    # We connect to the same database file used in rec.py
    conn = sqlite3.connect('hospital_management.db')
    query = """
    SELECT 
        patient_name AS 'Patient Name', 
        doc_id AS 'Doctor ID', 
        slot AS 'Appointment Date & Time' 
    FROM appointments 
    ORDER BY slot ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Load the data
df = get_appointments()

if not df.empty:
    # 1. Show a summary metric
    st.metric("Total Bookings", len(df))
    
    # 2. Show the interactive table
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # 3. Add a download button for CSV (Optional)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Schedule", data=csv, file_name="clinic_schedule.csv", mime="text/csv")
else:
    st.warning("No appointments found in the database.")

# Admin Tools
with st.expander("🛠️ Admin Tools"):
    if st.button("Clear Database"):
        conn = sqlite3.connect('hospital_management.db')
        conn.execute("DELETE FROM appointments")
        conn.commit()
        conn.close()
        st.success("Database cleared!")
        st.rerun()
