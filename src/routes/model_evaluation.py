from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, require_competition, find_competition_document
from src.services.archive import load_archive_from_db
from src.services.model_evaluation import compare_models
from src.services.forecast_evaluation import evaluate_archive


def init_router(archive_collections, *, cache_collections=None):
    router = APIRouter(prefix="/api")

    @router.get("/model-comparison")
    def get_model_comparison(competition: str | None = None):
        comp = require_competition(competition)
        if archive_collections is None:
            raise HTTPException(status_code=503, detail="Archive storage unavailable")
        archive_collection = collection_for(archive_collections, comp)
        archive = load_archive_from_db(archive_collection)
        return compare_models(archive, comp)

    @router.get("/model-evaluation")
    def model_evaluation(competition: str | None = None):
        comp = require_competition(competition)
        try:
            archive = list(collection_for(archive_collections, comp).find({}))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Model evaluation storage unavailable") from exc
        result = evaluate_archive(archive, competition=comp)
        if cache_collections is not None:
            status = find_competition_document(collection_for(cache_collections, comp), comp, 'forecast_capture_status') or {}
            result['capture_status'] = {key: status.get(key) for key in ('status', 'last_run_at', 'last_successful_at', 'next_capture_at', 'interval_seconds', 'error')}
            if comp.is_club_competition:
                maintenance = find_competition_document(collection_for(cache_collections, comp), comp, 'maintenance_status') or {}
                result['maintenance_status'] = {key: maintenance.get(key) for key in ('status', 'last_run_at', 'last_successful_at', 'next_due_at', 'interval_seconds', 'error')}
        return result

    return router
