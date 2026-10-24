from copy import deepcopy
from datetime import datetime, timedelta, timezone

from src.services import espn_data
from src.services.maintenance import run_maintenance, _recent_club_fixtures
from test_model_evaluation import MemoryCollection as BaseCollection
from src.competitions import get_competition
from test_task2_providers import _event


class MemoryCollection(BaseCollection):
    def insert_one(self, document):
        if document['_id'] in self.documents:
            raise RuntimeError('duplicate key')
        self.documents[document['_id']] = deepcopy(document)

    def delete_one(self, query):
        self.documents.pop(query['_id'], None)


def test_ucl_year_request_includes_results_beyond_espns_first_hundred_games():
    events = [_event(str(i), '2026-01-01T12:00:00Z') for i in range(100)]
    recent = _event('new-final', '2026-10-13T19:00:00Z')
    recent['competitions'][0]['status']['type'] = {'completed': True, 'detail': 'FT'}
    recent['competitions'][0]['competitors'][0]['score'] = '2'
    recent['competitions'][0]['competitors'][1]['score'] = '0'
    events.append(recent)
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'events': self.events}
    def get(url, params, timeout):
        response = Response()
        response.events = events[:params.get('limit', 100)]
        return response
    games = espn_data.get_scoreboard(competition='ucl2026', now=datetime(2026, 10, 20, tzinfo=timezone.utc), days_back=20, days_forward=0, use_cache=False, request_get=get)
    assert len(games) == 1
    assert games[0]['completed'] is True
    assert games[0]['actual_score'] == '2:0'


def test_overdue_results_are_rechecked_even_more_than_six_hours_after_kickoff():
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    cache = MemoryCollection([{'_id': 'ucl2026:matches_cache', 'status': 'fresh', 'observed_at': (now-timedelta(minutes=20)).isoformat(), 'data': [
        {'id': 'game', 'commence_time': (now-timedelta(days=7)).isoformat(), 'completed': False},
    ]}])
    assert _recent_club_fixtures(cache, get_competition('ucl2026'), now) is None


def test_results_only_updates_archive_points_without_paid_calls_or_tip_changes():
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    fixture = {'id': 'game', 'home_team': 'Home', 'away_team': 'Away', 'commence_time': '2026-10-13T19:00:00Z', 'round': 'league phase', 'completed': False}
    cache = MemoryCollection([{'_id': 'ucl2026:matches_cache', 'data': [fixture]}])
    prediction = {'user_tip': '2:0', 'top_tip': '1:0', 'evaluation_forecast': {'captured_at': '2026-10-13T18:50:00Z'}, 'bots': {'broker': {'tip': '2:0'}}}
    archive = MemoryCollection([{'_id': 'game', 'metadata': {}, 'prediction': deepcopy(prediction), 'post_match_result': {'status': 'pending'}}])
    class NoPaidCalls:
        def get_competition_odds(self, *args, **kwargs):
            raise AssertionError('results must not request paid odds')
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        return [{**fixture, 'completed': True, 'actual_score': '2:0'}]
    result = run_maintenance(cache, NoPaidCalls(), archive_collections=archive, competition='ucl2026', now=now, fixture_fetcher=fetch, results_only=True)
    saved = archive.find_one({'_id': 'game'})
    assert result['archived_results'] == 1
    assert result['provider_calls'] == 0
    assert saved['post_match_result']['status'] == 'completed'
    assert saved['post_match_result']['points_earned'] == 10
    assert saved['post_match_result']['bot_points']['broker'] == 10
    assert saved['prediction'] == prediction
    assert calls[0]['require_complete'] is True
    again = run_maintenance(cache, NoPaidCalls(), archive_collections=archive, competition='ucl2026', now=now, fixture_fetcher=fetch, results_only=True)
    assert again['archived_results'] == 0
    assert len(calls) == 1


def test_already_completed_games_with_missing_points_are_repaired():
    from src.services.maintenance import _sync_completed_results
    fixture = {'id': 'game', 'home_team': 'Home', 'away_team': 'Away', 'commence_time': '2026-10-13T19:00:00Z', 'round': 'league phase', 'completed': True, 'actual_score': '2:0'}
    archive = MemoryCollection([{'_id': 'game', 'prediction': {'user_tip': '2:0', 'top_tip': '2:0', 'bots': {'broker': {'tip': '2:0'}}}, 'post_match_result': {'status': 'completed', 'actual_score': '2:0'}}])
    assert _sync_completed_results(archive, [fixture], 'ucl2026') == 1
    result = archive.find_one({'_id': 'game'})['post_match_result']
    assert result['points_earned'] == result['algo_points'] == result['bot_points']['broker'] == 10
    assert _sync_completed_results(archive, [fixture], 'ucl2026') == 0
