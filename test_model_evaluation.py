from datetime import datetime
from math import log

import pandas as pd
import pytest

from src.services.prediction import freeze_prediction
from src.services.model_evaluation import compare_models, freeze_due_comparisons


def _baseline(probabilities, observed_at, source):
    return {"probabilities": probabilities, "observed_at": observed_at, "source": source}


def _entry(*, actual="1:0", baselines=None, frozen_at="2026-09-30T10:00:00+00:00", metadata_fields=None, **prediction_fields):
    prediction = {
        "frozen_at": frozen_at,
        "probabilities": {"home": 0.6, "draw": 0.3, "away": 0.1},
        **prediction_fields,
    }
    if baselines is not None:
        prediction["evaluation_baselines"] = baselines
    return {
        "metadata": {"commence_time": "2026-09-30T12:00:00+00:00", **(metadata_fields or {})},
        "prediction": prediction,
        "post_match_result": {"status": "completed", "actual_score": actual},
    }


def test_comparison_uses_one_verified_pre_kickoff_sample_and_excludes_hindsight():
    before_freeze = "2026-09-30T09:45:00+00:00"
    paired = _entry(baselines={
        "bookmaker": _baseline({"home": 0.5, "draw": 0.3, "away": 0.2}, before_freeze, "odds_api"),
        "elo": _baseline({"home": 0.4, "draw": 0.35, "away": 0.25}, before_freeze, "clubelo"),
    })
    missing = _entry(baselines={
        "bookmaker": _baseline({"home": 0.5, "draw": 0.3, "away": 0.2}, before_freeze, "odds_api"),
    })
    hindsight = _entry(baselines={
        "bookmaker": _baseline({"home": 0.5, "draw": 0.3, "away": 0.2}, "2026-09-30T12:01:00+00:00", "odds_api"),
        "elo": _baseline({"home": 0.4, "draw": 0.35, "away": 0.25}, before_freeze, "clubelo"),
    })
    late_capture = _entry(baselines={
        "bookmaker": _baseline({"home": 0.5, "draw": 0.3, "away": 0.2}, "2026-09-30T10:01:00+00:00", "odds_api"),
        "elo": _baseline({"home": 0.4, "draw": 0.35, "away": 0.25}, before_freeze, "clubelo"),
    })
    reconstructed = _entry(baselines={
        "bookmaker": _baseline({"home": 0.5, "draw": 0.3, "away": 0.2}, before_freeze, "odds_api"),
        "elo": _baseline({"home": 0.4, "draw": 0.35, "away": 0.25}, before_freeze, "clubelo"),
    }, algo_reconstructed=True)

    result = compare_models({
        "paired": paired, "missing": missing, "hindsight": hindsight,
        "late_capture": late_capture, "reconstructed": reconstructed,
    }, "ucl2026")

    assert result["counts"] == {
        "total_completed": 5,
        "verified_model": 4,
        "paired": 1,
        "missing_baselines": 3,
        "excluded": 1,
    }
    model, bookmaker, elo = result["models"]
    assert [row["n"] for row in result["models"]] == [1, 1, 1]
    assert model["brier"] == 0.26
    assert bookmaker["brier"] == 0.38
    assert elo["brier"] == 0.545
    assert round(model["log_loss"], 6) == round(-log(0.6), 6)
    assert model["accuracy"] == 1.0
    assert model["calibration"] == [{
        "range": "0.50-0.65", "count": 1, "mean_confidence": 0.6, "observed_accuracy": 1.0,
    }]


def test_comparison_has_an_explicit_empty_paired_sample():
    result = compare_models({"legacy": _entry(frozen_at=None)}, "ucl2026")

    assert result["counts"]["paired"] == 0
    assert result["models"]
    assert all(row["brier"] is None and row["log_loss"] is None for row in result["models"])


def test_extra_time_match_is_scored_against_confirmed_90_minute_draw():
    observed_at = "2026-09-30T09:45:00+00:00"
    probabilities = {"home": 0.2, "draw": 0.6, "away": 0.2}
    baselines = {
        name: _baseline(probabilities, observed_at, source)
        for name, source in (("bookmaker", "odds_api"), ("elo", "clubelo"))
    }
    entry = _entry(
        actual="2:1",
        baselines=baselines,
        metadata_fields={"is_ko_phase": True, "extra_time_eligible": True, "score_90": "1:1"},
        probabilities=probabilities,
    )

    result = compare_models({"extra_time": entry}, "ucl2026")

    assert result["counts"]["paired"] == 1
    assert result["models"][0]["accuracy"] == 1.0
    assert result["models"][0]["log_loss"] == round(-log(0.6), 6)


def test_extra_time_match_without_confirmed_90_minute_score_is_excluded():
    entry = _entry(
        actual="2:1",
        metadata_fields={"is_ko_phase": True, "extra_time_eligible": True},
    )

    result = compare_models({"no_90_score": entry}, "ucl2026")

    assert result["counts"]["verified_model"] == 0
    assert result["counts"]["excluded"] == 1
    assert result["counts"]["paired"] == 0


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}

    def find(self, query=None):
        return list(self.documents.values())

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        document = self.documents.get(key)
        inserted = document is None
        if inserted:
            if not upsert:
                return type("Result", (), {"matched_count": 0})()
            document = {"_id": key}
            self.documents[key] = document
        if not _matches(document, query):
            if inserted:
                del self.documents[key]
            return type("Result", (), {"matched_count": 0, "upserted_id": None})()
        for path, value in update.get("$setOnInsert", {}).items() if inserted else ():
            _set_path(document, path, value)
        for path, value in update.get("$set", {}).items():
            _set_path(document, path, value)
        return type("Result", (), {
            "matched_count": 0 if inserted else 1,
            "upserted_id": key if inserted else None,
        })()


def _get_path(document, path):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _set_path(document, path, value):
    target = document
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _matches(document, query):
    for path, expected in query.items():
        if path == "_id":
            continue
        actual = _get_path(document, path)
        if isinstance(expected, dict):
            if "$exists" in expected and (actual is not None) != bool(expected["$exists"]):
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True


class FakeMathEngine:
    @staticmethod
    def remove_margin(home, draw, away):
        implied = {"home": 1 / home, "draw": 1 / draw, "away": 1 / away}
        total = sum(implied.values())
        return {key: value / total for key, value in implied.items()}

    @staticmethod
    def get_elo_probability(home, away):
        return 1 / (10 ** (-(home - away) / 400) + 1)


class FreezeService:
    math_engine = FakeMathEngine()

    def predict(self, **_kwargs):
        return {
            "model_tip": "1:0", "top_tip": "1:0", "pool_tip": None,
            "pool_status": "unavailable", "status": "fresh", "source_status": "fresh",
            "source": "odds_api+clubelo", "observed_at": "2026-10-01T11:45:00+00:00",
            "source_mode": "odds+elo", "model_version": "test", "context": {},
            "input_provenance": {}, "source_inputs": {},
            "probabilities": {"home": 0.52, "draw": 0.27, "away": 0.21},
        }

    def _probabilities(self, _odds, elo):
        share = self.math_engine.get_elo_probability(elo["home_rating"], elo["away_rating"])
        draw = max(0.18, 0.28 - abs(elo["home_rating"] - elo["away_rating"]) / 10000)
        return ({
            "home": share * (1 - draw),
            "draw": draw,
            "away": (1 - share) * (1 - draw),
        }, {})


def _freeze_fixture(elo_state):
    kickoff = "2026-10-01T12:00:00+00:00"
    archive = MemoryCollection([{
        "_id": "game-1",
        "metadata": {"commence_time": kickoff},
        "pre_match_snapshot": {
            "timestamp_recorded": "2026-10-01T10:00:00+00:00",
            "elo_state": elo_state,
            # PredictionService may default a source timestamp to the odds
            # timestamp when the Elo input itself has none.
            "input_provenance": {
                "elo": {
                    "source": "clubelo",
                    "status": "fresh",
                    "observed_at": "2026-10-01T11:45:00+00:00",
                },
            },
        },
    }])
    cache = MemoryCollection([{
        "_id": "ucl2026:odds_snapshot:game-1:t15m",
        "competition": "ucl2026",
        "event_id": "game-1",
        "bucket": "t15m",
        "observed_at": "2026-10-01T11:45:00+00:00",
        "source": "odds_api",
        "status": "fresh",
        "odds": {"home": 2.0, "draw": 3.4, "away": 4.0},
    }])
    frozen = freeze_prediction(
        cache,
        archive,
        FreezeService(),
        "game-1",
        competition="ucl2026",
        now=datetime.fromisoformat("2026-10-01T11:50:00+00:00"),
    )
    return archive, frozen["prediction"]


def test_freeze_captures_exact_margin_free_market_and_pure_elo_inputs():
    archive, prediction = _freeze_fixture({
        "home_rating": 1600, "away_rating": 1500, "source": "clubelo", "status": "fresh",
    })

    baselines = prediction["evaluation_baselines"]
    assert baselines["bookmaker"]["probabilities"] == pytest.approx({
        "home": 34 / 71, "draw": 20 / 71, "away": 17 / 71,
    })
    assert baselines["bookmaker"]["observed_at"] == "2026-10-01T11:45:00+00:00"
    assert baselines["bookmaker"]["source"] == "odds_api"
    assert baselines["elo"]["source"] == "clubelo"
    assert baselines["elo"]["observed_at"] == "2026-10-01T10:00:00+00:00"
    assert baselines["elo"]["probabilities"] == pytest.approx({
        "home": 0.4672474498561061, "draw": 0.27, "away": 0.2627525501438939,
    })

    frozen_again = freeze_prediction(
        MemoryCollection(), archive, FreezeService(), "game-1", competition="ucl2026",
        now=datetime.fromisoformat("2026-10-01T11:55:00+00:00"),
    )
    assert frozen_again["prediction"]["evaluation_baselines"] == baselines


def test_freeze_does_not_turn_stale_undated_elo_into_a_comparable_baseline():
    _archive, prediction = _freeze_fixture({
        "home_rating": 1600, "away_rating": 1500, "source": "clubelo", "status": "stale",
    })

    assert "bookmaker" in prediction["evaluation_baselines"]
    assert "elo" not in prediction["evaluation_baselines"]


def test_pre_kickoff_historical_elo_provenance_remains_eligible():
    _archive, prediction = _freeze_fixture({
        "home_rating": 1600,
        "away_rating": 1500,
        "source": "historical_clubelo",
        "status": "fresh",
        "observed_at": "2026-10-01T09:00:00+00:00",
    })

    assert prediction["evaluation_baselines"]["elo"]["source"] == "historical_clubelo"


def _auto_capture_fixtures(*, kickoff="2026-10-01T12:00:00+00:00", snapshot=True):
    cache_docs = [{
        "_id": "ucl2026:matches_cache",
        "data": [{
            "id": "game-auto",
            "home_team": "Home",
            "away_team": "Away",
            "commence_time": kickoff,
            "round": "League Phase",
        }],
    }, {
        "_id": "ucl2026:clubelo_ratings",
        "source": "clubelo",
        "status": "fresh",
        "observed_at": "2026-10-01T10:00:00+00:00",
        "rows": [
            {"team_name": "Home", "elo_rating": 1600},
            {"team_name": "Away", "elo_rating": 1500},
        ],
    }]
    if snapshot:
        cache_docs.append({
            "_id": "ucl2026:odds_snapshot:game-auto:t15m",
            "competition": "ucl2026",
            "event_id": "game-auto",
            "bucket": "t15m",
            "observed_at": "2026-10-01T11:45:00+00:00",
            "source": "odds_api",
            "status": "fresh",
            "odds": {"home": 2.0, "draw": 3.4, "away": 4.0},
        })
    return MemoryCollection(cache_docs)


def test_due_freeze_runs_once_from_cached_snapshot_and_preserves_user_tip():
    cache = _auto_capture_fixtures()
    archive = MemoryCollection([{
        "_id": "game-auto",
        "metadata": {"commence_time": "2026-10-01T12:00:00+00:00"},
        "prediction": {"user_tip": "1:1"},
        "post_match_result": {"status": "pending", "actual_score": None},
    }])
    service = FreezeService()
    now = datetime.fromisoformat("2026-10-01T11:50:00+00:00")

    first = freeze_due_comparisons(service, cache, archive, "ucl2026", now)
    frozen = archive.find_one({"_id": "game-auto"})
    second = freeze_due_comparisons(service, cache, archive, "ucl2026", now)

    assert first == 1
    assert second == 0
    assert frozen["prediction"]["user_tip"] == "1:1"
    assert frozen["post_match_result"] == {"status": "pending", "actual_score": None}
    assert frozen["prediction"]["evaluation_baselines"]["elo"]["source"] == "clubelo"


def test_due_freeze_initializes_missing_archive_and_skips_past_or_unquoted_fixtures():
    cache = _auto_capture_fixtures()
    archive = MemoryCollection()
    service = FreezeService()
    now = datetime.fromisoformat("2026-10-01T11:50:00+00:00")

    assert freeze_due_comparisons(service, cache, archive, "ucl2026", now) == 1
    new_entry = archive.find_one({"_id": "game-auto"})
    assert new_entry["metadata"]["home_team"] == "Home"
    assert new_entry["prediction"]["frozen_at"] < new_entry["metadata"]["commence_time"]

    past_cache = _auto_capture_fixtures(kickoff="2026-10-01T11:40:00+00:00")
    past_archive = MemoryCollection()
    assert freeze_due_comparisons(
        FreezeService(), past_cache, past_archive, "ucl2026", now,
    ) == 0
    assert past_archive.documents == {}

    no_quote_cache = _auto_capture_fixtures(snapshot=False)
    no_quote_archive = MemoryCollection()
    assert freeze_due_comparisons(
        FreezeService(), no_quote_cache, no_quote_archive, "ucl2026", now,
    ) == 0
    assert no_quote_archive.documents == {}


def test_due_freeze_does_not_substitute_current_elo_for_a_missing_cached_team():
    cache = _auto_capture_fixtures()
    cache.documents["ucl2026:clubelo_ratings"]["rows"] = [
        {"team_name": "Home", "elo_rating": 1600},
    ]
    service = FreezeService()
    service.math_engine.elo_df = pd.DataFrame([
        {"team_name": "Home", "elo_rating": 1600},
        {"team_name": "Away", "elo_rating": 1500},
    ])
    archive = MemoryCollection()
    now = datetime.fromisoformat("2026-10-01T11:50:00+00:00")

    assert freeze_due_comparisons(service, cache, archive, "ucl2026", now) == 1
    assert "elo" not in archive.find_one({"_id": "game-auto"})["prediction"]["evaluation_baselines"]
