# reception-# AlShifa Clinic Reception System

I built this for my project — it's basically a clinic receptionist that runs in your browser. Instead of filling out some boring form to book an appointment, you just chat with an AI and it handles everything.

It's built in Python using Streamlit, and the AI part runs on Mistral. The whole thing took a while to get working properly, especially the voice input.

---

## What it actually does

When you open the app you log in as a patient, enter your name and phone number, and then you just... talk to it. You can say something like "I need to see a cardiologist sometime next week" and the AI figures out which doctor, asks you to confirm a time, and books it. It saves to a real SQLite database, validates the slot, and spits out a PDF receipt you can download.

There's also a staff login that opens a completely different dashboard where you can see all the appointments, download the database, and change each doctor's working hours.

Oh and there's voice input too — you can just speak instead of typing, it uses Google's speech-to-text under the hood.

---

## The part I'm most proud of

The way the AI triggers database actions was the trickiest thing to figure out. The AI doesn't write to the database directly — instead I made it embed a hidden command tag in its reply, like this:

```
what the AI actually outputs:
"Great, I've booked that for you! [BOOKING: sara ahmed, +97312345, 2, 2025-05-10 10:00]"

what the patient sees:
"Great, I've booked that for you!"

what the app does behind the scenes:
runs save_booking("sara ahmed", "+97312345", "2", "2025-05-10 10:00")
```

The app strips the tag before showing the message, then separately scans for it with regex to run the right function. Same thing for cancellations and rescheduling. It's a bit fragile (if Mistral formats the tag weirdly it breaks) but it works well enough for this.

---

## Tech used

- Python + Streamlit — the whole UI is just Python, no HTML needed
- Mistral AI (`mistral-large-latest`) — the chat model
- SQLite — stores appointments and doctor schedules
- FPDF — generates the PDF receipts
- SpeechRecognition — for the voice input feature
- Pandas — for the admin appointments table

---

## Running it yourself

Clone it and install the dependencies:

```bash
git clone https://github.com/yourusername/alshifa-clinic.git
cd alshifa-clinic
pip install streamlit mistralai fpdf2 SpeechRecognition pandas
```

You need a Mistral API key. Create a file at `.streamlit/secrets.toml` and put this in it:

```toml
MISTRAL_API_KEY = "your_key_here"
```

Then just run:

```bash
streamlit run rec.py
```

---

## Logging in

- **Patient** — just type any name and phone number
- **Staff** — password is `admin123`
- **Guest** — can browse but can't book anything

---

## How bookings are validated

Before anything gets saved to the database, the app checks:

1. The date/time string is actually a valid format
2. The slot is in the future (not today or earlier)
3. The doctor works on that day and at that hour
4. Nobody else has already booked that exact slot

The database also has a `UNIQUE(doc_id, slot)` constraint as a backup so even if something slips through, the insert will fail cleanly.

---

## Stuff I know is not perfect

**Password hashing** — I'm using SHA-256 with no salt for the admin password. It's not great, in a real system I'd use bcrypt. But it's a student project so I left it.

**The regex parsing** — if Mistral decides to format `[BOOKING: ...]` slightly differently one day, the whole thing breaks. The proper fix would be to use Mistral's function calling feature so you get structured output guaranteed. I know how to fix it, just didn't implement it here.

**Patient identity** — patients are identified by name only (stored lowercase). If two people have the same name that could cause issues. Would need a proper user ID system for production.

**Chat history** — the full conversation gets sent to Mistral every single message. For a long chat that's going to hit the context limit eventually. Would need to truncate or summarize old messages.

---

## Doctors in the system

10 doctors across different specialties — Cardiology, Pediatrics, Orthopedics, Dermatology, General Medicine, Gynecology, Neurology, Ophthalmology, ENT, and Psychiatry. Their schedules default to 9am–6pm Sunday to Thursday but the admin can change that.

---

## Clinic details

AlShifa Clinic, Building 115, Block 945, Street 4504, Awali, Bahrain. Open Sun–Thu 9am to 6pm.

---

*Student project — 2025*
