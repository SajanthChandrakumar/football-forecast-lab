import logging

from fastapi import APIRouter, Request, HTTPException
from src.services.input_validation import bounded_match_id

from src.constants import TOTALS_CACHE_TTL
from src.competitions import collection_for, find_competition_document, require_competition
from src.services.odds_helpers import extract_odds, fetch_or_cache_totals
from src.services.prediction import PredictionService, freeze_prediction

logger = logging.getLogger(__name__)


def effective_is_ko(competition, payload: dict, match_data: dict) -> bool:
    """Resolve KO scoring without letting new competitions trust client flags."""
    comp = require_competition(competition)
    if comp.id == "wc2026":
        return bool(payload.get("is_ko", False))

    # UCL match context is provider/archive metadata. Keep the accepted
    # field explicit; stage/leg resolution is owned by the central predictor.
    for source in (
        match_data,
        match_data.get("match_context"),
        match_data.get("metadata"),
        match_data.get("raw_match"),
    ):
        if isinstance(source, dict) and "extra_time_eligible" in source:
            return bool(source["extra_time_eligible"])
    return False


def init_router(math_engine, odds_engine, cache_collection, limiter, archive_collection=None):
    router = APIRouter(prefix="/api")
    prediction_service = PredictionService(math_engine)

    @router.post("/predict")
    @limiter.limit("20/minute")
    def predict_match(request: Request, payload: dict, competition: str | None = None):
        comp = require_competition(competition or payload.get("competition"))
        cache_store = collection_for(cache_collection, comp)
        math_engine.reload_elo_data()
        match_data = payload.get("match")

        if not match_data:
            raise HTTPException(status_code=400, detail="Match data required")

        is_ko = effective_is_ko(comp, payload, match_data)

        try:
            event_id = match_data.get("id", "")
            # Totals already ride along in raw_match.bookmakers from /api/matches
            # (Odds API h2h+totals or ESPN). Only serve from cache — never fire a
            # live per-event call keyed by an ESPN/archive id the Odds API won't know.
            match_data = fetch_or_cache_totals(
                event_id,
                match_data,
                odds_engine,
                cache_store,
                TOTALS_CACHE_TTL,
                fetch_if_missing=False,
                competition=comp,
            )

            cached = find_competition_document(cache_store, comp, "matches_cache")
            cached_match = next(
                (match for match in (cached or {}).get("data", []) if match.get("id") == event_id),
                {},
            )
            try:
                odds = extract_odds(match_data)
            except ValueError:
                # ESPN-sourced raw_match entries carry no bookmakers — fall back
                # to the aggregated odds stored alongside the match in the cache.
                odds = None
                if cached_match.get("odds", {}).get("home"):
                    odds = cached_match["odds"]

            elo_state = None
            try:
                from src.routes.matches import build_elo_snapshot
                elo_document = find_competition_document(cache_store, comp, "elo_ratings")
                elo_state = build_elo_snapshot(
                    math_engine,
                    match_data.get("home_team"),
                    match_data.get("away_team"),
                    comp,
                    elo_document,
                )
            except Exception:
                elo_state = None
            context = dict(match_data.get("match_context") or match_data.get("metadata") or {})
            context.update({
                key: payload[key]
                for key in (
                    "stage", "tie_id", "leg", "first_leg_score", "score_90", "score_aet",
                    "shootout_winner", "extra_time_eligible",
                )
                if key in payload
            })
            context.setdefault("commence_time", match_data.get("commence_time") or (match_data.get("raw_match") or {}).get("commence_time"))
            if comp.id == "wc2026":
                context.setdefault("is_ko", is_ko)
            pool_context = find_competition_document(cache_store, comp, f"pool_context:{event_id}") or {}
            field_counts = payload.get("tip_counts") or payload.get("field_tip_counts")
            if field_counts is None:
                field_counts = pool_context.get("tip_counts")
            odds_observed_at = cached_match.get("odds_observed_at") or match_data.get("odds_observed_at")
            odds_input = ({
                "odds": odds,
                "status": cached_match.get("odds_status") or match_data.get("odds_status") or ("fresh" if odds_observed_at else "stale"),
                "source": "odds_api",
                "observed_at": odds_observed_at,
                "provenance": cached_match.get("odds_provenance") or match_data.get("odds_provenance") or {},
            } if odds else None)
            result = prediction_service.predict(
                odds=odds_input,
                elo=elo_state,
                competition=comp,
                context=context,
                field_counts=field_counts,
                user_points=payload.get("user_points", pool_context.get("user_points", 0)),
                leader_points=payload.get("leader_points", pool_context.get("leader_points", 0)),
                remaining_srf_max_points=payload.get("remaining_srf_max_points", pool_context.get("remaining_srf_max_points", 1)),
                observed_at=odds_observed_at,
            )
            if odds and not odds_observed_at:
                result["observed_at"] = None
            matrix = result.pop("score_matrix_df", None)
            result["max_prob"] = float(matrix.to_numpy().max()) if matrix is not None else 0.0
            return result
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An error occurred processing your request")

    @router.post("/predict/freeze")
    @router.post("/freeze")
    def freeze_match(payload: dict, competition: str | None = None):
        comp = require_competition(competition or payload.get("competition"))
        if archive_collection is None:
            raise HTTPException(status_code=503, detail="Archive storage unavailable")
        archive_store = collection_for(archive_collection, comp)
        cache_store = collection_for(cache_collection, comp)
        match_id = payload.get("match_id")
        if not match_id:
            raise HTTPException(status_code=400, detail="match_id required")
        try:
            match_id = bounded_match_id(match_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            return freeze_prediction(
                cache_store,
                archive_store,
                prediction_service,
                str(match_id),
                competition=comp,
                field_counts=payload.get("tip_counts") or payload.get("field_tip_counts"),
                user_points=payload.get("user_points", 0),
                leader_points=payload.get("leader_points", 0),
                remaining_srf_max_points=payload.get("remaining_srf_max_points", 1),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
