"""Read-only, pre-kickoff bookmaker odds observations for one fixture."""

from __future__ import annotations

import math
from datetime import timezone

from src.competitions import find_competition_document, get_competition
from src.services.archive import build_archive_id_index, resolve_archive_id
from src.services.snapshots import SNAPSHOT_BUCKETS, parse_time


MAX_ODDS_HISTORY_POINTS = 100
_VALID_SNAPSHOT_STATUSES = {"fresh", "stale"}


def _kickoff_and_event_id(cache_collection, archive_collection, match_id: str, competition: str):
    archived = None
    if archive_collection is not None:
        candidate = archive_collection.find_one({"_id": match_id}) or {}
        if candidate.get("competition") in (None, competition):
            archived = candidate

    matches = find_competition_document(cache_collection, competition, "matches_cache") or {}
    fixtures = matches.get("data") or []
    if archived is not None:
        metadata = archived.get("metadata") or {}
        archived_kickoff = None
        try:
            if metadata.get("commence_time"):
                archived_kickoff = parse_time(metadata["commence_time"])
        except (TypeError, ValueError, OverflowError):
            pass

        home, away = metadata.get("home_team"), metadata.get("away_team")
        if home and away:
            # Cached fixtures carry provider event IDs while the archive may use
            # a date-qualified local ID. Resolve by the trusted archived pairing
            # and kickoff using the same canonicalization as matches.py.
            fixture_index = {}
            for fixture in fixtures:
                provider_id = str(fixture.get("id") or fixture.get("event_id") or "")
                raw_match = fixture.get("raw_match") or {}
                fixture_home = fixture.get("home_team") or raw_match.get("home_team")
                fixture_away = fixture.get("away_team") or raw_match.get("away_team")
                if provider_id and fixture_home and fixture_away:
                    fixture_index[provider_id] = {"metadata": {
                        "home_team": fixture_home,
                        "away_team": fixture_away,
                        "commence_time": (
                            fixture.get("commence_time") or raw_match.get("commence_time") or ""
                        ),
                    }}
            provider_id = resolve_archive_id(
                build_archive_id_index(fixture_index),
                home,
                away,
                metadata.get("commence_time") or "",
            )
            if provider_id and archived_kickoff is not None:
                return archived_kickoff, str(provider_id)
            return None, None

        if archived_kickoff is not None:
            # Legacy archive entries without team provenance historically use
            # the same ID in the snapshot store; retain that exact-ID lookup.
            return archived_kickoff, match_id

    for match in fixtures:
        provider_id = str(match.get("id") or match.get("event_id") or "")
        if provider_id != match_id:
            continue
        raw_match = match.get("raw_match") or {}
        for value in (match.get("commence_time"), raw_match.get("commence_time")):
            try:
                if value:
                    return parse_time(value), provider_id
            except (TypeError, ValueError, OverflowError):
                continue
    return None, None


def _snapshot_rows(cache_collection, match_id: str, competition: str):
    query = {
        "competition": competition,
        "event_id": match_id,
        "bucket": {"$in": list(SNAPSHOT_BUCKETS)},
        "status": {"$in": sorted(_VALID_SNAPSHOT_STATUSES)},
    }
    cursor = cache_collection.find(query)
    sort = getattr(cursor, "sort", None)
    if callable(sort):
        try:
            cursor = sort("observed_at", -1)
        except TypeError:
            rows = list(cursor)
            rows.sort(key=lambda row: str(row.get("observed_at") or ""), reverse=True)
            cursor = rows
    limit = getattr(cursor, "limit", None)
    if callable(limit):
        cursor = limit(MAX_ODDS_HISTORY_POINTS)
    rows = list(cursor)
    if len(rows) > MAX_ODDS_HISTORY_POINTS:
        rows.sort(key=lambda row: str(row.get("observed_at") or ""), reverse=True)
        rows = rows[:MAX_ODDS_HISTORY_POINTS]
    return rows


def _clean_odds(value):
    if not isinstance(value, dict) or not all(key in value for key in ("home", "draw", "away")):
        return None
    odds = {}
    try:
        for key in ("home", "draw", "away"):
            raw = value[key]
            if isinstance(raw, bool):
                return None
            odds[key] = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(price) and price > 1 for price in odds.values()):
        return None
    implied = {key: 1 / price for key, price in odds.items()}
    total = sum(implied.values())
    if not math.isfinite(total) or total <= 0:
        return None
    probabilities = {key: implied[key] / total for key in ("home", "draw", "away")}
    return odds, probabilities


def get_odds_history(
    cache_collection,
    match_id: str,
    *,
    competition=None,
    archive_collection=None,
) -> dict:
    """Return at most 100 actual odds observations taken before known kickoff."""
    comp = get_competition(competition)
    kickoff, snapshot_event_id = _kickoff_and_event_id(
        cache_collection, archive_collection, match_id, comp.id
    )
    result = {
        "match_id": match_id,
        "competition": comp.id,
        "status": "unavailable",
        "observations": [],
    }
    if kickoff is None or snapshot_event_id is None:
        return result

    ranked = []
    for row in _snapshot_rows(cache_collection, snapshot_event_id, comp.id):
        if row.get("source") != "odds_api" or row.get("status") not in _VALID_SNAPSHOT_STATUSES:
            continue
        if row.get("bucket") not in SNAPSHOT_BUCKETS:
            continue
        try:
            observed = parse_time(row.get("observed_at"))
        except (TypeError, ValueError, OverflowError):
            continue
        if observed >= kickoff:
            continue
        cleaned = _clean_odds(row.get("odds"))
        if cleaned is None:
            continue
        odds, probabilities = cleaned
        timestamp = observed.astimezone(timezone.utc)
        ranked.append((timestamp, list(SNAPSHOT_BUCKETS).index(row["bucket"]), str(row.get("_id") or ""), {
            "observed_at": timestamp.isoformat(),
            "bucket": row["bucket"],
            "source": row["source"],
            "odds": odds,
            "probabilities": probabilities,
        }))

    # Stable bucket/id ordering makes same-instant duplicate selection deterministic.
    ranked.sort(key=lambda item: item[:3])
    by_timestamp = {}
    for timestamp, _bucket_order, _document_id, point in ranked:
        by_timestamp[timestamp] = point
    observations = list(by_timestamp.values())
    result["observations"] = observations
    if observations:
        result["status"] = "available"
    if len(observations) >= 2:
        first = observations[0]["probabilities"]
        last = observations[-1]["probabilities"]
        result["probability_change_pp"] = {
            outcome: (last[outcome] - first[outcome]) * 100
            for outcome in ("home", "draw", "away")
        }
    return result
