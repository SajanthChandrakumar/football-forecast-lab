"""Quota-safe, cached lineups and match statistics for UCL fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from src.competitions import competition_document_id, get_competition
from src.services.snapshots import parse_time
from src.services.archive import _canon_team


ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary"
MAX_ESPN_CALLS_PER_RUN = 12


def fetch_espn_summary(event_id: str, *, request_get=None) -> dict:
    response = (request_get or requests.get)(
        ESPN_SUMMARY_URL,
        params={"event": str(event_id)},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("ESPN returned an invalid match summary")
    return payload


def normalize_espn_summary(payload: dict, *, observed_at=None) -> dict:
    observed = parse_time(observed_at or datetime.now(timezone.utc)).isoformat()
    lineups = {}
    for roster in payload.get("rosters", []) or []:
        team = (roster.get("team") or {}).get("displayName")
        players = roster.get("roster") or roster.get("entries") or []
        if not team or not players:
            continue
        starters, substitutes = [], []
        for entry in players:
            athlete = entry.get("athlete") or {}
            name = athlete.get("displayName") or athlete.get("shortName")
            if not name:
                continue
            position = athlete.get("position") or entry.get("position") or {}
            stats = {
                str(stat.get("name") or stat.get("abbreviation")): stat.get("value", stat.get("displayValue"))
                for stat in entry.get("stats", []) or []
                if isinstance(stat, dict)
                if stat.get("name") or stat.get("abbreviation")
            }
            player = {
                "id": str(athlete.get("id") or ""),
                "name": name,
                "position": position.get("abbreviation") or position.get("name"),
                "jersey": str(entry.get("jersey") or athlete.get("jersey") or ""),
                "stats": stats,
            }
            (starters if entry.get("starter") else substitutes).append(player)
        if starters or substitutes:
            lineups[team] = {"starters": starters, "substitutes": substitutes}

    team_stats = {}
    for row in (payload.get("boxscore") or {}).get("teams", []) or []:
        team = (row.get("team") or {}).get("displayName")
        if not team:
            continue
        team_stats[team] = {
            str(stat.get("name") or stat.get("label")): stat.get("displayValue", stat.get("value"))
            for stat in row.get("statistics", []) or []
            if stat.get("name") or stat.get("label")
        }

    status = "fresh" if lineups else "unavailable"
    return {
        "status": status,
        "source": "espn",
        "observed_at": observed,
        "reason": None if lineups else "lineups_not_published",
        "lineups": lineups,
        "team_stats": team_stats,
        # ESPN does not consistently expose a structured injury list here.
        "injuries": {"status": "unavailable", "players": []},
    }


def normalize_api_football_fixture(payload: dict, *, observed_at=None) -> dict:
    observed = parse_time(observed_at or datetime.now(timezone.utc)).isoformat()
    lineups = {}
    for row in payload.get("lineups", []) or []:
        team = (row.get("team") or {}).get("name")
        if not team:
            continue

        def players(entries):
            normalized = []
            for entry in entries or []:
                player = entry.get("player") or {}
                if not player.get("name"):
                    continue
                normalized.append({
                    "id": str(player.get("id") or ""),
                    "name": player["name"],
                    "position": player.get("pos"),
                    "jersey": str(player.get("number") or ""),
                    "stats": {},
                })
            return normalized

        lineups[team] = {
            "formation": row.get("formation"),
            "starters": players(row.get("startXI")),
            "substitutes": players(row.get("substitutes")),
        }
    team_stats = {}
    for row in payload.get("statistics", []) or []:
        team = (row.get("team") or {}).get("name")
        if team:
            team_stats[team] = {
                str(stat.get("type")): stat.get("value")
                for stat in row.get("statistics", []) or [] if stat.get("type")
            }
    return {
        "status": "fresh" if lineups else "unavailable",
        "source": "api_football",
        "observed_at": observed,
        "reason": None if lineups else "lineups_not_published",
        "lineups": lineups,
        "team_stats": team_stats,
        "injuries": {"status": "unavailable", "players": []},
    }


def _has_complete_lineups(data: dict) -> bool:
    lineups = data.get("lineups") or {}
    return len(lineups) >= 2 and all((lineup.get("starters") or []) for lineup in lineups.values())


def _due_bucket(fixture: dict, current: datetime, document: dict) -> str | None:
    attempted = set(document.get("attempted_buckets") or [])
    data = document.get("data") or {}
    if not fixture.get("historical") and document.get("fallback_pending") and "fallback_retry" not in attempted:
        return "fallback_retry"
    if _has_complete_lineups(data) and not fixture.get("completed"):
        return None
    if fixture.get("completed"):
        if "post_match" not in attempted:
            return "post_match"
        last_attempt = document.get("last_attempt") or {}
        if last_attempt.get("status") == "failed" and "post_match_retry" not in attempted:
            return "post_match_retry"
        return None
    kickoff_value = fixture.get("commence_time") or (fixture.get("raw_match") or {}).get("commence_time")
    if not kickoff_value:
        return None
    kickoff = parse_time(kickoff_value)
    minutes = (kickoff - current).total_seconds() / 60
    if 15 < minutes <= 45 and "t35" not in attempted:
        return "t35"
    if -5 <= minutes <= 15 and "t15" not in attempted:
        return "t15"
    return None


def refresh_match_intelligence(cache_collection, fixtures, *, now=None, espn_fetcher=None, api_football_client=None, competition="ucl2026") -> dict:
    """Refresh only due events. This function is called by authenticated maintenance."""
    comp = get_competition(competition)
    current = parse_time(now or datetime.now(timezone.utc))
    fetcher = espn_fetcher or fetch_espn_summary
    calls = 0
    api_calls = 0
    updated = 0
    fallback_due = []
    event_ids = {
        str(fixture.get("id") or fixture.get("event_id"))
        for fixture in fixtures if fixture.get("id") or fixture.get("event_id")
    }
    document_ids = {
        event_id: competition_document_id(comp, f"match_intelligence:{event_id}")
        for event_id in event_ids
    }
    documents = list(cache_collection.find({"_id": {"$in": list(document_ids.values())}})) if document_ids else []
    documents_by_id = {document.get("_id"): document for document in documents}
    for fixture in fixtures:
        event_id = str(fixture.get("id") or fixture.get("event_id") or "")
        if not event_id:
            continue
        document_id = document_ids[event_id]
        document = documents_by_id.get(document_id) or {}
        bucket = _due_bucket(fixture, current, document)
        if bucket is None:
            continue
        if bucket == "fallback_retry":
            cache_collection.update_one(
                {"_id": document_id},
                {"$addToSet": {"attempted_buckets": bucket}},
                upsert=True,
            )
            fallback_due.append((fixture, document_id))
            updated += 1
            continue
        if calls >= MAX_ESPN_CALLS_PER_RUN:
            break
        calls += 1
        try:
            data = normalize_espn_summary(fetcher(event_id), observed_at=current)
        except Exception as exc:
            failure = {
                "status": "failed",
                "source": "espn",
                "observed_at": current.isoformat(),
                "reason": "provider_error",
                "error": str(exc),
            }
            data = document.get("data") or {
                **failure,
                "lineups": {}, "team_stats": {},
                "injuries": {"status": "unavailable", "players": []},
            }
            attempt = failure
        else:
            if bucket.startswith("post_match") and not _has_complete_lineups(data):
                previous = document.get("data") or {}
                if previous:
                    preserved = dict(previous)
                    if data.get("team_stats"):
                        preserved["team_stats"] = data["team_stats"]
                    data = preserved
                attempt = {
                    "status": "failed", "source": "espn", "observed_at": current.isoformat(),
                    "reason": "incomplete_post_match_payload", "bucket": bucket,
                }
            else:
                attempt = {"status": "fresh", "source": "espn", "observed_at": current.isoformat(), "bucket": bucket}
        cache_collection.update_one(
            {"_id": document_id},
            {"$set": {
                "competition": comp.id,
                "event_id": event_id,
                "data": data,
                "updated_at": current.isoformat(),
                "last_attempt": attempt,
            }, "$addToSet": {"attempted_buckets": bucket}},
            upsert=True,
        )
        if not _has_complete_lineups(data) and not fixture.get("historical"):
            fallback_due.append((fixture, document_id))
        updated += 1
    if fallback_due and api_football_client is not None:
        # A date lookup discovers provider fixture IDs once. A later due run
        # uses those cached IDs to request enriched fixtures in one batch.
        kickoff = parse_time(fallback_due[0][0].get("commence_time"))
        date_key = kickoff.date().isoformat()
        mapping_id = competition_document_id(comp, f"match_intelligence_provider_ids:{date_key}")
        mapping_document = cache_collection.find_one({"_id": mapping_id}) or {}
        provider_ids = mapping_document.get("event_ids") or {}
        mapped_by_event = {
            str(fixture.get("id") or fixture.get("event_id")): provider_ids.get(
                str(fixture.get("id") or fixture.get("event_id"))
            )
            for fixture, _ in fallback_due
        }
        all_mapped = bool(mapped_by_event) and all(mapped_by_event.values())
        mapped = [str(provider_id) for provider_id in mapped_by_event.values() if provider_id]
        try:
            params = {"ids": "-".join(mapped[:20])} if all_mapped else {
                "league": 2, "season": int(str(comp.season).split("/", 1)[0]), "date": date_key,
            }
            payload = api_football_client.request("/fixtures", params)
            api_calls = 1
            responses = payload.get("response", []) if isinstance(payload, dict) else []
            by_teams = {
                (
                    _canon_team(((item.get("teams") or {}).get("home") or {}).get("name", "")),
                    _canon_team(((item.get("teams") or {}).get("away") or {}).get("name", "")),
                ): item for item in responses if isinstance(item, dict)
            }
            if not all_mapped:
                discovered = {}
                for fixture, _ in fallback_due:
                    event_id = str(fixture.get("id") or fixture.get("event_id"))
                    match = by_teams.get((
                        _canon_team(fixture.get("home_team", "")),
                        _canon_team(fixture.get("away_team", "")),
                    ))
                    provider_id = ((match or {}).get("fixture") or {}).get("id")
                    if provider_id is not None:
                        discovered[event_id] = str(provider_id)
                merged_ids = {**provider_ids, **discovered}
                if discovered:
                    cache_collection.update_one(
                        {"_id": mapping_id},
                        {"$set": {
                            "competition": comp.id, "date": date_key,
                            "event_ids": merged_ids, "observed_at": current.isoformat(),
                        }},
                        upsert=True,
                    )
                for fixture, document_id in fallback_due:
                    event_id = str(fixture.get("id") or fixture.get("event_id"))
                    if event_id in merged_ids:
                        cache_collection.update_one(
                            {"_id": document_id},
                            {"$set": {"fallback_pending": True}},
                            upsert=True,
                        )
            for fixture, document_id in fallback_due:
                event_id = str(fixture.get("id") or fixture.get("event_id"))
                provider_id = provider_ids.get(event_id)
                match = next((
                    item for item in responses
                    if str(((item.get("fixture") or {}).get("id") or "")) == str(provider_id or "")
                ), None) if provider_id else by_teams.get((
                    _canon_team(fixture.get("home_team", "")), _canon_team(fixture.get("away_team", "")),
                ))
                if not match:
                    continue
                data = normalize_api_football_fixture(match, observed_at=current)
                if not data.get("lineups"):
                    continue
                cache_collection.update_one(
                    {"_id": document_id},
                    {"$set": {
                        "data": data, "updated_at": current.isoformat(),
                        "fallback_pending": False,
                    }},
                    upsert=True,
                )
        except Exception:
            # ESPN's explicit unavailable state remains authoritative; quota
            # or plan failures in the optional fallback never break maintenance.
            api_calls = 1
    return {
        "status": "fresh" if calls or api_calls else "idle",
        "reason": None if calls or api_calls else "nothing_due",
        "espn_calls": calls,
        "api_football_calls": api_calls,
        "updated": updated,
    }


def attach_cached_match_intelligence(matches, cache_collection, competition="ucl2026"):
    """Attach cached data to public responses without any provider access."""
    comp = get_competition(competition)
    ids = {
        str(match.get("id") or match.get("event_id"))
        for match in matches if isinstance(match, dict) and (match.get("id") or match.get("event_id"))
    }
    document_ids = {
        event_id: competition_document_id(comp, f"match_intelligence:{event_id}")
        for event_id in ids
    }
    documents = list(cache_collection.find({"_id": {"$in": list(document_ids.values())}})) if document_ids else []
    by_id = {document.get("_id"): document for document in documents}
    presented = []
    for match in matches:
        if not isinstance(match, dict):
            presented.append(match)
            continue
        row = dict(match)
        event_id = str(row.get("id") or row.get("event_id") or "")
        document = by_id.get(document_ids.get(event_id))
        if document and document.get("data"):
            row["match_intelligence"] = document["data"]
        presented.append(row)
    return presented


def cached_match_intelligence(cache_collection, event_id, competition="ucl2026"):
    """Return one cached historical match without contacting a provider."""
    comp = get_competition(competition)
    document = cache_collection.find_one({
        "_id": competition_document_id(comp, f"match_intelligence:{event_id}")
    }) or {}
    return document.get("data") or {
        "status": "unavailable",
        "source": "cache",
        "observed_at": None,
        "reason": "not_collected",
        "lineups": {},
        "team_stats": {},
        "injuries": {"status": "unavailable", "players": []},
    }
