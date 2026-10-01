"""Read-only historical bookmaker odds for a match."""

from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, require_competition
from src.services.input_validation import bounded_match_id
from src.services.odds_history import get_odds_history


def init_router(cache_collections, archive_collections=None):
    router = APIRouter(prefix="/api")

    @router.get("/odds-history/{match_id}")
    def get_match_odds_history(match_id: str, competition: str | None = None):
        try:
            match_id = bounded_match_id(match_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        comp = require_competition(competition)
        cache = collection_for(cache_collections, comp)
        archive = collection_for(archive_collections, comp) if archive_collections is not None else None
        return get_odds_history(
            cache,
            match_id,
            competition=comp,
            archive_collection=archive,
        )

    return router
