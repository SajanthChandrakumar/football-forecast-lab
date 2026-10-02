"""Persist API-quota counters in MongoDB so they survive on Render.

Render's filesystem is ephemeral — it resets on every deploy, restart, and
free-tier spin-down. The quota counters used to live in `data/*.json`, which
meant `/api/quota` returned `--` after every cold start. Everything else in
this app (matches, archive, standings) is persisted in MongoDB;
this module brings quota in line with that.

Quota display falls back to local files without Mongo. Paid requests do not:
their shared atomic budget must be available before contacting a provider.
"""

import os
import json
import logging
import time

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# provider -> local-dev fallback filename (kept identical to the old behaviour)
_FILES = {
    "odds": "api_quota_odds.json",
    "football": "api_quota.json",
}
_DEFAULT = {"remaining": "--", "used": "?"}

_collection = None
_resolved = False  # whether we've attempted the (lazy, one-shot) Mongo connect

# Conservative rolling windows avoid assuming a provider's billing/reset date.
BUDGETS = {"odds": (400, 31 * 86400, 100), "football": (80, 86400, 20)}


class ProviderBudgetExceeded(RuntimeError):
    """No request was sent: shared budget, pacing, or persistence is unavailable."""


def reserve_request(provider: str, cost: int = 1, *, now=None) -> float:
    """Atomically reserve before HTTP, shared by all competitions and workers.

    Failed/empty requests remain charged locally (conservative). There is no
    process-only fallback: if Mongo cannot reserve, paid requests are blocked.
    Returns a bounded wait for the shared API-Football minute limit.
    """
    if provider not in BUDGETS or isinstance(cost, bool) or not isinstance(cost, int) or cost < 1:
        raise ValueError("Invalid provider request cost")
    current = time.time() if now is None else float(now)
    cap, window, headroom = BUDGETS[provider]
    collection = _get_collection()
    if collection is None:
        raise ProviderBudgetExceeded("Shared provider budget unavailable; request blocked")
    document_id = f"provider_budget:{provider}"
    try:
        for _ in range(12):
            document = collection.find_one({"_id": document_id})
            if document is None:
                try:
                    collection.insert_one({"_id": document_id, "version": 0, "requests": []})
                except Exception as exc:
                    if "duplicate" not in str(exc).lower():
                        raise
                continue
            events = [entry for entry in document.get("requests", []) if current - entry[0] < window]
            if sum(entry[1] for entry in events) + cost > cap:
                raise ProviderBudgetExceeded(f"Shared {provider} budget exhausted ({cap} per rolling window)")
            quota = collection.find_one({"_id": f"quota_{provider}"}) or {}
            # Unknown counters do not override the hard local ceiling. Known
            # recent remaining quota also protects usage outside this app.
            try:
                remaining = int((quota.get("data") or {}).get("remaining"))
                if quota.get("observed_at") is not None and current - float(quota["observed_at"]) < window and remaining - cost < headroom:
                    raise ProviderBudgetExceeded(f"{provider} provider reserve reached; request blocked")
            except (TypeError, ValueError):
                pass
            scheduled = current
            if provider == "football" and events:
                scheduled = max(current, events[-1][0] + 7)
                if len(events) >= 9:
                    scheduled = max(scheduled, events[-9][0] + 60)
                if scheduled - current > 30:
                    raise ProviderBudgetExceeded("Shared football minute budget busy; retry later")
            version = document["version"]
            result = collection.update_one(
                {"_id": document_id, "version": version},
                {"$set": {"version": version + 1, "requests": events + [[scheduled, cost]],
                          "limit": cap, "window_seconds": window, "updated_at": current}},
                upsert=False,
            )
            if result.matched_count:
                return max(0, scheduled - current)
        raise ProviderBudgetExceeded("Shared provider budget busy; request blocked")
    except ProviderBudgetExceeded:
        raise
    except Exception:
        raise ProviderBudgetExceeded("Shared provider budget unavailable; request blocked") from None


def _get_collection():
    """Lazily connect to the same `wm2026_db.cache` collection api.py uses.

    Returns None when MONGO_URI is unset or the connection fails — callers then
    fall back to the local filesystem. The connection is attempted once and the
    result (collection or None) is cached for the process lifetime.
    """
    global _collection, _resolved
    if _resolved:
        return _collection
    _resolved = True

    uri = os.getenv("MONGO_URI")
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        import certifi
        client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
        _collection = client["wm2026_db"]["cache"]
    except Exception as e:
        logger.warning(f"quota_store: MongoDB unavailable, using files: {e}")
        _collection = None
    return _collection


def write_quota(provider: str, data: dict) -> None:
    """Persist the latest quota counters for a provider ('odds' | 'football')."""
    coll = _get_collection()
    if coll is not None:
        try:
            coll.update_one(
                {"_id": f"quota_{provider}"},
                {"$set": {"data": data, "observed_at": time.time()}},
                upsert=True,
            )
            return
        except Exception as e:
            logger.warning(f"quota_store: Mongo write failed ({provider}): {e}")

    # Filesystem fallback (local dev without MongoDB)
    fname = _FILES.get(provider)
    if not fname:
        return
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(os.path.join(_DATA_DIR, fname), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.warning(f"quota_store: file write failed ({provider}): {e}")


def read_quota(provider: str) -> dict:
    """Return the latest stored quota for a provider, or a placeholder default."""
    coll = _get_collection()
    if coll is not None:
        try:
            doc = coll.find_one({"_id": f"quota_{provider}"})
            if doc and isinstance(doc.get("data"), dict):
                return doc["data"]
        except Exception as e:
            logger.warning(f"quota_store: Mongo read failed ({provider}): {e}")

    fname = _FILES.get(provider)
    if fname:
        try:
            with open(os.path.join(_DATA_DIR, fname), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return dict(_DEFAULT)
