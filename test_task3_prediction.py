from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.math_engine import MathEngine
from src.services.prediction import (
    MatchContext,
    PredictionService,
    advancement_probabilities,
    build_aet_distribution,
    build_match_context,
    extra_time_eligible_for_score,
    pool_lambda,
    pool_tip_from_field,
    freeze_prediction,
    user_tip_is_open,
    rebuild_prediction,
)
from src.routes.predict import init_router as predict_router
from src.routes.pool import init_router as pool_router
from src.routes.matches import _enrich_edge
from src.routes.matches import init_router as matches_router
from src.services.ucl_providers import compose_match_sources


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}
        self.replacements = 0

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def find(self, query=None):
        values = list(self.documents.values())
        if not query:
            return values
        return [doc for doc in values if all(doc.get(key) == value for key, value in query.items())]

    def replace_one(self, query, document, upsert=False):
        self.documents[query["_id"]] = dict(document)
        self.replacements += 1

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        existing = self.documents.get(key, {"_id": key})
        for field, expected in query.items():
            if field == "_id":
                continue
            current = existing
            for part in field.split("."):
                if not isinstance(current, dict) or part not in current:
                    current = None
                    break
                current = current[part]
            if isinstance(expected, dict) and "$exists" in expected:
                exists = current is not None
                if exists != bool(expected["$exists"]):
                    return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
                continue
            if current != expected:
                return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
        for field, value in update.get("$set", {}).items():
            target = existing
            parts = field.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        if key not in self.documents:
            existing.update(update.get("$setOnInsert", {}))
        self.documents[key] = existing
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()


def _matrix(cells, size=4):
    values = np.zeros((size, size), dtype=float)
    for (home, away), probability in cells.items():
        values[home, away] = probability
    return pd.DataFrame(values, index=[str(i) for i in range(size)], columns=[str(i) for i in range(size)])


def _engine():
    return MathEngine("data/elo_ratings.csv")


class NoopLimiter:
    def limit(self, *_args, **_kwargs):
        return lambda function: function


class RaceArchive(MemoryCollection):
    """Simulate a concurrent writer winning the freeze compare-and-set."""

    def __init__(self, documents=()):
        super().__init__(documents)
        self.raced = False

    def update_one(self, query, update, upsert=False):
        if not self.raced and "prediction.frozen_at" in query:
            self.raced = True
            winner = dict(self.documents[query["_id"]])
            winner["prediction"] = dict(winner.get("prediction") or {})
            winner["prediction"].update({"user_tip": "1:1", "frozen_at": "winner"})
            self.documents[query["_id"]] = winner
            return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
        return super().update_one(query, update, upsert=upsert)

    def replace_one(self, *_args, **_kwargs):
        raise AssertionError("freeze must use a conditional update, not replace_one")


def _bookmakers(home="Bayern Munich", away="Arsenal"):
    return [{"key": "book", "markets": [{"key": "h2h", "outcomes": [
        {"name": home, "price": 2.0}, {"name": "Draw", "price": 3.2}, {"name": away, "price": 4.0},
    ]}]}]


def test_context_derives_second_leg_and_final_extra_time_rules():
    second = build_match_context({
        "stage": "round_of_16",
        "tie_id": "tie-1",
        "leg": "second",
        "first_leg_score": "1:0",
    }, competition="ucl2026")
    assert isinstance(second, MatchContext)
    assert second.stage == "round_of_16"
    assert second.tie_id == "tie-1"
    assert second.leg == "second"
    assert extra_time_eligible_for_score(second, 0, 1)
    assert not extra_time_eligible_for_score(second, 1, 1)

    final = build_match_context({"stage": "final", "leg": "single"}, competition="ucl2026")
    assert extra_time_eligible_for_score(final, 1, 1)
    assert not extra_time_eligible_for_score(final, 2, 1)

    first = build_match_context({"stage": "round_of_16", "leg": "first", "first_leg_score": "0:0"}, competition="ucl2026")
    assert not extra_time_eligible_for_score(first, 0, 0)


def test_aet_convolves_only_aggregate_tie_cells_and_stays_normalized():
    base = _matrix({(2, 2): 0.4, (0, 1): 0.6})
    context = build_match_context({"stage": "round_of_16", "leg": "second", "first_leg_score": "0:0"}, competition="ucl2026")
    result = build_aet_distribution(base, 1.2, 0.9, context)

    assert result.loc["0", "1"] == pytest.approx(0.6)
    assert result.loc["2", "2"] < 0.4
    assert float(result.to_numpy().sum()) == pytest.approx(1.0)


def test_final_aet_only_changes_90_minute_draw_cells():
    base = _matrix({(2, 2): 0.5, (0, 1): 0.5})
    context = build_match_context({"stage": "final", "leg": "single"}, competition="ucl2026")
    result = build_aet_distribution(base, 1.0, 1.0, context)
    assert result.loc["0", "1"] == pytest.approx(0.5)
    assert result.loc["2", "2"] < 0.5


def test_penalty_advancement_is_separate_from_srf_score_distribution():
    base = _matrix({(1, 1): 1.0})
    context = build_match_context({"stage": "final", "leg": "single"}, competition="ucl2026")
    result = build_aet_distribution(base, 1.0, 1.0, context)
    assert advancement_probabilities(context, 1, 1) == {"home": 0.5, "away": 0.5}
    assert result.loc["1", "1"] < 1.0
    assert all(value >= 0 for value in result.to_numpy().ravel())


def test_pool_lambda_uses_leader_gap_and_remaining_srf_points():
    assert pool_lambda(user_points=80, leader_points=100, remaining_srf_max_points=50) == pytest.approx(0.24)
    assert pool_lambda(user_points=100, leader_points=80, remaining_srf_max_points=50) == 0.0
    assert pool_lambda(user_points=0, leader_points=100, remaining_srf_max_points=1) == 0.6


def test_pool_tip_uses_field_counts_and_returns_expected_tip():
    matrix = _matrix({(0, 0): 0.5, (2, 0): 0.5})
    result = pool_tip_from_field(
        matrix,
        field_counts={"0:0": 3, "2:0": 1},
        user_points=0,
        leader_points=20,
        remaining_srf_max_points=100,
    )
    assert result["tip"] in {"0:0", "2:0"}
    assert result["lambda"] == pytest.approx(0.12)
    assert result["field_count"] == 4


def test_invalid_field_counts_only_disable_pool_tip():
    service = PredictionService(_engine())
    result = service.predict(
        odds={"home": 2.0, "draw": 3.2, "away": 4.0},
        elo=None,
        competition="ucl2026",
        context={"stage": "league", "leg": "single"},
        field_counts={"not-a-score": 3},
        user_points=0,
        leader_points=10,
        remaining_srf_max_points=100,
    )
    assert result["source_mode"] == "odds-only"
    assert result["model_tip"]
    assert result["top_tip"] == result["model_tip"]
    assert result["pool_tip"] is None
    assert result["pool_status"] == "unavailable"
    assert result["model_version"]
    assert result["input_provenance"]


def test_freeze_uses_latest_eligible_t15_snapshot_and_is_idempotent():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {"_id": "ucl2026:matches_cache", "data": [{"id": "m1", "commence_time": kickoff.isoformat()}]},
        {
            "_id": "ucl2026:odds_snapshot:m1:t24h:1",
            "event_id": "m1", "bucket": "t24h", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(),
            "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
        },
        {
            "_id": "ucl2026:odds_snapshot:m1:t15m:2",
            "event_id": "m1", "bucket": "t15m", "status": "fresh",
            "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
            "odds": {"home": 1.8, "draw": 3.4, "away": 4.6},
        },
    ])
    archive = MemoryCollection([{"_id": "m1", "metadata": {"commence_time": kickoff.isoformat()}, "prediction": {}}])
    service = PredictionService(_engine())
    frozen = freeze_prediction(
        cache,
        archive,
        service,
        "m1",
        competition="ucl2026",
        now=kickoff - timedelta(minutes=10),
    )
    assert frozen["prediction"]["frozen_at"]
    assert frozen["prediction"]["model_tip"] == frozen["prediction"]["top_tip"]
    assert frozen["prediction"]["source_inputs"]["odds"]["home"] == 1.8
    assert sum(frozen["prediction"]["probabilities"].values()) == pytest.approx(1.0)
    assert sum(frozen["prediction"]["base_probabilities"].values()) == pytest.approx(1.0)
    writes = archive.replacements
    again = freeze_prediction(
        cache,
        archive,
        service,
        "m1",
        competition="ucl2026",
        now=kickoff - timedelta(minutes=9),
    )
    assert again == frozen
    assert archive.replacements == writes


def test_freeze_records_forecast_without_replacing_the_visible_tip():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": "ucl2026:odds_snapshot:m1:t15m:1", "event_id": "m1",
        "bucket": "t15m", "status": "fresh",
        "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
        "odds": {"home": 1.8, "draw": 3.4, "away": 4.6},
    }])
    original = {
        "top_tip": "3:2", "model_tip": "3:2", "user_tip": "1:1",
        "status": "existing", "probabilities": {"home": 0.4, "draw": 0.3, "away": 0.3},
    }
    archive = MemoryCollection([{
        "_id": "m1", "metadata": {"commence_time": kickoff.isoformat()},
        "prediction": original,
    }])

    frozen = freeze_prediction(
        cache, archive, PredictionService(_engine()), "m1",
        competition="ucl2026", now=kickoff - timedelta(minutes=10),
        visible_tip="2:1",
    )["prediction"]

    for key, value in original.items():
        assert frozen[key] == value
    capture = frozen["evaluation_forecast"]
    assert capture["visible_tip"] == "2:1"
    assert capture["visible_tip_source"] == "matches_cache"
    assert capture["model_tip"]
    assert capture["source_inputs"]["odds"]["home"] == 1.8
    assert capture["provenance"]["snapshot_bucket"] == "t15m"
    assert capture["frozen_at"] == frozen["frozen_at"]


def test_freeze_refuses_to_record_after_tip_deadline():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    archive = MemoryCollection([{"_id": "m1", "metadata": {"commence_time": kickoff.isoformat()}, "prediction": {}}])

    with pytest.raises(ValueError, match="tip deadline"):
        freeze_prediction(
            MemoryCollection(), archive, PredictionService(_engine()), "m1",
            competition="ucl2026", now=kickoff - timedelta(minutes=4),
        )
    assert not archive.find_one({"_id": "m1"})["prediction"].get("frozen_at")


def test_freeze_uses_stored_archive_context_and_persists_it():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": "ucl2026:odds_snapshot:m1:t15m:1", "event_id": "m1", "competition": "ucl2026",
        "bucket": "t15m", "status": "fresh", "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
        "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
    }])
    archive = MemoryCollection([{"_id": "m1", "metadata": {
        "commence_time": kickoff.isoformat(), "stage": "final", "leg": "single", "score_90": "1:1",
    }, "prediction": {}}])
    frozen = freeze_prediction(cache, archive, PredictionService(_engine()), "m1", competition="ucl2026",
                               now=kickoff - timedelta(minutes=10))
    assert frozen["prediction"]["score_inputs"]["score_90"] == "1:1"
    assert frozen["prediction"]["context"]["stage"] == "final"


def test_user_tip_closes_at_t5_but_undated_legacy_entry_stays_open():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    assert user_tip_is_open(kickoff.isoformat(), kickoff - timedelta(minutes=6))
    assert not user_tip_is_open(kickoff.isoformat(), kickoff - timedelta(minutes=5))
    assert user_tip_is_open(None, kickoff)
    assert user_tip_is_open("not-a-time", kickoff)


def test_prediction_maps_pool_tip_without_overwriting_source_status():
    service = PredictionService(_engine())
    result = service.predict(
        odds={"home": 2.0, "draw": 3.2, "away": 4.0},
        elo=None,
        competition="ucl2026",
        field_counts={"0:0": 3, "1:0": 1},
        user_points=10,
        leader_points=20,
        remaining_srf_max_points=50,
    )
    assert result["status"] == "fresh"
    assert result["pool_status"] == "available"
    assert result["pool_tip"] is not None
    assert result["lambda"] == pytest.approx(0.12)


def test_freeze_compare_and_set_preserves_concurrent_user_tip():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {"_id": "ucl2026:odds_snapshot:m1:t15m:1", "event_id": "m1", "competition": "ucl2026",
         "bucket": "t15m", "status": "fresh", "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
         "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}},
    ])
    archive = RaceArchive([{"_id": "m1", "metadata": {"commence_time": kickoff.isoformat()}, "prediction": {}}])
    frozen = freeze_prediction(cache, archive, PredictionService(_engine()), "m1", competition="ucl2026",
                               now=kickoff - timedelta(minutes=10))
    assert frozen["prediction"]["frozen_at"] == "winner"
    assert frozen["prediction"]["user_tip"] == "1:1"
    assert archive.documents["m1"]["prediction"]["user_tip"] == "1:1"


def test_predict_accepts_top_level_context_and_pool_context():
    cache = MemoryCollection([{
        "_id": "ucl2026:pool_context:m1", "tip_counts": {"0:0": 2, "1:0": 1},
        "user_points": 0, "leader_points": 10, "remaining_srf_max_points": 100,
    }])
    router = predict_router(_engine(), object(), {"ucl2026": cache}, NoopLimiter())
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/predict")
    result = endpoint(None, {
        "competition": "ucl2026",
        "stage": "final",
        "leg": "single",
        "tie_id": "final-1",
        "match": {"id": "m1", "home_team": "Bayern Munich", "away_team": "Arsenal", "bookmakers": _bookmakers()},
    }, competition="ucl2026")
    assert result["context"]["stage"] == "final"
    assert result["context"]["tie_id"] == "final-1"
    assert result["pool_status"] == "available"
    assert result["pool_tip"] is not None


def test_pool_context_put_clears_stale_archived_pool_tip():
    cache = MemoryCollection()
    archive = MemoryCollection([{"_id": "m1", "prediction": {"pool_tip": "2:0", "pool_status": "available"}}])
    router = pool_router({"ucl2026": cache}, {"ucl2026": archive})
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/pool-context/{match_id}" and route.methods == {"PUT"})
    endpoint("m1", {"tip_counts": {"1:1": 2}, "user_points": 4, "leader_points": 8, "remaining_srf_max_points": 30}, competition="ucl2026")
    assert archive.documents["m1"]["prediction"]["pool_tip"] is None
    assert archive.documents["m1"]["prediction"]["pool_status"] == "unavailable"


@pytest.mark.parametrize("match_id,tip_counts", [
    ("m" * 129, {"1:1": 2}),
    ("m1", {"21:0": 2}),
    ("m1", {"1:1": -1}),
])
def test_pool_context_rejects_unbounded_public_write_fields(match_id, tip_counts):
    cache = MemoryCollection()
    router = pool_router({"ucl2026": cache}, {"ucl2026": MemoryCollection()})
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/pool-context/{match_id}" and route.methods == {"PUT"})

    with pytest.raises(Exception) as error:
        endpoint(match_id, {
            "tip_counts": tip_counts,
            "user_points": 4,
            "leader_points": 8,
            "remaining_srf_max_points": 30,
        }, competition="ucl2026")

    assert getattr(error.value, "status_code", None) == 400
    assert cache.documents == {}


def test_freeze_rejects_oversized_match_id_before_archive_lookup():
    router = predict_router(
        _engine(), object(), {"ucl2026": MemoryCollection()}, NoopLimiter(), {"ucl2026": MemoryCollection()},
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/predict/freeze")

    with pytest.raises(Exception) as error:
        endpoint({"match_id": "m" * 129}, competition="ucl2026")

    assert getattr(error.value, "status_code", None) == 400


def test_user_tip_missing_kickoff_is_only_permissive_for_legacy_wc():
    now = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    assert user_tip_is_open(None, now, competition="wc2026")
    assert not user_tip_is_open(None, now, competition="ucl2026")
    assert not user_tip_is_open("not-a-time", now, competition="ucl2026")


def test_first_leg_never_gets_final_draw_extra_time():
    context = build_match_context({"stage": "final", "leg": "first", "first_leg_score": "0:0"}, competition="ucl2026")
    assert not extra_time_eligible_for_score(context, 0, 0)


def test_reconstruction_preserves_full_ucl_context_and_model_alias():
    engine = _engine()
    engine.elo_df = pd.DataFrame([
        {"team_name": "Bayern Munich", "elo_rating": 1900.0},
        {"team_name": "Arsenal", "elo_rating": 1800.0},
    ])
    result = PredictionService(engine).reconstruct(
        "Bayern Munich", "Arsenal", competition="ucl2026",
        context={"stage": "round_of_16", "tie_id": "t1", "leg": "second", "first_leg_score": "1:0"},
    )
    assert result["context"]["stage"] == "round_of_16"
    assert result["context"]["leg"] == "second"
    assert result["model_tip"] == result["top_tip"]


def test_honest_rebuild_uses_shared_service_and_persists_model_alias():
    service = PredictionService(_engine())
    entry = {
        "metadata": {"stage": "final", "leg": "single"},
        "pre_match_snapshot": {
            "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
            "elo_state": {"home_rating": 1800, "away_rating": 1700},
        },
        "prediction": {"top_tip": "9:9"},
        "post_match_result": {"status": "completed", "actual_score": "1:0"},
    }
    rebuilt = rebuild_prediction(service, entry, competition="wc2026")
    assert rebuilt["prediction"]["model_tip"] == rebuilt["prediction"]["top_tip"]
    assert rebuilt["prediction"]["source_mode"] == "odds+elo"


def test_cached_ucl_edge_uses_pool_context_when_ratings_are_explicit():
    engine = _engine()
    engine.elo_df = pd.DataFrame([
        {"team_name": "Bayern Munich", "elo_rating": 1900.0},
        {"team_name": "Arsenal", "elo_rating": 1800.0},
    ])
    cache = MemoryCollection([{"_id": "ucl2026:pool_context:m1", "tip_counts": {"0:0": 2, "1:0": 1},
                              "user_points": 0, "leader_points": 10, "remaining_srf_max_points": 100}])
    match = {"id": "m1", "home_team": "Bayern Munich", "away_team": "Arsenal",
             "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}, "raw_match": {"round": "League Phase"}}
    enriched = _enrich_edge([match], engine, object(), competition="ucl2026", pool_context_collection=cache)[0]
    assert enriched["pool_status"] == "available"
    assert enriched["pool_tip"] is not None


def test_failed_source_status_is_preserved_in_prediction_provenance():
    service = PredictionService(_engine())
    result = service.predict(
        odds={"status": "stale", "odds": {"home": 2.0, "draw": 3.2, "away": 4.0}},
        elo=None,
        competition="ucl2026",
    )
    assert result["status"] == "stale"
    assert result["input_provenance"]["odds"]["status"] == "stale"


def test_ucl_cached_edge_clears_legacy_edge_without_explicit_ratings():
    engine = _engine()
    engine.elo_df = pd.DataFrame([{"team_name": "Different Club", "elo_rating": 1800}])

    match = {"id": "m1", "home_team": "Bayern Munich", "away_team": "Arsenal",
             "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}, "edge_home": 0.9,
             "raw_match": {"round": "League Phase"}}
    enriched = _enrich_edge([match], engine, object(), competition="ucl2026")[0]
    assert enriched.get("edge_home") is None
    assert enriched.get("elo_home_share") is None


def test_freeze_preserves_snapshot_source_status_and_provenance():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    observed_at = (kickoff - timedelta(minutes=15)).isoformat()
    snapshot_provenance = {
        "provider_request_id": "request-123",
        "url": "https://odds.example/t15",
    }
    cache = MemoryCollection([{
        "_id": "ucl2026:odds_snapshot:m1:t15m:1",
        "event_id": "m1",
        "competition": "ucl2026",
        "bucket": "t15m",
        "status": "stale",
        "source": "odds_cache",
        "observed_at": observed_at,
        "provenance": snapshot_provenance,
        "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
    }])
    archive = MemoryCollection([{
        "_id": "m1",
        "metadata": {"commence_time": kickoff.isoformat()},
        "prediction": {},
    }])

    frozen = freeze_prediction(
        cache,
        archive,
        PredictionService(_engine()),
        "m1",
        competition="ucl2026",
        now=kickoff - timedelta(minutes=10),
    )
    prediction = frozen["prediction"]

    assert prediction["status"] == "stale"
    assert prediction["source"] == "odds_cache"
    assert prediction["observed_at"] == observed_at
    assert prediction["provenance"]["odds"]["provider_request_id"] == "request-123"
    assert prediction["provenance"]["odds"]["source"] == "odds_cache"
    assert prediction["provenance"]["odds"]["status"] == "stale"
    assert prediction["input_provenance"]["odds"]["url"] == snapshot_provenance["url"]


def test_rebuild_prediction_persists_prediction_context():
    entry = {
        "metadata": {
            "stage": "round_of_16",
            "tie_id": "tie-7",
            "leg": "second",
            "first_leg_score": "1:0",
        },
        "pre_match_snapshot": {
            "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
            "elo_state": {"home_rating": 1800, "away_rating": 1700},
        },
        "prediction": {},
    }

    rebuilt = rebuild_prediction(PredictionService(_engine()), entry, competition="ucl2026")

    assert rebuilt["prediction"]["context"]["stage"] == "round_of_16"
    assert rebuilt["prediction"]["context"]["tie_id"] == "tie-7"
    assert rebuilt["prediction"]["context"]["leg"] == "second"
    assert rebuilt["prediction"]["context"]["first_leg_score"] == "1:0"


def test_completed_matches_surface_archived_prediction_contract(monkeypatch):
    kickoff = datetime(2026, 9, 1, 18, tzinfo=timezone.utc)
    observed_at = (kickoff - timedelta(minutes=15)).isoformat()
    archived_context = {
        "competition": "ucl2026",
        "stage": "round_of_16",
        "tie_id": "tie-7",
        "leg": "second",
        "first_leg_score": "1:0",
    }
    archived_provenance = {
        "odds": {
            "source": "odds_cache",
            "status": "stale",
            "observed_at": observed_at,
            "provider_request_id": "request-123",
        },
    }
    archive = MemoryCollection([{
        "_id": "m1",
        "metadata": {
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": kickoff.isoformat(),
        },
        "pre_match_snapshot": {
            "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
            "source_mode": "odds-only",
            "status": "stale",
            "source": "odds_cache",
            "observed_at": observed_at,
            "input_provenance": archived_provenance,
            "provenance": archived_provenance,
        },
        "prediction": {
            "model_tip": "1:0",
            "top_tip": "1:0",
            "pool_tip": "0:0",
            "pool_status": "available",
            "source_mode": "odds-only",
            "status": "stale",
            "source": "odds_cache",
            "observed_at": observed_at,
            "input_provenance": archived_provenance,
            "provenance": archived_provenance,
            "context": archived_context,
            "max_xp": 1.5,
        },
        "post_match_result": {"status": "completed", "actual_score": "1:0"},
    }])
    cache = MemoryCollection([{
        "_id": "ucl2026:matches_cache",
        "data": [{
            "id": "m1",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "raw_match": {
                "id": "m1",
                "home_team": "Bayern Munich",
                "away_team": "Arsenal",
                "commence_time": kickoff.isoformat(),
                "round": "Round of 16",
            },
        }],
    }])
    monkeypatch.setattr(
        "src.routes.matches.espn_data.get_scoreboard",
        lambda competition=None: [{
            "id": "m1",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": kickoff.isoformat(),
            "round": "Round of 16",
            "completed": True,
            "actual_score": "1:0",
        }],
    )
    monkeypatch.setattr("src.routes.matches._build_odds_api_lookup", lambda *args, **kwargs: {})

    router = matches_router(_engine(), object(), cache, archive)
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/matches")
    result = endpoint(competition="ucl2026")
    match = result[0]

    assert match["model_tip"] == "1:0"
    assert match["top_tip"] == "1:0"
    assert match["pool_tip"] == "0:0"
    assert match["pool_status"] == "available"
    assert match["source_mode"] == "odds-only"
    assert match["status"] == "stale"
    assert match["source"] == "odds_cache"
    assert match["input_provenance"] == archived_provenance
    assert match["provenance"] == archived_provenance
    assert match["match_context"] == archived_context


@pytest.mark.parametrize("competition", ["wc2026", "ucl2026"])
def test_undated_elo_does_not_borrow_odds_age_or_claim_a_provider(competition):
    result = PredictionService(_engine()).predict(
        odds={"home": 2.0, "draw": 3.2, "away": 4.0},
        elo={"home_rating": 1800, "away_rating": 1700},
        competition=competition,
        observed_at="2026-10-04T10:00:00+00:00",
    )
    assert result["source_mode"] == "odds+elo"
    assert result["input_provenance"]["odds"]["observed_at"] == "2026-10-04T10:00:00+00:00"
    assert result["input_provenance"]["elo"]["observed_at"] is None
    assert result["input_provenance"]["elo"]["source"] == "elo"


def test_elo_retains_its_own_nested_source_observation():
    result = PredictionService(_engine()).predict(
        odds={"home": 2.0, "draw": 3.2, "away": 4.0},
        elo={"home_rating": 1800, "away_rating": 1700, "provenance": {
            "source": "clubelo", "observed_at": "2026-09-24T10:00:00+00:00",
        }},
        competition="ucl2026",
        observed_at="2026-10-04T10:00:00+00:00",
    )
    assert result["input_provenance"]["elo"]["source"] == "clubelo"
    assert result["input_provenance"]["elo"]["observed_at"] == "2026-09-24T10:00:00+00:00"
