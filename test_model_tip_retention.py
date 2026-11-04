from copy import deepcopy
from datetime import datetime, timedelta, timezone

from src.competitions import competition_document_id
from test_user_tips import MemoryCollection, cache_fixture

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def fixture_store(kickoff, observed=None):
    match = cache_fixture(commence_time=kickoff.isoformat(), raw_match={'commence_time': kickoff.isoformat()},
                          observed_at=(observed or NOW).isoformat(), status='fresh', model_version='prediction-v1')
    return MemoryCollection([{'_id': competition_document_id('epl2026', 'matches_cache'),
                              'observed_at': (observed or NOW).isoformat(), 'data': [match]}])


def test_maintenance_archives_new_model_tip_before_freeze(monkeypatch):
    import src.services.maintenance as module
    store = fixture_store(NOW+timedelta(minutes=10))
    archive = MemoryCollection()
    def freeze(*args):
        assert archive.documents['fixture-1']['prediction']['top_tip'] == '2:1'
        assert archive.documents['fixture-1']['prediction']['user_tip'] is None
        return 1
    monkeypatch.setattr(module, 'freeze_due_comparisons', freeze)
    assert module._freeze_due_forecasts(store, archive, object(), 'epl2026', NOW) == 1


def test_archiving_is_idempotent_and_keeps_user_tip_and_frozen_forecast():
    from src.services.user_tips import archive_cached_model_tips
    store = fixture_store(NOW+timedelta(hours=1))
    archive = MemoryCollection()
    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW) == 1
    prediction = archive.documents['fixture-1']['prediction']
    prediction.update({'user_tip': '0:0', 'top_tip': '1:1', 'frozen_at': NOW.isoformat(), 'evaluation_forecast': {'captured_at': NOW.isoformat()}})
    before = deepcopy(archive.documents)
    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW) == 0
    assert archive.documents == before


def test_past_cache_recovery_requires_explicit_ids_and_pre_kickoff_observations():
    from src.services.user_tips import archive_cached_model_tips
    kickoff = NOW-timedelta(days=2)
    store = fixture_store(kickoff, kickoff-timedelta(minutes=30))
    archive = MemoryCollection()
    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW) == 0
    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW, recover_event_ids={'fixture-1'}) == 1
    entry = archive.documents['fixture-1']
    assert entry['prediction']['top_tip'] == '2:1'
    assert entry['prediction']['user_tip'] is None
    assert 'frozen_at' not in entry['prediction']
    assert 'evaluation_forecast' not in entry['prediction']
    assert entry['pre_match_snapshot']['timestamp_recorded'] == NOW.isoformat()
    assert entry['prediction']['tip_archive_source'] == 'cache_recovery'
    assert entry['prediction']['cached_fixture_observed_at'] == (kickoff-timedelta(minutes=30)).isoformat()
    late_store = fixture_store(kickoff, kickoff+timedelta(minutes=1))
    assert archive_cached_model_tips(MemoryCollection(), late_store, 'epl2026', now=NOW, recover_event_ids={'fixture-1'}) == 0


def test_missing_or_invalid_model_tip_is_never_invented():
    from src.services.user_tips import archive_cached_model_tips
    store = fixture_store(NOW+timedelta(hours=1))
    match = next(iter(store.documents.values()))['data'][0]
    match['top_tip'] = match['model_tip'] = 'N/A'
    archive = MemoryCollection()
    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW) == 0
    assert archive.documents == {}


def test_explicit_recovery_is_limited_to_the_named_fixture_ids():
    from src.services.user_tips import archive_cached_model_tips
    kickoff = NOW-timedelta(days=2)
    store = fixture_store(kickoff, kickoff-timedelta(minutes=30))
    future = next(iter(fixture_store(NOW+timedelta(days=2)).documents.values()))['data'][0]
    future['id'] = 'other-fixture'
    next(iter(store.documents.values()))['data'].append(future)
    archive = MemoryCollection()
    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW, recover_event_ids={'fixture-1'}) == 1
    assert set(archive.documents) == {'fixture-1'}


def test_maintenance_archives_existing_ucl_prediction_without_rebuilding_or_evaluation(monkeypatch):
    from test_model_evaluation import MemoryCollection as EvaluationCollection
    from src.services import maintenance

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    kickoff = now + timedelta(days=2)
    observed_at = (now - timedelta(minutes=5)).isoformat()
    fixture = {
        'id': 'ucl-game', 'home_team': 'Home', 'away_team': 'Away',
        'commence_time': kickoff.isoformat(), 'round': 'League phase',
        'observed_at': observed_at, 'status': 'fresh', 'source_status': 'fresh',
        'source_mode': 'odds+elo', 'source': 'odds_api+clubelo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'base_probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'xg_home': 1.1, 'xg_away': 1.4, 'max_xp': 4.25,
        'input_provenance': {'odds': {'observed_at': observed_at}, 'elo': {'observed_at': observed_at}},
        'provenance': {'odds': {'observed_at': observed_at}, 'elo': {'observed_at': None}},
        'context': {'competition': 'ucl2026', 'stage': 'league', 'leg': 'single'},
    }
    cache = EvaluationCollection([{
        '_id': 'ucl2026:matches_cache', 'observed_at': observed_at, 'data': [fixture],
    }])
    cache.insert_one = lambda document: cache.documents.setdefault(document['_id'], document)
    cache.delete_one = lambda query: cache.documents.pop(query.get('_id'), None)
    archive = ArchiveCollection()
    archive.insert_one = lambda document: archive.documents.setdefault(document['_id'], document)
    archive.delete_one = lambda query: archive.documents.pop(query.get('_id'), None)

    monkeypatch.setattr(maintenance, '_recent_club_fixtures', lambda *_args: {
        'status': 'fresh', 'source': 'cache', 'observed_at': observed_at, 'changed': False,
    })
    monkeypatch.setattr(maintenance, '_discovery_due', lambda *_args: False)
    monkeypatch.setattr(maintenance, '_persist_club_predictions', lambda *_args: 0)
    monkeypatch.setattr(maintenance, '_freeze_due_forecasts', lambda *_args: 0)

    result = maintenance.run_maintenance(
        {'ucl2026': cache}, None, archive_collections={'ucl2026': archive},
        competition='ucl2026', now=now,
    )

    prediction = archive.find_one({'_id': 'ucl-game'})['prediction']
    assert result['status'] == 'idle'
    assert prediction['model_tip'] == prediction['top_tip'] == '1:2'
    assert prediction['probabilities'] == fixture['probabilities']
    assert prediction['base_probabilities'] == fixture['base_probabilities']
    assert prediction['xg_home'] == 1.1 and prediction['xg_away'] == 1.4
    assert prediction['max_xp'] == 4.25
    assert prediction['provenance'] == fixture['provenance']
    assert prediction['model_version'] == 'prediction-club-v2'
    assert prediction['context'] == fixture['context']
    assert prediction['observed_at'] == observed_at
    assert prediction['tip_archive_source'] == 'maintenance'
    assert prediction['tip_archived_at'] == now.isoformat()
    assert 'frozen_at' not in prediction
    assert 'evaluation_forecast' not in prediction


def test_legacy_frozen_club_archive_is_not_shadowed_by_canonical_duplicate():
    from test_model_evaluation import MemoryCollection as EvaluationCollection
    from src.services.maintenance import archive_pre_match_club_predictions

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    kickoff = (now + timedelta(days=1)).isoformat()
    observed_at = (now - timedelta(minutes=5)).isoformat()
    fixture = {
        'id': 'canonical-ucl-id', 'home_team': 'Home', 'away_team': 'Away',
        'commence_time': kickoff, 'round': 'League phase',
        'observed_at': observed_at, 'status': 'fresh', 'source_mode': 'odds+elo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'provenance': {'odds': {'observed_at': observed_at}, 'elo': {'observed_at': None}},
    }
    legacy = {
        '_id': 'legacy-ucl-id',
        'metadata': {'home_team': 'Home', 'away_team': 'Away', 'commence_time': kickoff},
        'prediction': {'top_tip': '0:0', 'model_tip': '0:0', 'user_tip': '2:2', 'frozen_at': observed_at},
        'post_match_result': {'status': 'pending', 'actual_score': None},
    }
    cache = EvaluationCollection([{'_id': 'ucl2026:matches_cache', 'data': [fixture]}])
    archive = ArchiveCollection([legacy])

    archived = archive_pre_match_club_predictions(archive, cache, 'ucl2026', now=now)

    assert archived == 0
    assert set(archive.documents) == {'legacy-ucl-id'}
    assert archive.documents['legacy-ucl-id']['prediction']['top_tip'] == '0:0'
    assert archive.documents['legacy-ucl-id']['prediction']['user_tip'] == '2:2'
    assert archive.documents['legacy-ucl-id']['prediction']['frozen_at'] == observed_at


def test_pending_legacy_club_archive_is_updated_in_place_and_keeps_user_tip():
    from test_model_evaluation import MemoryCollection as EvaluationCollection
    from src.services.maintenance import archive_pre_match_club_predictions

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    kickoff = (now + timedelta(days=1)).isoformat()
    observed_at = (now - timedelta(minutes=5)).isoformat()
    fixture = {
        'id': 'canonical-ucl-id', 'home_team': 'Home', 'away_team': 'Away',
        'commence_time': kickoff, 'round': 'League phase',
        'observed_at': observed_at, 'status': 'fresh', 'source_mode': 'odds+elo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'provenance': {'odds': {'observed_at': observed_at}, 'elo': {'observed_at': None}},
    }
    legacy = {
        '_id': 'legacy-ucl-id',
        'metadata': {'home_team': 'Home', 'away_team': 'Away', 'commence_time': kickoff},
        'prediction': {
            'top_tip': '0:0', 'model_tip': '0:0', 'user_tip': '2:2',
            'observed_at': (now - timedelta(minutes=10)).isoformat(),
        },
        'post_match_result': {'status': 'pending', 'actual_score': None},
    }
    cache = EvaluationCollection([{'_id': 'ucl2026:matches_cache', 'data': [fixture]}])
    archive = ArchiveCollection([legacy])

    archived = archive_pre_match_club_predictions(archive, cache, 'ucl2026', now=now)

    assert archived == 1
    assert set(archive.documents) == {'legacy-ucl-id'}
    prediction = archive.documents['legacy-ucl-id']['prediction']
    assert prediction['top_tip'] == prediction['model_tip'] == '1:2'
    assert prediction['probabilities'] == fixture['probabilities']
    assert prediction['user_tip'] == '2:2'


def test_unknown_elo_time_in_regular_archive_does_not_become_evaluation_evidence():
    from test_model_evaluation import FreezeService, MemoryCollection as EvaluationCollection
    from src.services.forecast_evaluation import capture_archive_forecasts, evaluate_archive
    from src.services.model_evaluation import compare_models, freeze_due_comparisons
    from src.services.maintenance import archive_pre_match_club_predictions

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    class EvaluationService(FreezeService):
        model_version = 'test'

        def evaluation_probabilities(self, odds, elo):
            from src.services.prediction import PredictionService
            return PredictionService(self.math_engine).evaluation_probabilities(odds, elo)

    kickoff = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    captured_window = kickoff - timedelta(minutes=10)
    market_observed = kickoff - timedelta(minutes=15)
    fixture = {
        'id': 'ucl-game', 'home_team': 'Home', 'away_team': 'Away',
        'commence_time': kickoff.isoformat(), 'round': 'League phase',
        'observed_at': market_observed.isoformat(), 'status': 'fresh',
        'source_mode': 'odds+elo', 'source': 'odds_api+clubelo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'provenance': {
            'odds': {'source': 'odds_api', 'observed_at': market_observed.isoformat()},
            'elo': {'source': 'clubelo', 'observed_at': None},
        },
        'elo_state': {'home_rating': 1600, 'away_rating': 1500, 'source': 'clubelo', 'observed_at': None},
    }
    cache = EvaluationCollection([
        {'_id': 'ucl2026:matches_cache', 'data': [fixture]},
        {
            '_id': 'ucl2026:odds_snapshot:ucl-game:t15m', 'competition': 'ucl2026',
            'event_id': 'ucl-game', 'bucket': 't15m', 'observed_at': market_observed.isoformat(),
            'source': 'odds_api', 'status': 'fresh',
            'odds': {'home': 2.0, 'draw': 3.4, 'away': 4.0},
        },
    ])
    archive = ArchiveCollection()

    archived = archive_pre_match_club_predictions(archive, cache, 'ucl2026', now=captured_window)
    entry = archive.find_one({'_id': 'ucl-game'})
    captured = capture_archive_forecasts(
        cache, archive, EvaluationService(), competition='ucl2026', now=captured_window,
    )
    frozen = freeze_due_comparisons(
        EvaluationService(), cache, archive, 'ucl2026', captured_window,
        require_complete_capture=True,
    )

    assert archived == 1
    assert entry['pre_match_snapshot']['elo_state']['observed_at'] is None
    assert 'timestamp_recorded' not in entry['pre_match_snapshot']
    assert captured == 0
    assert frozen == 0
    saved = archive.find_one({'_id': 'ucl-game'})
    assert 'frozen_at' not in saved['prediction']
    assert 'evaluation_forecast' not in saved['prediction']
    completed = {**saved, 'post_match_result': {'status': 'completed', 'actual_score': '0:1'}}
    assert evaluate_archive([completed], competition='ucl2026')['exclusions']['missing_capture'] == 1
    assert compare_models({'ucl-game': completed}, competition='ucl2026')['counts']['verified_model'] == 0


def test_cached_club_archive_rejects_past_completed_and_future_observations():
    from test_model_evaluation import MemoryCollection as EvaluationCollection
    from src.services.maintenance import archive_pre_match_club_predictions

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    observed_at = (now - timedelta(minutes=5)).isoformat()
    base = {
        'id': 'ucl-game', 'home_team': 'Home', 'away_team': 'Away',
        'round': 'League phase', 'status': 'fresh', 'source_mode': 'odds+elo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'observed_at': observed_at,
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'provenance': {'odds': {'observed_at': observed_at}},
    }
    fixtures = [
        {**base, 'id': 'past', 'commence_time': (now - timedelta(minutes=1)).isoformat()},
        {**base, 'id': 'completed', 'commence_time': (now + timedelta(days=1)).isoformat(), 'completed': True},
        {**base, 'id': 'future-observation', 'commence_time': (now + timedelta(days=1)).isoformat(),
         'observed_at': (now + timedelta(minutes=1)).isoformat()},
        {**base, 'id': 'future-source-observation', 'commence_time': (now + timedelta(days=1)).isoformat(),
         'provenance': {'odds': {'observed_at': (now + timedelta(minutes=1)).isoformat()}}},
    ]
    cache = EvaluationCollection([{'_id': 'ucl2026:matches_cache', 'data': fixtures}])
    archive = ArchiveCollection()

    archived = archive_pre_match_club_predictions(archive, cache, 'ucl2026', now=now)

    assert archived == 0
    assert archive.documents == {}


def test_cached_club_archive_preserves_newer_frozen_and_evaluation_records():
    from test_model_evaluation import MemoryCollection as EvaluationCollection
    from src.services.maintenance import archive_pre_match_club_predictions

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    kickoff = (now + timedelta(days=1)).isoformat()
    observed_at = (now - timedelta(minutes=5)).isoformat()
    fixture = {
        'id': 'update-older', 'home_team': 'Home', 'away_team': 'Away',
        'commence_time': kickoff, 'round': 'League phase',
        'observed_at': observed_at, 'status': 'fresh', 'source_mode': 'odds+elo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'provenance': {'odds': {'observed_at': observed_at}},
    }
    base = {'metadata': {'commence_time': kickoff}, 'post_match_result': {'status': 'pending'}}
    frozen = {**base, 'prediction': {'frozen_at': observed_at, 'top_tip': '0:0'}}
    evaluated = {**base, 'prediction': {'evaluation_forecast': {'captured_at': observed_at}, 'top_tip': '0:1'}}
    newer = {**base, 'prediction': {'observed_at': (now - timedelta(minutes=1)).isoformat(), 'top_tip': '2:0'}}
    older = {**base, 'prediction': {'observed_at': (now - timedelta(minutes=10)).isoformat(),
                                    'top_tip': '0:0', 'user_tip': '2:2'},
             'post_match_result': {'status': 'pending', 'points_earned': None}}
    for document, match_id in ((frozen, 'frozen'), (evaluated, 'evaluated'),
                               (newer, 'newer'), (older, 'update-older')):
        document['_id'] = match_id
    fixtures = [{**fixture, 'id': 'frozen'}, {**fixture, 'id': 'evaluated'},
                {**fixture, 'id': 'newer'}, fixture]
    cache = EvaluationCollection([{'_id': 'ucl2026:matches_cache', 'data': fixtures}])
    archive = ArchiveCollection([frozen, evaluated, newer, older])

    archived = archive_pre_match_club_predictions(archive, cache, 'ucl2026', now=now)

    assert archived == 1
    assert archive.documents['frozen']['prediction']['top_tip'] == '0:0'
    assert archive.documents['evaluated']['prediction']['top_tip'] == '0:1'
    assert archive.documents['newer']['prediction']['top_tip'] == '2:0'
    updated = archive.documents['update-older']
    assert updated['prediction']['top_tip'] == '1:2'
    assert updated['prediction']['user_tip'] == '2:2'
    assert updated['post_match_result']['points_earned'] is None


def test_cached_club_archive_rejects_future_timestamp_in_either_provenance_map():
    from test_model_evaluation import MemoryCollection as EvaluationCollection
    from src.services.maintenance import archive_pre_match_club_predictions

    class ArchiveCollection(EvaluationCollection):
        def find(self, query=None, projection=None):
            return super().find(query)

    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    observed_at = (now - timedelta(minutes=5)).isoformat()
    future_observed = (now + timedelta(minutes=5)).isoformat()
    fixture = {
        'id': 'ucl-game', 'home_team': 'Home', 'away_team': 'Away',
        'commence_time': (now + timedelta(days=1)).isoformat(), 'round': 'League phase',
        'observed_at': observed_at, 'status': 'fresh', 'source_mode': 'odds+elo',
        'model_version': 'prediction-club-v2', 'model_tip': '1:2', 'top_tip': '1:2',
        'probabilities': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
        'provenance': {'odds': {'observed_at': observed_at}, 'elo': {'observed_at': observed_at}},
        'input_provenance': {'elo': {'observed_at': future_observed}},
    }
    cache = EvaluationCollection([{'_id': 'ucl2026:matches_cache', 'data': [fixture]}])
    archive = ArchiveCollection()

    archived = archive_pre_match_club_predictions(archive, cache, 'ucl2026', now=now)

    assert archived == 0
    assert archive.documents == {}


def test_archiving_skips_existing_ids_with_one_bulk_read_and_keeps_atomic_insert_for_new_id():
    from src.services.user_tips import archive_cached_model_tips

    kickoff = NOW + timedelta(hours=1)
    fixtures = []
    existing = []
    for index in range(305):
        event_id = f'fixture-{index}'
        fixtures.append(cache_fixture(
            id=event_id,
            commence_time=kickoff.isoformat(),
            raw_match={'commence_time': kickoff.isoformat()},
        ))
        existing.append({
            '_id': event_id,
            'prediction': {'user_tip': '1:0', 'top_tip': '2:1', 'frozen_at': NOW.isoformat()},
            'post_match_result': {'status': 'pending', 'actual_score': None},
        })
    fixtures.append(cache_fixture(
        id='new-fixture',
        commence_time=kickoff.isoformat(),
        raw_match={'commence_time': kickoff.isoformat()},
    ))
    store = MemoryCollection([{
        '_id': competition_document_id('epl2026', 'matches_cache'),
        'observed_at': NOW.isoformat(),
        'data': fixtures,
    }])
    archive = MemoryCollection(existing)

    assert archive_cached_model_tips(archive, store, 'epl2026', now=NOW) == 1

    assert len(archive.bulk_find_calls) == 1
    assert set(archive.bulk_find_calls[0][0]['_id']['$in']) == {row['_id'] for row in existing} | {'new-fixture'}
    assert len(archive.update_calls) == 1
    query, update, upsert = archive.update_calls[0]
    assert query == {'_id': 'new-fixture'}
    assert '$setOnInsert' in update and upsert is True
    assert update['$setOnInsert']['prediction.top_tip'] == '2:1'
    assert set(archive.documents) == {*(row['_id'] for row in existing), 'new-fixture'}
    assert archive.documents['fixture-0']['prediction'] == {
        'user_tip': '1:0', 'top_tip': '2:1', 'frozen_at': NOW.isoformat(),
    }
    assert archive.documents['new-fixture']['prediction']['top_tip'] == '2:1'
