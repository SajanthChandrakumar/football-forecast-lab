"""Read-only competition-scoped forecast evaluation endpoint."""

from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, require_competition
from src.services.model_evaluation import evaluate_archive


def init_router(archive_collections):
    router = APIRouter(prefix="/api")

    @router.get("/model-evaluation")
    def model_evaluation(competition: str | None = None):
        comp = require_competition(competition)
        try:
            archive = list(collection_for(archive_collections, comp).find({}))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Model evaluation storage unavailable") from exc
        return evaluate_archive(archive, competition=comp)

    return router
