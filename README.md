# Yojimbo — Government AI Phone Receptionist

[![CI](https://github.com/andkhong/yojimbo/actions/workflows/ci.yml/badge.svg)](https://github.com/andkhong/yojimbo/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **real-time, multilingual AI phone receptionist** built specifically for city and county government. Handles 24/7 inbound calls, books appointments, routes to departments, and gives city staff a full admin dashboard with compliance audit trails.

## Why Yojimbo for Government?

| Problem | Yojimbo Solution |
|---------|-----------------|
| Staff overwhelmed by repetitive calls | AI resolves 70%+ of calls without human escalation |
| After-hours call abandonment | 24/7 coverage in 10+ languages |
| No visibility into call patterns | Real-time analytics dashboard + SLA reports |
| Compliance/procurement requirements | Full audit log, RBAC, staff access controls |
| Multi-department routing complexity | Per-department phone numbers, time slots, AI context |
| Translation service latency | Native Gemini multilingual — zero translation delay |

## Feature Overview

### Core AI
- **Gemini-powered conversation** — native multilingual, no translation step
- **Knowledge base injection** — FAQ entries from your database into every call
- **Department-aware routing** — AI knows which departments handle which services
- **Appointment booking** — books in real time, sends SMS reminders
- **Live transcript** — every call turn stored, full call summary on completion

### Admin Dashboard
- **Live call monitor** — watch active calls, transfer or terminate from browser
- **WebSocket events** — real-time call start/end/transcript broadcasts at `/ws/monitor`
- **Staff management** — create users with roles: `admin` / `supervisor` / `operator` / `readonly`
- **Department management** — CRUD, per-department phone numbers, time slots, staff
- **Knowledge base editor** — manage FAQ entries per department + language
- **Reminder management** — view pending reminders, trigger batch send, see history

### Analytics & Compliance
- Call volume by day/week/month, per department
- Language distribution breakdown
- AI resolution rate vs. escalated vs. abandoned
- SLA compliance per department (configurable handle-time target)
- Appointment booking, cancellation, and no-show rates
- Full government operational summary (`GET /api/gov/summary`)
- **Audit log** — every API mutation is auto-logged with IP, user, action, resource

### Authentication
- **Session cookie** — for browser dashboard
- **JWT Bearer token** — for API integrations and external clients
- **Token refresh** — 8-hour access tokens, 30-day refresh tokens
- **Rate limiting** — per-IP token bucket (60/min webhooks, 10/min auth, 300/min API)

---

## Quick Start

### Prerequisites
- Python 3.11+
- A [Twilio](https://www.twilio.com) account (phone number + ConversationRelay)
- A [Google Gemini](https://aistudio.google.com) API key

### Local Development

```bash
# 1. Clone and set up environment
git clone https://github.com/andkhong/yojimbo
cd yojimbo
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure secrets
cp .env.example .env
# Edit .env with your Twilio and Gemini credentials

# 3. Initialize database
alembic upgrade head

# 4. Start the server
uvicorn app.main:app --reload --port 8000

# 5. Open dashboard
open http://localhost:8000
```

### Docker (Production)

```bash
cp .env.example .env && vi .env   # fill in real credentials
docker compose up -d              # starts app + nginx
docker compose logs -f app        # watch logs
```

Access at `http://localhost` (nginx proxies to the app on port 8000).

---

## API Reference

Interactive docs at `/docs` (Swagger UI) or `/redoc` (ReDoc) when the server is running.

### Authentication

```bash
# 1. Get tokens
curl -X POST /api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "yourpassword"}'
# → { "access_token": "...", "refresh_token": "...", "token_type": "bearer" }

# 2. Use token
curl /api/gov/summary \
  -H "Authorization: Bearer <access_token>"

# 3. Refresh
curl -X POST "/api/auth/refresh?refresh_token=<refresh_token>"
# → { "access_token": "...", "token_type": "bearer" }
```

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/gov/summary` | Operational summary (calls, appts, staff, KB) |
| `GET` | `/api/gov/compliance` | Compliance report (audit, SLA, governance) |
| `GET` | `/api/calls/live` | All active calls with transcript |
| `POST` | `/api/calls/{id}/transfer` | Transfer call to human agent |
| `POST` | `/api/calls/{id}/terminate` | End call from dashboard |
| `GET` | `/api/analytics/calls` | Call volume by period |
| `GET` | `/api/analytics/languages` | Language distribution |
| `GET` | `/api/analytics/resolution` | AI vs. escalated vs. abandoned |
| `GET` | `/api/reports/sla` | SLA compliance per department |
| `GET` | `/api/analytics/export` | Download analytics as JSON or CSV |
| `GET/POST` | `/api/knowledge` | Knowledge base CRUD |
| `GET` | `/api/knowledge/context` | AI-ready FAQ context for a department+language |
| `GET/PUT` | `/api/config/agent` | AI system prompt, greeting, escalation rules |
| `GET` | `/api/reminders/pending` | Upcoming reminders due in 24h |
| `POST` | `/api/reminders/run` | Trigger batch SMS reminders (supports dry-run) |
| `GET` | `/api/health/full` | DB + Twilio connectivity check |
| `WS` | `/ws/monitor` | Live call event stream for admin dashboard |

### WebSocket Monitor

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/monitor');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // msg.event: 'connected' | 'call_started' | 'call_ended' | 'ping'
  // msg.data: call details
  // msg.department_id: for filtering
};

// Subscribe to a specific department
ws.send(JSON.stringify({ action: 'subscribe', department_id: 3 }));
```

---

## Configuration Reference

Key environment variables (see `.env.example` for the full list):

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Session + JWT signing key (64-char hex) | Yes |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Yes |
| `TWILIO_PHONE_NUMBER` | Your Twilio phone number | Yes |
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `DATABASE_URL` | SQLite or PostgreSQL URL | Yes |
| `OFFICE_NAME` | Your city/county name | No |
| `ELEVENLABS_API_KEY` | Optional premium TTS | No |

---

## Development

```bash
# Run tests
.venv311/bin/pytest -q

# Lint
.venv311/bin/ruff check app/ tests/ --fix

# Format
.venv311/bin/ruff format app/ tests/

# Create a new DB migration
alembic revision --autogenerate -m "describe_change"

# Apply migrations
alembic upgrade head
```

### Test Coverage

```
274 tests across 16 test files:
  test_api.py                  Core MVP: departments, contacts, calls, dashboard
  test_models.py               ORM model tests
  test_ai_agent.py             AI agent unit tests
  test_ai_integration.py       Knowledge base + config injection
  test_appointment_engine.py   Booking conflict detection
  test_appointments_crud.py    Appointment CRUD + lifecycle
  test_government_platform.py  Tier 1+2+3 endpoint tests (58)
  test_platform_tier3.py       Health, export, pagination, edge cases (44)
  test_gov_dashboard.py        Gov summary + compliance
  test_auth_and_search.py      JWT auth + contact search/lookup (24)
  test_validation.py           Input validation + rate limit unit tests (33)
  test_reminders.py            Reminder service
  test_twilio_webhooks.py      Twilio webhook handlers
  test_tts_providers.py        TTS provider selection
```

---

## Architecture

```
app/
├── api/             REST endpoints (17 modules)
│   ├── calls.py     call CRUD + live monitor + transfer/terminate
│   ├── analytics.py call/appointment/language analytics + CSV export
│   ├── departments/ department CRUD + time slots + stats
│   ├── knowledge.py FAQ knowledge base
│   ├── gov_dashboard.py  operational summary + compliance
│   └── ...
├── models/          SQLAlchemy ORM models
├── schemas/         Pydantic v2 schemas (with validation)
├── services/        AI agent, appointment engine, reminders, notifications
├── ws/              WebSocket handlers (conversation, dashboard, monitor)
├── middleware/       Audit log + rate limiting
└── core/            Security (JWT, bcrypt), settings
```

### Request flow (inbound call)

```
Twilio Phone → Twilio ConversationRelay → /ws/converse (WebSocket)
  → handle_conversation_relay()
    → load departments + knowledge base (from DB)
    → load DB agent config (system_prompt, greeting_message)
    → ConversationSession (Gemini AI)
    → book appointment / answer query / escalate
    → store transcript turns to DB
    → on call end: save summary + broadcast to /ws/monitor
```

---

## Deployment Checklist

- [ ] Set `SECRET_KEY` to a random 64-char hex string
- [ ] Configure Twilio ConversationRelay webhook → `https://your-domain/ws/converse`
- [ ] Set Twilio status callback → `https://your-domain/api/twilio/status`
- [ ] Set `BASE_URL` to your public domain
- [ ] Set `DEBUG=false` in production
- [ ] Mount TLS certificates in `./ssl/` for nginx HTTPS
- [ ] Run `alembic upgrade head` before first launch
- [ ] Create first admin user via `POST /api/users`
- [ ] Seed knowledge base via `POST /api/knowledge`
- [ ] Configure department time slots via `POST /api/departments/{id}/slots/bulk`

---

## License

MIT © 2026 — built for cities that answer the phone.
