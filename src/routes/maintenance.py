"""Authenticated scheduler entry point for provider maintenance."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from src.competitions import require_competition
from src.services import espn_data
from src.services.auth import require_cron_secret
from src.services.maintenance import run_maintenance
from src.services.ucl_providers import ingest_clubelo


def init_router(cache_collections, odds_provider, *, archive_collections=None, math_engine=None, team_form_service=None, cron_secret: str | None = None, now_fn=None):
    router = APIRouter(prefix="/api/internal")
    configured_secret = cron_secret if cron_secret is not None else os.getenv("CRON_SECRET", "")

    @router.post("/maintenance")
    def maintenance(request: Request, competition: str | None = None, force: bool = False):
        require_cron_secret(request, configured_secret)
        require_competition(competition)
        return run_maintenance(
            cache_collections,
            odds_provider,
            archive_collections=archive_collections,
            competition=competition,
            force=force,
            allow_force_capture=True,
            now=(now_fn() if now_fn else None),
            fixture_fetcher=espn_data.get_scoreboard,
            clubelo_ingestor=ingest_clubelo,
            math_engine=math_engine,
            team_form_service=team_form_service,
        )

    return router
