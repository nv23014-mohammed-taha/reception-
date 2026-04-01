from mistralai import Mistral, UserMessage, SystemMessage
import sqlite3
import dateparser
import os
from dotenv import load_dotenv

load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

# --- DATABASE ---
conn = sqlite3.connect("appointments.db")
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS doctors (id INTEGER PRIMARY KEY, name TEXT)")
c.execute("""CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY,
    patient_name TEXT,
    doctor_name TEXT,
    date TEXT,
    time TEXT)""")
conn.commit()
c.executemany("INSERT OR IGNORE INTO doctors (id, name) VALUES (?, ?)",
              [(1, "Dr. Ahmed"), (2, "Dr. Sara"), (3, "Dr. Khalid")])
conn.commit()

# --- Tools ---
def doctor_availability_tool(patient_name, doctor_name, date, time):
    # check availability
    booked = c.execute(
        "SELECT * FROM appointments WHERE doctor_name=? AND date=? AND time=?",
        (doctor_name, date, time)
    ).fetchone()
    if booked:
        return f"{doctor_name} is not available at {date} {time}."
    c.execute(
        "INSERT INTO appointments (patient_name, doctor_name, date, time) VALUES (?, ?, ?, ?)",
        (patient_name, doctor_name, date, time)
    )
    conn.commit()
    return f"✅ Appointment booked for {patient_name} with {doctor_name} on {date} at {time}."

# --- Receptionist Agent ---
agent = client.beta.agents.create(
    model="mistral-medium-latest",
    name="Healthcare Receptionist",
    description="Handles appointments for doctors in a clinic",
    instructions="""
You are a smart healthcare receptionist. Extract patient name, doctor, date, and time from user input. 
Use the doctor_availability_tool to check availability and book appointments. 
Respond in friendly natural language.
""",
    tools=[{"type": "custom", "name": "doctor_availability_tool"}]
)

# --- Start conversation ---
while True:
    user_input = input("User: ")
    if user_input.lower() in ["quit", "exit"]:
        break

    response = client.beta.conversations.start(
        agent_id=agent.id,
        inputs=user_input
    )
    print("Receptionist:", response.outputs[0].content)
