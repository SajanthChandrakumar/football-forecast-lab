from src.services.team_form import ApiFootballClient
from src.routes.maintenance import init_router
from test_manual_refresh import cache,Provider,request,endpoint
from test_team_form import FakeResponse


def test_daily_fixture_query_omits_unsupported_first_page(monkeypatch):
    import src.services.team_form as module
    monkeypatch.setattr(module.quota_store,'reserve_request',lambda *args,**kwargs:0)
    monkeypatch.setattr(module,'write_quota',lambda *args,**kwargs:None)
    sent=[]
    def get(url,**kwargs):
        sent.append(kwargs['params'])
        return FakeResponse({'response':[],'paging':{'current':1,'total':1}})
    params={'date':'2026-10-19','timezone':'Europe/Zurich','page':1}
    client=ApiFootballClient('test-key',request_fn=get)
    client.request('/fixtures',params)
    assert sent==[{'date':'2026-10-19','timezone':'Europe/Zurich'}]
    assert params['page']==1


def test_player_pagination_is_preserved(monkeypatch):
    import src.services.team_form as module
    monkeypatch.setattr(module.quota_store,'reserve_request',lambda *args,**kwargs:0)
    monkeypatch.setattr(module,'write_quota',lambda *args,**kwargs:None)
    sent=[]
    client=ApiFootballClient('test-key',request_fn=lambda url,**kw:sent.append(kw['params']) or FakeResponse({'response':[]}))
    client.request('/players',{'league':2,'season':2026,'page':2})
    assert sent==[{'league':2,'season':2026,'page':2}]


def test_manual_ucl_report_does_not_hide_team_form_failure(monkeypatch):
    import src.routes.maintenance as module
    observed='2026-10-20T12:40:00+00:00'
    monkeypatch.setattr(module,'run_maintenance',lambda *a,**kw:{
        'fixture_status':{'status':'fresh','observed_at':observed},
        'clubelo_status':{'status':'fresh','observed_at':observed},
        'odds_status':{'status':'fresh','observed_at':observed},
        'team_form_status':{'status':'stale','source':'api_football','error':'url?apiKey=must-stay-private'},
        'match_intelligence_status':{'espn_calls':1,'confirmed':1,'observed_at':observed},
    })
    route=endpoint(init_router(cache(),Provider(),admin_refresh_token='admin-only'))
    result=route(request('admin-only'),competition='ucl2026')
    assert result['status']=='partial'
    source=next(item for item in result['sources'] if item['id']=='team_form')
    assert source['status']=='stale'
    assert source['message']
    assert 'must-stay-private' not in str(result)


def test_daily_sync_requires_exact_provider_team_id_and_ignores_display_name():
    from src.services.team_form import TeamFormService
    from test_team_form import MemoryCollection, _fixture
    store=MemoryCollection()
    wrong=_fixture('wrong')
    wrong['teams']['home']['id']=999
    right=_fixture('right')
    right['teams']['home']['name']='Unrelated Club'
    class Client:
        provider='api_football'
    service=TeamFormService(store,Client())
    rows=service.parse_fixtures('10',{'response':[wrong,right]},provider='api_football')
    assert [row['fixture_id'] for row in rows]==['right']


def test_initial_daily_sync_catches_up_since_completed_bootstrap():
    from datetime import datetime, timezone
    from src.services.team_form import TeamFormService
    from test_team_form import MemoryCollection
    store=MemoryCollection([
        {'_id':'ucl2026:team_form_teams','teams':[{'team_id':'10','name':'Team'}]},
        {'_id':'ucl2026:team_form_bootstrap','last_successful_at':'2026-09-26T08:39:59+00:00'},
    ])
    dates=[]
    class Client:
        provider='api_football'
        def request(self,path,params):
            dates.append(params['date'])
            return {'response':[],'paging':{'current':1,'total':1}}
    result=TeamFormService(store,Client()).refresh_daily(now=datetime(2026,10,20,tzinfo=timezone.utc),max_catchup_days=2)
    assert dates==['2026-09-26','2026-09-27']
    assert result['status']=='stale'
    assert result['remaining_dates']==22


def test_club_form_does_not_resolve_team_ids_from_cross_provider_aliases():
    from src.services.team_form import TeamFormService
    from test_team_form import MemoryCollection
    store=MemoryCollection([
        {'_id':'ucl2026:team_form_teams','provider_namespace':'espn:team-id',
         'teams':[{'team_id':'132','name':'Bayern Munich'}]},
        {'_id':'ucl2026:team_form:132','team_id':'132','scope':'all_competitions','status':'fresh',
         'provider':'api_football','provider_namespace':'api_football:team-id',
         'matches':[{'fixture_id':'bayern-new','played_at':'2026-09-01T18:00:00Z','result':'W',
                     'identity_verified':True,'provider':'api_football','provider_namespace':'api_football:team-id',
                     'home_id':'132','away_id':'20','competition_id':'uefa.champions',
                     'competition_name':'UEFA Champions League','competition_kind':'europe'}]},
    ])
    class Client:
        provider='espn'
    service=TeamFormService(store,Client())
    form=service.cached_form_for_match('Bayern München',before='2026-10-01T18:00:00Z')
    assert form['matches']==[]
    assert service._resolve_team_id('Bayern Munich',None,store.find_one({'_id':'ucl2026:team_form_teams'})) is None
