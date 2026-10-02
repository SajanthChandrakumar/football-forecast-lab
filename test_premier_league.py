from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import HTTPException

from src.competitions import COMPETITIONS, competition_document_id, get_competition
from src.routes.matches import build_elo_snapshot, init_router as matches_router
from src.routes.simulate import init_router as simulate_router
from src.services import espn_data
from src.services import maintenance
from src.services.elo_sync import perform_elo_sync
from src.services.ucl_providers import ingest_clubelo


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def find(self, query=None):
        return list(self.documents.values())

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        doc = dict(self.documents.get(key, {"_id": key}))
        doc.update(update.get("$set", {}))
        if key not in self.documents:
            doc.update(update.get("$setOnInsert", {}))
        self.documents[key] = doc

    def replace_one(self, query, document, upsert=False):
        self.documents[document["_id"]] = dict(document)

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise ValueError("duplicate id")
        self.documents[document["_id"]] = dict(document)

    def delete_one(self, query):
        self.documents.pop(query["_id"], None)


class Response:
    def __init__(self, payload=None, text=""):
        self.payload = payload or {}
        self.text = text
        self.headers = {}
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _fixture_event(event_id, event_date, season_year):
    return {
        "id": event_id,
        "date": event_date,
        "season": {"year": season_year, "slug": "2026-27-english-premier-league"},
        "competitions": [{
            "status": {"type": {"completed": False, "detail": "Scheduled"}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Arsenal"}},
                {"homeAway": "away", "team": {"displayName": "Manchester City"}},
            ],
        }],
    }


def test_epl_registry_uses_club_mode_and_isolated_collections():
    comp = get_competition("epl2026")

    assert comp.is_club_competition is True
    assert get_competition("ucl2026").is_club_competition is True
    assert get_competition("wc2026").is_club_competition is False
    assert comp.espn_slug == "eng.1"
    assert comp.odds_api_sport_key == "soccer_epl"
    assert comp.season == "2026/27"
    assert comp.archive_collection == "archive_epl2026"
    assert comp.cache_collection == "cache_epl2026"
    assert comp.custom_bot_collection == "custom_bot_epl2026"
    assert competition_document_id(comp, "matches_cache") == "epl2026:matches_cache"
    assert set(COMPETITIONS) == {"wc2026", "ucl2026", "epl2026"}


def test_epl_scoreboard_uses_year_queries_and_filters_the_2026_27_season(monkeypatch):
    calls = []
    events = [
        _fixture_event("first", "2026-08-01T14:00:00Z", 2026),
        _fixture_event("last", "2027-06-30T20:00:00Z", 2026),
        _fixture_event("before-season", "2026-07-31T20:00:00Z", 2026),
        _fixture_event("previous-season", "2026-08-02T20:00:00Z", 2025),
        _fixture_event("after-season", "2027-07-01T20:00:00Z", 2027),
    ]

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return Response({"events": events})

    monkeypatch.setattr(espn_data.requests, "get", fake_get)
    fixtures = espn_data.get_scoreboard(
        competition="epl2026",
        now=datetime(2026, 10, 1, tzinfo=timezone.utc),
        use_cache=False,
    )

    assert [call[1]["dates"] for call in calls] == ["2026", "2027"]
    assert all(call[1]["limit"] == 1000 for call in calls)
    assert all("/soccer/eng.1/scoreboard" in call[0] for call in calls)
    assert [fixture["id"] for fixture in fixtures] == ["first", "last"]


def test_epl_standings_normalize_the_league_table(monkeypatch):
    calls = []
    payload = {"children": [{
        "name": "2026-27 English Premier League",
        "standings": {"entries": [{
            "team": {"displayName": "Arsenal", "logos": [{"href": "https://img/arsenal.png"}]},
            "stats": [
                {"name": "rank", "value": 1}, {"name": "gamesPlayed", "value": 7},
                {"name": "wins", "value": 6}, {"name": "ties", "value": 1},
                {"name": "losses", "value": 0}, {"name": "pointsFor", "value": 17},
                {"name": "pointsAgainst", "value": 3}, {"name": "pointDifferential", "value": 14},
                {"name": "points", "value": 19},
            ],
        }]},
    }]}

    def fake_get(url, params, timeout):
        calls.append((url, params))
        return Response(payload)

    monkeypatch.setattr(espn_data.requests, "get", fake_get)
    table = espn_data.get_standings_groups(competition="epl2026")

    assert calls[0][1] == {"season": 2026}
    assert "/soccer/eng.1/standings" in calls[0][0]
    assert table[0]["rows"] == [{
        "pos": 1, "team": "Arsenal", "logo": "https://img/arsenal.png",
        "p": 7, "w": 6, "d": 1, "l": 0, "gf": 17, "ga": 3, "gd": 14, "pts": 19,
    }]


def test_epl_standings_are_refreshed_at_most_once_a_day():
    cache = MemoryCollection()
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    calls = []

    def fetcher(*, competition):
        calls.append(competition.id)
        return [{"name": "2026-27 English Premier League", "rows": [{"team": "Arsenal"}]}]

    refresh_standings = getattr(maintenance, "_refresh_standings", None)
    assert refresh_standings is not None
    first = refresh_standings(cache, get_competition("epl2026"), fetcher, now)
    second = refresh_standings(cache, get_competition("epl2026"), fetcher, now + timedelta(hours=23))

    assert calls == ["epl2026"]
    assert first["status"] == "fresh"
    assert second["source"] == "cache"
    assert cache.find_one({"_id": "epl2026:standings_cache"})["data"][0]["rows"] == [{"team": "Arsenal"}]


def test_epl_persists_predictions_only_for_open_fixtures(monkeypatch):
    cache = MemoryCollection([{
        "_id": "epl2026:matches_cache",
        "data": [
            {"id": "finished", "home_team": "Arsenal", "away_team": "Chelsea", "completed": True, "actual_score": "1:0"},
            {"id": "upcoming", "home_team": "Arsenal", "away_team": "Chelsea", "completed": False},
        ],
    }])

    def enrich(matches, *_args):
        for match in matches:
            match.update({
                "model_tip": "1:0", "top_tip": "1:0", "source_mode": "elo-only",
                "model_version": "test", "matrix": {"1:0": 1.0},
            })
        return matches

    monkeypatch.setattr("src.routes.matches._enrich_edge", enrich)
    updated = maintenance._persist_club_predictions(
        cache, "epl2026", object(), {"status": "fresh", "rows": [{"team": "Arsenal"}]},
    )
    persisted = cache.find_one({"_id": "epl2026:matches_cache"})["data"]

    assert updated == 1
    assert "model_tip" not in persisted[0]
    assert persisted[1]["model_tip"] == "1:0"


def test_epl_elo_sync_does_not_reconstruct_completed_forecasts():
    cache = MemoryCollection([{
        "_id": "epl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
        "rows": [{"team": "Arsenal", "elo": 1800}],
    }])
    archive = MemoryCollection([{
        "_id": "played", "competition": "epl2026",
        "post_match_result": {"status": "completed", "actual_score": "2:0"},
        "metadata": {"home_team": "Arsenal", "away_team": "Chelsea"},
    }])

    result = perform_elo_sync(
        object(), object(), cache, archive, "/private/tmp", "/private/tmp/scores.json", object(),
        competition="epl2026",
    )

    assert result["updates"] == 0
    assert "prediction" not in archive.find_one({"_id": "played"})


def test_failed_epl_standings_attempt_is_throttled_and_preserves_old_rows():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": "epl2026:standings_cache",
        "status": "fresh",
        "observed_at": (now - timedelta(days=2)).isoformat(),
        "data": [{"name": "2026-27 English Premier League", "rows": [{"team": "Arsenal"}]}],
    }])
    calls = []

    def fetcher(*, competition):
        calls.append(competition.id)
        return [{"name": "2026-27 English Premier League", "rows": []}]

    refresh_standings = getattr(maintenance, "_refresh_standings", None)
    assert refresh_standings is not None
    first = refresh_standings(cache, get_competition("epl2026"), fetcher, now)
    second = refresh_standings(cache, get_competition("epl2026"), fetcher, now + timedelta(hours=1))
    stored = cache.find_one({"_id": "epl2026:standings_cache"})

    assert calls == ["epl2026"]
    assert first["status"] == second["status"] == "stale"
    assert stored["data"][0]["rows"] == [{"team": "Arsenal"}]
    assert stored["observed_at"] == (now - timedelta(days=2)).isoformat()
    assert stored["last_attempt_at"] == now.isoformat()


def test_epl_clubelo_requires_fixture_teams_and_keeps_missing_ratings_unavailable():
    cache = MemoryCollection([{
        "_id": "epl2026:matches_cache",
        "data": [{"home_team": "Arsenal", "away_team": "Manchester City"}],
    }])
    html = "<table><tr><td>1</td><td>Arsenal</td><td>1800</td></tr></table>"

    result = ingest_clubelo(cache, competition="epl2026", request_get=lambda *args, **kwargs: Response(text=html))

    assert result["status"] == "failed"
    assert result["coverage"]["required"] == 2
    assert result["coverage"]["missing"] == ["Man City"]
    assert result["rows"] == []
    math_engine = type("Math", (), {"elo_df": pd.DataFrame([{"team_name": "Arsenal", "elo_rating": 1800}])})()
    assert build_elo_snapshot(math_engine, "Arsenal", "Manchester City", "epl2026") is None


def test_epl_reuses_complete_daily_clubelo_ratings_when_fixture_results_change():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    fixture = {
        "id": "fixture-1", "home_team": "Arsenal", "away_team": "Manchester City",
        "commence_time": "2027-01-15T15:00:00Z", "completed": False,
    }
    cache = MemoryCollection([
        {
            "_id": "epl2026:matches_cache", "status": "fresh",
            "observed_at": (now - timedelta(days=2)).isoformat(), "data": [fixture],
        },
        {
            "_id": "epl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
            "observed_at": (now - timedelta(hours=1)).isoformat(), "rows": [{"team": "Arsenal"}],
            "coverage": {"required": 20, "available": 20, "missing": []},
        },
        {
            "_id": "epl2026:odds_discovery_state",
            "observed_at": (now - timedelta(hours=1)).isoformat(),
        },
    ])
    fixture_status = {**fixture, "completed": True, "actual_score": "2:0"}
    clubelo_calls = []

    result = maintenance.run_maintenance(
        cache,
        object(),
        competition="epl2026",
        now=now,
        fixture_fetcher=lambda **kwargs: [fixture_status],
        clubelo_ingestor=lambda *args, **kwargs: clubelo_calls.append(kwargs),
    )

    assert result["fixture_status"]["changed"] is True
    assert result["clubelo_status"]["source"] == "clubelo"
    assert clubelo_calls == []
    assert result["provider_calls"] == 0


def test_epl_matches_select_the_competition_team_form_service():
    cache = MemoryCollection([{
        "_id": "epl2026:matches_cache",
        "data": [{
            "id": "played", "home_team": "Arsenal", "away_team": "Manchester City",
            "completed": True, "actual_score": "1:0", "commence_time": "2026-08-01T14:00:00Z",
        }],
    }])

    class TeamFormService:
        def cached_forms_for_matches(self, matches):
            return [{**match, "cached_form_attached": True} for match in matches]

    router = matches_router(
        type("Math", (), {"team_forms": {}, "reload_elo_data": lambda self, **kwargs: None})(),
        object(),
        {"epl2026": cache},
        {"epl2026": MemoryCollection()},
        team_form_service={"epl2026": TeamFormService()},
    )
    result = router.routes[0].endpoint(competition="epl2026")

    assert result[0]["cached_form_attached"] is True


def test_epl_is_not_sent_to_a_knockout_tournament_simulator():
    router = simulate_router(object(), {"epl2026": MemoryCollection()})
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_knockout")

    with pytest.raises(HTTPException) as exc_info:
        endpoint(competition="epl2026")

    assert exc_info.value.status_code == 400


def test_pl_uses_only_t75_and_t15_and_dispatches_intelligence():
    from test_task2_providers import MemoryCollection as NestedCollection
    now = datetime(2026, 10, 10, 11, 0, tzinfo=timezone.utc)
    cache = NestedCollection([{'_id':'epl2026:matches_cache', 'data':[
        {'id':'game', 'completed':False, 'commence_time':(now + timedelta(minutes=30)).isoformat()}
    ]}])
    class Provider:
        calls = 0
        def get_competition_odds(self, competition, market):
            self.calls += 1
            return []
    provider = Provider()
    dispatched = []
    def refresh(*args, **kwargs):
        dispatched.append(kwargs['competition'].id)
        return {'espn_calls':0}
    first = maintenance.run_maintenance(cache, provider, competition='epl2026', now=now, match_intelligence_refresher=refresh)
    second = maintenance.run_maintenance(cache, provider, competition='epl2026', now=now + timedelta(minutes=15))
    repeated = maintenance.run_maintenance(cache, provider, competition='epl2026', now=now + timedelta(minutes=16))
    assert first['buckets'] == ['t75m']
    assert second['buckets'] == ['t15m']
    assert repeated['provider_calls'] == 0
    assert provider.calls == 2
    assert dispatched == ['epl2026']


def test_pl_discovery_does_not_poll_empty_distant_schedule():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    cache = MemoryCollection([{'_id':'epl2026:matches_cache', 'data':[
        {'id':'distant', 'completed':False, 'commence_time':(now + timedelta(days=9)).isoformat()}
    ]}])
    assert maintenance._discovery_due(cache, get_competition('epl2026'), now) is False


def test_budget_block_does_not_report_an_http_call_or_erase_existing_market_odds():
    from src.quota_store import ProviderBudgetExceeded
    from test_task2_providers import MemoryCollection as NestedCollection
    now = datetime(2026, 10, 10, 11, 0, tzinfo=timezone.utc)
    odds = {'home':2.0, 'draw':3.0, 'away':4.0}
    cache = NestedCollection([{'_id':'epl2026:matches_cache', 'data':[
        {'id':'game', 'completed':False, 'odds':odds, 'commence_time':(now + timedelta(minutes=30)).isoformat()}
    ]}])
    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            raise ProviderBudgetExceeded('blocked')
    result = maintenance.run_maintenance(cache, Provider(), competition='epl2026', now=now)
    assert result['reason'] == 'provider_budget_blocked'
    assert result['provider_calls'] == 0
    assert cache.documents['epl2026:matches_cache']['data'][0]['odds'] == odds
