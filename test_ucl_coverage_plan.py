from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.competitions import competition_document_id
from src.math_engine import MathEngine
from src.routes.matches import _enrich_edge
from src.routes.predict import init_router as predict_router
from src.routes.custom_bot import init_router as custom_bot_router
from src.services.maintenance import run_maintenance
from src.services.ucl_providers import CLUBELO_URL, _parse_team_page, ingest_clubelo

from test_task2_providers import MemoryCollection


class NoopLimiter:
    def limit(self, *_args, **_kwargs):
        return lambda function: function


def test_clubelo_homepage_team_row_wins_over_unrelated_elo_text():
    html = '<div>Elo: 1370</div><span>Sabah FK</span><td class="r">1563</td>'
    assert _parse_team_page(html, "Sabah FK")["elo_rating"] == 1563.0


def test_ucl_enrichment_builds_elo_only_prediction_without_bookmaker_odds():
    engine = MathEngine("data/elo_ratings.csv")
    engine.elo_df = pd.DataFrame([
        {"team_name": "Bayern Munich", "elo_rating": 1900.0},
        {"team_name": "Arsenal", "elo_rating": 1800.0},
    ])
    engine.team_forms = {}
    match = {
        "id": "ucl-elo-only",
        "home_team": "Bayern Munich",
        "away_team": "Arsenal",
        "commence_time": "2026-10-01T19:00:00Z",
        "odds": {},
        "raw_match": {"round": "League Phase"},
    }

    enriched = _enrich_edge([match], engine, object(), competition="ucl2026")[0]

    assert enriched["source_mode"] == "elo-only"
    assert enriched["model_tip"] not in (None, "N/A")
    probabilities = enriched["probabilities"]
    assert set(probabilities) == {"home", "draw", "away"}
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert all(0.0 < probability < 1.0 for probability in probabilities.values())
    assert enriched["odds"] == {}


def test_bookmaker_prediction_keeps_the_real_capture_time():
    engine = MathEngine("data/elo_ratings.csv")
    engine.elo_df = pd.DataFrame([
        {"team_name": "Bayern Munich", "elo_rating": 1900.0},
        {"team_name": "Arsenal", "elo_rating": 1800.0},
    ])
    captured = "2026-09-10T10:00:00+00:00"
    match = {
        "id": "ucl-real-odds",
        "home_team": "Bayern Munich",
        "away_team": "Arsenal",
        "odds": {"home": 2.0, "draw": 3.2, "away": 4.0},
        "odds_observed_at": captured,
        "odds_provenance": {"source": "odds_api", "observed_at": captured},
        "raw_match": {"round": "League Phase"},
    }

    enriched = _enrich_edge([match], engine, object(), competition="ucl2026")[0]

    assert enriched["observed_at"] == captured
    assert enriched["input_provenance"]["odds"]["observed_at"] == captured


def test_legacy_bookmaker_odds_without_capture_time_are_marked_stale():
    engine = MathEngine("data/elo_ratings.csv")
    engine.elo_df = pd.DataFrame([
        {"team_name": "Bayern Munich", "elo_rating": 1900.0},
        {"team_name": "Arsenal", "elo_rating": 1800.0},
    ])
    match = {
        "id": "ucl-legacy-odds",
        "home_team": "Bayern Munich",
        "away_team": "Arsenal",
        "odds": {"home": 2.0, "draw": 3.2, "away": 4.0},
        "raw_match": {"round": "League Phase"},
    }

    enriched = _enrich_edge([match], engine, object(), competition="ucl2026")[0]

    assert enriched["source_status"] == "stale"
    assert enriched["input_provenance"]["odds"]["observed_at"] is None


def test_ucl_detail_prediction_uses_cached_elo_when_bookmaker_odds_are_missing():
    engine = MathEngine("data/elo_ratings.csv")
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "ucl-elo-only", "home_team": "AEK Athens", "away_team": "Feyenoord Rotterdam", "odds": {}}],
    }, {
        "_id": competition_document_id("ucl2026", "elo_ratings"),
        "status": "fresh",
        "source": "clubelo",
        "observed_at": "2026-09-10T10:00:00+00:00",
        "rows": [
            {"team_name": "AEK", "elo_rating": 1707.0},
            {"team_name": "Feyenoord", "elo_rating": 1710.0},
        ],
    }])
    router = predict_router(engine, object(), {"ucl2026": cache}, NoopLimiter())
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/predict")

    result = endpoint(None, {
        "competition": "ucl2026",
        "match": {"id": "ucl-elo-only", "home_team": "AEK Athens", "away_team": "Feyenoord Rotterdam"},
    }, competition="ucl2026")

    assert result["source_mode"] == "elo-only"
    assert result["model_tip"]
    assert sum(result["probabilities"].values()) == pytest.approx(1.0)


def test_ucl_custom_bot_skips_archived_match_without_real_elo():
    class Engine:
        calls = 0

        def reload_elo_data(self, **kwargs):
            return None

        def compute_custom_bot_tip(self, *args, **kwargs):
            self.calls += 1
            return "1:0"

    archive = MemoryCollection([{
        "_id": "ucl-no-elo",
        "metadata": {"home_team": "Unknown A", "away_team": "Unknown B"},
        "pre_match_snapshot": {"odds": {"home": 2.0, "draw": 3.2, "away": 4.0}},
        "post_match_result": {"status": "completed", "actual_score": "1:0"},
    }])
    engine = Engine()
    router = custom_bot_router(engine, {"ucl2026": archive}, {"ucl2026": MemoryCollection()}, NoopLimiter())
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/custom_bot/simulate")

    result = endpoint(None, {"competition": "ucl2026"}, competition="ucl2026")

    assert result["matches"] == 0
    assert engine.calls == 0


def test_clubelo_ingestion_supplements_ranking_with_cached_ucl_teams():
    ranking_html = """
    <table id="ranking">
      <tr><th>Rank</th><th>Club</th><th>Elo</th></tr>
      <tr><td>1</td><td>Bayern Munich</td><td>1921</td></tr>
      <tr><td>2</td><td>Arsenal</td><td>1840</td></tr>
    </table>
    """
    page_html = {
        "aek": "<html><h1>AEK</h1><div>Current Elo: 1707</div></html>",
        "feyenoord": "<html><h1>Feyenoord</h1><div>Current Elo: 1710</div></html>",
    }
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{
            "id": "fixture-with-missing-ratings",
            "home_team": "AEK Athens",
            "away_team": "Feyenoord Rotterdam",
            "commence_time": "2026-10-01T19:00:00Z",
        }],
    }])
    calls = []

    class Response:
        status_code = 200
        headers = {}

        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def request_get(url, **kwargs):
        calls.append(url)
        if url == CLUBELO_URL:
            return Response(ranking_html)
        slug = url.rstrip("/").rsplit("/", 1)[-1].casefold()
        return Response(page_html[slug])

    document = ingest_clubelo(
        cache,
        competition="ucl2026",
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        request_get=request_get,
    )

    rows = {row["team"]: row for row in document["rows"]}
    assert rows["AEK"]["elo_rating"] == 1707.0
    assert rows["Feyenoord"]["elo_rating"] == 1710.0
    assert rows["AEK"]["elo_rating"] != 1500.0
    assert rows["Feyenoord"]["elo_rating"] != 1500.0
    fetched_pages = {url.rstrip("/").rsplit("/", 1)[-1].casefold() for url in calls[1:]}
    assert {"aek", "feyenoord"} <= fetched_pages


def test_clubelo_304_still_supplements_new_fixture_teams():
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "clubelo_ratings"),
        "rows": [{"team": "Arsenal", "team_name": "Arsenal", "elo": 2039.0, "elo_rating": 2039.0}],
    }, {
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"home_team": "Arsenal", "away_team": "AEK Athens"}],
    }])

    class Response:
        headers = {}

        def __init__(self, text="", status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            return None

    def request_get(url, **kwargs):
        if url == CLUBELO_URL:
            return Response(status_code=304)
        return Response("<div>Elo: 1707</div>")

    document = ingest_clubelo(cache, competition="ucl2026", request_get=request_get)

    assert document["coverage"]["missing"] == []
    assert {row["team"] for row in document["rows"]} == {"Arsenal", "AEK"}


def test_failed_clubelo_refresh_persists_stale_status_and_attempt_time():
    last_good = "2026-09-20T08:00:00+00:00"
    attempt = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    rows = [
        {"team": "Bayern Munich", "team_name": "Bayern Munich", "elo": 1900.0, "elo_rating": 1900.0},
        {"team": "Arsenal", "team_name": "Arsenal", "elo": 2039.0, "elo_rating": 2039.0},
    ]
    provenance = {
        "source": "clubelo",
        "url": CLUBELO_URL,
        "observed_at": last_good,
        "etag": "last-good-etag",
    }
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "clubelo_ratings"),
        "competition": "ucl2026",
        "status": "fresh",
        "source": "clubelo",
        "observed_at": last_good,
        "rows": rows,
        "provenance": provenance,
        "etag": "last-good-etag",
    }, {
        "_id": competition_document_id("ucl2026", "elo_ratings"),
        "competition": "ucl2026",
        "status": "fresh",
        "source": "clubelo",
        "observed_at": last_good,
        "rows": rows,
        "provenance": provenance,
    }, {
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{
            "id": "freshness-check",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": "2026-10-01T19:00:00Z",
            "odds": {},
        }],
    }])

    def failed_request(*_args, **_kwargs):
        raise RuntimeError("ClubElo is temporarily unavailable")

    returned = ingest_clubelo(
        cache,
        competition="ucl2026",
        observed_at=attempt,
        request_get=failed_request,
    )

    for key in ("clubelo_ratings", "elo_ratings"):
        stored = cache.find_one({"_id": competition_document_id("ucl2026", key)})
        assert stored["status"] == "stale"
        assert stored["observed_at"] == attempt.isoformat()
        assert stored["error"] == "ClubElo is temporarily unavailable"
        assert stored["rows"] == rows
        assert stored["provenance"]["observed_at"] == last_good
    assert returned["status"] == "stale"
    assert returned["rows"] == rows

    match = {"id": "freshness-check", "home_team": "Bayern Munich", "away_team": "Arsenal", "odds": {}}
    enriched = _enrich_edge(
        [match],
        MathEngine("data/elo_ratings.csv"),
        None,
        competition="ucl2026",
        pool_context_collection=cache,
    )[0]
    assert enriched["status"] == "stale"
    assert enriched["input_provenance"]["elo"]["status"] == "stale"


@pytest.mark.parametrize("include_due_fixture", [False, True])
def test_ucl_daily_discovery_uses_one_h2h_totals_bulk_call(include_due_fixture):
    now = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    future_kickoff = now + timedelta(days=3)
    fixtures = [{
        "id": "ucl-discovery",
        "home_team": "Bayern Munich",
        "away_team": "Arsenal",
        "commence_time": future_kickoff.isoformat(),
    }]
    quotes = [{
        "id": "ucl-discovery",
        "home_team": "Bayern Munich",
        "away_team": "Arsenal",
        "commence_time": future_kickoff.isoformat(),
        "odds": {"home": 2.0, "draw": 3.2, "away": 4.0},
    }]
    if include_due_fixture:
        due_kickoff = now + timedelta(minutes=10)
        fixtures.append({
            "id": "ucl-due",
            "home_team": "Barcelona",
            "away_team": "Feyenoord Rotterdam",
            "commence_time": due_kickoff.isoformat(),
        })
        quotes.append({
            "id": "ucl-due",
            "home_team": "Barcelona",
            "away_team": "Feyenoord",
            "commence_time": due_kickoff.isoformat(),
            "odds": {"home": 1.8, "draw": 3.5, "away": 4.6},
        })
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": fixtures,
    }])

    class Provider:
        def __init__(self):
            self.calls = []

        def get_competition_odds(self, competition, market):
            self.calls.append((competition.id, market))
            return quotes

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=now)

    assert provider.calls == [("ucl2026", "h2h,totals")]
    assert result["provider_calls"] == 1
    stored = {
        match["id"]: match
        for match in cache.find_one({"_id": competition_document_id("ucl2026", "matches_cache")})["data"]
    }
    assert stored["ucl-discovery"]["odds"] == {"home": 2.0, "draw": 3.2, "away": 4.0}
    assert stored["ucl-discovery"]["odds_observed_at"] == now.isoformat()
    assert stored["ucl-discovery"]["odds_provenance"]["source"] == "odds_api"
    if include_due_fixture:
        assert stored["ucl-due"]["odds"] == {"home": 1.8, "draw": 3.5, "away": 4.6}
