from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json

from fastapi import APIRouter

from src import quota_store
from src.competitions import competition_document_id
from src.routes.data_status import init_router


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


class ReadOnlyCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: deepcopy(doc) for doc in documents}
        self.reads = []
        self.find_one_calls = 0
        self.find_calls = 0
        self.find_queries = []
        self.writes = []

    def find_one(self, query, projection=None):
        self.find_one_calls += 1
        self.reads.append((deepcopy(query), deepcopy(projection)))
        return deepcopy(self.documents.get(query.get("_id")))

    def find(self, query=None, projection=None):
        self.find_calls += 1
        self.reads.append((deepcopy(query), deepcopy(projection)))
        self.find_queries.append((deepcopy(query), deepcopy(projection)))
        values = list(self.documents.values())
        ids = (query or {}).get("_id", {})
        if isinstance(ids, dict) and "$in" in ids:
            values = [doc for doc in values if doc.get("_id") in ids["$in"]]
        return [_project_document(doc, projection) for doc in values]

    def insert_one(self, document):
        self.writes.append(("insert_one", deepcopy(document)))

    def update_one(self, query, update, **kwargs):
        self.writes.append(("update_one", deepcopy(query), deepcopy(update)))

    def delete_one(self, query):
        self.writes.append(("delete_one", deepcopy(query)))


def _project_path(source, parts):
    if isinstance(source, list):
        return [value for item in source if (value := _project_path(item, parts)) is not None]
    if not isinstance(source, dict) or parts[0] not in source:
        return None
    key = parts[0]
    if len(parts) == 1:
        return {key: deepcopy(source[key])}
    nested = _project_path(source[key], parts[1:])
    return {key: nested} if nested is not None else None


def _merge_projection(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_projection(target[key], value)
        elif isinstance(value, list) and isinstance(target.get(key), list):
            for index, item in enumerate(value):
                if index >= len(target[key]):
                    target[key].append(item)
                elif isinstance(item, dict) and isinstance(target[key][index], dict):
                    _merge_projection(target[key][index], item)
                else:
                    target[key][index] = item
        else:
            target[key] = value


def _project_document(document, projection):
    if not projection:
        return deepcopy(document)
    result = {"_id": deepcopy(document["_id"])} if projection.get("_id", 1) else {}
    for path, include in projection.items():
        if include and path != "_id":
            projected = _project_path(document, path.split("."))
            if projected:
                _merge_projection(result, projected)
    return result


class ProjectionCollection(ReadOnlyCollection):
    def find_one(self, query, projection=None):
        document = super().find_one(query)
        if document is None or projection is None:
            return document
        return _project_document(document, projection)

    def find(self, query=None, projection=None):
        return super().find(query, projection)


def _doc(comp, key, **values):
    return {"_id": competition_document_id(comp, key), **values}


def _endpoint(router):
    assert isinstance(router, APIRouter)
    route = next(route for route in router.routes if route.path == "/api/data-status")
    return route.endpoint


def test_data_status_has_fixed_rows_and_separates_configured_from_observed_sources(monkeypatch):
    cache = ReadOnlyCollection([
        _doc("epl2026", "matches_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
             data=[{"id": "m1", "completed": True, "odds_observed_at": NOW.isoformat(),
                    "odds_provenance": {"source": "odds_api"}}]),
        _doc("epl2026", "standings_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
             data=[{"rows": [{"team": "A"}, {"team": "B"}]}]),
        _doc("epl2026", "team_form_sync", status="partial", source="espn", provider="espn",
             last_attempt_at=NOW.isoformat(), last_successful_at=NOW.isoformat(),
             teams_total=20, teams_failed=2, teams_unavailable=1),
        _doc("epl2026", "team_form_teams", status="fresh", source="espn", provider="espn",
             observed_at=NOW.isoformat(), teams=[{"team_id": "1"}, {"team_id": "2"}]),
        _doc("epl2026", "elo_ratings", status="fresh", source="clubelo", observed_at=NOW.isoformat(),
             rows=[{"team": "A"}, {"team": "B"}], coverage={"available": 2, "required": 2}),
        _doc("epl2026", "maintenance_status", status="partial", last_run_at=NOW.isoformat(),
             last_successful_at=NOW.isoformat(), error="provider failure"),
        _doc("epl2026", "maintenance_lease", lease_until="2026-10-25T12:05:00+00:00",
             lease_token="valid-token", competition="epl2026"),
    ])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": True,
        "providers": {
            "odds": {"data": {"remaining": "0", "used": "7"}, "observed_at": NOW.timestamp(), "requests": []},
            "football": {"data": {"remaining": "42", "used": "3", "limit": "100"},
                        "observed_at": NOW.timestamp(), "requests": [[NOW.timestamp(), 2]]},
        },
    })

    result = _endpoint(init_router(
        {"wc2026": ReadOnlyCollection(), "ucl2026": ReadOnlyCollection(), "epl2026": cache},
        odds_provider="odds_api",
        team_form_providers={"ucl2026": ["api_football", "espn"], "epl2026": ["espn"]},
        now_fn=lambda: NOW,
    ))(competition="epl2026")

    assert result["competition"] == "epl2026"
    assert {row["id"] for row in result["datasets"]} == {
        "fixtures_results", "standings", "team_form", "ratings", "odds", "lineups",
    }
    rows = {row["id"]: row for row in result["datasets"]}
    assert rows["fixtures_results"]["providers"] == {"configured": ["espn"], "observed": ["espn"]}
    assert rows["team_form"]["providers"]["configured"] == ["espn"]
    assert rows["team_form"]["status"] == "partial"
    assert rows["team_form"]["last_attempt_at"] == NOW.isoformat()
    assert rows["team_form"]["last_successful_at"] == NOW.isoformat()
    assert rows["odds"]["providers"] == {"configured": ["odds_api"], "observed": ["odds_api"]}
    assert rows["standings"]["coverage"] == {"available": 2, "required": None, "unit": "rows"}
    assert result["maintenance"]["running"] is True
    assert result["quotas"]["scope"] == "global_shared_all_competitions"
    assert result["quotas"]["providers"]["odds"]["reported"]["remaining"] == 0
    assert result["quotas"]["providers"]["odds"]["reported"]["limit"] is None
    assert result["quotas"]["providers"]["football"]["app_budget"]["used"] == 2
    assert cache.writes == []


def test_data_status_is_competition_scoped_and_never_promotes_partial_to_fresh(monkeypatch):
    wc = ReadOnlyCollection([_doc("wc2026", "matches_cache", status="partial", source="espn",
                                    observed_at=NOW.isoformat(), data=[{"id": "wc"}])])
    ucl = ReadOnlyCollection([_doc("ucl2026", "matches_cache", status="fresh", source="espn",
                                     observed_at=NOW.isoformat(), data=[{"id": "ucl"}])])
    epl = ReadOnlyCollection([_doc("epl2026", "matches_cache", status="fresh", source="espn",
                                     observed_at=NOW.isoformat(), data=[{"id": "epl"}])])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    endpoint = _endpoint(init_router(
        {"wc2026": wc, "ucl2026": ucl, "epl2026": epl}, now_fn=lambda: NOW,
    ))

    result = endpoint(competition="wc2026")
    fixtures = next(row for row in result["datasets"] if row["id"] == "fixtures_results")
    assert fixtures["status"] == "partial"
    assert fixtures["coverage"]["available"] == 1
    assert all(not collection.writes for collection in (wc, ucl, epl))
    assert not any(query.get("_id") == "ucl2026:matches_cache" for query, _ in wc.reads)


def test_team_form_status_normalizes_persisted_espn_fotmob_provenance(monkeypatch):
    cache = ReadOnlyCollection([_doc(
        "epl2026", "team_form_sync", status="fresh", source="espn+fotmob", provider="espn+fotmob",
        observed_at=NOW.isoformat(), last_attempt_at=NOW.isoformat(),
        last_successful_at=NOW.isoformat(), teams_total=20,
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router(
        {"epl2026": cache}, team_form_providers={"epl2026": ["espn"]}, now_fn=lambda: NOW,
    ))(competition="epl2026")

    form = next(row for row in result["datasets"] if row["id"] == "team_form")
    assert form["providers"] == {"configured": ["espn"], "observed": ["espn", "fotmob"]}
    assert form["status"] == "fresh"
    assert form["observed_at"] == NOW.isoformat()
    assert form["last_attempt_at"] == NOW.isoformat()
    assert form["last_successful_at"] == NOW.isoformat()


def test_unknown_team_form_source_identifiers_are_not_reported(monkeypatch):
    cache = ReadOnlyCollection([_doc(
        "epl2026", "team_form_sync", status="fresh",
        source="https://provider.invalid/?apiKey=secret", observed_at=NOW.isoformat(), teams_total=20,
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router(
        {"epl2026": cache}, team_form_providers={"epl2026": ["espn"]}, now_fn=lambda: NOW,
    ))(competition="epl2026")

    form = next(row for row in result["datasets"] if row["id"] == "team_form")
    assert form["providers"] == {"configured": ["espn"], "observed": []}
    assert "provider.invalid" not in repr(result)
    assert "secret" not in repr(result)


def test_ucl_standings_are_not_derived_from_an_incomplete_fixture_sample(monkeypatch):
    cache = ReadOnlyCollection([_doc(
        "ucl2026", "matches_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
        data=[{"id": "ucl-1", "home_team": "A", "away_team": "B", "completed": True}],
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router({"ucl2026": cache}, now_fn=lambda: NOW))(competition="ucl2026")
    standings = next(row for row in result["datasets"] if row["id"] == "standings")
    assert standings["source_kind"] == "derived"
    assert standings["providers"] == {"configured": [], "observed": ["espn"]}
    assert standings["coverage"] is None
    assert standings["status"] == "unavailable"


def test_odds_status_uses_bucket_observation_without_loading_or_requiring_inline_odds(monkeypatch):
    cache = ReadOnlyCollection([
        _doc("epl2026", "matches_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
             data=[{"id": "event-1"}]),
        _doc("epl2026", "odds_bucket_state", events={
            "event-1": {"t15": {"status": "fresh", "source": "odds_api", "observed_at": NOW.isoformat()}},
        }),
    ])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router(
        {"epl2026": cache}, odds_provider="odds_api", now_fn=lambda: NOW,
    ))(competition="epl2026")
    odds = next(row for row in result["datasets"] if row["id"] == "odds")
    assert odds["status"] == "fresh"
    assert odds["observed_at"] == NOW.isoformat()
    assert odds["coverage"] == {"available": 1, "required": None, "unit": "matches"}
    assert odds["providers"]["observed"] == ["odds_api"]


def test_data_status_treats_future_and_missing_timestamps_as_unknown_and_redacts_errors(monkeypatch):
    cache = ReadOnlyCollection([
        _doc("epl2026", "matches_cache", status="fresh", source="espn",
             observed_at="2026-10-26T12:00:00+00:00", error="https://example.invalid/?apiKey=secret", data=[{"id": "m1"}]),
        _doc("epl2026", "elo_ratings", status="fresh", source="clubelo", rows=[{"team": "A"}]),
        _doc("epl2026", "standings_cache", status="fresh", source="espn",
             observed_at="2026-10-20T12:00:00+00:00", data=[{"rows": [{"team": "A"}]}]),
    ])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    rows = {row["id"]: row for row in result["datasets"]}
    assert rows["fixtures_results"]["status"] in {"stale", "unknown"}
    assert rows["fixtures_results"]["last_successful_at"] is None
    assert rows["ratings"]["status"] == "unknown"
    assert rows["standings"]["status"] == "stale"
    assert rows["standings"]["error"] == "Gespeicherte Daten können veraltet sein."
    assert "secret" not in repr(result)
    assert "example.invalid" not in repr(result)


def test_failed_ratings_attempt_keeps_last_successful_capture_from_provenance(monkeypatch):
    previous = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    cache = ReadOnlyCollection([_doc(
        "epl2026", "clubelo_ratings", status="stale", source="clubelo",
        observed_at=NOW.isoformat(), error="provider error", rows=[{"team": "A"}],
        provenance={"source": "clubelo", "observed_at": previous.isoformat()},
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    ratings = next(row for row in result["datasets"] if row["id"] == "ratings")
    assert ratings["status"] == "stale"
    assert ratings["observed_at"] == previous.isoformat()
    assert ratings["last_attempt_at"] == NOW.isoformat()
    assert ratings["last_successful_at"] == previous.isoformat()


def test_failed_capture_timestamp_is_an_attempt_not_a_success(monkeypatch):
    cache = ReadOnlyCollection([_doc(
        "epl2026", "matches_cache", status="failed", source="espn",
        observed_at=NOW.isoformat(), error="refresh failed", data=[{"id": "old-match"}],
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    fixtures = next(row for row in result["datasets"] if row["id"] == "fixtures_results")
    assert fixtures["status"] == "failed"
    assert fixtures["observed_at"] is None
    assert fixtures["last_attempt_at"] == NOW.isoformat()
    assert fixtures["last_successful_at"] is None


def test_maintenance_status_reports_only_a_valid_unexpired_lease(monkeypatch):
    cache = ReadOnlyCollection([
        _doc("epl2026", "maintenance_status", status="success", last_run_at=NOW.isoformat()),
        _doc("epl2026", "maintenance_lease", lease_until="2026-10-25T11:59:59+00:00"),
    ])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    assert result["maintenance"]["running"] is False


def test_future_lease_without_owner_token_is_not_running(monkeypatch):
    cache = ReadOnlyCollection([_doc(
        "epl2026", "maintenance_lease", lease_until="2026-10-25T12:05:00+00:00",
        competition="epl2026",
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    result = _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    assert result["maintenance"]["running"] is False


def test_data_status_read_failure_is_sanitized_and_does_not_write(monkeypatch):
    class BrokenCollection(ReadOnlyCollection):
        def find_one(self, query, projection=None):
            raise RuntimeError("mongodb://user:secret@example.invalid")

        def find(self, query=None, projection=None):
            raise RuntimeError("mongodb://user:secret@example.invalid")

    cache = BrokenCollection()
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("private")))
    result = _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    assert all(row["status"] == "unknown" for row in result["datasets"])
    assert all(row["error"] == "Gespeicherte Daten sind derzeit nicht lesbar." for row in result["datasets"])
    assert result["quotas"]["providers"]["odds"]["app_budget"]["status"] == "unknown"
    assert "secret" not in repr(result)
    assert "example.invalid" not in repr(result)
    assert cache.writes == []


def test_cache_reads_use_one_bounded_matches_projection(monkeypatch):
    cache = ReadOnlyCollection([_doc(
        "epl2026", "matches_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
        data=[{"id": "m1", "home_team": "A", "away_team": "B", "odds_observed_at": NOW.isoformat(),
               "odds_provenance": {"source": "odds_api"}, "score_matrix": [[1, 2]]}],
    )])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")
    reads = [
        projection for query, projection in cache.find_queries
        if "epl2026:matches_cache" in query.get("_id", {}).get("$in", [])
    ]
    assert len(reads) == 1
    assert "data.odds_observed_at" in reads[0]
    assert "data.odds_provenance.source" in reads[0]
    assert "data.score_matrix" not in reads[0]
    assert "data.odds" not in reads[0]


def test_data_status_batches_competition_reads_and_uses_narrow_union_projection(monkeypatch):
    cache = ReadOnlyCollection([
        _doc("epl2026", "matches_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
             teams=["A", "B"], data=[{"id": "m1", "score_matrix": [[1, 2]], "odds": {"book": 2}}]),
        _doc("epl2026", "standings_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
             coverage={"available": 2}, data=[{"rows": [{"team": "A", "pos": 1}]}]),
        _doc("epl2026", "elo_ratings", status="fresh", source="clubelo", observed_at=NOW.isoformat(),
             rows=[{"team": "A", "elo_rating": 1500}]),
        _doc("epl2026", "maintenance_status", status="success", last_run_at=NOW.isoformat()),
        _doc("epl2026", "team_form_teams", status="fresh", source="espn", observed_at=NOW.isoformat(),
             teams=[{"team_id": "1", "matches": [{"score": "1:0"}]}]),
    ])
    quota_collection = ReadOnlyCollection([
        {"_id": "quota_odds", "data": {"remaining": 0}, "observed_at": NOW.timestamp()},
        {"_id": "provider_budget:odds", "requests": []},
        {"_id": "quota_football", "data": {"remaining": 4}, "observed_at": NOW.timestamp()},
        {"_id": "provider_budget:football", "requests": []},
    ])
    monkeypatch.setattr(quota_store, "_get_collection", lambda: quota_collection)

    _endpoint(init_router({"epl2026": cache}, now_fn=lambda: NOW))(competition="epl2026")

    assert cache.find_one_calls == 0
    assert cache.find_calls == 2  # One metadata batch and one ID-bounded lineup read.
    metadata_reads = [
        (query, projection) for query, projection in cache.find_queries
        if "epl2026:matches_cache" in query.get("_id", {}).get("$in", [])
    ]
    assert len(metadata_reads) == 1
    query, projection = metadata_reads[0]
    assert set(query["_id"]["$in"]) >= {
        "epl2026:matches_cache", "epl2026:standings_cache", "epl2026:elo_ratings",
        "epl2026:team_form_sync", "epl2026:team_form_teams", "epl2026:odds_bucket_state",
        "epl2026:maintenance_status", "epl2026:maintenance_lease",
    }
    assert "data.score_matrix" not in projection
    assert "data.odds" not in projection
    assert "data.odds_provenance.source" in projection
    assert "metadata.uefa_coefficients" in projection
    assert projection.get("teams") == 1  # Needed by the UCL table callback.
    assert quota_collection.find_one_calls == 0
    assert quota_collection.find_calls == 1
    quota_query, quota_projection = quota_collection.find_queries[0]
    assert set(quota_query["_id"]["$in"]) == {
        "quota_odds", "provider_budget:odds", "quota_football", "provider_budget:football",
    }
    assert set(quota_projection) == {"data", "observed_at", "requests", "_id"}


def test_data_status_prefers_scoped_document_when_legacy_alias_is_also_present(monkeypatch):
    cache = ReadOnlyCollection([
        {"_id": "matches_cache", "status": "fresh", "source": "fotmob", "observed_at": NOW.isoformat(),
         "data": [{"id": "legacy"}]},
        _doc("wc2026", "matches_cache", status="fresh", source="espn", observed_at=NOW.isoformat(),
             data=[{"id": "scoped"}]),
    ])
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })

    result = _endpoint(init_router({"wc2026": cache}, now_fn=lambda: NOW))(competition="wc2026")

    fixtures = next(row for row in result["datasets"] if row["id"] == "fixtures_results")
    assert fixtures["providers"]["observed"] == ["espn"]
    assert fixtures["coverage"]["available"] == 1
    assert cache.find_one_calls == 0
    assert cache.find_calls == 2


def test_quota_status_keeps_provider_snapshot_and_application_ledger_separate(monkeypatch):
    collection = ReadOnlyCollection([
        {"_id": "quota_odds", "data": {"remaining": 0, "used": 9}, "observed_at": NOW.timestamp()},
        {"_id": "provider_budget:odds", "requests": [
            [NOW.timestamp() - 1, 4], [NOW.timestamp() + 1, 3], [NOW.timestamp() - 31 * 86400 - 1, 100],
        ]},
        {"_id": "quota_football", "data": {"remaining": "Unknown", "used": "Unknown"}},
    ])
    monkeypatch.setattr(quota_store, "_get_collection", lambda: collection)

    snapshot = quota_store.read_status_snapshot()
    odds = quota_store.read_status("odds", snapshot=snapshot, now=NOW.timestamp())
    football = quota_store.read_status("football", snapshot=snapshot, now=NOW.timestamp())

    assert odds["reported"] == {
        "remaining": 0, "used": 9, "limit": None,
        "observed_at": NOW.isoformat(), "status": "fresh",
    }
    assert odds["app_budget"] == {
        "used": 7, "remaining": 393, "limit": 400, "unit": "credits",
        "window_seconds": 31 * 86400, "headroom": 100, "status": "available",
    }
    assert football["reported"]["remaining"] is None
    assert football["reported"]["status"] == "unknown"
    assert football["app_budget"]["headroom"] == 20
    assert football["app_budget"]["limit"] == 80
    assert collection.find_one_calls == 0
    assert collection.find_calls == 1


def test_future_provider_quota_observation_is_not_reported_as_fresh(monkeypatch):
    snapshot = {
        "mongo_available": True,
        "providers": {"odds": {
            "data": {"remaining": 0, "used": 9},
            "observed_at": NOW.timestamp() + 60,
            "requests": [],
        }},
    }
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: snapshot)
    result = quota_store.read_status("odds", now=NOW.timestamp())
    assert result["reported"]["status"] == "unknown"
    assert result["reported"]["remaining"] is None
    assert result["reported"]["used"] is None
    assert result["reported"]["limit"] is None


def test_invalid_provider_quota_observation_hides_numeric_counters(monkeypatch):
    result = quota_store.read_status("football", snapshot={
        "mongo_available": True,
        "providers": {"football": {
            "data": {"remaining": 4, "used": 8, "limit": 100},
            "observed_at": "not-a-timestamp",
            "requests": [],
        }},
    }, now=NOW.timestamp())
    assert result["reported"] == {
        "remaining": None, "used": None, "limit": None,
        "observed_at": None, "status": "unknown",
    }


def test_undated_local_quota_file_keeps_legacy_reader_but_status_hides_counters(monkeypatch, tmp_path):
    payload = {"remaining": "5", "used": "2", "limit": "10"}
    monkeypatch.setattr(quota_store, "_get_collection", lambda: None)
    monkeypatch.setattr(quota_store, "_DATA_DIR", str(tmp_path))
    (tmp_path / "api_quota_odds.json").write_text(json.dumps(payload), encoding="utf-8")

    assert quota_store.read_quota("odds") == payload
    result = quota_store.read_status("odds", now=NOW.timestamp())
    assert result["reported"] == {
        "remaining": None, "used": None, "limit": None,
        "observed_at": None, "status": "unknown",
    }


def test_quota_snapshot_read_failure_keeps_local_fallback_and_unknown_budget(monkeypatch, tmp_path):
    class BrokenCollection:
        def __init__(self):
            self.find_calls = 0
            self.find_one_calls = 0

        def find(self, query, projection=None):
            self.find_calls += 1
            raise RuntimeError("mongodb://user:secret@example.invalid")

        def find_one(self, query, projection=None):
            self.find_one_calls += 1
            raise RuntimeError("mongodb://user:secret@example.invalid")

    collection = BrokenCollection()
    payload = {"remaining": "5", "used": "2", "limit": "10"}
    monkeypatch.setattr(quota_store, "_get_collection", lambda: collection)
    monkeypatch.setattr(quota_store, "_DATA_DIR", str(tmp_path))
    (tmp_path / "api_quota_odds.json").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = quota_store.read_status_snapshot()
    result = quota_store.read_status("odds", snapshot=snapshot, now=NOW.timestamp())

    assert snapshot["mongo_available"] is False
    assert snapshot["providers"]["odds"]["data"] == payload
    assert result["reported"]["status"] == "unknown"
    assert result["reported"]["remaining"] is None
    assert result["app_budget"]["status"] == "unknown"
    assert result["app_budget"]["used"] is None
    assert collection.find_calls == 1
    assert collection.find_one_calls == 0


def test_dated_stale_provider_quota_keeps_reported_counters(monkeypatch):
    result = quota_store.read_status("odds", snapshot={
        "mongo_available": True,
        "providers": {"odds": {
            "data": {"remaining": 0, "used": 400, "limit": 500},
            "observed_at": NOW.timestamp() - 2 * 86400,
            "requests": [],
        }},
    }, now=NOW.timestamp())
    assert result["reported"] == {
        "remaining": 0, "used": 400, "limit": 500,
        "observed_at": "2026-10-23T12:00:00+00:00", "status": "stale",
    }


def _ucl_teams_and_fixtures():
    teams = [f"Team {index:02d}" for index in range(36)]
    fixtures = []
    for round_no in range(4):
        for team_index, home in enumerate(teams):
            away = teams[(team_index + round_no + 1) % len(teams)]
            fixtures.append({
                "id": f"m-{round_no}-{team_index}", "home_team": home, "away_team": away,
                "status": "completed", "score_90": "0:0", "round": "League Phase",
            })
    return teams, fixtures


def _api_status_and_standings(monkeypatch, competition, cache):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=50")
    monkeypatch.setenv("ODDS_API_KEY", "test-only-key")
    api = importlib.import_module("src.api")
    monkeypatch.setitem(api.cache_collections, competition, cache)
    monkeypatch.setattr(quota_store, "read_status_snapshot", lambda: {
        "mongo_available": False, "providers": {},
    })
    status_route = next(
        route
        for included in api.app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", [included])
        if getattr(route, "path", None) == "/api/data-status"
    )
    return api.get_standings(competition=competition), status_route.endpoint(competition=competition)


def test_standings_status_matches_api_cache_and_derived_behavior(monkeypatch):
    now = datetime.now(timezone.utc)
    teams, fixtures = _ucl_teams_and_fixtures()
    cached_rows = [{"pos": index + 1, "team": team} for index, team in enumerate(teams)]
    cases = [
        ("wc2026", ProjectionCollection([_doc(
            "wc2026", "matches_cache", status="fresh", source="espn", observed_at=now.isoformat(),
            data=fixtures[:1],
        )]), "unavailable", "provider"),
        ("ucl2026", ProjectionCollection([
            _doc("ucl2026", "matches_cache", status="fresh", source="espn", observed_at=now.isoformat(), data=fixtures),
            _doc("ucl2026", "standings_cache", status="fresh", source="espn", observed_at=now.isoformat(),
                 data=[{"name": "UCL League Phase", "rows": cached_rows}]),
        ]), "fresh", "provider"),
        ("ucl2026", ProjectionCollection([_doc(
            "ucl2026", "matches_cache", status="fresh", source="espn", observed_at=now.isoformat(), data=fixtures,
        )]), "fresh", "derived"),
        ("ucl2026", ProjectionCollection([_doc(
            "ucl2026", "matches_cache", status="fresh", source="espn", observed_at=now.isoformat(),
            data=[{"id": "one", "home_team": "A", "away_team": "B", "completed": True}],
        )]), "unavailable", "derived"),
    ]

    for competition, cache, expected_status, expected_kind in cases:
        api_standings, summary = _api_status_and_standings(monkeypatch, competition, cache)
        standings = next(row for row in summary["datasets"] if row["id"] == "standings")
        assert standings["status"] == expected_status, (competition, expected_kind, api_standings, standings)
        assert standings["source_kind"] == expected_kind
        assert bool(api_standings) is (expected_status == "fresh")
        if expected_status == "fresh":
            assert len(api_standings[0]["rows"]) == standings["coverage"]["available"] == 36


def test_quota_status_unknown_without_mongo_but_preserves_local_budget_limit(monkeypatch):
    monkeypatch.setattr(quota_store, "_get_collection", lambda: None)
    result = quota_store.read_status("football", now=NOW.timestamp())
    assert result["reported"]["status"] == "unknown"
    assert result["app_budget"]["status"] == "unknown"
    assert result["app_budget"]["used"] is None
    assert result["app_budget"]["remaining"] is None
    assert result["app_budget"]["limit"] == 80


def test_legacy_quota_reader_keeps_its_existing_payload(monkeypatch):
    payload = {"remaining": "5", "used": "2"}
    monkeypatch.setattr(quota_store, "_get_collection", lambda: ReadOnlyCollection([
        {"_id": "quota_odds", "data": payload, "observed_at": NOW.timestamp()},
    ]))
    assert quota_store.read_quota("odds") == payload
