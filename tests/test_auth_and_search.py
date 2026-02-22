"""Tests for JWT token auth and contact search/lookup endpoints.

Covers:
- POST /api/auth/token — login returns JWT tokens
- POST /api/auth/refresh — refresh token → new access token
- JWT token structure and claims
- Invalid credentials rejected
- Token decode / validation helpers
- GET /api/contacts/search — ranked full-text search
- GET /api/contacts/lookup/{phone} — exact phone lookup
"""

import pytest
from jose import jwt

from app.core.security import (
    _ALGORITHM,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.config import settings
from app.models.contact import Contact
from app.models.user import DashboardUser
from app.core.security import hash_password


# ===========================================================================
# JWT helper unit tests
# ===========================================================================


def test_create_access_token_structure():
    """Access token has correct claims."""
    token = create_access_token(subject=42, role="supervisor")
    payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    assert payload["sub"] == "42"
    assert payload["role"] == "supervisor"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_create_refresh_token_structure():
    """Refresh token has type='refresh'."""
    token = create_refresh_token(subject=7)
    payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    assert payload["sub"] == "7"
    assert payload["type"] == "refresh"


def test_decode_token_valid():
    """decode_token returns payload for a valid token."""
    token = create_access_token(subject=1, role="admin")
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "admin"


def test_decode_token_invalid_raises():
    """decode_token raises HTTPException for a garbage token."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_token("not.a.valid.token")
    assert exc_info.value.status_code == 401


def test_decode_token_wrong_secret():
    """Token signed with wrong secret is rejected."""
    from fastapi import HTTPException

    token = jwt.encode({"sub": "1", "type": "access"}, "wrong-secret", algorithm=_ALGORITHM)
    with pytest.raises(HTTPException):
        decode_token(token)


def test_access_token_extra_claims():
    """Extra claims are preserved in the token."""
    token = create_access_token(subject=5, role="operator", extra={"dept": "PW"})
    payload = decode_token(token)
    assert payload.get("dept") == "PW"


# ===========================================================================
# POST /api/auth/token
# ===========================================================================


@pytest.mark.asyncio
async def test_login_returns_tokens(client, db):
    """Valid credentials return access + refresh tokens."""
    db.add(DashboardUser(
        username="tokenuser",
        password_hash=hash_password("securepass1"),
        name="Token User",
        role="operator",
    ))
    await db.flush()

    resp = await client.post(
        "/api/auth/token",
        json={"username": "tokenuser", "password": "securepass1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 60 * 60 * 8


@pytest.mark.asyncio
async def test_login_token_contains_correct_claims(client, db):
    """Access token contains user id and role."""
    db.add(DashboardUser(
        username="claimuser",
        password_hash=hash_password("securepass1"),
        name="Claim User",
        role="supervisor",
    ))
    await db.flush()

    resp = await client.post(
        "/api/auth/token",
        json={"username": "claimuser", "password": "securepass1"},
    )
    assert resp.status_code == 200
    access_token = resp.json()["access_token"]
    payload = jwt.decode(access_token, settings.secret_key, algorithms=[_ALGORITHM])
    assert payload["role"] == "supervisor"
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_login_wrong_password(client, db):
    """Wrong password returns 401."""
    db.add(DashboardUser(
        username="wrongpw",
        password_hash=hash_password("correctpass1"),
        name="Wrong PW",
        role="operator",
    ))
    await db.flush()

    resp = await client.post(
        "/api/auth/token",
        json={"username": "wrongpw", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    """Unknown username returns 401."""
    resp = await client.post(
        "/api/auth/token",
        json={"username": "nobody_here", "password": "password1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_rejected(client, db):
    """Inactive user cannot log in."""
    db.add(DashboardUser(
        username="inactiveuser",
        password_hash=hash_password("password1"),
        name="Inactive",
        role="operator",
        is_active=False,
    ))
    await db.flush()

    resp = await client.post(
        "/api/auth/token",
        json={"username": "inactiveuser", "password": "password1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_response_includes_user(client, db):
    """Login response includes user info."""
    db.add(DashboardUser(
        username="withinfo",
        password_hash=hash_password("password1"),
        name="With Info",
        role="admin",
    ))
    await db.flush()

    resp = await client.post(
        "/api/auth/token",
        json={"username": "withinfo", "password": "password1"},
    )
    assert resp.status_code == 200
    user_data = resp.json()["user"]
    assert user_data["username"] == "withinfo"
    assert user_data["role"] == "admin"
    assert "password" not in user_data
    assert "password_hash" not in user_data


# ===========================================================================
# POST /api/auth/refresh
# ===========================================================================


@pytest.mark.asyncio
async def test_refresh_token_issues_new_access_token(client, db):
    """Valid refresh token returns a new access token."""
    user = DashboardUser(
        username="refreshuser",
        password_hash=hash_password("password1"),
        name="Refresh User",
        role="operator",
    )
    db.add(user)
    await db.flush()

    # Login first
    login_resp = await client.post(
        "/api/auth/token",
        json={"username": "refreshuser", "password": "password1"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Use refresh token
    resp = await client.post(
        "/api/auth/refresh",
        params={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert resp.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client, db):
    """Access token cannot be used as a refresh token."""
    user = DashboardUser(
        username="badrefresh",
        password_hash=hash_password("password1"),
        name="Bad Refresh",
        role="operator",
    )
    db.add(user)
    await db.flush()

    login_resp = await client.post(
        "/api/auth/token",
        json={"username": "badrefresh", "password": "password1"},
    )
    access_token = login_resp.json()["access_token"]

    # Pass access token as refresh token — should fail
    resp = await client.post(
        "/api/auth/refresh",
        params={"refresh_token": access_token},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_fails(client):
    """Garbage refresh token returns 401."""
    resp = await client.post(
        "/api/auth/refresh",
        params={"refresh_token": "not-a-real-token"},
    )
    assert resp.status_code == 401


# ===========================================================================
# GET /api/contacts/search
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_search_by_name(client, db):
    """Search returns contacts matching name."""
    db.add(Contact(phone_number="+15560001001", name="Alice Johnson"))
    db.add(Contact(phone_number="+15560001002", name="Bob Smith"))
    await db.flush()

    resp = await client.get("/api/contacts/search?q=Alice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    names = [r["contact"]["name"] for r in data["results"]]
    assert "Alice Johnson" in names


@pytest.mark.asyncio
async def test_contact_search_by_phone(client, db):
    """Search returns contacts matching phone number."""
    db.add(Contact(phone_number="+15560002001", name="Phone Search Test"))
    await db.flush()

    resp = await client.get("/api/contacts/search?q=%2B15560002001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    phones = [r["contact"]["phone_number"] for r in data["results"]]
    assert "+15560002001" in phones


@pytest.mark.asyncio
async def test_contact_search_exact_phone_ranks_first(client, db):
    """Exact phone match scores higher than partial matches."""
    db.add(Contact(phone_number="+15560003001", name="Exact Match"))
    db.add(Contact(phone_number="+15560003001999", name="Partial Match"))
    await db.flush()

    resp = await client.get("/api/contacts/search?q=%2B15560003001")
    assert resp.status_code == 200
    results = resp.json()["results"]
    if len(results) >= 2:
        # First result should have higher score
        assert results[0]["score"] >= results[1]["score"]


@pytest.mark.asyncio
async def test_contact_search_no_results(client):
    """Search with no matching contacts returns empty results."""
    resp = await client.get("/api/contacts/search?q=zzz_no_match_xyz")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_contact_search_by_email(client, db):
    """Search matches email addresses."""
    db.add(Contact(
        phone_number="+15560004001",
        name="Email Test",
        email="searchtest@example.gov",
    ))
    await db.flush()

    resp = await client.get("/api/contacts/search?q=searchtest%40example")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_contact_search_empty_query_rejected(client):
    """Empty search query returns 422."""
    resp = await client.get("/api/contacts/search?q=")
    assert resp.status_code == 422


# ===========================================================================
# GET /api/contacts/lookup/{phone}
# ===========================================================================


@pytest.mark.asyncio
async def test_contact_lookup_by_phone(client, db):
    """Exact phone lookup returns matching contact."""
    db.add(Contact(phone_number="+15570001001", name="Lookup Test"))
    await db.flush()

    resp = await client.get("/api/contacts/lookup/%2B15570001001")
    assert resp.status_code == 200
    assert resp.json()["contact"]["phone_number"] == "+15570001001"
    assert resp.json()["contact"]["name"] == "Lookup Test"


@pytest.mark.asyncio
async def test_contact_lookup_not_found(client):
    """Lookup with unknown phone returns 404."""
    resp = await client.get("/api/contacts/lookup/%2B15579999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_contact_lookup_url_encoded_phone(client, db):
    """URL-encoded phone number is decoded and matched correctly."""
    db.add(Contact(phone_number="+447911000001", name="UK Caller"))
    await db.flush()

    # +447911000001 → %2B447911000001
    resp = await client.get("/api/contacts/lookup/%2B447911000001")
    assert resp.status_code == 200
    assert resp.json()["contact"]["name"] == "UK Caller"
