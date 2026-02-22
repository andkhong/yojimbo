# WORKLOG

## 2026-02-21 10:13 PST — Milestone 5: Latency optimization — native multilingual Gemini

### Context
Competitor analysis identified call latency as key product risk. Current architecture
made 2 Google Cloud Translation API calls per conversation turn (caller→EN, EN→caller).
Gemini 2.0 Flash natively supports 40+ languages — translation was pure overhead.

### Architecture change

**BEFORE** (4 API hops per turn):
```
STT (Twilio) → translate(caller→EN) [Google] → Gemini(EN) → translate(EN→caller) [Google] → TTS (Twilio)
```

**AFTER** (2 API hops per turn):
```
STT (Twilio) → Gemini(native caller language) → TTS (Twilio)
```

### Files changed
- `app/core/prompts.py` — Added `LANGUAGE INSTRUCTION` block to `RECEPTIONIST_SYSTEM_PROMPT`:
  Gemini explicitly instructed to respond natively in caller's language; lists the 5 top US
  immigrant languages (es/zh/vi/tl/ko) plus ar/fr/de/ja; instructs mid-call language switching.
- `app/services/ai_agent.py` — Added `ConversationSession.update_language(code)`:
  Rebuilds `system_instruction` when Twilio confirms caller's BCP-47 language on first turn.
  Idempotent (no-op if same language). Logs the language switch.
- `app/ws/conversation_relay.py` — Removed `translator` import; stripped both
  `translate_text()` calls from `prompt` event handler. Calls `session.update_language()`
  when Twilio `lang` field differs from session default. Passes raw caller text directly
  to Gemini. `ConversationTurn.translated_text` set to `None` (no longer needed).
- `tests/test_ai_agent.py` — 5 new tests: attribute update, system_instruction rebuild,
  no-op guard, all 5 immigrant languages, native-language directive present.

### Also committed (missed from prior run)
- `app/services/reminders.py` + `tests/test_reminders.py` — appointment SMS reminders
  (see Milestone 4 below).

### Results
- ✅ 52 tests passing (was 47 before this run, 35 before reminders)
- Branch `feat/latency-optimization` pushed to origin
- PR ready: https://github.com/andkhong/yojimbo/pull/new/feat/latency-optimization

### ElevenLabs TTS (deferred)
Alpha decided to evaluate after translation bottleneck is resolved. ElevenLabs requires
their SDK + a separate TTS WebSocket stream — larger architectural change, separate PR.

---

## 2026-02-21 10:11 PST — Milestone 4: Appointment reminder SMS (Twilio)

### Actions
- Implemented `app/services/reminders.py`:
  - `send_appointment_reminder(appointment_id, db)` — loads appointment + contact,
    sends SMS via Twilio, marks `reminder_sent=True`, broadcasts `reminder.sent`
    dashboard event via existing notification service.
  - `get_appointments_needing_reminders(db)` — 23-25h window, filters
    `reminder_sent=False` and `status=confirmed`.
  - `process_due_reminders(db)` — batch runner returning `{sent, failed, total}`.
  - `_send_sms(to, body)` — Twilio client wrapper; graceful fallback (returns False,
    logs warning) when credentials absent. No hardcoded secrets.
- Implemented `tests/test_reminders.py` — 12 tests covering message content,
  error paths, reminder_sent flag, window boundary filtering, batch summary.

### Results
- ✅ 47 tests passing (was 35 before this run)
- Branch: `feat/latency-optimization` (committed together with latency work)

---

## 2026-02-20 23:17 PST — Milestone 1: Repo scan + baseline

### Actions
- Inspected repo structure and tests.
- Searched for explicit TODO/FIXME markers (none in app/tests code).
- Attempted project install with editable + dev deps.
- Ran test baseline.

### Findings
- Environment constraint: host has Python 3.9.6 only; project requires Python >=3.11.
- Full install (`pip install -e ".[dev]"`) fails on python version gate.
- Best-effort dependency install under 3.9 succeeded for running tests.
- Test run fails at import-time:
  - `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`
  - source: type hints like `int | None` in models on Python 3.9.

### Current baseline
- Tests do not execute due to Python-version/type-hint incompatibility in runtime.

### Prioritized roadmap (proposed)
1. **Unblock test execution in current runtime** (high impact): make type hints 3.9-safe (use `Optional[...]` or `from __future__ import annotations`) in modules loaded by tests.
2. Run full pytest, collect functional failures.
3. Fix highest-frequency/runtime-critical failing test cluster.
4. Run lint/tests; commit cleanly.
5. Optional hardening: enforce 3.11 in CI + dev bootstrap script.

### First implementation task (proposed)
- Apply minimal compatibility patch using `from __future__ import annotations` to model modules causing import failure, then rerun pytest and address next concrete failure.

## 2026-02-20 23:50 PST — Milestone 3: Python 3.11 venv + full baseline

### Actions
- Confirmed Python 3.11.14 installed via Homebrew
- Created venv at `.venv311/` using Python 3.11
- Installed project with dev extras (`pip install -e ".[dev]"`)
- Ran full test suite

### Results
- ✅ 29 tests passed in 3.24s — clean baseline
- Python version gate: resolved
- Type-hint compat issues: resolved (native 3.11 support)

### Next actions
1. Implement highest-impact roadmap item
2. Commit clean baseline
3. Report next milestone

---

## 2026-02-20 23:40 PST — Milestone 2: Install + baseline tests re-check

### Actions
- Verified runtime Python version in venv.
- Ran editable install with dev extras.
- Ran `pytest -q --maxfail=1`.

### Findings
- Install gate confirmed: project requires Python >=3.11, host runtime is 3.9.6.
- Baseline still blocked at import-time due to PEP 604 union syntax under 3.9:
  - `app/models/appointment.py` uses `int | None`.

### Decision
- For local validation in current environment, proceed with minimal 3.9-compat type-hint patch to unblock tests.
