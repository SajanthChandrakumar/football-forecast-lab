import os
import sys
import json
import logging
from datetime import datetime, timezone

import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
import certifi
from slowapi import Limiter
from slowapi.util import get_remote_address

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

if os.getenv("USE_API_FOOTBALL", "").lower() in ("1", "true", "yes"):
    from src.odds_engine_apifootball import OddsApiEngine
    print("Odds engine: API-Football (api-sports.io)")
else:
    from src.odds_engine import OddsApiEngine
    print("Odds engine: The Odds API")

from src.math_engine import MathEngine
from src.quota_store import read_quota
from src.constants import TEAM_MAPPING, SCORES_CACHE_TTL, _is_ko_round
from src.competitions import (
    COMPETITIONS,
    DEFAULT_COMPETITION_ID,
    collection_for,
    find_competition_document,
    list_competitions,
    require_competition,
)
from src.services.archive import load_archive_from_db, upsert_archive_entry
from src.services.auth import require_cron_secret
from src.services.elo_sync import perform_elo_sync
from src.services.prediction import PredictionService, infer_stage, rebuild_prediction, user_tip_is_open
from src.services.ucl_simulation import _fixture_score, _fixture_teams, build_ucl_table
from src.services.team_form import (
    ApiFootballClient,
    EspnTeamFormClient,
    FailoverTeamFormClient,
    TeamFormService,
)
from src.routes.matches import init_router as matches_router
from src.routes.predict import init_router as predict_router
from src.routes.custom_bot import init_router as custom_bot_router
from src.routes.simulate import init_router as simulate_router
from src.routes.maintenance import init_router as maintenance_router
from src.routes.pool import init_router as pool_router
from src.routes.elo_status import init_router as elo_status_router
from src.routes.model_evaluation import init_router as model_evaluation_router

app = FastAPI(title="Football Forecast Lab API")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MongoDB ──────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is required. Set it in your .env file.")
_mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
_db = _mongo_client["wm2026_db"]
archive_collection = _db["archive"]
cache_collection = _db["cache"]
custom_bot_collection = _db["custom_bot"]
archive_collections = {
    competition.id: _db[competition.archive_collection]
    for competition in COMPETITIONS.values()
}
cache_collections = {
    competition.id: _db[competition.cache_collection]
    for competition in COMPETITIONS.values()
}
custom_bot_collections = {
    competition.id: _db[competition.custom_bot_collection]
    for competition in COMPETITIONS.values()
}

# ── CORS ─────────────────────────────────────────────────────
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

# Compress JSON payloads and static assets (the matches/archive responses
# are several hundred KB uncompressed).
app.add_middleware(GZipMiddleware, minimum_size=1024)

def _real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=_real_ip)
app.state.limiter = limiter

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src 'self' fonts.gstatic.com; img-src 'self' data: https://a.espncdn.com"
    # Force browsers to revalidate JS/CSS/HTML every load (ETag → 304 when
    # unchanged). Without this, unversioned ES-module sub-imports get cached
    # indefinitely and code changes silently fail to reach the browser.
    path = request.url.path
    if path.startswith("/assets/"):
        # Vite emits content-hashed filenames under /assets/ — safe to cache
        # forever; a new build changes the hash and busts the cache.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path.endswith((".js", ".css", ".html")):
        # Everything unhashed (index.html, legacy frontend) must revalidate
        # every load (ETag → 304), or code changes silently fail to arrive.
        response.headers["Cache-Control"] = "no-cache"
    return response

# ── Engine init ──────────────────────────────────────────────
_data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(_data_dir, exist_ok=True)
elo_csv_path = os.path.join(_data_dir, 'elo_ratings.csv')
if not os.path.exists(elo_csv_path):
    pd.DataFrame({
        "team_code": ["GER", "ARG", "FRA"],
        "team_name": ["Deutschland", "Argentinien", "Frankreich"],
        "elo_rating": [1980, 2140, 2090]
    }).to_csv(elo_csv_path, index=False)

try:
    _elo_doc = find_competition_document(cache_collection, DEFAULT_COMPETITION_ID, "elo_ratings")
    if _elo_doc and _elo_doc.get("rows"):
        pd.DataFrame(_elo_doc["rows"]).to_csv(elo_csv_path, index=False)
        logger.info("Startup: restored elo_ratings.csv from MongoDB")
    _hist_doc = find_competition_document(cache_collection, DEFAULT_COMPETITION_ID, "elo_history")
    if _hist_doc and _hist_doc.get("data"):
        _hist_path = os.path.join(_data_dir, 'elo_history.json')
        with open(_hist_path, 'w', encoding='utf-8') as _hf:
            json.dump(_hist_doc["data"], _hf, indent=4)
        logger.info("Startup: restored elo_history.json from MongoDB")
    _proc_doc = find_competition_document(cache_collection, DEFAULT_COMPETITION_ID, "processed_match_ids")
    if _proc_doc and _proc_doc.get("ids") is not None:
        _proc_path = os.path.join(_data_dir, 'processed_matches.json')
        with open(_proc_path, 'w', encoding='utf-8') as _pf:
            json.dump(_proc_doc["ids"], _pf)
        logger.info(f"Startup: restored {len(_proc_doc['ids'])} processed match IDs from MongoDB")
except Exception as _e:
    logger.warning(f"Startup: MongoDB restore skipped — {_e}")

math_engine = MathEngine(elo_csv_path, TEAM_MAPPING)
prediction_service = PredictionService(math_engine)
global_odds_engine = OddsApiEngine()
scores_cache_path = os.path.join(_data_dir, 'scores_cache.json')
_form_key = os.getenv("API_FOOTBALL_KEY", "").strip()
if not _form_key or _form_key.lower() in {"your_key_here", "your_api_football_key", "placeholder", "replace_me"}:
    _form_key = None
_form_cache = cache_collections["ucl2026"]
_form_primary = (
    ApiFootballClient(_form_key, cache_collection=_form_cache, competition="ucl2026")
    if _form_key else None
)
team_form_service = TeamFormService(
    _form_cache,
    FailoverTeamFormClient(
        _form_primary,
        EspnTeamFormClient(season=int(os.getenv("UCL_TEAM_FORM_SEASON", "2026"))),
    ),
    competition="ucl2026",
)

# ── Wire routers ─────────────────────────────────────────────
app.include_router(matches_router(
    math_engine, global_odds_engine, cache_collections, archive_collections,
    team_form_service=team_form_service,
))
app.include_router(predict_router(math_engine, global_odds_engine, cache_collections, limiter, archive_collections))
app.include_router(custom_bot_router(math_engine, archive_collections, custom_bot_collections, limiter))
app.include_router(simulate_router(math_engine, cache_collections))
app.include_router(maintenance_router(
    cache_collections,
    global_odds_engine,
    archive_collections=archive_collections,
    math_engine=math_engine,
    team_form_service=team_form_service,
))
app.include_router(pool_router(cache_collections, archive_collections))
app.include_router(elo_status_router(cache_collections))
app.include_router(model_evaluation_router(archive_collections))

# ── Small endpoints (not worth extracting) ───────────────────

@app.get("/api/ping")
def ping():
    """Lightweight keep-alive endpoint — call every 5 min to prevent Render cold starts."""
    return {"ok": True}


@app.get("/api/competitions")
def get_competitions():
    return list_competitions()


@app.get("/api/quota")
def get_quota(competition: str | None = None):
    require_competition(competition)
    return {"odds": read_quota("odds"), "football": read_quota("football")}


@app.get("/api/bonus_questions")
def bonus_questions():
    """SRF Tippspiel bonus questions, graded against the real tournament outcome."""
    actual_results = {
        "champion": "Spanien",
        "draws_00": 8,
        "top_scorer_goals": 10,
        "switzerland_goals": 10,
        "switzerland_round": "Viertelfinal",
    }
    try:
        math_engine.reload_elo_data()
        return math_engine.compute_bonus_predictions(actual_results)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your request")


@app.post("/api/archive/user_tip")
@limiter.limit("30/minute")
def set_user_tip(request: Request, payload: dict, competition: str | None = None):
    comp = require_competition(competition or payload.get("competition"))
    archive_store = collection_for(archive_collections, comp)
    match_id  = payload.get("match_id")
    user_tip  = payload.get("user_tip", "").strip()

    if not match_id or not user_tip:
        raise HTTPException(status_code=400, detail="match_id and user_tip required")

    parts = user_tip.split(":")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise HTTPException(status_code=400, detail="user_tip must be in format H:A (e.g. 2:1)")

    doc = archive_store.find_one({"_id": match_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Match not in archive")

    commence_time = (doc.get("metadata") or {}).get("commence_time")
    if not user_tip_is_open(commence_time, datetime.now(timezone.utc), competition=comp):
        raise HTTPException(status_code=409, detail="User tips are closed at T-5")

    entry = {k: v for k, v in doc.items() if k != "_id"}
    entry["prediction"]["user_tip"] = user_tip

    actual = entry["post_match_result"].get("actual_score")
    if actual:
        is_ko = entry["metadata"].get("is_ko_phase", False)
        pts = MathEngine.calculate_actual_points(user_tip, actual, is_ko)
        entry["post_match_result"]["points_earned"] = pts
    else:
        pts = None

    upsert_archive_entry(archive_store, match_id, entry)
    return {"ok": True, "points_earned": pts}

@app.get("/api/archive")
def get_archive(competition: str | None = None):
    comp = require_competition(competition)
    return load_archive_from_db(collection_for(archive_collections, comp))

@app.get("/api/standings")
def get_standings(competition: str | None = None):
    comp = require_competition(competition)
    cache_store = collection_for(cache_collections, comp)
    try:
        doc = find_competition_document(cache_store, comp, "standings_cache")
        if comp.id != "ucl2026" and doc and doc.get("data"):
            return doc["data"]
    except Exception:
        doc = None
    if comp.id == "ucl2026":
        cached = None
        try:
            cached = find_competition_document(cache_store, comp, "matches_cache")
            if doc and _valid_ucl_standings(doc.get("data")):
                return doc["data"]
            derived = _derive_ucl_standings(cached or {})
            if derived:
                return [{"name": "UCL League Phase", "rows": derived}]
        except Exception:
            pass
    return []


def _valid_ucl_standings(data) -> bool:
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        return False
    rows = data[0].get("rows")
    if not isinstance(rows, list) or len(rows) != 36:
        return False
    teams, positions = [], []
    for row in rows:
        if not isinstance(row, dict) or not row.get("team"):
            return False
        try:
            positions.append(int(row.get("pos")))
        except (TypeError, ValueError):
            return False
        teams.append(str(row["team"]))
    return len(set(teams)) == 36 and set(positions) == set(range(1, 37))


def _derive_ucl_standings(cached: dict) -> list[dict]:
    if not isinstance(cached, dict):
        return []
    metadata = cached.get("metadata") if isinstance(cached.get("metadata"), dict) else {}
    fixtures = cached.get("data")
    if not isinstance(fixtures, list) or not fixtures:
        return []
    league_fixtures = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            return []
        raw_match = fixture.get("raw_match") if isinstance(fixture.get("raw_match"), dict) else {}
        round_name = fixture.get("round") or fixture.get("stage") or raw_match.get("round", "")
        if _is_ko_round(round_name) or infer_stage(round_name) != "league":
            continue
        league_fixtures.append(fixture)

    def metadata_value(key):
        return cached.get(key, metadata.get(key))

    teams = cached.get("teams", metadata.get("teams"))
    if isinstance(teams, dict):
        teams = [row.get("team", row.get("team_name")) for row in teams.values() if isinstance(row, dict)]
    elif isinstance(teams, (list, tuple)) and teams and isinstance(teams[0], dict):
        teams = [row.get("team", row.get("team_name")) for row in teams]
    if not isinstance(teams, (list, tuple)) or not teams:
        teams = sorted({
            team
            for fixture in league_fixtures
            for team in (fixture.get("home_team"), fixture.get("away_team"))
            if team
        })
    teams = [str(team) for team in teams if team]
    if len(teams) != 36 or len(set(teams)) != 36:
        return []

    official_order = metadata_value("official_order")
    if isinstance(official_order, list) and official_order and isinstance(official_order[0], dict):
        official_order = [row.get("team", row.get("team_name")) for row in official_order]
    try:
        table = build_ucl_table(
            teams,
            league_fixtures,
            official_order=official_order,
            disciplinary_scores=metadata_value("disciplinary_scores"),
            uefa_coefficients=metadata_value("uefa_coefficients"),
            uefa_coefficient_ranks=metadata_value("uefa_coefficient_ranks"),
            coefficient_version=metadata_value("coefficient_version") or "2026",
        )
    except (TypeError, ValueError, KeyError):
        return []

    played = {team: 0 for team in teams}
    draws = {team: 0 for team in teams}
    logos = {}
    team_metadata = metadata_value("team_metadata") or metadata_value("teams_metadata") or metadata_value("team_logos")
    if isinstance(team_metadata, dict):
        team_metadata = team_metadata.items()
    if isinstance(team_metadata, (list, tuple)):
        entries = team_metadata if team_metadata and isinstance(team_metadata[0], dict) else ()
        if entries:
            team_metadata = ((row.get("team", row.get("team_name")), row) for row in entries)
        else:
            team_metadata = ()
    if team_metadata:
        for team, details in team_metadata:
            if team and isinstance(details, dict) and details.get("logo"):
                logos[str(team)] = details["logo"]
    for fixture in league_fixtures:
        try:
            home, away = _fixture_teams(fixture)
        except (TypeError, ValueError):
            return []
        raw_match = fixture.get("raw_match") if isinstance(fixture.get("raw_match"), dict) else {}
        for team, key in ((home, "home_logo"), (away, "away_logo")):
            logo = fixture.get(key) or raw_match.get(key)
            if logo:
                logos.setdefault(team, logo)
        score = _fixture_score(fixture)
        if score is None:
            continue
        played[home] += 1
        played[away] += 1
        if score[0] == score[1]:
            draws[home] += 1
            draws[away] += 1

    rows = []
    for row in table:
        team = row["team"]
        wins = int(row.get("wins", 0))
        draws_count = draws[team]
        rows.append({
            "pos": int(row["rank"]),
            "team": team,
            "logo": logos.get(team, ""),
            "p": played[team],
            "w": wins,
            "d": draws_count,
            "l": max(0, played[team] - wins - draws_count),
            "gf": int(row.get("goals_for", 0)),
            "ga": int(row.get("goals_against", 0)),
            "gd": int(row.get("goal_difference", 0)),
            "pts": int(row.get("points", 0)),
        })
    return rows if _valid_ucl_standings([{"rows": rows}]) else []

@app.get("/api/elo_history")
def get_elo_history(competition: str | None = None):
    comp = require_competition(competition)
    cache_store = collection_for(cache_collections, comp)
    try:
        doc = find_competition_document(cache_store, comp, "elo_history")
        if doc and doc.get("data"):
            return doc["data"]
    except Exception:
        pass
    if comp.id != "wc2026":
        return {}
    history_path = os.path.join(_data_dir, 'elo_history.json')
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

@app.get("/api/elo_ratings")
def get_elo_ratings(competition: str | None = None):
    comp = require_competition(competition)
    cache_store = collection_for(cache_collections, comp)
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
    out = {}
    cached_rows = None
    try:
        cached_doc = find_competition_document(cache_store, comp, "elo_ratings")
        cached_rows = (cached_doc or {}).get("rows")
    except Exception:
        cached_rows = None
    rows = cached_rows
    if rows is not None:
        for row in rows:
            try:
                out[row['team_name']] = {
                    'team_code': row.get('team_code', ''),
                    'elo': float(row['elo_rating']),
                }
            except (ValueError, KeyError, TypeError):
                continue
        return out
    if comp.id != "wc2026":
        return out
    try:
        import csv as _csv
        with open(csv_path, 'r', encoding='utf-8') as f:
            for row in _csv.DictReader(f):
                try:
                    out[row['team_name']] = {
                        'team_code': row.get('team_code', ''),
                        'elo': float(row['elo_rating']),
                    }
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    return out

@app.get("/api/recalculate_points")
def recalculate_all_points(request: Request, competition: str | None = None):
    require_cron_secret(request, os.getenv("CRON_SECRET", ""))
    comp = require_competition(competition)
    archive_store = collection_for(archive_collections, comp)
    archive = load_archive_from_db(archive_store)
    updated = 0
    for match_id, entry in archive.items():
        if entry.get("post_match_result", {}).get("status") == "completed":
            actual_score = entry.get("post_match_result", {}).get("actual_score")
            algo_tip = entry.get("prediction", {}).get("top_tip")
            is_ko = entry.get("metadata", {}).get("is_ko_phase", False)

            if actual_score and algo_tip:
                old_algo_pts = entry.get("post_match_result", {}).get("algo_points")
                new_algo_pts = MathEngine.calculate_actual_points(algo_tip, actual_score, is_ko)

                if old_algo_pts != new_algo_pts:
                    entry["post_match_result"]["algo_points"] = new_algo_pts
                    updated += 1

                    bots = entry.get("prediction", {}).get("bots", {})
                    if bots:
                        entry["post_match_result"]["bot_points"] = {
                            bot: MathEngine.calculate_actual_points(info["tip"], actual_score, is_ko)
                            for bot, info in bots.items() if info.get("tip")
                        }

                    upsert_archive_entry(archive_store, match_id, entry)

    return {"status": "success", "recalculated": updated}


@app.get("/api/rebuild_honest_tips")
def rebuild_honest_tips(request: Request, competition: str | None = None):
    require_cron_secret(request, os.getenv("CRON_SECRET", ""))
    """One-off repair: recompute every completed match's algo tip from its
    pre_match_snapshot (odds + Elo captured BEFORE kickoff) using the exact
    dashboard pipeline. Removes any hindsight tips that leaked into the
    archive, then regrades algo_points from the honest tip."""
    comp = require_competition(competition)
    archive_store = collection_for(archive_collections, comp)
    archive = load_archive_from_db(archive_store)
    rebuilt = skipped = 0
    for match_id, entry in archive.items():
        if entry.get("post_match_result", {}).get("status") != "completed":
            continue
        try:
            rebuilt_entry = rebuild_prediction(prediction_service, entry, competition=comp)
            if rebuilt_entry is None:
                skipped += 1
                continue
            upsert_archive_entry(archive_store, match_id, rebuilt_entry)
            rebuilt += 1
        except Exception as e:
            logger.warning(f"rebuild_honest_tips failed for {match_id}: {e}")
            skipped += 1

    return {"status": "success", "rebuilt": rebuilt, "skipped": skipped}


@app.get("/api/sync_elo")
@limiter.limit("5/hour")
def sync_elo(request: Request, force: bool = False, competition: str | None = None):
    require_cron_secret(request, os.getenv("CRON_SECRET", ""))
    comp = require_competition(competition)
    archive_store = collection_for(archive_collections, comp)
    cache_store = collection_for(cache_collections, comp)
    try:
        return perform_elo_sync(
            math_engine=math_engine,
            odds_engine=global_odds_engine,
            cache_collection=cache_store,
            archive_collection=archive_store,
            data_dir=_data_dir,
            scores_cache_path=scores_cache_path,
            MathEngine=MathEngine,
            force=force,
            competition=comp,
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your request")

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend-v2', 'dist'))
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
