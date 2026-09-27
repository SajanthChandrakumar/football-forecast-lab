"""Credit-safe, idempotent maintenance for provider snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from uuid import uuid4

from src.competitions import collection_for, competition_document_id, find_competition_document, get_competition
from src.constants import DISPLAY_MAPPING, TEAM_MAPPING, _is_ko_round
from src.math_engine import MathEngine
from src.services.archive import (
    invalidate_archive_mem_cache,
    load_archive_from_db,
    upsert_archive_entry,
)
from src.services.elo_sync import _reconstruct_completed_entries
from src.services.odds_helpers import extract_odds
from src.services.prediction import PredictionService
from src.services.snapshots import append_odds_snapshot, bucket_state, due_buckets, mark_bucket, parse_time


LEASE_SECONDS = 300
DISCOVERY_INTERVAL = timedelta(days=1)


def run_maintenance(
    cache_collections,
    odds_provider,
    *,
    archive_collections=None,
    competition=None,
    now=None,
    force: bool = False,
    lease_seconds: int = LEASE_SECONDS,
    fixture_fetcher=None,
    clubelo_ingestor=None,
    math_engine=None,
    team_form_service=None,
) -> dict:
    """Capture due odds buckets with at most one bulk provider call.

    ``force`` is deliberately a public no-op.  Manual/public refreshes cannot
    spend provider credits or write a snapshot; only the authenticated route
    should invoke normal maintenance.
    """
    comp = get_competition(competition)
    if force:
        result = {"status": "noop", "reason": "force_disabled", "provider_calls": 0, "mutated": False}
        if comp.id == "ucl2026":
            result["team_form_status"] = {"status": "skipped", "reason": "force_disabled"}
        return result
    cache_collection = collection_for(cache_collections, comp)
    current = parse_time(now or datetime.now(timezone.utc))
    lease_id = competition_document_id(comp, "maintenance_lease")
    lease_token = uuid4().hex
    lease = {
        "_id": lease_id,
        "competition": comp.id,
        "lease_until": (current + timedelta(seconds=lease_seconds)).isoformat(),
        "lease_token": lease_token,
    }
    try:
        cache_collection.insert_one(lease)
        owns_lease = True
    except Exception:
        # Unique _id is the Mongo claim. A live holder wins; a crashed worker's
        # expired claim can be atomically replaced using its old lease value.
        existing = cache_collection.find_one({"_id": lease_id}) or {}
        try:
            expiry = parse_time(existing.get("lease_until"))
        except (TypeError, ValueError):
            expiry = current
        if expiry > current:
            result = {"status": "skipped", "reason": "lease_held", "provider_calls": 0, "mutated": False, "buckets": []}
            if comp.id == "ucl2026":
                result["team_form_status"] = {"status": "skipped", "reason": "lease_held"}
            return result
        result = cache_collection.update_one(
            {"_id": lease_id, "lease_until": existing.get("lease_until")},
            {"$set": {key: value for key, value in lease.items() if key != "_id"}},
            upsert=False,
        )
        matched = getattr(result, "matched_count", None)
        if matched == 0:
            owns_lease = False
        elif matched is None:
            owns_lease = (cache_collection.find_one({"_id": lease_id}) or {}).get("lease_token") == lease_token
        else:
            owns_lease = True
    if not owns_lease:
        result = {"status": "skipped", "reason": "lease_held", "provider_calls": 0, "mutated": False, "buckets": []}
        if comp.id == "ucl2026":
            result["team_form_status"] = {"status": "skipped", "reason": "lease_held"}
        return result

    fixture_status = {"status": "fresh", "source": "cache", "observed_at": current.isoformat()}
    clubelo_status = None
    team_form_status = None
    try:
        if comp.id == "ucl2026":
            team_form_status = {"status": "unavailable", "source": "api_football", "error": "team form service unavailable"}
            if team_form_service is not None:
                try:
                    team_form_status = team_form_service.refresh_daily(now=current)
                except Exception as exc:
                    team_form_status = {"status": "stale", "source": "api_football", "error": str(exc), "observed_at": current.isoformat()}
        if fixture_fetcher is not None:
            fixture_status = _refresh_fixtures(cache_collection, comp, fixture_fetcher, current)
        if comp.id == "ucl2026" and clubelo_ingestor is not None:
            clubelo_status = clubelo_ingestor(cache_collection, competition=comp, observed_at=current)
        fixtures = _fixtures(cache_collection, comp)
        archived_results = 0
        reconstructed_results = 0
        snapshot_predictions = 0
        predictions_updated = 0
        rows = (clubelo_status or {}).get("rows") or []
        if comp.id == "ucl2026" and math_engine is not None and rows:
            import pandas as pd
            math_engine.elo_df = pd.DataFrame(rows)
        if archive_collections is not None:
            archive_collection = collection_for(archive_collections, comp)
            archived_results = _sync_completed_results(
                archive_collection, fixtures, comp
            )
            if comp.id == "ucl2026" and math_engine is not None:
                archive = load_archive_from_db(archive_collection, force=True)
                changed_entries = {}
                reconstructed_results, snapshot_predictions = _reconstruct_completed_entries(
                    PredictionService(math_engine),
                    archive,
                    changed_entries,
                    MathEngine,
                    comp,
                    cache_collection=cache_collection,
                )
                for match_id, entry in changed_entries.items():
                    upsert_archive_entry(archive_collection, match_id, entry)
        due_by_event = {}
        all_due = []
        for fixture in fixtures:
            event_id = str(fixture.get("id") or fixture.get("event_id") or "")
            kickoff = fixture.get("commence_time") or (fixture.get("raw_match") or {}).get("commence_time")
            if not event_id or not kickoff:
                continue
            due = due_buckets(kickoff, current, bucket_state(cache_collection, comp, event_id).keys())
            if due:
                due_by_event[event_id] = (fixture, due)
                all_due.extend(due)
        discovery_due = _discovery_due(cache_collection, comp, current)
        if not due_by_event and not discovery_due:
            predictions_updated = _persist_ucl_predictions(cache_collection, comp, math_engine, clubelo_status)
            return {
                "status": "idle",
                "provider_calls": 0,
                "mutated": bool(
                    (comp.id == "ucl2026" and fixture_status.get("changed"))
                    or archived_results
                    or reconstructed_results
                    or snapshot_predictions
                    or predictions_updated
                ),
                "buckets": [],
                "fixture_status": fixture_status,
                "clubelo_status": clubelo_status,
                **({"team_form_status": team_form_status} if comp.id == "ucl2026" else {}),
                "archived_results": archived_results,
                "reconstructed_results": reconstructed_results,
                "snapshot_predictions": snapshot_predictions,
            }

        try:
            quotes = _bulk_quotes(odds_provider, comp)
        except Exception as exc:
            if comp.id == "ucl2026":
                _record_discovery(cache_collection, comp, current, "failed", error=str(exc))
            for event_id, (fixture, due) in due_by_event.items():
                for bucket in due[:-1]:
                    mark_bucket(cache_collection, comp, event_id, bucket, status="unavailable", observed_at=current, error="missed")
                mark_bucket(cache_collection, comp, event_id, due[-1], status="failed", observed_at=current, error=str(exc))
            predictions_updated = _persist_ucl_predictions(
                cache_collection, comp, math_engine, clubelo_status
            )
            return {
                "status": "failed",
                "source": "odds_api",
                "observed_at": current.isoformat(),
                "error": str(exc),
                "provider_calls": 1,
                "mutated": True,
                "buckets": sorted(set(all_due), key=lambda item: list(_bucket_order()).index(item)),
                "fixture_status": fixture_status,
                "clubelo_status": clubelo_status,
                **({"team_form_status": team_form_status} if comp.id == "ucl2026" else {}),
                "archived_results": archived_results,
                "reconstructed_results": reconstructed_results,
                "snapshot_predictions": snapshot_predictions,
            }

        lookup = _quote_lookup(quotes)
        if comp.id == "ucl2026":
            _record_discovery(cache_collection, comp, current, "fresh", events=len(quotes))
        available_by_event = {}
        for fixture in fixtures:
            event_id = str(fixture.get("id") or fixture.get("event_id") or "")
            match = lookup.get(event_id) or _match_by_names(lookup, fixture)
            odds = _extract_odds(match) if match else {}
            if event_id and match:
                available_by_event[event_id] = (match, odds)
            if event_id and odds:
                _store_fixture_odds(cache_collection, comp, event_id, odds, match, current)
        for event_id, (fixture, due) in due_by_event.items():
            # Missing historical windows become explicit missed buckets; only
            # the current (closest-to-kickoff) observation is recorded.
            for bucket in due[:-1]:
                mark_bucket(cache_collection, comp, event_id, bucket, status="unavailable", observed_at=current, error="missed")
            match, odds = available_by_event.get(event_id, (None, {}))
            observed_bucket = due[-1]
            if match is None:
                append_odds_snapshot(
                    cache_collection, comp, event_id, observed_bucket, current, {}, status="unavailable",
                    error="event not returned by odds provider",
                )
                mark_bucket(cache_collection, comp, event_id, observed_bucket, status="unavailable", observed_at=current, error="event not returned by odds provider")
            else:
                snapshot_status = "fresh" if odds else "unavailable"
                append_odds_snapshot(cache_collection, comp, event_id, observed_bucket, current, odds, status=snapshot_status)
                mark_bucket(cache_collection, comp, event_id, observed_bucket, status="fresh" if odds else "unavailable", observed_at=current)
                if odds:
                    _store_fixture_odds(cache_collection, comp, event_id, odds, match, current)
        _persist_ucl_predictions(cache_collection, comp, math_engine, clubelo_status)
        return {
            "status": "success",
            "provider_calls": 1,
            "mutated": True,
            "buckets": sorted(set(all_due), key=lambda item: list(_bucket_order()).index(item)),
            "events": len(due_by_event),
            "fixture_status": fixture_status,
            "clubelo_status": clubelo_status,
            **({"team_form_status": team_form_status} if comp.id == "ucl2026" else {}),
            "archived_results": archived_results,
            "reconstructed_results": reconstructed_results,
            "snapshot_predictions": snapshot_predictions,
            "discovery": discovery_due,
        }
    finally:
        cache_collection.delete_one({"_id": lease_id, "lease_token": lease_token})


def _fixtures(cache_collection, competition) -> list[dict]:
    document = find_competition_document(cache_collection, competition, "matches_cache") or {}
    return document.get("data") or []


def _persist_ucl_predictions(cache_collection, competition, math_engine, clubelo_status) -> int:
    """Persist open UCL fixture predictions for cache-only public reads and simulation."""
    comp = get_competition(competition)
    if comp.id != "ucl2026" or math_engine is None:
        return 0
    if not isinstance(clubelo_status, dict) or clubelo_status.get("status") not in {"fresh", "stale"}:
        return 0
    document = find_competition_document(cache_collection, comp, "matches_cache") or {}
    fixtures = document.get("data")
    if not isinstance(fixtures, list) or not fixtures:
        return 0

    # Reuse the same enrichment path as match presentation. This runs only
    # inside authenticated maintenance; public cache reads remain read-only.
    from src.routes.matches import _enrich_edge, _is_completed_match
    from src.services.ucl_simulation import _normalised_matrix_dict

    prediction_fields = (
        "model_tip", "top_tip", "pool_tip", "pool_status", "status", "source_status",
        "source", "observed_at", "source_mode", "model_version", "input_provenance",
        "provenance", "xg_home", "xg_away", "probabilities", "matrix", "score_matrix", "max_xp",
        "context", "match_context", "elo_home_share", "market_home_share", "edge_home",
    )
    originals = {
        str(match.get("id") or match.get("event_id")): dict(match)
        for match in fixtures
        if isinstance(match, dict) and (match.get("id") or match.get("event_id"))
    }
    matches = [
        match for match in fixtures
        if isinstance(match, dict) and not _is_completed_match(match)
    ]
    if not matches:
        return 0
    _enrich_edge(matches, math_engine, None, comp, cache_collection)

    updated = 0
    for match in matches:
        match_id = str(match.get("id") or match.get("event_id") or "")
        original = originals.get(match_id) or {}
        previous = {key: original[key] for key in prediction_fields if key in original}
        previous_matrix = previous.get("matrix")
        if _normalised_matrix_dict(previous_matrix) is None:
            previous_matrix = previous.get("score_matrix")
        if (
            previous
            and _normalised_matrix_dict(match.get("matrix")) is None
            and _normalised_matrix_dict(previous_matrix) is not None
        ):
            # Keep a previously produced model payload intact if this refresh
            # cannot produce a replacement matrix from the available inputs.
            for key in prediction_fields:
                if key in previous:
                    if key == "matrix" and _normalised_matrix_dict(previous.get(key)) is None:
                        match.pop(key, None)
                        continue
                    match[key] = previous[key]
                else:
                    match.pop(key, None)
        if match != original:
            updated += 1

    if updated:
        cache_collection.update_one(
            {"_id": competition_document_id(comp, "matches_cache")},
            {"$set": {"data": fixtures}},
            upsert=True,
        )
        _invalidate_ucl_simulation_cache(cache_collection, comp)
    return updated


def _invalidate_ucl_simulation_cache(cache_collection, competition) -> None:
    comp = get_competition(competition)
    if comp.id != "ucl2026":
        return
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "ucl_simulation")},
        {"$set": {"timestamp": 0}},
        upsert=False,
    )


def _discovery_due(cache_collection, competition, current: datetime) -> bool:
    comp = get_competition(competition)
    if comp.id != "ucl2026":
        return False
    document = find_competition_document(cache_collection, comp, "odds_discovery_state") or {}
    try:
        observed_at = parse_time(document.get("observed_at"))
    except (TypeError, ValueError):
        return True
    return current - observed_at >= DISCOVERY_INTERVAL


def _record_discovery(cache_collection, competition, current: datetime, status: str, *, events: int = 0, error: str | None = None) -> None:
    comp = get_competition(competition)
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "odds_discovery_state")},
        {"$set": {
            "competition": comp.id,
            "source": "odds_api",
            "status": status,
            "observed_at": current.isoformat(),
            "events": events,
            "error": error,
        }},
        upsert=True,
    )


def _refresh_fixtures(cache_collection, competition, fetcher, current) -> dict:
    """Refresh the fixture skeleton without collecting paid enrichment."""
    comp = get_competition(competition)
    fetch_now = current
    days_back = 30
    days_forward = 75
    if comp.id == "ucl2026":
        start_year = int(comp.season.split("/", 1)[0])
        season_start = current.replace(year=start_year, month=7, day=1)
        season_end = current.replace(year=start_year + 1, month=6, day=30)
        fetch_now = min(max(current, season_start), season_end)
        days_back = (fetch_now.date() - season_start.date()).days
        days_forward = (season_end.date() - fetch_now.date()).days
    kwargs = {
        "competition": comp,
        "now": fetch_now,
        "days_back": days_back,
        "days_forward": days_forward,
        "chunk_days": 7,
    }
    try:
        fixtures = fetcher(**kwargs) or []
    except Exception as exc:
        return {"status": "failed", "source": "espn", "observed_at": current.isoformat(), "error": str(exc)}
    existing_document = find_competition_document(cache_collection, comp, "matches_cache") or {}
    previous_data = existing_document.get("data") or []
    existing = {
        str(item.get("id") or item.get("event_id")): dict(item)
        for item in previous_data
        if isinstance(item, dict) and (item.get("id") or item.get("event_id"))
    }
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            continue
        event_id = str(fixture.get("id") or fixture.get("event_id") or "")
        if not event_id:
            continue
        match = dict(existing.get(event_id) or {})
        match.update({key: fixture.get(key) for key in (
            "id", "home_team", "away_team", "home_logo", "away_logo",
            "commence_time", "round", "completed", "actual_score",
        ) if key in fixture})
        raw_match = dict(match.get("raw_match") or {})
        raw_match.update({
            "id": event_id,
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "commence_time": match.get("commence_time"),
            "round": match.get("round", ""),
        })
        if match.get("bookmakers"):
            raw_match["bookmakers"] = match["bookmakers"]
        match["raw_match"] = raw_match
        match.setdefault("status", "unavailable")
        match.setdefault("source", "cache")
        existing[event_id] = match
    data = sorted(existing.values(), key=lambda item: item.get("commence_time", ""))
    changed = data != previous_data
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "matches_cache")},
        {"$set": {
            "competition": comp.id,
            "timestamp": current.timestamp(),
            "observed_at": current.isoformat(),
            "source": "espn",
            "status": "fresh",
            "data": data,
        }},
        upsert=True,
    )
    if changed:
        _invalidate_ucl_simulation_cache(cache_collection, comp)
    return {
        "status": "fresh",
        "source": "espn",
        "observed_at": current.isoformat(),
        "fixtures": len(data),
        "changed": changed,
    }


def _bulk_quotes(provider, competition):
    if hasattr(provider, "get_competition_odds"):
        return provider.get_competition_odds(competition, market="h2h,totals") or []
    return provider.get_world_cup_odds(market="h2h,totals") or []


def _quote_lookup(quotes) -> dict:
    lookup = {}
    for quote in quotes or []:
        event_id = str(quote.get("id") or quote.get("event_id") or "")
        if event_id:
            lookup[event_id] = quote
    return lookup


def _match_by_names(lookup, fixture):
    home, away = fixture.get("home_team"), fixture.get("away_team")
    fixture_kickoff = fixture.get("commence_time") or (fixture.get("raw_match") or {}).get("commence_time")
    for quote in lookup.values():
        same_teams = (
            _normalise_team(quote.get("home_team")) == _normalise_team(home)
            and _normalise_team(quote.get("away_team")) == _normalise_team(away)
        )
        quote_kickoff = quote.get("commence_time")
        try:
            same_kickoff = not fixture_kickoff or not quote_kickoff or abs(
                (parse_time(fixture_kickoff) - parse_time(quote_kickoff)).total_seconds()
            ) <= 300
        except (TypeError, ValueError):
            same_kickoff = False
        if same_teams and same_kickoff:
            return quote
    return None


def _extract_odds(quote):
    direct = quote.get("odds")
    if isinstance(direct, dict):
        source = direct.get("odds") if isinstance(direct.get("odds"), dict) else direct
        try:
            values = {key: float(source[key]) for key in ("home", "draw", "away")}
            for key in ("over25", "under25"):
                if key in source:
                    values[key] = float(source[key])
            if any(not math.isfinite(value) or value <= 1.0 for value in values.values()):
                return {}
            return values
        except (KeyError, TypeError, ValueError):
            pass
    bookmakers = quote.get("bookmakers") or []
    if not bookmakers:
        return {}
    try:
        odds = extract_odds({
            "home_team": quote.get("home_team"),
            "away_team": quote.get("away_team"),
            "bookmakers": bookmakers,
        })
    except (TypeError, ValueError, KeyError):
        return {}
    return {key: float(value) for key, value in odds.items() if key in {"home", "draw", "away", "over25", "under25"}}


def _normalise_team(value):
    name = str(value or "")
    return " ".join(TEAM_MAPPING.get(name, name).casefold().split())


def _store_fixture_odds(cache_collection, competition, event_id, odds, quote, observed_at):
    comp = get_competition(competition)
    document = find_competition_document(cache_collection, comp, "matches_cache") or {}
    data = list(document.get("data") or [])
    for match in data:
        if str(match.get("id") or match.get("event_id")) != str(event_id):
            continue
        match["odds"] = odds
        match["odds_status"] = "fresh"
        match["odds_observed_at"] = observed_at.isoformat()
        match["odds_provenance"] = {
            "source": "odds_api",
            "observed_at": observed_at.isoformat(),
            "provider_event_id": str(quote.get("id") or quote.get("event_id") or ""),
        }
        if quote.get("bookmakers"):
            match["bookmakers"] = quote["bookmakers"]
            match.setdefault("raw_match", {})["bookmakers"] = quote["bookmakers"]
        match.setdefault("raw_match", {})["odds_status"] = "fresh"
        match["raw_match"]["odds_observed_at"] = match["odds_observed_at"]
        match["raw_match"]["odds_provenance"] = match["odds_provenance"]
        match["status"] = "fresh"
        match["source_status"] = "fresh"
        match["source"] = "odds_api"
        break
    cache_collection.update_one(
        {"_id": competition_document_id(comp, "matches_cache")},
        {"$set": {"data": data}},
        upsert=True,
    )


def _sync_completed_results(archive_collection, fixtures, competition) -> int:
    """Persist completed fixtures while preserving only real pre-match tips."""
    changed = 0
    for fixture in fixtures:
        event_id = str(fixture.get("id") or fixture.get("event_id") or "")
        actual_score = fixture.get("actual_score")
        if not event_id or not fixture.get("completed") or not _valid_score(actual_score):
            continue
        existing = archive_collection.find_one({"_id": event_id}) or {}
        metadata = dict(existing.get("metadata") or {})
        metadata.update({
            "competition": get_competition(competition).id,
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
            "home_disp": DISPLAY_MAPPING.get(fixture.get("home_team"), fixture.get("home_team")),
            "away_disp": DISPLAY_MAPPING.get(fixture.get("away_team"), fixture.get("away_team")),
            "is_ko_phase": _is_ko_round(fixture.get("round", "")),
            "round": fixture.get("round", ""),
            "commence_time": fixture.get("commence_time"),
        })
        prediction = dict(existing.get("prediction") or {"top_tip": None, "max_xp": None})
        post = dict(existing.get("post_match_result") or {})
        if post.get("status") == "completed" and post.get("actual_score") == actual_score:
            continue
        algo_tip = prediction.get("top_tip") or prediction.get("model_tip")
        user_tip = prediction.get("user_tip")
        bots = prediction.get("bots") or {}
        post.update({
            "status": "completed",
            "actual_score": actual_score,
            "points_earned": MathEngine.calculate_actual_points(user_tip, actual_score, metadata["is_ko_phase"]) if user_tip else None,
            "algo_points": MathEngine.calculate_actual_points(algo_tip, actual_score, metadata["is_ko_phase"]) if algo_tip else None,
            "bot_points": {
                name: MathEngine.calculate_actual_points(info["tip"], actual_score, metadata["is_ko_phase"])
                for name, info in bots.items() if info.get("tip")
            },
        })
        archive_collection.update_one(
            {"_id": event_id},
            {"$set": {
                "competition": get_competition(competition).id,
                "metadata": metadata,
                "pre_match_snapshot": existing.get("pre_match_snapshot"),
                "prediction": prediction,
                "post_match_result": post,
            }},
            upsert=True,
        )
        changed += 1
    if changed:
        invalidate_archive_mem_cache(archive_collection)
    return changed


def _valid_score(value) -> bool:
    try:
        home, away = str(value).split(":", 1)
        return int(home) >= 0 and int(away) >= 0
    except (TypeError, ValueError):
        return False


def _bucket_order():
    return ("t24h", "t6h", "t75m", "t30m", "t15m")
