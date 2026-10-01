from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, require_competition
from src.services.archive import load_archive_from_db
from src.services.model_evaluation import compare_models


def init_router(archive_collections):
    router = APIRouter(prefix="/api")

    @router.get("/model-comparison")
    def get_model_comparison(competition: str | None = None):
        comp = require_competition(competition)
        if archive_collections is None:
            raise HTTPException(status_code=503, detail="Archive storage unavailable")
        archive_collection = collection_for(archive_collections, comp)
        archive = load_archive_from_db(archive_collection)
        return compare_models(archive, comp)

    return router
