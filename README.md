# Yojimbo

**Real-Time Multi-Lingual AI Agent Receptionist for Local Government**

Yojimbo is the operating system for local government offices. It manages calls, texts, and bookings with AI-powered multi-lingual support.

## What It Does

Yojimbo handles the entire communication lifecycle for government offices:

- **AI Phone Calls** - Inbound/outbound call handling via Twilio ConversationRelay. The AI agent (powered by Google Gemini) greets callers, answers questions, routes to departments, and books appointments — all in the caller's native language.
- **Real-Time Translation** - Automatic language detection and translation for 10+ languages (English, Spanish, Chinese, Vietnamese, Korean, Tagalog, Arabic, French, German, Japanese). Callers speak their language; staff see English transcripts.
- **SMS Messaging** - Inbound SMS handling with AI-generated responses. Appointment confirmations and reminders via text.
- **Appointment Booking** - AI-driven scheduling with real-time availability checking, conflict detection, and multi-department support. Callers can book, look up, and cancel appointments by voice or text.
- **Staff Dashboard** - Live WebSocket-powered dashboard showing active calls, real-time transcripts with translations, appointment calendar, contact directory, and call analytics.

## Architecture

```
Caller --> Twilio --> [Webhook] --> FastAPI --> [WebSocket] --> Gemini AI
                                      |                           |
                                      v                           v
                                   SQLite DB              Google Translate
                                      |
                                      v
                              Staff Dashboard (HTMX)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python FastAPI + Uvicorn (async) |
| AI Agent | Google Gemini 2.0 Flash (function-calling) |
| Telephony | Twilio Voice + ConversationRelay + SMS |
| Translation | Google Cloud Translation API v3 |
| Database | SQLite + aiosqlite + SQLAlchemy 2.0 (async) |
| Frontend | Jinja2 + HTMX + Alpine.js + Tailwind CSS |
| Real-time | WebSockets (native FastAPI) |

### Key Design Decisions

- **Twilio ConversationRelay** abstracts away raw audio/STT/TTS. The backend only handles text, making the architecture dramatically simpler.
- **Google Gemini** as the AI agent with native function-calling for structured actions (booking, availability checking, call transfer).
- **SQLite for MVP** with async SQLAlchemy. Migration to PostgreSQL is a one-line config change.
- **HTMX + Alpine.js** instead of React/Vue — no build step, server-rendered, real-time via WebSocket.

## Project Structure

```
yojimbo/
├── app/
│   ├── main.py                  # FastAPI app, routes, lifespan
│   ├── config.py                # Pydantic Settings (env vars)
│   ├── database.py              # Async SQLAlchemy engine
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── call.py              # Call, CallEvent, ConversationTurn
│   │   ├── appointment.py       # Appointment, TimeSlot
│   │   ├── contact.py           # Contact
│   │   ├── department.py        # Department, StaffMember
│   │   ├── message.py           # SMSMessage
│   │   └── user.py              # DashboardUser
│   ├── schemas/                 # Pydantic request/response models
│   ├── api/                     # REST API endpoints
│   │   ├── twilio_webhooks.py   # /api/twilio/voice, /sms, /status
│   │   ├── calls.py             # Call management
│   │   ├── appointments.py      # Appointment CRUD + availability
│   │   ├── contacts.py          # Contact directory
│   │   ├── departments.py       # Department management
│   │   ├── messages.py          # SMS endpoints
│   │   └── dashboard.py         # Stats, activity feed, auth
│   ├── ws/                      # WebSocket handlers
│   │   ├── conversation_relay.py # Twilio ConversationRelay
│   │   ├── dashboard.py         # Staff dashboard real-time
│   │   └── manager.py           # Connection manager
│   ├── services/                # Business logic
│   │   ├── ai_agent.py          # Gemini conversation + function-calling
│   │   ├── translator.py        # Google Cloud Translation
│   │   ├── appointment_engine.py # Booking logic
│   │   ├── sms_handler.py       # SMS processing
│   │   └── notification.py      # Dashboard event broadcasting
│   ├── core/                    # Shared utilities
│   │   ├── prompts.py           # AI system prompts + Gemini function declarations
│   │   ├── constants.py         # Language codes, statuses
│   │   └── security.py          # Auth, password hashing, Twilio validation
│   ├── templates/               # Jinja2 HTML (dashboard UI)
│   └── static/                  # CSS + JS
├── tests/                       # Pytest async tests
├── scripts/
│   └── seed_departments.py      # Populate demo data
├── pyproject.toml
├── .env.example
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- A Twilio account (for calls and SMS)
- A Google Gemini API key
- (Optional) Google Cloud project for Translation API

### Installation

```bash
# Clone the repository
git clone <repo-url> yojimbo
cd yojimbo

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Configure API Keys

Edit `.env` with your credentials:

```ini
# Required
GEMINI_API_KEY=your-gemini-api-key
SECRET_KEY=a-random-secret-string

# For phone calls (requires Twilio account)
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# For translation (optional - falls back to pass-through)
GOOGLE_CLOUD_PROJECT_ID=your-project-id

# Public URL for Twilio webhooks (use ngrok for local dev)
BASE_URL=https://your-domain.ngrok-free.app
```

### Seed the Database

```bash
python scripts/seed_departments.py
```

This creates 7 government departments, staff members, time slots, and demo login accounts:
- **admin / admin** (full access)
- **staff / staff** (front desk)

### Run the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 and log in.

### Connect Twilio (for phone calls)

1. Install ngrok and expose your local server:
   ```bash
   ngrok http 8000
   ```
2. Copy the ngrok HTTPS URL to `.env` as `BASE_URL`
3. In your Twilio console, set your phone number's webhooks:
   - Voice: `https://your-ngrok-url/api/twilio/voice` (POST)
   - SMS: `https://your-ngrok-url/api/twilio/sms` (POST)

### Run Tests

```bash
pytest -v
```

## API Endpoints

### Twilio Webhooks
- `POST /api/twilio/voice` - Inbound call (returns ConversationRelay TwiML)
- `POST /api/twilio/voice/outbound` - Outbound call callback
- `POST /api/twilio/sms` - Inbound SMS
- `POST /api/twilio/status` - Call status updates

### REST API
- `GET/POST /api/calls` - Call management
- `GET/POST /api/appointments` - Appointment CRUD
- `GET /api/appointments/availability` - Check open slots
- `GET/POST /api/contacts` - Contact directory
- `GET/POST /api/departments` - Department management
- `GET/POST /api/messages` - SMS history and sending
- `GET /api/dashboard/stats` - Dashboard statistics
- `GET /api/dashboard/activity` - Activity feed
- `POST /api/auth/login` - Staff authentication

### WebSockets
- `ws://host/ws/conversation-relay` - Twilio ConversationRelay
- `ws://host/ws/dashboard` - Staff dashboard real-time updates

## How a Call Works

1. A caller dials the Twilio number
2. Twilio hits `POST /api/twilio/voice` and gets TwiML with ConversationRelay config
3. Twilio opens a WebSocket to `/ws/conversation-relay` and handles STT/TTS
4. Caller speech arrives as text; the server:
   - Detects the language
   - Translates to English (via Google Translate)
   - Sends to Gemini with function-calling tools
   - If Gemini calls a function (book_appointment, check_availability, etc.), executes it
   - Translates the response back to the caller's language
   - Streams text back through ConversationRelay (Twilio speaks it)
5. Staff see the live transcript (both languages) on the dashboard via WebSocket
6. After the call ends, a summary and sentiment are recorded

## Supported Languages

English, Spanish, Chinese (Mandarin), Vietnamese, Korean, Tagalog, Arabic, French, German, Japanese — with automatic detection.

## License

Proprietary - Yojimbo Inc.
