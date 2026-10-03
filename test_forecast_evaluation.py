from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest
from fastapi import HTTPException

from src.routes.model_evaluation import init_router
from src.services.forecast_evaluation import (
    evaluation_record,
    build_evaluation_forecast,
    evaluate_archive,
    persist_evaluation_forecast,
)
from src.services.maintenance import run_maintenance
from src.services.prediction import PredictionService, freeze_prediction


KICKOFF = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
CAPTURED = KICKOFF - timedelta(minutes=15)


class MathStub:
    def remove_margin(self, home, draw, away):
        implied = [1 / home, 1 / draw, 1 / away]
        total = sum(implied)
        return dict(zip(("home", "draw", "away"), (value / total for value in implied)))

    def get_elo_probability(self, home, away):
        return 0.75


class MemoryCollection:
    def __init__(self, documents=(), *, fail_find=False):
        self.documents = {doc["_id"]: deepcopy(doc) for doc in documents}
        self.updates = []
        self.fail_find = fail_find

    def find(self, query=None):
        if self.fail_find:
            raise RuntimeError("storage unavailable")
        return list(self.documents.values())

    def find_one(self, query):
        return deepcopy(self.documents.get(query["_id"]))

    def update_one(self, query, update, upsert=False):
        doc = self.documents.get(query.get("_id"))
        if doc is None:
            return type("Result", (), {"matched_count": 0})()
        for path, condition in query.items():
            if path == "_id":
                continue
            value = doc
            exists = True
            for part in path.split("."):
                if not isinstance(value, dict) or part not in value:
                    exists = False
                    value = None
                    break
                value = value[part]
            if isinstance(condition, dict) and "$exists" in condition and exists != condition["$exists"]:
                return type("Result", (), {"matched_count": 0})()
        self.updates.append(deepcopy(update))
        updated = deepcopy(doc)
        for path, value in update.get("$set", {}).items():
            target = updated
            parts = path.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = deepcopy(value)
        self.documents[query["_id"]] = updated
        return type("Result", (), {"matched_count": 1})()

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise RuntimeError("duplicate key")
        self.documents[document["_id"]] = deepcopy(document)

    def delete_one(self, query):
        self.documents.pop(query.get("_id"), None)


class FreezeService:
    model_version = "prediction-test"

    def __init__(self):
        self.math_engine = MathStub()
        self._probability_service = PredictionService(self.math_engine)

    def _probabilities(self, odds, elo):
        return self._probability_service._probabilities(odds, elo)

    def evaluation_probabilities(self, odds, elo):
        return self._probability_service.evaluation_probabilities(odds, elo)

    def predict(self, **kwargs):
        return {
            "probabilities": self.evaluation_probabilities(kwargs["odds"], kwargs["elo"])["model"],
            "model_tip": "1:0", "top_tip": "1:0", "pool_tip": None,
            "pool_status": "unavailable", "status": "fresh",
            "source_status": "fresh", "source": "odds_api",
            "observed_at": kwargs["observed_at"], "source_mode": "combined",
            "model_version": self.model_version, "context": kwargs["context"],
            "input_provenance": {}, "provenance": {},
            "source_inputs": {"odds": kwargs["odds"], "elo": kwargs["elo"]},
            "xg_home": 1.2, "xg_away": 0.7,
        }


def forecast(**overrides):
    result = {
        "schema_version": 1,
        "capture_source": "maintenance",
        "captured_at": CAPTURED.isoformat(),
        "kickoff_at": KICKOFF.isoformat(),
        "model_version": "prediction-test",
        "probabilities": {
            "model": {"home": 0.8, "draw": 0.1, "away": 0.1},
            "market": {"home": 0.6, "draw": 0.2, "away": 0.2},
            "elo": {"home": 0.3, "draw": 0.4, "away": 0.3},
        },
        "provenance": {
            "market": {"source": "odds_api", "observed_at": (CAPTURED - timedelta(minutes=1)).isoformat()},
            "elo": {"source": "clubelo", "observed_at": (CAPTURED - timedelta(minutes=1)).isoformat()},
        },
    }
    result.update(overrides)
    return result


def archive_entry(match_id, *, evaluation_forecast=None, actual_score="1:0", metadata=None, prediction=None):
    return {
        "_id": match_id,
        "metadata": {"commence_time": KICKOFF.isoformat(), "is_ko_phase": False, **(metadata or {})},
        "prediction": {"evaluation_forecast": evaluation_forecast, **(prediction or {})},
        "post_match_result": {"status": "completed", "actual_score": actual_score},
    }


def test_prediction_service_returns_model_market_and_elo_vectors_from_shared_probability_path():
    service = PredictionService(MathStub())
    vectors = service.evaluation_probabilities(
        {"home": 2.0, "draw": 4.0, "away": 4.0},
        {"home_rating": 2000, "away_rating": 1800},
    )

    assert vectors["model"] == pytest.approx({"home": 0.51875, "draw": 0.25, "away": 0.23125})
    assert vectors["market"] == pytest.approx({"home": 0.5, "draw": 0.25, "away": 0.25})
    assert vectors["elo"] == pytest.approx({"home": 0.555, "draw": 0.26, "away": 0.185})


def test_capture_accepts_t15_and_rejects_t5_or_unknown_input_timestamps():
    service = PredictionService(MathStub())
    odds = {
        "_id": "wc2026:odds_snapshot:m1:t15m:1",
        "bucket": "t15m",
        "source": "odds_api",
        "status": "fresh",
        "observed_at": (CAPTURED - timedelta(seconds=1)).isoformat(),
        "odds": {"home": 2.0, "draw": 4.0, "away": 4.0},
    }
    elo = {
        "home_rating": 2000,
        "away_rating": 1800,
        "source": "clubelo",
        "observed_at": (CAPTURED - timedelta(seconds=1)).isoformat(),
    }

    record = build_evaluation_forecast(
        service, odds, elo, kickoff_at=KICKOFF, captured_at=CAPTURED,
        capture_source="freeze",
    )
    assert record["captured_at"] == CAPTURED.isoformat()
    assert record["probabilities"]["elo"]["draw"] == pytest.approx(0.26)
    assert record["provenance"]["market"]["snapshot_id"] == odds["_id"]

    assert build_evaluation_forecast(
        service, odds, elo, kickoff_at=KICKOFF,
        captured_at=KICKOFF - timedelta(minutes=5), capture_source="freeze",
    ) is None
    assert build_evaluation_forecast(
        service, {**odds, "observed_at": None}, elo,
        kickoff_at=KICKOFF, captured_at=CAPTURED, capture_source="freeze",
    ) is None


def test_evaluation_uses_one_common_sample_and_reports_each_primary_exclusion():
    invalid_vector = forecast()
    invalid_vector["probabilities"]["market"] = {"home": 0.7, "draw": 0.2, "away": 0.2}
    missing_timestamp = forecast()
    missing_timestamp["provenance"]["elo"].pop("observed_at")
    docs = [
        archive_entry("included", evaluation_forecast=forecast()),
        archive_entry("invalid-vector", evaluation_forecast=invalid_vector),
        archive_entry("missing-source-time", evaluation_forecast=missing_timestamp),
        archive_entry("missing-capture", evaluation_forecast=None),
        archive_entry("ambiguous-ko", evaluation_forecast=forecast(), metadata={"is_ko_phase": True}),
    ]

    result = evaluate_archive(docs, competition="wc2026")

    assert result["completed_count"] == 5
    assert result["captured_count"] == 4
    assert result["common_sample_count"] == 1
    assert result["coverage_rate"] == pytest.approx(0.2)
    assert result["exclusions"] == {
        "invalid_probability_vector": 1,
        "missing_source_timestamp": 1,
        "missing_capture": 1,
        "ambiguous_ko_result": 1,
    }
    assert result["metrics"]["model"]["brier_score"] == pytest.approx(0.06)
    assert result["metrics"]["model"]["log_loss"] == pytest.approx(-math.log(0.8))


def test_evaluation_uses_explicit_90_minute_score_for_knockout_and_floors_log_loss():
    zero = forecast()
    zero["probabilities"]["model"] = {"home": 0.0, "draw": 0.4, "away": 0.6}
    docs = [archive_entry(
        "ko",
        evaluation_forecast=zero,
        actual_score="2:1",
        metadata={"is_ko_phase": True, "score_90": "1:0"},
    )]

    result = evaluate_archive(docs, competition="ucl2026")

    assert result["common_sample_count"] == 1
    assert result["metrics"]["model"]["log_loss"] == pytest.approx(-math.log(1e-15))
    assert result["metric_definitions"]["brier_range"] == [0, 2]
    assert result["metric_definitions"]["probability_floor"] == 1e-15


def test_empty_archive_has_null_metrics_and_storage_failure_is_503():
    empty_router = init_router({"wc2026": MemoryCollection()})
    endpoint = next(route.endpoint for route in empty_router.routes if route.path == "/api/model-evaluation")
    empty = endpoint(competition="wc2026")
    assert empty["completed_count"] == 0
    assert empty["metrics"]["model"] == {"brier_score": None, "log_loss": None}
    assert empty["coverage_rate"] is None

    failed_router = init_router({"wc2026": MemoryCollection(fail_find=True)})
    failed_endpoint = next(route.endpoint for route in failed_router.routes if route.path == "/api/model-evaluation")
    with pytest.raises(HTTPException) as error:
        failed_endpoint(competition="wc2026")
    assert error.value.status_code == 503


def test_forecast_write_is_conditional_and_only_sets_the_immutable_record():
    record = forecast()
    archive = MemoryCollection([{"_id": "m1", "prediction": {"top_tip": "2:0", "user_tip": "1:1"}}])

    assert persist_evaluation_forecast(archive, "m1", record) is True
    assert persist_evaluation_forecast(archive, "m1", {**record, "model_version": "later"}) is False
    saved = archive.find_one({"_id": "m1"})
    assert saved["prediction"]["evaluation_forecast"] == record
    assert saved["prediction"]["top_tip"] == "2:0"
    assert saved["prediction"]["user_tip"] == "1:1"
    assert archive.updates[0] == {"$set": {"prediction.evaluation_forecast": record}}

    frozen = MemoryCollection([{"_id": "m2", "prediction": {"frozen_at": CAPTURED.isoformat()}}])
    assert persist_evaluation_forecast(frozen, "m2", record) is False


def test_explicit_freeze_captures_separate_forecast_only_inside_t15_to_t5_window():
    odds = {
        "_id": "wc2026:odds_snapshot:m1:t15m:1", "competition": "wc2026",
        "event_id": "m1", "bucket": "t15m", "status": "fresh",
        "source": "odds_api", "observed_at": CAPTURED.isoformat(),
        "odds": {"home": 2.0, "draw": 4.0, "away": 4.0},
    }
    elo = {"home_rating": 2000, "away_rating": 1800, "source": "local_elo", "observed_at": CAPTURED.isoformat()}
    entry = {
        "_id": "m1",
        "metadata": {"home_team": "Home", "away_team": "Away", "commence_time": KICKOFF.isoformat()},
        "pre_match_snapshot": {"timestamp_recorded": CAPTURED.isoformat(), "elo_state": elo},
        "prediction": {"top_tip": "8:8", "model_tip": "7:7", "user_tip": "2:1"},
    }
    cache = MemoryCollection([odds])
    archive = MemoryCollection([entry])

    frozen = freeze_prediction(cache, archive, FreezeService(), "m1", competition="wc2026", now=CAPTURED)
    saved = frozen["prediction"]
    normalized = evaluation_record(frozen)
    assert normalized["captured_at"] == CAPTURED.isoformat()
    assert normalized["probabilities"]["market"]["home"] == pytest.approx(0.5)
    assert saved["user_tip"] == "2:1"

    later = MemoryCollection([{
        **entry,
        "prediction": {"top_tip": "8:8", "user_tip": "2:1"},
    }])
    with pytest.raises(ValueError, match="T-5"):
        freeze_prediction(
            cache, later, FreezeService(), "m1", competition="wc2026",
            now=KICKOFF - timedelta(minutes=5),
        )
    assert later.updates == []


def maintenance_fixture(*, bucket_claimed=False):
    old_time = KICKOFF - timedelta(minutes=30)
    cache_documents = [
        {
            "_id": "wc2026:matches_cache",
            "data": [{"id": "m1", "home_team": "Home", "away_team": "Away", "commence_time": KICKOFF.isoformat(), "round": "Group"}],
        },
        {
            "_id": "wc2026:odds_snapshot:m1:t30m:old", "competition": "wc2026",
            "event_id": "m1", "bucket": "t30m", "status": "fresh", "source": "odds_api",
            "observed_at": old_time.isoformat(),
            "odds": {"home": 2.0, "draw": 4.0, "away": 4.0},
        },
    ]
    if bucket_claimed:
        cache_documents.append({
            "_id": "wc2026:odds_bucket_state",
            "events": {"m1": {bucket: {"status": "fresh"} for bucket in ("t24h", "t6h", "t75m", "t30m", "t15m")}},
        })
    archive = MemoryCollection([{
        "_id": "m1",
        "metadata": {"home_team": "Home", "away_team": "Away", "is_ko_phase": False, "commence_time": KICKOFF.isoformat()},
        "pre_match_snapshot": {
            "timestamp_recorded": old_time.isoformat(),
            "elo_state": {"home_rating": 2000, "away_rating": 1800, "source": "local_elo", "observed_at": old_time.isoformat()},
        },
        "prediction": {"top_tip": "3:0", "model_tip": "1:0", "user_tip": "0:0", "bots": {"broker": {"tip": "1:1"}}},
        "post_match_result": {"status": "pending", "actual_score": None, "points_earned": None},
    }])
    return MemoryCollection(cache_documents), archive


class Provider:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def get_competition_odds(self, competition, market):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return [{
            "id": "m1", "home_team": "Home", "away_team": "Away",
            "commence_time": KICKOFF.isoformat(),
            "odds": {"home": 1.8, "draw": 3.2, "away": 4.5},
        }]


@pytest.mark.parametrize("branch", ["idle", "failure", "success"])
def test_authenticated_maintenance_captures_only_the_forecast_in_every_return_branch(branch):
    cache, archive = maintenance_fixture(bucket_claimed=(branch == "idle"))
    provider = Provider(fail=(branch == "failure"))
    before = archive.find_one({"_id": "m1"})
    result = run_maintenance(
        {"wc2026": cache}, provider,
        archive_collections={"wc2026": archive},
        math_engine=MathStub(), competition="wc2026",
        now=KICKOFF - timedelta(minutes=10),
    )

    saved = archive.find_one({"_id": "m1"})
    assert saved["prediction"]["evaluation_forecast"]["capture_source"] == "maintenance"
    assert saved["prediction"]["top_tip"] == before["prediction"]["top_tip"]
    assert saved["prediction"]["model_tip"] == before["prediction"]["model_tip"]
    assert saved["prediction"]["user_tip"] == before["prediction"]["user_tip"]
    assert saved["prediction"]["bots"] == before["prediction"]["bots"]
    assert saved["post_match_result"] == before["post_match_result"]
    assert provider.calls == (0 if branch == "idle" else 1)
    if branch == "success":
        assert saved["prediction"]["evaluation_forecast"]["inputs"]["odds"]["home"] == 1.8
    else:
        assert saved["prediction"]["evaluation_forecast"]["inputs"]["odds"]["home"] == 2.0
    assert result["provider_calls"] == provider.calls


def test_authenticated_force_maintenance_captures_from_cache_without_provider_call():
    cache, archive = maintenance_fixture(bucket_claimed=True)
    provider = Provider()
    result = run_maintenance(
        {"wc2026": cache}, provider,
        archive_collections={"wc2026": archive},
        math_engine=MathStub(), competition="wc2026", force=True,
        allow_force_capture=True, now=KICKOFF - timedelta(minutes=10),
    )

    assert result["provider_calls"] == 0
    assert provider.calls == 0
    assert archive.find_one({"_id": "m1"})["prediction"]["evaluation_forecast"]


@pytest.mark.parametrize("context", [{"stage": "final"}, {"is_ko_phase": True}, {"extra_time_eligible": True}, {"score_aet": "2:1"}, {"shootout_winner": "Home"}])
def test_ambiguous_extra_time_context_is_excluded_without_explicit_90_minute_score(context):
    entry = archive_entry("ko", evaluation_forecast=forecast(), prediction={"context": context})
    result = evaluate_archive([entry])
    assert result["common_sample_count"] == 0
    assert result["exclusions"] == {"ambiguous_ko_result": 1}


def test_malformed_result_does_not_break_other_completed_samples():
    broken = {"_id": "broken", "post_match_result": "completed"}
    result = evaluate_archive([broken, archive_entry("valid", evaluation_forecast=forecast())])
    assert result["common_sample_count"] == 1


@pytest.mark.parametrize("delta, reason", [(0, "after_kickoff_capture"), (-4, "outside_capture_window"), (-16, "outside_capture_window")])
def test_evaluation_rejects_late_and_out_of_window_captures(delta, reason):
    result = evaluate_archive([archive_entry("late", evaluation_forecast=forecast(captured_at=(KICKOFF + timedelta(minutes=delta)).isoformat()))])
    assert result["common_sample_count"] == 0
    assert result["exclusions"] == {reason: 1}


def test_existing_null_capture_is_not_replaced():
    archive = MemoryCollection([{"_id": "null", "prediction": {"evaluation_forecast": None}}])
    assert persist_evaluation_forecast(archive, "null", forecast()) is False


@pytest.mark.parametrize("format", ["nested", "native"])
def test_both_evaluation_endpoints_read_each_immutable_forecast_format(format):
    from src.services.model_evaluation import compare_models

    record = forecast()
    if format == "native":
        record = {
            "frozen_at": record["captured_at"],
            "model_version": record["model_version"],
            "context": {"commence_time": record["kickoff_at"]},
            "probabilities": record["probabilities"]["model"],
            "evaluation_baselines": {
                "bookmaker": {**record["provenance"]["market"], "probabilities": record["probabilities"]["market"]},
                "elo": {**record["provenance"]["elo"], "probabilities": record["probabilities"]["elo"]},
            },
        }
    entry = archive_entry("m1", evaluation_forecast=record)
    original = deepcopy(entry)
    evaluation = evaluate_archive([entry], competition="wc2026")
    comparison = compare_models({"m1": entry}, "wc2026")
    assert evaluation["common_sample_count"] == comparison["counts"]["paired"] == 1
    for method, row in zip(("model", "market", "elo"), comparison["models"]):
        assert evaluation["metrics"][method]["brier_score"] == pytest.approx(row["brier"])
        assert round(evaluation["metrics"][method]["log_loss"], 6) == row["log_loss"]
    assert entry == original


@pytest.mark.parametrize("existing_record", [None, forecast()])
def test_native_freeze_preserves_an_existing_evaluation_capture_and_visible_tips(existing_record):
    odds = {
        "_id": "wc2026:odds_snapshot:m1:t15m:1", "competition": "wc2026",
        "event_id": "m1", "bucket": "t15m", "status": "fresh", "source": "odds_api",
        "observed_at": CAPTURED.isoformat(), "odds": {"home": 2.0, "draw": 4.0, "away": 4.0},
    }
    entry = {
        "_id": "m1",
        "metadata": {"home_team": "Home", "away_team": "Away", "commence_time": KICKOFF.isoformat()},
        "pre_match_snapshot": {"timestamp_recorded": CAPTURED.isoformat(), "elo_state": {
            "home_rating": 2000, "away_rating": 1800, "source": "local_elo", "observed_at": CAPTURED.isoformat(),
        }},
        "prediction": {"top_tip": "8:8", "model_tip": "7:7", "user_tip": "2:1", "evaluation_forecast": existing_record},
    }
    archive = MemoryCollection([entry])
    saved = freeze_prediction(MemoryCollection([odds]), archive, FreezeService(), "m1", competition="wc2026", now=CAPTURED)["prediction"]
    assert saved["evaluation_forecast"] == existing_record
    assert saved["frozen_at"] == CAPTURED.isoformat()
    assert (saved["top_tip"], saved["model_tip"], saved["user_tip"]) == ("8:8", "7:7", "2:1")
    assert all("prediction.evaluation_forecast" not in update["$set"] for update in archive.updates)


def test_malformed_native_capture_does_not_break_the_strict_evaluation():
    malformed = {"frozen_at": CAPTURED.isoformat(), "evaluation_baselines": {"bookmaker": [1]}, "context": [1]}
    result = evaluate_archive([archive_entry("m1", evaluation_forecast=malformed)], competition="wc2026")
    assert result["common_sample_count"] == 0
    assert result["exclusions"] == {"missing_source_timestamp": 1}
