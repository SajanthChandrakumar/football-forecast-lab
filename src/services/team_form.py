"""API-Football client and competition-scoped team-form cache."""

from collections import deque
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import re
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests

from src.competitions import competition_document_id, get_competition
from src.constants import TEAM_MAPPING
from src.quota_store import write_quota
from src import quota_store

CLUB_FORM_REFRESH_DEADLINE_SECONDS = 45
CLUB_FORM_REFRESH_WORKERS = 16
_CLUB_FORM_REFRESH_EXECUTOR = ThreadPoolExecutor(
    max_workers=CLUB_FORM_REFRESH_WORKERS,
    thread_name_prefix="club-form-refresh",
)


class ApiFootballClient:
    BASE_URL = "https://v3.football.api-sports.io"
    provider = "api_football"

    def __init__(
        self, api_key, request_fn=None, *, cache_collection=None, competition="ucl2026",
        now_fn=None, monotonic_fn=None, wall_time_fn=None, sleep_fn=None, min_interval_seconds=7,
    ):
        if not api_key:
            raise ValueError("API-Football API key is required")
        self.api_key = api_key
        self.request_fn = request_fn or requests.get
        self.cache_collection = cache_collection
        self.competition = get_competition(competition)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.monotonic_fn = monotonic_fn or time.monotonic
        self.wall_time_fn = wall_time_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self.min_interval_seconds = min_interval_seconds
        self._request_times = deque()

    def request(self, path, params=None):
        if self.cache_collection is None:
            self._pace()
            return self._send(path, params)
        with self._request_gate():
            self._reserve_and_pace()
            return self._send(path, params)

    def _send(self, path, params):
        # /fixtures rejects page=1; it is only the daily reader's first-page marker.
        if path.strip("/") == "fixtures" and params and params.get("page") == 1:
            params = {key: value for key, value in params.items() if key != "page"}
        delay = quota_store.reserve_request("football", now=self.wall_time_fn())
        if delay:
            self.sleep_fn(delay)
        response = self.request_fn(
            f"{self.BASE_URL}/{path.lstrip('/')}",
            headers={"x-apisports-key": self.api_key},
            params=params or {},
            timeout=10,
        )
        self._record_quota(response.headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("API-Football returned an invalid JSON payload")
        if payload.get("errors"):
            raise RuntimeError(f"API-Football error: {payload['errors']}")
        return payload

    @contextmanager
    def _request_gate(self):
        document_id = competition_document_id(self.competition, "team_form_request_gate")
        token = uuid4().hex
        while True:
            now = self.wall_time_fn()
            lease = {"_id": document_id, "competition": self.competition.id,
                     "lease_token": token, "lease_until": now + 120}
            try:
                self.cache_collection.insert_one(lease)
                break
            except Exception:
                existing = self.cache_collection.find_one({"_id": document_id})
                if existing is None:
                    raise
                expiry = existing.get("lease_until", 0)
                if expiry <= now:
                    result = self.cache_collection.update_one(
                        {"_id": document_id, "lease_token": existing.get("lease_token"),
                         "lease_until": expiry},
                        {"$set": {"competition": self.competition.id,
                                  "lease_token": token, "lease_until": now + 120}},
                        upsert=False,
                    )
                    if result.matched_count:
                        break
                else:
                    self.sleep_fn(min(expiry - now, 1))
        try:
            yield
        finally:
            self.cache_collection.delete_one({"_id": document_id, "lease_token": token})

    def _reserve_and_pace(self):
        document_id = competition_document_id(self.competition, "team_form_sync")
        state = self.cache_collection.find_one({"_id": document_id}) or {}
        date = self.now_fn().astimezone(timezone.utc).date().isoformat()
        count = int(state.get("api_requests_count") or 0) if state.get("api_requests_date") == date else 0
        if count >= 100:
            raise RuntimeError("API-Football daily budget of 100 requests exhausted")
        now = self.wall_time_fn()
        timestamps = [at for at in state.get("api_request_timestamps", []) if 0 <= now - at < 60]
        delay = max(
            self.min_interval_seconds - (now - timestamps[-1]) if timestamps else 0,
            60 - (now - timestamps[0]) if len(timestamps) >= 9 else 0,
        )
        if delay > 0:
            self.sleep_fn(delay)
            now = self.wall_time_fn()
            timestamps = [at for at in timestamps if 0 <= now - at < 60]
        self.cache_collection.update_one(
            {"_id": document_id},
            {"$set": {
                "competition": self.competition.id,
                "api_requests_date": date,
                "api_requests_count": count + 1,
                "api_request_timestamps": timestamps + [now],
            }},
            upsert=True,
        )

    def _pace(self):
        now = self.monotonic_fn()
        while self._request_times and now - self._request_times[0] >= 60:
            self._request_times.popleft()
        delay = max(
            self.min_interval_seconds - (now - self._request_times[-1]) if self._request_times else 0,
            60 - (now - self._request_times[0]) if len(self._request_times) >= 9 else 0,
        )
        if delay > 0:
            self.sleep_fn(delay)
            now = self.monotonic_fn()
            while self._request_times and now - self._request_times[0] >= 60:
                self._request_times.popleft()
        self._request_times.append(now)

    @staticmethod
    def _record_quota(headers):
        remaining = headers.get("x-ratelimit-requests-remaining", "Unknown")
        limit = headers.get("x-ratelimit-requests-limit", "Unknown")
        try:
            used = int(limit) - int(remaining)
        except (TypeError, ValueError):
            used = "Unknown"
        write_quota("football", {"remaining": remaining, "used": used, "limit": limit})


class EspnTeamFormClient:
    """Public ESPN fallback normalized to the API-Football response boundary."""

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    def __init__(self, request_fn=None, *, season=2026, competition="ucl2026", enable_fotmob_fallback=False):
        self.request_fn = request_fn or requests.get
        self.season = int(season)
        self.competition = get_competition(competition)
        # Kept as a constructor compatibility argument; form rows use ESPN IDs only.
        self.enable_fotmob_fallback = False
        self.provider = "espn"
        self.provider_namespace = "espn:team-id"
        self._team_names = {}

    def request(self, path, params=None):
        params = params or {}
        self.provider = "espn"
        if path == "/teams":
            season = int(params.get("season", self.season))
            payload = self._get(
                f"{self.BASE_URL}/{self.competition.espn_slug}/scoreboard",
                {"dates": str(season), "limit": 1000},
            )
            teams = {}
            fixture_index = {}
            for event in payload.get("events", []) or []:
                if (event.get("season") or {}).get("year") != season:
                    continue
                competition = (event.get("competitions") or [{}])[0]
                home = next((item for item in competition.get("competitors", []) or []
                             if item.get("homeAway") == "home"), None)
                away = next((item for item in competition.get("competitors", []) or []
                             if item.get("homeAway") == "away"), None)
                for competitor in competition.get("competitors", []) or []:
                    team = competitor.get("team") or {}
                    team_id = team.get("id")
                    name = team.get("displayName") or team.get("name")
                    if team_id is None or not name:
                        continue
                    teams[str(team_id)] = {"team": {
                        "id": str(team_id),
                        "name": name,
                        "logo": self._logo(team),
                        "provider": "espn",
                        "provider_namespace": self.provider_namespace,
                    }}
                    self._team_names[str(team_id)] = name
                if home and away and event.get("id"):
                    home_team = home.get("team") or {}
                    away_team = away.get("team") or {}
                    home_id = home_team.get("id")
                    away_id = away_team.get("id")
                    if home_id is not None and away_id is not None:
                        fixture_index[str(event["id"])] = {
                            "home_id": str(home_id), "away_id": str(away_id),
                        }
            return {
                "response": list(teams.values()), "fixture_index": fixture_index,
                "events": payload.get("events", []) or [],
                "paging": {"current": 1, "total": 1},
            }

        if path != "/fixtures":
            raise ValueError(f"Unsupported ESPN team-form path: {path}")
        if params.get("team") is not None:
            team_id = str(params["team"])
            season = int(params.get("season", self.season))
            payload = self._get(
                f"{self.BASE_URL}/all/teams/{team_id}/schedule",
                {"season": season, "limit": 1000},
            )
            events = payload.get("events", []) or []
            response = [item for event in events if (item := self._normalize_event(event))]
            return {"response": response, "paging": {"current": 1, "total": 1}}
        elif params.get("date"):
            payload = self._get(
                f"{self.BASE_URL}/all/scoreboard",
                {"dates": str(params["date"]).replace("-", ""), "limit": 1000},
            )
        else:
            raise ValueError("ESPN fixtures request requires team or date")
        events = payload.get("events", []) or []
        return {
            "response": [item for event in events if (item := self._normalize_event(event))],
            "paging": {"current": 1, "total": 1},
        }

    def _get(self, url, params):
        response = self.request_fn(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("ESPN returned an invalid JSON payload")
        return payload

    @staticmethod
    def _logo(team):
        if team.get("logo"):
            return team["logo"]
        logos = team.get("logos") or []
        return logos[0].get("href") if logos and isinstance(logos[0], dict) else None

    @staticmethod
    def _competition_name(event, competition):
        league = event.get("league") or competition.get("league") or {}
        name = str(league.get("name") or "") if isinstance(league, dict) else ""
        if name:
            return name.strip()
        name = str((event.get("season") or {}).get("displayName") or "")
        if not name:
            name = str(competition.get("altGameNote") or "").split(",", 1)[0]
        return re.sub(r"^\d{4}(?:-\d{2,4})?\s+", "", name).strip()

    @classmethod
    def _normalize_event(cls, event):
        competition = (event.get("competitions") or [{}])[0]
        league = event.get("league") or competition.get("league") or {}
        if not isinstance(league, dict):
            league = {}
        competitors = competition.get("competitors") or []
        home = next((item for item in competitors if item.get("homeAway") == "home"), None)
        away = next((item for item in competitors if item.get("homeAway") == "away"), None)
        if not home or not away:
            return None
        status_type = (competition.get("status") or {}).get("type") or {}
        detail = str(status_type.get("detail") or status_type.get("shortDetail") or "").upper()
        if not status_type.get("completed"):
            status = detail
        elif "PEN" in detail:
            status = "PEN"
        elif "AET" in detail:
            status = "AET"
        elif detail in {"FT", "FULL TIME", "FINAL"} or "FULL TIME" in detail:
            status = "FT"
        else:
            status = detail

        def team_node(competitor):
            team = competitor.get("team") or {}
            team_id = team.get("id")
            return {
                "id": str(team_id) if team_id is not None else None,
                "name": team.get("displayName") or team.get("name"),
                "logo": cls._logo(team),
                "winner": competitor.get("winner"),
            }

        def score(competitor):
            value = competitor.get("score")
            return value.get("value") if isinstance(value, dict) else value

        home_penalty = home.get("shootoutScore") or home.get("penaltyScore")
        away_penalty = away.get("shootoutScore") or away.get("penaltyScore")
        line_scores = [
            (item.get("value") if isinstance(item, dict) else item)
            for item in (home.get("linescores") or [])
        ]
        away_line_scores = [
            (item.get("value") if isinstance(item, dict) else item)
            for item in (away.get("linescores") or [])
        ]

        def total(values):
            try:
                return sum(int(value) for value in values)
            except (TypeError, ValueError):
                return None

        score_90 = None
        if len(line_scores) >= 2 and len(away_line_scores) >= 2:
            home_90, away_90 = total(line_scores[:2]), total(away_line_scores[:2])
            if home_90 is not None and away_90 is not None:
                score_90 = {"home": home_90, "away": away_90}
        goals = {"home": score(home), "away": score(away)}
        score_aet = goals if status in {"AET", "PEN"} else None
        league_uid = str(competition.get("uid") or event.get("uid") or "")
        uid_league = re.search(r"(?:^|~)l:([^~]+)", league_uid)
        league_id = league.get("id") or league.get("slug") or (uid_league.group(1) if uid_league else None)
        league_name = cls._competition_name(event, competition)
        league_type = league.get("type") or competition.get("type") or ""
        if isinstance(league_type, dict):
            league_type = league_type.get("name") or league_type.get("text") or ""
        return {
            "fixture": {
                "id": str(event.get("id") or competition.get("id")),
                "date": event.get("date") or competition.get("date"),
                "status": {"short": status, "cancelled": bool(status_type.get("cancelled"))},
            },
            "league": {
                "id": str(league_id) if league_id is not None else None,
                "slug": league.get("slug"), "name": league_name, "type": league_type,
            },
            "teams": {"home": team_node(home), "away": team_node(away)},
            "goals": goals,
            "score": {
                "penalty": {"home": home_penalty, "away": away_penalty},
                **({"fulltime": score_90} if score_90 is not None else {}),
                **({"extratime": score_aet} if score_aet is not None else {}),
            },
        }


class FailoverTeamFormClient:
    """Use API-Football first, then remember ESPN when plan access is denied."""

    provider = "api_football"

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self._fallback_only = primary is None

    def request(self, path, params=None):
        if not self._fallback_only:
            try:
                payload = self.primary.request(path, params)
                self.provider = getattr(self.primary, "provider", "api_football")
                return payload
            except RuntimeError as exc:
                if "plan" not in str(exc).casefold():
                    raise
                self._fallback_only = True
        payload = self.fallback.request(path, params)
        self.provider = getattr(self.fallback, "provider", "espn")
        return payload


class TeamFormService:
    ALLOWED_STATUSES = {"FT", "AET", "PEN"}
    FORM_LIMIT = 10
    HISTORY_BACKFILL_TEAMS_PER_DAY = 6
    VALIDATION_VERSION = "senior-men-v1"
    EXPECTED_CLUB_TEAM_COUNTS = {"epl2026": 20, "ucl2026": 36}
    PROVIDER_NAMESPACES = {
        "espn": "espn:team-id",
        "api_football": "api_football:team-id",
    }
    ESPN_SENIOR_COMPETITION_KINDS = {
        # Senior domestic leagues observed in current EPL/UCL club schedules.
        "eng.1": "league", "esp.1": "league", "ita.1": "league",
        "ger.1": "league", "fra.1": "league", "ned.1": "league",
        "por.1": "league", "tur.1": "league", "gre.1": "league",
        "aut.1": "league", "bel.1": "league", "nor.1": "league",
        # Other explicitly named senior top-flight leagues.
        "sco.1": "league", "sui.1": "league", "ukr.1": "league",
        "cze.1": "league", "den.1": "league", "swe.1": "league",
        "pol.1": "league", "cro.1": "league", "srb.1": "league",
        "rou.1": "league", "bra.1": "league", "arg.1": "league",
        "usa.1": "league", "mex.1": "league", "jpn.1": "league",
        "kor.1": "league", "aus.1": "league", "ksa.1": "league",
        "rus.1": "league",
        # Senior men's domestic cups and super cups; invitational friendlies
        # such as Joan Gamper and Emirates Cup are deliberately absent.
        "eng.fa": "cup", "eng.league_cup": "cup", "eng.charity": "cup",
        "esp.copa_del_rey": "cup",
        "ita.coppa_italia": "cup", "ger.dfb_pokal": "cup",
        "ger.super_cup": "cup", "fra.coupe_de_france": "cup",
        "fra.super_cup": "cup", "ned.supercup": "cup",
        # UEFA men's club competitions.
        "uefa.champions": "europe", "uefa.champions_qual": "europe",
        "uefa.europa": "europe", "uefa.europa_qual": "europe",
        "uefa.europa.conf": "europe", "uefa.europa.conf_qual": "europe",
        "uefa.super_cup": "europe",
    }
    ESPN_COMPETITION_SLUG_BY_ID = {
        "700": "eng.1", "740": "esp.1", "730": "ita.1", "720": "ger.1",
        "710": "fra.1", "725": "ned.1", "715": "por.1", "3946": "tur.1",
        "3955": "gre.1", "3907": "aut.1", "3901": "bel.1", "3960": "nor.1",
        "3918": "eng.fa", "3920": "eng.league_cup", "5329": "eng.charity",
        "3951": "esp.copa_del_rey", "3952": "fra.coupe_de_france",
        "3954": "ger.dfb_pokal", "3956": "ita.coppa_italia", "8357": "fra.super_cup",
        "8101": "ger.super_cup", "10749": "ned.supercup",
        "775": "uefa.champions", "776": "uefa.europa",
        "19874": "uefa.champions_qual", "5462": "uefa.super_cup",
        "20296": "uefa.europa.conf", "20221": "uefa.europa.conf_qual",
    }

    def __init__(self, cache_collection, client, competition="ucl2026", now_fn=None, history_client=None):
        self.cache_collection = cache_collection
        self.client = client
        self.history_client = history_client or getattr(client, "fallback", None) or client
        self.competition = get_competition(competition)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _id(self, key):
        return competition_document_id(self.competition, key)

    def _provider(self):
        return getattr(self.client, "provider", "api_football") if self.client is not None else "api_football"

    def parse_teams(self, payload, *, provider=None):
        teams = {}
        provider = provider or self._provider()
        namespace = self.PROVIDER_NAMESPACES.get(provider)
        if namespace is None:
            return []
        for item in payload.get("response", []) or []:
            team = item.get("team") or item
            team_id = team.get("id")
            if team_id is None or not team.get("name"):
                continue
            team_id = str(team_id)
            teams[team_id] = {
                "team_id": team_id,
                "name": team["name"],
                "country": team.get("country"),
                "logo": team.get("logo"),
                "provider": provider,
                "provider_namespace": namespace,
            }
        return list(teams.values())

    def store_teams(self, teams, *, provider=None, fixture_index=None, observed_at=None):
        normalized = [dict(team) for team in teams]
        observed_at = observed_at or self.now_fn().isoformat()
        provider = provider or self._provider()
        values = {
            "competition": self.competition.id, "teams": normalized,
            "status": "fresh", "source": provider, "provider": provider,
            "provider_namespace": self.PROVIDER_NAMESPACES.get(provider),
            "observed_at": observed_at, "last_attempt_at": observed_at,
            "last_successful_at": observed_at, "coverage": {"teams": len(normalized)},
            "error": None,
        }
        if fixture_index is not None:
            values["fixture_index"] = fixture_index
        self.cache_collection.update_one(
            {"_id": self._id("team_form_teams")},
            {"$set": values},
            upsert=True,
        )
        return normalized

    @staticmethod
    def _pair_score(value):
        if not isinstance(value, dict):
            return None
        pair = {}
        for side in ("home", "away"):
            number = value.get(side)
            if isinstance(number, dict):
                number = number.get("total") or number.get("value")
            try:
                pair[side] = int(number)
            except (TypeError, ValueError):
                return None
        return pair

    @staticmethod
    def _competition_details(league, *, provider=None):
        if not isinstance(league, dict):
            return None
        name = str(league.get("name") or "").strip()
        raw_id = league.get("id")
        competition_id = str(raw_id) if raw_id is not None else ""
        if not name or not competition_id:
            return None
        name_check = name.casefold()
        if re.search(r"women|female|fem(en|in)|ladies|girls|frauen|\bliga\s*f\b|\bu\s?-?\d{2}\b|under[- ]?\d{2}|youth|junior|academy|development league|premier league\s+2|\bpl2\b|reserves?|\bb team\b|friendl|preseason", name_check):
            return None
        slug = str(league.get("slug") or "").strip().casefold()
        id_slug = (
            TeamFormService.ESPN_COMPETITION_SLUG_BY_ID.get(competition_id)
            if provider in (None, "espn") else None
        )
        if not slug:
            slug = id_slug or (
                competition_id if competition_id in TeamFormService.ESPN_SENIOR_COMPETITION_KINDS else ""
            )
        if not slug or slug not in TeamFormService.ESPN_SENIOR_COMPETITION_KINDS:
            return None
        if id_slug and id_slug != slug:
            return None
        if competition_id in TeamFormService.ESPN_SENIOR_COMPETITION_KINDS and competition_id != slug:
            return None
        kind = TeamFormService.ESPN_SENIOR_COMPETITION_KINDS[slug]
        return competition_id, name, kind, slug

    @staticmethod
    def _time(value):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

    def parse_fixtures(self, team_id, payload, *, team_name=None, provider=None, now=None):
        team_id = str(team_id)
        provider = provider or self._provider()
        provider_namespace = self.PROVIDER_NAMESPACES.get(provider)
        if provider_namespace is None:
            return []
        current = now or self.now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        by_fixture = {}
        for item in payload.get("response", []) or []:
            fixture = item.get("fixture") or {}
            league = item.get("league") or {}
            teams = item.get("teams") or {}
            goals = item.get("goals") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            status = str((fixture.get("status") or {}).get("short") or "").upper()
            if status not in self.ALLOWED_STATUSES or (fixture.get("status") or {}).get("cancelled"):
                continue
            details = self._competition_details(league, provider=provider)
            if details is None:
                continue
            home_id = str(home.get("id")) if home.get("id") is not None else None
            away_id = str(away.get("id")) if away.get("id") is not None else None
            home_matches = home_id == team_id
            away_matches = away_id == team_id
            if home_matches and away_id and away.get("name"):
                opponent, venue = away, "home"
                goals_for, goals_against = goals.get("home"), goals.get("away")
            elif away_matches and home_id and home.get("name"):
                opponent, venue = home, "away"
                goals_for, goals_against = goals.get("away"), goals.get("home")
            else:
                continue

            fixture_id = fixture.get("id")
            played_at = fixture.get("date")
            opponent_id = opponent.get("id")
            if fixture_id is None or not played_at or opponent_id is None or not opponent.get("name"):
                continue
            kickoff = self._time(played_at)
            if kickoff is None or kickoff > current:
                continue
            try:
                goals_for, goals_against = int(goals_for), int(goals_against)
            except (TypeError, ValueError):
                continue
            result_for, result_against = goals_for, goals_against
            score_data = item.get("score") or {}
            penalty_score = self._pair_score(
                item.get("penalties") or score_data.get("penalty")
            )
            if status == "PEN":
                side = "home" if venue == "home" else "away"
                other_side = "away" if side == "home" else "home"
                if penalty_score:
                    result_for, result_against = penalty_score[side], penalty_score[other_side]
                elif home.get("winner") is True and away.get("winner") is not True:
                    result_for, result_against = (1, 0) if venue == "home" else (0, 1)
                elif away.get("winner") is True and home.get("winner") is not True:
                    result_for, result_against = (0, 1) if venue == "home" else (1, 0)
                else:
                    continue
            result = "W" if result_for > result_against else "D" if result_for == result_against else "L"
            competition_id, competition_name, competition_kind, competition_slug = details
            row = {
                "fixture_id": str(fixture_id),
                "played_at": str(played_at),
                "competition_name": competition_name,
                "competition_id": competition_id,
                "competition_slug": competition_slug,
                "competition_kind": competition_kind,
                "opponent_id": str(opponent_id),
                "opponent_name": opponent["name"],
                "venue": venue,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "score": f"{goals_for}:{goals_against}",
                "result": result,
                "home_id": home_id,
                "home_team": str(home.get("name") or ""),
                "home_logo": home.get("logo"),
                "away_id": away_id,
                "away_team": str(away.get("name") or ""),
                "away_logo": away.get("logo"),
                "result_type": status,
                "provider": provider,
                "provider_namespace": provider_namespace,
                "identity_verified": True,
            }
            for field, raw in (
                ("score_90", item.get("score_90") or score_data.get("fulltime")),
                ("score_aet", item.get("score_aet") or score_data.get("extratime")),
                ("penalties", item.get("penalties") or score_data.get("penalty")),
            ):
                pair = self._pair_score(raw)
                if pair is not None:
                    row[field] = pair
            by_fixture[str(fixture_id)] = row
        return self._latest(list(by_fixture.values()))

    def merge_matches(self, team_id, matches, observed_at=None, provider=None):
        team_id = str(team_id)
        document_id = self._id(f"team_form:{team_id}")
        existing = self.cache_collection.find_one({"_id": document_id}) or {}
        by_fixture = {}
        provider = provider or self._provider()
        provider_namespace = self.PROVIDER_NAMESPACES.get(provider)
        raw_legacy = list(existing.get("raw_legacy_matches") or [])
        for match in existing.get("matches", []) or []:
            if not self._verified_match(match, provider_namespace, team_id=team_id):
                raw_legacy.append(match)
                continue
            by_fixture[str(match["fixture_id"])] = dict(match)
        for match in matches:
            if self._verified_match(match, provider_namespace, team_id=team_id):
                by_fixture[str(match["fixture_id"])] = dict(match)
        latest = self._latest(list(by_fixture.values()))
        observed_at = observed_at or self.now_fn().isoformat()
        if not latest:
            values = {
                "competition": self.competition.id,
                "team_id": team_id,
                "matches": [],
                "status": "stale" if existing.get("last_successful_at") else "unavailable",
                "source": provider,
                "provider": provider,
                "provider_namespace": provider_namespace,
                "scope": "all_competitions",
                "validation_version": self.VALIDATION_VERSION,
                "last_attempt_at": observed_at,
                "coverage": {"available": 0, "required": self.FORM_LIMIT, "complete": False},
                "error": "No verified competitive senior men's matches available",
            }
            if raw_legacy:
                values["raw_legacy_matches"] = raw_legacy
            self.cache_collection.update_one(
                {"_id": document_id}, {"$set": values}, upsert=True,
            )
            return []
        status = "fresh"
        values = {
            "competition": self.competition.id,
            "team_id": team_id,
            "matches": latest,
            "status": status,
            "source": provider,
            "provider": provider,
            "provider_namespace": provider_namespace,
            "scope": "all_competitions",
            "validation_version": self.VALIDATION_VERSION,
            "observed_at": observed_at,
            "last_attempt_at": observed_at,
            "last_successful_at": observed_at,
            "coverage": {
                "available": len(latest), "required": self.FORM_LIMIT,
                "complete": len(latest) >= self.FORM_LIMIT,
            },
            "error": None,
        }
        if raw_legacy:
            values["raw_legacy_matches"] = raw_legacy
        self.cache_collection.update_one(
            {"_id": document_id},
            {"$set": values},
            upsert=True,
        )
        return latest

    @staticmethod
    def _verified_match(match, provider_namespace=None, *, team_id=None):
        if not (
            isinstance(match, dict)
            and match.get("identity_verified") is True
            and match.get("provider_namespace") in TeamFormService.PROVIDER_NAMESPACES.values()
            and (provider_namespace is None or match.get("provider_namespace") == provider_namespace)
            and match.get("fixture_id") is not None
            and match.get("home_id") is not None
            and match.get("away_id") is not None
            and match.get("competition_id") is not None
            and match.get("competition_kind") in {"league", "cup", "europe"}
            and match.get("provider_namespace") == TeamFormService.PROVIDER_NAMESPACES.get(match.get("provider"))
        ):
            return False
        if team_id is not None and str(team_id) not in {str(match.get("home_id")), str(match.get("away_id"))}:
            return False
        details = TeamFormService._competition_details({
            "id": match.get("competition_id"),
            "slug": match.get("competition_slug"),
            "name": match.get("competition_name"),
        }, provider=match.get("provider"))
        return (
            details is not None
            and details[0] == str(match.get("competition_id"))
            and details[2] == match.get("competition_kind")
            and (match.get("competition_slug") is None or details[3] == match.get("competition_slug"))
        )

    def _mark_verified_refresh_failure(self, team_ids, error, observed_at):
        fields = {
            "status": "stale", "error": str(error),
            "last_attempt_at": observed_at, "last_attempt_provider": "espn",
        }
        for team_id in team_ids:
            document_id = self._id(f"team_form:{team_id}")
            if self.cache_collection.find_one({"_id": document_id}) is not None:
                self.cache_collection.update_one({"_id": document_id}, {"$set": fields})
        roster_id = self._id("team_form_teams")
        if self.cache_collection.find_one({"_id": roster_id}) is not None:
            self.cache_collection.update_one({"_id": roster_id}, {"$set": fields})
        sync_id = self._id("team_form_sync")
        # A first-ever failure still needs a throttle timestamp. Keep this
        # failure marker separate from observed_at / last_successful_at, which
        # must continue to describe the last verified refresh only.
        self.cache_collection.update_one(
            {"_id": sync_id},
            {"$set": {"competition": self.competition.id, **fields}},
            upsert=True,
        )

    @staticmethod
    def _fixture_index(payload):
        index = {}
        raw_index = payload.get("fixture_index") or {}
        if isinstance(raw_index, dict):
            for fixture_id, teams in raw_index.items():
                if not isinstance(teams, dict):
                    continue
                home_id, away_id = teams.get("home_id"), teams.get("away_id")
                if fixture_id and home_id is not None and away_id is not None:
                    index[str(fixture_id)] = {"home_id": str(home_id), "away_id": str(away_id)}
        for event in payload.get("events", []) or []:
            normalized = EspnTeamFormClient._normalize_event(event)
            if not normalized:
                continue
            fixture = normalized.get("fixture") or {}
            teams = normalized.get("teams") or {}
            home_id = (teams.get("home") or {}).get("id")
            away_id = (teams.get("away") or {}).get("id")
            if fixture.get("id") and home_id is not None and away_id is not None:
                index[str(fixture["id"])] = {"home_id": str(home_id), "away_id": str(away_id)}
        return index

    def refresh_all_competitions(self, now=None):
        """Refresh verified ESPN senior-men form across each club's competitions."""
        deadline = time.monotonic() + CLUB_FORM_REFRESH_DEADLINE_SECONDS
        current = now or self.now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        observed_at = current.isoformat()
        client = self.history_client
        roster_id = self._id("team_form_teams")
        sync_id = self._id("team_form_sync")
        old_roster = self.cache_collection.find_one({"_id": roster_id}) or {}
        old_sync = self.cache_collection.find_one({"_id": sync_id}) or {}
        previous_observed_at = (
            old_roster.get("last_successful_at")
            or (old_roster.get("observed_at") if old_roster.get("scope") == "all_competitions" else None)
            or old_sync.get("last_successful_at")
            or old_sync.get("observed_at")
        )
        old_team_ids = [
            str(team.get("team_id")) for team in old_roster.get("teams", [])
            if team.get("team_id") is not None
        ]
        if client is None or getattr(client, "provider", None) != "espn":
            error = "A free ESPN provider is required for verified club form"
            self._mark_verified_refresh_failure(old_team_ids, error, observed_at)
            return {
                "status": "stale" if old_roster else "unavailable",
                "source": "espn", "provider": "espn", "provider_calls": 0,
                "error": error, "observed_at": previous_observed_at,
            }
        if hasattr(client, "enable_fotmob_fallback"):
            client.enable_fotmob_fallback = False
        season = int(str(self.competition.season).split("/", 1)[0])
        provider_calls = 0
        roster_future = None
        try:
            if time.monotonic() >= deadline:
                raise FuturesTimeoutError
            provider_calls += 1
            roster_future = _CLUB_FORM_REFRESH_EXECUTOR.submit(
                client.request, "/teams", {"season": season},
            )
            scoreboard = roster_future.result(timeout=max(0, deadline - time.monotonic()))
            if time.monotonic() >= deadline:
                raise FuturesTimeoutError
            if getattr(client, "provider", None) != "espn":
                raise RuntimeError("The club form roster was not returned by ESPN")
            teams = self.parse_teams(scoreboard, provider="espn")
            expected_teams = self.EXPECTED_CLUB_TEAM_COUNTS.get(self.competition.id)
            if expected_teams is None or len(teams) != expected_teams:
                raise RuntimeError(
                    f"ESPN returned {len(teams)} provider-identified teams; "
                    f"expected {expected_teams} for {self.competition.id}"
                )
        except FuturesTimeoutError:
            if roster_future is not None:
                roster_future.cancel()
            error = "ESPN team-roster refresh deadline exceeded"
            self._mark_verified_refresh_failure(old_team_ids, error, observed_at)
            return {
                "status": "stale" if old_roster else "unavailable",
                "source": "espn", "provider": "espn", "provider_calls": provider_calls,
                "error": error, "observed_at": previous_observed_at,
            }
        except Exception as exc:
            self._mark_verified_refresh_failure(old_team_ids, exc, observed_at)
            return {
                "status": "stale" if old_roster else "unavailable",
                "source": "espn", "provider": "espn", "provider_calls": provider_calls,
                "error": str(exc), "observed_at": previous_observed_at,
            }

        namespace = self.PROVIDER_NAMESPACES["espn"]
        fixture_index = self._fixture_index(scoreboard)
        failed = []
        remaining = iter(teams)
        unavailable = 0
        schedule_payloads = {}
        while True:
            batch = []
            for _ in range(CLUB_FORM_REFRESH_WORKERS):
                team = next(remaining, None)
                if team is None:
                    break
                batch.append(team)
            if not batch:
                break
            if time.monotonic() >= deadline:
                failed.extend(str(team["team_id"]) for team in batch)
                failed.extend(str(team["team_id"]) for team in remaining)
                break

            futures = {
                _CLUB_FORM_REFRESH_EXECUTOR.submit(
                    client.request, "/fixtures", {"team": str(team["team_id"]), "season": season},
                ): team
                for team in batch
            }
            provider_calls += len(futures)
            processed = set()
            timed_out = False
            try:
                for future in as_completed(futures, timeout=max(0, deadline - time.monotonic())):
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    processed.add(future)
                    team = futures[future]
                    team_id = str(team["team_id"])
                    try:
                        payload = future.result()
                        if getattr(client, "provider", None) != "espn":
                            raise RuntimeError("The team schedule was not returned by ESPN")
                        schedule_payloads[team_id] = self.parse_fixtures(
                            team_id, payload, provider="espn", now=current,
                        )
                    except Exception as exc:
                        failed.append(team_id)
                        self._mark_verified_refresh_failure([team_id], exc, observed_at)
            except FuturesTimeoutError:
                timed_out = True

            if timed_out:
                for future, team in futures.items():
                    if future in processed:
                        continue
                    future.cancel()
                    team_id = str(team["team_id"])
                    failed.append(team_id)
                    self._mark_verified_refresh_failure(
                        [team_id], "ESPN team-schedule refresh deadline exceeded", observed_at,
                    )
                failed.extend(str(team["team_id"]) for team in remaining)
                break

        failed_set = set(failed)
        for team in teams:
            team_id = str(team["team_id"])
            if team_id in failed_set:
                continue
            document_id = self._id(f"team_form:{team_id}")
            existing = self.cache_collection.find_one({"_id": document_id}) or {}
            raw_legacy = list(existing.get("raw_legacy_matches") or [])
            old_matches = []
            for match in existing.get("matches", []) or []:
                if self._verified_match(match, namespace, team_id=team_id):
                    old_matches.append(dict(match))
                else:
                    raw_legacy.append(match)
            merged = {str(match["fixture_id"]): match for match in old_matches}
            merged.update({str(match["fixture_id"]): match for match in schedule_payloads.get(team_id, [])})
            latest = self._latest(list(merged.values()))
            status = "fresh" if latest else "unavailable"
            if not latest:
                unavailable += 1
            values = {
                "competition": self.competition.id,
                "team_id": team_id,
                "team_name": team["name"],
                "matches": latest,
                "status": status,
                "source": "espn",
                "provider": "espn",
                "provider_namespace": namespace,
                "scope": "all_competitions",
                "validation_version": self.VALIDATION_VERSION,
                "observed_at": observed_at,
                "last_attempt_at": observed_at,
                "last_successful_at": observed_at,
                "coverage": {
                    "available": len(latest), "required": self.FORM_LIMIT,
                    "complete": len(latest) >= self.FORM_LIMIT,
                },
                "error": None if latest else "No completed competitive senior men's matches available",
            }
            if raw_legacy:
                values["raw_legacy_matches"] = raw_legacy
            self.cache_collection.update_one({"_id": document_id}, {"$set": values}, upsert=True)

        state_values = {
            "status": "stale" if failed else "fresh",
            "source": "espn", "provider": "espn",
            "last_attempt_at": observed_at,
            "error": f"Schedule refresh failed for {len(failed)} team(s)" if failed else None,
            "teams_total": len(teams), "teams_failed": len(failed), "teams_unavailable": unavailable,
            "teams_stale": len(failed),
        }
        if not failed:
            state_values.update({"observed_at": observed_at, "last_successful_at": observed_at})
        roster_values = {
            "competition": self.competition.id,
            "teams": teams,
            "fixture_index": fixture_index,
            "provider": "espn",
            "source": "espn",
            "provider_namespace": namespace,
            "scope": "all_competitions",
            "status": "stale" if failed else "fresh",
            "last_attempt_at": observed_at,
            "coverage": {"teams": len(teams)},
            "error": state_values["error"],
        }
        if not failed:
            roster_values.update({"observed_at": observed_at, "last_successful_at": observed_at})
        self.cache_collection.update_one({"_id": roster_id}, {"$set": roster_values}, upsert=True)
        self.cache_collection.update_one(
            {"_id": sync_id},
            {"$set": {"competition": self.competition.id, **state_values}},
            upsert=True,
        )
        return {
            "status": "stale" if failed else "fresh",
            "source": "espn", "provider": "espn", "provider_calls": provider_calls,
            "observed_at": observed_at if not failed else previous_observed_at, "teams": len(teams),
            "teams_failed": len(failed), "teams_unavailable": unavailable,
            **({"error": state_values["error"]} if failed else {}),
        }

    def get_sync_state(self):
        document_id = self._id("team_form_sync")
        return self.cache_collection.find_one({"_id": document_id}) or {
            "_id": document_id,
            "competition": self.competition.id,
        }

    def store_sync_state(self, state):
        values = {
            key: value for key, value in state.items()
            if key not in {"_id", "competition"}
        }
        self.cache_collection.update_one(
            {"_id": self._id("team_form_sync")},
            {"$set": {"competition": self.competition.id, **values}},
            upsert=True,
        )
        return self.get_sync_state()

    def ingest_league_fixtures(self, fixtures, *, now=None):
        """Reuse stored domestic results for form; never call a provider."""
        if self.competition.is_club_competition:
            return {
                "status": "skipped", "source": "cache", "provider_calls": 0,
                "reason": "club_form_requires_verified_all_competitions_refresh",
            }
        current_roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        if current_roster.get("scope") == "all_competitions":
            return {
                "status": "skipped", "source": current_roster.get("provider"),
                "provider_calls": 0, "teams": len(current_roster.get("teams") or []),
                "reason": "all_competitions_form_is_authoritative",
            }
        current = now or self.now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        teams, matches = {}, {}
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            names = [str(fixture.get(f"{side}_team") or "") for side in ("home", "away")]
            if not all(names):
                continue
            ids = [TEAM_MAPPING.get(name, name) for name in names]
            for side, name, team_id in zip(("home", "away"), names, ids):
                teams[team_id] = {"team_id": team_id, "name": name, "logo": fixture.get(f"{side}_logo")}
                matches.setdefault(team_id, [])
            if not fixture.get("completed"):
                continue
            event_id = str(fixture.get("id") or "")
            played_at = str(fixture.get("commence_time") or "")
            score = str(fixture.get("actual_score") or "")
            if not event_id or not re.fullmatch(r"\d+:\d+", score):
                continue
            try:
                kickoff = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
                if kickoff > current:
                    continue
            except ValueError:
                continue
            goals = [int(value) for value in score.split(":")]
            for index, team_id in enumerate(ids):
                scored, conceded = goals[index], goals[1 - index]
                matches[team_id].append({
                    "fixture_id": event_id, "played_at": played_at,
                    "competition_name": self.competition.display_name,
                    "opponent_id": ids[1 - index], "opponent_name": names[1 - index],
                    "venue": "home" if index == 0 else "away",
                    "goals_for": scored, "goals_against": conceded,
                    "score": f"{scored}:{conceded}",
                    "result": "W" if scored > conceded else "D" if scored == conceded else "L",
                    "provider": "espn",
                })
        if not teams:
            return {"status": "unavailable", "source": "espn", "provider_calls": 0, "teams": 0}
        observed = current.isoformat()
        self.cache_collection.update_one(
            {"_id": self._id("team_form_teams")},
            {"$set": {"competition": self.competition.id, "teams": list(teams.values()),
                      "source": "espn", "provider": "espn", "status": "fresh", "observed_at": observed}},
            upsert=True,
        )
        for team_id, results in matches.items():
            latest = self._latest(results)
            self.cache_collection.update_one(
                {"_id": self._id(f"team_form:{team_id}")},
                {"$set": {"competition": self.competition.id, "team_id": team_id,
                          "matches": latest, "source": "espn", "provider": "espn", "scope": "league",
                          "observed_at": observed, "status": "fresh" if latest else "unavailable",
                          "error": None if latest else "No completed league matches available"}},
                upsert=True,
            )
        return {"status": "fresh", "source": "espn", "provider_calls": 0, "teams": len(teams)}

    def cached_form_for_match(
        self, team_name, fallback_team_id=None, *, before=None, fixture_id=None, side=None,
    ) -> dict:
        """Return display-only form data from MongoDB without provider access."""
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        if fallback_team_id is None and fixture_id is not None and side in {"home", "away"}:
            entry = (roster.get("fixture_index") or {}).get(str(fixture_id)) or {}
            fallback_team_id = entry.get(f"{side}_id")
        team_id = self._resolve_team_id(team_name, fallback_team_id, roster)
        document = (
            self.cache_collection.find_one({"_id": self._id(f"team_form:{team_id}")})
            if team_id is not None else None
        ) or {}
        return self._display_form(document, roster, before=before)

    def _match_team_id(self, match, side, roster):
        roster_namespace = roster.get("provider_namespace")
        match_namespace = match.get("provider_namespace")
        if not roster_namespace or match_namespace != roster_namespace:
            return None
        team_id = match.get(f"{side}_team_id") or match.get(f"{side}_id")
        fixture_id = match.get("id") or match.get("fixture_id") or match.get("event_id")
        if team_id is None and fixture_id is not None:
            team_id = ((roster.get("fixture_index") or {}).get(str(fixture_id)) or {}).get(f"{side}_id")
        return self._resolve_team_id(match.get(f"{side}_team"), team_id, roster)

    def cached_forms_for_matches(self, matches):
        """Attach cached form and player trends without provider access."""
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        team_ids = {
            team_id
            for match in matches if isinstance(match, dict)
            for side in ("home", "away")
            if (team_id := self._match_team_id(match, side, roster)) is not None
        }
        documents = {
            str(document["_id"]): document
            for document in self.cache_collection.find({
                "_id": {"$in": [self._id(f"team_form:{team_id}") for team_id in sorted(team_ids)]}
            })
        } if team_ids else {}
        history_ids = {
            str(item.get("fixture_id"))
            for document in documents.values()
            for item in document.get("matches", []) or []
            if item.get("fixture_id") is not None
        }
        history_documents = list(self.cache_collection.find({
            "_id": {"$in": [self._id(f"match_intelligence:{event_id}") for event_id in history_ids]}
        })) if history_ids else []
        history_by_event = {
            str(document.get("event_id") or str(document.get("_id") or "").rsplit(":", 1)[-1]): document
            for document in history_documents
        }
        team_names = {
            str(team.get("team_id")): str(team.get("name") or "")
            for team in roster.get("teams", []) or [] if team.get("team_id") is not None
        }
        verified_times_by_team = {}
        for team_id in team_ids:
            document = documents.get(self._id(f"team_form:{team_id}"), {})
            expected_namespace = roster.get("provider_namespace") or document.get("provider_namespace")
            verified_times_by_team[str(team_id)] = sorted(
                played_at
                for match in document.get("matches", []) or []
                if document.get("scope") == "all_competitions"
                and self._verified_match(match, expected_namespace, team_id=document.get("team_id"))
                and (played_at := self._time(match.get("played_at"))) is not None
            )

        form_cache = {}
        presented = []
        for match in matches:
            if not isinstance(match, dict):
                presented.append(match)
                continue
            row = dict(match)
            kickoff = row.get("commence_time") or row.get("kickoff") or row.get("played_at") or ""
            for side in ("home", "away"):
                team_id = self._match_team_id(row, side, roster)
                document = documents.get(self._id(f"team_form:{team_id}"), {}) if team_id else {}
                cutoff = self._time(kickoff)
                cutoff_count = bisect_left(verified_times_by_team.get(str(team_id), ()), cutoff) if cutoff else 0
                cache_key = (str(team_id) if team_id is not None else None, cutoff_count)
                form = form_cache.get(cache_key)
                if form is None:
                    form = self._display_form(document, roster, before=kickoff)
                    player_document = {**document, "matches": form.get("matches", [])}
                    form["player_form"] = self._player_form(
                        player_document, team_names.get(str(team_id), row.get(f"{side}_team", "")),
                        history_by_event,
                    )
                    form_cache[cache_key] = form
                row[f"{side}_form"] = form
            presented.append(row)
        return presented

    @staticmethod
    def _player_form(document, team_name, history_by_event):
        def contributions(entry):
            stats = {str(name).casefold(): value for name, value in (entry.get("stats") or {}).items()}
            parsed = {}
            for field, keys in (("goals", ("totalgoals", "goals")), ("assists", ("goalassists", "assists"))):
                value = next((stats[key] for key in keys if key in stats), None)
                if isinstance(value, bool):
                    continue
                try:
                    value = int(float(value))
                except (TypeError, ValueError, OverflowError):
                    continue
                if value >= 0:
                    parsed[field] = value
            return parsed

        canonical_team = TEAM_MAPPING.get(str(team_name), str(team_name)).casefold()
        players = {}
        matches_sampled = 0
        for match in TeamFormService._latest(document.get("matches", []) or []):
            history = history_by_event.get(str(match.get("fixture_id"))) or {}
            lineups = ((history.get("data") or {}).get("lineups") or {})
            lineup = next((
                value for name, value in lineups.items()
                if TEAM_MAPPING.get(str(name), str(name)).casefold() == canonical_team
            ), None)
            if not lineup or not lineup.get("starters"):
                continue
            entries = (lineup.get("starters") or []) + (lineup.get("substitutes") or [])
            if not any(contributions(entry) for entry in entries):
                continue
            matches_sampled += 1
            seen = set()
            for started, entries in ((True, lineup.get("starters") or []), (False, lineup.get("substitutes") or [])):
                for entry in entries:
                    name = str(entry.get("name") or "")
                    key = str(entry.get("id") or name.casefold())
                    if not name or key in seen:
                        continue
                    seen.add(key)
                    recorded = contributions(entry)
                    if not started and not any(recorded.values()):
                        continue
                    row = players.setdefault(key, {
                        "id": str(entry.get("id") or ""), "name": name,
                        "appearances": 0, "starts": 0, "goals": 0, "assists": 0,
                        "goals_complete": True, "assists_complete": True,
                    })
                    row["appearances"] += 1
                    row["starts"] += int(started)
                    for field in ("goals", "assists"):
                        if field in recorded:
                            row[field] += recorded[field]
                        else:
                            row[f"{field}_complete"] = False
        ranked_rows = sorted(
            (row for row in players.values() if row["goals"] or row["assists"]),
            key=lambda row: (-row["goals"], -row["assists"], -row["starts"], row["name"]),
        )[:3]
        ranked = [{
            "id": row["id"], "name": row["name"],
            "appearances": row["appearances"], "starts": row["starts"],
            "goals": row["goals"] if row["goals_complete"] else None,
            "assists": row["assists"] if row["assists_complete"] else None,
        } for row in ranked_rows]
        status = "fresh" if matches_sampled >= 3 and ranked_rows else "unavailable"
        result = {
            "status": status, "matches_sampled": matches_sampled,
            "minimum_matches": 3, "players": ranked if status == "fresh" else [],
        }
        if status == "unavailable":
            result["reason"] = "insufficient_sample" if matches_sampled < 3 else "no_contributions"
        return result

    def cached_history_fixtures(self):
        """Return unique ESPN history rows suitable for summary backfill."""
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        teams = {
            str(team.get("team_id")): str(team.get("name") or "")
            for team in roster.get("teams", []) if team.get("team_id") is not None
        }
        documents = list(self.cache_collection.find({
            "_id": {"$in": [self._id(f"team_form:{team_id}") for team_id in teams]}
        })) if teams else []
        fixtures = {}
        for document in documents:
            for match in document.get("matches", []) or []:
                if document.get("scope") != "all_competitions" or not self._verified_match(
                    match, "espn:team-id", team_id=document.get("team_id"),
                ):
                    continue
                event_id = str(match.get("fixture_id") or "")
                if not event_id or match.get("provider") != "espn":
                    continue
                played_at = match.get("played_at")
                home, away = match.get("home_team"), match.get("away_team")
                if not home or not away or not played_at:
                    continue
                fixtures[event_id] = {
                    "id": event_id, "home_team": home, "away_team": away,
                    "commence_time": played_at, "completed": True, "historical": True,
                }
        return list(fixtures.values())

    def refresh_history_depth(self, now=None):
        """Gradually expand legacy five-match caches without a request burst."""
        current = now or self.now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        local_date = current.astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()
        state = self.get_sync_state()
        if state.get("history_backfill_date") == local_date:
            return {"status": "idle", "teams_attempted": 0, "reason": "already_checked_today"}
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        if self.competition.is_club_competition and roster.get("scope") == "all_competitions":
            return {
                "status": "skipped", "teams_attempted": 0,
                "reason": "all_competitions_form_is_authoritative",
            }
        team_ids = [
            str(team.get("team_id")) for team in roster.get("teams", [])
            if team.get("team_id") is not None
        ]
        documents = {
            str(document.get("team_id") or str(document.get("_id") or "").rsplit(":", 1)[-1]): document
            for document in self.cache_collection.find({
                "_id": {"$in": [self._id(f"team_form:{team_id}") for team_id in team_ids]}
            })
        } if team_ids else {}
        attempted = set(state.get("history_backfill_attempted_team_ids") or [])
        due = [
            team_id for team_id in team_ids
            if team_id not in attempted and len((documents.get(team_id) or {}).get("matches") or []) < self.FORM_LIMIT
        ][:self.HISTORY_BACKFILL_TEAMS_PER_DAY]
        roster_provider = str(roster.get("provider") or roster.get("source") or "")
        history_team_ids = {
            str(key): str(value)
            for key, value in (state.get("history_espn_team_ids") or {}).items()
        }
        if roster.get("provider_namespace") == "espn:team-id" or roster_provider == "espn":
            history_team_ids.update({team_id: team_id for team_id in team_ids})
        else:
            # Provider IDs from another namespace cannot be translated by name.
            history_team_ids = {}
        completed = []
        for team_id in due:
            history_team_id = history_team_ids.get(team_id)
            if not history_team_id:
                continue
            try:
                payload = self.history_client.request("/fixtures", {"team": history_team_id, "last": self.FORM_LIMIT})
                history_provider = getattr(self.history_client, "provider", "espn")
                self.merge_matches(
                    team_id, self.parse_fixtures(history_team_id, payload, provider=history_provider),
                    current.isoformat(), provider=history_provider,
                )
            except Exception as exc:
                self.store_sync_state({
                    "history_backfill_date": local_date,
                    "history_backfill_attempted_team_ids": sorted(attempted | set(completed)),
                    "history_backfill_error": str(exc),
                })
                return {"status": "stale", "teams_attempted": len(completed), "error": str(exc)}
            completed.append(team_id)
        self.store_sync_state({
            "history_backfill_date": local_date,
            "history_backfill_attempted_team_ids": sorted(attempted | set(completed)),
            "history_backfill_error": None,
        })
        return {"status": "fresh" if completed else "idle", "teams_attempted": len(completed)}

    def _resolve_team_id(self, team_name, fallback_team_id, roster):
        known_ids = {
            str(team.get("team_id")) for team in roster.get("teams", [])
            if team.get("team_id") is not None
        }
        if fallback_team_id is not None:
            team_id = str(fallback_team_id)
            return team_id if team_id in known_ids else None
        if not self.competition.is_club_competition:
            requested = TEAM_MAPPING.get(str(team_name), str(team_name))
            for team in roster.get("teams", []):
                provider_name = str(team.get("name") or "")
                if provider_name == str(team_name) or TEAM_MAPPING.get(provider_name, provider_name) == requested:
                    team_id = str(team.get("team_id")) if team.get("team_id") is not None else None
                    return team_id
        return None

    @classmethod
    def _display_form(cls, document, roster, *, before=None):
        expected_namespace = roster.get("provider_namespace") or document.get("provider_namespace")
        matches = [
            dict(match) for match in document.get("matches", [])
            if cls._verified_match(match, expected_namespace, team_id=document.get("team_id"))
            and document.get("scope") == "all_competitions"
        ]
        if before is not None:
            cutoff = cls._time(before)
            matches = [
                match for match in matches
                if cutoff is not None
                and (played_at := cls._time(match.get("played_at"))) is not None
                and played_at < cutoff
            ]
        matches = cls._latest(matches)
        coverage = {
            "available": len(matches), "required": cls.FORM_LIMIT,
            "complete": len(matches) >= cls.FORM_LIMIT,
        }
        metadata = {
            "scope": "all_competitions",
            "coverage": coverage,
            "validation_version": document.get("validation_version", cls.VALIDATION_VERSION),
            "provider_namespace": expected_namespace,
        }
        if not matches:
            return {
                "status": document.get("status") if document.get("status") in {"stale", "unavailable"} else "unavailable",
                **metadata,
                "source": document.get("source") or roster.get("source") or "api_football",
                "observed_at": document.get("observed_at"),
                "error": document.get("error") or "Form data is not available for this team",
                "form": [],
                "on_fire": False,
                "matches": [],
            }

        results = [match.get("result") for match in reversed(matches)]
        form = [result for result in results if result in {"W", "D", "L"}]
        newest = [match.get("result") for match in matches[:3]]
        return {
            "status": document.get("status") if document.get("status") in {"fresh", "stale"} else "stale",
            **metadata,
            "source": document.get("source") or document.get("provider") or "api_football",
            "observed_at": document.get("observed_at"),
            "error": document.get("error"),
            "form": form,
            "on_fire": len(newest) == 3 and all(result == "W" for result in newest),
            "matches": matches,
        }

    def _mark_stale(self, team_ids, error, observed_at):
        provider = self._provider()
        fields = {
            "status": "stale", "source": provider, "provider": provider,
            "error": str(error), "observed_at": observed_at, "last_attempt_at": observed_at,
        }
        for team_id in team_ids:
            document_id = self._id(f"team_form:{team_id}")
            if self.cache_collection.find_one({"_id": document_id}) is not None:
                self.cache_collection.update_one({"_id": document_id}, {"$set": fields})
        roster_id = self._id("team_form_teams")
        if self.cache_collection.find_one({"_id": roster_id}) is not None:
            self.cache_collection.update_one({"_id": roster_id}, {"$set": fields})

    def _mark_bootstrap_stale(self, error, observed_at):
        provider = self._provider()
        self.cache_collection.update_one({"_id": self._id("team_form_bootstrap")}, {"$set": {
            "competition": self.competition.id, "status": "stale",
            "source": provider, "provider": provider,
            "error": str(error), "observed_at": observed_at, "last_attempt_at": observed_at,
        }}, upsert=True)

    def refresh_daily(self, now=None, max_catchup_days=7) -> dict:
        current = now or self.now_fn()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        observed_at = current.isoformat()
        yesterday = current.astimezone(ZoneInfo("Europe/Zurich")).date() - timedelta(days=1)
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        if self.competition.is_club_competition and roster.get("scope") == "all_competitions":
            return {
                "status": "skipped", "source": roster.get("provider"),
                "provider_calls": 0, "reason": "all_competitions_form_is_authoritative",
            }
        team_ids = {str(team["team_id"]) for team in roster.get("teams", []) if team.get("team_id") is not None}
        if self.client is None:
            error = "API_FOOTBALL_KEY is unavailable"
            if roster:
                self._mark_stale(team_ids, error, observed_at)
                self.store_sync_state({
                    "status": "stale", "source": "api_football", "provider": "api_football",
                    "error": error, "observed_at": observed_at, "last_attempt_at": observed_at,
                })
            return {
                "status": "stale" if roster else "unavailable",
                "source": "api_football", "provider": "api_football",
                "observed_at": observed_at, "error": error, "dates_processed": [],
            }
        if not team_ids:
            provider = self._provider()
            return {
                "status": "unavailable", "source": provider, "provider": provider,
                "observed_at": observed_at,
                "error": "UCL team roster is unavailable",
                "dates_processed": [],
            }

        state = self.get_sync_state()
        last_date = state.get("last_successful_date")
        try:
            if last_date:
                next_date = date.fromisoformat(last_date) + timedelta(days=1)
            else:
                bootstrap = self.cache_collection.find_one({"_id": self._id("team_form_bootstrap")}) or {}
                bootstrap_at = datetime.fromisoformat(str(bootstrap.get("last_successful_at")).replace("Z", "+00:00"))
                if bootstrap_at.tzinfo is None:
                    bootstrap_at = bootstrap_at.replace(tzinfo=timezone.utc)
                # The bootstrap day itself was not necessarily complete yet.
                next_date = min(bootstrap_at.astimezone(ZoneInfo("Europe/Zurich")).date(), yesterday)
        except (TypeError, ValueError):
            next_date = yesterday
        team_names = {str(team.get("team_id")): team.get("name") for team in roster.get("teams", [])}
        pending = []
        while next_date <= yesterday and len(pending) < max_catchup_days:
            pending.append(next_date)
            next_date += timedelta(days=1)

        processed = []
        try:
            for day in pending:
                page = 1
                fixtures = []
                while True:
                    payload = self.client.request("/fixtures", {
                        "date": day.isoformat(), "timezone": "Europe/Zurich", "page": page,
                    })
                    fixtures.extend(payload.get("response") or [])
                    paging = payload.get("paging") or {}
                    current_page = paging.get("current")
                    total_pages = paging.get("total")
                    if (
                        type(current_page) is not int or type(total_pages) is not int
                        or current_page != page or current_page < 1 or total_pages < current_page
                    ):
                        raise ValueError("Invalid API-Football paging metadata")
                    if current_page >= total_pages:
                        break
                    page = current_page + 1

                for team_id in sorted(team_ids):
                    self.merge_matches(team_id, self.parse_fixtures(
                        team_id, {"response": fixtures}, team_name=team_names.get(team_id),
                    ), observed_at)
                provider = self._provider()
                self.store_sync_state({
                    "last_successful_date": day.isoformat(), "status": "fresh",
                    "source": provider, "provider": provider,
                    "observed_at": observed_at, "last_attempt_at": observed_at,
                    "last_successful_at": observed_at, "error": None,
                    "remaining_dates": 0,
                })
                processed.append(day.isoformat())
        except Exception as exc:
            error = str(exc)
            self._mark_stale(team_ids, error, observed_at)
            provider = self._provider()
            self.store_sync_state({
                "status": "stale", "source": provider, "provider": provider,
                "error": error, "observed_at": observed_at, "last_attempt_at": observed_at,
            })
            return {
                "status": "stale", "source": provider, "provider": provider,
                "observed_at": observed_at, "error": error, "dates_processed": processed,
            }
        remaining = max(0, (yesterday - next_date).days + 1)
        if remaining:
            error = f"catch-up pending: {remaining} date(s) remaining"
            self._mark_stale(team_ids, error, observed_at)
            provider = self._provider()
            self.store_sync_state({
                "status": "stale", "source": provider, "provider": provider,
                "error": error, "observed_at": observed_at, "last_attempt_at": observed_at,
                "remaining_dates": remaining,
            })
            return {
                "status": "stale", "source": provider, "provider": provider,
                "observed_at": observed_at, "error": error, "remaining_dates": remaining,
                "dates_processed": processed, "last_successful_date": processed[-1] if processed else last_date,
            }

        provider = self._provider()
        return {
            "status": "fresh", "source": provider, "provider": provider,
            "observed_at": observed_at, "dates_processed": processed,
            "last_successful_date": (processed[-1] if processed else last_date),
        }

    def bootstrap(self, season=2026, sleep_fn=time.sleep, min_interval_seconds=7, league=2):
        """Fetch the provider's current UCL field, saving progress after each team."""
        existing_roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        if self.competition.is_club_competition and existing_roster.get("scope") == "all_competitions":
            return {
                "status": "skipped", "provider_calls": 0,
                "reason": "all_competitions_form_is_authoritative",
            }
        observed_at = self.now_fn().isoformat()
        try:
            team_payload = self.client.request("/teams", {"league": league, "season": season})
        except Exception as exc:
            roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
            self._mark_stale([team["team_id"] for team in roster.get("teams", [])], exc, observed_at)
            self._mark_bootstrap_stale(exc, observed_at)
            raise
        teams = self.store_teams(self.parse_teams(team_payload))
        document_id = self._id("team_form_bootstrap")
        state = self.cache_collection.find_one({"_id": document_id}) or {}
        completed = set(state.get("completed_team_ids", [])) if (
            state.get("season") == season and state.get("league", 2) == league
        ) else set()
        completed.intersection_update(team["team_id"] for team in teams)
        completed = {
            team_id for team_id in completed
            if not (
                (document := self.cache_collection.find_one({"_id": self._id(f"team_form:{team_id}")}))
                and len(document.get("matches") or []) < self.FORM_LIMIT
            )
        }
        skipped = 0
        last_fixture_at = None
        clock_fn = getattr(self.client, "monotonic_fn", time.monotonic)
        for team in teams:
            team_id = team["team_id"]
            if team_id in completed:
                skipped += 1
                continue
            if last_fixture_at is not None and self._provider() == "api_football":
                delay = min_interval_seconds - (clock_fn() - last_fixture_at)
                if delay > 0:
                    sleep_fn(delay)
            try:
                payload = self.client.request("/fixtures", {"team": team_id, "last": self.FORM_LIMIT})
            except Exception as exc:
                self._mark_stale([item["team_id"] for item in teams], exc, observed_at)
                self._mark_bootstrap_stale(exc, observed_at)
                raise
            last_fixture_at = clock_fn()
            self.merge_matches(team_id, self.parse_fixtures(team_id, payload))
            completed.add(team_id)
            provider = self._provider()
            self.cache_collection.update_one(
                {"_id": document_id},
                {"$set": {
                    "competition": self.competition.id,
                    "league": league,
                    "season": season,
                    "completed_team_ids": [item["team_id"] for item in teams if item["team_id"] in completed],
                    "status": "fresh", "source": provider, "provider": provider,
                    "observed_at": observed_at, "last_attempt_at": observed_at,
                    "last_successful_at": observed_at,
                    "coverage": {"teams_completed": len(completed), "teams_total": len(teams)},
                    "error": None,
                }},
                upsert=True,
            )
        return {"teams_total": len(teams), "teams_skipped": skipped, "teams_completed": len(completed)}

    @classmethod
    def _latest(cls, matches):
        def sort_key(match):
            value = str(match.get("played_at") or "").replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return float("-inf")
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()

        return sorted(matches, key=sort_key, reverse=True)[:cls.FORM_LIMIT]
