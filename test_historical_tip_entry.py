from copy import deepcopy
from datetime import datetime, timezone
import importlib
import pytest
from fastapi import HTTPException
from test_model_evaluation import MemoryCollection
from src.services.maintenance import _sync_completed_results


def entry():
    return {'_id': 'game', 'metadata': {'home_team': 'Home', 'away_team': 'Away', 'commence_time': '2026-10-20T16:45:00Z', 'is_ko_phase': False},
            'prediction': {'user_tip': None, 'top_tip': '1:0', 'evaluation_forecast': {'immutable': True}},
            'post_match_result': {'status': 'completed', 'actual_score': '2:0', 'algo_points': 6}}


def test_completed_tip_can_be_entered_and_scored_without_changing_model_or_forecast():
    fn = getattr(importlib.import_module('src.services.user_tips'), 'save_historical_tip', None)
    assert callable(fn)
    collection = MemoryCollection([entry()])
    result = fn(collection, 'game', '2:0', 'ucl2026', now=datetime(2026,10,20,20,tzinfo=timezone.utc))
    saved = collection.find_one({'_id': 'game'})
    assert result['points_earned'] == saved['post_match_result']['points_earned'] == 10
    assert saved['prediction']['user_tip'] == '2:0'
    assert saved['prediction']['user_tip_source'] == 'manual_historical'
    assert saved['prediction']['top_tip'] == '1:0'
    assert saved['prediction']['evaluation_forecast'] == {'immutable': True}
    fn(collection, 'game', '1:1', 'ucl2026')
    assert collection.find_one({'_id': 'game'})['prediction']['user_tip_edits'][-1]['previous_tip'] == '2:0'


def test_historical_route_does_not_bypass_the_deadline_for_running_or_future_games():
    fn = getattr(importlib.import_module('src.services.user_tips'), 'save_historical_tip', None)
    assert callable(fn)
    original=entry(); original['post_match_result']={'status':'pending'}
    collection=MemoryCollection([deepcopy(original)])
    with pytest.raises(HTTPException) as exc:
        fn(collection,'game','2:0','ucl2026')
    assert exc.value.status_code == 409
    assert collection.find_one({'_id':'game'}) == original
    with pytest.raises(HTTPException) as exc:
        fn(MemoryCollection([entry()]),'game','99:0','ucl2026')
    assert exc.value.status_code == 400


def test_result_sync_keeps_real_cached_model_tip_when_archive_has_none():
    original=entry(); original['prediction']={'user_tip': None, 'top_tip': None}
    collection=MemoryCollection([original])
    fixture={'id':'game','home_team':'Home','away_team':'Away','commence_time':'2026-10-20T16:45:00Z','round':'league phase','completed':True,'actual_score':'2:0','top_tip':'2:0','model_tip':'2:0','observed_at':'2026-10-20T13:04:00Z','source_mode':'odds+elo'}
    _sync_completed_results(collection,[fixture],'ucl2026')
    saved=collection.find_one({'_id':'game'})
    assert saved['prediction']['top_tip'] == '2:0'
    assert saved['post_match_result']['algo_points'] == original['post_match_result']['algo_points']
    assert 'frozen_at' not in saved['prediction']
    assert saved['prediction']['algo_tip_source'] == 'saved_cache'
