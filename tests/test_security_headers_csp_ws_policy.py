"""Focused regression tests for CSP websocket policy hardening."""

import pytest


@pytest.mark.asyncio
async def test_csp_allows_ws_only_in_debug(client, monkeypatch):
    """Debug CSP keeps ws: for local tooling; production CSP removes it."""
    monkeypatch.setenv("DEBUG", "true")
    debug_resp = await client.get("/api/health")
    debug_csp = debug_resp.headers.get("content-security-policy", "")
    assert "connect-src" in debug_csp
    assert " ws:" in debug_csp

    monkeypatch.setenv("DEBUG", "false")
    prod_resp = await client.get("/api/health")
    prod_csp = prod_resp.headers.get("content-security-policy", "")
    assert "connect-src" in prod_csp
    assert " wss:" in prod_csp
    assert " ws:" not in prod_csp
