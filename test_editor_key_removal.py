"""Shared editing reaches its handler without an editor token; admin refresh stays guarded."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.fixture
def api_module(monkeypatch):
    import pymongo

    class EmptyDatabase:
        def __getitem__(self, _name):
            return self

        def find_one(self, *_args, **_kwargs):
            return None

    monkeypatch.setenv('MONGO_URI', 'mongodb://unused-local-test')
    monkeypatch.setenv('ODDS_API_KEY', 'unused-test-provider-key')
    monkeypatch.setenv('ADMIN_REFRESH_TOKEN', 'test-admin-token')
    monkeypatch.delenv('API_FOOTBALL_KEY', raising=False)
    monkeypatch.delenv('USE_API_FOOTBALL', raising=False)
    monkeypatch.setattr(pymongo, 'MongoClient', lambda *_args, **_kwargs: EmptyDatabase())
    name = 'src.api_editor_key_removal_test'
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / 'src' / 'api.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _post(app, path, payload, competition='epl2026'):
    async def run():
        body = json.dumps(payload).encode()
        sent_body = False
        events = []

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await asyncio.Event().wait()

        async def send(message):
            events.append(message)

        await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                   'method': 'POST', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                   'query_string': ('competition=' + competition).encode(), 'root_path': '',
                   'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())],
                   'client': ('127.0.0.1', 12345), 'server': ('testserver', 80)}, receive, send)
        status = next(event['status'] for event in events if event['type'] == 'http.response.start')
        data = b''.join(event.get('body', b'') for event in events if event['type'] == 'http.response.body')
        return status, json.loads(data)

    return asyncio.run(run())


@pytest.mark.parametrize('configured_token', [None, 'obsolete-editor-token'])
def test_shared_tip_save_does_not_require_an_editor_key(api_module, monkeypatch, configured_token):
    if configured_token is None:
        monkeypatch.delenv('EDITOR_TOKEN', raising=False)
    else:
        monkeypatch.setenv('EDITOR_TOKEN', configured_token)
    saved = []

    def save(_archive, _cache, match_id, user_tip, competition, **_kwargs):
        saved.append((match_id, user_tip, competition.id))
        return {'ok': True}

    monkeypatch.setattr(api_module, 'save_shared_tip', save)
    monkeypatch.setattr(api_module, 'save_historical_tip', lambda _archives, match_id, user_tip, competition, **_kwargs: {'ok': True})
    for competition in ('wc2026', 'ucl2026', 'epl2026'):
        status, body = _post(api_module.app, '/api/archive/user_tip',
                             {'match_id': 'test-fixture', 'user_tip': '2:1'}, competition)
        assert status == 200
        assert body == {'ok': True}
        status, body = _post(api_module.app, '/api/archive/historical_tip',
                             {'match_id': 'test-fixture', 'user_tip': '2:1'}, competition)
        assert status == 200
        assert body == {'ok': True}
    assert saved == [('test-fixture', '2:1', competition) for competition in ('wc2026', 'ucl2026', 'epl2026')]


def test_admin_provider_refresh_still_requires_its_own_key(api_module):
    status, _body = _post(api_module.app, '/api/internal/manual-refresh', {})
    assert status == 401
