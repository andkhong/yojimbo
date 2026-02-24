import pytest


@pytest.mark.asyncio
async def test_get_config_invalid_key_is_i18n_ready(client):
    response = await client.get("/api/config/agent/__bad_key__")

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["message_key"] == "agent_config.invalid_key"
    assert detail["params"]["key"] == "__bad_key__"


@pytest.mark.asyncio
async def test_get_config_missing_key_is_i18n_ready(client):
    response = await client.get("/api/config/agent/timezone")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message_key"] == "agent_config.key_not_set"
    assert detail["params"]["key"] == "timezone"


@pytest.mark.asyncio
async def test_delete_config_missing_key_is_i18n_ready(client):
    response = await client.delete("/api/config/agent/timezone")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message_key"] == "agent_config.key_not_set"
    assert detail["params"]["key"] == "timezone"
