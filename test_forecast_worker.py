from copy import deepcopy
from datetime import datetime, timedelta
import importlib

from test_model_evaluation import MemoryCollection, FreezeService as BaseService, _auto_capture_fixtures
from src.services.forecast_evaluation import evaluate_archive


class FreezeService(BaseService):
    model_version = 'test'

    def evaluation_probabilities(self, odds, elo):
        from src.services.prediction import PredictionService
        return PredictionService(self.math_engine).evaluation_probabilities(odds, elo)


def test_background_capture_is_immutable_preserves_tips_and_becomes_evaluable():
    module = importlib.import_module('src.services.forecast_worker')
    cache = _auto_capture_fixtures()
    archive = MemoryCollection([{
        '_id': 'game-auto',
        'metadata': {'home_team': 'Bayern Munich', 'away_team': 'Arsenal', 'commence_time': '2026-10-01T12:00:00+00:00'},
        'prediction': {'user_tip': '1:1', 'top_tip': '3:2'},
        'post_match_result': {'status': 'pending', 'actual_score': None},
    }])
    now = datetime.fromisoformat('2026-10-01T11:50:00+00:00')
    service = FreezeService()
    first = module.capture_competition(cache, archive, service, 'ucl2026', now=now)
    saved = deepcopy(archive.find_one({'_id': 'game-auto'}))
    second = module.capture_competition(cache, archive, service, 'ucl2026', now=now + timedelta(minutes=1))
    assert first['forecasts_frozen'] == 1
    assert second['forecasts_frozen'] == 0
    assert archive.find_one({'_id': 'game-auto'}) == saved
    assert saved['prediction']['user_tip'] == '1:1'
    assert saved['prediction']['top_tip'] == '3:2'
    saved['post_match_result'] = {'status': 'completed', 'actual_score': '1:0'}
    assert evaluate_archive([saved], competition='ucl2026')['common_sample_count'] == 1
    assert cache.find_one({'_id': 'ucl2026:forecast_capture_status'})['last_run_at'] == (now + timedelta(minutes=1)).isoformat()


def test_worker_cannot_retrofit_past_games_and_reports_next_capture_window():
    module = importlib.import_module('src.services.forecast_worker')
    cache = _auto_capture_fixtures()
    archive = MemoryCollection()
    early = datetime.fromisoformat('2026-10-01T10:00:00+00:00')
    status = module.capture_competition(cache, archive, FreezeService(), 'ucl2026', now=early)
    assert status['next_capture_at'] == '2026-10-01T11:45:00+00:00'
    module.capture_competition(cache, archive, FreezeService(), 'ucl2026', now=early + timedelta(hours=3))
    assert archive.documents == {}


def test_missing_elo_does_not_permanently_freeze_an_incomplete_forecast():
    module = importlib.import_module('src.services.forecast_worker')
    cache = _auto_capture_fixtures()
    ratings = cache.documents.pop('ucl2026:clubelo_ratings')
    archive = MemoryCollection()
    now = datetime.fromisoformat('2026-10-01T11:46:00+00:00')
    first = module.capture_competition(cache, archive, FreezeService(), 'ucl2026', now=now)
    assert first['forecasts_frozen'] == 0
    assert archive.documents == {}
    cache.documents[ratings['_id']] = ratings
    later = module.capture_competition(cache, archive, FreezeService(), 'ucl2026', now=now + timedelta(minutes=1))
    assert later['forecasts_frozen'] == 1


def test_worker_waits_when_archived_elo_has_no_source():
    module = importlib.import_module('src.services.forecast_worker')
    cache = _auto_capture_fixtures()
    archive = MemoryCollection([{
        '_id': 'game-auto',
        'metadata': {'commence_time': '2026-10-01T12:00:00+00:00'},
        'pre_match_snapshot': {'elo_state': {'home_rating': 1600, 'away_rating': 1500, 'observed_at': '2026-10-01T10:00:00+00:00'}},
        'prediction': {'user_tip': '1:1'},
    }])
    status = module.capture_competition(cache, archive, FreezeService(), 'ucl2026', now=datetime.fromisoformat('2026-10-01T11:46:00+00:00'))
    assert status['forecasts_frozen'] == 0
    assert 'frozen_at' not in archive.find_one({'_id': 'game-auto'})['prediction']


def test_evaluation_endpoint_exposes_only_safe_worker_status_fields():
    from src.routes.model_evaluation import init_router
    cache = MemoryCollection([{
        '_id': 'ucl2026:forecast_capture_status', 'status': 'running',
        'last_run_at': '2026-10-01T10:00:00+00:00', 'next_capture_at': '2026-10-01T11:45:00+00:00',
        'interval_seconds': 60, 'internal_detail': 'not public',
    }])
    route = next(route for route in init_router({'ucl2026': MemoryCollection()}, cache_collections={'ucl2026': cache}).routes if route.path == '/api/model-evaluation')
    result = route.endpoint(competition='ucl2026')
    assert result['capture_status'] == {
        'status': 'running', 'last_run_at': '2026-10-01T10:00:00+00:00',
        'next_capture_at': '2026-10-01T11:45:00+00:00', 'interval_seconds': 60,
        'last_successful_at': None, 'error': None,
    }
