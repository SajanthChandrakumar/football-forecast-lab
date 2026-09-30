import time
import logging

from src.constants import TEAM_MAPPING

logger = logging.getLogger(__name__)

# ── In-process archive cache ─────────────────────────────────────────────────
# Avoids a full MongoDB collection scan on every /api/matches cache-hit.
# Invalidated explicitly after any write (upsert_archive_entry) so reads
# always see the latest user tips and match results within 2 minutes. The
# cache is keyed by collection identity/name so WC and UCL snapshots cannot
# leak into one another.
_archive_mem: dict = {}
_archive_mem_ts: dict = {}
_ARCHIVE_MEM_TTL = 120  # seconds

# User-provided UCL tips for already completed matches. The identifiers and
# expected fixture data make this one-time shared backfill safe to retry.
_SHARED_HISTORICAL_UCL_TIPS = (
    ("401915452", "2026-09-08", "AEK Athens", "LASK Linz", "2:1", "1:0"),
    ("401915426", "2026-09-08", "Club Brugge", "Aston Villa", "1:2", "2:3"),
    ("401915451", "2026-09-08", "Real Madrid", "Internazionale", "2:1", "2:1"),
    ("401915450", "2026-09-08", "Lille", "Real Betis", "1:1", "2:3"),
    ("401915425", "2026-09-08", "FC Porto", "Manchester City", "1:2", "0:2"),
    ("401915449", "2026-09-08", "Borussia Dortmund", "Villarreal", "2:0", "3:2"),
    ("401915424", "2026-09-09", "Barcelona", "Feyenoord Rotterdam", "3:1", "5:1"),
    ("401915448", "2026-09-09", "VfB Stuttgart", "Viking FK", "2:1", "3:1"),
    ("401915423", "2026-09-09", "Napoli", "Arsenal", "1:2", "0:1"),
    ("401915447", "2026-09-09", "Sporting CP", "Galatasaray", "2:1", "3:1"),
    ("401915446", "2026-09-09", "Liverpool", "Atlético Madrid", "2:1", "2:1"),
    ("401915445", "2026-09-09", "Paris Saint-Germain", "Slovan Bratislava", "3:0", "6:1"),
    ("401915422", "2026-09-10", "PSV Eindhoven", "Shakhtar Donetsk", "2:1", "1:1"),
    ("401915444", "2026-09-10", "Fenerbahce", "AS Roma", "1:2", "1:1"),
    ("401915440", "2026-09-10", "Slavia Prague", "Lens", "1:1", "2:3"),
    ("401915443", "2026-09-10", "Bayern Munich", "Bodo/Glimt", "4:1", "5:0"),
    ("401915441", "2026-09-10", "Como", "RB Leipzig", "1:2", "4:1"),
    ("401915442", "2026-09-10", "Manchester United", "Sabah FK", "4:0", "4:0"),
)


def _canon_team(name: str) -> str:
    """Canonical team name for cross-source matching (ESPN ↔ Odds API ↔ archive)."""
    return TEAM_MAPPING.get(name, name)


def build_archive_id_index(archive: dict):
    """
    Build a lookup so an external fixture (home, away, date) can be resolved to
    the existing archive _id. Prefer a date-qualified key so a stale entry can't
    absorb a different match with the same pairing; fall back to (home, away)
    for legacy entries written without a commence_time.
    """
    dated = {}
    undated = {}
    for mid, entry in archive.items():
        meta = entry.get("metadata") or {}
        h, a, ct = meta.get("home_team"), meta.get("away_team"), meta.get("commence_time") or ""
        if not (h and a):
            continue
        hc, ac = _canon_team(h), _canon_team(a)
        if ct[:10]:
            dated[(hc, ac, ct[:10])] = mid
        else:
            undated.setdefault((hc, ac), mid)
    return dated, undated


def resolve_archive_id(index, home: str, away: str, date: str):
    """Return the archive _id for a fixture, or None if it's a new match."""
    dated, undated = index
    hc, ac = _canon_team(home), _canon_team(away)
    d = (date or "")[:10]
    return dated.get((hc, ac, d)) or undated.get((hc, ac))


def _archive_cache_key(archive_collection) -> str:
    """Use the Mongo collection name when available, otherwise object identity."""
    for attr in ("full_name", "name"):
        value = getattr(archive_collection, attr, None)
        if value:
            return str(value)
    return f"collection:{id(archive_collection)}"


def load_archive_from_db(archive_collection, force: bool = False) -> dict:
    global _archive_mem, _archive_mem_ts
    if not isinstance(_archive_mem, dict):
        _archive_mem = {}
    if not isinstance(_archive_mem_ts, dict):
        _archive_mem_ts = {}
    cache_key = _archive_cache_key(archive_collection)
    now = time.time()
    if (
        not force
        and cache_key in _archive_mem
        and (now - _archive_mem_ts.get(cache_key, 0.0)) < _ARCHIVE_MEM_TTL
    ):
        return _archive_mem[cache_key]  # serve from RAM — no MongoDB round-trip
    result = {}
    try:
        for doc in archive_collection.find():
            mid = doc["_id"]
            result[mid] = {k: v for k, v in doc.items() if k != "_id"}
        _archive_mem[cache_key] = result
        _archive_mem_ts[cache_key] = now
    except Exception as e:
        logger.error(f"Failed to load archive from MongoDB: {e}")
        if cache_key in _archive_mem:  # return stale cache on error rather than empty dict
            return _archive_mem[cache_key]
    return result


def invalidate_archive_mem_cache(archive_collection=None) -> None:
    """Call after any write so the next read fetches fresh data from MongoDB."""
    global _archive_mem_ts
    if not isinstance(_archive_mem_ts, dict):
        _archive_mem_ts = {}
    if archive_collection is None:
        _archive_mem_ts = {key: 0.0 for key in _archive_mem_ts}
        return
    _archive_mem_ts[_archive_cache_key(archive_collection)] = 0.0


def upsert_archive_entry(archive_collection, match_id: str, entry: dict) -> None:
    archive_collection.replace_one(
        {"_id": match_id},
        {"_id": match_id, **entry},
        upsert=True
    )
    invalidate_archive_mem_cache(archive_collection)  # next read will re-fetch from MongoDB


def seed_shared_historical_ucl_tips(archive_collection, calculate_points) -> dict:
    """Backfill the user's 18 completed UCL tips into the shared archive once.

    Only exact, completed fixture matches with the expected result are eligible.
    Existing tips are never overwritten, making this safe on every API startup.
    """
    archive = load_archive_from_db(archive_collection, force=True)
    updated = skipped = points_added = 0
    for match_id, date, home, away, tip, actual in _SHARED_HISTORICAL_UCL_TIPS:
        entry = archive.get(match_id)
        if not entry:
            skipped += 1
            continue

        metadata = entry.get("metadata") or {}
        result = entry.get("post_match_result") or {}
        prediction = entry.get("prediction") or {}
        if (
            result.get("status") != "completed"
            or result.get("actual_score") != actual
            or (metadata.get("commence_time") or "")[:10] != date
            or metadata.get("home_team") != home
            or metadata.get("away_team") != away
            or metadata.get("is_ko_phase") is True
            or prediction.get("user_tip") not in (None, "")
        ):
            skipped += 1
            continue

        points = calculate_points(tip, actual, False)
        updated_entry = {**entry}
        updated_entry["prediction"] = {
            **prediction,
            "user_tip": tip,
            "user_tip_source": "shared_historical",
        }
        updated_entry["post_match_result"] = {
            **result,
            "points_earned": points,
        }
        upsert_archive_entry(archive_collection, match_id, updated_entry)
        updated += 1
        points_added += points

    return {"updated": updated, "skipped": skipped, "points_added": points_added}
