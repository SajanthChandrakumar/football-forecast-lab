"""Safe writes for shared fixture tips."""

from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from src.competitions import collection_for, find_competition_document, require_competition
from src.services.archive import (
    build_archive_id_index,
    invalidate_archive_mem_cache,
    resolve_archive_id,
)
from src.services.input_validation import bounded_match_id, bounded_score
from src.services.prediction import user_tip_is_open
from src.services.snapshots import parse_time


_PREDICTION_FIELDS = (
    "model_tip", "top_tip", "pool_tip", "pool_status", "probabilities", "base_probabilities",
    "frozen_at", "status", "source_status",
    "source", "observed_at", "source_mode", "model_version", "input_provenance",
    "provenance", "context", "max_xp", "bots",
)
_SNAPSHOT_FIELDS = (
    "odds", "elo_state", "source_mode", "status", "source_status", "source",
    "observed_at", "model_version", "input_provenance", "provenance", "context",
)
_CONTEXT_FIELDS = (
    "stage", "tie_id", "leg", "first_leg_score", "score_90", "score_aet",
    "shootout_winner", "extra_time_eligible",
)


def _completed(fixture: Mapping[str, Any]) -> bool:
    result = fixture.get("post_match_result") or {}
    status = str(fixture.get("status") or result.get("status") or "").lower()
    return bool(
        fixture.get("completed")
        or fixture.get("actual_score")
        or fixture.get("score_90")
        or result.get("actual_score")
        or status in {"completed", "final", "post"}
    )


def _archive_insert_fields(fixture: Mapping[str, Any], kickoff: str) -> dict[str, Any]:
    raw = fixture.get("raw_match") if isinstance(fixture.get("raw_match"), Mapping) else {}
    context = fixture.get("match_context") or fixture.get("context") or {}
    context = context if isinstance(context, Mapping) else {}
    home = fixture.get("home_team") or raw.get("home_team")
    away = fixture.get("away_team") or raw.get("away_team")
    if not isinstance(home, str) or not home or not isinstance(away, str) or not away:
        raise HTTPException(status_code=409, detail="Cached fixture teams are unavailable")

    metadata = {
        "home_team": home,
        "away_team": away,
        "home_disp": fixture.get("home_disp") or home,
        "away_disp": fixture.get("away_disp") or away,
        "is_ko_phase": fixture.get("is_ko_phase") is True,
        "round": fixture.get("round") or raw.get("round") or "",
        "commence_time": kickoff,
        **{key: context[key] for key in _CONTEXT_FIELDS if key in context},
    }
    prediction = fixture.get("prediction") if isinstance(fixture.get("prediction"), Mapping) else fixture
    insert_fields: dict[str, Any] = {
        "metadata": metadata,
        "post_match_result": {"status": "pending", "actual_score": None},
    }
    snapshot = {key: fixture[key] for key in _SNAPSHOT_FIELDS if key in fixture}
    if snapshot:
        insert_fields["pre_match_snapshot"] = snapshot
    insert_fields.update({
        f"prediction.{key}": prediction[key]
        for key in _PREDICTION_FIELDS
        if key in prediction
    })
    return insert_fields


def _archive_fixture(cache_store, archive_store, match_id: str, competition) -> dict[str, Any]:
    cache = find_competition_document(cache_store, competition, "matches_cache") or {}
    matches = cache.get("data")
    if not isinstance(matches, list):
        raise HTTPException(status_code=404, detail="Match not in fixture cache")
    fixtures_by_id = {}
    fixture_index = {}
    for item in matches:
        if not isinstance(item, Mapping):
            continue
        fixture_id = str(item.get("id") or item.get("event_id") or "")
        if not fixture_id:
            continue
        fixtures_by_id[fixture_id] = item
        raw = item.get("raw_match") if isinstance(item.get("raw_match"), Mapping) else {}
        home = item.get("home_team") or raw.get("home_team")
        away = item.get("away_team") or raw.get("away_team")
        kickoff = item.get("commence_time") or raw.get("commence_time")
        if isinstance(home, str) and home and isinstance(away, str) and away and isinstance(kickoff, str) and kickoff:
            fixture_index[fixture_id] = {
                "metadata": {"home_team": home, "away_team": away, "commence_time": kickoff},
            }
    fixture = fixtures_by_id.get(match_id)
    if fixture is None:
        existing = archive_store.find_one({"_id": match_id}) or {}
        metadata = existing.get("metadata") or {}
        home, away, kickoff = metadata.get("home_team"), metadata.get("away_team"), metadata.get("commence_time")
        if isinstance(home, str) and home and isinstance(away, str) and away and isinstance(kickoff, str) and kickoff:
            fixture_id = resolve_archive_id(build_archive_id_index(fixture_index), home, away, kickoff)
            fixture = fixtures_by_id.get(fixture_id) if fixture_id else None
    if fixture is None:
        raise HTTPException(status_code=404, detail="Match not in fixture cache")
    if _completed(fixture):
        raise HTTPException(status_code=409, detail="User tips are closed for completed matches")

    raw = fixture.get("raw_match") if isinstance(fixture.get("raw_match"), Mapping) else {}
    kickoff = fixture.get("commence_time") or raw.get("commence_time")
    try:
        parse_time(kickoff)
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=409, detail="Cached kickoff time is unavailable") from None
    return {"fixture": fixture, "kickoff": kickoff}


def _archive_is_completed(entry: Mapping[str, Any] | None) -> bool:
    if not entry:
        return False
    result = entry.get("post_match_result") or {}
    status = str(result.get("status") or "").lower()
    return status in {"completed", "final", "post"} or bool(result.get("actual_score"))


def save_shared_tip(
    archive_store,
    cache_store,
    match_id: str,
    user_tip: str,
    competition,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Save one shared tip from a competition-scoped cached fixture only.

    New archive rows copy the forecast already present in the cache. The write
    changes only ``prediction.user_tip`` on existing rows, so forecast and
    result updates from other writers survive.
    """
    comp = require_competition(competition)
    archive_store = collection_for(archive_store, comp)
    cache_store = collection_for(cache_store, comp)
    try:
        match_id = bounded_match_id(match_id)
        user_tip = bounded_score(user_tip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cached = _archive_fixture(cache_store, archive_store, match_id, comp)
    fixture, kickoff = cached["fixture"], cached["kickoff"]
    current = now or datetime.now(timezone.utc)
    if not user_tip_is_open(kickoff, current, competition=comp):
        raise HTTPException(status_code=409, detail="User tips are closed at T-5")

    existing = archive_store.find_one({"_id": match_id})
    if _archive_is_completed(existing):
        raise HTTPException(status_code=409, detail="User tips are closed for completed matches")

    insert_fields = _archive_insert_fields(fixture, kickoff)
    query = {
        "_id": match_id,
        "post_match_result.status": {"$nin": ["completed", "final", "post"]},
        "post_match_result.actual_score": {"$in": [None, ""]},
    }
    try:
        result = archive_store.update_one(
            query,
            {
                "$setOnInsert": insert_fields,
                "$set": {"prediction.user_tip": user_tip},
            },
            upsert=True,
        )
    except DuplicateKeyError as exc:
        latest = archive_store.find_one({"_id": match_id})
        if _archive_is_completed(latest):
            raise HTTPException(status_code=409, detail="User tips are closed for completed matches") from exc
        if latest is None:
            raise
        result = archive_store.update_one(
            query,
            {"$set": {"prediction.user_tip": user_tip}},
            upsert=False,
        )
        if getattr(result, "matched_count", 0) == 0:
            latest = archive_store.find_one({"_id": match_id})
            if _archive_is_completed(latest):
                raise HTTPException(status_code=409, detail="User tips are closed for completed matches") from exc
            raise HTTPException(status_code=409, detail="Could not save user tip") from exc

    if getattr(result, "matched_count", 1) == 0 and getattr(result, "upserted_id", None) is None:
        latest = archive_store.find_one({"_id": match_id})
        if _archive_is_completed(latest):
            raise HTTPException(status_code=409, detail="User tips are closed for completed matches")
        raise HTTPException(status_code=409, detail="Could not save user tip")

    invalidate_archive_mem_cache(archive_store)
    return {"ok": True, "points_earned": None}
