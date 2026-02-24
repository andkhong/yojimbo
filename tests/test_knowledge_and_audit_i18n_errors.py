import pytest


@pytest.mark.asyncio
async def test_get_knowledge_not_found_error_is_i18n_ready(client):
    response = await client.get("/api/knowledge/99999")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message_key"] == "knowledge.not_found"
    assert detail["params"]["entry_id"] == 99999


@pytest.mark.asyncio
async def test_get_audit_log_not_found_error_is_i18n_ready(client):
    response = await client.get("/api/audit-logs/99999")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message_key"] == "audit_logs.not_found"
    assert detail["params"]["log_id"] == 99999
