# Yojimbo Builder — WORKLOG

## 2026-02-23 16:22 PST — Iteration: caller preference language persistence + integration coverage ✅

### Shipped in this iteration
- Improved caller preference persistence in `app/ws/conversation_relay.py`:
  - on **new inbound calls** for an existing phone number, Yojimbo now updates `caller_preferences.preferred_language` to the latest detected setup language
  - preserves existing reconnect behavior (same `CallSid` remains idempotent for call count)
- Added integration regression coverage in `tests/test_conversation_relay_integration.py`:
  - verifies a returning caller with existing preferences gets language updated (`en -> es`) and `call_count` increments correctly on a new call
- Increased suite size from **361** to **362 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **362 passed**

---

## 2026-02-23 16:03 PST — Iteration: overnight status-page operating-hours enforcement ✅

### Shipped in this iteration
- Improved public status department availability logic in `app/api/status.py`:
  - `_dept_is_open(...)` now supports overnight operating windows (e.g. `22:00 -> 02:00`)
  - correctly handles both same-day late-night checks and previous-day spillover after midnight
  - preserves closed-state behavior when no matching window applies
- Added focused regression tests in `tests/test_new_features.py`:
  - validates overnight open state on start day (`23:30`)
  - validates post-midnight spillover open (`01:30`) and closed cutoff (`02:15`)
- Increased suite size from **359** to **361 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **361 passed**

---

## 2026-02-23 15:56 PST — Iteration: production CORS allowlist enforcement + security coverage ✅

### Shipped in this iteration
- Hardened security middleware CORS behavior in `app/middleware/security_headers.py`:
  - debug mode remains permissive for local development
  - production mode now requires explicit `CORS_ALLOWED_ORIGINS` membership
  - removed fallback behavior that unintentionally allowed all origins when allowlist was unset
- Expanded security test coverage in `tests/test_new_features.py`:
  - production allowlist permits trusted origin and blocks untrusted origin
  - production mode without configured origins omits CORS headers
  - validated HSTS header remains enabled in production responses
- Increased suite size from **357** to **359 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **359 passed**

---

## 2026-02-23 15:33 PST — Iteration: contacts API i18n-ready error payloads ✅

### Shipped in this iteration
- Improved Contacts API error responses (`app/api/contacts.py`) to be i18n-ready with structured payloads via `message_key`, `message`, and `params`.
- Added stable translation keys for common contact failure paths:
  - `contacts.lookup.not_found`
  - `contacts.not_found`
  - `contacts.merge.primary_not_found`
  - `contacts.merge.duplicate_not_found`
  - `contacts.merge.same_contact`
- Expanded coverage to enforce response contracts:
  - lookup-by-phone not-found now asserts `message_key` + `phone_number` parameter
  - merge-self invalid operation now asserts `message_key` + `contact_id` parameter
- Suite remains stable at **357 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **357 passed**

---

## 2026-02-23 15:24 PST — Iteration: reconnect/preference edge integration coverage ✅

### Shipped in this iteration
- Expanded ConversationRelay integration coverage (`tests/test_conversation_relay_integration.py`) with additional setup/reconnect edge-path tests:
  - missing/anonymous caller phone on setup still creates call state without creating `caller_preferences` rows
  - reconnect for same `CallSid` with updated language hint updates `calls.detected_language` while preserving idempotent caller preference counting
- Increased suite size from **355** to **357 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **357 passed**

---

## 2026-02-23 14:47 PST — Iteration: call-flow status/transport edge integration coverage ✅

### Shipped in this iteration
- Expanded full call-flow integration coverage (`tests/test_call_flow_integration.py`) with additional edge-path contracts:
  - unknown/unmapped Twilio `CallStatus` values are persisted raw for forward compatibility
  - invalid `CallDuration` is ignored for non-`completed` statuses (no parse crash path)
  - inbound voice TwiML now has explicit test coverage for HTTPS base URL -> `wss://` ConversationRelay URL generation
- Increased suite size from **351** to **353 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **353 passed**

---

## 2026-02-23 14:33 PST — Iteration: bulk-import time-window validation hardening ✅

### Shipped in this iteration
- Hardened bulk appointment import validation (`app/api/appointments.py`) for additional row-level error paths:
  - invalid `scheduled_end` datetime now returns structured row error (instead of bubbling a server error)
  - invalid time windows where `scheduled_end <= scheduled_start` are rejected
- Kept error responses i18n-ready with stable keys and params:
  - `appointments.import.invalid_datetime` (field-aware for `scheduled_end`)
  - `appointments.import.invalid_time_window`
- Expanded coverage in `tests/test_new_features.py` with two new tests for these edge cases.
- Increased suite size from **349** to **351 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **351 passed**

---

## 2026-02-23 14:22 PST — Iteration: Twilio call-flow edge hardening + integration coverage ✅

### Shipped in this iteration
- Hardened Twilio status callback duration parsing (`app/api/twilio_webhooks.py`):
  - completed-call `CallDuration` parsing now safely handles invalid values
  - invalid duration no longer causes a server error; defaults to `0` with warning log
- Expanded full call-flow integration coverage (`tests/test_call_flow_integration.py`):
  - added outbound voice webhook TwiML contract test (`/api/twilio/voice/outbound`)
  - added status-callback invalid-duration error-path test ensuring graceful `204` + persisted safe default
- Increased suite size from **347** to **349 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **349 passed**

---

## 2026-02-23 14:04 PST — Iteration: bulk-import i18n-ready row errors + contract coverage ✅

### Shipped in this iteration
- Improved bulk appointment import error payloads (`app/api/appointments.py`) to be **i18n-ready per row** via structured fields:
  - `message_key`
  - `message`
  - `params`
- Added dedicated row-level translation keys:
  - `appointments.import.contact_not_found`
  - `appointments.import.department_not_found`
  - `appointments.import.invalid_datetime`
- Expanded import error-path tests (`tests/test_new_features.py`) to validate payload contracts and keys across unknown-contact, unknown-department, invalid-datetime, and mixed-result scenarios.
- Test suite remains stable at **347 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **347 passed**

---

## 2026-02-23 13:49 PST — Iteration: operating-hours overnight enforcement edge cases ✅

### Shipped in this iteration
- Hardened department operating-hours enforcement (`app/services/appointment_engine.py`) for **overnight windows** where `close <= open` (e.g. `22:00 -> 02:00`).
- Validation now uses datetime windows (not just wall-clock times), correctly handling bookings that cross midnight.
- Added new edge-case tests in `tests/test_new_features.py`:
  - allows valid cross-midnight booking inside overnight window
  - rejects booking ending after overnight close time
- Increased suite size from 345 to **347 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **347 passed**

---

## 2026-02-23 13:32 PST — Iteration: pagination validation/error-path coverage expansion ✅

### Shipped in this iteration
- Expanded pagination error-path coverage in `tests/test_platform_tier3.py` with new parameterized tests across all paginated list APIs:
  - reject invalid `page=0` for:
    - `/api/calls`, `/api/contacts`, `/api/users`, `/api/knowledge`, `/api/audit-logs`, `/api/appointments`, `/api/messages`
  - reject `per_page` above endpoint max bounds (100/200 depending on API)
- Added **14 new assertions** for boundary validation behavior and consistent `422` responses.
- Increased suite size from 331 to **345 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **345 passed**

---

## 2026-02-23 13:24 PST — Iteration: i18n-ready appointment errors + conflict/not-found coverage ✅

### Shipped in this iteration
- Improved appointment API error responses (`app/api/appointments.py`) to be **i18n-ready** with structured payloads:
  - `appointments.outside_operating_hours` (422)
  - `appointments.booking_conflict` (409)
  - `appointments.not_found` (404 on GET/PATCH/DELETE)
  - standardized payload shape: `{message_key, message, params}`
- Expanded feature tests (`tests/test_new_features.py`):
  - out-of-hours booking now validates structured `message_key`
  - appointment not-found payload contract across GET/PATCH/DELETE
  - booking-conflict payload contract validation
- Increased suite size from 329 to **331 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **331 passed**

---

## 2026-02-23 13:06 PST — Iteration: additional monitor reconnect edge-case coverage ✅

### Shipped in this iteration
- Expanded WebSocket monitor test coverage (`tests/test_recordings_and_monitor.py`) with reconnect/error-path edge cases:
  - replay buffer max-length behavior validation (drops oldest events as buffer fills)
  - invalid `last_event_id` query parameter handling during reconnect (graceful connect, no replay)
- Increased suite size from 327 to **329 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **329 passed**

---

## 2026-02-23 12:52 PST — Iteration: monitor WS replay on reconnect ✅

### Shipped in this iteration
- Added **WebSocket reconnection replay support** for `/ws/monitor` (`app/ws/monitor.py`):
  - process-local replay buffer of recent monitor events (max 500)
  - monotonic `event_id` attached to each broadcast call event
  - reconnect resume via `?last_event_id=<n>` query parameter
  - best-effort replay of missed events immediately after connect
- Added monitor replay tests (`tests/test_recordings_and_monitor.py`):
  - monotonic `event_id` generation validation
  - `_events_since(...)` filtering behavior validation
- Increased suite size from 325 to **327 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **327 passed**

---

## 2026-02-23 12:34 PST — Iteration: i18n-ready preference errors + extra coverage ✅

### Shipped in this iteration
- Improved caller preference not-found API errors (`app/api/caller_preferences.py`) to be **i18n-ready** with structured payload:
  - `message_key` (stable translation key)
  - `message` (current English fallback)
  - `params` (template params, e.g. `phone_number`)
- Added focused regression/contract tests (`tests/test_new_features.py`):
  - not-found payload shape assertions for `GET/DELETE /api/preferences/{phone}`
  - increment-call behavior preserves existing caller preference fields
  - cross-endpoint consistency check for shared error contract
- Increased suite size from 323 to **325 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **325 passed**

---

## 2026-02-23 12:23 PST — Iteration: WebSocket reconnection hardening ✅

### Shipped in this iteration
- Hardened dashboard WebSocket client reconnection logic (`app/static/js/dashboard.js`):
  - exponential backoff + jitter reconnect scheduling (caps at 30s)
  - heartbeat ping loop with stale-connection detection and forced reconnect
  - reconnect-at-focus behavior when browser tab resumes and socket is closed
  - reconnect attempt counter reset on successful connect

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **323 passed**

---

## 2026-02-23 12:19 PST — Iteration: full call-flow integration tests ✅

### Shipped in this iteration
- Added **end-to-end call flow integration tests** (`tests/test_call_flow_integration.py`):
  - outbound call initiation (`POST /api/calls/outbound`) with Twilio client mocked
  - Twilio status progression (`in-progress` -> `completed`) and duration persistence checks
  - inbound voice TwiML validation (`POST /api/twilio/voice`) for ConversationRelay wiring
  - unknown CallSid callback noop validation (`POST /api/twilio/status`)
- Increased total test count from 320 to **323**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **323 passed**

---

## 2026-02-23 12:10 PST — Iteration: hardening + coverage to 320 ✅

### Shipped in this iteration
- Added/finished **caller preferences API** (`/api/preferences/{phone}` CRUD + increment-call)
- Added **public status endpoints** (`/api/status`, `/api/status/ping`) with no auth
- Added **security middleware** for CSP/CORS-aligned headers
- Added **DB performance indexes** migration (`bf5cfbb6a13b_add_performance_indexes.py`)
- Added/expanded **operating-hours enforcement** support (structured format) with legacy-format compatibility
- Expanded test suite with edge/error/bulk-import coverage

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **320 passed**

---

## 2026-02-21 22:53 PST — ALL ROADMAP ITEMS COMPLETE ✅

### Current state
- **Branch:** `feat/government-platform`
- **Tests:** 197 passing (was 29 at MVP baseline)
- **Budget spent:** CORRECTED: $35 spent / $99 total | $64 remaining | halt at $20 remaining
- **PR:** https://github.com/andkhong/yojimbo/pull/4 (merged to main via PR)

---

### Full feature inventory shipped

#### TIER 1 — Core Platform ✅
| # | Feature | Endpoint(s) | Status |
|---|---------|-------------|--------|
| 1 | Department Management | `GET/POST/PUT/PATCH/DELETE /api/departments` + stats + phone assignment + staff | ✅ |
| 2 | AI Agent Configuration | `GET/PUT /api/config/agent`, `/api/config/languages`, `/api/config/twilio` | ✅ |
| 3 | Audit Log System | `GET /api/audit-logs` + summary + middleware auto-log | ✅ |
| 4 | Staff Management | `GET/POST/PATCH/DELETE /api/users` + activate + role filter | ✅ |
| 5 | Live Call Monitor | `GET /api/calls/live` + transfer + terminate + `/ws/monitor` WebSocket | ✅ |

#### TIER 2 — Analytics & Reporting ✅
| # | Feature | Endpoint(s) | Status |
|---|---------|-------------|--------|
| 6 | Call Analytics | volume, languages, resolution, departments, peak-hours | ✅ |
| 7 | Appointment Analytics | booking rates, no-shows, reminder effectiveness | ✅ |
| 8 | SLA Reporting | `/api/reports/sla` per-department + overall | ✅ |

#### TIER 3 — Knowledge Base & Enhancements ✅
| # | Feature | Endpoint(s) | Status |
|---|---------|-------------|--------|
| 9  | Knowledge Base | `GET/POST/PATCH/DELETE /api/knowledge` + context endpoint | ✅ |
| 10 | Contact Enhancements | history, merge duplicates, tags | ✅ |
| 11 | Reminder Cron | pending, run (dry-run supported), history | ✅ |
| 12 | Time Slot Management | CRUD + bulk generate + availability check | ✅ |

#### BONUS — Beyond Roadmap ✅
| Feature | Details |
|---------|---------|
| Health Checks | `/api/health`, `/api/health/db`, `/api/health/twilio`, `/api/health/full` |
| Analytics Export | `/api/analytics/export?format=json\|csv` |
| WebSocket Monitor | `/ws/monitor` — live call event broadcasts |
| Audit Middleware | Auto-logs all `POST/PUT/PATCH/DELETE /api/*` to audit_logs table |
| AI Knowledge Injection | Knowledge base FAQ entries injected into Gemini system prompt per call |
| DB Agent Config | `system_prompt`, `greeting_message` from DB override defaults at call start |
| Call Transcript Storage | Full conversation history saved to `Call.summary` on call end |
| Gov Dashboard | `/api/gov/summary` + `/api/gov/compliance` — operational + audit overview |

---

### Architecture reference

```
app/
  api/          — REST endpoints (17 modules)
  models/       — SQLAlchemy ORM models
  schemas/      — Pydantic schemas
  services/     — Business logic (AI agent, notifications, reminders)
  ws/           — WebSocket handlers (conversation relay, dashboard, monitor)
  middleware/   — Audit log middleware
  core/         — Security, constants, prompts
tests/
  test_api.py                  — Core MVP API tests
  test_models.py               — ORM model tests
  test_ai_agent.py             — AI agent unit tests
  test_ai_integration.py       — AI+knowledge+config integration tests
  test_appointment_engine.py   — Appointment booking logic
  test_government_platform.py  — Tier 1+2+3 endpoint tests (58 tests)
  test_platform_tier3.py       — Health, export, pagination, edge cases (44 tests)
  test_gov_dashboard.py        — Gov summary + compliance (10 tests)
  test_reminders.py            — Reminder service tests
  test_tts_providers.py        — TTS provider tests
  test_twilio_webhooks.py      — Twilio webhook handler tests
```

### Commands
```bash
.venv311/bin/pytest -q                        # run all tests
.venv311/bin/ruff check app/ tests/ --fix     # lint
git push origin feat/government-platform      # push branch
```

---

## NEXT ACTIONS (if continuing)

Low priority polish (all major features done):
1. Alembic migrations — formalize DB schema versioning
2. Rate limiting middleware on public webhook endpoints
3. More appointment CRUD tests (create, patch, cancel)
4. Messages endpoint tests
5. Integration test: full call lifecycle (setup → turns → end → transcript stored)
6. Docker compose for production deploy
7. CI/CD workflow (GitHub Actions: test + lint on PR)

---

## Prior sessions (summarized)

| Date | Milestone | Tests | Notes |
|------|-----------|-------|-------|
| 2026-02-20 23:17 | Repo scan + baseline | 0 | Python 3.9 compat issue |
| 2026-02-20 23:40 | Install check | 0 | Confirmed 3.11 needed |
| 2026-02-20 23:50 | Python 3.11 venv + baseline | 29 | Clean baseline |
| 2026-02-21 10:11 | Appointment reminder SMS | 47 | Twilio SMS reminders |
| 2026-02-21 10:13 | Latency opt (remove translation) | 52 | Native Gemini multilingual |
| 2026-02-21 22:33 | Tier 1+2 government platform | 87 | 8 core endpoints |
| 2026-02-21 22:38 | Tier 3 + edge cases | 131 | Health, export, monitor |
| 2026-02-21 22:47 | AI integration | 146 | Knowledge+config injection |
| 2026-02-21 22:50 | Gov dashboard + compliance | 156 | /api/gov/* endpoints |
| 2026-02-21 22:53 | Merge + lint fix | 197 | All items complete ✅ |

## 2026-02-23 15:05 PST — WebSocket reconnection hardening + full relay integration tests

### Completed
- **WebSocket reconnection handling (server-side, Item #10 iteration):**
  - Updated `app/ws/conversation_relay.py::_handle_setup` to be **CallSid idempotent**.
  - If Twilio reconnects with the same `callSid`, we now reuse the existing `Call` row instead of creating duplicates.
  - `call_started` notifications/broadcasts are emitted only for truly new calls.
- **Caller preference storage per phone number (Item #5 integration polish):**
  - On first setup for a new inbound call, increment `caller_preferences.call_count` and set `last_call_at`.
  - Reconnects for the same CallSid do **not** double-increment.
- **Integration tests for full call flow (Item #2):**
  - Added `tests/test_conversation_relay_integration.py` with coverage for:
    - setup reconnect idempotency (no duplicate call row, no double count)
    - setup → prompt → disconnect flow
    - call completion + transcript summary persistence
    - response token emission to ConversationRelay client

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **355 passed**


## 2026-02-23 16:32 PST — i18n-ready operating-hours errors (structured keys + params)

### Completed
- Enhanced `OutsideOperatingHoursError` with i18n metadata:
  - Added `message_key` and `params` fields while preserving readable fallback text.
  - Introduced granular keys:
    - `appointments.operating_hours.before_open`
    - `appointments.operating_hours.after_close`
    - `appointments.operating_hours.closed_day`
- Updated appointment API error handling (`POST /api/appointments`) to surface these structured keys/params directly in `detail` payloads.
- Expanded tests to validate structured metadata for operating-hours failures (service-level + API-level assertions).

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **362 passed**
