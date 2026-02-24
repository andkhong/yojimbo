## 2026-02-24 09:24 PST — CSP directive hardening (objects/forms/mixed-content) ✅

### Shipped in this iteration
- Hardened default CSP in `app/middleware/security_headers.py` by adding:
  - `form-action 'self'`
  - `object-src 'none'`
  - `block-all-mixed-content`
- Added regression coverage in `tests/test_new_features.py`:
  - `test_security_headers_csp_denies_objects_and_limits_forms`
- Kept scope focused to CSP policy tightening only (no CORS behavior changes).

### Validation
- `.venv311/bin/ruff format app/ tests/` ✅
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **412 passed**

---

## 2026-02-23 23:12 PST — Monitor WebSocket reconnect cursor-ahead handling + coverage ✅

### Shipped in this iteration
- Hardened monitor reconnect behavior in `app/ws/monitor.py` for out-of-range forward cursors:
  - when `last_event_id` is **ahead** of the server replay head, the socket now emits a structured `replay_cursor_ahead` event
  - payload includes:
    - `requested_last_event_id`
    - `newest_available_event_id`
    - `reason: cursor_ahead_of_server`
  - replay behavior remains safe/idempotent (no phantom event replay)
- Added regression coverage in `tests/test_recordings_and_monitor.py`:
  - `test_monitor_ws_replay_cursor_ahead_emitted_when_cursor_exceeds_server_head`
- Increased suite size from **410** to **411 passing tests**.

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **411 passed**

---

## 2026-02-23 22:57 PST — Twilio status normalization integration coverage expansion ✅

### Shipped in this iteration
- Added a new parametrized integration test to harden full call-status callback mapping coverage in `tests/test_call_flow_integration.py`:
  - `test_status_callback_known_twilio_statuses_are_normalized`
  - validates Twilio → internal status normalization for:
    - `busy -> busy`
    - `no-answer -> no_answer`
    - `canceled -> cancelled`
    - `failed -> failed`
    - `in-progress -> in_progress`
- This closes an edge-case gap where callback status mapping logic existed but lacked explicit regression coverage for all known mapped statuses.
- Increased suite size from **405** to **410 passing tests**.

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **410 passed**

---

## 2026-02-23 22:40 PST — Agent config i18n-ready error contracts + coverage ✅

### Shipped in this iteration
- Improved `app/api/agent_config.py` error payload contracts to be i18n-ready using structured `detail` objects (`message_key`, `message`, `params`):
  - `agent_config.invalid_key` for `GET /api/config/agent/{key}` invalid-key validation (400)
  - `agent_config.key_not_set` for missing key lookups/deletes (404)
- Added focused regression tests in `tests/test_agent_config_i18n_errors.py`:
  - `test_get_config_invalid_key_is_i18n_ready`
  - `test_get_config_missing_key_is_i18n_ready`
  - `test_delete_config_missing_key_is_i18n_ready`
- Increased suite size from **402** to **405 passing tests**.

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **405 passed**

---

## 2026-02-23 22:26 PST — Knowledge + audit-log i18n-ready not-found errors ✅

### Shipped in this iteration
- Expanded i18n-ready error contracts for additional APIs:
  - `app/api/knowledge.py`
    - added `_localized_error(...)` helper
    - converted not-found paths on `GET/PATCH/DELETE/restore /api/knowledge/{entry_id}`
    - stable key: `knowledge.not_found` with `params.entry_id`
  - `app/api/audit_logs.py`
    - added `_localized_error(...)` helper
    - converted `GET /api/audit-logs/{log_id}` not-found response
    - stable key: `audit_logs.not_found` with `params.log_id`
- Added focused contract tests in `tests/test_knowledge_and_audit_i18n_errors.py`:
  - `test_get_knowledge_not_found_error_is_i18n_ready`
  - `test_get_audit_log_not_found_error_is_i18n_ready`
- Increased suite size from **400** to **402 passing tests**.

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **402 passed**

---

## 2026-02-23 21:54 PST — Bulk-import duplicate conflict i18n contract (skip_duplicates=false) ✅

### Shipped in this iteration
- Hardened `POST /api/appointments/import` duplicate handling in `app/api/appointments.py`:
  - duplicate confirmed appointments are now always detected per row
  - when `skip_duplicates=true`, behavior is unchanged (row is listed in `skipped_rows`)
  - when `skip_duplicates=false`, row now returns structured i18n-ready error payload in `error_rows` with:
    - `message_key`: `appointments.import.duplicate`
    - params including `existing_id`, `contact_phone`, `department_code`, `scheduled_start`
- Updated regression coverage in `tests/test_new_features.py`:
  - replaced permissive duplicate insert assertion with strict duplicate-error contract test
- Suite remains stable at **397 passing tests** with stronger bulk-import error-path coverage.

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **397 passed**

---

## 2026-02-23 21:36 PST — Bulk-import empty-payload i18n error contract + coverage ✅

### Shipped in this iteration
- Improved bulk appointment import validation in `app/api/appointments.py`:
  - `POST /api/appointments/import` now rejects empty `appointments` arrays with HTTP 422
  - returns i18n-ready structured `detail` payload:
    - `message_key`: `appointments.import.empty`
    - `params.field`: `appointments`
- Added regression coverage in `tests/test_new_features.py`:
  - `test_bulk_import_empty_payload_is_i18n_ready`
- Increased suite size from **396** to **397 passing tests**.

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **397 passed**

---

## 2026-02-23 21:19 PST — Iteration: auth i18n-ready error contracts + refresh edge coverage ✅

### Shipped in this iteration
- Improved auth error payloads in `app/api/dashboard.py` to be i18n-ready with structured `detail` objects (`message_key`, `message`, `params`) for key failure paths:
  - `auth.invalid_credentials` on `/api/auth/login` and `/api/auth/token`
  - `auth.refresh.invalid_token_type` on `/api/auth/refresh` when an access token is provided
  - `auth.refresh.user_not_active` when refresh subject no longer maps to an active user
- Expanded auth integration tests in `tests/test_auth_and_search.py`:
  - wrong-password login now asserts i18n error contract and username parameter
  - refresh-with-access-token now asserts token-type error key/params
  - added inactive-user refresh-path test to verify structured payload contract
- Increased suite size from **395** to **396 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **396 passed**

---

# Yojimbo Builder — WORKLOG

## 2026-02-23 20:18 PST — Iteration: ConversationRelay invalid setup reconnect-guard + integration coverage ✅

### Shipped in this iteration
- Hardened WebSocket setup handling in `app/ws/conversation_relay.py`:
  - `_handle_setup(...)` now treats missing/empty `callSid` as invalid setup and safely no-ops
  - avoids creating/overwriting `Call` rows under empty SID values on malformed reconnect/setup payloads
- Expanded reconnection/error-path integration coverage in `tests/test_conversation_relay_integration.py`:
  - `test_handle_setup_without_callsid_is_noop`
  - `test_conversation_relay_missing_callsid_drops_subsequent_prompt`
- Increased suite size from **387** to **389 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **389 passed**

---

## 2026-02-23 20:08 PST — Iteration: outbound HTTPS TwiML transport parity integration coverage ✅

### Shipped in this iteration
- Expanded full call-flow integration coverage in `tests/test_call_flow_integration.py`:
  - added `test_outbound_voice_uses_wss_when_base_url_is_https`
  - verifies `POST /api/twilio/voice/outbound` emits secure `wss://` ConversationRelay URL when `settings.base_url` is HTTPS
- This closes a transport-parity gap where inbound HTTPS TwiML was covered, but outbound HTTPS TwiML was not.
- Increased suite size from **386** to **387 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **387 passed**

---

## 2026-02-23 19:26 PST — Iteration: users API i18n-ready error contracts + coverage expansion ✅

### Shipped in this iteration
- Improved `app/api/users.py` error responses to use i18n-ready structured payloads (`message_key`, `message`, `params`) for common failure paths:
  - `users.invalid_role` (create/update/by-role)
  - `users.username_taken` (duplicate username)
  - `users.not_found` (get/patch/delete/activate)
  - `users.last_admin_deactivate_forbidden` (last active admin guard)
- Added dedicated regression tests in `tests/test_users_i18n_errors.py`:
  - duplicate username contract
  - not-found payload contract
  - last-admin deactivate guard payload contract
  - invalid role payload contract for `/api/users/by-role/{role}`
- Increased suite size from **378** to **382 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **382 passed**

---

## 2026-02-23 19:08 PST — Iteration: CORS cache correctness hardening + security coverage ✅

### Shipped in this iteration
- Hardened CORS middleware cache behavior in `app/middleware/security_headers.py`:
  - allowed-origin responses now include `Vary: Origin`
  - prevents shared caches from reusing a CORS-allowed response across different origins
- Expanded security/CORS edge-case coverage in `tests/test_new_features.py`:
  - `test_cors_sets_vary_origin_for_allowed_origin`
  - `test_non_cors_request_has_no_vary_origin`
- Increased suite size from **376** to **378 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **378 passed**

---

## 2026-02-23 18:48 PST — Iteration: monitor WebSocket replay-window reconnect hardening ✅

### Shipped in this iteration
- Hardened monitor reconnect behavior in `app/ws/monitor.py`:
  - added replay window introspection helper to track oldest/newest buffered `event_id`
  - clamped negative `last_event_id` query params to `0` (fresh connect semantics)
  - when a reconnect cursor falls outside retained history, server now emits a structured `replay_reset` event before replaying available events
- Expanded monitor reconnection tests in `tests/test_recordings_and_monitor.py`:
  - `test_monitor_ws_negative_last_event_id_clamps_to_zero`
  - `test_monitor_ws_replay_reset_emitted_when_cursor_is_too_old`
- Increased suite size from **374** to **376 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **376 passed**

---

## 2026-02-23 18:03 PST — Iteration: reconnect caller-preference backfill hardening + integration coverage ✅

### Shipped in this iteration
- Improved ConversationRelay reconnect handling in `app/ws/conversation_relay.py`:
  - when an existing `CallSid` reconnects with a caller phone number that was previously missing, we now backfill `caller_preferences` for that phone
  - preserves idempotency by **not** double-incrementing counts on reconnect for existing preferences
  - still updates `preferred_language` on reconnect language hints
- Added integration coverage in `tests/test_conversation_relay_integration.py`:
  - `test_reconnect_with_late_phone_backfills_preference_once`
  - `test_reconnect_with_existing_pref_updates_language_without_count_bump`
- Increased suite size from **370** to **372 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **372 passed**

---

## 2026-02-23 17:31 PST — Iteration: bulk-import operating-hours enforcement + coverage ✅

### Shipped in this iteration
- Extended bulk appointment import validation in `app/api/appointments.py` to enforce **structured department operating-hours** per row:
  - applies `appointment_engine.check_operating_hours(...)` during `/api/appointments/import`
  - rejects out-of-hours rows with existing i18n-ready operating-hours keys/params (e.g. `appointments.operating_hours.before_open`)
  - preserves row-level partial success behavior (errors are returned in `error_rows` without 500s)
- Added focused regression coverage in `tests/test_new_features.py`:
  - `test_bulk_import_enforces_operating_hours`
  - validates import rejects out-of-hours rows and returns structured `message_key` + `params.day`
- Increased suite size from **367** to **368 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **368 passed**

---

## 2026-02-23 17:08 PST — Iteration: inbound call-flow stateless webhook integration coverage ✅

### Shipped in this iteration
- Expanded full call-flow integration coverage in `tests/test_call_flow_integration.py`:
  - added `test_inbound_voice_webhook_is_stateless_until_relay_setup`
  - verifies `/api/twilio/voice` remains transport/TwiML-only and does **not** prematurely persist a `Call` row before ConversationRelay setup
  - verifies follow-up `/api/twilio/status` for that unknown SID safely remains a no-op (`204`), protecting webhook robustness under out-of-order callbacks
- Increased suite size from **364** to **365 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **365 passed**

---

## 2026-02-23 16:49 PST — Iteration: outbound SMS error contract hardening + integration tests ✅

### Shipped in this iteration
- Hardened outbound SMS API failure behavior in `app/api/messages.py`:
  - replaced ad-hoc `{error: ...}` success-200 fallback with proper `HTTP 502`
  - added i18n-ready structured error payload contract on failure:
    - `message_key`: `messages.send.failed`
    - `message`: English fallback
    - `params.reason`: upstream Twilio/client exception string
  - added server-side exception logging for easier production diagnostics
- Expanded endpoint coverage in `tests/test_appointments_crud.py`:
  - added success-path test for `POST /api/messages/send` with fake Twilio client
  - added failure-path contract test asserting `502` + structured `detail` payload
- Increased suite size from **362** to **364 passing tests**.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **364 passed**

---

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

## 2026-02-23 18:36 PST — SMS send configuration guardrails + i18n-ready error payload

### Completed
- Improved outbound SMS endpoint error handling (Item #3 iteration):
  - Added explicit Twilio configuration validation in `POST /api/messages/send`.
  - Endpoint now returns HTTP 503 with structured i18n detail when required settings are missing:
    - `message_key`: `messages.send.not_configured`
    - `params.missing_fields`: one or more of `twilio_account_sid`, `twilio_auth_token`, `twilio_phone_number`
  - Existing downstream failure path remains HTTP 502 with:
    - `message_key`: `messages.send.failed`
- Expanded message endpoint tests:
  - Added `test_send_sms_not_configured_is_i18n_ready`
  - Updated success/failure Twilio tests to explicitly patch configured credentials before exercising provider behavior.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **374 passed**

## 2026-02-23 19:49 PST — High-traffic DB index expansion (SMS feeds + slot lookup)

### Completed
- Implemented additional performance indexes for Item #8 (DB indexes):
  - `sms_messages`
    - `ix_sms_created` on `(created_at)` for newest-first global message feeds.
    - `ix_sms_contact_created` on `(contact_id, created_at)` for per-contact threaded history.
    - `ix_sms_dept_created` on `(department_id, created_at)` for department-level inbox filtering.
  - `time_slots`
    - `ix_time_slots_lookup` on `(department_id, day_of_week, is_active, start_time)` to accelerate department availability lookups and ordered slot scans.
- Added Alembic migration:
  - `9a7e1c2d4f10_add_sms_and_timeslot_indexes.py`
- Added schema contract tests in `tests/test_new_features.py` to assert these indexes remain declared:
  - `test_sms_message_model_declares_high_traffic_indexes`
  - `test_time_slot_model_declares_lookup_index`

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **384 passed**

## 2026-02-23 19:49 PST — CORS normalization hardening + cache-safe Vary merge

### Completed
- Strengthened CORS allowlist matching in `SecurityHeadersMiddleware` (Item #9 iteration):
  - Added origin normalization utility for both config allowlist entries and incoming `Origin` headers.
  - Matching now tolerates common real-world variants without loosening policy:
    - case differences in scheme/host
    - trailing slash in configured origins
    - explicit default ports (`:80`, `:443`)
  - Still enforces exact scheme+host(+non-default-port) in production.
- Improved response cache safety when CORS applies:
  - `Vary` header now appends `Origin` without clobbering existing `Vary` values.
- Added focused regression tests:
  - `test_cors_allowlist_matches_case_and_default_port_variants`
  - `test_cors_appends_origin_to_existing_vary_header`

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **386 passed**

## 2026-02-23 20:33 PST — Full call-flow integration test for caller preference persistence

### Completed
- Expanded Item #2 (integration tests for full call flow) with a cross-endpoint integration scenario in `tests/test_call_flow_integration.py`:
  - Added `test_outbound_call_flow_can_track_returning_caller_preference`.
  - Flow now validates, end-to-end:
    1. Seed caller preference via `PUT /api/preferences/{phone}`
    2. Create outbound call via `POST /api/calls/outbound`
    3. Complete call via `POST /api/twilio/status`
    4. Record returning-caller activity via `POST /api/preferences/{phone}/increment-call`
    5. Confirm preference profile fields remain intact while `call_count` increments.
    6. Confirm persisted DB state for both `Call` and `CallerPreference` rows.
- Added direct DB assertions to verify durable persistence beyond API response payloads.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **390 passed**

## 2026-02-23 20:51 PST — Dashboard WebSocket server heartbeat hardening (reconnection support)

### Completed
- Expanded Item #10 (WebSocket reconnection handling) on the **server side** for dashboard clients:
  - Added periodic server-originated heartbeat pings in `app/ws/dashboard.py` via `_ping_loop`.
  - `handle_dashboard_ws` now starts/stops a ping task per connection and cancels it cleanly on exit.
  - Added explicit handling for client-side `pong` messages (no-op today, forward-compatible for future last-seen tracking).
  - Preserved existing `ping -> pong` response behavior for backward compatibility.
- Added focused tests in `tests/test_dashboard_ws.py`:
  - `test_dashboard_ws_handles_ping_and_invalid_json`
  - `test_dashboard_ws_disconnects_manager_on_socket_disconnect`
- Net effect: dashboard clients can now rely on both **client-originated** and **server-originated** heartbeat signals to detect stale connections and trigger reconnect logic faster.

### Validation
- `ruff check app/ tests/ --fix` ✅
- `pytest -q` ✅ **392 passed**

## 2026-02-23 21:04 PST — Departments API i18n-ready error payloads (Item #3 iteration)

### Completed
- Expanded i18n-ready error detail coverage in `app/api/departments.py`:
  - Added `_localized_error(...)` helper for structured error payloads.
  - Converted key string-only errors to structured `detail` objects with `message_key`, `message`, and `params`:
    - `departments.not_found` (all major department lookup paths)
    - `departments.conflict.code_or_name_exists`
    - `departments.phone_number.already_assigned`
    - `departments.time_slot.not_found`
    - `departments.time_slot.invalid_day_of_week`
    - `departments.availability.invalid_date_format`
- Added focused regression tests in `tests/test_departments_i18n_errors.py`:
  - `test_department_not_found_error_is_i18n_ready`
  - `test_bulk_slot_invalid_day_error_is_i18n_ready`
  - `test_slot_availability_invalid_date_error_is_i18n_ready`

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **395 passed**

## 2026-02-23 22:04 PST — Calls API i18n-ready error payloads (Item #3 iteration)

### Completed
- Expanded Item #3 by converting key `app/api/calls.py` errors from plain strings into structured i18n-ready payloads.
- Added `_localized_error(message_key, message, **params)` helper and applied it to:
  - `calls.not_found` for call lookups (`GET /api/calls/{id}`, transfer, recording GET/PUT, terminate)
  - `calls.transfer.invalid_status` with `status` and `allowed_statuses` params
  - `calls.terminate.invalid_status` with `status` and `allowed_statuses` params
- Added focused contract tests in `tests/test_calls_i18n_errors.py`:
  - `test_get_call_not_found_error_is_i18n_ready`
  - `test_transfer_invalid_status_error_is_i18n_ready`
  - `test_terminate_invalid_status_error_is_i18n_ready`

### Validation
- `.venv311/bin/ruff check app/ tests/ --fix` ✅
- `.venv311/bin/pytest -q` ✅ **400 passed**
