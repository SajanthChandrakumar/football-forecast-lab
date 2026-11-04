"""Small shared authorization boundary for maintenance-style routes."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


def require_cron_secret(request: Request, configured_secret: str) -> None:
    authorization = request.headers.get("authorization", "")
    presented = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not configured_secret or not hmac.compare_digest(presented.encode(), configured_secret.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")



def client_ip(request):
    """Use the ASGI client; proxy trust belongs in server configuration."""
    return request.client.host if request.client else 'unknown'
