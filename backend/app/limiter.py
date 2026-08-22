from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import is_production_grade
from app.services.auth.client_ip import resolve_client_ip


def rate_limit_key(request: Request) -> str:
    """Bucket requests by the real client, not by the reverse proxy.

    slowapi's ``get_remote_address`` reads the socket peer. Behind Caddy
    that is the proxy for every visitor, which collapses every limit in
    the app into one shared counter — so a handful of logins would 429
    the whole site while doing nothing to bound a single abuser.
    ``resolve_client_ip`` reads ``X-Forwarded-For`` only when the peer is
    a configured trusted proxy, so the key cannot be spoofed by a client
    connecting directly.
    """
    return resolve_client_ip(request) or get_remote_address(request)


# Rate limits apply in ci/staging/production only — local dev should not 429 loops.
limiter = Limiter(key_func=rate_limit_key, enabled=is_production_grade())
