"""Age checks for club sources; attempted refreshes never prove freshness."""
from datetime import datetime, timedelta, timezone

MAX_SOURCE_AGE = timedelta(hours=24)


def source_status(status, observed_at, *, now=None):
    if status in {"failed", "unavailable"}:
        return status
    try:
        observed = observed_at if isinstance(observed_at, datetime) else datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if observed.tzinfo is None or current.tzinfo is None:
            return "stale"
        age = current - observed
    except (TypeError, ValueError, OverflowError):
        return "stale"
    if status == "stale" or not timedelta(0) <= age <= MAX_SOURCE_AGE:
        return "stale"
    return "fresh"
