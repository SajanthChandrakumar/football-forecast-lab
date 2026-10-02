import logging

from fastapi import APIRouter, Request
from src.math_engine import MathEngine
from src.competitions import (
    collection_for,
    competition_document_id,
    find_competition_document,
    require_competition,
)
from src.services.archive import load_archive_from_db

logger = logging.getLogger(__name__)

_CUSTOM_BOT_ID = "default"


def _clean_bot_params(params: dict) -> dict:
    def clamp(v, lo, hi, default):
        try:
            return max(lo, min(hi, float(v)))
        except (TypeError, ValueError):
            return default
    return {
        "market_weight": clamp(params.get("market_weight"), 0.0, 1.0, 0.7),
        "risk":          clamp(params.get("risk"), -1.0, 1.0, 0.0),
        "draw_bias":     clamp(params.get("draw_bias"), 0.0, 6.0, 0.0),
        "underdog_bias": clamp(params.get("underdog_bias"), 0.0, 6.0, 0.0),
    }


def init_router(math_engine, archive_collection, custom_bot_collection, limiter):
    router = APIRouter(prefix="/api")

    @router.post("/custom_bot/simulate")
    @limiter.limit("60/minute")
    def simulate_custom_bot(request: Request, payload: dict, competition: str | None = None):
        comp = require_competition(competition or payload.get("competition"))
        archive_store = collection_for(archive_collection, comp)
        params = _clean_bot_params(payload.get("params") or {})
        archive = load_archive_from_db(archive_store)
        math_engine.reload_elo_data(archive=archive)

        completed = []
        for mid, match in archive.items():
            pmr = match.get("post_match_result", {})
            if pmr.get("status") != "completed":
                continue
            actual = pmr.get("actual_score")
            snap = match.get("pre_match_snapshot") or {}
            odds = snap.get("odds") or {}
            if not actual or not all(k in odds for k in ("home", "draw", "away")):
                continue
            completed.append((mid, match, snap, odds, actual))

        completed.sort(key=lambda x: x[2].get("timestamp_recorded") or "")

        total = 0
        correct_tendency = 0
        running = 0
        race = []
        breakdown = []
        for mid, match, snap, odds, actual in completed:
            meta = match.get("metadata", {})
            is_ko = meta.get("is_ko_phase", False)
            elo_state = snap.get("elo_state") or {}
            if comp.is_club_competition and not all(key in elo_state for key in ("home_rating", "away_rating")):
                continue
            elo_home = elo_state.get("home_rating", 1500.0)
            elo_away = elo_state.get("away_rating", 1500.0)
            try:
                tip = math_engine.compute_custom_bot_tip(odds, elo_home, elo_away, params, is_ko)
                pts = MathEngine.calculate_actual_points(tip, actual, is_ko)
            except Exception as e:
                logger.error(f"Custom-bot sim failed for {mid}: {e}")
                continue
            total += pts
            if pts >= 5:
                correct_tendency += 1
            running += pts
            label = f"{(meta.get('home_team', '') or '')[:3].upper()}–{(meta.get('away_team', '') or '')[:3].upper()}"
            race.append({"label": label, "cumulative": running})
            breakdown.append({
                "match_id": mid,
                "home_disp": meta.get("home_disp"),
                "away_disp": meta.get("away_disp"),
                "actual": actual,
                "tip": tip,
                "points": pts,
            })

        n = len(breakdown)
        return {
            "params": params,
            "total_points": total,
            "matches": n,
            "tendency_rate": (correct_tendency / n) if n else 0.0,
            "race": race,
            "breakdown": breakdown,
        }

    @router.get("/custom_bot")
    def get_custom_bot(competition: str | None = None):
        comp = require_competition(competition)
        bot_store = collection_for(custom_bot_collection, comp)
        doc = find_competition_document(bot_store, comp, _CUSTOM_BOT_ID)
        if not doc:
            return {"exists": False}
        return {"exists": True, "name": doc.get("name"), "params": doc.get("params", {})}

    @router.post("/custom_bot")
    @limiter.limit("30/minute")
    def save_custom_bot(request: Request, payload: dict, competition: str | None = None):
        comp = require_competition(competition or payload.get("competition"))
        bot_store = collection_for(custom_bot_collection, comp)
        name = (payload.get("name") or "Mein Bot").strip()[:40] or "Mein Bot"
        params = _clean_bot_params(payload.get("params") or {})
        bot_id = competition_document_id(comp, _CUSTOM_BOT_ID)
        bot_store.replace_one(
            {"_id": bot_id},
            {"_id": bot_id, "name": name, "params": params, "competition": comp.id},
            upsert=True,
        )
        return {"ok": True, "name": name, "params": params}

    return router
