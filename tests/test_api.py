"""Tests for REST API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_departments_empty(client):
    response = await client.get("/api/departments")
    assert response.status_code == 200
    data = response.json()
    assert "departments" in data
    assert isinstance(data["departments"], list)


@pytest.mark.asyncio
async def test_create_department(client):
    response = await client.post(
        "/api/departments",
        json={
            "name": "Test Department",
            "code": "TEST",
            "description": "A test department",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["department"]["name"] == "Test Department"
    assert data["department"]["code"] == "TEST"


@pytest.mark.asyncio
async def test_create_contact(client):
    response = await client.post(
        "/api/contacts",
        json={
            "phone_number": "+15551234567",
            "name": "Test User",
            "preferred_language": "es",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["contact"]["phone_number"] == "+15551234567"
    assert data["contact"]["preferred_language"] == "es"


@pytest.mark.asyncio
async def test_list_contacts(client):
    # Create a contact first
    await client.post(
        "/api/contacts",
        json={"phone_number": "+15559999999", "name": "Search Me"},
    )

    response = await client.get("/api/contacts?search=Search")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_calls_empty(client):
    response = await client.get("/api/calls")
    assert response.status_code == 200
    data = response.json()
    assert data["calls"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_appointments_empty(client):
    response = await client.get("/api/appointments")
    assert response.status_code == 200
    data = response.json()
    assert data["appointments"] == []


@pytest.mark.asyncio
async def test_get_nonexistent_appointment(client):
    response = await client.get("/api/appointments/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_stats(client):
    response = await client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "today_calls" in data
    assert "active_calls" in data
    assert "today_appointments" in data
    assert "total_contacts" in data


@pytest.mark.asyncio
async def test_activity_feed(client):
    response = await client.get("/api/dashboard/activity")
    assert response.status_code == 200
    data = response.json()
    assert "activities" in data
