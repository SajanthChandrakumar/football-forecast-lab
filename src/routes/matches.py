import time
import logging
import math
from datetime import datetime, timezone, timedelta

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.constants import TEAM_MAPPING, DISPLAY_MAPPING, _is_ko_round
from src.competitions import (
    collection_for,
    competition_document_id,
    find_competition_document,
    get_competition,
    require_competition,
)
from src.services.odds_helpers import extract_odds, dynamic_ttl
from src.services.archive import (
    load_archive_from_db, upsert_archive_entry,
    build_archive_id_index, resolve_archive_id, _canon_team,
)
from src.services import espn_data
from src.services.prediction import PredictionService, infer_stage
from src.services.ucl_simulation import _normalised_matrix_dict
from src.math_engine import MathEngine

logger = logging.getLogger(__name__)


def _synth_bookmakers(espn_odds: dict, home_team: str, away_team: str) -> list:
    """Build a single-bookmaker entry (ESPN/DraftKings) in the legacy shape
    extract_odds() expects, used when The Odds API has no match for a fixture."""
    h2h = [
        {"name": home_team, "price": espn_odds["home"]},
        {"name": "Draw", "price": espn_odds["draw"]},
        {"name": away_team, "price": espn_odds["away"]},
    ]
    markets = [{"key": "h2h", "outcomes": h2h}]
    if "over25" in espn_odds and "under25" in espn_odds:
        markets.append({"key": "totals", "outcomes": [
            {"name": "Over", "price": espn_odds["over25"], "point": 2.5},
            {"name": "Under", "price": espn_odds["under25"], "point": 2.5},
        ]})
    return [{"key": "espn_draftkings", "title": "DraftKings (ESPN)", "markets": markets}]


def _build_odds_api_lookup(odds_engine, competition=None) -> dict:
    """Fetch The Odds API once (h2h+totals) → {(canon_home,canon_away,date): bookmakers}.
    Best-effort: returns {} on any failure so ESPN odds are used instead."""
    try:
        if hasattr(odds_engine, "get_competition_odds"):
            games = odds_engine.get_competition_odds(competition, market="h2h,totals")
        else:
            games = odds_engine.get_world_cup_odds(market="h2h,totals")
    except Exception as e:
        print(f"Odds API fetch failed, using ESPN odds only: {e}")
        return {}
    lookup = {}
    for g in games or []:
        h = _canon_team(g.get("home_team", ""))
        a = _canon_team(g.get("away_team", ""))
        date = (g.get("commence_time") or "")[:10]
        if h and a and g.get("bookmakers"):
            lookup[(h, a, date)] = g["bookmakers"]
    return lookup


def _match_odds_api(lookup: dict, home: str, away: str, date: str):
    """Resolve Odds-API bookmakers for a fixture; tolerate ±1 day (UTC edge)."""
    h, a = _canon_team(home), _canon_team(away)
    d = (date or "")[:10]
    if (h, a, d) in lookup:
        return lookup[(h, a, d)]
    try:
        base = datetime.fromisoformat(d)
        for delta in (-1, 1):
            alt = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
            if (h, a, alt) in lookup:
                return lookup[(h, a, alt)]
    except Exception:
        pass
    return None


def build_elo_snapshot(math_engine, home_team: str, away_team: str, competition=None, elo_document: dict | None = None) -> dict | None:
    """Return known ratings, retaining WC's legacy default only for WC."""
    comp = get_competition(competition)
    if elo_document and elo_document.get("rows"):
        ratings = {
            str(row.get("team_name") or row.get("team")): row.get("elo_rating", row.get("elo"))
            for row in elo_document["rows"]
            if isinstance(row, dict)
        }
        names = [TEAM_MAPPING.get(team, team) for team in (home_team, away_team)]
        try:
            snapshot = {"home_rating": float(ratings[names[0]]), "away_rating": float(ratings[names[1]])}
            snapshot.update({
                key: elo_document[key]
                for key in ("status", "source", "observed_at", "provenance")
                if elo_document.get(key) is not None
            })
            return snapshot
        except (KeyError, TypeError, ValueError):
            pass
    frame = getattr(math_engine, "elo_df", None)
    rows = getattr(frame, "loc", None)
    if rows is None:
        return {"home_rating": 1500.0, "away_rating": 1500.0} if comp.id == "wc2026" else None
    values = []
    for team in (home_team, away_team):
        normalized = TEAM_MAPPING.get(team, team)
        try:
            selected = frame.loc[frame["team_name"] == normalized, "elo_rating"]
            values.append(float(selected.values[0]) if not selected.empty else None)
        except (KeyError, IndexError, TypeError, ValueError):
            values.append(None)
    if any(value is None for value in values):
        return {"home_rating": 1500.0, "away_rating": 1500.0} if comp.id == "wc2026" else None
    return {"home_rating": values[0], "away_rating": values[1]}


def _sync_archive_tips(matches, archive, archive_collection):
    """Reconcile dashboard tips with the archive.

    Pending matches: the archive follows the latest recalculation (prediction
    may legitimately shift until kickoff). Completed matches: the archived
    pre-match tip is FROZEN — the dashboard shows it instead of a tip
    recalculated with post-match Elo (that would be hindsight)."""
    changed = {}
    for m in matches:
        mid = m.get("id")
        entry = archive.get(mid)
        if not mid or not entry or not entry.get("prediction"):
            continue

        if entry.get("post_match_result", {}).get("status") == "completed":
            prediction = entry["prediction"]
            snapshot = entry.get("pre_match_snapshot") or {}
            frozen = prediction.get("top_tip") or prediction.get("model_tip")
            if frozen:
                m["top_tip"] = frozen
                m["model_tip"] = prediction.get("model_tip") or frozen
                m["max_xp"] = float(prediction.get("max_xp") or 0)
                for key in ("pool_tip", "pool_status", "source_mode", "status", "source_status", "source", "observed_at"):
                    if key in prediction:
                        m[key] = prediction[key]
                    elif key in snapshot:
                        m[key] = snapshot[key]
                for key in ("input_provenance", "provenance"):
                    value = prediction.get(key) or snapshot.get(key)
                    if value is not None:
                        m[key] = value
                archived_context = prediction.get("context") or snapshot.get("context")
                if not archived_context:
                    metadata = entry.get("metadata") or {}
                    context_keys = {
                        "competition", "stage", "tie_id", "leg", "first_leg_score",
                        "first_leg_home_score", "first_leg_away_score", "score_90",
                        "score_aet", "shootout_winner", "extra_time_eligible", "commence_time",
                    }
                    archived_context = {key: metadata[key] for key in context_keys if key in metadata}
                if archived_context:
                    m["context"] = archived_context
                    m["match_context"] = archived_context
                    for key in ("stage", "tie_id", "leg", "first_leg_score", "score_90", "score_aet", "shootout_winner", "extra_time_eligible"):
                        if key in archived_context:
                            m[key] = archived_context[key]
            continue

        tip = m.get("top_tip")
        if not tip or tip == "N/A":
            continue
        if entry["prediction"].get("top_tip") != tip:
            entry["prediction"]["top_tip"] = tip
            entry["prediction"]["max_xp"] = m.get("max_xp", 0)
            changed[mid] = entry
    for mid, entry in changed.items():
        upsert_archive_entry(archive_collection, mid, entry)
    return matches


def _unavailable_matches(source: str = "matches_cache") -> dict:
    observed_at = datetime.now(timezone.utc).isoformat()
    return {
        "status": "unavailable",
        "source": source,
        "observed_at": observed_at,
        "error": "match cache unavailable; authenticated maintenance has not populated fixtures",
        "data": [],
    }


def _propagate_team_logos(matches):
    """Reuse provider logos across fixtures for the same team without inventing any."""
    known = {}
    for match in matches:
        if not isinstance(match, dict):
            continue
        for side in ("home", "away"):
            team = str(match.get(f"{side}_team") or "")
            logo = match.get(f"{side}_logo")
            if team and isinstance(logo, str) and logo.strip():
                known.setdefault(TEAM_MAPPING.get(team, team), logo)

    presented = []
    for match in matches:
        if not isinstance(match, dict):
            presented.append(match)
            continue
        row = dict(match)
        for side in ("home", "away"):
            if not row.get(f"{side}_logo"):
                team = str(row.get(f"{side}_team") or "")
                logo = known.get(TEAM_MAPPING.get(team, team))
                if logo:
                    row[f"{side}_logo"] = logo
        presented.append(row)
    return presented


def _apply_cached_ucl_forms(matches, team_form_service):
    if team_form_service is None:
        return matches
    presented = []
    for match in matches:
        if not isinstance(match, dict):
            presented.append(match)
            continue
        row = dict(match)
        row["home_form"] = team_form_service.cached_form_for_match(
            row.get("home_team"), row.get("home_team_id")
        )
        row["away_form"] = team_form_service.cached_form_for_match(
            row.get("away_team"), row.get("away_team_id")
        )
        presented.append(row)
    return presented


def _present_cached_matches(
    cached_data, math_engine, odds_engine, competition, archive_store, cache_store,
    team_form_service=None,
):
    """Apply one presentation path to normal and forced cache reads."""
    if not isinstance(cached_data, list) or not cached_data:
        return cached_data if isinstance(cached_data, list) else _unavailable_matches()
    comp = get_competition(competition)
    if comp.id == "ucl2026":
        # Predictions and matrices are persisted by maintenance. Enrich only
        # legacy or incomplete open fixtures; reads do not persist that work.
        needs_enrichment = [
            dict(match) for match in cached_data
            if isinstance(match, dict)
            and not _is_completed_match(match)
            and not _has_complete_ucl_prediction(match)
        ]
    else:
        needs_enrichment = [dict(match) if isinstance(match, dict) else match for match in cached_data]
    presented_data = cached_data
    if needs_enrichment:
        if hasattr(math_engine, "reload_elo_data"):
            math_engine.reload_elo_data()
        enriched = _enrich_edge(needs_enrichment, math_engine, odds_engine, comp, cache_store)
        if comp.id == "ucl2026":
            by_id = {
                str(match.get("id") or match.get("event_id")): match
                for match in enriched
                if isinstance(match, dict) and (match.get("id") or match.get("event_id"))
            }
            presented_data = [
                by_id.get(str(match.get("id") or match.get("event_id")), match)
                if isinstance(match, dict) else match
                for match in cached_data
            ]
        else:
            presented_data = enriched
    presented_data = _propagate_team_logos(presented_data)
    if comp.id == "ucl2026":
        presented_data = _apply_cached_ucl_forms(presented_data, team_form_service)
    archive = load_archive_from_db(archive_store)
    return _sync_archive_tips(
        presented_data,
        archive,
        archive_store,
    )


def _is_completed_match(match):
    post_match = match.get("post_match_result") or {}
    status = str(match.get("status", "")).lower()
    post_status = str(post_match.get("status", "")).lower() if isinstance(post_match, dict) else ""
    return (
        match.get("completed")
        or status in {"completed", "final", "post"}
        or post_status in {"completed", "final", "post"}
        or match.get("actual_score") is not None
        or match.get("score_90") is not None
    )


def _has_complete_ucl_prediction(match):
    if not isinstance(match, dict):
        return False
    probabilities = match.get("probabilities")
    provenance = match.get("input_provenance") or match.get("provenance")
    if not isinstance(probabilities, dict) or not {"home", "draw", "away"}.issubset(probabilities):
        return False
    if not isinstance(provenance, dict) or not provenance:
        return False
    try:
        values = [float(probabilities[key]) for key in ("home", "draw", "away")]
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
            return False
        if not math.isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-6):
            return False
        if any(not math.isfinite(float(match.get(key))) for key in ("xg_home", "xg_away")):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(
        _normalised_matrix_dict(match.get("matrix") or match.get("score_matrix"))
        and (match.get("model_tip") or match.get("top_tip"))
        and match.get("source_mode") not in (None, "unavailable")
        and match.get("model_version")
    )


def _enrich_edge(matches, math_engine, odds_engine, competition=None, pool_context_collection=None):
    comp = get_competition(competition)
    prediction_service = PredictionService(math_engine)
    elo_document = (
        find_competition_document(pool_context_collection, comp, "elo_ratings")
        if comp.id == "ucl2026" and pool_context_collection is not None
        else None
    )
    for m in matches:
        raw_match = m.get("raw_match") or {}
        round_name = raw_match.get("round", m.get("round", "")) if isinstance(raw_match, dict) else m.get("round", "")
        if comp.id == "ucl2026":
            # Cached legacy edge values are not trusted until this pass proves
            # that both explicit ratings are available.
            m["edge_home"] = None
            m["elo_home_share"] = None
            m["market_home_share"] = None
        # Always recompute — round-keyword logic may have changed since caching.
        m["is_ko_phase"] = _is_ko_round(round_name)

        home_norm = TEAM_MAPPING.get(m.get("home_team"), m.get("home_team"))
        away_norm = TEAM_MAPPING.get(m.get("away_team"), m.get("away_team"))
        m["home_form"] = math_engine.team_forms.get(home_norm, {"form": [], "on_fire": False})
        m["away_form"] = math_engine.team_forms.get(away_norm, {"form": [], "on_fire": False})

        if _is_completed_match(m):
            # Completed matches must retain their archived pre-match tip; a
            # fresh prediction here would use hindsight Elo.
            continue
        odds = m.get("odds") or {}
        try:
            elo_state = m.get("elo_state") or build_elo_snapshot(
                math_engine, m.get("home_team"), m.get("away_team"), comp, elo_document
            )
            context = dict(m.get("match_context") or m.get("context") or {})
            context.setdefault("stage", m.get("stage") or infer_stage(round_name))
            context.setdefault("leg", m.get("leg", "single"))
            context.setdefault("first_leg_score", m.get("first_leg_score"))
            context.setdefault("commence_time", m.get("commence_time") or raw_match.get("commence_time"))
            if comp.id == "wc2026":
                context.setdefault("is_ko", m.get("is_ko_phase", False))
            pool_document = {}
            if pool_context_collection is not None:
                pool_document = find_competition_document(
                    pool_context_collection, comp, f"pool_context:{m.get('id')}"
                ) or {}
            odds_input = ({
                "odds": odds,
                "status": m.get("odds_status") or ("fresh" if m.get("odds_observed_at") else "stale"),
                "source": "odds_api",
                "observed_at": m.get("odds_observed_at"),
                "provenance": m.get("odds_provenance") or {},
            } if odds else None)
            prediction = prediction_service.predict(
                odds=odds_input,
                elo=elo_state,
                competition=comp,
                context=context,
                field_counts=pool_document.get("tip_counts"),
                user_points=pool_document.get("user_points", 0),
                leader_points=pool_document.get("leader_points", 0),
                remaining_srf_max_points=pool_document.get("remaining_srf_max_points", 1),
                observed_at=m.get("odds_observed_at") if odds else None,
            )
            m.update({
                "model_tip": prediction.get("model_tip"),
                "top_tip": prediction.get("top_tip"),
                "pool_tip": prediction.get("pool_tip"),
                "pool_status": prediction.get("pool_status"),
                "status": prediction.get("status"),
                "source_status": prediction.get("source_status", prediction.get("status")),
                "source": prediction.get("source"),
                "observed_at": prediction.get("observed_at"),
                "source_mode": prediction.get("source_mode"),
                "model_version": prediction.get("model_version"),
                "input_provenance": prediction.get("input_provenance"),
                "provenance": prediction.get("provenance"),
                "xg_home": prediction.get("xg_home"),
                "xg_away": prediction.get("xg_away"),
                "probabilities": prediction.get("probabilities"),
                "matrix": prediction.get("matrix", m.get("matrix", {})),
                "max_xp": float(prediction.get("max_xp") or 0.0),
                "context": prediction.get("context") or context,
                "match_context": prediction.get("context") or context,
            })
            if isinstance(elo_state, dict) and "home_rating" in elo_state and "away_rating" in elo_state:
                m["elo_home_share"] = math_engine.get_elo_probability(
                    float(elo_state["home_rating"]), float(elo_state["away_rating"])
                )
            else:
                m["elo_home_share"] = None
            if not all(key in odds for key in ("home", "draw", "away")):
                m["market_home_share"] = None
                m["edge_home"] = None
                continue
            true_probs = MathEngine.remove_margin(odds["home"], odds["draw"], odds["away"])
            pool = true_probs["home"] + true_probs["away"]
            market_home_share = (true_probs["home"] / pool) if pool > 0 else 0.5
            # UCL has no synthetic 1500 fallback.  Without a known rating the
            # edge is unavailable; odds-only predictions remain valid.
            if comp.id == "ucl2026" and elo_state is None:
                continue
            elo_home_share = m.get("elo_home_share")
            if elo_home_share is None:
                elo_home_share, _ = math_engine.get_match_elo_probabilities(m.get("home_team"), m.get("away_team"))
            m["elo_home_share"] = elo_home_share
            m["market_home_share"] = market_home_share
            m["edge_home"] = elo_home_share - market_home_share
        except Exception:
            pass
    return matches


def init_router(math_engine, odds_engine, cache_collection, archive_collection, *, team_form_service=None):
    router = APIRouter(prefix="/api")
    prediction_service = PredictionService(math_engine)

    @router.get("/matches")
    def get_matches(force: bool = False, competition: str | None = None):
        comp = require_competition(competition)
        cache_store = collection_for(cache_collection, comp)
        archive_store = collection_for(archive_collection, comp)
        cache_id = competition_document_id(comp, "matches_cache")
        try:
            cached = find_competition_document(cache_store, comp, "matches_cache")
            cached_data = (cached or {}).get("data")
        except Exception:
            cached_data = None
        # Public refresh flags are intentionally cache-only. Provider credits
        # and writes belong to the authenticated maintenance scheduler.
        if force:
            if isinstance(cached_data, list):
                return _present_cached_matches(
                    cached_data, math_engine, odds_engine, comp, archive_store, cache_store,
                    team_form_service,
                ) if cached_data else ([] if cached is not None else _unavailable_matches())
            return _unavailable_matches()
        if isinstance(cached_data, list) and cached_data:
            return _present_cached_matches(
                cached_data, math_engine, odds_engine, comp, archive_store, cache_store,
                team_form_service,
            )
        if cached is not None and cached_data == []:
            return []
        return _unavailable_matches()
        # ── Fast path: serve from MongoDB cache without any expensive work ──
        if not force:
            try:
                cached = find_competition_document(cache_store, comp, "matches_cache")
                if cached:
                    timestamp = cached.get("timestamp", 0)
                    data = cached.get("data")
                    if data is not None:
                        ttl = dynamic_ttl(data)
                        if time.time() - timestamp < ttl:
                            data = [
                                m for m in data
                                if not (espn_data._is_placeholder(m.get("home_team", ""))
                                        or espn_data._is_placeholder(m.get("away_team", "")))
                            ]
                            # Elo reload is cheap here thanks to the debounce guard.
                            math_engine.reload_elo_data()
                            archive = load_archive_from_db(archive_store)
                            return _sync_archive_tips(
                                _enrich_edge(data, math_engine, odds_engine, comp, cache_store),
                                archive, archive_store
                            )
            except Exception:
                pass

        # ── Slow path: cache miss or force refresh ──
        archive = load_archive_from_db(archive_store)
        math_engine.reload_elo_data(archive=archive, force=True)

        # Fixture skeleton comes from ESPN (only source with played + upcoming).
        try:
            fixtures = espn_data.get_scoreboard(competition=comp)
        except Exception as e:
            try:
                cached = find_competition_document(cache_store, comp, "matches_cache")
                if cached and cached.get("data"):
                    print(f"ESPN unavailable, serving stale cache: {e}")
                    return _sync_archive_tips(
                        _enrich_edge(cached["data"], math_engine, odds_engine, comp, cache_store),
                        archive, archive_store
                    )
            except Exception:
                pass
            raise HTTPException(status_code=503, detail=f"Fixture source unavailable: {e}")

        # Multi-bookmaker odds for upcoming games from The Odds API (best-effort).
        odds_lookup = _build_odds_api_lookup(odds_engine, comp)
        id_index = build_archive_id_index(archive)

        results = []
        _bot_inputs = {}
        for fx in fixtures:
            home_raw = fx["home_team"]
            away_raw = fx["away_team"]
            date = fx.get("commence_time", "")

            # Keep the same _id the archive already uses for this pairing.
            match_id = resolve_archive_id(id_index, home_raw, away_raw, date) or fx["id"]

            # Prefer Odds-API multi-book bookmakers; fall back to ESPN/DraftKings.
            bookmakers = _match_odds_api(odds_lookup, home_raw, away_raw, date)
            if not bookmakers and fx.get("espn_odds"):
                bookmakers = _synth_bookmakers(fx["espn_odds"], home_raw, away_raw)

            raw_match = {
                "id": match_id,
                "home_team": home_raw,
                "away_team": away_raw,
                "home_logo": fx.get("home_logo"),
                "away_logo": fx.get("away_logo"),
                "commence_time": date,
                "round": fx.get("round", ""),
                "bookmakers": bookmakers or [],
            }
            is_ko_detected = _is_ko_round(fx.get("round", ""))

            odds = {}
            top_tip, max_xp = "N/A", 0.0
            elo_home_share = market_home_share = edge_home = None
            prediction_result = {}
            context = {
                "stage": infer_stage(fx.get("round")) if fx.get("round") else ("playoff" if is_ko_detected else "league"),
                "leg": "single",
                "commence_time": date,
            }
            try:
                odds = extract_odds(raw_match)
            except ValueError:
                odds = {}

            # Completed games: show the frozen odds + algo tip from the archive
            # (recomputing with today's Elo would corrupt a past prediction).
            arc = archive.get(match_id) or {}
            archived_prediction = arc.get("prediction") or {}
            archived_snapshot = arc.get("pre_match_snapshot") or {}
            arc_tip = archived_prediction.get("top_tip") or archived_prediction.get("model_tip")
            if fx.get("completed") and arc_tip:
                snap_odds = archived_snapshot.get("odds") or {}
                if all(k in snap_odds for k in ("home", "draw", "away")):
                    odds = snap_odds
                prediction_result = {
                    "model_tip": archived_prediction.get("model_tip") or arc_tip,
                    "top_tip": archived_prediction.get("top_tip") or arc_tip,
                    "pool_tip": archived_prediction.get("pool_tip"),
                    "pool_status": archived_prediction.get("pool_status", "unavailable"),
                    "source_mode": archived_prediction.get("source_mode", archived_snapshot.get("source_mode", "unavailable")),
                    "status": archived_prediction.get("status", archived_snapshot.get("status", "unavailable")),
                    "source_status": archived_prediction.get("source_status") or archived_snapshot.get("source_status") or archived_prediction.get("status") or archived_snapshot.get("status") or "unavailable",
                    "source": archived_prediction.get("source", archived_snapshot.get("source")),
                    "observed_at": archived_prediction.get("observed_at", archived_snapshot.get("observed_at")),
                    "model_version": archived_prediction.get("model_version", archived_snapshot.get("model_version")),
                    "input_provenance": archived_prediction.get("input_provenance") or archived_snapshot.get("input_provenance", {}),
                    "provenance": archived_prediction.get("provenance") or archived_snapshot.get("provenance", {}),
                    "context": archived_prediction.get("context") or archived_snapshot.get("context") or context,
                }
                context = prediction_result.get("context") or context
                top_tip = prediction_result["top_tip"]
                max_xp = float(archived_prediction.get("max_xp") or 0.0)
            elif odds:
                try:
                    elo_state = build_elo_snapshot(math_engine, home_raw, away_raw, comp)
                    if comp.id == "wc2026":
                        math_engine.ensure_teams_exist(
                            TEAM_MAPPING.get(home_raw, home_raw),
                            TEAM_MAPPING.get(away_raw, away_raw),
                        )
                    context = dict(fx.get("match_context") or {})
                    context.setdefault("stage", fx.get("stage") or infer_stage(fx.get("round")) or ("playoff" if is_ko_detected else "league"))
                    context.setdefault("leg", fx.get("leg", "single"))
                    context.setdefault("tie_id", fx.get("tie_id"))
                    context.setdefault("first_leg_score", fx.get("first_leg_score"))
                    context.setdefault("commence_time", date)
                    if comp.id == "wc2026":
                        context.setdefault("is_ko", is_ko_detected)
                    pool_document = find_competition_document(
                        cache_store, comp, f"pool_context:{match_id}"
                    ) or {}
                    result = prediction_service.predict(
                        odds=odds,
                        elo=elo_state,
                        competition=comp,
                        context=context,
                        field_counts=pool_document.get("tip_counts"),
                        user_points=pool_document.get("user_points", 0),
                        leader_points=pool_document.get("leader_points", 0),
                        remaining_srf_max_points=pool_document.get("remaining_srf_max_points", 1),
                    )
                    prediction_result = result
                    top_tip = result.get("model_tip") or "N/A"
                    max_xp = float(result.get("max_xp") or 0.0)
                    probabilities = result.get("probabilities") or {}
                    true_probs = result.get("base_probabilities") or probabilities
                    elo_home_share = result.get("probabilities", {}).get("home") if elo_state else None
                    if elo_state:
                        elo_home_share, elo_away_share = math_engine.get_match_elo_probabilities(home_raw, away_raw)
                    win_loss_pool = (true_probs or {}).get("home", 0) + (true_probs or {}).get("away", 0)
                    market_home_share = ((true_probs or {}).get("home", 0) / win_loss_pool) if win_loss_pool > 0 else None
                    edge_home = elo_home_share - market_home_share if elo_home_share is not None and market_home_share is not None else None
                    if top_tip != "N/A":
                        _bot_inputs[match_id] = {
                            "score_matrix": result.get("score_matrix_df"),
                            "base_xp_df": pd.DataFrame(result.get("xp_tips") or []),
                            "true_probs": true_probs,
                            "prob_over25": None,
                        }
                except Exception:
                    top_tip, max_xp = "N/A", 0.0
                    elo_home_share = market_home_share = edge_home = None

            results.append({
                "id": match_id,
                "home_team": home_raw,
                "away_team": away_raw,
                "home_disp": DISPLAY_MAPPING.get(home_raw, home_raw),
                "away_disp": DISPLAY_MAPPING.get(away_raw, away_raw),
                "home_logo": fx.get("home_logo"),
                "away_logo": fx.get("away_logo"),
                "odds": odds,
                "top_tip": top_tip,
                "model_tip": prediction_result.get("model_tip") or (top_tip if top_tip != "N/A" else None),
                "pool_tip": prediction_result.get("pool_tip"),
                "pool_status": prediction_result.get("pool_status", "unavailable"),
                "status": prediction_result.get("status", "unavailable"),
                "source_status": prediction_result.get("source_status") or prediction_result.get("status", "unavailable"),
                "source": prediction_result.get("source"),
                "observed_at": prediction_result.get("observed_at"),
                "source_mode": prediction_result.get("source_mode", "unavailable"),
                "model_version": prediction_result.get("model_version"),
                "input_provenance": prediction_result.get("input_provenance", {}),
                "provenance": prediction_result.get("provenance", {}),
                "xg_home": prediction_result.get("xg_home"),
                "xg_away": prediction_result.get("xg_away"),
                "matrix": prediction_result.get("matrix", {}),
                "stage": prediction_result.get("stage", context.get("stage")),
                "tie_id": prediction_result.get("tie_id", context.get("tie_id")),
                "leg": prediction_result.get("leg", context.get("leg")),
                "first_leg_score": prediction_result.get("first_leg_score", context.get("first_leg_score")),
                "score_90": prediction_result.get("score_90", context.get("score_90")),
                "score_aet": prediction_result.get("score_aet", context.get("score_aet")),
                "shootout_winner": prediction_result.get("shootout_winner", context.get("shootout_winner")),
                "extra_time_eligible": prediction_result.get("extra_time_eligible", context.get("extra_time_eligible", False)),
                "max_xp": max_xp,
                "elo_home_share": elo_home_share,
                "market_home_share": market_home_share,
                "edge_home": edge_home,
                "is_ko_phase": is_ko_detected,
                "actual_score": fx.get("actual_score"),
                "completed": fx.get("completed", False),
                "raw_match": raw_match,
                "context": prediction_result.get("context", context),
                "match_context": prediction_result.get("context", context),
            })

        # Cache update — merge with existing
        try:
            existing_matches = {}
            try:
                cached = find_competition_document(cache_store, comp, "matches_cache")
                if cached:
                    existing_matches = {m["id"]: m for m in cached.get("data", [])}
            except Exception:
                pass
            for r in results:
                prev = existing_matches.get(r["id"])
                if prev:
                    old_o, new_o = prev.get("odds", {}), r.get("odds", {})
                    # Never overwrite previously-captured odds with an odds-less
                    # fixture (e.g. a completed game whose odds ESPN no longer lists).
                    if old_o and not new_o:
                        merged_entry = dict(r)
                        merged_entry["odds"] = old_o
                        merged_entry["top_tip"] = prev.get("top_tip", "N/A")
                        merged_entry["max_xp"] = prev.get("max_xp", 0)
                        merged_entry["raw_match"] = prev.get("raw_match", r["raw_match"])
                        existing_matches[r["id"]] = merged_entry
                        continue
                    odds_changed = any(
                        abs(new_o.get(k, 0) - old_o.get(k, 0)) > 0.02
                        for k in ["home", "draw", "away"]
                    )
                    missing_edge = "edge_home" not in prev and r.get("edge_home") is not None
                    if not odds_changed and not missing_edge:
                        # Preserve fresh ESPN-sourced fields (result + recomputed KO flag).
                        prev.update({
                            "actual_score": r.get("actual_score"),
                            "completed": r.get("completed", False),
                            "is_ko_phase": r.get("is_ko_phase", False),
                        })
                        prev.setdefault("raw_match", {})["round"] = r["raw_match"].get("round", "")
                        existing_matches[r["id"]] = prev
                        continue
                existing_matches[r["id"]] = r
            # Drop stale placeholder bracket slots (teams undecided) that a
            # previous cache may still hold — the merge otherwise keeps them.
            merged = sorted(
                (m for m in existing_matches.values()
                 if not (espn_data._is_placeholder(m.get("home_team", ""))
                         or espn_data._is_placeholder(m.get("away_team", "")))),
                key=lambda m: m.get("raw_match", {}).get("commence_time", ""),
            )
            cache_store.update_one(
                {"_id": cache_id},
                {"$set": {"timestamp": time.time(), "data": merged}},
                upsert=True
            )
        except Exception as e:
            print(f"Fehler beim Speichern des Caches: {e}")

        # Archive: log pre-match snapshots + backfill bots
        try:
            changed_entries = {}
            for r in results:
                if r["top_tip"] == "N/A":
                    continue

                bot_in = _bot_inputs.get(r["id"])
                bots = None
                if bot_in:
                    try:
                        bots = math_engine.compute_bot_tips(
                            score_matrix=bot_in["score_matrix"],
                            base_xp_df=bot_in["base_xp_df"],
                            true_probs=bot_in["true_probs"],
                            prob_over25=bot_in["prob_over25"],
                            home_team=r["home_team"],
                            away_team=r["away_team"],
                            match_id=r["id"],
                            is_ko_phase=r.get("is_ko_phase", False)
                        )
                    except Exception as e:
                        print(f"Bot tips failed for {r['id']}: {e}")

                if r["id"] not in archive:
                    elo_state = build_elo_snapshot(math_engine, r["home_team"], r["away_team"], comp)

                    new_entry = {
                        "metadata": {
                            "home_team": r["home_team"],
                            "away_team": r["away_team"],
                            "home_disp": r["home_disp"],
                            "away_disp": r["away_disp"],
                            "is_ko_phase": r.get("is_ko_phase", False),
                            "round": r.get("raw_match", {}).get("round", ""),
                            "commence_time": r.get("raw_match", {}).get("commence_time"),
                            **{key: value for key, value in (r.get("match_context") or {}).items() if key in {
                                "stage", "tie_id", "leg", "first_leg_score", "score_90", "score_aet",
                                "shootout_winner", "extra_time_eligible",
                            }},
                        },
                        "pre_match_snapshot": {
                            "timestamp_recorded": datetime.now(timezone.utc).isoformat(),
                            "odds": r["odds"],
                            "elo_state": elo_state,
                            "source_mode": r.get("source_mode"),
                            "status": r.get("status"),
                            "source_status": r.get("source_status", r.get("status")),
                            "source": r.get("source"),
                            "observed_at": r.get("observed_at"),
                            "model_version": r.get("model_version"),
                            "input_provenance": r.get("input_provenance", {}),
                            "provenance": r.get("provenance", {}),
                            "context": r.get("context", r.get("match_context", {})),
                        },
                        "prediction": {
                            "model_tip": r.get("model_tip") or r["top_tip"],
                            "top_tip": r["top_tip"],
                            "pool_tip": r.get("pool_tip"),
                            "pool_status": r.get("pool_status", "unavailable"),
                            "status": r.get("status", "unavailable"),
                            "source_status": r.get("source_status", r.get("status", "unavailable")),
                            "source": r.get("source"),
                            "observed_at": r.get("observed_at"),
                            "source_mode": r.get("source_mode"),
                            "model_version": r.get("model_version"),
                            "input_provenance": r.get("input_provenance", {}),
                            "provenance": r.get("provenance", {}),
                            "context": r.get("context", r.get("match_context", {})),
                            "user_tip": None,
                            "max_xp": float(r["max_xp"]),
                            "bots": bots or {},
                        },
                        "post_match_result": {
                            "status": "pending",
                            "actual_score": None,
                            "points_earned": None,
                            "algo_points": None,
                            "bot_points": {k: None for k in (bots or {})},
                        }
                    }
                    archive[r["id"]] = new_entry
                    changed_entries[r["id"]] = new_entry
                elif bots and "bots" not in archive[r["id"]].get("prediction", {}):
                    archive[r["id"]]["prediction"]["bots"] = bots
                    pmr = archive[r["id"]]["post_match_result"]
                    if "bot_points" not in pmr:
                        actual = pmr.get("actual_score")
                        is_ko = archive[r["id"]]["metadata"].get("is_ko_phase", False)
                        if actual:
                            pmr["bot_points"] = {
                                bot: MathEngine.calculate_actual_points(info["tip"], actual, is_ko)
                                for bot, info in bots.items() if info.get("tip")
                            }
                        else:
                            pmr["bot_points"] = {k: None for k in bots}
                    changed_entries[r["id"]] = archive[r["id"]]

            for mid, entry in changed_entries.items():
                upsert_archive_entry(archive_store, mid, entry)
        except Exception as e:
            print(f"Archive logging failed: {e}")

        for r in results:
            arc = archive.get(r["id"], {})
            r["bots"] = arc.get("prediction", {}).get("bots", {})

        return _sync_archive_tips(results, archive, archive_store)

    return router
