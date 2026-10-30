from copy import deepcopy
from datetime import datetime, timezone

from src.competitions import competition_document_id
from src.services.club_views import overview_view_id, prepare_club_views
from src.services.maintenance import (
    _persist_club_predictions,
    _refresh_fixtures,
    _store_fixture_odds,
    run_maintenance,
)
from src.services.model_evaluation import freeze_due_comparisons
from src.services.archive import upsert_archive_entry
from src.services.user_tips import save_historical_tip, save_shared_tip
from test_club_views import ViewCollection, _fixture


class _InsertableCollection(ViewCollection):
    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise RuntimeError("duplicate key")
        self.documents[document["_id"]] = deepcopy(document)

    def delete_one(self, query):
        self.documents.pop(query["_id"], None)


class _SourceWriteTracker(_InsertableCollection):
    def __init__(self, documents=(), *, competition="epl2026"):
        super().__init__(documents)
        self.competition = competition
        self.source_write_fences = []

    def update_one(self, query, update, upsert=False):
        if query.get("_id") == competition_document_id(self.competition, "matches_cache"):
            head = self.documents.get(overview_view_id(self.competition), {})
            self.source_write_fences.append((bool(head.get("active_writers")), head.get("input_revision", 0)))
        return super().update_one(query, update, upsert=upsert)


class _ArchiveWriteTracker(_InsertableCollection):
    def __init__(self, cache, documents=(), *, competition="epl2026"):
        super().__init__(documents)
        self.cache = cache
        self.competition = competition
        self.source_write_fences = []

    def update_one(self, query, update, upsert=False):
        head = self.cache.documents.get(overview_view_id(self.competition), {})
        self.source_write_fences.append((bool(head.get("active_writers")), head.get("input_revision", 0)))
        return super().update_one(query, update, upsert=upsert)

    def replace_one(self, query, replacement, upsert=False):
        head = self.cache.documents.get(overview_view_id(self.competition), {})
        self.source_write_fences.append((bool(head.get("active_writers")), head.get("input_revision", 0)))
        return super().replace_one(query, replacement, upsert=upsert)


def test_fixture_refresh_fetches_before_fencing_only_the_source_write():
    cache = _SourceWriteTracker([{"_id": "epl2026:matches_cache", "data": []}])
    observed_during_fetch = []

    def fetch(**_kwargs):
        head = cache.documents.get(overview_view_id("epl2026"), {})
        observed_during_fetch.append((bool(head.get("active_writers")), head.get("input_revision", 0)))
        return [_fixture()]

    result = _refresh_fixtures(cache, "epl2026", fetch, datetime(2026, 10, 28, tzinfo=timezone.utc))

    assert result["status"] == "fresh"
    assert observed_during_fetch == [(False, 0)]
    assert cache.source_write_fences == [(True, 1)]
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_world_cup_fixture_refresh_does_not_create_a_club_view_fence():
    cache = _SourceWriteTracker([{"_id": "wc2026:matches_cache", "data": []}], competition="wc2026")

    _refresh_fixtures(cache, "wc2026", lambda **_kwargs: [_fixture()], datetime(2026, 10, 28, tzinfo=timezone.utc))

    assert cache.documents.get(overview_view_id("wc2026")) is None
    assert overview_view_id("wc2026") not in cache.documents


def test_odds_cache_mutation_is_fenced_after_any_provider_work():
    fixture = _fixture()
    cache = _SourceWriteTracker([{"_id": "epl2026:matches_cache", "data": [fixture]}])

    _store_fixture_odds(cache, "epl2026", "game-1", {"home": 2.0, "draw": 3.4, "away": 4.0},
                        {"id": "game-1", "bookmakers": []}, datetime(2026, 10, 28, tzinfo=timezone.utc))

    saved = cache.documents["epl2026:matches_cache"]["data"][0]
    assert saved["odds"] == {"home": 2.0, "draw": 3.4, "away": 4.0}
    assert cache.source_write_fences == [(True, 1)]
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_results_only_path_uses_no_paid_provider_and_fences_result_and_fixture_writes():
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    cache = _SourceWriteTracker([{"_id": "epl2026:matches_cache", "data": []}])
    archive = _ArchiveWriteTracker(cache, [{
        "_id": "game-1", "metadata": {},
        "prediction": {"user_tip": "1:0", "top_tip": "1:0"},
        "post_match_result": {"status": "pending"},
    }])

    class NoPaidCalls:
        def get_competition_odds(self, *_args, **_kwargs):
            raise AssertionError("results-only maintenance must not request odds")

    fixture = {
        "id": "game-1", "home_team": "Arsenal", "away_team": "Chelsea",
        "commence_time": "2026-10-27T19:00:00Z", "round": "League Phase",
        "completed": True, "actual_score": "1:0",
    }
    result = run_maintenance(
        cache, NoPaidCalls(), archive_collections=archive, competition="epl2026", now=now,
        fixture_fetcher=lambda **_kwargs: [fixture], results_only=True,
    )

    assert result["provider_calls"] == 0
    assert result["archived_results"] == 1
    assert cache.source_write_fences == [(True, 1)]
    assert archive.source_write_fences == [(True, 3)]
    assert archive.documents["game-1"]["post_match_result"]["actual_score"] == "1:0"
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 4
    assert cache.documents[overview_view_id("epl2026")]["active_writers"] == {}


def test_saved_tip_survives_cold_view_patch_failure_and_cache_only_prepare_repairs_it():
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    fixture = _fixture()
    cache = _SourceWriteTracker([{"_id": "epl2026:matches_cache", "data": [fixture]}])
    archive = _ArchiveWriteTracker(cache)

    result = save_shared_tip(archive, cache, "game-1", "2:1", "epl2026", now=now)

    assert result["ok"] is True and result["points_earned"] is None
    assert result["match_id"] == "game-1"
    assert result["canonical_match_id"] == "game-1"
    assert result["archive_entry"]["prediction"]["user_tip"] == "2:1"
    assert archive.documents["game-1"]["prediction"]["user_tip"] == "2:1"
    assert archive.source_write_fences == [(True, 1)]
    prepared = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026", now=now)
    assert prepared["status"] == "success"
    assert cache.documents[overview_view_id("epl2026")]["overview"][0]["user_tip"] == "2:1"


def test_historical_tip_archive_write_is_fenced_when_cache_is_available():
    cache = _SourceWriteTracker()
    archive = _ArchiveWriteTracker(cache, [{
        "_id": "done-1",
        "metadata": {"is_ko_phase": False},
        "prediction": {"user_tip": "1:0"},
        "post_match_result": {"status": "completed", "actual_score": "2:0"},
    }])

    result = save_historical_tip(
        archive, "done-1", "2:0", "epl2026", cache_store=cache,
        now=datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
    )

    assert result["points_earned"] == 10
    assert result["match_id"] == "done-1"
    assert result["canonical_match_id"] == "done-1"
    assert archive.source_write_fences == [(True, 1)]
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_saved_model_prediction_is_fenced_after_prediction_work(monkeypatch):
    from src.routes import matches

    fixture = _fixture()
    cache = _SourceWriteTracker([{"_id": "epl2026:matches_cache", "data": [fixture]}])

    def enrich(rows, *_args):
        rows[0]["model_tip"] = "2:0"
        rows[0]["top_tip"] = "2:0"

    monkeypatch.setattr(matches, "_enrich_edge", enrich)
    updated = _persist_club_predictions(cache, "epl2026", object(), {"status": "fresh"})

    assert updated == 1
    assert cache.source_write_fences == [(True, 1)]
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_frozen_prediction_archive_writes_are_fenced():
    from test_model_evaluation import FreezeService, _auto_capture_fixtures

    cache = _SourceWriteTracker(_auto_capture_fixtures().documents.values(), competition="ucl2026")
    archive = _ArchiveWriteTracker(cache, [{
        "_id": "game-auto",
        "metadata": {"commence_time": "2026-10-01T12:00:00+00:00"},
        "pre_match_snapshot": {
            "timestamp_recorded": "2026-10-01T10:00:00+00:00",
            "elo_state": {"home_rating": 1600, "away_rating": 1500, "source": "clubelo",
                           "observed_at": "2026-10-01T10:00:00+00:00"},
        },
        "prediction": {"user_tip": "1:1", "top_tip": "3:2"},
        "post_match_result": {"status": "pending", "actual_score": None},
    }], competition="ucl2026")

    frozen = freeze_due_comparisons(
        FreezeService(), cache, archive, "ucl2026", datetime(2026, 10, 1, 11, 50, tzinfo=timezone.utc),
    )

    assert frozen == 1
    saved = archive.documents["game-auto"]["prediction"]
    assert saved["user_tip"] == "1:1"
    assert saved["top_tip"] == "3:2"
    assert archive.source_write_fences
    assert all(active for active, _revision in archive.source_write_fences)
    head = cache.documents[overview_view_id("ucl2026")]
    assert head["input_revision"] == 2 * len(archive.source_write_fences)
    assert head["active_writers"] == {}


def test_evaluation_forecast_archive_write_is_fenced_after_model_work(monkeypatch):
    from src.services import forecast_evaluation

    kickoff = "2026-11-01T19:00:00+00:00"
    observed = "2026-11-01T18:45:00+00:00"
    cache = _SourceWriteTracker([{
        "_id": "epl2026:odds_snapshot:game-1:t15m", "competition": "epl2026",
        "event_id": "game-1", "observed_at": observed, "status": "fresh",
        "odds": {"home": 2.0, "draw": 3.4, "away": 4.0},
    }])
    archive = _ArchiveWriteTracker(cache, [{
        "_id": "game-1", "metadata": {"commence_time": kickoff},
        "pre_match_snapshot": {"timestamp_recorded": "2026-11-01T18:00:00+00:00"},
        "prediction": {}, "post_match_result": {"status": "pending"},
    }])
    monkeypatch.setattr(forecast_evaluation, "build_evaluation_forecast", lambda *_args, **_kwargs: {"captured_at": observed})

    captured = forecast_evaluation.capture_archive_forecasts(
        cache, archive, object(), competition="epl2026",
        now=datetime(2026, 11, 1, 18, 50, tzinfo=timezone.utc),
    )

    assert captured == 1
    assert archive.documents["game-1"]["prediction"]["evaluation_forecast"] == {"captured_at": observed}
    assert archive.source_write_fences == [(True, 1)]
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_idle_maintenance_is_cache_only_and_makes_no_paid_request():
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    cache = _SourceWriteTracker([{
        "_id": "epl2026:matches_cache", "status": "fresh", "observed_at": now.isoformat(), "data": [],
    }])

    class NoPaidCalls:
        def get_competition_odds(self, *_args, **_kwargs):
            raise AssertionError("idle maintenance must not request odds")

    result = run_maintenance(cache, NoPaidCalls(), competition="epl2026", now=now)

    assert result["status"] == "idle"
    assert result["provider_calls"] == 0
    assert cache.source_write_fences == []


def test_provider_budget_error_return_still_fences_model_and_archive_mutations(monkeypatch):
    from src.quota_store import ProviderBudgetExceeded
    from src.routes import matches

    now = datetime(2026, 11, 1, 18, 50, tzinfo=timezone.utc)
    fixture = _fixture()
    fixture["commence_time"] = "2026-11-01T19:00:00+00:00"
    fixture["observed_at"] = "2026-11-01T18:40:00+00:00"
    cache = _SourceWriteTracker([{
        "_id": "epl2026:matches_cache", "status": "fresh", "observed_at": now.isoformat(), "data": [fixture],
    }])
    archive = _ArchiveWriteTracker(cache)

    class BudgetBlockedProvider:
        def get_competition_odds(self, *_args, **_kwargs):
            raise ProviderBudgetExceeded("blocked before provider request")

    def enrich(rows, *_args):
        rows[0]["model_tip"] = "2:0"
        rows[0]["top_tip"] = "2:0"

    monkeypatch.setattr(matches, "_enrich_edge", enrich)
    result = run_maintenance(
        cache, BudgetBlockedProvider(), archive_collections=archive, competition="epl2026", now=now,
        math_engine=object(), clubelo_ingestor=lambda *_args, **_kwargs: {"status": "fresh", "rows": []},
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "provider_budget_blocked"
    assert result["provider_calls"] == 0
    assert cache.source_write_fences == [(True, 1)]
    assert archive.source_write_fences
    assert all(active for active, _revision in archive.source_write_fences)
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == (
        2 * (1 + len(archive.source_write_fences))
    )


def test_archive_upsert_fences_club_view_inputs_when_cache_is_available():
    cache = _SourceWriteTracker()
    archive = _ArchiveWriteTracker(cache)

    upsert_archive_entry(
        archive, "done-1", {"prediction": {"top_tip": "2:0"}},
        cache_collection=cache, competition="epl2026",
    )

    assert archive.documents["done-1"]["prediction"]["top_tip"] == "2:0"
    assert archive.source_write_fences == [(True, 1)]
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_pool_context_archive_reset_invalidates_club_views_only():
    from src.routes.pool import init_router

    for competition in ("ucl2026", "wc2026"):
        cache = ViewCollection()
        archive = _ArchiveWriteTracker(cache, [{
            "_id": "game-1", "prediction": {"pool_tip": "2:1", "pool_status": "fresh"},
        }], competition=competition)
        router = init_router({competition: cache}, {competition: archive})
        endpoint = next(route.endpoint for route in router.routes if "PUT" in route.methods)
        endpoint("game-1", {"tip_counts": {"1:0": 1}}, competition)
        assert archive.documents["game-1"]["prediction"]["pool_tip"] is None
        assert archive.source_write_fences[0][0] is (competition != "wc2026")
        if competition == "wc2026":
            assert overview_view_id(competition) not in cache.documents
        else:
            head = cache.documents[overview_view_id(competition)]
            assert head["input_revision"] == 2
            assert head["active_writers"] == {}
