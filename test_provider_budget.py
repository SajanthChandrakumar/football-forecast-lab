from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
from types import SimpleNamespace

import pytest

from src import quota_store


class AtomicCollection:
    def __init__(self):
        self.documents = {}
        self.lock = Lock()

    def find_one(self, query):
        with self.lock:
            return deepcopy(self.documents.get(query['_id']))

    def insert_one(self, document):
        with self.lock:
            if document['_id'] in self.documents:
                raise RuntimeError('duplicate key')
            self.documents[document['_id']] = deepcopy(document)

    def update_one(self, query, update, upsert=False):
        with self.lock:
            document = self.documents.get(query['_id'])
            if document is None or any(document.get(k) != v for k, v in query.items()):
                return SimpleNamespace(matched_count=0)
            document.update(deepcopy(update['$set']))
            return SimpleNamespace(matched_count=1)


@pytest.fixture
def budget(monkeypatch):
    collection = AtomicCollection()
    monkeypatch.setattr(quota_store, '_get_collection', lambda: collection)
    return collection


def test_odds_all_competitions_and_restarts_share_credit_cap(budget):
    for _ in range(200):
        quota_store.reserve_request('odds', 2, now=1000)
    with pytest.raises(quota_store.ProviderBudgetExceeded):
        quota_store.reserve_request('odds', 2, now=1001)
    assert sum(cost for at, cost in budget.documents['provider_budget:odds']['requests']) == 400
    assert quota_store.reserve_request('odds', 2, now=1000 + 31 * 86400) == 0


def test_daily_budget_and_minute_pacing_are_shared(budget):
    for index in range(80):
        assert quota_store.reserve_request('football', now=1000 + index * 7) == 0
    with pytest.raises(quota_store.ProviderBudgetExceeded):
        quota_store.reserve_request('football', now=2000)
    assert quota_store.reserve_request('football', now=1000 + 86400) == 0


def test_parallel_reservations_do_not_exceed_budget(budget):
    def reserve(_):
        try:
            quota_store.reserve_request('odds', 2, now=1000)
            return True
        except quota_store.ProviderBudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(240))) == 200


def test_unknown_store_fails_closed(monkeypatch):
    monkeypatch.setattr(quota_store, '_get_collection', lambda: None)
    with pytest.raises(quota_store.ProviderBudgetExceeded, match='unavailable'):
        quota_store.reserve_request('odds', 2)


def test_known_provider_remaining_preserves_headroom(budget):
    budget.documents['quota_odds'] = {'_id': 'quota_odds', 'data': {'remaining': '101'}, 'observed_at': 1000}
    with pytest.raises(quota_store.ProviderBudgetExceeded, match='reserve'):
        quota_store.reserve_request('odds', 2, now=1000)
    assert budget.documents['provider_budget:odds']['requests'] == []


def test_both_engines_and_football_client_reserve_before_http(monkeypatch, budget):
    from src.odds_engine import OddsApiEngine
    from src.odds_engine_apifootball import OddsApiEngine as FootballEngine
    from src.services.team_form import ApiFootballClient
    monkeypatch.setenv('ODDS_API_KEY', 'test-key')
    monkeypatch.setenv('API_FOOTBALL_KEY', 'test-key')
    monkeypatch.setattr(quota_store, 'reserve_request', lambda *args, **kwargs: (_ for _ in ()).throw(quota_store.ProviderBudgetExceeded('blocked')))
    monkeypatch.setattr('requests.get', lambda *args, **kwargs: pytest.fail('HTTP sent despite exhausted budget'))
    for request in (lambda: OddsApiEngine().get_competition_odds('epl2026'),
                    lambda: OddsApiEngine().get_competition_odds('ucl2026'),
                    lambda: FootballEngine()._request('/fixtures'),
                    lambda: ApiFootballClient('test-key').request('/fixtures')):
        with pytest.raises(quota_store.ProviderBudgetExceeded):
            request()


def test_odds_connection_errors_never_expose_key(monkeypatch, budget):
    import requests
    from src.odds_engine import OddsApiEngine
    monkeypatch.setenv('ODDS_API_KEY', 'secret-test-token')
    def fail(*args, **kwargs):
        raise requests.ConnectionError('URL?apiKey=secret-test-token')
    monkeypatch.setattr('requests.get', fail)
    with pytest.raises(RuntimeError) as error:
        OddsApiEngine().get_competition_odds('epl2026')
    assert 'secret-test-token' not in str(error.value)
    assert budget.documents['provider_budget:odds']['requests'][0][1] == 2
