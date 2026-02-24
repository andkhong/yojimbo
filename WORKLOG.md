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

## 2026-02-23 17:18 PST — Status endpoint edge-case test coverage expansion

### Completed
- Added targeted edge/error-path tests for public status page behavior (Item #1 coverage iteration):
  - `test_public_status_high_load_threshold`
    - Verifies status flips to `high_load` when active calls exceed threshold (>50).
  - `test_public_status_db_outage_sets_service_degraded`
    - Simulates DB health-check probe failure (`SELECT 1`) and verifies:
      - overall status becomes `outage`
      - database service status is `degraded`
- Kept assertions focused on externally visible API contract (`status`, `services`, `metrics`) to harden regression detection.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **367 passed**

## 2026-02-23 17:48 PST — i18n-ready invalid-date errors for appointments list + availability

### Completed
- Improved API error handling for malformed date inputs (Item #3 iteration):
  - `GET /api/appointments` now catches invalid `target_date` values and returns HTTP 422 with structured i18n payload:
    - `message_key`: `appointments.invalid_date`
    - `params`: includes `field` and `value`
  - `GET /api/appointments/availability` now applies the same i18n-ready validation and response shape for invalid `target_date`.
- Added regression tests for both endpoints to ensure invalid-date errors stay explicit and machine-localizable.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **370 passed**

## 2026-02-23 18:19 PST — Bulk import dept-code normalization + edge-case coverage

### Completed
- Hardened bulk import department resolution (Item #1/#6 reliability iteration):
  - Updated `POST /api/appointments/import` lookup query to normalize department codes via `func.upper(Department.code)`.
  - Normalized in-memory `dept_map` keys to uppercase to match request normalization.
  - This fixes false `appointments.import.department_not_found` errors when legacy/manual data contains lowercase department codes.
- Added regression test:
  - `test_bulk_import_matches_department_code_case_insensitively`
  - Verifies import succeeds when DB has `code="lc1"` and request uses `department_code="LC1"`.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **373 passed**
