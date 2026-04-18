from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime, timedelta
import sqlite3, re

app = Flask(__name__)

DB_PATH = "hospital_management.db"


def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def setup():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        phone TEXT PRIMARY KEY,
        name TEXT
    )
    """)

    conn.commit()
    conn.close()


setup()


DOCTORS = {
    "1": "Dr. Faisal Al-Mahmood (Cardiology)",
    "2": "Dr. Mariam Al-Sayed (Pediatrics)",
    "3": "Dr. Yousef Al-Haddad (Orthopedics)",
    "4": "Dr. Noura Al-Khalifa (Dermatology)",
    "5": "Dr. Khalid Al-Fares",
    "6": "Dr. Sara Al-Ansari",
    "7": "Dr. Jasim Al-Ghanem",
    "8": "Dr. Layla Al-Mulla",
    "9": "Dr. Hassan Ibrahim",
    "10": "Dr. Ahmed Al-Aali"
}


def get_user(phone):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM users WHERE phone=?", (phone,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else None


def save_user(phone, name):
    conn = db()
    cur = conn.cursor()
    cur.execute("REPLACE INTO users VALUES (?,?)", (phone, name))
    conn.commit()
    conn.close()


def parse_doctor(msg):
    msg = msg.lower()
    if "derma" in msg: return "4"
    if "cardio" in msg: return "1"
    if "child" in msg or "pediatric" in msg: return "2"
    if "bone" in msg or "ortho" in msg: return "3"
    return None


def parse_date(msg):
    now = datetime.now()
    msg = msg.lower()

    if "tomorrow" in msg:
        base = now + timedelta(days=1)
    elif "today" in msg:
        base = now
    else:
        m = re.search(r"\d{4}-\d{2}-\d{2}", msg)
        base = datetime.strptime(m.group(), "%Y-%m-%d") if m else now + timedelta(days=1)

    t = re.search(r"(\d{1,2})(:\d{2})?\s*(am|pm)?", msg)
    if t:
        h = int(t.group(1))
        m = int(t.group(2)[1:]) if t.group(2) else 0
        if t.group(3) == "pm" and h != 12: h += 12
        base = base.replace(hour=h, minute=m)
    else:
        base = base.replace(hour=10, minute=0)

    if base.year < 2026:
        base = base.replace(year=2026)

    if base < now:
        base += timedelta(days=1)

    return base.strftime("%Y-%m-%d %H:%M")


def get_free_slots(doc):
    now = datetime.now()
    slots = []

    for d in range(3):
        day = now + timedelta(days=d)
        if day.weekday() >= 5:
            continue

        for h in range(9, 18):
            for m in [0, 30]:
                slot = day.replace(hour=h, minute=m, second=0, microsecond=0)
                if slot > now:
                    slots.append(slot.strftime("%Y-%m-%d %H:%M"))

    return slots[:5]


def detect_intent(msg):
    msg = msg.lower()
    if "cancel" in msg: return "cancel"
    if "reschedule" in msg or "change" in msg: return "reschedule"
    if "book" in msg or "appointment" in msg: return "book"
    return "unknown"


def process(msg, phone):
    name = get_user(phone)

    if not name:
        m = re.search(r"my name is (\w+)", msg.lower())
        if m:
            name = m.group(1)
            save_user(phone, name)
            return f"Nice to meet you, {name}! How can I help?"
        return "👋 Hi! What's your name?"

    intent = detect_intent(msg)

    if intent == "book":
        doc = parse_doctor(msg)
        if not doc:
            return f"{name}, which doctor?"

        slot = parse_date(msg)

        return f"""✅ Done {name}
Doctor: {DOCTORS[doc]}
Time: {slot}"""

    if intent == "cancel":
        return f"✅ Cancelled, {name}"

    if intent == "reschedule":
        slot = parse_date(msg)
        return f"🔄 Updated {name}, new time: {slot}"

    return f"""Hi {name} 👋

Try:
- Book dermatology tomorrow at 3
- Cancel appointment
- Reschedule to 5pm"""
    

@app.route("/whatsapp", methods=["POST"])
def reply():
    msg = request.form.get("Body")
    phone = request.form.get("From")

    resp = MessagingResponse()
    resp.message(process(msg, phone))

    return str(resp)


if __name__ == "__main__":
    app.run(port=5000)
