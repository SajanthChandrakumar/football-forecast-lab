from datetime import datetime, timedelta, timezone
from copy import deepcopy

import pytest

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def test_source_status_uses_successful_observation_age():
    from src.services.source_freshness import source_status
    assert source_status('fresh', (NOW-timedelta(hours=25)).isoformat(), now=NOW) == 'stale'
    assert source_status('fresh', NOW.isoformat(), now=NOW) == 'fresh'
    assert source_status('fresh', (NOW+timedelta(seconds=1)).isoformat(), now=NOW) == 'stale'
    assert source_status('fresh', None, now=NOW) == 'stale'
    assert source_status('fresh', '2026-10-24T12:00:00', now=NOW) == 'stale'
    assert source_status('failed', NOW.isoformat(), now=NOW) == 'failed'
    assert source_status('unavailable', NOW.isoformat(), now=NOW) == 'unavailable'


def test_prediction_memo_reuses_inputs_and_never_leaks_mutations():
    from src.services.prediction_cache import cached_prediction, clear_prediction_cache
    clear_prediction_cache()
    class Service:
        model_version = 'prediction-club-v2'
        math_engine = object()
        def __init__(self): self.calls = 0
        def predict(self, **kwargs):
            self.calls += 1
            return {'top_tip': '2:1', 'nested': {'x': 1}}
    service = Service()
    args = {'odds': {'home': 2}, 'elo': {'home_rating': 1600}, 'context': {'commence_time': '2026-11-01T12:00Z'}}
    first = cached_prediction(service, 'ucl2026', **args)
    first['nested']['x'] = 99
    assert cached_prediction(service, 'ucl2026', **args)['nested']['x'] == 1
    assert service.calls == 1
    cached_prediction(service, 'epl2026', **args)
    assert service.calls == 2
    cached_prediction(service, 'ucl2026', **{**args, 'odds': {'home': 3}})
    assert service.calls == 3


def test_prediction_memo_never_caches_world_cup_calculations():
    from src.services.prediction_cache import cached_prediction
    class Service:
        model_version = 'prediction-v1'
        math_engine = object()
        calls = 0
        def predict(self, **kwargs):
            self.calls += 1
            return {'top_tip': str(self.calls)}
    service = Service()
    assert cached_prediction(service, 'wc2026')['top_tip'] == '1'
    assert cached_prediction(service, 'wc2026')['top_tip'] == '2'


def test_club_source_ages_refresh_without_changing_world_cup_or_archives():
    from src.routes.matches import _apply_club_source_status
    row = {'id':'x', 'source_mode':'elo-only', 'input_provenance': {'elo': {'status':'fresh','observed_at':(NOW-timedelta(days=4)).isoformat()}}}
    original = deepcopy(row)
    result = _apply_club_source_status([row], 'ucl2026', now=NOW)[0]
    assert result['source_status'] == 'stale'
    assert result['input_provenance']['elo']['status'] == 'stale'
    assert row == original
    assert _apply_club_source_status([row], 'wc2026', now=NOW) == [original]
    finished = {**row, 'completed':True}
    assert _apply_club_source_status([finished], 'ucl2026', now=NOW) == [finished]


def test_capture_claim_is_exclusive_and_can_recover_expired_holder():
    from src.services.forecast_worker import claim_capture
    from test_model_evaluation import MemoryCollection
    cache = MemoryCollection()
    first = claim_capture(cache, 'ucl2026', NOW)
    assert first
    assert claim_capture(cache, 'ucl2026', NOW) is None
    assert claim_capture(cache, 'ucl2026', NOW+timedelta(seconds=121)) not in (None, first)


def test_maintenance_calls_verified_form_refresh_for_both_clubs():
    from src.services.maintenance import run_maintenance
    from test_result_refresh import MemoryCollection
    class Form:
        def __init__(self): self.calls = []
        def refresh_all_competitions(self, now=None):
            self.calls.append(now)
            return {'status':'fresh','teams':2}
    for competition in ('epl2026','ucl2026'):
        service = Form()
        cache = MemoryCollection()
        result = run_maintenance(cache, None, competition=competition, now=NOW, team_form_service=service)
        assert service.calls == [NOW]
        assert result['team_form_status']['status'] == 'fresh'


def test_elo_status_does_not_call_four_day_old_data_fresh():
    from src.routes.elo_status import init_router
    from test_model_evaluation import MemoryCollection
    cache = MemoryCollection([{'_id':'ucl2026:clubelo_ratings','status':'fresh',
        'observed_at': '2000-01-01T12:00:00+00:00','source':'clubelo','rows':[]}])
    result = init_router({'ucl2026':cache}).routes[0].endpoint(competition='ucl2026')
    assert result['status'] == 'stale'


def test_maintenance_status_keeps_last_success_on_failure(monkeypatch):
    from src.services import maintenance
    from test_result_refresh import MemoryCollection
    cache = MemoryCollection()
    monkeypatch.setattr(maintenance, 'run_maintenance', lambda *a, **kw: {'status':'success','provider_calls':0})
    maintenance.run_tracked_maintenance(cache, None, competition='epl2026', now=NOW)
    key = 'epl2026:maintenance_status'
    assert cache.find_one({'_id':key})['last_successful_at'] == NOW.isoformat()
    def broken(*a, **kw): raise RuntimeError('sensitive provider URL')
    monkeypatch.setattr(maintenance, 'run_maintenance', broken)
    with pytest.raises(RuntimeError):
        maintenance.run_tracked_maintenance(cache, None, competition='epl2026', now=NOW+timedelta(minutes=1))
    state = cache.find_one({'_id':key})
    assert state['last_successful_at'] == NOW.isoformat()
    assert state['status'] == 'failed'
    assert 'sensitive' not in str(state)
    assert state['next_due_at']


def test_form_refresh_is_daily_with_hourly_failure_retry():
    from src.services.maintenance import _recent_club_form
    from test_result_refresh import MemoryCollection
    from src.competitions import get_competition
    cache = MemoryCollection([{'_id':'epl2026:team_form_sync','status':'fresh',
        'last_attempt_at': NOW.isoformat(), 'last_successful_at':NOW.isoformat(), 'observed_at':NOW.isoformat()}])
    comp = get_competition('epl2026')
    assert _recent_club_form(cache, comp, NOW+timedelta(hours=23))['status'] == 'fresh'
    assert _recent_club_form(cache, comp, NOW+timedelta(hours=25)) is None
    cache.update_one({'_id':'epl2026:team_form_sync'}, {'$set': {'status':'stale'}})
    assert _recent_club_form(cache, comp, NOW+timedelta(minutes=30))['status'] == 'stale'
    assert _recent_club_form(cache, comp, NOW+timedelta(hours=2)) is None


def test_club_maintenance_preserves_world_cup_ratings_and_historical_forecasts(monkeypatch):
    from src.services import maintenance
    from test_result_refresh import MemoryCollection
    cache, archive = MemoryCollection(), MemoryCollection()
    legacy_ratings = object()
    class Engine: elo_df = legacy_ratings
    engine = Engine()
    def forbidden(*args, **kwargs):
        raise AssertionError('Club maintenance must not reconstruct historical predictions')
    monkeypatch.setattr(maintenance, '_reconstruct_completed_entries', forbidden)
    monkeypatch.setattr(maintenance, '_persist_club_predictions', lambda *a, **kw: 0)
    monkeypatch.setattr(maintenance, '_freeze_due_forecasts', lambda *a, **kw: 0)
    monkeypatch.setattr(maintenance, 'capture_archive_forecasts', lambda *a, **kw: 0)
    result = maintenance.run_maintenance(cache, None, archive_collections=archive,
        competition='ucl2026', now=NOW, math_engine=engine,
        clubelo_ingestor=lambda *a, **kw: {'status':'fresh','rows':[{'Team':'Arsenal','Elo':1800}]})
    assert engine.elo_df is legacy_ratings
    assert result['reconstructed_results'] == 0


def test_completed_historical_points_are_preserved_during_club_refresh():
    from src.services.maintenance import _sync_completed_results
    from test_result_refresh import MemoryCollection
    prediction = {'user_tip':'2:0','top_tip':'1:0','model_version':'prediction-v1','bots':{'old':{'tip':'0:0'}}}
    archive = MemoryCollection([{'_id':'done','prediction':deepcopy(prediction),
        'post_match_result': {'status':'completed','actual_score':'2:0','points_earned':7,'algo_points':3,'bot_points':{'old':1}}}])
    fixture = {'id':'done','completed':True,'actual_score':'2:0','home_team':'A','away_team':'B','round':'League Phase'}
    _sync_completed_results(archive,[fixture],'ucl2026')
    saved = archive.find_one({'_id':'done'})
    assert saved['prediction'] == prediction
    assert saved['post_match_result']['points_earned'] == 7
    assert saved['post_match_result']['algo_points'] == 3
    assert saved['post_match_result']['bot_points'] == {'old':1}


def test_club_fixture_pipeline_preserves_exact_provider_participant_ids():
    from src.services.espn_data import get_scoreboard
    from src.services.maintenance import _refresh_fixtures
    from src.competitions import get_competition
    from test_task2_providers import _event
    from test_result_refresh import MemoryCollection
    event = _event('identity-target', '2026-10-24T12:00:00Z')
    event['competitions'][0]['competitors'][0]['team']['id'] = '132'
    event['competitions'][0]['competitors'][1]['team']['id'] = '359'
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'events':[event]}
    rows = get_scoreboard(competition='ucl2026',now=NOW,days_back=0,days_forward=0,
        use_cache=False,request_get=lambda *a, **kw: Response())
    assert rows[0]['home_team_id'] == '132'
    assert rows[0]['away_team_id'] == '359'
    cache = MemoryCollection()
    _refresh_fixtures(cache,get_competition('ucl2026'),lambda **kw: rows,NOW)
    saved=cache.find_one({'_id':'ucl2026:matches_cache'})['data'][0]
    assert saved['home_team_id'] == '132'
    assert saved['away_team_id'] == '359'


@pytest.mark.parametrize('provenance', [None, {'source':'legacy','observed_at':None}])
def test_missing_source_provenance_cannot_confirm_fresh_club_prediction(provenance):
    from src.routes.matches import _apply_club_source_status
    result = _apply_club_source_status([{'id':'open','status':'fresh','source_status':'fresh','observed_at':None,'provenance':provenance}], 'epl2026',now=NOW)[0]
    assert result['source_status'] == 'stale'


def test_failed_discovery_keeps_success_time_and_retries_after_one_hour():
    from src.services.maintenance import _record_discovery, _discovery_due
    from src.competitions import get_competition
    from test_result_refresh import MemoryCollection
    comp=get_competition('ucl2026')
    previous=(NOW-timedelta(days=2)).isoformat()
    cache=MemoryCollection([{'_id':'ucl2026:odds_discovery_state','status':'fresh','observed_at':previous}])
    _record_discovery(cache,comp,NOW,'failed',error='temporary')
    saved=cache.find_one({'_id':'ucl2026:odds_discovery_state'})
    assert saved['observed_at'] == previous
    assert saved['last_attempt_at'] == NOW.isoformat()
    assert not _discovery_due(cache,comp,NOW+timedelta(minutes=5))
    assert _discovery_due(cache,comp,NOW+timedelta(hours=1,seconds=1))


def test_completed_club_detail_uses_stored_forecast_without_current_model():
    from src.routes.predict import _archived_club_prediction
    from test_result_refresh import MemoryCollection
    original={'_id':'old','prediction':{'model_tip':'3:0','top_tip':'3:0','model_version':'prediction-v1','probabilities':{'home':.7,'draw':.2,'away':.1}},'post_match_result':{'status':'completed'}}
    archive=MemoryCollection([deepcopy(original)])
    result=_archived_club_prediction(archive,'old')
    assert result['model_tip']=='3:0'
    assert result['model_version']=='prediction-v1'
    assert result['historical'] is True
    assert result['matrix']=={}
    assert archive.find_one({'_id':'old'})==original
    assert _archived_club_prediction(archive,'missing')['status']=='unavailable'


def test_provider_observation_time_is_after_the_response_not_job_start(monkeypatch):
    from src.services import maintenance
    from test_result_refresh import MemoryCollection
    clock=[NOW]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return clock[0]
    monkeypatch.setattr(maintenance,'datetime',Clock)
    cache=MemoryCollection()
    def fixtures(**kwargs):
        clock[0]+=timedelta(minutes=2)
        return [{'id':'new','home_team':'A','away_team':'B','commence_time':(NOW+timedelta(days=1)).isoformat()}]
    class Provider:
        def get_competition_odds(self,*a,**kw):
            clock[0]+=timedelta(minutes=1)
            return [{'id':'new','home_team':'A','away_team':'B','odds':{'home':2,'draw':3,'away':4}}]
    maintenance.run_maintenance(cache,Provider(),competition='ucl2026',fixture_fetcher=fixtures)
    saved=cache.find_one({'_id':'ucl2026:matches_cache'})
    assert saved['observed_at']==(NOW+timedelta(minutes=2)).isoformat()
    assert saved['data'][0]['odds_observed_at']==(NOW+timedelta(minutes=3)).isoformat()


def test_lease_heartbeat_is_fenced_to_its_current_owner():
    from src.services.maintenance import _renew_maintenance_lease
    from test_result_refresh import MemoryCollection
    cache=MemoryCollection([{'_id':'epl2026:maintenance_lease','lease_token':'new-owner','lease_until':NOW.isoformat()}])
    assert not _renew_maintenance_lease(cache,'epl2026:maintenance_lease','old-owner',NOW,300)
    assert cache.find_one({'_id':'epl2026:maintenance_lease'})['lease_until']==NOW.isoformat()
    assert _renew_maintenance_lease(cache,'epl2026:maintenance_lease','new-owner',NOW,300)
    assert cache.find_one({'_id':'epl2026:maintenance_lease'})['lease_until']==(NOW+timedelta(seconds=300)).isoformat()

@pytest.mark.parametrize('competition',['epl2026','ucl2026'])
def test_public_legacy_club_list_never_runs_a_full_forecast_calculation(monkeypatch,competition):
    from src.routes.matches import _present_cached_matches
    from test_result_refresh import MemoryCollection
    old={'id':'legacy','home_team':'Home','away_team':'Away','model_version':'prediction-v1','top_tip':'9:0','bots':{'professor':{'tip':'9:0'}},'probabilities':{'home':.99,'draw':.005,'away':.005}}
    def forbidden(*a,**kw):raise AssertionError('Public lists must not calculate forecasts')
    monkeypatch.setattr('src.routes.matches._enrich_edge',forbidden)
    result=_present_cached_matches([deepcopy(old)],object(),None,competition,MemoryCollection(),MemoryCollection())
    assert result[0]['calculation_status']=='pending'
    assert result[0]['bots']=={}
    assert result[0]['model_tip'] is None and result[0]['top_tip'] is None
    assert result[0]['probabilities'] is None
    assert result[0]['source_status']=='unavailable'
    assert old['top_tip']=='9:0'
