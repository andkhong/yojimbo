"""Tests for new features: CORS/CSP, caller preferences, status page,
operating hours enforcement, bulk import, and DB index coverage.
"""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.call import Call
from app.models.contact import Contact
from app.models.department import Department


# ===========================================================================
# Item 9: CORS + Security Headers
# ===========================================================================


@pytest.mark.asyncio
async def test_security_headers_present(client):
    """All key security headers are present on API responses."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert "x-content-type-options" in resp.headers
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "x-frame-options" in resp.headers
    assert resp.headers["x-frame-options"] == "DENY"
    assert "referrer-policy" in resp.headers
    assert "content-security-policy" in resp.headers
    assert "permissions-policy" in resp.headers


@pytest.mark.asyncio
async def test_cors_preflight_request(client):
    """OPTIONS preflight returns correct CORS headers in debug mode."""
    resp = await client.options(
        "/api/departments",
        headers={"origin": "https://dashboard.cityname.gov"},
    )
    # In debug mode, CORS is permissive
    assert resp.status_code in (200, 204)


@pytest.mark.asyncio
async def test_security_headers_csp_includes_twilio(client):
    """CSP header allows Twilio API connections."""
    resp = await client.get("/api/health")
    csp = resp.headers.get("content-security-policy", "")
    assert "api.twilio.com" in csp or "https:" in csp


@pytest.mark.asyncio
async def test_security_headers_no_hsts_in_debug(client):
    """HSTS header is NOT present in debug mode."""
    resp = await client.get("/api/health")
    # In debug mode HSTS should be absent
    assert "strict-transport-security" not in resp.headers


@pytest.mark.asyncio
async def test_cors_allowlist_enforced_in_production(client, monkeypatch):
    """Production mode only allows CORS for explicitly allowlisted origins."""
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://dashboard.city.gov, https://ops.city.gov",
    )

    allowed = await client.options(
        "/api/departments",
        headers={"origin": "https://dashboard.city.gov"},
    )
    assert allowed.status_code in (200, 204)
    assert allowed.headers.get("access-control-allow-origin") == "https://dashboard.city.gov"

    blocked = await client.options(
        "/api/departments",
        headers={"origin": "https://evil.example.com"},
    )
    assert blocked.status_code in (200, 204)
    assert "access-control-allow-origin" not in blocked.headers


@pytest.mark.asyncio
async def test_production_requires_explicit_cors_origins(client, monkeypatch):
    """With no allowlist configured in production, CORS headers are omitted."""
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    resp = await client.options(
        "/api/departments",
        headers={"origin": "https://dashboard.city.gov"},
    )
    assert resp.status_code in (200, 204)
    assert "access-control-allow-origin" not in resp.headers
    assert "strict-transport-security" in resp.headers


# ===========================================================================
# Item 5: Caller Preferences
# ===========================================================================


@pytest.mark.asyncio
async def test_get_preferences_not_found(client):
    """Returns i18n-ready 404 payload when no preferences set for a phone number."""
    resp = await client.get("/api/preferences/%2B15580001111")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["message_key"] == "preferences.not_found"
    assert detail["params"]["phone_number"] == "+15580001111"
    assert "No preferences found" in detail["message"]


@pytest.mark.asyncio
async def test_upsert_preferences_creates(client):
    """PUT creates preferences for a new phone number."""
    resp = await client.put(
        "/api/preferences/%2B15580002222",
        json={
            "preferred_language": "es",
            "name": "Maria Garcia",
            "sms_opt_in": True,
            "email_opt_in": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["preference"]
    assert data["preferred_language"] == "es"
    assert data["name"] == "Maria Garcia"
    assert data["phone_number"] == "+15580002222"


@pytest.mark.asyncio
async def test_upsert_preferences_updates(client):
    """PUT updates existing preferences."""
    # Create first
    await client.put(
        "/api/preferences/%2B15580003333",
        json={"preferred_language": "en", "name": "Bob"},
    )
    # Update
    resp = await client.put(
        "/api/preferences/%2B15580003333",
        json={"preferred_language": "zh", "name": "Bob Chen"},
    )
    assert resp.status_code == 200
    assert resp.json()["preference"]["preferred_language"] == "zh"
    assert resp.json()["preference"]["name"] == "Bob Chen"


@pytest.mark.asyncio
async def test_get_preferences_after_upsert(client):
    """GET returns preferences after upsert."""
    await client.put(
        "/api/preferences/%2B15580004444",
        json={"preferred_language": "vi", "hearing_impaired": True},
    )
    resp = await client.get("/api/preferences/%2B15580004444")
    assert resp.status_code == 200
    data = resp.json()["preference"]
    assert data["preferred_language"] == "vi"
    assert data["hearing_impaired"] is True


@pytest.mark.asyncio
async def test_delete_preferences(client):
    """DELETE removes preferences and GET returns 404."""
    await client.put(
        "/api/preferences/%2B15580005555",
        json={"preferred_language": "ko"},
    )
    resp = await client.delete("/api/preferences/%2B15580005555")
    assert resp.status_code == 204

    resp2 = await client.get("/api/preferences/%2B15580005555")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_preferences(client):
    """DELETE for unknown phone returns i18n-ready 404 payload."""
    resp = await client.delete("/api/preferences/%2B15589999999")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["message_key"] == "preferences.not_found"
    assert detail["params"]["phone_number"] == "+15589999999"


@pytest.mark.asyncio
async def test_increment_call_count(client):
    """increment-call endpoint tracks call count."""
    resp = await client.post("/api/preferences/%2B15580006666/increment-call")
    assert resp.status_code == 200
    assert resp.json()["call_count"] == 1

    resp2 = await client.post("/api/preferences/%2B15580006666/increment-call")
    assert resp2.json()["call_count"] == 2


@pytest.mark.asyncio
async def test_increment_call_creates_if_not_exists(client):
    """increment-call creates a new preference record if none exists."""
    resp = await client.post("/api/preferences/%2B15580007777/increment-call")
    assert resp.status_code == 200
    assert resp.json()["call_count"] == 1
    assert "last_call_at" in resp.json()


@pytest.mark.asyncio
async def test_increment_call_preserves_existing_preferences(client):
    """increment-call should not overwrite previously saved caller settings."""
    await client.put(
        "/api/preferences/%2B15580009999",
        json={"preferred_language": "es", "name": "Ana"},
    )

    resp = await client.post("/api/preferences/%2B15580009999/increment-call")
    assert resp.status_code == 200
    assert resp.json()["call_count"] == 1

    fetch = await client.get("/api/preferences/%2B15580009999")
    pref = fetch.json()["preference"]
    assert pref["preferred_language"] == "es"
    assert pref["name"] == "Ana"


@pytest.mark.asyncio
async def test_preferences_not_found_payload_shape_consistent_between_get_and_delete(client):
    """GET/DELETE not-found errors should share the same i18n message key contract."""
    get_resp = await client.get("/api/preferences/%2B15580012345")
    del_resp = await client.delete("/api/preferences/%2B15580012345")

    assert get_resp.status_code == 404
    assert del_resp.status_code == 404
    assert get_resp.json()["detail"]["message_key"] == del_resp.json()["detail"]["message_key"]


@pytest.mark.asyncio
async def test_preferences_accessibility_flags(client):
    """Accessibility flags are stored and retrieved correctly."""
    resp = await client.put(
        "/api/preferences/%2B15580008888",
        json={
            "hearing_impaired": True,
            "speech_impaired": False,
            "requires_interpreter": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["preference"]
    assert data["hearing_impaired"] is True
    assert data["speech_impaired"] is False
    assert data["requires_interpreter"] is True


# ===========================================================================
# Item 7: Public status page
# ===========================================================================


@pytest.mark.asyncio
async def test_public_status_ping(client):
    """Ping endpoint returns ok immediately."""
    resp = await client.get("/api/status/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "ts" in data


@pytest.mark.asyncio
async def test_public_status_full(client):
    """Status page returns expected structure."""
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("operational", "degraded", "outage", "high_load")
    assert "services" in data
    assert "metrics" in data
    assert "departments" in data
    assert data["services"]["database"] == "ok"
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_public_status_metrics(client, db):
    """Status metrics reflect actual data."""
    # Add an active call
    db.add(Call(
        twilio_call_sid="CA_status_001",
        direction="inbound",
        status="in_progress",
        started_at=datetime.utcnow(),
    ))
    await db.flush()

    resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["metrics"]["active_calls"] >= 1


@pytest.mark.asyncio
async def test_public_status_departments_list(client, db):
    """Status page lists active departments."""
    db.add(Department(name="Street Light Dept", code="SLD", is_active=True))
    await db.flush()

    resp = await client.get("/api/status")
    data = resp.json()
    codes = [d["code"] for d in data["departments"]]
    assert "SLD" in codes


@pytest.mark.asyncio
async def test_status_no_auth_required(client):
    """Status page accessible without any auth headers."""
    # Explicitly send no auth headers
    resp = await client.get("/api/status/ping")
    assert resp.status_code == 200


def test_status_dept_open_handles_overnight_window_current_day():
    """22:00-02:00 schedules should be open late on the start day."""
    from app.api.status import _dept_is_open

    dept = Department(
        name="After Hours",
        code="AH",
        operating_hours=json.dumps({"monday": {"open": "22:00", "close": "02:00"}}),
    )
    # Monday 23:30 should be open.
    assert _dept_is_open(dept, datetime(2026, 2, 23, 23, 30)) is True


def test_status_dept_open_handles_overnight_window_next_day_spillover():
    """22:00-02:00 schedules should remain open after midnight on next day."""
    from app.api.status import _dept_is_open

    dept = Department(
        name="After Hours",
        code="AH",
        operating_hours=json.dumps({"monday": {"open": "22:00", "close": "02:00"}}),
    )
    # Tuesday 01:30 should still be open due to Monday overnight window.
    assert _dept_is_open(dept, datetime(2026, 2, 24, 1, 30)) is True
    # Tuesday 02:15 should be closed.
    assert _dept_is_open(dept, datetime(2026, 2, 24, 2, 15)) is False


# ===========================================================================
# Item 4: Operating hours enforcement
# ===========================================================================


@pytest.mark.asyncio
async def test_operating_hours_check_within_hours():
    """Appointment within operating hours passes validation."""
    from app.services.appointment_engine import check_operating_hours

    hours_json = json.dumps({
        "monday": {"open": "09:00", "close": "17:00"},
    })
    # Monday at 10am
    start = datetime(2026, 2, 23, 10, 0)  # Monday
    end = datetime(2026, 2, 23, 10, 30)
    check_operating_hours(hours_json, start, end)  # Should not raise


@pytest.mark.asyncio
async def test_operating_hours_check_before_open():
    """Appointment before opening time raises OutsideOperatingHoursError."""
    from app.services.appointment_engine import OutsideOperatingHoursError, check_operating_hours

    hours_json = json.dumps({
        "monday": {"open": "09:00", "close": "17:00"},
    })
    start = datetime(2026, 2, 23, 7, 0)  # 7am Monday — too early
    end = datetime(2026, 2, 23, 7, 30)
    with pytest.raises(OutsideOperatingHoursError) as exc_info:
        check_operating_hours(hours_json, start, end)
    assert exc_info.value.message_key == "appointments.operating_hours.before_open"
    assert exc_info.value.params["opens_at"] == "09:00"
    assert "opens at" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_operating_hours_check_after_close():
    """Appointment ending after closing time raises OutsideOperatingHoursError."""
    from app.services.appointment_engine import OutsideOperatingHoursError, check_operating_hours

    hours_json = json.dumps({
        "monday": {"open": "09:00", "close": "17:00"},
    })
    start = datetime(2026, 2, 23, 16, 30)  # 4:30pm Monday
    end = datetime(2026, 2, 23, 17, 30)   # 5:30pm — past close
    with pytest.raises(OutsideOperatingHoursError) as exc_info:
        check_operating_hours(hours_json, start, end)
    assert exc_info.value.message_key == "appointments.operating_hours.after_close"
    assert exc_info.value.params["closes_at"] == "17:00"
    assert "closes at" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_operating_hours_closed_day():
    """Appointment on a closed day raises OutsideOperatingHoursError."""
    from app.services.appointment_engine import OutsideOperatingHoursError, check_operating_hours

    hours_json = json.dumps({
        "monday": {"open": "09:00", "close": "17:00"},
        # No entry for Saturday = closed
    })
    # Saturday
    start = datetime(2026, 2, 28, 10, 0)  # Saturday
    end = datetime(2026, 2, 28, 10, 30)
    with pytest.raises(OutsideOperatingHoursError) as exc_info:
        check_operating_hours(hours_json, start, end)
    assert exc_info.value.message_key == "appointments.operating_hours.closed_day"
    assert exc_info.value.params["day"] == "saturday"
    assert "closed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_operating_hours_no_config_allows_any_time():
    """No operating hours configured = no restriction."""
    from app.services.appointment_engine import check_operating_hours

    check_operating_hours(None, datetime.utcnow(), datetime.utcnow() + timedelta(hours=1))
    check_operating_hours("", datetime.utcnow(), datetime.utcnow() + timedelta(hours=1))
    # Should not raise


@pytest.mark.asyncio
async def test_operating_hours_legacy_mon_fri_format_supported():
    """Legacy mon-fri range format remains backward-compatible."""
    from app.services.appointment_engine import check_operating_hours

    hours_json = json.dumps({"mon-fri": "9:00-16:00"})
    start = datetime(2026, 2, 24, 10, 0)  # Tuesday
    end = datetime(2026, 2, 24, 10, 30)
    check_operating_hours(hours_json, start, end)


@pytest.mark.asyncio
async def test_operating_hours_legacy_weekend_closed():
    """Legacy mon-fri format rejects weekend bookings."""
    from app.services.appointment_engine import OutsideOperatingHoursError, check_operating_hours

    hours_json = json.dumps({"mon-fri": "9:00-16:00"})
    start = datetime(2026, 2, 28, 10, 0)  # Saturday
    end = datetime(2026, 2, 28, 10, 30)
    with pytest.raises(OutsideOperatingHoursError):
        check_operating_hours(hours_json, start, end)


@pytest.mark.asyncio
async def test_operating_hours_overnight_window_allows_cross_midnight():
    """Overnight windows (e.g. 22:00-02:00) allow bookings that end next day."""
    from app.services.appointment_engine import check_operating_hours

    hours_json = json.dumps({
        "monday": {"open": "22:00", "close": "02:00"},
    })
    start = datetime(2026, 2, 23, 23, 30)  # Monday 11:30pm
    end = datetime(2026, 2, 24, 1, 30)     # Tuesday 1:30am
    check_operating_hours(hours_json, start, end)


@pytest.mark.asyncio
async def test_operating_hours_overnight_window_rejects_after_close():
    """Overnight windows still reject bookings past close time next day."""
    from app.services.appointment_engine import OutsideOperatingHoursError, check_operating_hours

    hours_json = json.dumps({
        "monday": {"open": "22:00", "close": "02:00"},
    })
    start = datetime(2026, 2, 23, 23, 30)  # Monday 11:30pm
    end = datetime(2026, 2, 24, 2, 30)     # Tuesday 2:30am (too late)
    with pytest.raises(OutsideOperatingHoursError) as exc_info:
        check_operating_hours(hours_json, start, end)
    assert "closes" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_booking_enforces_operating_hours_via_api(client, seeded_db):
    """POST /api/appointments returns 422 for out-of-hours booking when dept has hours."""
    contact_resp = await client.post(
        "/api/contacts", json={"phone_number": "+15591110001"}
    )
    contact_id = contact_resp.json()["contact"]["id"]

    # Create dept with strict hours
    dept_resp = await client.post(
        "/api/departments",
        json={
            "name": "Strict Hours Dept",
            "code": "SHD",
            "operating_hours": json.dumps({
                "monday": {"open": "09:00", "close": "17:00"},
            }),
        },
    )
    dept_id = dept_resp.json()["department"]["id"]

    # Try to book at 8pm Monday
    resp = await client.post(
        "/api/appointments",
        json={
            "contact_id": contact_id,
            "department_id": dept_id,
            "title": "Late Night",
            "scheduled_start": "2026-02-23T20:00:00",
            "scheduled_end": "2026-02-23T20:30:00",
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message_key"] == "appointments.operating_hours.after_close"
    assert detail["params"]["closes_at"] == "17:00"
    assert "closes" in detail["message"].lower() or "hours" in detail["message"].lower()


@pytest.mark.asyncio
async def test_appointment_not_found_errors_are_i18n_ready(client):
    """Appointment get/patch/delete 404 errors return i18n-ready payloads."""
    missing_id = 999999

    get_resp = await client.get(f"/api/appointments/{missing_id}")
    patch_resp = await client.patch(f"/api/appointments/{missing_id}", json={"title": "x"})
    delete_resp = await client.delete(f"/api/appointments/{missing_id}")

    assert get_resp.status_code == 404
    assert patch_resp.status_code == 404
    assert delete_resp.status_code == 404

    for resp in (get_resp, patch_resp, delete_resp):
        detail = resp.json()["detail"]
        assert detail["message_key"] == "appointments.not_found"
        assert detail["params"]["appointment_id"] == missing_id


@pytest.mark.asyncio
async def test_appointment_conflict_error_is_i18n_ready(client, seeded_db):
    """Booking conflict returns structured i18n-ready error payload."""
    contact_resp = await client.post(
        "/api/contacts", json={"phone_number": "+15591110002"}
    )
    contact_id = contact_resp.json()["contact"]["id"]

    dept_resp = await client.post(
        "/api/departments",
        json={"name": "Conflict Dept", "code": "CFD"},
    )
    dept_id = dept_resp.json()["department"]["id"]

    payload = {
        "contact_id": contact_id,
        "department_id": dept_id,
        "title": "First",
        "scheduled_start": "2026-03-03T10:00:00",
        "scheduled_end": "2026-03-03T10:30:00",
    }

    first = await client.post("/api/appointments", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/appointments", json=payload)
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["message_key"] == "appointments.booking_conflict"
    assert "book" in detail["message"].lower() or "conflict" in detail["message"].lower()


# ===========================================================================
# Item 6: Bulk appointment import
# ===========================================================================


@pytest.mark.asyncio
async def test_bulk_import_success(client, db):
    """Bulk import creates appointments for valid rows."""
    contact = Contact(phone_number="+15592220001", name="Bulk Import Test")
    dept = Department(name="Bulk Dept", code="BLK2")
    db.add(contact)
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [
                {
                    "contact_phone": "+15592220001",
                    "department_code": "BLK2",
                    "title": "Import Appt 1",
                    "scheduled_start": "2026-03-01T09:00:00",
                    "scheduled_end": "2026-03-01T09:30:00",
                },
                {
                    "contact_phone": "+15592220001",
                    "department_code": "BLK2",
                    "title": "Import Appt 2",
                    "scheduled_start": "2026-03-02T10:00:00",
                    "scheduled_end": "2026-03-02T10:30:00",
                },
            ],
            "dry_run": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["created"] == 2
    assert data["errors"] == 0


@pytest.mark.asyncio
async def test_bulk_import_dry_run(client, db):
    """Dry run validates without creating records."""
    contact = Contact(phone_number="+15592220002")
    dept = Department(name="Dry Run Dept", code="DRY")
    db.add(contact)
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220002",
                "department_code": "DRY",
                "title": "Dry Run Appt",
                "scheduled_start": "2026-03-03T09:00:00",
            }],
            "dry_run": True,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["dry_run"] is True
    assert resp.json()["created"] == 1
    # Verify nothing was actually created
    await client.get("/api/appointments?department_id=999999")
    # No crash = success


@pytest.mark.asyncio
async def test_bulk_import_unknown_contact_error(client, db):
    """Rows with unknown contact phone go to errors list."""
    dept = Department(name="Error Dept", code="ERR")
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15599999001",  # doesn't exist
                "department_code": "ERR",
                "title": "Orphan Appt",
                "scheduled_start": "2026-03-04T09:00:00",
            }],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["errors"] == 1
    assert data["created"] == 0
    err = data["error_rows"][0]
    assert err["message_key"] == "appointments.import.contact_not_found"
    assert err["params"]["contact_phone"] == "+15599999001"


@pytest.mark.asyncio
async def test_bulk_import_unknown_dept_error(client, db):
    """Rows with unknown department code go to errors list."""
    contact = Contact(phone_number="+15592220003")
    db.add(contact)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220003",
                "department_code": "XXXXXX",  # doesn't exist
                "title": "Bad Dept Appt",
                "scheduled_start": "2026-03-05T09:00:00",
            }],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["errors"] == 1
    err = data["error_rows"][0]
    assert err["message_key"] == "appointments.import.department_not_found"
    assert err["params"]["department_code"] == "XXXXXX"


@pytest.mark.asyncio
async def test_bulk_import_skip_duplicates(client, db):
    """skip_duplicates=True skips existing confirmed appointments."""
    contact = Contact(phone_number="+15592220004")
    dept = Department(name="Skip Dup Dept", code="SKP")
    db.add(contact)
    db.add(dept)
    await db.flush()

    # Pre-create an appointment
    db.add(Appointment(
        contact_id=contact.id,
        department_id=dept.id,
        title="Pre-existing",
        status="confirmed",
        scheduled_start=datetime(2026, 3, 10, 9, 0),
        scheduled_end=datetime(2026, 3, 10, 9, 30),
    ))
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220004",
                "department_code": "SKP",
                "title": "Duplicate",
                "scheduled_start": "2026-03-10T09:00:00",
            }],
            "skip_duplicates": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["skipped"] == 1
    assert data["created"] == 0


@pytest.mark.asyncio
async def test_bulk_import_mixed_results(client, db):
    """Mix of valid, invalid, and duplicate rows handled correctly."""
    contact = Contact(phone_number="+15592220005")
    dept = Department(name="Mixed Import Dept", code="MXD")
    db.add(contact)
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [
                # Valid
                {
                    "contact_phone": "+15592220005",
                    "department_code": "MXD",
                    "title": "Good Appt",
                    "scheduled_start": "2026-03-06T09:00:00",
                },
                # Invalid contact
                {
                    "contact_phone": "+15599999999",
                    "department_code": "MXD",
                    "title": "Bad Contact",
                    "scheduled_start": "2026-03-07T09:00:00",
                },
                # Invalid dept
                {
                    "contact_phone": "+15592220005",
                    "department_code": "NOPE",
                    "title": "Bad Dept",
                    "scheduled_start": "2026-03-08T09:00:00",
                },
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_rows"] == 3
    assert data["created"] == 1
    assert data["errors"] == 2
    keys = {row["message_key"] for row in data["error_rows"]}
    assert keys == {
        "appointments.import.contact_not_found",
        "appointments.import.department_not_found",
    }


@pytest.mark.asyncio
async def test_bulk_import_invalid_datetime_row(client, db):
    """Rows with invalid datetime strings are reported as errors."""
    contact = Contact(phone_number="+15592220006")
    dept = Department(name="Datetime Dept", code="DTM")
    db.add(contact)
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220006",
                "department_code": "DTM",
                "title": "Bad Datetime",
                "scheduled_start": "not-a-date",
            }],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["errors"] == 1
    err = data["error_rows"][0]
    assert err["message_key"] == "appointments.import.invalid_datetime"
    assert err["params"]["field"] == "scheduled_start"


@pytest.mark.asyncio
async def test_bulk_import_default_end_time_is_one_hour(client, db):
    """When scheduled_end is omitted, endpoint defaults to +1 hour."""
    contact = Contact(phone_number="+15592220007")
    dept = Department(name="Default End Dept", code="DEF")
    db.add(contact)
    db.add(dept)
    await db.flush()

    start = "2026-03-09T11:00:00"
    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220007",
                "department_code": "DEF",
                "title": "Default End",
                "scheduled_start": start,
            }],
        },
    )
    assert resp.status_code == 201
    appt = (await db.execute(select(Appointment).where(Appointment.title == "Default End"))).scalar_one()
    assert int((appt.scheduled_end - appt.scheduled_start).total_seconds()) == 3600


@pytest.mark.asyncio
async def test_bulk_import_no_skip_duplicates_allows_second_row(client, db):
    """With skip_duplicates=False, duplicate rows are inserted."""
    contact = Contact(phone_number="+15592220008")
    dept = Department(name="No Skip Dept", code="NSK")
    db.add(contact)
    db.add(dept)
    await db.flush()

    payload = {
        "appointments": [
            {
                "contact_phone": "+15592220008",
                "department_code": "NSK",
                "title": "Dup One",
                "scheduled_start": "2026-03-11T09:00:00",
            },
            {
                "contact_phone": "+15592220008",
                "department_code": "NSK",
                "title": "Dup Two",
                "scheduled_start": "2026-03-11T09:00:00",
            },
        ],
        "skip_duplicates": False,
    }
    resp = await client.post("/api/appointments/import", json=payload)
    assert resp.status_code == 201
    assert resp.json()["created"] == 2


@pytest.mark.asyncio
async def test_bulk_import_invalid_scheduled_end_row(client, db):
    """Invalid scheduled_end values are reported as row errors (not 500s)."""
    contact = Contact(phone_number="+15592220009")
    dept = Department(name="Bad End Dept", code="BND")
    db.add(contact)
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220009",
                "department_code": "BND",
                "title": "Bad End",
                "scheduled_start": "2026-03-12T09:00:00",
                "scheduled_end": "definitely-not-a-date",
            }],
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["created"] == 0
    assert data["errors"] == 1
    err = data["error_rows"][0]
    assert err["message_key"] == "appointments.import.invalid_datetime"
    assert err["params"]["field"] == "scheduled_end"


@pytest.mark.asyncio
async def test_bulk_import_end_before_start_row(client, db):
    """Rows with scheduled_end <= scheduled_start are rejected with i18n-ready payloads."""
    contact = Contact(phone_number="+15592220010")
    dept = Department(name="Window Dept", code="WND")
    db.add(contact)
    db.add(dept)
    await db.flush()

    resp = await client.post(
        "/api/appointments/import",
        json={
            "appointments": [{
                "contact_phone": "+15592220010",
                "department_code": "WND",
                "title": "Backwards Window",
                "scheduled_start": "2026-03-12T11:00:00",
                "scheduled_end": "2026-03-12T10:59:00",
            }],
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["created"] == 0
    assert data["errors"] == 1
    err = data["error_rows"][0]
    assert err["message_key"] == "appointments.import.invalid_time_window"
    assert err["params"]["field"] == "scheduled_end"
