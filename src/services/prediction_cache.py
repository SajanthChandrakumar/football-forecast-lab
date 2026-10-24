"""Bounded process-local reuse of pure club predictions, keyed by every input."""
from collections import OrderedDict
from copy import deepcopy
import json
from threading import RLock
import time

_cache = OrderedDict()
_lock = RLock()
_MAX_ENTRIES = 2048
_TTL_SECONDS = 24 * 60 * 60


def clear_prediction_cache():
    with _lock:
        _cache.clear()


def cached_prediction(service, competition, **inputs):
    from src.competitions import get_competition
    comp = get_competition(competition)
    if not comp.is_club_competition:
        return service.predict(competition=comp, **inputs)
    from src.services.source_freshness import source_status
    inputs = deepcopy(inputs)
    for name in ("odds", "elo"):
        source = inputs.get(name)
        if isinstance(source, dict):
            observed = source.get("observed_at") or (source.get("provenance") or {}).get("observed_at")
            source["status"] = source_status(source.get("status", "fresh"), observed)
    version = service.model_version_for(comp) if hasattr(service, "model_version_for") else service.model_version
    key = (id(service.math_engine), comp.id, version, json.dumps(inputs, sort_keys=True, default=str, separators=(",", ":")))
    # ponytail: serialize a cold calculation to avoid duplicate CPU work; shard only if measured contention warrants it.
    with _lock:
        previous = _cache.get(key)
        if previous and time.monotonic() - previous[0] < _TTL_SECONDS:
            _cache.move_to_end(key)
            return deepcopy(previous[1])
        result = service.predict(competition=comp, **inputs)
        _cache[key] = (time.monotonic(), deepcopy(result))
        _cache.move_to_end(key)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
        return result
