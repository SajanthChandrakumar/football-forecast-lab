import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, competition_document_id, find_competition_document, require_competition
from src.services.monte_carlo import simulate_knockout
from src.services.ucl_simulation import DEFAULT_UCL_RUNS, build_cached_ucl_inputs, simulate_ucl_tournament

logger = logging.getLogger(__name__)

_CACHE_ID = "ko_simulation"
_UCL_CACHE_ID = "ucl_simulation"
_CACHE_TTL = 300  # 5min — Elo ändert sich nur nach einem Sync


def init_router(math_engine, cache_collection):
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
        cache_id = competition_document_id(comp, _UCL_CACHE_ID)
        try:
            cached_result = find_competition_document(cache_store, comp, _UCL_CACHE_ID)
            if (
                cached_result
                and cached_result.get("runs") == runs
                and time.time() - cached_result.get("timestamp", 0) < _CACHE_TTL
            ):
                return cached_result["data"]
        except Exception:
            pass
        cached = find_competition_document(cache_store, comp, "matches_cache") or {}
        try:
            inputs = build_cached_ucl_inputs(cached)
            fixtures = inputs["fixtures"]
            teams = inputs.get("teams") or sorted({team for fixture in fixtures for team in (fixture.get("home_team"), fixture.get("away_team")) if team})
            result = simulate_ucl_tournament(
                teams,
                fixtures,
                inputs["score_matrices"],
                n_runs=runs,
                disciplinary_scores=inputs["disciplinary_scores"],
                uefa_coefficients=inputs["uefa_coefficients"],
                uefa_coefficient_ranks=inputs["uefa_coefficient_ranks"],
                official_order=inputs["official_order"],
                coefficient_version=inputs["coefficient_version"],
                coefficient_provenance=inputs["provenance"],
            )
            if result.get("status") != "unavailable":
                try:
                    cache_store.update_one(
                        {"_id": cache_id},
                        {"$set": {"timestamp": time.time(), "runs": runs, "data": result}},
                        upsert=True,
                    )
                except Exception:
                    pass
            return result
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            return {
                "status": "unavailable",
                "source": "ucl_matches_cache",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
                "reason": str(exc),
                "runs": runs,
                "n_runs": runs,
                "seed": 20260908,
            }

    return router
