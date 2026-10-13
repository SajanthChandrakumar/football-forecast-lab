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
