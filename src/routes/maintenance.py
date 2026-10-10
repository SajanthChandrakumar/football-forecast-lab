"""Authenticated scheduler entry point for provider maintenance."""

from __future__ import annotations

import os
import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from src.competitions import require_competition
from src.services import espn_data
from src.services.auth import require_cron_secret
from src.services.maintenance import run_maintenance
from src.services.ucl_providers import ingest_clubelo


def init_router(cache_collections, odds_provider, *, archive_collections=None, math_engine=None, team_form_service=None, match_intelligence_refresher=None, cron_secret: str | None = None, admin_refresh_token: str | None = None, now_fn=None):
    router = APIRouter(prefix="/api/internal")
    configured_secret = cron_secret if cron_secret is not None else os.getenv("CRON_SECRET", "")

    @router.post("/maintenance")
    def maintenance(request: Request, competition: str | None = None, force: bool = False):
        require_cron_secret(request, configured_secret)
        comp = require_competition(competition)
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
            team_form_service=(team_form_service.get(comp.id) if isinstance(team_form_service, dict) else team_form_service),
            standings_fetcher=(espn_data.get_standings_groups if comp.id == "epl2026" else None),
            match_intelligence_refresher=match_intelligence_refresher,
        )

    @router.post("/manual-refresh")
    def manual_refresh(request: Request, competition: str | None = None):
        token = admin_refresh_token if admin_refresh_token is not None else os.getenv("ADMIN_REFRESH_TOKEN", "")
        if not token:
            raise HTTPException(status_code=503, detail="API-Aktualisierung ist noch nicht eingerichtet.")
        presented = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not request.headers.get("authorization", "").startswith("Bearer ") or not hmac.compare_digest(presented.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="Admin-Schlüssel ist ungültig.")
        comp = require_competition(competition)
        if not comp.is_club_competition:
            raise HTTPException(status_code=422, detail="Der Sofortabruf ist für Premier League und UCL verfügbar.")
        current = now_fn() if now_fn else datetime.now(timezone.utc)
        try:
            result = run_maintenance(
                cache_collections, odds_provider, archive_collections=archive_collections,
                competition=comp.id, manual=True, now=current if now_fn else None,
                fixture_fetcher=espn_data.get_scoreboard, clubelo_ingestor=ingest_clubelo,
                math_engine=math_engine,
                team_form_service=team_form_service.get(comp.id) if isinstance(team_form_service, dict) else team_form_service,
                standings_fetcher=espn_data.get_standings_groups if comp.id == "epl2026" else None,
                match_intelligence_refresher=match_intelligence_refresher,
            )
        except Exception:
            # Provider exception strings can contain URLs with API credentials.
            raise HTTPException(status_code=503, detail="Aktualisierung fehlgeschlagen. Gespeicherte Daten bleiben erhalten.") from None
        if result.get("reason") in {"cooldown", "lease_held"}:
            retry_after = result.get("retry_after", 60)
            raise HTTPException(status_code=429, detail="Bitte warte kurz vor dem nächsten Abruf.",
                                headers={"Retry-After": str(retry_after)})
        sources = []
        def source(source_id, label, value):
            value = value or {}
            status = value.get("status", "unavailable")
            sources.append({"id": source_id, "label": label, "status": status,
                            "observed_at": None if status == "failed" else (
                                (value.get("provenance") or {}).get("observed_at") or value.get("observed_at")
                            ),
                            "message": "Abruf fehlgeschlagen; letzter gespeicherter Stand bleibt erhalten." if status in {"failed", "stale"} else None})
        source("fixtures", "Spiele & Ergebnisse", result.get("fixture_status"))
        source("elo", "Elo-Werte", result.get("clubelo_status"))
        if comp.id == "epl2026":
            source("standings", "Tabelle", result.get("standings_status"))
        odds = result.get("odds_status") or {"status": "failed" if result.get("source") == "odds_api" else "unavailable"}
        source("odds", "Buchmacherquoten", odds)
        if result.get("reason") == "provider_budget_blocked":
            sources[-1]["message"] = "API-Budget erreicht; letzter gespeicherter Stand bleibt erhalten."
        intelligence = result.get("match_intelligence_status") or {}
        checked = intelligence.get("espn_calls", 0)
        confirmed = intelligence.get("confirmed", 0)
        failed = intelligence.get("failed_calls", 0)
        lineup_status = (
            "fresh" if checked and confirmed == checked else "partial" if confirmed
            else "failed" if (checked and failed == checked) or intelligence.get("status") == "failed"
            else "unavailable"
        )
        source("lineups", "Aufstellungen", {"status": lineup_status, "observed_at": intelligence.get("observed_at")})
        if lineup_status != "failed":
            sources[-1]["message"] = f"{confirmed} von {checked} geprüften Spielen mit vollständiger Aufstellung." if checked else "Kein Spiel im Abruffenster oder keine Aufstellung erfasst."
        successful = sum(item["status"] == "fresh" for item in sources)
        return {"competition": comp.id, "status": "success" if successful == len(sources) else "partial" if successful else "failed",
                "requested_at": current.isoformat(), "sources": sources, "cooldown_seconds": 60}

    return router
