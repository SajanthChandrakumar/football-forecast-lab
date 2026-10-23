"""Small shared authorization boundary for maintenance-style routes."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


def require_cron_secret(request: Request, configured_secret: str) -> None:
    authorization = request.headers.get("authorization", "")
    presented = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not configured_secret or not hmac.compare_digest(presented.encode(), configured_secret.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def shared_write_guard(request, call_next):
    """Fail closed for routes that mutate shared user-managed data."""
    import os
    from starlette.responses import JSONResponse
    path = request.url.path.rstrip('/')
    protected = path in {
        '/api/archive/user_tip', '/api/archive/historical_tip', '/api/custom_bot',
        '/api/freeze', '/api/predict/freeze',
    } or path.startswith('/api/pool-context/')
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and protected:
        try:
            require_cron_secret(request, os.getenv('EDITOR_TOKEN', ''))
        except HTTPException:
            return JSONResponse({'detail': 'Editor authorization required'}, status_code=401)
    return await call_next(request)


def client_ip(request):
    """Use the ASGI client; proxy trust belongs in server configuration."""
    return request.client.host if request.client else 'unknown'
