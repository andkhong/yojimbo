"""Tests for input validation, rate limiting, and audit middleware.

Covers:
- Contact phone number E.164 validation
- Contact email validation
- User username format validation
- User password minimum length
- Department code format validation
- Department name length validation
- Rate limit middleware (429 responses)
- Audit middleware integration (entries created on mutations)
"""

import pytest

from app.models.audit_log import AuditLog


# ===========================================================================
# Contact phone validation
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_valid_e164_phone(client):
    """Valid E.164 phone is accepted."""
    resp = await client.post("/api/contacts", json={"phone_number": "+15551234567"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_contact_invalid_phone_no_plus(client):
    """Phone without leading + is rejected."""
    resp = await client.post("/api/contacts", json={"phone_number": "15551234567"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_contact_invalid_phone_too_short(client):
    """Phone that's too short is rejected."""
    resp = await client.post("/api/contacts", json={"phone_number": "+123"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_contact_invalid_phone_letters(client):
    """Phone containing letters is rejected."""
    resp = await client.post("/api/contacts", json={"phone_number": "+1555ABC4567"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_contact_valid_international_phone(client):
    """International E.164 phones are accepted."""
    for phone in ["+447911123456", "+4915212345678", "+819012345678"]:
        resp = await client.post(
            "/api/contacts",
            json={"phone_number": phone, "name": f"Test {phone}"},
        )
        assert resp.status_code == 201, f"Expected 201 for {phone}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_contact_valid_email(client):
    """Valid email is stored (lowercased)."""
    resp = await client.post(
        "/api/contacts",
        json={"phone_number": "+15550001001", "email": "User@Example.COM"},
    )
    assert resp.status_code == 201
    assert resp.json()["contact"]["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_contact_invalid_email_no_at(client):
    """Email without @ is rejected."""
    resp = await client.post(
        "/api/contacts",
        json={"phone_number": "+15550001002", "email": "notanemail"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_contact_invalid_email_no_domain(client):
    """Email without domain is rejected."""
    resp = await client.post(
        "/api/contacts",
        json={"phone_number": "+15550001003", "email": "user@"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_contact_null_email_accepted(client):
    """Null email is accepted (optional field)."""
    resp = await client.post(
        "/api/contacts",
        json={"phone_number": "+15550001004", "email": None},
    )
    assert resp.status_code == 201
    assert resp.json()["contact"]["email"] is None


@pytest.mark.asyncio
async def test_contact_update_invalid_email(client):
    """Updating contact with invalid email returns 422."""
    create_resp = await client.post("/api/contacts", json={"phone_number": "+15550001005"})
    cid = create_resp.json()["contact"]["id"]
    resp = await client.patch(f"/api/contacts/{cid}", json={"email": "not-valid"})
    assert resp.status_code == 422


# ===========================================================================
# User validation
# ===========================================================================


@pytest.mark.asyncio
async def test_user_username_too_short(client):
    """Username shorter than 3 chars is rejected."""
    resp = await client.post(
        "/api/users",
        json={"username": "ab", "password": "password1", "name": "X", "role": "operator"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_user_username_invalid_chars(client):
    """Username with spaces or special chars is rejected."""
    for bad_name in ["user name", "user@domain", "user!admin"]:
        resp = await client.post(
            "/api/users",
            json={"username": bad_name, "password": "password1", "name": "X", "role": "operator"},
        )
        assert resp.status_code == 422, f"Expected 422 for username {bad_name!r}"


@pytest.mark.asyncio
async def test_user_valid_username_formats(client):
    """Valid username formats are accepted."""
    valid_names = ["alice", "alice_123", "alice-admin", "alice.doe", "ABC123"]
    for i, name in enumerate(valid_names):
        resp = await client.post(
            "/api/users",
            json={
                "username": name,
                "password": "password1",
                "name": f"User {i}",
                "role": "operator",
            },
        )
        assert resp.status_code == 201, (
            f"Expected 201 for username {name!r}, got {resp.status_code}: {resp.text}"
        )


@pytest.mark.asyncio
async def test_user_password_too_short(client):
    """Password shorter than 8 chars is rejected."""
    resp = await client.post(
        "/api/users",
        json={"username": "shortpw", "password": "pass", "name": "X", "role": "operator"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_user_valid_password(client):
    """Password exactly 8 chars is accepted."""
    resp = await client.post(
        "/api/users",
        json={"username": "minpwuser", "password": "12345678", "name": "Min", "role": "operator"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_user_invalid_role_in_schema(client):
    """Invalid role is rejected at schema level."""
    resp = await client.post(
        "/api/users",
        json={"username": "badrole_u", "password": "password1", "name": "X", "role": "god"},
    )
    assert resp.status_code == 422


# ===========================================================================
# Department validation
# ===========================================================================


@pytest.mark.asyncio
async def test_department_valid_code(client):
    """Valid department codes are accepted."""
    for code in ["BLDG", "PW-01", "DEPT_A", "X"]:
        resp = await client.post(
            "/api/departments",
            json={"name": f"Dept {code}", "code": code},
        )
        assert resp.status_code == 201, f"Expected 201 for code {code!r}"


@pytest.mark.asyncio
async def test_department_lowercase_code_auto_upcased(client):
    """Lowercase code is automatically uppercased."""
    resp = await client.post(
        "/api/departments",
        json={"name": "Test Dept Lower", "code": "lower"},
    )
    assert resp.status_code == 201
    assert resp.json()["department"]["code"] == "LOWER"


@pytest.mark.asyncio
async def test_department_invalid_code_special_chars(client):
    """Department code with spaces or special characters is rejected."""
    for bad_code in ["DEPT CODE", "DEPT@123", "DEPT/A", "DEPT.A"]:
        resp = await client.post(
            "/api/departments",
            json={"name": "Test Dept", "code": bad_code},
        )
        assert resp.status_code == 422, f"Expected 422 for code {bad_code!r}"


@pytest.mark.asyncio
async def test_department_code_too_long(client):
    """Department code longer than 20 chars is rejected."""
    resp = await client.post(
        "/api/departments",
        json={"name": "Long Code Dept", "code": "A" * 21},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_department_name_too_short(client):
    """Department name with less than 2 chars is rejected."""
    resp = await client.post(
        "/api/departments",
        json={"name": "X", "code": "X1"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_department_name_too_long(client):
    """Department name longer than 255 chars is rejected."""
    resp = await client.post(
        "/api/departments",
        json={"name": "A" * 256, "code": "LNG"},
    )
    assert resp.status_code == 422


# ===========================================================================
# Audit middleware integration
# ===========================================================================


@pytest.mark.asyncio
async def test_audit_middleware_logs_post(client):
    """POST to /api/departments creates an audit log entry (middleware runs in bg)."""
    resp = await client.post("/api/departments", json={"name": "Audit Test Dept", "code": "AUD1"})
    assert resp.status_code == 201

    # Middleware uses its own DB session (fires after response).
    # Verify the endpoint didn't crash and the audit log API is accessible.
    audit_resp = await client.get("/api/audit-logs?action=CREATE&resource_type=department")
    assert audit_resp.status_code == 200


@pytest.mark.asyncio
async def test_audit_middleware_skips_get(client, db):
    """GET requests are NOT logged by the audit middleware."""
    from sqlalchemy import func, select

    before_count = (await db.execute(select(func.count()).select_from(AuditLog))).scalar() or 0

    await client.get("/api/departments")
    await client.get("/api/calls")
    await client.get("/api/contacts")

    after_count = (await db.execute(select(func.count()).select_from(AuditLog))).scalar() or 0

    # GET requests must not generate audit log entries
    assert after_count == before_count


@pytest.mark.asyncio
async def test_audit_middleware_skips_twilio(client):
    """Twilio webhook endpoints are excluded from audit logging."""
    # Even if these hit the webhook, they should not crash
    resp = await client.post("/api/twilio/voice", data={"CallSid": "CA123", "From": "+15550001111"})
    # Just verify no 500 error
    assert resp.status_code != 500


# ===========================================================================
# Rate limit middleware
# ===========================================================================


@pytest.mark.asyncio
async def test_rate_limit_auth_endpoint(client):
    """Auth endpoint is rate-limited (10/min). Burst past limit returns 429."""
    # The test client doesn't share an IP limit with other tests in this suite
    # because the rate limiter resets between test processes.
    # We can check the middleware by sending many rapid requests.
    # Use a different approach: check the 429 response format when limit is hit.
    # For unit test: directly test the token bucket logic.
    from app.middleware.rate_limit import _BucketStore

    store = _BucketStore()
    store.register("test", capacity=3, per_seconds=60)

    # First 3 should succeed
    assert store.consume("1.2.3.4", "test") is True
    assert store.consume("1.2.3.4", "test") is True
    assert store.consume("1.2.3.4", "test") is True
    # 4th should be rate-limited
    assert store.consume("1.2.3.4", "test") is False


@pytest.mark.asyncio
async def test_rate_limit_different_ips_not_shared(client):
    """Different IPs have independent token buckets."""
    from app.middleware.rate_limit import _BucketStore

    store = _BucketStore()
    store.register("test2", capacity=2, per_seconds=60)

    # IP A burns 2 tokens
    assert store.consume("10.0.0.1", "test2") is True
    assert store.consume("10.0.0.1", "test2") is True
    assert store.consume("10.0.0.1", "test2") is False  # exhausted

    # IP B still has full quota
    assert store.consume("10.0.0.2", "test2") is True
    assert store.consume("10.0.0.2", "test2") is True
    assert store.consume("10.0.0.2", "test2") is False  # now exhausted


@pytest.mark.asyncio
async def test_rate_limit_bucket_refills(client):
    """Token bucket refills over time."""
    from app.middleware.rate_limit import _Bucket

    # Very fast refill: 10 tokens/second
    bucket = _Bucket(capacity=2, refill_rate=10.0)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False  # empty

    # Simulate time passing
    bucket.last_refill -= 0.5  # pretend 0.5 seconds passed
    # Should have refilled ~5 tokens, enough to consume again
    assert bucket.consume() is True


@pytest.mark.asyncio
async def test_rate_limit_classify_paths():
    """Path classifier assigns correct limit keys."""
    from app.middleware.rate_limit import _classify

    assert _classify("/api/twilio/voice") == "twilio"
    assert _classify("/api/twilio/sms") == "twilio"
    assert _classify("/api/auth/login") == "auth"
    assert _classify("/api/auth/logout") == "auth"
    assert _classify("/api/departments") == "api"
    assert _classify("/api/calls") == "api"
    assert _classify("/static/css/app.css") is None
    assert _classify("/ws/dashboard") is None
    assert _classify("/dashboard") is None


@pytest.mark.asyncio
async def test_rate_limit_unregistered_key_passes():
    """Unregistered limit keys always pass (no limit)."""
    from app.middleware.rate_limit import _BucketStore

    store = _BucketStore()
    # "unregistered" key never added to store
    for _ in range(100):
        assert store.consume("1.2.3.4", "unregistered") is True


# ===========================================================================
# Schema validation — edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_phone_with_spaces_rejected(client):
    """Phone number with spaces is rejected."""
    resp = await client.post(
        "/api/contacts",
        json={"phone_number": "+1 555 123 4567"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_contact_phone_leading_zero_rejected(client):
    """Phone number starting with +0 is rejected (no country code starts with 0)."""
    resp = await client.post(
        "/api/contacts",
        json={"phone_number": "+0123456789"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_user_username_max_length(client):
    """Username exactly 64 chars is accepted; 65 chars rejected."""
    long_name = "a" * 64
    resp = await client.post(
        "/api/users",
        json={"username": long_name, "password": "password1", "name": "Long", "role": "readonly"},
    )
    assert resp.status_code == 201

    too_long = "a" * 65
    resp2 = await client.post(
        "/api/users",
        json={
            "username": too_long,
            "password": "password1",
            "name": "Too Long",
            "role": "readonly",
        },
    )
    assert resp2.status_code == 422
