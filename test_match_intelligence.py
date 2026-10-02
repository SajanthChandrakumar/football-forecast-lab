from datetime import datetime, timedelta, timezone

from src.competitions import competition_document_id
from src.services.match_intelligence import (
    attach_cached_match_intelligence,
    cached_match_intelligence,
    fetch_espn_summary,
    normalize_espn_summary,
    refresh_match_intelligence,
)
from test_task2_providers import MemoryCollection


NOW = datetime(2026, 10, 13, 18, 30, tzinfo=timezone.utc)


def _summary(with_players=True):
    roster = []
    if with_players:
        roster = [
            {
                "starter": index <= 11,
                "jersey": str(index),
                "athlete": {
                    "id": str(index),
                    "displayName": f"Player {index}",
                    "position": {"abbreviation": "GK" if index == 1 else "MF"},
                },
                "stats": [{"name": "goals", "value": 1 if index == 9 else 0}],
            }
            for index in range(1, 15)
        ]
    return {
        "rosters": [
            {"team": {"displayName": "Lens"}, "roster": roster},
            {"team": {"displayName": "Sporting CP"}, "roster": roster},
        ],
        "boxscore": {"teams": [{
            "team": {"displayName": "Lens"},
            "statistics": [{"name": "possessionPct", "displayValue": "54%"}],
        }]},
    }


def test_normalize_espn_summary_separates_starters_and_substitutes():
    result = normalize_espn_summary(_summary(), observed_at=NOW)

    assert result["status"] == "fresh"
    assert result["source"] == "espn"
    assert len(result["lineups"]["Lens"]["starters"]) == 11
    assert len(result["lineups"]["Lens"]["substitutes"]) == 3
    assert result["lineups"]["Lens"]["starters"][8]["stats"]["goals"] == 1
    assert result["team_stats"]["Lens"]["possessionPct"] == "54%"


def test_normalize_espn_summary_marks_unpublished_lineups_explicitly():
    result = normalize_espn_summary(_summary(with_players=False), observed_at=NOW)

    assert result["status"] == "unavailable"
    assert result["reason"] == "lineups_not_published"
    assert result["lineups"] == {}


def test_espn_formation_is_preserved_without_guessing():
    payload = _summary()
    payload['rosters'][0]['formation'] = '4-2-3-1'
    result = normalize_espn_summary(payload, observed_at=NOW)
    assert result['lineups']['Lens']['formation'] == '4-2-3-1'
    assert 'formation' not in result['lineups']['Sporting CP']


def test_pl_old_match_backfill_is_five_per_day_and_near_kickoff_has_priority():
    collection = MemoryCollection()
    fixtures = [{'id': f'old-{i}', 'completed': True,
                 'commence_time': (NOW - timedelta(days=10+i)).isoformat()} for i in range(12)]
    fixtures.append({'id': 'upcoming', 'completed': False,
                     'commence_time': (NOW + timedelta(minutes=30)).isoformat()})
    calls = []
    def fetch(event):
        calls.append(event)
        return _summary()
    first = refresh_match_intelligence(collection, fixtures, now=NOW, espn_fetcher=fetch, competition='epl2026')
    assert calls[0] == 'upcoming'
    assert first['espn_calls'] == 6
    assert first['historical_calls_today'] == 5
    repeated = refresh_match_intelligence(collection, fixtures, now=NOW, espn_fetcher=fetch, competition='epl2026')
    assert repeated['espn_calls'] == 0
    next_day = refresh_match_intelligence(collection, fixtures, now=NOW + timedelta(days=1), espn_fetcher=fetch, competition='epl2026')
    assert next_day['historical_calls_today'] == 5
    assert len(calls) == 11


def test_pl_failed_backfill_is_charged_and_never_uses_unverified_paid_fallback():
    collection = MemoryCollection()
    class ForbiddenFallback:
        def request(self, *args, **kwargs):
            raise AssertionError('PL must use ESPN only until paid season coverage is verified')
    fixture = {'id':'old', 'completed':True, 'commence_time':(NOW-timedelta(days=10)).isoformat()}
    def fail(_):
        raise RuntimeError('unavailable')
    first = refresh_match_intelligence(collection, [fixture], now=NOW, competition='epl2026',
                                      espn_fetcher=fail, api_football_client=ForbiddenFallback())
    assert first['historical_calls_today'] == 1
    assert first['api_football_calls'] == 0


def test_fetch_espn_summary_uses_all_competitions_for_domestic_history():
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return _summary()

    def request_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    fetch_espn_summary("401876453", request_get=request_get)

    assert calls[0][0].endswith("/soccer/all/summary")
    assert calls[0][1]["params"] == {"event": "401876453"}


def test_refresh_is_due_near_kickoff_and_stops_after_confirmed_lineups():
    fixture = {
        "id": "401915418",
        "home_team": "Lens",
        "away_team": "Sporting CP",
        "commence_time": (NOW + timedelta(minutes=30)).isoformat(),
        "completed": False,
    }
    collection = MemoryCollection()
    calls = []

    def fetch(event_id):
        calls.append(event_id)
        return _summary()

    first = refresh_match_intelligence(collection, [fixture], now=NOW, espn_fetcher=fetch)
    second = refresh_match_intelligence(collection, [fixture], now=NOW + timedelta(minutes=5), espn_fetcher=fetch)

    assert calls == ["401915418"]
    assert first["espn_calls"] == 1
    assert second["espn_calls"] == 0
    assert second["reason"] == "nothing_due"


def test_partial_lineup_is_checked_again_at_t15():
    fixture = {
        "id": "partial",
        "commence_time": (NOW + timedelta(minutes=30)).isoformat(),
        "completed": False,
    }
    collection = MemoryCollection()
    calls = []

    def fetch(event_id):
        calls.append(event_id)
        payload = _summary()
        if len(calls) == 1:
            payload["rosters"] = payload["rosters"][:1]
        return payload

    refresh_match_intelligence(collection, [fixture], now=NOW, espn_fetcher=fetch)
    refresh_match_intelligence(
        collection, [fixture], now=NOW + timedelta(minutes=20), espn_fetcher=fetch,
    )

    assert calls == ["partial", "partial"]


def test_failed_post_match_refresh_preserves_confirmed_lineups():
    event_id = "played"
    document_id = competition_document_id("ucl2026", f"match_intelligence:{event_id}")
    confirmed = normalize_espn_summary(_summary(), observed_at=NOW)
    collection = MemoryCollection([{
        "_id": document_id,
        "competition": "ucl2026",
        "event_id": event_id,
        "data": confirmed,
        "attempted_buckets": ["t35"],
    }])

    refresh_match_intelligence(
        collection, [{"id": event_id, "completed": True}], now=NOW,
        espn_fetcher=lambda event_id: (_ for _ in ()).throw(RuntimeError("temporary")),
    )

    stored = collection.find_one({"_id": document_id})
    assert stored["data"] == confirmed
    assert stored["last_attempt"]["status"] == "failed"


def test_empty_post_match_payload_preserves_lineups_and_remains_retryable():
    event_id = "played-empty"
    document_id = competition_document_id("ucl2026", f"match_intelligence:{event_id}")
    confirmed = normalize_espn_summary(_summary(), observed_at=NOW)
    collection = MemoryCollection([{
        "_id": document_id, "data": confirmed, "attempted_buckets": ["t35"],
    }])
    calls = []

    refresh_match_intelligence(
        collection, [{"id": event_id, "completed": True}], now=NOW,
        espn_fetcher=lambda event_id: calls.append(event_id) or _summary(with_players=False),
    )
    refresh_match_intelligence(
        collection, [{"id": event_id, "completed": True}], now=NOW + timedelta(minutes=5),
        espn_fetcher=lambda event_id: calls.append(event_id) or _summary(),
    )

    stored = collection.find_one({"_id": document_id})
    assert calls == [event_id, event_id]
    assert stored["data"]["lineups"] == confirmed["lineups"]
    assert "post_match_retry" in stored["attempted_buckets"]


def test_attach_cached_match_intelligence_never_calls_a_provider():
    class BulkCollection(MemoryCollection):
        def find(self, query=None):
            wanted = set((query or {}).get("_id", {}).get("$in", []))
            return [doc for key, doc in self.documents.items() if key in wanted]

    collection = BulkCollection([{
        "_id": competition_document_id("ucl2026", "match_intelligence:401915418"),
        "competition": "ucl2026",
        "event_id": "401915418",
        "data": normalize_espn_summary(_summary(), observed_at=NOW),
    }])

    matches = attach_cached_match_intelligence(
        [{"id": "401915418", "home_team": "Lens", "away_team": "Sporting CP"}],
        collection,
        "ucl2026",
    )

    assert matches[0]["match_intelligence"]["status"] == "fresh"
    assert len(matches[0]["match_intelligence"]["lineups"]["Lens"]["starters"]) == 11


def test_api_football_fallback_is_one_batched_call_for_a_matchday():
    fixtures = [{
        "id": str(index),
        "home_team": f"Home {index}",
        "away_team": f"Away {index}",
        "commence_time": (NOW + timedelta(minutes=30)).isoformat(),
        "completed": False,
    } for index in (1, 2)]

    class ApiClient:
        def __init__(self):
            self.calls = []

        def request(self, path, params=None):
            self.calls.append((path, params))
            return {"response": [{
                "teams": {"home": {"name": "Home 1"}, "away": {"name": "Away 1"}},
                "lineups": [{
                    "team": {"name": team},
                    "startXI": [{"player": {"id": 1, "name": f"{team} Keeper", "number": 1, "pos": "G"}}],
                    "substitutes": [],
                } for team in ("Home 1", "Away 1")],
                "statistics": [],
            }]}

    api = ApiClient()
    result = refresh_match_intelligence(
        MemoryCollection(), fixtures, now=NOW,
        espn_fetcher=lambda event_id: _summary(with_players=False),
        api_football_client=api,
    )

    assert len(api.calls) == 1
    assert api.calls[0][0] == "/fixtures"
    assert result["api_football_calls"] == 1


def test_historical_backfill_never_spends_api_football_quota():
    fixture = {
        "id": "historic-1", "home_team": "Home", "away_team": "Away",
        "commence_time": "2026-08-20T18:00:00+00:00", "completed": True,
        "historical": True,
    }

    class ApiClient:
        def request(self, path, params=None):
            raise AssertionError("historical cache fill must remain ESPN-only")

    result = refresh_match_intelligence(
        MemoryCollection(), [fixture], now=NOW,
        espn_fetcher=lambda event_id: _summary(with_players=False),
        api_football_client=ApiClient(),
    )

    assert result["espn_calls"] == 1
    assert result["api_football_calls"] == 0


def test_historical_fixture_never_retries_a_stale_api_fallback():
    event_id = "historic-pending"
    collection = MemoryCollection([{
        "_id": competition_document_id("ucl2026", f"match_intelligence:{event_id}"),
        "event_id": event_id,
        "fallback_pending": True,
        "attempted_buckets": ["t15"],
        "data": normalize_espn_summary(_summary(with_players=False), observed_at=NOW),
    }])

    class ApiClient:
        def request(self, path, params=None):
            raise AssertionError("historical fallback retry must remain ESPN-only")

    result = refresh_match_intelligence(
        collection, [{
            "id": event_id, "home_team": "Home", "away_team": "Away",
            "commence_time": "2026-08-20T18:00:00+00:00", "completed": True,
            "historical": True,
        }], now=NOW, espn_fetcher=lambda event_id: _summary(),
        api_football_client=ApiClient(),
    )

    assert result["api_football_calls"] == 0


def test_api_football_uses_cached_fixture_ids_for_enriched_batch():
    fixture = {
        "id": "espn-1", "home_team": "Home 1", "away_team": "Away 1",
        "commence_time": (NOW + timedelta(minutes=30)).isoformat(), "completed": False,
    }
    mapping_id = competition_document_id("ucl2026", f"match_intelligence_provider_ids:{(NOW + timedelta(minutes=30)).date().isoformat()}")
    collection = MemoryCollection([{
        "_id": mapping_id,
        "competition": "ucl2026",
        "event_ids": {"espn-1": "991"},
    }])

    class ApiClient:
        def __init__(self):
            self.calls = []

        def request(self, path, params=None):
            self.calls.append((path, params))
            return {"response": [{
                "fixture": {"id": 991},
                "teams": {"home": {"name": "Home 1"}, "away": {"name": "Away 1"}},
                "lineups": [{
                    "team": {"name": team},
                    "startXI": [{"player": {"id": 1, "name": f"{team} Keeper", "number": 1, "pos": "G"}}],
                    "substitutes": [],
                } for team in ("Home 1", "Away 1")],
                "statistics": [],
            }]}

    api = ApiClient()
    refresh_match_intelligence(
        collection, [fixture], now=NOW,
        espn_fetcher=lambda event_id: _summary(with_players=False),
        api_football_client=api,
    )

    assert api.calls[0][1] == {"ids": "991"}
    stored = collection.find_one({
        "_id": competition_document_id("ucl2026", "match_intelligence:espn-1")
    })
    assert stored["data"]["source"] == "api_football"
    assert len(stored["data"]["lineups"]) == 2


def test_t15_id_discovery_schedules_one_enriched_fallback_retry():
    current = NOW
    fixture = {
        "id": "late", "home_team": "Home", "away_team": "Away",
        "commence_time": (current + timedelta(minutes=10)).isoformat(), "completed": False,
    }

    class ApiClient:
        def __init__(self):
            self.calls = []

        def request(self, path, params=None):
            self.calls.append(params)
            if "ids" not in params:
                return {"response": [{
                    "fixture": {"id": 77},
                    "teams": {"home": {"name": "Home"}, "away": {"name": "Away"}},
                }]}
            return {"response": [{
                "fixture": {"id": 77},
                "teams": {"home": {"name": "Home"}, "away": {"name": "Away"}},
                "lineups": [{
                    "team": {"name": team},
                    "startXI": [{"player": {"name": f"{team} Keeper"}}],
                    "substitutes": [],
                } for team in ("Home", "Away")],
            }]}

    api = ApiClient()
    espn_calls = []
    kwargs = {
        "espn_fetcher": lambda event_id: espn_calls.append(event_id) or _summary(with_players=False),
        "api_football_client": api,
    }
    collection = MemoryCollection()
    refresh_match_intelligence(collection, [fixture], now=current, **kwargs)
    refresh_match_intelligence(collection, [fixture], now=current + timedelta(minutes=2), **kwargs)

    assert "date" in api.calls[0]
    assert api.calls[1] == {"ids": "77"}
    assert espn_calls == ["late"]
    stored = collection.find_one({
        "_id": competition_document_id("ucl2026", "match_intelligence:late")
    })
    assert len(stored["data"]["lineups"]) == 2


def test_partial_provider_id_map_rediscoveries_the_matchday():
    fixtures = [{
        "id": event_id, "home_team": f"Home {event_id}", "away_team": f"Away {event_id}",
        "commence_time": (NOW + timedelta(minutes=30)).isoformat(), "completed": False,
    } for event_id in ("one", "two")]
    date_key = (NOW + timedelta(minutes=30)).date().isoformat()
    collection = MemoryCollection([{
        "_id": competition_document_id("ucl2026", f"match_intelligence_provider_ids:{date_key}"),
        "event_ids": {"one": "11"},
    }])

    class ApiClient:
        def __init__(self):
            self.params = None

        def request(self, path, params=None):
            self.params = params
            return {"response": []}

    api = ApiClient()
    refresh_match_intelligence(
        collection, fixtures, now=NOW,
        espn_fetcher=lambda event_id: _summary(with_players=False),
        api_football_client=api,
    )

    assert api.params["date"] == date_key
    assert "ids" not in api.params
    mapped = collection.find_one({
        "_id": competition_document_id("ucl2026", "match_intelligence:one")
    })
    assert mapped["fallback_pending"] is True


def test_cached_match_intelligence_returns_explicit_unavailable_without_provider_call():
    result = cached_match_intelligence(MemoryCollection(), "missing", "ucl2026")

    assert result == {
        "status": "unavailable",
        "source": "cache",
        "observed_at": None,
        "reason": "not_collected",
        "lineups": {},
        "team_stats": {},
        "injuries": {"status": "unavailable", "players": []},
    }


def test_api_football_uses_ucl_season_start_year_after_new_year():
    current = datetime(2027, 1, 20, 18, 30, tzinfo=timezone.utc)
    fixture = {
        "id": "jan",
        "home_team": "Arsenal",
        "away_team": "Bayern Munich",
        "commence_time": (current + timedelta(minutes=30)).isoformat(),
        "completed": False,
    }

    class ApiClient:
        def __init__(self):
            self.params = None

        def request(self, path, params=None):
            self.params = params
            return {"response": []}

    api = ApiClient()
    refresh_match_intelligence(
        MemoryCollection(), [fixture], now=current,
        espn_fetcher=lambda event_id: _summary(with_players=False),
        api_football_client=api,
    )

    assert api.params["season"] == 2026


def test_espn_summary_calls_are_capped_per_maintenance_run():
    fixtures = [{
        "id": str(index),
        "commence_time": (NOW + timedelta(minutes=30)).isoformat(),
        "completed": False,
    } for index in range(20)]
    calls = []

    result = refresh_match_intelligence(
        MemoryCollection(), fixtures, now=NOW,
        espn_fetcher=lambda event_id: calls.append(event_id) or _summary(),
    )

    assert result["espn_calls"] == 12
    assert len(calls) == 12
