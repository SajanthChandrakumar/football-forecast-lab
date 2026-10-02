from datetime import datetime, timedelta, timezone
import pytest
import requests
from fastapi import FastAPI
from starlette.requests import Request

from src.competitions import competition_document_id
from src.routes.maintenance import init_router
from src.routes.matches import init_router as matches_router
from src.services import espn_data
from src.services.maintenance import _match_by_names, run_maintenance
from src.services.snapshots import (
    BUCKET_OFFSETS,
    append_odds_snapshot,
    select_t15_snapshot,
)
from src.services.ucl_providers import (
    compose_match_sources,
    ingest_clubelo,
    parse_clubelo_html,
)
from src.odds_engine import OddsApiEngine
from src import quota_store
from src.odds_engine_apifootball import OddsApiEngine as ApiFootballOddsEngine
from src.routes.matches import build_elo_snapshot
from src.routes.elo_status import init_router as elo_status_router


@pytest.fixture(autouse=True)
def no_live_budget_store(monkeypatch):
    monkeypatch.setattr(quota_store, "reserve_request", lambda *args, **kwargs: 0)


class DuplicateKeyError(Exception):
    pass


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {}
        self.inserts = []
        for document in documents:
            self.documents[document["_id"]] = dict(document)

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def find(self, query=None):
        values = list(self.documents.values())
        if not query:
            return values
        def matches(document, field, expected):
            if isinstance(expected, dict) and "$in" in expected:
                return document.get(field) in expected["$in"]
            return document.get(field) == expected
        return [doc for doc in values if all(matches(doc, k, v) for k, v in query.items())]

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise DuplicateKeyError(document["_id"])
        self.documents[document["_id"]] = dict(document)
        self.inserts.append(dict(document))

    def update_one(self, query, update, upsert=False):
        key = query.get("_id")
        document = dict(self.documents.get(key, {"_id": key}))
        if "$set" in update:
            for field, value in update["$set"].items():
                target = document
                bits = field.split(".")
                for bit in bits[:-1]:
                    target = target.setdefault(bit, {})
                target[bits[-1]] = value
        if "$setOnInsert" in update and key not in self.documents:
            document.update(update["$setOnInsert"])
        if "$addToSet" in update:
            for field, value in update["$addToSet"].items():
                values = list(document.get(field, []))
                if value not in values:
                    values.append(value)
                document[field] = values
        self.documents[key] = document

    def delete_one(self, query):
        self.documents.pop(query.get("_id"), None)


class MongoRejectsImmutableId(MemoryCollection):
    def update_one(self, query, update, upsert=False):
        if any(field == "_id" or field.endswith("._id") for field in update.get("$set", {})):
            raise AssertionError("Mongo rejects _id in $set")
        super().update_one(query, update, upsert=upsert)


class OwnershipAwareCollection(MongoRejectsImmutableId):
    def delete_one(self, query):
        key = query.get("_id")
        document = self.documents.get(key)
        if document and all(document.get(field) == value for field, value in query.items()):
            self.documents.pop(key, None)


def _event(event_id, date):
    return {
        "id": event_id,
        "date": date,
        "season": {"slug": "league-phase"},
        "competitions": [{
            "status": {"type": {"completed": False, "detail": "Scheduled"}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Bayern Munich"}},
                {"homeAway": "away", "team": {"displayName": "Arsenal"}},
            ],
        }],
    }


def test_ucl_espn_uses_calendar_years_filters_dates_and_deduplicates(monkeypatch):
    calls = []
    base = datetime(2026, 12, 31, tzinfo=timezone.utc)

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return Response({"events": [
            _event("before", "2026-12-29T18:00:00Z"),
            _event("same", "2026-12-30T18:00:00Z"),
            _event("other", "2027-01-01T18:00:00Z"),
            _event("after", "2027-01-03T18:00:00Z"),
        ]})

    monkeypatch.setattr(espn_data.requests, "get", fake_get)
    events = espn_data.get_scoreboard(
        competition="ucl2026",
        days_back=1,
        days_forward=2,
        now=base,
        use_cache=False,
    )

    assert len(calls) == 2
    assert [call[1]["dates"] for call in calls] == ["2026", "2027"]
    assert all("uefa.champions" in call[0] for call in calls)
    assert [event["id"] for event in events] == ["same", "other"]


def test_wc_espn_keeps_its_single_range_request(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"events": []}

    def fake_get(url, params, timeout):
        calls.append(params["dates"])
        return Response()

    espn_data.get_scoreboard(
        competition="wc2026",
        days_back=2,
        days_forward=3,
        now=datetime(2026, 9, 1, tzinfo=timezone.utc),
        request_get=fake_get,
        use_cache=False,
    )

    assert calls == ["20260830-20260904"]


def test_espn_parses_current_and_legacy_team_logo_fields(monkeypatch):
    event = _event("logos", "2026-09-01T18:00:00Z")
    competitors = event["competitions"][0]["competitors"]
    competitors[0]["team"].update({"logo": "https://img.example/home.png"})
    competitors[1]["team"].update({"logos": [{"href": "https://img.example/away.png"}]})

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"events": [event]}

    result = espn_data.get_scoreboard(
        competition="wc2026",
        days_back=0,
        days_forward=0,
        now=datetime(2026, 9, 1, tzinfo=timezone.utc),
        request_get=lambda *args, **kwargs: Response(),
        use_cache=False,
    )

    assert result[0]["home_logo"] == "https://img.example/home.png"
    assert result[0]["away_logo"] == "https://img.example/away.png"


def test_ucl_espn_keeps_successful_year_when_another_year_fails():
    base = datetime(2026, 12, 31, tzinfo=timezone.utc)

    class Response:
        def __init__(self, payload=None, error=None):
            self.payload = payload or {}
            self.error = error

        def raise_for_status(self):
            if self.error:
                raise self.error

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if params["dates"] == "2026":
            return Response({"events": [_event("kept", "2026-12-30T18:00:00Z")]})
        return Response(error=requests.HTTPError("502 Bad Gateway"))

    events = espn_data.get_scoreboard(
        competition="ucl2026",
        days_back=1,
        days_forward=2,
        now=base,
        chunk_days=7,
        use_cache=False,
        request_get=fake_get,
    )

    assert [event["id"] for event in events] == ["kept"]


def test_ucl_espn_raises_when_every_requested_year_fails():
    class Response:
        def raise_for_status(self):
            raise requests.HTTPError("502 Bad Gateway")

    with pytest.raises(requests.HTTPError):
        espn_data.get_scoreboard(
            competition="ucl2026",
            days_back=0,
            days_forward=0,
            now=datetime(2026, 9, 1, tzinfo=timezone.utc),
            use_cache=False,
            request_get=lambda *args, **kwargs: Response(),
        )


def test_clubelo_cache_contract_preserves_alias_and_provenance(monkeypatch):
    html = """
    <html><body><table id="ranking">
      <tr><th>Rank</th><th>Club</th><th>Elo</th></tr>
      <tr><td>1</td><td>Bayern Munich</td><td>1921</td></tr>
      <tr><td>2</td><td>Arsenal</td><td>1840</td></tr>
    </table></body></html>
    """
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"home_team": "Bayern Munich", "away_team": "Arsenal"}],
    }])

    class Response:
        text = html
        content = html.encode()
        headers = {"etag": '"ucl"'}

        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.services.ucl_providers.requests.get", lambda *args, **kwargs: Response())
    observed_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    document = ingest_clubelo(cache, competition="ucl2026", observed_at=observed_at)

    assert document["status"] == "fresh"
    assert document["source"] == "clubelo"
    assert document["observed_at"] == observed_at.isoformat()
    assert document["provenance"]["url"]
    assert {row["team"] for row in document["rows"]} == {"Bayern Munich", "Arsenal"}
    assert cache.find_one({"_id": competition_document_id("ucl2026", "clubelo_ratings")})["etag"] == '"ucl"'


def test_clubelo_parser_reads_current_vega_dataset():
    html = '''<script>
      var vegaJson = {"datasets":{"data-live":[
        {"Name":"Bayern München","Elo":2042.3},
        {"Name":"Arsenal","Elo":2035.4}
      ]}};
    </script>'''

    rows = parse_clubelo_html(html)

    assert rows == [
        {"rank": 1, "team": "Bayern Munich", "team_name": "Bayern Munich", "elo": 2042.3, "elo_rating": 2042.3},
        {"rank": 2, "team": "Arsenal", "team_name": "Arsenal", "elo": 2035.4, "elo_rating": 2035.4},
    ]


def test_clubelo_persistence_never_sets_immutable_mongo_id(monkeypatch):
    html = "<table><tr><td>1</td><td>Arsenal</td><td>1840</td></tr></table>"

    class Response:
        text = html
        headers = {}

        def raise_for_status(self):
            return None

    cache = MongoRejectsImmutableId([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"home_team": "Arsenal", "away_team": "Arsenal"}],
    }])
    document = ingest_clubelo(cache, competition="ucl2026", request_get=lambda *a, **k: Response())
    assert document["status"] == "fresh"
    assert cache.find_one({"_id": competition_document_id("ucl2026", "elo_ratings")})["rows"]


def test_clubelo_failure_is_truthful_and_does_not_create_ratings(monkeypatch):
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"home_team": "Arsenal", "away_team": "Arsenal"}],
    }])

    def failed_get(*args, **kwargs):
        raise RuntimeError("ClubElo unavailable")

    document = ingest_clubelo(cache, competition="ucl2026", request_get=failed_get)
    assert document["status"] == "failed"
    assert document["rows"] == []
    assert "error" in document
    stored = cache.find_one({"_id": competition_document_id("ucl2026", "clubelo_ratings")})
    assert stored["status"] == "failed"
    assert stored["rows"] == []
    assert stored["coverage"]["missing"] == ["Arsenal"]


def test_partial_clubelo_snapshot_is_failed_and_does_not_publish_partial_ratings():
    clubs = ["Arsenal", "Bayern Munich"]
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"home_team": clubs[0], "away_team": clubs[1]}],
    }])

    class Response:
        text = "<table><tr><td>1</td><td>Arsenal</td><td>1840</td></tr></table>"
        headers = {}

        def raise_for_status(self):
            return None

    document = ingest_clubelo(cache, competition="ucl2026", request_get=lambda *a, **k: Response())

    assert document["status"] == "failed"
    assert document["rows"] == []
    assert document["coverage"]["missing"] == ["Bayern Munich"]
    assert "Bayern Munich" in document["error"]
    for key in ("clubelo_ratings", "elo_ratings"):
        stored = cache.find_one({"_id": competition_document_id("ucl2026", key)})
        assert stored["status"] == "failed"
        assert stored["rows"] == []
        assert stored["coverage"]["missing"] == ["Bayern Munich"]


def test_partial_clubelo_refresh_preserves_only_a_complete_previous_snapshot():
    clubs = ["Arsenal", "Bayern Munich"]
    good_rows = [
        {"team": "Arsenal", "team_name": "Arsenal", "elo": 1840.0, "elo_rating": 1840.0},
        {"team": "Bayern Munich", "team_name": "Bayern Munich", "elo": 1921.0, "elo_rating": 1921.0},
    ]
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"home_team": clubs[0], "away_team": clubs[1]}],
    }, {
        "_id": competition_document_id("ucl2026", "clubelo_ratings"),
        "competition": "ucl2026", "status": "fresh", "rows": good_rows,
        "coverage": {"required": 2, "available": 2, "missing": [], "errors": {}},
        "provenance": {"source": "clubelo", "observed_at": "2026-09-20T08:00:00+00:00"},
    }])

    class Response:
        text = "<table><tr><td>1</td><td>Arsenal</td><td>1840</td></tr></table>"
        headers = {}

        def raise_for_status(self):
            return None

    document = ingest_clubelo(cache, competition="ucl2026", request_get=lambda *a, **k: Response())

    assert document["status"] == "stale"
    assert document["rows"] == good_rows
    assert document["coverage"]["missing"] == ["Bayern Munich"]
    assert document["coverage"]["errors"]["Bayern Munich"]
    compatibility = cache.find_one({"_id": competition_document_id("ucl2026", "elo_ratings")})
    assert compatibility["status"] == "stale"
    assert compatibility["rows"] == good_rows
    assert compatibility["coverage"]["missing"] == ["Bayern Munich"]


def test_elo_ratings_status_route_exposes_stale_coverage_without_changing_rating_map():
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "clubelo_ratings"),
        "competition": "ucl2026",
        "status": "stale",
        "source": "clubelo",
        "observed_at": "2026-09-24T08:00:00+00:00",
        "error": "ClubElo snapshot is incomplete; missing current ratings for: Bayern Munich",
        "coverage": {"required": 36, "available": 35, "missing": ["Bayern Munich"], "errors": {"Bayern Munich": "not published"}},
    }])
    router = elo_status_router({"ucl2026": cache})
    route = next(route for route in router.routes if getattr(route, "path", None) == "/api/elo_ratings_status")
    response = route.endpoint(competition="ucl2026")

    assert response == {
        "status": "stale",
        "source": "clubelo",
        "observed_at": "2026-09-24T08:00:00+00:00",
        "error": "ClubElo snapshot is incomplete; missing current ratings for: Bayern Munich",
        "coverage": {"required": 36, "available": 35, "missing": ["Bayern Munich"], "errors": {"Bayern Munich": "not published"}},
    }


def test_source_modes_are_explicit_when_provider_is_missing():
    assert compose_match_sources({"home": 2}, {"home": 1800})["source_mode"] == "odds+elo"
    assert compose_match_sources({"home": 2}, None)["source_mode"] == "odds-only"
    assert compose_match_sources(None, {"home": 1800})["source_mode"] == "elo-only"
    unavailable = compose_match_sources(None, None)
    assert unavailable["source_mode"] == "unavailable"
    assert unavailable["status"] == "unavailable"


def test_failed_or_empty_elo_is_not_a_present_source():
    result = compose_match_sources(
        {"home": 2.0, "draw": 3.2, "away": 4.0},
        {"status": "failed", "rows": [], "source": "clubelo"},
    )
    assert result["source_mode"] == "odds-only"
    assert result["source"] == "odds_api"


def test_odds_provider_uses_configurable_competition_identifier(monkeypatch):
    calls = []

    class Response:
        headers = {}
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": "e1", "bookmakers": []}]

    def fake_get(url, params, timeout):
        calls.append((url, params))
        return Response()

    monkeypatch.setenv("ODDS_API_UCL2026_SPORT_KEY", "soccer_custom_ucl")
    monkeypatch.setattr("src.odds_engine.requests.get", fake_get)
    engine = object.__new__(OddsApiEngine)
    engine.api_key = "captured-key"
    engine._update_quota = lambda headers: None

    assert engine.get_competition_odds("ucl2026", market="h2h,totals")
    assert calls[0][0].endswith("/soccer_custom_ucl/odds")
    assert calls[0][1]["markets"] == "h2h,totals"


def test_ucl_quote_matching_uses_club_aliases_and_kickoff():
    fixture = {
        "home_team": "Sporting CP",
        "away_team": "Galatasaray",
        "commence_time": "2026-09-09T19:00:00Z",
    }
    wrong_kickoff = {
        "id": "wrong",
        "home_team": "Sporting Lisbon",
        "away_team": "Galatasaray",
        "commence_time": "2026-10-09T19:00:00Z",
    }
    right_kickoff = {
        "id": "right",
        "home_team": "Sporting Lisbon",
        "away_team": "Galatasaray",
        "commence_time": "2026-09-09T19:00:00Z",
    }

    assert _match_by_names({"wrong": wrong_kickoff, "right": right_kickoff}, fixture) == right_kickoff


def test_maintenance_stores_every_bulk_quote_but_snapshots_only_due_fixture():
    now = datetime(2026, 9, 9, 18, 45, tzinfo=timezone.utc)
    due = datetime(2026, 9, 9, 19, 0, tzinfo=timezone.utc)
    later = datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc)
    fixtures = [
        {"id": "espn-liverpool", "home_team": "Liverpool", "away_team": "Atlético Madrid", "commence_time": due.isoformat()},
        {"id": "espn-feyenoord", "home_team": "Barcelona", "away_team": "Feyenoord Rotterdam", "commence_time": later.isoformat()},
        {"id": "espn-sporting", "home_team": "Sporting CP", "away_team": "Galatasaray", "commence_time": later.isoformat()},
        {"id": "espn-psg", "home_team": "Paris Saint-Germain", "away_team": "Slovan Bratislava", "commence_time": later.isoformat()},
        {"id": "espn-bodo", "home_team": "Bayern Munich", "away_team": "Bodo/Glimt", "commence_time": later.isoformat()},
        {"id": "espn-slavia", "home_team": "Slavia Prague", "away_team": "Lens", "commence_time": later.isoformat()},
    ]
    provider_pairs = [
        ("Liverpool", "Atlético Madrid"),
        ("Barcelona", "Feyenoord"),
        ("Sporting Lisbon", "Galatasaray"),
        ("Paris Saint Germain", "ŠK Slovan Bratislava"),
        ("Bayern Munich", "Bodø/Glimt"),
        ("Slavia Praha", "RC Lens"),
    ]
    quotes = [
        {
            "id": f"odds-{index}",
            "home_team": home,
            "away_team": away,
            "commence_time": (due if index == 0 else later).isoformat(),
            "odds": {"home": 2.0 + index / 10, "draw": 3.2, "away": 4.0},
        }
        for index, (home, away) in enumerate(provider_pairs)
    ]
    cache = MemoryCollection()

    class Provider:
        def get_competition_odds(self, competition, market):
            return quotes

    run_maintenance(
        {"ucl2026": cache},
        Provider(),
        competition="ucl2026",
        now=now,
        fixture_fetcher=lambda **kwargs: fixtures,
        clubelo_ingestor=lambda *args, **kwargs: {"status": "fresh", "source": "clubelo"},
    )

    stored = cache.find_one({"_id": competition_document_id("ucl2026", "matches_cache")})["data"]
    assert [match.get("odds", {}).get("home") for match in stored] == [2.0, 2.1, 2.2, 2.3, 2.4, 2.5]
    snapshots = [document for document in cache.inserts if "odds_snapshot" in document["_id"]]
    assert len(snapshots) == 1
    assert snapshots[0]["event_id"] == "espn-liverpool"


def test_maintenance_fixture_refresh_preserves_cached_odds_and_predictions():
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    old_odds = {"home": 1.9, "draw": 3.4, "away": 4.2}
    old_prediction = {"model_tip": "1:0", "probabilities": {"home": 0.5}}
    old_snapshot = {"odds": old_odds, "observed_at": "2026-09-09T17:00:00+00:00"}
    bookmakers = [{"key": "book-a"}]
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{
            "id": "e1",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": kickoff.isoformat(),
            "odds": old_odds,
            "bookmakers": bookmakers,
            "pre_match_snapshot": old_snapshot,
            "prediction": old_prediction,
            "raw_match": {"bookmakers": bookmakers},
        }],
    }])

    class Provider:
        def get_competition_odds(self, competition, market):
            return []

    run_maintenance(
        cache,
        Provider(),
        competition="ucl2026",
        now=now,
        fixture_fetcher=lambda **kwargs: [{
            "id": "e1",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "home_logo": "https://img.example/bayern.png",
            "commence_time": kickoff.isoformat(),
            "round": "League Phase",
        }],
    )

    refreshed = cache.find_one({"_id": competition_document_id("ucl2026", "matches_cache")})["data"][0]
    assert refreshed["home_logo"] == "https://img.example/bayern.png"
    assert refreshed["odds"] == old_odds
    assert refreshed["bookmakers"] == bookmakers
    assert refreshed["raw_match"]["bookmakers"] == bookmakers
    assert refreshed["pre_match_snapshot"] == old_snapshot
    assert refreshed["prediction"] == old_prediction


def test_append_only_snapshots_and_t15_selector_use_observation_time():
    cache = MemoryCollection()
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    first = append_odds_snapshot(
        cache,
        competition="ucl2026",
        event_id="e1",
        bucket="t24h",
        observed_at=kickoff - timedelta(hours=24),
        odds={"home": 2.0, "draw": 3.0, "away": 4.0},
    )
    second = append_odds_snapshot(
        cache,
        competition="ucl2026",
        event_id="e1",
        bucket="t15m",
        observed_at=kickoff - timedelta(minutes=10),
        odds={"home": 1.9, "draw": 3.1, "away": 4.2},
    )

    assert first["_id"] != second["_id"]
    assert len(cache.inserts) == 2
    selected = select_t15_snapshot(cache.inserts, kickoff)
    assert selected["odds"]["home"] == 2.0
    assert selected["bucket"] == "t24h"


def test_maintenance_missed_buckets_are_not_backfilled_and_bulk_call_is_capped():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=10)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat(), "home_team": "Bayern Munich", "away_team": "Arsenal"}],
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, competition, market):
            self.calls += 1
            return [{"id": "e1", "home_team": "Bayern Munich", "away_team": "Arsenal", "bookmakers": []}]

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=now)

    assert provider.calls == 1
    assert result["buckets"] == ["t24h", "t6h", "t75m", "t30m", "t15m"]
    state = cache.find_one({"_id": competition_document_id("ucl2026", "odds_bucket_state")})
    assert state["events"]["e1"]["t15m"]["status"] == "unavailable"
    assert state["events"]["e1"]["t24h"]["status"] == "unavailable"
    assert state["events"]["e1"]["t24h"]["error"] == "missed"
    assert all(
        state["events"]["e1"][bucket]["status"] in {"fresh", "stale", "unavailable", "failed"}
        for bucket in state["events"]["e1"]
    )
    assert [doc["bucket"] for doc in cache.inserts if "odds_snapshot" in doc["_id"]] == ["t15m"]
    again = run_maintenance(cache, provider, competition="ucl2026", now=now + timedelta(minutes=1))
    assert provider.calls == 1
    assert again["buckets"] == []


def test_force_maintenance_is_a_safe_noop():
    cache = MemoryCollection()

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("force must not call a provider")

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", force=True)
    assert result == {
        "status": "noop", "reason": "force_disabled", "provider_calls": 0, "mutated": False,
        "team_form_status": {"status": "skipped", "reason": "force_disabled"},
    }
    assert cache.documents == {}


def test_no_due_bucket_and_fresh_daily_discovery_does_not_spend_credits_or_write_snapshots():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(days=3)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }, {
        "_id": competition_document_id("ucl2026", "odds_discovery_state"),
        "observed_at": now.isoformat(),
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            return []

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=now)
    assert result["provider_calls"] == 0
    assert provider.calls == 0
    assert not [doc for doc in cache.documents.values() if "snapshot" in doc.get("_id", "")]


def test_authenticated_maintenance_runs_the_bounded_history_backfill_once():
    now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "odds_discovery_state"),
        "observed_at": now.isoformat(),
    }])

    class TeamFormService:
        def __init__(self):
            self.history_calls = 0

        def refresh_daily(self, now=None):
            return {"status": "fresh"}

        def refresh_history_depth(self, now=None):
            self.history_calls += 1
            return {"status": "fresh", "teams_attempted": 6}

        def cached_history_fixtures(self):
            return []

    service = TeamFormService()
    result = run_maintenance(
        cache, object(), competition="ucl2026", now=now,
        team_form_service=service,
    )

    assert service.history_calls == 1
    assert result["team_form_status"]["history_backfill"] == {
        "status": "fresh", "teams_attempted": 6,
    }


def test_maintenance_reuses_recent_ucl_fixtures_and_ratings_between_odds_windows():
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    fixture = {
        "id": "e1", "home_team": "Arsenal", "away_team": "Lille",
        "commence_time": (now + timedelta(days=3)).isoformat(), "completed": False,
    }
    cache = MemoryCollection([
        {"_id": "ucl2026:matches_cache", "data": [fixture], "status": "fresh", "source": "espn",
         "observed_at": (now - timedelta(hours=1)).isoformat()},
        {"_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
         "observed_at": (now - timedelta(hours=1)).isoformat(), "rows": [{"team_name": "Arsenal", "elo_rating": 1900}]},
        {"_id": "ucl2026:odds_discovery_state", "observed_at": now.isoformat()},
    ])
    fixture_calls = []
    rating_calls = []

    def fetcher(**kwargs):
        fixture_calls.append(kwargs)
        return [fixture]

    def ratings(*args, **kwargs):
        rating_calls.append((args, kwargs))
        return {"status": "fresh", "rows": []}

    result = run_maintenance(
        cache, object(), competition="ucl2026", now=now,
        fixture_fetcher=fetcher, clubelo_ingestor=ratings,
    )

    assert result["status"] == "idle"
    assert result["fixture_status"]["source"] == "cache"
    assert result["clubelo_status"]["rows"][0]["team_name"] == "Arsenal"
    assert fixture_calls == rating_calls == []


def test_maintenance_refreshes_ucl_fixtures_near_unfinished_kickoff():
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    fixture = {
        "id": "e1", "home_team": "Arsenal", "away_team": "Lille",
        "commence_time": (now + timedelta(minutes=10)).isoformat(), "completed": False,
    }
    cache = MemoryCollection([
        {"_id": "ucl2026:matches_cache", "data": [fixture], "status": "fresh", "source": "espn",
         "observed_at": (now - timedelta(minutes=20)).isoformat()},
        {"_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
         "observed_at": now.isoformat(), "rows": [{"team_name": "Arsenal", "elo_rating": 1900}]},
        {"_id": "ucl2026:odds_discovery_state", "observed_at": now.isoformat()},
        {"_id": "ucl2026:odds_bucket_state", "events": {"e1": {
            bucket: {"status": "fresh"} for bucket in BUCKET_OFFSETS
        }}},
    ])
    calls = []
    rating_calls = []

    def fetcher(**kwargs):
        calls.append(kwargs)
        return [{**fixture, "completed": True, "actual_score": "2:0"}]

    def ratings(*args, **kwargs):
        rating_calls.append((args, kwargs))
        return {"status": "fresh", "rows": [{"team_name": "Arsenal", "elo_rating": 1901}]}

    result = run_maintenance(
        cache, object(), competition="ucl2026", now=now,
        fixture_fetcher=fetcher, clubelo_ingestor=ratings,
    )

    assert len(calls) == 1
    assert len(rating_calls) == 1
    assert result["fixture_status"]["changed"] is True
    assert cache.find_one({"_id": "ucl2026:matches_cache"})["data"][0]["actual_score"] == "2:0"


def test_maintenance_reads_odds_bucket_state_once_for_all_fixtures():
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)

    class CountingCollection(MemoryCollection):
        bucket_reads = 0

        def find_one(self, query):
            if query.get("_id") == "ucl2026:odds_bucket_state":
                self.bucket_reads += 1
            return super().find_one(query)

    cache = CountingCollection([
        {"_id": "ucl2026:matches_cache", "data": [
            {"id": str(i), "commence_time": (now + timedelta(days=3)).isoformat()}
            for i in range(4)
        ]},
        {"_id": "ucl2026:odds_discovery_state", "observed_at": now.isoformat()},
    ])

    result = run_maintenance(cache, object(), competition="ucl2026", now=now)

    assert result["status"] == "idle"
    assert cache.bucket_reads == 1


def test_provider_failure_marks_bucket_failed_without_fabricating_odds():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            raise RuntimeError("Odds API failed")

    result = run_maintenance(cache, Provider(), competition="ucl2026", now=kickoff - timedelta(minutes=14))
    assert result["status"] == "failed"
    state = cache.find_one({"_id": competition_document_id("ucl2026", "odds_bucket_state")})
    assert state["events"]["e1"]["t15m"]["status"] == "failed"
    assert not [doc for doc in cache.documents.values() if "snapshot" in doc.get("_id", "")]


def test_captured_bucket_uses_fresh_status():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            return [{"id": "e1", "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}}]

    run_maintenance(cache, Provider(), competition="ucl2026", now=kickoff - timedelta(minutes=14))
    state = cache.find_one({"_id": competition_document_id("ucl2026", "odds_bucket_state")})
    assert state["events"]["e1"]["t15m"]["status"] == "fresh"


def test_live_maintenance_lease_is_a_unique_no_provider_claim():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=14)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }, {
        "_id": competition_document_id("ucl2026", "maintenance_lease"),
        "lease_until": (now + timedelta(minutes=2)).isoformat(),
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            return []

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=now)
    assert result["status"] == "skipped"
    assert provider.calls == 0


def test_expired_lease_replacement_does_not_delete_a_new_owner_lease():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=14)
    lease_id = competition_document_id("ucl2026", "maintenance_lease")
    cache = OwnershipAwareCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }, {
        "_id": lease_id,
        "lease_until": (now - timedelta(minutes=1)).isoformat(),
        "lease_token": "expired-owner",
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            cache.update_one(
                {"_id": lease_id},
                {"$set": {"lease_token": "renewed-owner", "lease_until": (now + timedelta(minutes=5)).isoformat()}},
            )
            return []

    run_maintenance(cache, Provider(), competition="ucl2026", now=now)
    assert cache.find_one({"_id": lease_id})["lease_token"] == "renewed-owner"


def test_public_match_force_is_cache_only():
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "cached"}],
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("public force must not call a provider")

    class Engine:
        team_forms = {}

    router = matches_router(Engine(), Provider(), {"ucl2026": cache}, {"ucl2026": MemoryCollection()})
    result = router.routes[0].endpoint(force=True, competition="ucl2026")
    assert result[0]["id"] == "cached"
    assert "edge_home" in result[0]
    assert "is_ko_phase" in result[0]


def test_force_maintenance_validates_competition_before_noop():
    with pytest.raises(ValueError, match="Unknown competition"):
        run_maintenance({}, object(), competition="bad", force=True)


def test_maintenance_route_returns_http_400_for_unknown_competition():
    endpoint = init_router({"ucl2026": MemoryCollection()}, object(), cron_secret="test-secret").routes[0].endpoint
    scope = {
        "type": "http", "method": "POST", "path": "/api/internal/maintenance", "headers": [(b"authorization", b"Bearer test-secret")],
        "query_string": b"", "scheme": "http", "server": ("test", 80), "client": ("test", 1), "root_path": "", "http_version": "1.1",
    }
    with pytest.raises(Exception) as exc_info:
        endpoint(Request(scope), competition="bad")
    assert getattr(exc_info.value, "status_code", None) == 400


def test_ucl_unknown_clubs_have_no_synthetic_elo_snapshot():
    class Engine:
        elo_df = type("Frame", (), {"team_name": []})()

    assert build_elo_snapshot(Engine(), "Unknown Home", "Unknown Away", "ucl2026") is None


def test_api_football_ucl_quotes_use_ucl_sport_key(monkeypatch):
    fixture = {
        "fixture": {"id": 1, "date": "2026-09-10T18:00:00Z"},
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Bayern Munich"}},
        "league": {"round": "League Phase"},
    }
    odd = {
        "fixture": {"id": 1},
        "bookmakers": [{"id": 1, "name": "Book", "bets": [{"id": 1, "values": [
            {"value": "Home", "odd": "2.0"}, {"value": "Draw", "odd": "3.0"}, {"value": "Away", "odd": "4.0"}
        ]}]}],
    }
    engine = object.__new__(ApiFootballOddsEngine)
    engine._request = lambda path, params: {"response": [fixture] if path == "/fixtures" else [odd]}
    assert engine.get_competition_odds("ucl2026")[0]["sport_key"] == "soccer_uefa_champs_league"


def test_maintenance_route_requires_bearer_secret_and_supports_idempotency():
    cache = MemoryCollection()

    class Provider:
        calls = 0

        def get_competition_odds(self, competition, market):
            self.calls += 1
            return []

    provider = Provider()
    endpoint = init_router({"ucl2026": cache}, provider, cron_secret="test-secret").routes[0].endpoint

    def request(headers):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/internal/maintenance",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "query_string": b"force=true",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1),
            "root_path": "",
            "http_version": "1.1",
        }
        return Request(scope)

    with pytest.raises(Exception) as missing:
        endpoint(request({}))
    assert getattr(missing.value, "status_code", None) == 401
    with pytest.raises(Exception) as wrong:
        endpoint(request({"Authorization": "Bearer wrong"}))
    assert getattr(wrong.value, "status_code", None) == 401
    response = endpoint(request({"Authorization": "Bearer test-secret"}), force=True)
    assert response["provider_calls"] == 0
    assert provider.calls == 0
