"""Paired, provenance-checked evaluation for frozen 1X2 probabilities."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from src.competitions import collection_for, find_competition_document, get_competition
from src.constants import TEAM_MAPPING
from src.services.snapshots import parse_time, select_t15_snapshot


OUTCOMES = ("home", "draw", "away")
SCORE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
EPSILON = 1e-15
CALIBRATION_BINS = (
    (1 / 3, 0.50, "0.33-0.50"),
    (0.50, 0.65, "0.50-0.65"),
    (0.65, 0.80, "0.65-0.80"),
    (0.80, 1.0000001, "0.80-1.00"),
)
MODEL_ROWS = (
    ("model", "Statistisches Modell"),
    ("bookmaker", "Buchmacher, margenfrei"),
    ("elo", "Reines Elo"),
)


def _probabilities(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        result = {key: float(value[key]) for key in OUTCOMES}
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(item) or item < 0 or item > 1 for item in result.values()):
        return None
    total = sum(result.values())
    if total <= 0 or abs(total - 1.0) > 0.01:
        return None
    return {key: item / total for key, item in result.items()}


def _outcome(actual_score: Any) -> str | None:
    match = SCORE_RE.fullmatch(str(actual_score or ""))
    if not match:
        return None
    home, away = int(match.group(1)), int(match.group(2))
    return "home" if home > away else "away" if away > home else "draw"


def _knockout_match(metadata: Mapping[str, Any]) -> bool:
    if metadata.get("extra_time_eligible") is True or metadata.get("is_ko_phase") is True or metadata.get("is_ko") is True:
        return True
    phase = " ".join(str(metadata.get(key) or "") for key in ("stage", "round", "phase")).lower()
    return any(term in phase for term in ("knockout", "playoff", "round of 16", "quarter", "semi", "final"))


def _evaluation_outcome(result: Mapping[str, Any], metadata: Mapping[str, Any]) -> str | None:
    if _knockout_match(metadata):
        # 1X2 inputs target regulation time; a post-extra-time score is not
        # comparable unless the archive also confirms the 90-minute score.
        return _outcome(metadata.get("score_90"))
    return _outcome(result.get("actual_score"))


def _time(value: Any):
    if value is None:
        return None
    try:
        return parse_time(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _verified_model(entry: Mapping[str, Any]) -> tuple[dict[str, float], str, Any] | None:
    prediction = entry.get("prediction")
    metadata = entry.get("metadata")
    result = entry.get("post_match_result")
    if not isinstance(prediction, Mapping) or not isinstance(metadata, Mapping) or not isinstance(result, Mapping):
        return None
    if result.get("status") != "completed" or prediction.get("algo_reconstructed") is True:
        return None
    tip_source = str(prediction.get("tip_source") or "").lower()
    if any(term in tip_source for term in ("reconstruct", "historical", "legacy")):
        return None
    frozen_at = _time(prediction.get("frozen_at"))
    kickoff = _time(metadata.get("commence_time"))
    probabilities = _probabilities(prediction.get("probabilities"))
    outcome = _evaluation_outcome(result, metadata)
    if frozen_at is None or kickoff is None or frozen_at >= kickoff or probabilities is None or outcome is None:
        return None
    return probabilities, outcome, (frozen_at, kickoff)


def _valid_baseline(value: Any, frozen_at, kickoff) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    probabilities = _probabilities(value.get("probabilities"))
    observed_at = _time(value.get("observed_at"))
    source = str(value.get("source") or "").strip()
    lowered_source = source.lower()
    if (
        probabilities is None
        or observed_at is None
        or observed_at > frozen_at
        or observed_at >= kickoff
        or not source
        or lowered_source in {"unknown", "none", "unavailable"}
        or any(term in lowered_source for term in ("reconstruct", "legacy"))
    ):
        return None
    return {"probabilities": probabilities, "source": source}


def _metrics(rows: list[tuple[dict[str, float], str]]) -> dict[str, Any]:
    count = len(rows)
    if not count:
        return {"n": 0, "brier": None, "log_loss": None, "accuracy": None, "calibration": []}

    brier_total = 0.0
    loss_total = 0.0
    correct = 0
    calibration = [[] for _ in CALIBRATION_BINS]
    for probabilities, actual in rows:
        brier_total += sum((probabilities[key] - (key == actual)) ** 2 for key in OUTCOMES)
        loss_total -= math.log(max(EPSILON, probabilities[actual]))
        predicted = max(OUTCOMES, key=lambda key: probabilities[key])
        confidence = probabilities[predicted]
        is_correct = predicted == actual
        correct += int(is_correct)
        for index, (lower, upper, _label) in enumerate(CALIBRATION_BINS):
            if lower <= confidence < upper or (index == len(CALIBRATION_BINS) - 1 and confidence == 1.0):
                calibration[index].append((confidence, is_correct))
                break

    bins = []
    for (_lower, _upper, label), items in zip(CALIBRATION_BINS, calibration):
        if not items:
            continue
        bins.append({
            "range": label,
            "count": len(items),
            "mean_confidence": round(sum(confidence for confidence, _ in items) / len(items), 6),
            "observed_accuracy": round(sum(int(hit) for _, hit in items) / len(items), 6),
        })
    return {
        "n": count,
        "brier": round(brier_total / count, 6),
        "log_loss": round(loss_total / count, 6),
        "accuracy": round(correct / count, 6),
        "calibration": bins,
    }


def compare_models(archive: Mapping[str, Any] | None, competition=None) -> dict[str, Any]:
    """Return all three scores on the exact same verifiable frozen sample."""
    comp = get_competition(competition)
    entries = archive.values() if isinstance(archive, Mapping) else ()
    total_completed = 0
    verified = 0
    paired_rows = {key: [] for key, _label in MODEL_ROWS}

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        post_match = entry.get("post_match_result")
        if not isinstance(post_match, Mapping) or post_match.get("status") != "completed":
            continue
        total_completed += 1
        model_sample = _verified_model(entry)
        if model_sample is None:
            continue
        verified += 1
        model_probs, actual, (frozen_at, kickoff) = model_sample
        prediction = entry["prediction"]
        baselines = prediction.get("evaluation_baselines")
        baselines = baselines if isinstance(baselines, Mapping) else {}
        bookmaker = _valid_baseline(baselines.get("bookmaker"), frozen_at, kickoff)
        elo = _valid_baseline(baselines.get("elo"), frozen_at, kickoff)
        if bookmaker is None or elo is None:
            continue
        paired_rows["model"].append((model_probs, actual))
        paired_rows["bookmaker"].append((bookmaker["probabilities"], actual))
        paired_rows["elo"].append((elo["probabilities"], actual))

    paired = len(paired_rows["model"])
    return {
        "competition": comp.id,
        "counts": {
            "total_completed": total_completed,
            "verified_model": verified,
            "paired": paired,
            "missing_baselines": verified - paired,
            "excluded": total_completed - verified,
        },
        "models": [
            {"id": key, "label": label, **_metrics(paired_rows[key])}
            for key, label in MODEL_ROWS
        ],
    }


def _trusted_elo_snapshot(service, math_engine, fixture, rating_document, current, kickoff, competition):
    """Build Elo from the cached ratings only when their observation is verifiable."""
    if not isinstance(rating_document, Mapping):
        return None
    provenance = rating_document.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    source = rating_document.get("source") or provenance.get("source")
    observed_at = rating_document.get("observed_at") or provenance.get("observed_at")
    observed = _time(observed_at)
    if not source or observed is None or observed > current or observed >= kickoff:
        return None
    rows = rating_document.get("rows")
    if not isinstance(rows, list):
        return None
    ratings = {
        str(row.get("team_name") or row.get("team")): row.get("elo_rating", row.get("elo"))
        for row in rows if isinstance(row, Mapping)
    }
    teams = [
        TEAM_MAPPING.get(str(fixture.get(key) or ""), str(fixture.get(key) or ""))
        for key in ("home_team", "away_team")
    ]
    try:
        cached_values = [float(ratings[team]) for team in teams]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in cached_values):
        return None
    try:
        from src.routes.matches import build_elo_snapshot

        elo = build_elo_snapshot(
            math_engine,
            str(fixture.get("home_team") or ""),
            str(fixture.get("away_team") or ""),
            competition,
            dict(rating_document),
        )
    except Exception:
        return None
    if not isinstance(elo, Mapping) or _safe_elo_values(elo) is None:
        return None
    # Preserve the exact ratings' provenance rather than deriving a clock from
    # fixture time or from the current maintenance invocation.
    return {**dict(elo), "source": source, "observed_at": observed.isoformat()}


def _safe_elo_values(value: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        home = float(value["home_rating"])
        away = float(value["away_rating"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(home) and math.isfinite(away)):
        return None
    return home, away


def freeze_due_comparisons(service, cache_collection, archive_collection, competition=None, now=None) -> int:
    """Freeze eligible cached fixtures once during the T-15-to-kickoff window.

    This maintenance-only path does not call sports providers. It uses the
    persisted fixture, ratings, and eligible odds snapshot and skips aliases
    whose archive ID differs from the odds-snapshot event ID.
    """
    if service is None or cache_collection is None or archive_collection is None:
        return 0
    comp = get_competition(competition)
    cache_collection = collection_for(cache_collection, comp)
    archive_collection = collection_for(archive_collection, comp)
    current = _time(now or datetime.now(timezone.utc))
    if current is None:
        return 0
    fixtures_document = find_competition_document(cache_collection, comp, "matches_cache") or {}
    fixtures = fixtures_document.get("data")
    if not isinstance(fixtures, list):
        return 0
    due_fixtures = []
    for fixture in fixtures:
        try:
            if not isinstance(fixture, Mapping) or fixture.get("completed") is True:
                continue
            match_id = str(fixture.get("id") or fixture.get("event_id") or "").strip()
            raw_match = fixture.get("raw_match")
            raw_match = raw_match if isinstance(raw_match, Mapping) else {}
            kickoff = _time(fixture.get("commence_time") or raw_match.get("commence_time"))
            status = str(fixture.get("status") or "").lower()
            if (
                match_id
                and kickoff
                and kickoff - timedelta(minutes=15) <= current < kickoff
                and status not in {"complete", "completed", "final", "in progress", "live"}
            ):
                due_fixtures.append(fixture)
        except Exception:
            continue
    if not due_fixtures:
        return 0
    fixtures = due_fixtures
    ratings = (
        find_competition_document(cache_collection, comp, "clubelo_ratings")
        or find_competition_document(cache_collection, comp, "elo_ratings")
    )

    try:
        from src.services.archive import invalidate_archive_mem_cache
        from src.services.prediction import _all_snapshots, _safe_odds, freeze_prediction
        from src.services.archive import build_archive_id_index, resolve_archive_id

        # Avoid creating a second archive fixture when provider IDs differ.
        archive = {
            str(doc["_id"]): {key: value for key, value in doc.items() if key != "_id"}
            for doc in archive_collection.find()
            if isinstance(doc, Mapping) and doc.get("_id") is not None
        }
        archive_index = build_archive_id_index(archive)
    except Exception:
        return 0

    frozen_count = 0
    wrote_archive = False
    for fixture in fixtures:
        try:
            if not isinstance(fixture, Mapping) or fixture.get("completed") is True:
                continue
            match_id = str(fixture.get("id") or fixture.get("event_id") or "").strip()
            kickoff_value = fixture.get("commence_time") or (fixture.get("raw_match") or {}).get("commence_time")
            kickoff = _time(kickoff_value)
            if not match_id or kickoff is None or not kickoff - timedelta(minutes=15) <= current < kickoff:
                continue
            if str(fixture.get("status") or "").lower() in {"complete", "completed", "final", "in progress", "live"}:
                continue

            aliased_id = resolve_archive_id(
                archive_index,
                str(fixture.get("home_team") or ""),
                str(fixture.get("away_team") or ""),
                str(kickoff_value),
            )
            if aliased_id and str(aliased_id) != match_id:
                continue

            snapshot = select_t15_snapshot(_all_snapshots(cache_collection, match_id, comp), kickoff)
            if not snapshot or _safe_odds(snapshot) is None:
                continue

            elo_state = _trusted_elo_snapshot(service, service.math_engine, fixture, ratings, current, kickoff, comp)
            entry = archive_collection.find_one({"_id": match_id})
            if entry is None:
                metadata = {
                    key: fixture.get(key)
                    for key in (
                        "home_team", "away_team", "round", "is_ko_phase", "stage", "tie_id", "leg",
                        "first_leg_score", "extra_time_eligible", "score_90", "score_aet", "shootout_winner",
                    )
                    if fixture.get(key) is not None
                }
                metadata.update({"competition": comp.id, "commence_time": str(kickoff_value)})
                prematch = {
                    "timestamp_recorded": current.isoformat(),
                    "odds": snapshot.get("odds"),
                    "source": snapshot.get("source"),
                    "observed_at": snapshot.get("observed_at"),
                    "status": snapshot.get("status"),
                }
                if elo_state:
                    prematch["elo_state"] = elo_state
                archive_collection.update_one(
                    {"_id": match_id},
                    {"$setOnInsert": {
                        "competition": comp.id,
                        "metadata": metadata,
                        "pre_match_snapshot": prematch,
                        "prediction": {},
                        "post_match_result": {"status": "pending", "actual_score": None},
                    }},
                    upsert=True,
                )
                entry = archive_collection.find_one({"_id": match_id})
                archive[match_id] = {"metadata": metadata}
                archive_index = build_archive_id_index(archive)
                wrote_archive = True
            if not isinstance(entry, Mapping):
                continue
            prediction = entry.get("prediction") if isinstance(entry.get("prediction"), Mapping) else {}
            result = entry.get("post_match_result") if isinstance(entry.get("post_match_result"), Mapping) else {}
            if prediction.get("frozen_at") or result.get("status") == "completed" or result.get("actual_score"):
                continue
            entry_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
            entry_kickoff = _time(entry_metadata.get("commence_time"))
            if entry_kickoff is None or entry_kickoff != kickoff:
                continue

            prematch = entry.get("pre_match_snapshot")
            if not isinstance(prematch, Mapping):
                prematch = {
                    "timestamp_recorded": current.isoformat(),
                    "odds": snapshot.get("odds"),
                    "source": snapshot.get("source"),
                    "observed_at": snapshot.get("observed_at"),
                    "status": snapshot.get("status"),
                }
                if elo_state:
                    prematch["elo_state"] = elo_state
                result_write = archive_collection.update_one(
                    {"_id": match_id, "pre_match_snapshot": {"$exists": False}, "prediction.frozen_at": {"$exists": False}, "post_match_result.status": {"$ne": "completed"}},
                    {"$set": {"pre_match_snapshot": prematch}},
                    upsert=False,
                )
                if not getattr(result_write, "matched_count", 0):
                    continue
                wrote_archive = True
            elif elo_state and not prematch.get("elo_state"):
                result_write = archive_collection.update_one(
                    {"_id": match_id, "pre_match_snapshot.elo_state": {"$exists": False}, "prediction.frozen_at": {"$exists": False}, "post_match_result.status": {"$ne": "completed"}},
                    {"$set": {"pre_match_snapshot.elo_state": elo_state}},
                    upsert=False,
                )
                if not getattr(result_write, "matched_count", 0):
                    continue
                wrote_archive = True

            before = (archive_collection.find_one({"_id": match_id}) or {}).get("prediction", {})
            was_frozen = bool((before or {}).get("frozen_at"))
            frozen = freeze_prediction(
                cache_collection,
                archive_collection,
                service,
                match_id,
                competition=comp,
                now=current,
            )
            if not was_frozen and (frozen.get("prediction") or {}).get("frozen_at") == current.isoformat():
                frozen_count += 1
                wrote_archive = True
        except Exception:
            # A malformed individual cache fixture must not abort maintenance.
            continue
    if wrote_archive:
        invalidate_archive_mem_cache(archive_collection)
    return frozen_count
