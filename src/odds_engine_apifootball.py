"""
Drop-in replacement for src.odds_engine.OddsApiEngine that hits API-Football
(api-sports.io) instead of The Odds API. Returns data normalized to the legacy
Odds-API shape so the rest of the codebase needs zero changes.

Activate via the `USE_API_FOOTBALL=true` env flag — see src/api.py for the switch.

World Cup league ID = 1 on API-Football. If that ID ever changes for a
different season schema, override WC_LEAGUE_ID before constructing the engine.
"""
import os
import json
import requests
import time
from src import quota_store
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from src.competitions import get_competition

try:
    from src.quota_store import write_quota
except ImportError:
    from quota_store import write_quota

load_dotenv()


class OddsApiEngine:
    BASE_URL = "https://v3.football.api-sports.io"
    WC_LEAGUE_ID = 1
    UCL_LEAGUE_ID = int(os.getenv("ODDS_API_FOOTBALL_UCL_LEAGUE_ID", "2"))
    EPL_LEAGUE_ID = 39
    SEASON = 2026

    def __init__(self):
        self.api_key = os.getenv("API_FOOTBALL_KEY")
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError(
                "API_FOOTBALL_KEY missing or invalid in .env. "
                "Get one at https://dashboard.api-football.com/profile?access"
            )
        self._headers = {"x-apisports-key": self.api_key}
        self._h2h_mem_cache = {}
        self._lineup_mem_cache = {}

    def _request(self, path: str, params: dict | None = None) -> dict:
        delay = quota_store.reserve_request("football")
        if delay:
            time.sleep(delay)
        response = requests.get(f"{self.BASE_URL}{path}", headers=self._headers, params=params or {}, timeout=10)
        self._update_quota(response.headers)
        response.raise_for_status()
        return response.json()

    def _update_quota(self, headers) -> None:
        remaining = headers.get("x-ratelimit-requests-remaining", "Unknown")
        limit = headers.get("x-ratelimit-requests-limit", "Unknown")
        try:
            used = int(limit) - int(remaining)
        except (ValueError, TypeError):
            used = "Unknown"
        write_quota("football", {"remaining": remaining, "used": used, "limit": limit})

    # ── Public API (matches src.odds_engine.OddsApiEngine signatures) ────────

    def get_competition_odds(self, competition=None, market: str = "h2h,totals") -> list[dict]:
        comp = get_competition(competition)
        if comp.id == "wc2026":
            return self.get_world_cup_odds(market=market, sport_key=comp.odds_api_sport_key)
        league = self.EPL_LEAGUE_ID if comp.id == "epl2026" else self.UCL_LEAGUE_ID
        return self.get_world_cup_odds(
            market=market, sport_key=comp.odds_api_sport_key,
            league_id=league, season=int(comp.season.split("/", 1)[0]),
        )

    get_odds = get_competition_odds

    def get_world_cup_odds(self, market: str = "h2h", sport_key: str = "soccer_fifa_world_cup", *, league_id=None, season=None) -> list[dict]:
        """
        Two requests: /fixtures (for team names + kickoff time) and /odds (for
        bookmaker quotes). Merged + normalized into the legacy Odds-API shape:

            {
              id, sport_key, commence_time,
              home_team, away_team,
              bookmakers: [{key, title, markets: [{key, outcomes: [{name, price, point?}]}]}]
            }
        """
        fixtures_resp = self._request("/fixtures", {
            "league": self.WC_LEAGUE_ID if league_id is None else league_id,
            "season": self.SEASON if season is None else season,
        })
        fixtures_by_id = {f["fixture"]["id"]: f for f in fixtures_resp.get("response", [])}

        odds_resp = self._request("/odds", {
            "league": self.WC_LEAGUE_ID if league_id is None else league_id,
            "season": self.SEASON if season is None else season,
        })

        out = []
        for odd in odds_resp.get("response", []):
            fid = (odd.get("fixture") or {}).get("id")
            fixture = fixtures_by_id.get(fid)
            if not fixture:
                continue
            normalized = self._normalize_odds_entry(fixture, odd, sport_key=sport_key)
            if normalized:
                # Attach team IDs so we can use them for H2H later
                normalized["home_team_id"] = fixture.get("teams", {}).get("home", {}).get("id")
                normalized["away_team_id"] = fixture.get("teams", {}).get("away", {}).get("id")
                out.append(normalized)
        return out

    def get_lineup(self, fixture_id: str, commence_time: str) -> dict:
        """
        Fetches lineups if commence_time is within 60 mins. Caches the result.
        Compares starting XI to the last known starting XI to find missing players.
        """
        cache_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'lineups_cache.json')
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}
            
        if str(fixture_id) in self._lineup_mem_cache:
            return self._lineup_mem_cache[str(fixture_id)]

        if str(fixture_id) in cache:
            self._lineup_mem_cache[str(fixture_id)] = cache[str(fixture_id)]
            return cache[str(fixture_id)]

        # Check if within 60 mins of kickoff
        try:
            kickoff = datetime.strptime(commence_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            # Fetch if within 65 minutes
            if (kickoff - now).total_seconds() > 3900:
                return {} # Too early
        except Exception:
            return {}
            
        resp = self._request("/fixtures/lineups", {"fixture": fixture_id})
        lineups = resp.get("response", [])
        if not lineups:
            return {}
            
        result = {}
        for team_lineup in lineups:
            team_name = team_lineup.get("team", {}).get("name")
            starters = {str(p["player"]["id"]): p["player"]["name"] for p in team_lineup.get("startXI", [])}
            
            # Find last lineup for this team in cache
            last_starters = {}
            # Sort keys so we find the most recently cached fixture (assumes ordered dict behavior)
            for cached_fid, cached_data in cache.items():
                if team_name in cached_data:
                    last_starters = cached_data[team_name].get("starters", {})
                    
            missing = []
            if last_starters:
                for pid, pname in last_starters.items():
                    if str(pid) not in starters:
                        missing.append(pname)
                        
            result[team_name] = {
                "starters": starters,
                "missing": missing
            }
            
        cache[str(fixture_id)] = result
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4)
            
        return result

    def get_h2h(self, team1_id: int, team2_id: int) -> dict:
        """
        Fetches deep H2H history. Caches permanently to save quota.
        """
        if not team1_id or not team2_id:
            return {}
        key = f"{min(team1_id, team2_id)}-{max(team1_id, team2_id)}"
        if key in self._h2h_mem_cache:
            return self._h2h_mem_cache[key]

        cache_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'h2h_cache.json')
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}

        if key in cache:
            self._h2h_mem_cache[key] = cache[key]
            return cache[key]
            
        resp = self._request("/fixtures/headtohead", {"h2h": key})
        fixtures = resp.get("response", [])
        
        w1 = w2 = d = 0
        for fix in fixtures:
            teams = fix.get("teams", {})
            goals = fix.get("goals", {})
            h_id = teams.get("home", {}).get("id")
            a_id = teams.get("away", {}).get("id")
            hg = goals.get("home")
            ag = goals.get("away")
            if hg is None or ag is None: continue
            
            if hg > ag:
                if h_id == team1_id: w1 += 1
                elif h_id == team2_id: w2 += 1
            elif ag > hg:
                if a_id == team1_id: w1 += 1
                elif a_id == team2_id: w2 += 1
            else:
                d += 1
                
        res = {str(team1_id): w1, str(team2_id): w2, "draws": d}
        cache[key] = res
        self._h2h_mem_cache[key] = res
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4)

        return res

    def get_event_odds(self, event_id: str, market: str = "totals") -> dict:
        """
        Compatibility shim — API-Football already returns Match Winner + Goals
        Over/Under in the same /odds payload, so a separate per-event call is
        unnecessary. Returning the cached entry from /odds keeps the legacy
        _fetch_or_cache_totals code path happy if any caller still uses it.
        """
        resp = self._request("/odds", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
            "fixture": event_id,
        })
        entries = resp.get("response", [])
        if not entries:
            return {"bookmakers": []}
        odd = entries[0]
        fid = (odd.get("fixture") or {}).get("id")

        # Need the fixture for team names — minimal call
        fix_resp = self._request("/fixtures", {"id": fid})
        fixtures = fix_resp.get("response", [])
        if not fixtures:
            return {"bookmakers": []}
        normalized = self._normalize_odds_entry(fixtures[0], odd)
        return normalized or {"bookmakers": []}

    def get_standings(self) -> list[dict]:
        """Fetch WC group standings. Returns the raw API-Football response array."""
        resp = self._request("/standings", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
        })
        return resp.get("response", [])

    def get_completed_scores(self, days_from: int = 3) -> list[dict]:
        """
        Finished WC fixtures within the last `days_from` days, normalized into
        the legacy Odds-API scores shape: {id, completed, home_team, away_team,
        commence_time, scores: [{name, score}]}.
        """
        to_dt = datetime.now(timezone.utc).date()
        from_dt = to_dt - timedelta(days=days_from)
        resp = self._request("/fixtures", {
            "league": self.WC_LEAGUE_ID,
            "season": self.SEASON,
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
        })
        out = []
        for m in resp.get("response", []):
            fixture = m.get("fixture") or {}
            teams = m.get("teams") or {}
            goals = m.get("goals") or {}
            status = (fixture.get("status") or {}).get("short")
            completed = status in ("FT", "AET", "PEN")
            home = (teams.get("home") or {}).get("name")
            away = (teams.get("away") or {}).get("name")
            if not home or not away:
                continue
            out.append({
                "id": str(fixture.get("id", "")),
                "completed": completed,
                "home_team": home,
                "away_team": away,
                "commence_time": fixture.get("date", ""),
                "round": (m.get("league") or {}).get("round", ""),
                "scores": (
                    [
                        {"name": home, "score": str(goals.get("home"))},
                        {"name": away, "score": str(goals.get("away"))},
                    ]
                    if completed and goals.get("home") is not None and goals.get("away") is not None
                    else None
                ),
            })
        return out

    # ── Internal normalizers ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_odds_entry(fixture: dict, odd: dict, sport_key: str = "soccer_fifa_world_cup") -> dict | None:
        teams = fixture.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        fixture_meta = fixture.get("fixture") or {}
        if not home or not away or not fixture_meta.get("id"):
            return None

        legacy_bookies = []
        for b in odd.get("bookmakers", []):
            markets = []
            h2h_outcomes = []
            totals_outcomes = []
            for bet in b.get("bets", []):
                bid = bet.get("id")
                if bid == 1:  # Match Winner
                    for v in bet.get("values", []):
                        try:
                            price = float(v["odd"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        nm = v.get("value")
                        if nm == "Home":
                            h2h_outcomes.append({"name": home, "price": price})
                        elif nm == "Draw":
                            h2h_outcomes.append({"name": "Draw", "price": price})
                        elif nm == "Away":
                            h2h_outcomes.append({"name": away, "price": price})
                elif bid == 5:  # Goals Over/Under
                    for v in bet.get("values", []):
                        try:
                            price = float(v["odd"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        nm = v.get("value", "")
                        if nm == "Over 2.5":
                            totals_outcomes.append({"name": "Over", "price": price, "point": 2.5})
                        elif nm == "Under 2.5":
                            totals_outcomes.append({"name": "Under", "price": price, "point": 2.5})
            if h2h_outcomes:
                markets.append({"key": "h2h", "outcomes": h2h_outcomes})
            if totals_outcomes:
                markets.append({"key": "totals", "outcomes": totals_outcomes})
            if markets:
                legacy_bookies.append({
                    "key": str(b.get("id", "")) or b.get("name", "unknown"),
                    "title": b.get("name", ""),
                    "markets": markets,
                })

        return {
            "id": str(fixture_meta["id"]),
            "sport_key": sport_key,
            "commence_time": fixture_meta.get("date", ""),
            "home_team": home,
            "away_team": away,
            "bookmakers": legacy_bookies,
            "round": (fixture.get("league") or {}).get("round", ""),
        }
