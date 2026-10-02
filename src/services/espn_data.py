"""
ESPN data service — public, no auth, no quota.

Provides the full WC fixture list (played + upcoming), completed scores,
and group standings, normalized to the shapes the rest of the codebase
already consumes. ESPN is the only source that returns completed fixtures
(The Odds API drops games once they kick off), so it is the fixture
skeleton; odds are layered on top from The Odds API where available.
"""
import os
import time
import requests
from datetime import date, datetime, timedelta, timezone

from src.competitions import get_competition

ESPN_BASE_URL = os.getenv("ESPN_BASE_URL", "https://site.api.espn.com/apis/site/v2")
SCOREBOARD_ENDPOINT = f"{ESPN_BASE_URL}/sports/soccer/fifa.world/scoreboard"
STANDINGS_ENDPOINT = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"

# ESPN uses a few names that differ from what /api/matches / TEAM_MAPPING settled on.
# Keep this tight — only the names that actually clash.
ESPN_NAME_FIXUP = {
    "Congo DR": "DR Congo",
    "Bosnia-Herzegovina": "Bosnia & Herzegovina",
    "Czechia": "Czech Republic",
}

# In-memory cache for the raw scoreboard payload — the same dates query is hit by
# fixtures + completed-scores + commence_time backfill within one request cycle.
_SCOREBOARD_TTL = 300  # 5 min
_scoreboard_cache = {}  # {query_key: (timestamp, events)}


def _canon(name: str) -> str:
    return ESPN_NAME_FIXUP.get(name, name)


def _team_logo(team: dict) -> str | None:
    if team.get("logo"):
        return team["logo"]
    logos = team.get("logos") or []
    return logos[0].get("href") if logos and isinstance(logos[0], dict) else None


def _event_in_date_range(event: dict, start_date, end_date) -> bool:
    try:
        event_date = datetime.fromisoformat(str(event.get("date") or "").replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return False
    return start_date <= event_date <= end_date


def _event_has_season_year(event: dict, year: int) -> bool:
    try:
        return int((event.get("season") or {}).get("year")) == year
    except (TypeError, ValueError):
        return False


# Bracket slots whose teams aren't decided yet come back with placeholder names
# like "Round of 32 11 Winner" or "Group A Runner-Up" — not real, untippable.
_PLACEHOLDER_TOKENS = ("winner", "runner-up", "runner up", "loser", "tbd")


def _is_placeholder(name: str) -> bool:
    low = (name or "").lower()
    return any(tok in low for tok in _PLACEHOLDER_TOKENS)


def _american_to_decimal(american) -> float | None:
    """ESPN moneyline/totals odds are American integers; we need decimal."""
    try:
        a = float(american)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + (a / 100.0) if a > 0 else 1 + (100.0 / abs(a))


def _scoreboard_endpoint(competition=None) -> str:
    comp = get_competition(competition)
    if comp.id == "wc2026" and "ESPN_SCOREBOARD_URL_TEMPLATE" not in os.environ:
        return SCOREBOARD_ENDPOINT
    env_name = f"ESPN_{comp.id.upper()}_SLUG"
    slug = os.getenv(env_name, comp.espn_slug)
    template = os.getenv(
        "ESPN_SCOREBOARD_URL_TEMPLATE",
        f"{ESPN_BASE_URL}/sports/soccer/{{slug}}/scoreboard",
    )
    return template.format(slug=slug, competition=comp.id)


def _standings_endpoint(competition=None) -> str:
    comp = get_competition(competition)
    if comp.id == "wc2026" and "ESPN_STANDINGS_URL_TEMPLATE" not in os.environ:
        return STANDINGS_ENDPOINT
    template = os.getenv(
        "ESPN_STANDINGS_URL_TEMPLATE",
        f"https://site.api.espn.com/apis/v2/sports/soccer/{{slug}}/standings",
    )
    slug = os.getenv(f"ESPN_{comp.id.upper()}_SLUG", comp.espn_slug)
    return template.format(slug=slug, competition=comp.id)


def _fetch_scoreboard_dates(
    dates: str,
    *,
    competition=None,
    request_get=None,
    use_cache: bool = True,
) -> list[dict]:
    comp = get_competition(competition)
    endpoint = _scoreboard_endpoint(competition)
    params = {"dates": dates}
    if comp.id == "epl2026":
        params["limit"] = 1000
    key = f"{endpoint}|{tuple(sorted(params.items()))}"
    cached = _scoreboard_cache.get(key) if use_cache else None
    if cached and time.time() - cached[0] < _SCOREBOARD_TTL:
        return cached[1]
    resp = (request_get or requests.get)(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    events = resp.json().get("events", []) or []
    _scoreboard_cache[key] = (time.time(), events)
    return events


def _extract_espn_odds(comp: dict) -> dict | None:
    """Pull DraftKings H/D/A + O/U 2.5 from an ESPN competition, as decimals."""
    odds_list = comp.get("odds") or []
    o = odds_list[0] if odds_list else None
    if not o:
        return None
    ml = o.get("moneyline") or {}
    total = o.get("total") or {}

    def _ml(side):
        node = (ml.get(side) or {}).get("close") or (ml.get(side) or {}).get("open") or {}
        return _american_to_decimal(node.get("odds"))

    def _ou(side):
        node = (total.get(side) or {}).get("close") or (total.get(side) or {}).get("open") or {}
        return _american_to_decimal(node.get("odds"))

    home, draw, away = _ml("home"), _ml("draw"), _ml("away")
    if not (home and draw and away):
        return None
    out = {"home": home, "draw": draw, "away": away}
    over, under = _ou("over"), _ou("under")
    if over and under:
        out["over25"] = over
        out["under25"] = under
    return out


def get_scoreboard(
    days_back: int = 30,
    days_forward: int = 75,
    *,
    competition=None,
    now: datetime | None = None,
    chunk_days: int = 7,
    request_get=None,
    use_cache: bool = True,
) -> list[dict]:
    """
    ALL WC events (played + upcoming) normalized to fixture dicts:
      {id, home_team, away_team, commence_time, round, completed,
       actual_score|None, espn_odds|None}
    """
    if chunk_days < 1:
        raise ValueError("chunk_days must be positive")
    today = (now or datetime.now(timezone.utc)).date()
    from_dt = today - timedelta(days=days_back)
    to_dt = today + timedelta(days=days_forward)
    events_by_id = {}
    resolved_competition = get_competition(competition)
    epl_start_year = None
    if resolved_competition.id == "ucl2026":
        date_queries = [str(year) for year in range(from_dt.year, to_dt.year + 1)]
    elif resolved_competition.id == "epl2026":
        epl_start_year = int(resolved_competition.season.split("/", 1)[0])
        from_dt, to_dt = date(epl_start_year, 8, 1), date(epl_start_year + 1, 6, 30)
        date_queries = [str(year) for year in range(from_dt.year, to_dt.year + 1)]
    else:
        # Keep the WC's existing single-range scoreboard request unchanged.
        date_queries = [f"{from_dt:%Y%m%d}-{to_dt:%Y%m%d}"] if from_dt <= to_dt else []
    successful_windows = 0
    last_request_error = None
    for dates in date_queries:
        try:
            events = _fetch_scoreboard_dates(
                dates,
                competition=competition,
                request_get=request_get,
                use_cache=use_cache,
            )
            successful_windows += 1
        except requests.RequestException as exc:
            last_request_error = exc
            continue
        for event in events:
            if resolved_competition.id == "ucl2026" and not _event_in_date_range(
                event, from_dt, to_dt
            ):
                continue
            if resolved_competition.id == "epl2026" and (
                not _event_in_date_range(event, from_dt, to_dt)
                or not _event_has_season_year(event, epl_start_year)
            ):
                continue
            event_id = str(event.get("id", ""))
            if event_id:
                events_by_id[event_id] = event

    if not successful_windows and last_request_error is not None:
        raise last_request_error

    out = []
    for e in events_by_id.values():
        comp = (e.get("competitions") or [{}])[0]
        status_type = (comp.get("status") or {}).get("type") or {}
        completed = bool(status_type.get("completed"))
        detail = status_type.get("detail", "")
        # ESPN finished-state details: "FT", "AET", "FT-Pens" (STATUS_FINAL_PEN).
        is_final = completed and (detail in ("FT", "AET", "PEN") or detail.startswith("FT-"))

        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        home_team = home.get("team") or {}
        away_team = away.get("team") or {}
        home_name = _canon(home_team.get("displayName", ""))
        away_name = _canon(away_team.get("displayName", ""))
        if not home_name or not away_name:
            continue
        # Skip undecided bracket slots (teams not yet known).
        if _is_placeholder(home_name) or _is_placeholder(away_name):
            continue

        round_name = ((e.get("season") or {}).get("slug") or "").replace("-", " ")

        actual_score = None
        if is_final:
            hs, as_ = home.get("score"), away.get("score")
            if hs is not None and as_ is not None:
                actual_score = f"{hs}:{as_}"

        out.append({
            "id": str(e.get("id", "")),
            "home_team": home_name,
            "away_team": away_name,
            "home_logo": _team_logo(home_team),
            "away_logo": _team_logo(away_team),
            "commence_time": e.get("date", ""),
            "round": round_name,
            "completed": is_final,
            "actual_score": actual_score,
            "espn_odds": _extract_espn_odds(comp),
        })
    return out


def get_completed_scores(days_from: int = 30, *, competition=None) -> list[dict]:
    """
    Completed fixtures in the legacy Odds-API scores shape consumed by
    perform_elo_sync / math_engine.update_elo_from_api_scores.
    """
    out = []
    for f in get_scoreboard(days_back=days_from, days_forward=0, competition=competition):
        if not f["completed"] or not f["actual_score"]:
            continue
        home_name, away_name = f["home_team"], f["away_team"]
        hs, as_ = f["actual_score"].split(":")
        out.append({
            "id": f["id"],
            "completed": True,
            "home_team": home_name,
            "away_team": away_name,
            "commence_time": f["commence_time"],
            "round": f["round"],
            "scores": [
                {"name": home_name, "score": hs},
                {"name": away_name, "score": as_},
            ],
        })
    return out


def get_standings_groups(*, competition=None) -> list[dict]:
    """Normalize ESPN tables for the competition's standings cache."""
    comp = get_competition(competition)
    season_year = int(comp.season.split("/", 1)[0])
    resp = requests.get(_standings_endpoint(comp), params={"season": season_year}, timeout=10)
    resp.raise_for_status()
    children = resp.json().get("children", []) or []

    groups = []
    for grp in children:
        rows = []
        entries = (grp.get("standings") or {}).get("entries", []) or []
        for entry in entries:
            team = entry.get("team") or {}
            stats = {s.get("name"): s.get("value") for s in entry.get("stats", [])}
            logos = team.get("logos") or []
            rows.append({
                "pos": int(stats.get("rank", 0) or 0),
                "team": _canon(team.get("displayName", "")),
                "logo": logos[0].get("href", "") if logos else "",
                "p": int(stats.get("gamesPlayed", 0) or 0),
                "w": int(stats.get("wins", 0) or 0),
                "d": int(stats.get("ties", 0) or 0),
                "l": int(stats.get("losses", 0) or 0),
                "gf": int(stats.get("pointsFor", 0) or 0),
                "ga": int(stats.get("pointsAgainst", 0) or 0),
                "gd": int(stats.get("pointDifferential", 0) or 0),
                "pts": int(stats.get("points", 0) or 0),
            })
        rows.sort(key=lambda r: r["pos"])
        groups.append({"name": grp.get("name", ""), "rows": rows})
    return groups
