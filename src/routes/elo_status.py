"""Read-only provenance for the current Elo ratings snapshot."""

from fastapi import APIRouter

from src.competitions import collection_for, find_competition_document, require_competition


def init_router(cache_collections):
    router = APIRouter(prefix="/api")

    @router.get("/elo_ratings_status")
    def get_elo_ratings_status(competition: str | None = None):
        comp = require_competition(competition)
        cache = collection_for(cache_collections, comp)
        doc = None
        if comp.is_club_competition:
            doc = find_competition_document(cache, comp, "clubelo_ratings")
        doc = doc or find_competition_document(cache, comp, "elo_ratings")
        if not doc:
            return {
                "status": "unavailable",
                "source": "clubelo" if comp.is_club_competition else "unknown",
                "observed_at": None,
                "error": "Elo ratings snapshot is unavailable",
                "coverage": None,
            }
        return {
            "status": doc.get("status", "unavailable"),
            "source": doc.get("source", "clubelo" if comp.is_club_competition else "unknown"),
            "observed_at": doc.get("observed_at"),
            "error": doc.get("error"),
            "coverage": doc.get("coverage"),
        }

    return router
