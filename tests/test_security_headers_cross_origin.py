import pytest


@pytest.mark.asyncio
async def test_security_headers_include_cross_origin_isolation(client):
    """Security middleware emits cross-origin isolation hardening headers."""
    resp = await client.get("/api/health")

    assert resp.status_code == 200
    assert resp.headers.get("cross-origin-opener-policy") == "same-origin"
    assert resp.headers.get("cross-origin-resource-policy") == "same-origin"
