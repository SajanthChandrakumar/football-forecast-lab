"""Prepared, cache-only read views for the two club competitions."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
import asyncio
import gzip
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from pymongo import ReplaceOne
from pymongo.errors import BulkWriteError, DuplicateKeyError

from src.competitions import (
    COMPETITIONS,
    collection_for,
    competition_document_id,
    find_competition_document,
    get_competition,
)
from src.constants import _is_ko_round
from src.services.archive import build_archive_id_index, _canon_team
from src.services.ucl_simulation import _normalised_matrix_dict
from src.services.snapshots import parse_time

logger = logging.getLogger(__name__)


BUILD_LEASE_SECONDS = 180
STALE_WRITE_SECONDS = 300
CLUB_VIEW_SCHEMA_VERSION = 2
OVERVIEW_ENCODING = "gzip-json-v1"
WORKER_INTERVAL_SECONDS = 10.0
SOURCE_AUDIT_SECONDS = 300.0
SOURCE_AUDIT_RETRY_SECONDS = 30.0
_HEAD_STATE_PROJECTION = {
    "input_revision": 1, "published_revision": 1, "active_writers": 1,
    "generation": 1, "lease_token": 1, "lease_until": 1,
    "schema_version": 1, "match_count": 1, "source_hash": 1, "overview_encoding": 1,
    "match_versions": 1,
}
_HEAVY_KEYS = {
    "home_form", "away_form", "match_intelligence", "bookmakers", "matrix",
    "score_matrix", "regulation_matrix", "bots",
}
_CORE_HEAVY_KEYS = _HEAVY_KEYS - {"home_form", "away_form", "match_intelligence"}
_ARCHIVE_PREDICTION_KEYS = (
    "model_tip", "top_tip", "user_tip", "pool_tip", "pool_status", "probabilities",
    "frozen_at", "status", "source_status", "source", "observed_at", "source_mode",
    "model_version", "input_provenance", "provenance", "context", "max_xp",
    "probability_basis", "score_inputs", "xg_home", "xg_away", "xp_tips",
)


def overview_view_id(competition) -> str:
    return competition_document_id(competition, "club_views")


def game_view_id(competition, match_id: str) -> str:
    return competition_document_id(competition, f"club_view:{match_id}")


def _head_defaults(competition) -> dict:
    return {
        "competition": get_competition(competition).id,
        "input_revision": 0,
        "published_revision": None,
        "active_writers": {},
        "generation": 0,
    }


def _ensure_head(cache, competition) -> None:
    cache.update_one(
        {"_id": overview_view_id(competition)},
        {"$setOnInsert": _head_defaults(competition)},
        upsert=True,
    )


def _view_is_current(head: Mapping, cache, head_id: str) -> bool:
    current = bool(
        head.get("published_revision") is not None
        and head.get("published_revision") == head.get("input_revision", 0)
        and head.get("schema_version") == CLUB_VIEW_SCHEMA_VERSION
        and head.get("overview_encoding") == OVERVIEW_ENCODING
        and not head.get("active_writers")
    )
    # Check storage presence/type without transferring the payload on idle checks.
    return current and cache.find_one(
        {"_id": head_id, "overview_gzip": {"$type": "binData"}}, {"_id": 1},
    ) is not None


def encode_overview(rows) -> bytes:
    payload = json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
                         default=jsonable_encoder).encode("utf-8")
    return gzip.compress(payload, compresslevel=1, mtime=0)


def decode_overview(payload) -> list:
    if not isinstance(payload, bytes):
        raise ValueError("invalid overview encoding")
    rows = json.loads(gzip.decompress(payload))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid overview rows")
    return rows


def club_view_input_write(cache, competition):
    """Fence a source mutation before and after it, including exceptions."""
    return _ClubViewInputWrite(cache, competition)


class _ClubViewInputWrite:
    def __init__(self, cache, competition):
        self.cache = cache
        self.competition = get_competition(competition)
        self.head_id = overview_view_id(self.competition)
        self.token = uuid4().hex

    def __enter__(self):
        _ensure_head(self.cache, self.competition)
        now = datetime.now(timezone.utc)
        self.cache.update_one(
            {"_id": self.head_id},
            {
                "$inc": {"input_revision": 1},
                "$set": {f"active_writers.{self.token}": (now + timedelta(seconds=STALE_WRITE_SECONDS)).isoformat()},
            },
            upsert=True,
        )
        return self

    def __exit__(self, exc_type, exc, traceback):
        # If the source write succeeded but this close notification fails, the
        # active-writer marker makes publishers fail closed until recovery.
        self.cache.update_one(
            {"_id": self.head_id},
            {
                "$inc": {"input_revision": 1},
                "$unset": {f"active_writers.{self.token}": ""},
            },
            upsert=False,
        )
        return False


def claim_club_view_build(cache, competition, *, now=None, lease_seconds=BUILD_LEASE_SECONDS):
    comp = get_competition(competition)
    if not comp.is_club_competition:
        return None
    _ensure_head(cache, comp)
    current = parse_time(now or datetime.now(timezone.utc))
    head_id = overview_view_id(comp)
    head = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION) or {}
    active_writers = head.get("active_writers") or {}
    for token, until_value in active_writers.items() if isinstance(active_writers, Mapping) else ():
        try:
            expired = parse_time(until_value) <= current
        except (TypeError, ValueError, OverflowError):
            expired = False
        if expired:
            cache.update_one(
                {"_id": head_id, f"active_writers.{token}": until_value},
                {"$unset": {f"active_writers.{token}": ""}, "$inc": {"input_revision": 1}},
                upsert=False,
            )
    head = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION) or {}
    if head.get("active_writers"):
        return None

    try:
        lease_until = parse_time(head.get("lease_until"))
    except (TypeError, ValueError, OverflowError):
        lease_until = current
    if lease_until > current:
        return None

    generation = int(head.get("generation") or 0) + 1
    token = hashlib.sha256(f"{comp.id}:{generation}:{current.isoformat()}".encode()).hexdigest()
    query = {"_id": head_id, "input_revision": head.get("input_revision", 0),
             "generation": head.get("generation", 0), "active_writers": {}}
    query["lease_token"] = head["lease_token"] if "lease_token" in head else {"$exists": False}
    query["lease_until"] = head["lease_until"] if "lease_until" in head else {"$exists": False}
    updated = cache.update_one(
        query,
        {"$set": {"generation": generation, "lease_token": token,
                   "lease_until": (current + timedelta(seconds=lease_seconds)).isoformat()}},
        upsert=False,
    )
    if not getattr(updated, "matched_count", 0):
        return None
    return {"generation": generation, "input_revision": head.get("input_revision", 0), "lease_token": token}


def release_club_view_build(cache, competition, lease_token) -> None:
    if not lease_token:
        return
    cache.update_one(
        {"_id": overview_view_id(competition), "lease_token": lease_token},
        {"$set": {"lease_until": datetime.now(timezone.utc).isoformat()}},
        upsert=False,
    )


def _fixture_id(fixture: Mapping) -> str:
    value = fixture.get("id") or fixture.get("event_id")
    return str(value).strip() if value is not None else ""


def _is_completed(match: Mapping) -> bool:
    post = match.get("post_match_result") or {}
    status = str(match.get("status") or (post.get("status") if isinstance(post, Mapping) else "") or "").lower()
    return bool(match.get("completed") or match.get("actual_score") or match.get("score_90")
                or status in {"completed", "final", "post"})


def has_complete_club_prediction(match: Mapping) -> bool:
    probabilities = match.get("probabilities")
    provenance = match.get("input_provenance") or match.get("provenance")
    if not isinstance(probabilities, Mapping) or not {"home", "draw", "away"}.issubset(probabilities):
        return False
    try:
        values = [float(probabilities[key]) for key in ("home", "draw", "away")]
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            return False
        if not math.isclose(sum(values), 1, rel_tol=1e-9, abs_tol=1e-6):
            return False
        if any(not math.isfinite(float(match.get(key))) for key in ("xg_home", "xg_away")):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(
        isinstance(provenance, Mapping) and provenance
        and _normalised_matrix_dict(match.get("matrix") or match.get("score_matrix"))
        and (match.get("model_tip") or match.get("top_tip"))
        and match.get("source_mode") not in (None, "unavailable")
        and match.get("model_version")
    )


def _strip_raw_bookmakers(match: dict) -> None:
    raw = match.get("raw_match")
    if isinstance(raw, dict):
        match["raw_match"] = {key: value for key, value in raw.items() if key != "bookmakers"}


def _merge_archive(match: dict, entry: Mapping | None, *, archive_id: str):
    if not isinstance(entry, Mapping):
        return None
    prediction = entry.get("prediction") if isinstance(entry.get("prediction"), Mapping) else {}
    post = entry.get("post_match_result") if isinstance(entry.get("post_match_result"), Mapping) else {}
    if "user_tip" in prediction:
        match["user_tip"] = prediction.get("user_tip")
    if str(post.get("status") or "").lower() != "completed":
        return None

    match["post_match_result"] = deepcopy(dict(post))
    match["completed"] = True
    # Completed-match chances come only from the stored archive snapshot. If
    # older archive rows lack a value, keep it visibly unknown rather than
    # carrying a later cache calculation into historical display.
    for key in ("probabilities", "base_probabilities", "xg_home", "xg_away", "max_xp"):
        match[key] = None
    frozen = prediction.get("top_tip") or prediction.get("model_tip")
    snapshot = entry.get("pre_match_snapshot") if isinstance(entry.get("pre_match_snapshot"), Mapping) else {}
    for key in ("probabilities", "base_probabilities", "max_xp", "xg_home", "xg_away"):
        if key in prediction:
            match[key] = deepcopy(prediction[key])
        elif key in snapshot:
            match[key] = deepcopy(snapshot[key])
    score_inputs = prediction.get("score_inputs") or snapshot.get("score_inputs") or {}
    if isinstance(score_inputs, Mapping):
        for target, source in (("xg_home", "xg_home"), ("xg_away", "xg_away")):
            if match.get(target) is None and score_inputs.get(source) is not None:
                match[target] = deepcopy(score_inputs[source])
    if frozen:
        match["top_tip"] = frozen
        match["model_tip"] = prediction.get("model_tip") or frozen
        for key in ("pool_tip", "pool_status", "source_mode", "status", "source_status", "source", "observed_at", "model_version"):
            if key in prediction:
                match[key] = deepcopy(prediction[key])
            elif key in snapshot:
                match[key] = deepcopy(snapshot[key])
        for key in ("input_provenance", "provenance"):
            value = prediction.get(key) or snapshot.get(key)
            if value is not None:
                match[key] = deepcopy(value)
        context = prediction.get("context") or snapshot.get("context")
        if not context:
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
            context_keys = {
                "competition", "stage", "tie_id", "leg", "first_leg_score", "first_leg_home_score",
                "first_leg_away_score", "score_90", "score_aet", "shootout_winner",
                "extra_time_eligible", "commence_time",
            }
            context = {key: metadata[key] for key in context_keys if key in metadata}
        if context:
            match["context"] = deepcopy(context)
            match["match_context"] = deepcopy(context)
            for key in ("stage", "tie_id", "leg", "first_leg_score", "score_90", "score_aet", "shootout_winner", "extra_time_eligible"):
                if key in context:
                    match[key] = deepcopy(context[key])

    archived = {}
    for key in _ARCHIVE_PREDICTION_KEYS:
        if key in prediction:
            archived[key] = deepcopy(prediction[key])
        elif key in snapshot:
            archived[key] = deepcopy(snapshot[key])
    if isinstance(score_inputs, Mapping) and score_inputs:
        archived["score_inputs"] = deepcopy(dict(score_inputs))
    if prediction.get("frozen_at") or frozen:
        match["archived_prediction"] = archived
    if archive_id:
        match["archive_id"] = archive_id
    return archived or None


def _prediction_ready_row(source: Mapping, comp) -> dict:
    match = deepcopy(dict(source))
    raw = match.get("raw_match") if isinstance(match.get("raw_match"), Mapping) else {}
    round_name = raw.get("round", match.get("round", ""))
    match["is_ko_phase"] = _is_ko_round(round_name)
    if _is_completed(match):
        return match
    if has_complete_club_prediction(match) and match.get("model_version") == "prediction-club-v2":
        match.pop("calculation_status", None)
        return match
    for key in ("model_tip", "top_tip", "pool_tip", "probabilities", "base_probabilities",
                "xg_home", "xg_away", "max_xp", "edge_home", "elo_home_share", "market_home_share"):
        match[key] = None
    match.update({"matrix": {}, "score_matrix": {}, "regulation_matrix": {}, "bots": {},
                  "status": "unavailable", "source_status": "unavailable", "source_mode": "unavailable",
                  "pool_status": "unavailable", "calculation_status": "pending"})
    match.pop("model_version", None)
    return match


def _match_digest(match_id: str, match: Mapping, archive_entry: Mapping | None) -> str:
    value = {"id": match_id, "match": match, "archive": archive_entry}
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _without_archive_id(entry: Mapping) -> dict:
    return {key: deepcopy(value) for key, value in entry.items() if key != "_id"}


def build_match_views(fixtures, archive_by_id, competition) -> dict:
    """Build compact overview and per-game records without provider or DB I/O."""
    comp = get_competition(competition)
    if not comp.is_club_competition:
        raise ValueError("prepared club views only support EPL and UCL")
    archive = {
        str(match_id): _without_archive_id(entry) if isinstance(entry, Mapping) else {}
        for match_id, entry in (archive_by_id or {}).items()
    }
    archive_index = build_archive_id_index(archive)
    overview = []
    games = {}
    aliases = {}
    archive_ids = {}

    for source in fixtures if isinstance(fixtures, list) else ():
        if not isinstance(source, Mapping):
            continue
        match_id = _fixture_id(source)
        if not match_id:
            continue
        match = _prediction_ready_row(source, comp)
        raw = match.get("raw_match") if isinstance(match.get("raw_match"), Mapping) else {}
        home = match.get("home_team") or raw.get("home_team")
        away = match.get("away_team") or raw.get("away_team")
        kickoff = match.get("commence_time") or raw.get("commence_time") or ""
        archive_id = match_id if match_id in archive else None
        if archive_id is None and home and away and kickoff:
            date = str(kickoff)[:10]
            if date:
                dated_archive_ids = archive_index[0]
                archive_id = dated_archive_ids.get((
                    _canon_team(str(home)), _canon_team(str(away)), date,
                ))
        archive_entry = archive.get(str(archive_id)) if archive_id else None
        if archive_id and str(archive_id) != match_id:
            aliases[str(archive_id)] = match_id
        if archive_id:
            archive_ids[match_id] = str(archive_id)
        _merge_archive(match, archive_entry, archive_id=str(archive_id or ""))

        analysis = deepcopy(match)
        for key in ("home_form", "away_form", "match_intelligence", "bookmakers"):
            analysis.pop(key, None)
        _strip_raw_bookmakers(analysis)
        version = f"{match_id}:{_match_digest(match_id, analysis, archive_entry)}"

        compact = deepcopy(analysis)
        for key in _HEAVY_KEYS:
            compact.pop(key, None)
        _strip_raw_bookmakers(compact)
        compact.update({"detail_level": "overview", "view_version": version})

        core = deepcopy(compact)
        for key in _CORE_HEAVY_KEYS:
            core.pop(key, None)
        core.update({"detail_level": "core", "view_version": version})
        analysis.update({"detail_level": "analysis", "view_version": version})
        overview.append(compact)
        games[match_id] = {"view_version": version, "core": core, "analysis": analysis}

    # Keep only aliases that point to a current canonical fixture.
    canonical_ids = set(games)
    aliases = {alias: canonical for alias, canonical in aliases.items() if canonical in canonical_ids}
    versions = {match_id: record["view_version"] for match_id, record in games.items()}
    source_payload = json.dumps(
        {"overview": overview, "versions": versions, "aliases": aliases, "archive_ids": archive_ids},
        sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False,
    )
    return {
        "overview": overview,
        "games": games,
        "aliases": aliases,
        "archive_ids": archive_ids,
        "source_hash": hashlib.sha256(source_payload.encode("utf-8")).hexdigest(),
    }


def _record_filter(match_id: str, generation: int) -> dict:
    return {
        "_id": match_id,
        "$or": [{"generation": {"$lte": generation}}, {"generation": {"$exists": False}}],
    }


def publish_club_views(cache, competition, bundle: Mapping, *, generation: int,
                       input_revision: int | None = None, lease_token: str | None = None) -> bool:
    """Publish per-game records, then atomically switch the compact overview."""
    comp = get_competition(competition)
    head_id = overview_view_id(comp)
    head = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION) or {}
    revision = head.get("input_revision", 0) if input_revision is None else input_revision
    if (head.get("generation", 0) != generation
            or head.get("input_revision", 0) != revision
            or bool(head.get("active_writers"))
            or (lease_token is not None and head.get("lease_token") != lease_token)):
        return False

    existing_rows = cache.find(
        {"kind": "club_game_view", "competition": comp.id},
        {"_id": 1, "match_id": 1, "generation": 1, "view_version": 1,
         "core": 1, "previous.view_version": 1, "previous.core": 1},
    )
    existing_by_match = {
        str(row.get("match_id")): row for row in existing_rows
        if isinstance(row, Mapping) and row.get("match_id") is not None
    }
    changed_ids = [
        game_view_id(comp, match_id)
        for match_id, record in bundle.get("games", {}).items()
        if (existing_by_match.get(match_id) or {}).get("view_version") != record.get("view_version")
    ]
    analysis_by_id = {}
    if changed_ids:
        analysis_by_id = {
            row["_id"]: row for row in cache.find(
                {"_id": {"$in": changed_ids}},
                {"_id": 1, "analysis": 1, "previous.analysis": 1},
            ) if isinstance(row, Mapping) and row.get("_id") is not None
        }
    replacements = []
    for match_id, record in bundle.get("games", {}).items():
        doc_id = game_view_id(comp, match_id)
        existing = existing_by_match.get(match_id) or {}
        if existing.get("view_version") == record.get("view_version"):
            continue
        replacement = {
            "_id": doc_id,
            "kind": "club_game_view",
            "competition": comp.id,
            "match_id": match_id,
            "generation": generation,
            "view_version": record["view_version"],
            "core": deepcopy(record["core"]),
            "analysis": deepcopy(record["analysis"]),
        }
        expected_previous = (head.get("match_versions") or {}).get(match_id)
        analysis_row = analysis_by_id.get(doc_id) or {}
        if "analysis" in analysis_row:
            existing["analysis"] = analysis_row["analysis"]
        if "previous" in analysis_row:
            existing.setdefault("previous", {}).update(analysis_row["previous"])
        prior = existing if existing.get("view_version") == expected_previous else existing.get("previous") or {}
        if expected_previous and prior.get("view_version") == expected_previous:
            replacement["previous"] = {
                "view_version": expected_previous,
                "core": deepcopy(prior.get("core") or {}),
                "analysis": deepcopy(prior.get("analysis") or {}),
            }
        replacements.append(ReplaceOne(_record_filter(doc_id, generation), replacement, upsert=True))

    if replacements:
        try:
            cache.bulk_write(replacements, ordered=False)
        except (BulkWriteError, DuplicateKeyError):
            latest = cache.find_one({"_id": head_id}) or {}
            if latest.get("generation", 0) > generation:
                return False
            raise

    set_fields = {
        "competition": comp.id,
        "overview": deepcopy(bundle.get("overview") or []),
        "overview_gzip": encode_overview(bundle.get("overview") or []),
        "overview_encoding": OVERVIEW_ENCODING,
        "aliases": deepcopy(bundle.get("aliases") or {}),
        "archive_ids": deepcopy(bundle.get("archive_ids") or {}),
        "match_versions": {key: value.get("view_version") for key, value in bundle.get("games", {}).items()},
        "source_hash": bundle.get("source_hash"),
        "schema_version": CLUB_VIEW_SCHEMA_VERSION,
        "match_count": len(bundle.get("overview") or []),
        "published_revision": revision,
    }
    query = {"_id": head_id, "generation": generation, "input_revision": revision, "active_writers": {}}
    if lease_token is not None:
        query["lease_token"] = lease_token
    result = cache.update_one(query, {"$set": set_fields}, upsert=False)
    if not getattr(result, "matched_count", 0):
        return False

    return True


def _archive_projection() -> dict:
    projection = {"_id": 1, "metadata.home_team": 1, "metadata.away_team": 1,
                  "metadata.commence_time": 1, "metadata.competition": 1,
                  "post_match_result": 1}
    projection.update({
        f"metadata.{key}": 1 for key in (
            "stage", "tie_id", "leg", "first_leg_score", "first_leg_home_score",
            "first_leg_away_score", "score_90", "score_aet", "shootout_winner",
            "extra_time_eligible",
        )
    })
    projection.update({f"prediction.{key}": 1 for key in _ARCHIVE_PREDICTION_KEYS})
    projection.update({f"pre_match_snapshot.{key}": 1 for key in _ARCHIVE_PREDICTION_KEYS})
    return projection


def prepare_club_views(cache_collections, archive_collections, competition, *, now=None, force=False) -> dict:
    """Rebuild cached views without contacting providers; public reads never call this."""
    comp = get_competition(competition)
    if not comp.is_club_competition:
        return {"status": "skipped", "reason": "not_club_competition"}
    cache = collection_for(cache_collections, comp)
    archive = collection_for(archive_collections, comp)
    head_id = overview_view_id(comp)
    initial_head = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION)
    if not isinstance(initial_head, Mapping):
        _ensure_head(cache, comp)
        initial_head = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION) or {}
    if not force and _view_is_current(initial_head, cache, head_id):
        return {"status": "unchanged", "matches": int(initial_head.get("match_count") or 0)}
    claim = claim_club_view_build(cache, comp, now=now)
    if claim is None:
        return {"status": "skipped", "reason": "lease_held"}
    try:
        current_head = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION) or {}
        revision = claim["input_revision"]
        if current_head.get("input_revision", 0) != revision or current_head.get("active_writers"):
            return {"status": "skipped", "reason": "source_changed"}
        if not force and _view_is_current(current_head, cache, head_id):
            return {"status": "unchanged", "matches": int(current_head.get("match_count") or 0)}
        fixture_document = find_competition_document(cache, comp, "matches_cache")
        if not fixture_document or not isinstance(fixture_document.get("data"), list):
            return {"status": "unavailable", "reason": "matches_cache_missing"}
        # Archive aliases are resolved only by exact canonical team pair and kickoff date.
        archive_rows = archive.find({}, _archive_projection())
        archive_by_id = {
            str(row["_id"]): {key: deepcopy(value) for key, value in row.items() if key != "_id"}
            for row in archive_rows if isinstance(row, Mapping) and row.get("_id") is not None
        }
        bundle = build_match_views(fixture_document["data"], archive_by_id, comp)
        latest = cache.find_one({"_id": head_id}, _HEAD_STATE_PROJECTION) or {}
        if (latest.get("input_revision", 0) != revision
                or latest.get("active_writers")
                or latest.get("generation") != claim["generation"]
                or latest.get("lease_token") != claim["lease_token"]):
            return {"status": "skipped", "reason": "source_changed"}
        if latest.get("source_hash") == bundle["source_hash"]:
            # Reconcile missing derived rows even when a forced source audit finds
            # the same content hash. Publication skips unchanged game records.
            published = publish_club_views(
                cache, comp, bundle, generation=claim["generation"], input_revision=revision,
                lease_token=claim["lease_token"],
            )
            return {"status": "unchanged" if published else "skipped",
                    "matches": len(bundle["overview"])}
        published = publish_club_views(
            cache, comp, bundle, generation=claim["generation"], input_revision=revision,
            lease_token=claim["lease_token"],
        )
        return {"status": "success" if published else "skipped",
                "reason": None if published else "source_changed", "matches": len(bundle["overview"])}
    finally:
        release_club_view_build(cache, comp, claim["lease_token"])


def published_match_view(cache, competition, requested_id: str, *, analysis=False):
    """Return the matching published core record, honoring explicit archive aliases."""
    comp = get_competition(competition)
    head = cache.find_one({
        "_id": overview_view_id(comp),
    }, {"aliases": 1, "match_versions": 1, "published_revision": 1,
        "input_revision": 1, "active_writers": 1})
    if not isinstance(head, Mapping) or head.get("published_revision") is None:
        return head, None, requested_id
    canonical_id = (head.get("aliases") or {}).get(requested_id, requested_id)
    expected = (head.get("match_versions") or {}).get(canonical_id)
    if not expected:
        return head, None, canonical_id
    projection = {"view_version": 1, "previous.view_version": 1}
    projection.update({"analysis": 1, "previous.analysis": 1} if analysis else {"core": 1, "previous.core": 1})
    record = cache.find_one({"_id": game_view_id(comp, canonical_id)}, projection)
    if not isinstance(record, Mapping):
        return head, None, canonical_id
    if record.get("view_version") == expected:
        selected = record
    elif (record.get("previous") or {}).get("view_version") == expected:
        selected = record["previous"]
    else:
        return head, None, canonical_id
    return head, selected, canonical_id


def load_archive_match(archive, cache, competition, match_id: str) -> dict:
    """Read one archive row, resolving only an explicit prepared ID alias."""
    comp = get_competition(competition)
    entry = archive.find_one({"_id": match_id})
    if entry is None and comp.is_club_competition:
        head = cache.find_one({"_id": overview_view_id(comp)}, {"archive_ids": 1}) or {}
        archive_id = (head.get("archive_ids") or {}).get(match_id)
        if archive_id and archive_id != match_id:
            entry = archive.find_one({"_id": archive_id})
    if not isinstance(entry, Mapping):
        return {}
    return {match_id: {key: deepcopy(value) for key, value in entry.items() if key != "_id"}}


def patch_saved_tip(cache, competition, match_id: str, user_tip: str) -> bool:
    """Reflect an accepted tip in its two published views without a rebuild."""
    comp = get_competition(competition)
    head_id = overview_view_id(comp)
    for _attempt in range(2):
        head = cache.find_one({"_id": head_id}, {"aliases": 1, "overview": 1,
            "match_versions": 1, "generation": 1, "input_revision": 1,
            "published_revision": 1, "active_writers": 1})
        if not isinstance(head, Mapping) or head.get("published_revision") is None or head.get("active_writers"):
            return False
        canonical_id = (head.get("aliases") or {}).get(match_id, match_id)
        expected = (head.get("match_versions") or {}).get(canonical_id)
        if not expected:
            return False
        doc_id = game_view_id(comp, canonical_id)
        record = cache.find_one({"_id": doc_id}, {
            "view_version": 1, "core": 1, "analysis": 1,
            "previous.view_version": 1, "previous.core": 1,
        })
        if not isinstance(record, Mapping):
            return False
        digest = hashlib.sha256(f"{expected}\0user_tip\0{user_tip}".encode()).hexdigest()
        version = f"{canonical_id}:{digest}"
        game_ready_for_version = False
        if record.get("view_version") == version and (record.get("core") or {}).get("user_tip") == user_tip:
            game_ready_for_version = True
        elif (record.get("previous") or {}).get("view_version") == version and (
            ((record.get("previous") or {}).get("core") or {}).get("user_tip") == user_tip
        ):
            game_ready_for_version = True
        elif record.get("view_version") == expected:
            query = {"_id": doc_id, "view_version": expected}
            changes = {
                "view_version": version,
                "core.user_tip": user_tip,
                "core.view_version": version,
                "analysis.user_tip": user_tip,
                "analysis.view_version": version,
                "previous.view_version": expected,
                "previous.core": deepcopy(record.get("core") or {}),
                "previous.analysis": deepcopy(record.get("analysis") or {}),
            }
        elif (record.get("previous") or {}).get("view_version") == expected:
            # This is the sole published fallback while a newer build is pending.
            # Leave it intact; the source revision triggers a safe rebuild.
            return False
        else:
            return False
        if not game_ready_for_version:
            saved_game = cache.update_one(query, {"$set": changes}, upsert=False)
            if not getattr(saved_game, "matched_count", 0):
                continue

        overview = deepcopy(head.get("overview") or [])
        for row in overview:
            if isinstance(row, dict) and str(row.get("id")) == canonical_id:
                row["user_tip"] = user_tip
                row["view_version"] = version
                break
        versions = dict(head.get("match_versions") or {})
        versions[canonical_id] = version
        saved_head = cache.update_one(
            {"_id": head_id, "generation": head.get("generation"),
             "input_revision": head.get("input_revision"),
             "published_revision": head.get("published_revision"), "active_writers": {}},
            {"$set": {"overview": overview, "overview_gzip": encode_overview(overview),
                      "overview_encoding": OVERVIEW_ENCODING, "match_versions": versions}},
            upsert=False,
        )
        if getattr(saved_head, "matched_count", 0):
            return True
    return False


def refresh_club_views_once(cache_collections, archive_collections) -> dict:
    """Prepare both competitions from persisted cache/archive data only."""
    return {
        comp.id: prepare_club_views(cache_collections, archive_collections, comp)
        for comp in COMPETITIONS.values() if comp.is_club_competition
    }


async def run_club_views_worker(cache_collections, archive_collections):
    """Warm on startup, then check dirty views cheaply and audit stored data every five minutes."""
    loop = asyncio.get_running_loop()
    last_audit = None
    retry_audit_after = 0.0
    first_cycle = True
    while True:
        started = loop.time()
        audit_due = first_cycle or last_audit is None or started - last_audit >= SOURCE_AUDIT_SECONDS
        force_audit = audit_due and started >= retry_audit_after
        audit_ok = True
        for comp in COMPETITIONS.values():
            if not comp.is_club_competition:
                continue
            try:
                result = await asyncio.to_thread(
                    prepare_club_views, cache_collections, archive_collections, comp,
                    force=force_audit,
                )
                if force_audit and result.get("status") not in {"success", "unchanged"}:
                    audit_ok = False
            except Exception as exc:
                if force_audit:
                    audit_ok = False
                logger.warning("Club view preparation failed for %s (%s)", comp.id, type(exc).__name__)
        if force_audit:
            completed = loop.time()
            if audit_ok:
                last_audit = completed
                retry_audit_after = 0.0
            else:
                retry_audit_after = completed + SOURCE_AUDIT_RETRY_SECONDS
        first_cycle = False
        elapsed = loop.time() - started
        await asyncio.sleep(max(0.0, WORKER_INTERVAL_SECONDS - elapsed))
