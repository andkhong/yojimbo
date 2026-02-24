import pytest


@pytest.mark.asyncio
async def test_department_not_found_error_is_i18n_ready(client):
    resp = await client.get("/api/departments/99999")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["message_key"] == "departments.not_found"
    assert detail["params"]["department_id"] == 99999


@pytest.mark.asyncio
async def test_bulk_slot_invalid_day_error_is_i18n_ready(client):
    create = await client.post(
        "/api/departments",
        json={"name": "Parks", "code": "PRK"},
    )
    assert create.status_code == 201
    department_id = create.json()["department"]["id"]

    resp = await client.post(
        f"/api/departments/{department_id}/slots/bulk",
        json={
            "days_of_week": [7],
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message_key"] == "departments.time_slot.invalid_day_of_week"
    assert detail["params"]["day_of_week"] == 7


@pytest.mark.asyncio
async def test_slot_availability_invalid_date_error_is_i18n_ready(client):
    create = await client.post(
        "/api/departments",
        json={"name": "Utilities", "code": "UTL"},
    )
    assert create.status_code == 201
    department_id = create.json()["department"]["id"]

    resp = await client.get(
        f"/api/departments/{department_id}/slots/availability?date=02-23-2026"
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message_key"] == "departments.availability.invalid_date_format"
    assert detail["params"]["expected_format"] == "YYYY-MM-DD"
