from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.competitions import competition_document_id
from src.routes.maintenance import init_router
from src.services.maintenance import run_maintenance
from src.services.match_intelligence import refresh_match_intelligence
from src.services.snapshots import append_odds_snapshot
from src.quota_store import ProviderBudgetExceeded
from test_task2_providers import MemoryCollection

NOW = datetime(2026, 10, 10, 10, 30, tzinfo=timezone.utc)


def fixture():
    return {'id': 'pl-next', 'home_team': 'Arsenal', 'away_team': 'Chelsea',
            'commence_time': (NOW + timedelta(hours=4)).isoformat(), 'completed': False}


class Provider:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def get_competition_odds(self, competition, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return [{**fixture(), 'odds': {'home': 1.9, 'draw': 3.4, 'away': 4.2}}]


def cache():
    return MemoryCollection([
        {'_id': competition_document_id('epl2026', 'matches_cache'), 'data': [fixture()],
         'observed_at': NOW.isoformat(), 'status': 'fresh'},
        {'_id': competition_document_id('epl2026', 'odds_discovery_state'), 'observed_at': NOW.isoformat()},
        {'_id': competition_document_id('epl2026', 'clubelo_ratings'), 'observed_at': NOW.isoformat(),
         'status': 'fresh', 'rows': [{'team_name': 'Arsenal', 'elo_rating': 1900}]},
    ])


def request(token=''):
    return Request({'type': 'http', 'method': 'POST', 'path': '/api/internal/manual-refresh',
                    'headers': [(b'authorization', ('Bearer '+token).encode())], 'query_string': b''})


def endpoint(router):
    return next(route.endpoint for route in router.routes if route.path == '/api/internal/manual-refresh')


def test_manual_refresh_requires_its_own_key_before_any_provider_call():
    provider = Provider()
    route = endpoint(init_router(cache(), provider, cron_secret='cron-only', admin_refresh_token='admin-only'))
    for token in ['', 'wrong', 'cron-only', 'ü']:
        with pytest.raises(HTTPException) as error:
            route(request(token), competition='epl2026')
        assert error.value.status_code == 401
    assert provider.calls == 0


def test_unconfigured_manual_refresh_is_disabled():
    route = endpoint(init_router(cache(), Provider(), admin_refresh_token=''))
    with pytest.raises(HTTPException) as error:
        route(request('anything'), competition='epl2026')
    assert error.value.status_code == 503


def test_manual_refresh_bypasses_due_windows_and_cache_ttls_but_keeps_daily_scheduler(monkeypatch):
    store, provider, calls = cache(), Provider(), []
    def fixtures(**kwargs):
        calls.append(('fixtures', kwargs.get('use_cache')))
        return [fixture()]
    def ratings(collection, **kwargs):
        calls.append(('elo', None))
        return {'status': 'fresh', 'source': 'clubelo', 'observed_at': NOW.isoformat(), 'rows': []}
    result = run_maintenance(store, provider, competition='epl2026', now=NOW,
                             manual=True, fixture_fetcher=fixtures, clubelo_ingestor=ratings)
    assert result['status'] == 'success'
    assert provider.calls == 1
    assert calls == [('fixtures', False), ('elo', None)]
    snapshots = [row for row in store.inserts if row.get('bucket') == 'manual']
    assert len(snapshots) == 1
    assert snapshots[0]['observed_at'] == NOW.isoformat()
    assert snapshots[0]['odds']['home'] == 1.9
    scheduled = run_maintenance(store, provider, competition='epl2026', now=NOW+timedelta(seconds=10))
    assert scheduled['provider_calls'] == 0
    assert provider.calls == 1


def test_manual_refresh_cooldown_is_server_side_and_survives_provider_failure():
    store, provider = cache(), Provider(error=ProviderBudgetExceeded('quota exhausted'))
    result = run_maintenance(store, provider, competition='epl2026', now=NOW, manual=True)
    assert result['reason'] == 'provider_budget_blocked'
    before = deepcopy(store.documents)
    second = run_maintenance(store, provider, competition='epl2026', now=NOW+timedelta(seconds=10), manual=True)
    assert second['reason'] == 'cooldown'
    assert second['retry_after'] == 50
    assert provider.calls == 1
    assert store.documents == before
    run_maintenance(store, provider, competition='epl2026', now=NOW+timedelta(seconds=60), manual=True)
    assert provider.calls == 2


def test_manual_refresh_returns_partial_sources_without_exposing_provider_error_urls():
    store, provider = cache(), Provider(error=RuntimeError('url?apiKey=do-not-expose'))
    route = endpoint(init_router(store, provider, admin_refresh_token='admin-only', now_fn=lambda: NOW))
    # Substitute free providers; this test must never contact live services.
    import src.routes.maintenance as router_module
    original = router_module.run_maintenance
    def isolated(*args, **kwargs):
        kwargs['fixture_fetcher'] = lambda **options: [fixture()]
        kwargs['clubelo_ingestor'] = None
        kwargs['standings_fetcher'] = None
        return original(*args, **kwargs)
    from unittest.mock import patch
    with patch.object(router_module, 'run_maintenance', isolated):
        result = route(request('admin-only'), competition='epl2026')
    assert result['status'] == 'partial'
    odds = next(source for source in result['sources'] if source['id'] == 'odds')
    assert odds['status'] == 'failed'
    assert odds['observed_at'] is None
    assert 'do-not-expose' not in str(result)


def test_manual_refresh_does_not_change_saved_tips_or_frozen_forecasts():
    store, provider = cache(), Provider()
    saved = {'prediction': {'user_tip': '1:0', 'top_tip': '2:1', 'evaluation_forecast': {'captured_at': NOW.isoformat()}}}
    archive = MemoryCollection([{'_id': 'pl-next', **deepcopy(saved)}])
    before = deepcopy(archive.documents)
    run_maintenance(store, provider, archive_collections=archive, competition='epl2026', now=NOW, manual=True)
    assert archive.documents == before


def test_manual_lineup_refresh_rechecks_imminent_matches_after_scheduled_attempt():
    match = {**fixture(), 'commence_time': (NOW+timedelta(minutes=35)).isoformat()}
    store = MemoryCollection([{'_id': competition_document_id('epl2026', 'match_intelligence:pl-next'),
                               'attempted_buckets': ['t35', 't15'], 'data': {'status': 'unavailable'}}])
    calls = []
    result = refresh_match_intelligence(store, [match, {**fixture(), 'id': 'distant'}],
                                        competition='epl2026', now=NOW, manual=True,
                                        espn_fetcher=lambda event_id: calls.append(event_id) or {})
    assert result['espn_calls'] >= 1
    assert 'pl-next' in calls


def test_manual_snapshot_is_distinct_from_scheduled_buckets():
    store = MemoryCollection()
    append_odds_snapshot(store, 'epl2026', 'pl-next', 'manual', NOW, {'home': 1.9})
    assert store.inserts[0]['bucket'] == 'manual'


def test_failed_lineup_refresh_never_claims_old_lineups_are_new():
    match = {**fixture(), 'commence_time': (NOW+timedelta(minutes=35)).isoformat()}
    old = {'status': 'fresh', 'observed_at': (NOW-timedelta(days=1)).isoformat(),
           'lineups': {'Arsenal': {'starters': [{'name': 'A'}]}, 'Chelsea': {'starters': [{'name': 'B'}]}}}
    store = MemoryCollection([{'_id': competition_document_id('epl2026', 'match_intelligence:pl-next'), 'data': old}])
    def unavailable(_):
        raise RuntimeError('offline')
    result = refresh_match_intelligence(store, [match], competition='epl2026', now=NOW,
                                        manual=True, espn_fetcher=unavailable)
    assert result['confirmed'] == 0
    assert result['failed_calls'] == 1
    assert result['observed_at'] is None
    assert store.find_one({'_id': competition_document_id('epl2026', 'match_intelligence:pl-next')})['data'] == old


def test_manual_lineups_prioritize_near_kickoff_and_skip_invalid_dates():
    matches = [{**fixture(), 'id': str(i), 'commence_time': (NOW+timedelta(hours=i)).isoformat()} for i in range(1, 15)]
    matches += [{**fixture(), 'id': 'missing', 'commence_time': None}, {**fixture(), 'id': 'invalid', 'commence_time': 'unknown'}]
    calls = []
    result = refresh_match_intelligence(MemoryCollection(), matches, competition='ucl2026', now=NOW,
                                        manual=True, espn_fetcher=lambda event_id: calls.append(event_id) or {})
    assert result['espn_calls'] == 12
    assert calls == [str(i) for i in range(1, 13)]


def test_manual_standings_bypass_daily_cache():
    store = cache()
    store.update_one({'_id': competition_document_id('epl2026', 'standings_cache')},
                     {'$set': {'observed_at': NOW.isoformat(), 'data': [{'rows': [{'points': 1}]}]}}, upsert=True)
    calls = []
    result = run_maintenance(store, Provider(), competition='epl2026', now=NOW, manual=True,
                             standings_fetcher=lambda **kwargs: calls.append(kwargs) or [{'rows': [{'points': 3}]}])
    assert len(calls) == 1
    assert result['standings_status']['status'] == 'fresh'
    assert store.find_one({'_id': competition_document_id('epl2026', 'standings_cache')})['data'][0]['rows'][0]['points'] == 3


def test_empty_manual_fixture_response_retains_data_without_claiming_freshness():
    store = cache()
    before = deepcopy(store.find_one({'_id': competition_document_id('epl2026', 'matches_cache')}))
    result = run_maintenance(store, Provider(), competition='epl2026', now=NOW+timedelta(hours=1),
                             manual=True, fixture_fetcher=lambda **kwargs: [])
    assert result['fixture_status']['status'] == 'stale'
    assert result['fixture_status']['observed_at'] == before['observed_at']
    assert store.find_one({'_id': before['_id']})['data'][0]['home_team'] == 'Arsenal'


def test_manual_snapshot_is_returned_in_read_only_history():
    from src.services.odds_history import get_odds_history
    store = cache()
    append_odds_snapshot(store, 'epl2026', 'pl-next', 'manual', NOW, {'home': 1.9, 'draw': 3.4, 'away': 4.2})
    result = get_odds_history(store, 'pl-next', competition='epl2026')
    assert result['status'] == 'available'
    assert result['observations'][0]['bucket'] == 'manual'


def test_manual_route_excludes_world_cup_and_returns_lease_retry_after(monkeypatch):
    provider = Provider()
    store = cache()
    route = endpoint(init_router(store, provider, admin_refresh_token='admin', now_fn=lambda: NOW))
    with pytest.raises(HTTPException) as error:
        route(request('admin'), competition='wc2026')
    assert error.value.status_code == 422
    assert provider.calls == 0
    store.insert_one({'_id': competition_document_id('epl2026', 'maintenance_lease'),
                      'lease_token': 'other-worker', 'lease_until': (NOW+timedelta(seconds=100)).isoformat()})
    with pytest.raises(HTTPException) as error:
        route(request('admin'), competition='epl2026')
    assert error.value.status_code == 429
    assert int(error.value.headers['Retry-After']) > 0
    assert provider.calls == 0


def test_manual_route_uses_execution_clock_in_production(monkeypatch):
    import src.routes.maintenance as module
    seen = []
    monkeypatch.setattr(module, 'run_maintenance', lambda *args, **kwargs: seen.append(kwargs['now']) or {})
    route = endpoint(init_router(cache(), Provider(), admin_refresh_token='admin'))
    route(request('admin'), competition='epl2026')
    assert seen == [None]


def test_slow_manual_refresh_uses_acquisition_time_and_completion_deadlines(monkeypatch):
    import src.services.maintenance as module
    clock = [NOW]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]
    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(module, '_persist_club_predictions', lambda *args: 0)
    monkeypatch.setattr(module, 'PredictionService', lambda engine: object())
    deadlines = []
    monkeypatch.setattr(module, '_freeze_due_forecasts', lambda *args: deadlines.append(args[-1]) or 0)
    monkeypatch.setattr(module, 'capture_archive_forecasts', lambda *args, **kwargs: deadlines.append(kwargs['now']) or 0)
    class SlowProvider(Provider):
        def get_competition_odds(self, *args, **kwargs):
            clock[0] += timedelta(minutes=2)
            return super().get_competition_odds(*args, **kwargs)
    store = cache()
    result = run_maintenance(store, SlowProvider(), competition='epl2026', manual=True,
                             math_engine=object(), archive_collections=MemoryCollection())
    assert result['odds_status']['observed_at'] == (NOW+timedelta(minutes=2)).isoformat()
    assert next(row for row in store.inserts if row.get('bucket') == 'manual')['observed_at'] == clock[0].isoformat()
    assert deadlines == [clock[0], clock[0]]


def test_manual_scoreboard_rejects_partial_year_failure():
    import requests
    from src.services.espn_data import get_scoreboard
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'events': []}
    def fetch(*args, **kwargs):
        if kwargs['params']['dates'] == '2027':
            raise requests.Timeout('second year unavailable')
        return Response()
    with pytest.raises(requests.Timeout):
        get_scoreboard(competition='epl2026', now=NOW, request_get=fetch, use_cache=False, require_complete=True)
    # Scheduled ingestion retains its existing tolerant behavior.
    assert get_scoreboard(competition='epl2026', now=NOW, request_get=fetch, use_cache=False) == []
