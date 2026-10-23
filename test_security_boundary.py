import asyncio
import pytest
from fastapi import FastAPI
from src.services.auth import shared_write_guard, client_ip


def test_shared_writes_fail_closed(monkeypatch):
    from starlette.requests import Request
    from starlette.responses import Response
    async def next_handler(request):
        return Response(status_code=204)
    def call(token='', path='/api/archive/user_tip'):
        request = Request({'type': 'http', 'method': 'POST', 'path': path,
                           'headers': [(b'authorization', ('Bearer ' + token).encode())]})
        return asyncio.run(shared_write_guard(request, next_handler)).status_code
    monkeypatch.delenv('EDITOR_TOKEN', raising=False)
    assert call() == 401
    monkeypatch.setenv('EDITOR_TOKEN', 'editor-secret')
    assert call('wrong') == 401
    assert call('editor-secret') == 204
    assert call('wrong', '/api/archive/user_tip/') == 401
    assert call('', '/api/predict') == 204
    assert call('', '/api/freeze') == 401
    assert call('', '/api/predict/freeze') == 401


def test_forwarded_ip_is_not_trusted():
    from starlette.requests import Request
    request = Request({'type': 'http', 'client': ('127.0.0.1', 123), 'headers': [(b'x-forwarded-for', b'fake')]})
    assert client_ip(request) == '127.0.0.1'
