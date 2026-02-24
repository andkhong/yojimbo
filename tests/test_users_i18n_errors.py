import pytest


@pytest.mark.asyncio
async def test_users_duplicate_username_error_is_i18n_ready(client):
    payload = {
        "username": "same-user",
        "password": "secret123",
        "name": "Same User",
        "role": "operator",
    }
    first = await client.post("/api/users", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/users", json=payload)
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["message_key"] == "users.username_taken"
    assert detail["params"]["username"] == "same-user"


@pytest.mark.asyncio
async def test_users_not_found_error_is_i18n_ready(client):
    resp = await client.get("/api/users/99999")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["message_key"] == "users.not_found"
    assert detail["params"]["user_id"] == 99999


@pytest.mark.asyncio
async def test_users_last_admin_deactivate_error_is_i18n_ready(client):
    create = await client.post(
        "/api/users",
        json={
            "username": "solo-admin",
            "password": "secret123",
            "name": "Solo Admin",
            "role": "admin",
        },
    )
    assert create.status_code == 201
    user_id = create.json()["user"]["id"]

    admins = await client.get("/api/users?role=admin")
    assert admins.status_code == 200
    for admin in admins.json()["users"]:
        if admin["id"] != user_id:
            resp = await client.delete(f"/api/users/{admin['id']}")
            assert resp.status_code == 204

    delete = await client.delete(f"/api/users/{user_id}")
    assert delete.status_code == 409
    detail = delete.json()["detail"]
    assert detail["message_key"] == "users.last_admin_deactivate_forbidden"
    assert detail["params"]["user_id"] == user_id


@pytest.mark.asyncio
async def test_users_by_role_invalid_role_is_i18n_ready(client):
    resp = await client.get("/api/users/by-role/not-a-role")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message_key"] == "users.invalid_role"
    assert detail["params"]["role"] == "not-a-role"
    assert "allowed_roles" in detail["params"]
