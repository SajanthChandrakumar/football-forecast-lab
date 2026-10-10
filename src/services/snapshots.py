"""Append-only odds observations and exact maintenance bucket semantics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.competitions import competition_document_id, find_competition_document, get_competition


BUCKET_OFFSETS = {
    "t24h": 1440,
    "t6h": 360,
    "t75m": 75,
    "t30m": 30,
    "t15m": 15,
}
SNAPSHOT_BUCKETS = (*BUCKET_OFFSETS, "manual")
SNAPSHOT_STATUSES = frozenset({"fresh", "stale", "unavailable", "failed"})


def normalize_status(value, *, default: str = "fresh") -> str:
    status = default if value is None else str(value)
    if status not in SNAPSHOT_STATUSES:
        raise ValueError(f"status must be one of {sorted(SNAPSHOT_STATUSES)}")
    return status


def parse_time(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def due_buckets(kickoff_at, now=None, claimed=()) -> list[str]:
    kickoff = parse_time(kickoff_at)
    current = parse_time(now or datetime.now(timezone.utc))
    claimed = set(claimed)
    return [
        label for label, minutes in BUCKET_OFFSETS.items()
        if label not in claimed
        and current >= kickoff - timedelta(minutes=minutes)
        and current < kickoff
    ]


def append_odds_snapshot(
    cache_collection,
    competition,
    event_id: str,
    bucket: str,
    observed_at,
    odds: dict,
    *,
    source: str = "odds_api",
    status: str = "fresh",
    error: str | None = None,
) -> dict:
    if bucket not in SNAPSHOT_BUCKETS:
        raise ValueError(f"Unknown odds bucket: {bucket}")
    status = normalize_status(status)
    comp = get_competition(competition)
    observed = parse_time(observed_at).isoformat()
    document = {
        "_id": f"{comp.id}:odds_snapshot:{event_id}:{bucket}:{observed}",
        "competition": comp.id,
        "event_id": str(event_id),
        "bucket": bucket,
        "observed_at": observed,
        "source": source,
        "status": status,
        "odds": odds or {},
    }
    if error:
        document["error"] = error
    # insert_one is intentionally used instead of update/upsert: snapshots are
    # an append-only audit trail. A repeated claim at the same instant is safe.
    try:
        cache_collection.insert_one(document)
    except Exception as exc:
        if "duplicate" not in str(exc).lower() and "unique" not in str(exc).lower():
            raise
    return document


def mark_bucket(
    cache_collection,
    competition,
    event_id: str,
    bucket: str,
    *,
    status: str,
    observed_at=None,
    error: str | None = None,
    source: str = "odds_api",
) -> None:
    comp = get_competition(competition)
    status = normalize_status(status)
    update = {"$set": {f"events.{event_id}.{bucket}": {
        "status": status,
        "source": source,
        **({"observed_at": parse_time(observed_at).isoformat()} if observed_at else {}),
        **({"error": error} if error else {}),
    }}}
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "odds_bucket_state")},
        update,
        upsert=True,
    )


def bucket_state(cache_collection, competition, event_id: str) -> dict:
    comp = get_competition(competition)
    document = find_competition_document(cache_collection, comp, "odds_bucket_state") or {}
    events = document.get("events") or {}
    value = events.get(str(event_id), {})
    return value if isinstance(value, dict) else {label: {"status": "captured"} for label in value}


def select_t15_snapshot(snapshots, kickoff_at):
    """Return the newest snapshot observed no later than T-15."""
    cutoff = parse_time(kickoff_at) - timedelta(minutes=15)
    eligible = []
    if isinstance(snapshots, dict):
        snapshots = snapshots.get("snapshots") or snapshots.get("data") or []
    for snapshot in snapshots or []:
        try:
            observed = parse_time(snapshot.get("observed_at") or snapshot.get("captured_at"))
        except (TypeError, ValueError):
            continue
        if observed <= cutoff and snapshot.get("status", "fresh") in {"fresh", "stale"}:
            eligible.append((observed, snapshot))
    return max(eligible, key=lambda item: item[0])[1] if eligible else None


# Friendly aliases for integrations and tests.
select_latest_t15 = select_t15_snapshot
get_due_buckets = due_buckets
