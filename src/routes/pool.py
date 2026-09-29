"""Manual opponent-field context for pool-aware predictions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, competition_document_id, find_competition_document, require_competition
from src.services.input_validation import bounded_match_id, bounded_tip_counts


def _integer(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value > 0 if positive else value >= 0


def init_router(cache_collections, archive_collections=None):
    router = APIRouter(prefix="/api")

    def stores(competition):
        comp = require_competition(competition)
        return comp, collection_for(cache_collections, comp), (
            collection_for(archive_collections, comp) if archive_collections is not None else None
        )

    @router.get("/pool-context/{match_id}")
    def get_pool_context(match_id: str, competition: str | None = None):
        comp, cache, _ = stores(competition)
        document = cache.find_one({"_id": competition_document_id(comp, f"pool_context:{match_id}")}) or {}
        return {
            "match_id": match_id,
            "competition": comp.id,
            "user_points": document.get("user_points", 0),
            "leader_points": document.get("leader_points", 0),
            "remaining_srf_max_points": document.get("remaining_srf_max_points", 1),
            "tip_counts": document.get("tip_counts", {}),
            "pool_tip": document.get("pool_tip"),
            "pool_status": document.get("pool_status", "unavailable"),
        }

    @router.put("/pool-context/{match_id}")
    def put_pool_context(match_id: str, payload: dict, competition: str | None = None):
        try:
            match_id = bounded_match_id(match_id)
            tip_counts = bounded_tip_counts(payload.get("tip_counts", {}))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        comp, cache, archive = stores(competition or payload.get("competition"))
        values = {
            "user_points": payload.get("user_points", 0),
            "leader_points": payload.get("leader_points", 0),
            "remaining_srf_max_points": payload.get("remaining_srf_max_points", 1),
        }
        if not _integer(values["user_points"]) or not _integer(values["leader_points"]):
            raise HTTPException(status_code=400, detail="user_points and leader_points must be nonnegative integers")
        if not _integer(values["remaining_srf_max_points"], positive=True):
            raise HTTPException(status_code=400, detail="remaining_srf_max_points must be a positive integer")
        # The prediction service deliberately treats malformed/empty field
        # counts as pool-unavailable; they must not invalidate model output.
        context_id = competition_document_id(comp, f"pool_context:{match_id}")
        document = {
            "_id": context_id,
            "competition": comp.id,
            "match_id": match_id,
            **values,
            "tip_counts": tip_counts,
            "pool_tip": None,
            "pool_status": "unavailable",
        }
        if archive is not None:
            archived = archive.find_one({"_id": match_id}) or {}
            stored_prediction = archived.get("prediction") or {}
            if stored_prediction:
                archive.update_one(
                    {"_id": match_id},
                    {"$set": {
                        "prediction.pool_tip": None,
                        "prediction.pool_status": "unavailable",
                        "prediction.pool_lambda": None,
                        "prediction.pool_score": None,
                    }},
                    upsert=False,
                )
        cache.update_one(
            {"_id": context_id},
            {"$set": {key: value for key, value in document.items() if key != "_id"}, "$setOnInsert": {"_id": context_id}},
            upsert=True,
        )
        return {key: document[key] for key in ("match_id", "competition", "user_points", "leader_points", "remaining_srf_max_points", "tip_counts", "pool_tip", "pool_status")}

    return router
