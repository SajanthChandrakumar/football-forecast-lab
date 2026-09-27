"""API-Football client and competition-scoped team-form cache."""

from collections import deque
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
    FOTMOB_BASE_URL = "https://www.fotmob.com/api/data"

    def __init__(self, request_fn=None, *, season=2026, enable_fotmob_fallback=True):
        self.request_fn = request_fn or requests.get
        self.season = int(season)
        self.enable_fotmob_fallback = enable_fotmob_fallback
        self.provider = "espn"
        self._team_names = {}

    def request(self, path, params=None):
        params = params or {}
        self.provider = "espn"
        if path == "/teams":
            season = int(params.get("season", self.season))
            payload = self._get(
                f"{self.BASE_URL}/uefa.champions/scoreboard",
                {"dates": str(season)},
            )
            teams = {}
            for event in payload.get("events", []) or []:
                if (event.get("season") or {}).get("year") != season:
                    continue
                competition = (event.get("competitions") or [{}])[0]
                for competitor in competition.get("competitors", []) or []:
                    team = competitor.get("team") or {}
                    team_id = team.get("id") or competitor.get("id")
                    name = team.get("displayName") or team.get("name")
                    if team_id is None or not name:
                        continue
                    teams[str(team_id)] = {"team": {
                        "id": str(team_id),
                        "name": name,
                        "logo": self._logo(team),
                    }}
                    self._team_names[str(team_id)] = name
            return {"response": list(teams.values()), "paging": {"current": 1, "total": 1}}

        if path != "/fixtures":
            raise ValueError(f"Unsupported ESPN team-form path: {path}")
        if params.get("team") is not None:
            team_id = str(params["team"])
            payload = self._get(
                f"{self.BASE_URL}/all/teams/{team_id}/schedule",
                {"season": self.season},
            )
            events = payload.get("events", []) or []
            response = [item for event in events if (item := self._normalize_event(event))]
            completed = [
                item for item in response
                if ((item.get("fixture") or {}).get("status") or {}).get("short") in {"FT", "AET", "PEN"}
                and "friendl" not in str((item.get("league") or {}).get("name") or "").casefold()
            ]
            if self.enable_fotmob_fallback and len(completed) < TeamFormService.FORM_LIMIT:
                team_name = (
                    self._team_names.get(team_id)
                    or (payload.get("team") or {}).get("displayName")
                    or (payload.get("team") or {}).get("name")
                )
                supplemental = self._fotmob_matches(team_id, team_name) if team_name else []
                if supplemental:
                    response = self._merge_team_events(team_id, response, supplemental)
                    self.provider = "espn+fotmob"
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
        response = self.request_fn(url, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("ESPN returned an invalid JSON payload")
        return payload

    def _fotmob_matches(self, espn_team_id, team_name):
        try:
            search = self._fotmob_get("search/suggest", {"term": team_name, "lang": "en"})
            suggestions = [
                suggestion
                for group in search if isinstance(group, dict)
                for suggestion in group.get("suggestions", []) or []
                if isinstance(suggestion, dict)
            ] if isinstance(search, list) else []
            exact = next((
                item for item in suggestions
                if item.get("type") == "team"
                and str(item.get("name") or "").casefold() == str(team_name).casefold()
            ), None)
            if not exact or exact.get("id") is None:
                return []
            payload = self._fotmob_get("teams", {"id": exact["id"], "ccode3": "CHE"})
            fixtures = (((payload.get("fixtures") or {}).get("allFixtures") or {}).get("fixtures") or [])
            return [
                item for fixture in fixtures
                if (item := self._normalize_fotmob_fixture(fixture, espn_team_id, team_name))
            ]
        except (requests.RequestException, RuntimeError, TypeError, ValueError):
            return []

    def _fotmob_get(self, path, params):
        response = self.request_fn(
            f"{self.FOTMOB_BASE_URL}/{path}",
            params=params,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        content_type = str(getattr(response, "headers", {}).get("content-type") or "")
        if content_type and "json" not in content_type.casefold():
            raise RuntimeError("FotMob returned a non-JSON response")
        return response.json()

    @staticmethod
    def _normalize_fotmob_fixture(fixture, espn_team_id, team_name):
        status = fixture.get("status") or {}
        if not status.get("finished") or status.get("cancelled"):
            return None
        reason = str((status.get("reason") or {}).get("short") or "FT").upper()
        normalized_status = "PEN" if "PEN" in reason else "AET" if "AET" in reason else "FT"
        home = dict(fixture.get("home") or {})
        away = dict(fixture.get("away") or {})
        if str(home.get("name") or "").casefold() == str(team_name).casefold():
            home["id"] = str(espn_team_id)
        elif str(away.get("name") or "").casefold() == str(team_name).casefold():
            away["id"] = str(espn_team_id)
        else:
            return None
        if home.get("id") is None or away.get("id") is None:
            return None
        home["id"], away["id"] = str(home["id"]), str(away["id"])
        return {
            "fixture": {
                "id": f"fotmob:{fixture.get('id')}",
                "date": status.get("utcTime"),
                "status": {"short": normalized_status},
            },
            "league": {"name": str((fixture.get("tournament") or {}).get("name") or ""), "type": "Cup"},
            "teams": {
                "home": {"id": home["id"], "name": home.get("name")},
                "away": {"id": away["id"], "name": away.get("name")},
            },
            "goals": {"home": home.get("score"), "away": away.get("score")},
            "score": {"penalty": {}},
        }

    @staticmethod
    def _merge_team_events(team_id, primary, supplemental):
        def signature(item):
            fixture = item.get("fixture") or {}
            teams = item.get("teams") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            opponent = away if str(home.get("id")) == str(team_id) else home
            return (
                str(fixture.get("date") or "")[:10],
                str(opponent.get("name") or "").casefold(),
            )

        merged = {}
        for item in [*primary, *supplemental]:
            merged.setdefault(signature(item), item)
        return list(merged.values())

    @staticmethod
    def _logo(team):
        if team.get("logo"):
            return team["logo"]
        logos = team.get("logos") or []
        return logos[0].get("href") if logos and isinstance(logos[0], dict) else None

    @staticmethod
    def _competition_name(event, competition):
        name = str((event.get("season") or {}).get("displayName") or "")
        if not name:
            name = str(competition.get("altGameNote") or "").split(",", 1)[0]
        return re.sub(r"^\d{4}(?:-\d{2,4})?\s+", "", name).strip()

    @classmethod
    def _normalize_event(cls, event):
        competition = (event.get("competitions") or [{}])[0]
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
            return {
                "id": str(team.get("id") or competitor.get("id")),
                "name": team.get("displayName") or team.get("name"),
            }

        def score(competitor):
            value = competitor.get("score")
            return value.get("value") if isinstance(value, dict) else value

        home_penalty = home.get("shootoutScore") or home.get("penaltyScore")
        away_penalty = away.get("shootoutScore") or away.get("penaltyScore")
        if status == "PEN" and home_penalty is None and away_penalty is None:
            home_penalty = 1 if home.get("winner") else 0
            away_penalty = 1 if away.get("winner") else 0
        return {
            "fixture": {
                "id": str(event.get("id") or competition.get("id")),
                "date": event.get("date") or competition.get("date"),
                "status": {"short": status},
            },
            "league": {"name": cls._competition_name(event, competition), "type": "Cup"},
            "teams": {"home": team_node(home), "away": team_node(away)},
            "goals": {"home": score(home), "away": score(away)},
            "score": {"penalty": {"home": home_penalty, "away": away_penalty}},
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
    FORM_LIMIT = 5

    def __init__(self, cache_collection, client, competition="ucl2026", now_fn=None):
        self.cache_collection = cache_collection
        self.client = client
        self.competition = get_competition(competition)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _id(self, key):
        return competition_document_id(self.competition, key)

    def _provider(self):
        return getattr(self.client, "provider", "api_football") if self.client is not None else "api_football"

    def parse_teams(self, payload):
        teams = {}
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
            }
        return list(teams.values())

    def store_teams(self, teams):
        normalized = [dict(team) for team in teams]
        observed_at = self.now_fn().isoformat()
        provider = self._provider()
        self.cache_collection.update_one(
            {"_id": self._id("team_form_teams")},
            {"$set": {
                "competition": self.competition.id, "teams": normalized,
                "status": "fresh", "source": provider, "provider": provider,
                "observed_at": observed_at, "last_attempt_at": observed_at,
                "last_successful_at": observed_at, "coverage": {"teams": len(normalized)},
                "error": None,
            }},
            upsert=True,
        )
        return normalized

    def parse_fixtures(self, team_id, payload):
        team_id = str(team_id)
        matches = []
        for item in payload.get("response", []) or []:
            fixture = item.get("fixture") or {}
            league = item.get("league") or {}
            teams = item.get("teams") or {}
            goals = item.get("goals") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            status = str((fixture.get("status") or {}).get("short") or "").upper()
            competition_name = str(league.get("name") or "")
            league_type = str(league.get("type") or "")

            if status not in self.ALLOWED_STATUSES:
                continue
            if "friendl" in competition_name.casefold() or "friendl" in league_type.casefold():
                continue
            if str(home.get("id")) == team_id:
                opponent, venue = away, "home"
                goals_for, goals_against = goals.get("home"), goals.get("away")
            elif str(away.get("id")) == team_id:
                opponent, venue = home, "away"
                goals_for, goals_against = goals.get("away"), goals.get("home")
            else:
                continue

            fixture_id = fixture.get("id")
            played_at = fixture.get("date")
            opponent_id = opponent.get("id")
            if fixture_id is None or not played_at or opponent_id is None or not opponent.get("name"):
                continue
            try:
                goals_for, goals_against = int(goals_for), int(goals_against)
            except (TypeError, ValueError):
                continue
            result_for, result_against = goals_for, goals_against
            if status == "PEN":
                penalties = ((item.get("score") or {}).get("penalty") or {})
                side = "home" if venue == "home" else "away"
                other_side = "away" if side == "home" else "home"
                try:
                    result_for, result_against = int(penalties[side]), int(penalties[other_side])
                except (KeyError, TypeError, ValueError):
                    result_for, result_against = goals_for, goals_against
            result = "W" if result_for > result_against else "D" if result_for == result_against else "L"
            matches.append({
                "fixture_id": str(fixture_id),
                "played_at": str(played_at),
                "competition_name": competition_name,
                "opponent_id": str(opponent_id),
                "opponent_name": opponent["name"],
                "venue": venue,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "score": f"{goals_for}:{goals_against}",
                "result": result,
            })
        return self._latest(matches)

    def merge_matches(self, team_id, matches, observed_at=None):
        team_id = str(team_id)
        document_id = self._id(f"team_form:{team_id}")
        existing = self.cache_collection.find_one({"_id": document_id}) or {}
        by_fixture = {}
        for match in existing.get("matches", []):
            fixture_id = match.get("fixture_id")
            if fixture_id is not None:
                by_fixture[str(fixture_id)] = dict(match)
        for match in matches:
            fixture_id = match.get("fixture_id")
            if fixture_id is not None:
                by_fixture[str(fixture_id)] = dict(match)
        latest = self._latest(list(by_fixture.values()))
        observed_at = observed_at or self.now_fn().isoformat()
        status = "fresh" if latest else "unavailable"
        provider = self._provider()
        self.cache_collection.update_one(
            {"_id": document_id},
            {"$set": {
                "competition": self.competition.id,
                "team_id": team_id,
                "matches": latest,
                "status": status,
                "source": provider,
                "provider": provider,
                "observed_at": observed_at,
                "last_attempt_at": observed_at,
                "last_successful_at": observed_at,
                "coverage": {"matches": len(latest), "limit": self.FORM_LIMIT},
                "error": None if latest else "No completed competitive matches available",
            }},
            upsert=True,
        )
        return latest

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

    def cached_form_for_match(self, team_name, fallback_team_id=None) -> dict:
        """Return display-only form data from MongoDB without provider access."""
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        team_id = self._resolve_team_id(team_name, fallback_team_id, roster)
        document = (
            self.cache_collection.find_one({"_id": self._id(f"team_form:{team_id}")})
            if team_id is not None else None
        ) or {}
        return self._display_form(document, roster)

    def cached_forms_for_matches(self, matches):
        """Attach cached form with one roster read and one indexed batch read."""
        roster = self.cache_collection.find_one({"_id": self._id("team_form_teams")}) or {}
        team_ids = {
            team_id
            for match in matches if isinstance(match, dict)
            for side in ("home", "away")
            if (team_id := self._resolve_team_id(
                match.get(f"{side}_team"), match.get(f"{side}_team_id"), roster,
            )) is not None
        }
        documents = {
            str(document["_id"]): document
            for document in self.cache_collection.find({
                "_id": {"$in": [self._id(f"team_form:{team_id}") for team_id in sorted(team_ids)]}
            })
        } if team_ids else {}
        presented = []
        for match in matches:
            if not isinstance(match, dict):
                presented.append(match)
                continue
            row = dict(match)
            for side in ("home", "away"):
                team_id = self._resolve_team_id(
                    row.get(f"{side}_team"), row.get(f"{side}_team_id"), roster,
                )
                document = documents.get(self._id(f"team_form:{team_id}"), {}) if team_id else {}
                row[f"{side}_form"] = self._display_form(document, roster)
            presented.append(row)
        return presented

    @staticmethod
    def _resolve_team_id(team_name, fallback_team_id, roster):
        team_id = str(fallback_team_id) if fallback_team_id is not None else None
        if team_id is None:
            requested = TEAM_MAPPING.get(str(team_name), str(team_name))
            for team in roster.get("teams", []):
                provider_name = str(team.get("name") or "")
                if provider_name == str(team_name) or TEAM_MAPPING.get(provider_name, provider_name) == requested:
                    team_id = str(team.get("team_id")) if team.get("team_id") is not None else None
                    break
        return team_id

    @classmethod
    def _display_form(cls, document, roster):
        matches = [dict(match) for match in document.get("matches", []) if isinstance(match, dict)]
        matches = cls._latest(matches)
        if not matches:
            return {
                "status": "unavailable",
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
            next_date = date.fromisoformat(last_date) + timedelta(days=1) if last_date else yesterday
        except ValueError:
            next_date = yesterday
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
                    self.merge_matches(team_id, self.parse_fixtures(team_id, {"response": fixtures}), observed_at)
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

        local_date = current.astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()
        sync_state = self.get_sync_state()
        supplemental_ids = [
            team_id for team_id in sorted(team_ids)
            if str((self.cache_collection.find_one({"_id": self._id(f"team_form:{team_id}")}) or {}).get("provider") or "")
            == "espn+fotmob"
        ]
        if supplemental_ids and sync_state.get("supplemental_refresh_date") != local_date:
            try:
                for team_id in supplemental_ids:
                    payload = self.client.request("/fixtures", {"team": team_id, "last": self.FORM_LIMIT})
                    self.merge_matches(team_id, self.parse_fixtures(team_id, payload), observed_at)
                self.store_sync_state({
                    "supplemental_refresh_date": local_date,
                    "supplemental_team_ids": supplemental_ids,
                })
            except Exception as exc:
                error = str(exc)
                self._mark_stale(supplemental_ids, error, observed_at)
                provider = self._provider()
                self.store_sync_state({
                    "status": "stale", "source": provider, "provider": provider,
                    "error": error, "observed_at": observed_at, "last_attempt_at": observed_at,
                })
                return {
                    "status": "stale", "source": provider, "provider": provider,
                    "observed_at": observed_at, "error": error, "dates_processed": processed,
                }
        provider = self._provider()
        return {
            "status": "fresh", "source": provider, "provider": provider,
            "observed_at": observed_at, "dates_processed": processed,
            "last_successful_date": (processed[-1] if processed else last_date),
        }

    def bootstrap(self, season=2026, sleep_fn=time.sleep, min_interval_seconds=7, league=2):
        """Fetch the provider's current UCL field, saving progress after each team."""
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
                and str(document.get("provider") or "").startswith("espn")
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
                payload = self.client.request("/fixtures", {"team": team_id, "last": 5})
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
