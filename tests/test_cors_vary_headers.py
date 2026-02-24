from starlette.responses import Response

from app.middleware.security_headers import SecurityHeadersMiddleware


def test_cors_vary_origin_dedupes_case_insensitively():
    """Existing lowercase 'origin' token should not produce duplicate Vary entries."""
    resp = Response(status_code=204)
    resp.headers["Vary"] = "Accept-Encoding, origin"

    SecurityHeadersMiddleware._add_cors_headers(
        response=resp,
        origin="https://dashboard.city.gov",
        is_debug=False,
        allowed_origins=["https://dashboard.city.gov"],
    )

    vary = resp.headers.get("vary", "")
    parts = [part.strip() for part in vary.split(",") if part.strip()]
    assert "Accept-Encoding" in parts
    assert sum(1 for part in parts if part.lower() == "origin") == 1
