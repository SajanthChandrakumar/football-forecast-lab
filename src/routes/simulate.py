import hashlib
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from math import isfinite
from threading import BoundedSemaphore

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.competitions import collection_for, competition_document_id, find_competition_document, require_competition
from src.constants import TEAM_MAPPING
from src.services.monte_carlo import simulate_knockout
from src.services.prediction import CLUB_MODEL_VERSION
from src.services.source_freshness import source_status
from src.services.ucl_simulation import (
    DEFAULT_UCL_RUNS,
    MissingModelInput,
    build_cached_ucl_inputs,
    build_club_pair_score_matrices,
    has_known_knockout_result,
    resolve_uefa_tiebreak_inputs,
    simulate_ucl_tournament,
    validate_ucl_schedule,
)

logger = logging.getLogger(__name__)

_CACHE_ID = "ko_simulation"
_UCL_CACHE_ID = "ucl_simulation"
_CACHE_TTL = 300  # 5min — Elo ändert sich nur nach einem Sync
_UCL_LEASE_SECONDS = 930
_UCL_MAX_RUNTIME_SECONDS = 900
_UCL_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ucl-simulation")
_UCL_SLOTS = BoundedSemaphore(2)


def init_router(math_engine, cache_collection, *, ucl_executor=None):
    router = APIRouter(prefix="/api")

    @router.get("/simulate_knockout")
    def get_knockout_simulation(
        runs: int | None = None,
        force: bool = False,
        competition: str | None = None,
    ):
        comp = require_competition(competition)
        if comp.id == "ucl2026":
            runs = max(DEFAULT_UCL_RUNS, min(runs if runs is not None else DEFAULT_UCL_RUNS, 100_000))
            return get_ucl_simulation(runs=runs, competition=comp.id)
        if comp.id != "wc2026":
            raise HTTPException(status_code=400, detail=f"Knockout simulation is unavailable for {comp.short_name}")
        runs = max(1_000, min(runs if runs is not None else 20_000, 100_000))
        cache_store = collection_for(cache_collection, comp)
        cache_id = competition_document_id(comp, _CACHE_ID)

        if not force:
            try:
                cached = find_competition_document(cache_store, comp, _CACHE_ID)
                if cached and cached.get("runs") == runs and time.time() - cached.get("timestamp", 0) < _CACHE_TTL:
                    return cached["data"]
            except Exception:
                pass

        math_engine.reload_elo_data()
        elo_df = math_engine.elo_df
        ratings = dict(zip(elo_df["team_name"], elo_df["elo_rating"]))

        try:
            result = simulate_knockout(ratings, n_runs=runs)
        except Exception as e:
            logger.error(f"Monte-Carlo-Simulation fehlgeschlagen: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Simulation fehlgeschlagen")

        try:
            cache_store.update_one(
                {"_id": cache_id},
                {"$set": {"timestamp": time.time(), "runs": runs, "data": result}},
                upsert=True,
            )
        except Exception:
            pass

        return result

    @router.get("/simulate_ucl")
    def get_ucl_simulation(
        runs: int = DEFAULT_UCL_RUNS,
        competition: str | None = None,
    ):
        """Run the local UCL simulation from the cache-only fixture snapshot."""
        comp = require_competition(competition)
        if comp.id != "ucl2026":
            raise HTTPException(status_code=400, detail="simulate_ucl requires competition=ucl2026")
        runs = max(DEFAULT_UCL_RUNS, min(runs, 100_000))
        cache_store = collection_for(cache_collection, comp)
        cached = find_competition_document(cache_store, comp, "matches_cache") or {}
        try:
            rating_document = (
                find_competition_document(cache_store, comp, "clubelo_ratings")
                or find_competition_document(cache_store, comp, "elo_ratings")
                or {}
            )
            if rating_document.get("source") != "clubelo":
                return _ucl_unavailable(runs, "verified ClubElo ratings are unavailable")
            status = source_status(rating_document.get("status"), rating_document.get("observed_at"))
            if status in {"failed", "unavailable"}:
                return _ucl_unavailable(runs, rating_document.get("error") or f"ClubElo ratings are {status}", status=status)
            observed_at = rating_document.get("observed_at")
            rows = rating_document.get("rows")
            if not isinstance(rows, list) or not observed_at:
                return _ucl_unavailable(runs, "verified ClubElo ratings are unavailable")
            ratings = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = row.get("team") or row.get("team_name")
                value = row.get("elo_rating", row.get("elo"))
                if not name or isinstance(value, bool):
                    continue
                try:
                    rating = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if isfinite(rating):
                    ratings[TEAM_MAPPING.get(str(name), str(name))] = rating

            inputs = build_cached_ucl_inputs(cached, rating_observed_at=observed_at)
            fixtures = inputs["fixtures"]
            if has_known_knockout_result(fixtures):
                return _ucl_unavailable(runs, "known knockout results require verified draw and leg metadata")
            teams = inputs.get("teams") or sorted({team for fixture in fixtures for team in (fixture.get("home_team"), fixture.get("away_team")) if team})
            validate_ucl_schedule(teams, fixtures)
            resolve_uefa_tiebreak_inputs(
                teams,
                inputs["uefa_coefficients"],
                inputs["uefa_coefficient_ranks"],
                coefficient_version=inputs["coefficient_version"],
            )
            missing = sorted(set(TEAM_MAPPING.get(str(team), str(team)) for team in teams) - set(ratings))
            if missing:
                return _ucl_unavailable(runs, f"verified ClubElo rating unavailable for: {', '.join(missing)}")
            snapshot = {
                "model_version": CLUB_MODEL_VERSION,
                "runs": runs,
                "rating_status": status,
                "rating_observed_at": observed_at,
                "ratings": ratings,
                "fixtures": fixtures,
                "score_matrices": sorted([[repr(key), value] for key, value in inputs["score_matrices"].items()], key=lambda item: item[0]),
                "disciplinary_scores": inputs["disciplinary_scores"],
                "uefa_coefficients": inputs["uefa_coefficients"],
                "uefa_coefficient_ranks": inputs["uefa_coefficient_ranks"],
                "official_order": inputs["official_order"],
                "coefficient_version": inputs["coefficient_version"],
                "coefficient_provenance": inputs["provenance"],
            }
            snapshot_hash = hashlib.sha256(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
            cache_key = f"{CLUB_MODEL_VERSION}:{snapshot_hash}:{runs}"
            cache_id = competition_document_id(comp, f"{_UCL_CACHE_ID}:{CLUB_MODEL_VERSION}:{runs}:{snapshot_hash}")
            cached_job = cache_store.find_one({"_id": cache_id}) if hasattr(cache_store, "find_one") else None
            if isinstance(cached_job, dict) and cached_job.get("data") is not None and cached_job.get("status") in {"completed", "unavailable"}:
                return cached_job["data"]
            if (
                isinstance(cached_job, dict)
                and cached_job.get("status") == "failed"
                and cached_job.get("data") is not None
                and not cached_job.get("failure_reported")
            ):
                try:
                    cache_store.update_one(
                        {"_id": cache_id, "status": "failed"},
                        {"$set": {"failure_reported": True}},
                    )
                except Exception:
                    pass
                return cached_job["data"]
            now = time.time()
            if (
                isinstance(cached_job, dict)
                and cached_job.get("status") == "processing"
                and cached_job.get("lease_until", 0) > now
            ):
                return _ucl_processing(runs)
            use_global_slot = ucl_executor is None
            if use_global_slot and not _UCL_SLOTS.acquire(blocking=False):
                return _ucl_processing(runs)
            try:
                cache_store.update_one(
                    {"_id": cache_id},
                    {"$setOnInsert": {"_id": cache_id, "cache_key": cache_key, "status": "queued", "created_at": now}},
                    upsert=True,
                )
                owner = uuid.uuid4().hex
                claimed = cache_store.update_one(
                    {"_id": cache_id, "$or": [{"status": {"$ne": "processing"}}, {"lease_until": {"$lte": now}}]},
                    {"$set": {
                        "cache_key": cache_key, "status": "processing", "lease_owner": owner,
                        "lease_until": now + _UCL_LEASE_SECONDS, "model_version": CLUB_MODEL_VERSION,
                        "input_snapshot_hash": snapshot_hash, "runs": runs, "n_runs": runs,
                        "failure_reported": False, "updated_at": now,
                    }},
                )
            except Exception as exc:
                if use_global_slot:
                    _UCL_SLOTS.release()
                logger.error("Could not claim UCL simulation job: %s", exc, exc_info=True)
                return _ucl_failed(runs, "simulation job could not be queued")
            matched_count = getattr(claimed, "matched_count", None)
            if matched_count == 0:
                if use_global_slot:
                    _UCL_SLOTS.release()
                return _ucl_processing(runs)
            if matched_count is None:
                claimed_document = cache_store.find_one({"_id": cache_id}) if hasattr(cache_store, "find_one") else None
                if not isinstance(claimed_document, dict) or claimed_document.get("lease_owner") != owner:
                    if use_global_slot:
                        _UCL_SLOTS.release()
                    return _ucl_processing(runs)

            executor = ucl_executor or _UCL_EXECUTOR
            job_args = (cache_store, cache_id, owner, math_engine, teams, fixtures, inputs, ratings, runs, status, observed_at, snapshot_hash)
            try:
                executor.submit(_run_ucl_job_with_slot if use_global_slot else _run_ucl_job, *job_args)
            except Exception as exc:
                if use_global_slot:
                    _UCL_SLOTS.release()
                logger.error("Could not submit UCL simulation job: %s", exc, exc_info=True)
                _store_ucl_job_result(cache_store, cache_id, owner, _ucl_failed(runs, "simulation worker could not be started"), status="failed")
                return _ucl_failed(runs, "simulation worker could not be started")
            return _ucl_processing(runs)
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            return _ucl_unavailable(runs, str(exc))

    return router


def _ucl_processing(runs: int) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        headers={"Retry-After": "3"},
        content={"status": "processing", "n_runs": runs, "model_version": CLUB_MODEL_VERSION, "retry_after": 3},
    )


def _ucl_unavailable(runs: int, reason: str, *, status: str = "unavailable") -> dict:
    return {
        "status": status,
        "source": "ucl_matches_cache",
        "model_version": CLUB_MODEL_VERSION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "error": reason,
        "reason": reason,
        "runs": runs,
        "n_runs": runs,
    }


def _ucl_failed(runs: int, reason: str) -> dict:
    return _ucl_unavailable(runs, reason, status="failed")


def _store_ucl_job_result(cache_store, cache_id, owner: str, result: dict, *, status: str) -> None:
    try:
        cache_store.update_one(
            {"_id": cache_id, "lease_owner": owner},
            {"$set": {"status": status, "data": result, "timestamp": time.time(), "updated_at": time.time(), "failure_reported": False}, "$unset": {"lease_owner": "", "lease_until": ""}},
        )
    except Exception:
        logger.error("Could not save UCL simulation result", exc_info=True)


def _run_ucl_job(cache_store, cache_id, owner, math_engine, teams, fixtures, inputs, ratings, runs, rating_status, rating_observed_at, snapshot_hash):
    try:
        pair_matrices = build_club_pair_score_matrices(teams, ratings, math_engine)
        pair_matrices.update(inputs["score_matrices"])
        result = simulate_ucl_tournament(
            teams,
            fixtures,
            pair_matrices,
            n_runs=runs,
            disciplinary_scores=inputs["disciplinary_scores"],
            uefa_coefficients=inputs["uefa_coefficients"],
            uefa_coefficient_ranks=inputs["uefa_coefficient_ranks"],
            official_order=inputs["official_order"],
            coefficient_version=inputs["coefficient_version"],
            coefficient_provenance=inputs["provenance"],
            max_duration_seconds=_UCL_MAX_RUNTIME_SECONDS,
        )
        result.update({
            "model_version": CLUB_MODEL_VERSION,
            "input_snapshot_hash": snapshot_hash,
            "rating_source": "clubelo",
            "rating_status": rating_status,
            "rating_observed_at": rating_observed_at,
        })
        if rating_status == "stale":
            result.setdefault("warnings", []).append("ClubElo ratings are stale")
        reason = str(result.get("reason", result.get("error", ""))).lower()
        if result.get("status") == "unavailable" and "bounded runtime" in reason:
            result["status"] = "failed"
            status = "failed"
        else:
            status = "completed" if result.get("status") != "unavailable" else "unavailable"
    except Exception as exc:
        logger.error("UCL simulation failed: %s", exc, exc_info=True)
        result = _ucl_failed(runs, str(exc))
        result.update({"input_snapshot_hash": snapshot_hash, "rating_status": rating_status, "rating_observed_at": rating_observed_at})
        status = "failed"
    _store_ucl_job_result(cache_store, cache_id, owner, result, status=status)


def _run_ucl_job_with_slot(*args) -> None:
    try:
        _run_ucl_job(*args)
    finally:
        _UCL_SLOTS.release()
