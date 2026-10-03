"""Pure scoring plus immutable storage helpers for archived forecasts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from numbers import Real
import re
from typing import Any, Mapping

from src.competitions import get_competition


METHODS = ("model", "market", "elo")
OUTCOMES = ("home", "draw", "away")
PROBABILITY_FLOOR = 1e-15
SCORE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
KO_STAGES = {"playoff", "round_of_16", "quarterfinal", "semifinal", "final"}


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _valid_vector(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping) or set(value) != set(OUTCOMES):
        return None
    result = {}
    for key in OUTCOMES:
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, Real):
            return None
        probability = float(item)
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            return None
        result[key] = probability
    if not math.isclose(sum(result.values()), 1.0, rel_tol=1e-9, abs_tol=1e-6):
        return None
    return result


def build_evaluation_forecast(
    service,
    odds_snapshot: Mapping[str, Any],
    elo_state: Mapping[str, Any],
    *,
    kickoff_at: Any,
    captured_at: Any,
    capture_source: str,
    elo_observed_at: Any = None,
) -> dict[str, Any] | None:
    """Build a complete, timestamp-verified forecast record without writing it."""
    kickoff = _timestamp(kickoff_at)
    captured = _timestamp(captured_at)
    market_time = _timestamp(odds_snapshot.get("observed_at"))
    elo_time = _timestamp(elo_state.get("observed_at") or elo_observed_at)
    if not kickoff or not captured or not market_time or not elo_time:
        return None
    if capture_source not in {"freeze", "maintenance"}:
        return None
    if not kickoff - timedelta(minutes=15) <= captured < kickoff - timedelta(minutes=5):
        return None
    if market_time > captured or elo_time > captured or market_time >= kickoff or elo_time >= kickoff:
        return None
    if odds_snapshot.get("status", "fresh") not in {"fresh", "stale"}:
        return None

    vectors = service.evaluation_probabilities(odds_snapshot, elo_state)
    if not isinstance(vectors, Mapping):
        return None
    normalized = {method: _valid_vector(vectors.get(method)) for method in METHODS}
    if any(value is None for value in normalized.values()):
        return None

    from src.services.prediction import _safe_odds, _safe_elo
    clean_odds, clean_elo = _safe_odds(odds_snapshot), _safe_elo(elo_state)
    if clean_odds is None or clean_elo is None:
        return None
    market_provenance = {
        "observed_at": market_time.isoformat(),
        **({"source": str(odds_snapshot["source"])} if odds_snapshot.get("source") else {}),
        **({"snapshot_id": str(odds_snapshot["_id"])} if odds_snapshot.get("_id") is not None else {}),
        **({"bucket": str(odds_snapshot["bucket"])} if odds_snapshot.get("bucket") else {}),
    }
    elo_provenance = {
        "observed_at": elo_time.isoformat(),
        **({"source": str(elo_state["source"])} if elo_state.get("source") else {}),
    }
    if isinstance(elo_state.get("provenance"), Mapping):
        for key in ("source", "snapshot_id", "observed_at"):
            if key in elo_state["provenance"] and key not in elo_provenance:
                elo_provenance[key] = elo_state["provenance"][key]

    return {
        "schema_version": 1,
        "capture_source": capture_source,
        "captured_at": captured.isoformat(),
        "kickoff_at": kickoff.isoformat(),
        "model_version": str(service.model_version),
        "probabilities": normalized,
        "inputs": {"odds": clean_odds, "elo": clean_elo},
        "provenance": {"market": market_provenance, "elo": elo_provenance},
    }


def persist_evaluation_forecast(archive_collection, match_id: str, record: Mapping[str, Any]) -> bool:
    """Write only once, and only while no legacy freeze has won the race."""
    result = archive_collection.update_one(
        {
            "_id": match_id,
            "prediction.evaluation_forecast": {"$exists": False},
            "prediction.frozen_at": {"$exists": False},
        },
        {"$set": {"prediction.evaluation_forecast": dict(record)}},
        upsert=False,
    )
    return getattr(result, "matched_count", 0) == 1


def capture_archive_forecasts(cache_collection, archive_collection, service, *, competition, now) -> int:
    """Capture eligible existing entries from stored inputs; no provider calls."""
    current = _timestamp(now)
    if current is None or archive_collection is None or service is None:
        return 0
    candidates = []
    for entry in archive_collection.find({}):
        if not isinstance(entry, Mapping):
            continue
        prediction = entry.get("prediction") or {}
        post = entry.get("post_match_result") if isinstance(entry.get("post_match_result"), Mapping) else {}
        kickoff = _timestamp((entry.get("metadata") or {}).get("commence_time"))
        if ("evaluation_forecast" in prediction or "frozen_at" in prediction
                or prediction.get("algo_reconstructed") is True
                or post.get("status") == "completed"
                or kickoff is None
                or not kickoff - timedelta(minutes=15) <= current < kickoff - timedelta(minutes=5)):
            continue
        candidates.append(entry)
    if not candidates:
        return 0
    comp = get_competition(competition)
    ids = [str(entry["_id"]) for entry in candidates]
    snapshots = list(cache_collection.find({"competition": comp.id, "event_id": {"$in": ids}}))
    captured = 0
    for entry in candidates:
        eligible = [snapshot for snapshot in snapshots
                    if str(snapshot.get("event_id")) == str(entry["_id"])
                    and snapshot.get("competition", comp.id) == comp.id
                    and snapshot.get("status", "fresh") in {"fresh", "stale"}
                    and (observed := _timestamp(snapshot.get("observed_at"))) is not None
                    and observed <= current]
        eligible.sort(key=lambda snapshot: _timestamp(snapshot["observed_at"]), reverse=True)
        pre_match = entry.get("pre_match_snapshot") or {}
        elo = pre_match.get("elo_state") or {}
        for snapshot in eligible:
            record = build_evaluation_forecast(
                service, snapshot, elo,
                kickoff_at=entry["metadata"]["commence_time"], captured_at=current,
                capture_source="maintenance", elo_observed_at=pre_match.get("timestamp_recorded"),
            )
            if record is not None:
                captured += int(persist_evaluation_forecast(archive_collection, entry["_id"], record))
                break
    if captured:
        from src.services.archive import invalidate_archive_mem_cache
        invalidate_archive_mem_cache(archive_collection)
    return captured


def _score(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = SCORE_RE.fullmatch(value)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _is_knockout(metadata: Mapping[str, Any]) -> bool:
    if metadata.get("is_ko_phase") is True or metadata.get("extra_time_eligible") is True:
        return True
    stage = str(metadata.get("stage") or "").casefold()
    if stage in KO_STAGES:
        return True
    try:
        from src.constants import _is_ko_round
        return bool(_is_ko_round(metadata.get("round", "")))
    except Exception:
        return False


def _result_score(document: Mapping[str, Any]) -> tuple[str | None, str | None]:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    post = document.get("post_match_result") if isinstance(document.get("post_match_result"), Mapping) else {}
    prediction = document.get("prediction") if isinstance(document.get("prediction"), Mapping) else {}
    context = prediction.get("context") if isinstance(prediction.get("context"), Mapping) else {}
    explicit_90 = post.get("score_90") or metadata.get("score_90") or context.get("score_90")
    if explicit_90 is not None:
        return ("invalid_90_minute_score", None) if _score(explicit_90) is None else (None, str(explicit_90))
    if any(_is_knockout(info) or any(info.get(key) is not None for key in ("score_aet", "shootout_winner"))
           for info in (metadata, context, post)):
        return "ambiguous_ko_result", None
    actual = post.get("actual_score")
    return ("invalid_result", None) if _score(actual) is None else (None, str(actual))


def _exclusion(document: Mapping[str, Any], forecast: Mapping[str, Any] | None) -> str | None:
    prediction = document.get("prediction") if isinstance(document.get("prediction"), Mapping) else {}
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    if not isinstance(forecast, Mapping):
        return "missing_capture"
    if prediction.get("algo_reconstructed") is True or forecast.get("capture_source") not in {"freeze", "maintenance"}:
        return "reconstructed_capture"
    captured = _timestamp(forecast.get("captured_at"))
    kickoff = _timestamp(forecast.get("kickoff_at"))
    metadata_kickoff = _timestamp(metadata.get("commence_time"))
    if not forecast.get("captured_at") or not forecast.get("kickoff_at") or not metadata.get("commence_time"):
        return "missing_capture_timestamp"
    if not captured or not kickoff or not metadata_kickoff:
        return "invalid_capture_timestamp"
    if kickoff != metadata_kickoff:
        return "kickoff_mismatch"
    if captured >= kickoff:
        return "after_kickoff_capture"
    if not kickoff - timedelta(minutes=15) <= captured < kickoff - timedelta(minutes=5):
        return "outside_capture_window"
    provenance = forecast.get("provenance") if isinstance(forecast.get("provenance"), Mapping) else {}
    for source in ("market", "elo"):
        info = provenance.get(source) if isinstance(provenance.get(source), Mapping) else {}
        value = info.get("observed_at")
        if not value:
            return "missing_source_timestamp"
        observed = _timestamp(value)
        if not observed or observed > captured or observed >= kickoff:
            return "invalid_source_timestamp"
    if not isinstance(forecast.get("model_version"), str) or not forecast["model_version"].strip():
        return "missing_model_version"
    probabilities = forecast.get("probabilities") if isinstance(forecast.get("probabilities"), Mapping) else {}
    if any(_valid_vector(probabilities.get(method)) is None for method in METHODS):
        return "invalid_probability_vector"
    result_reason, score = _result_score(document)
    if result_reason:
        return result_reason
    return None


def evaluation_record(document):
    """Read both immutable forecast formats without rewriting stored records."""
    prediction = document.get("prediction") if isinstance(document.get("prediction"), Mapping) else {}
    record = prediction.get("evaluation_forecast")
    if not isinstance(record, Mapping) or "capture_source" in record:
        return record
    baselines = record.get("evaluation_baselines") if isinstance(record.get("evaluation_baselines"), Mapping) else {}
    market = baselines.get("bookmaker") if isinstance(baselines.get("bookmaker"), Mapping) else {}
    elo = baselines.get("elo") if isinstance(baselines.get("elo"), Mapping) else {}
    context = record.get("context") if isinstance(record.get("context"), Mapping) else {}
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    return {
        "capture_source": "freeze", "captured_at": record.get("frozen_at"),
        "kickoff_at": context.get("commence_time") or metadata.get("commence_time"),
        "model_version": record.get("model_version"),
        "probabilities": {"model": record.get("probabilities"), "market": market.get("probabilities"), "elo": elo.get("probabilities")},
        "provenance": {"market": market, "elo": elo},
    }


def evaluate_archive(documents, *, competition=None) -> dict[str, Any]:
    """Score valid completed captures on one common sample; never fetch or write."""
    comp = get_competition(competition)
    completed = [
        document for document in documents
        if isinstance(document, Mapping)
        and isinstance(document.get("post_match_result"), Mapping)
        and document["post_match_result"].get("status") == "completed"
    ]
    scores = {method: {"brier": [], "log_loss": []} for method in METHODS}
    exclusions: dict[str, int] = {}
    captured_count = 0
    sample_count = 0
    for document in completed:
        prediction = document.get("prediction") if isinstance(document.get("prediction"), Mapping) else {}
        forecast = evaluation_record(document)
        if isinstance(forecast, Mapping):
            captured_count += 1
        reason = _exclusion(document, forecast if isinstance(forecast, Mapping) else None)
        if reason:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        reason, actual = _result_score(document)
        if reason or actual is None:
            exclusions[reason or "invalid_result"] = exclusions.get(reason or "invalid_result", 0) + 1
            continue
        home, away = _score(actual)
        outcome = "home" if home > away else "away" if home < away else "draw"
        probabilities = forecast["probabilities"]
        sample_count += 1
        for method in METHODS:
            vector = _valid_vector(probabilities[method])
            p = vector[outcome]
            scores[method]["brier"].append(sum((vector[key] - (1.0 if key == outcome else 0.0)) ** 2 for key in OUTCOMES))
            scores[method]["log_loss"].append(-math.log(max(p, PROBABILITY_FLOOR)))

    metrics = {
        method: {
            "brier_score": sum(values["brier"]) / sample_count if sample_count else None,
            "log_loss": sum(values["log_loss"]) / sample_count if sample_count else None,
        }
        for method, values in scores.items()
    }
    return {
        "competition": comp.id,
        "completed_count": len(completed),
        "captured_count": captured_count,
        "common_sample_count": sample_count,
        "coverage_rate": sample_count / len(completed) if completed else None,
        "exclusions": exclusions,
        "metrics": metrics,
        "metric_definitions": {
            "brier_range": [0, 2],
            "brier_score": "Mean per-game sum of the three squared class errors; range 0-2.",
            "log_loss": "Mean negative natural logarithm of the probability assigned to the observed 90-minute class.",
            "probability_floor": PROBABILITY_FLOOR,
        },
    }
