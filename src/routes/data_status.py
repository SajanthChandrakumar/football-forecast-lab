"""Read-only, cached provider and dataset status for the public data page."""

from datetime import datetime, timezone

from fastapi import APIRouter

from src.competitions import collection_for, document_ids, require_competition
from src import quota_store
from src.services.source_freshness import MAX_SOURCE_AGE


_KNOWN_PROVIDERS = {"espn", "fotmob", "odds_api", "api_football", "clubelo"}
_CONFIGURED_PROVIDERS = _KNOWN_PROVIDERS - {"fotmob"}
_KNOWN_COMBINED_PROVIDERS = {"espn+fotmob": ("espn", "fotmob")}
_MATCH_PROJECTION = {
    "status": 1, "source": 1, "observed_at": 1, "last_attempt_at": 1,
    "last_successful_at": 1, "error": 1,
    "teams": 1, "metadata.teams": 1, "metadata.official_order": 1,
    "metadata.disciplinary_scores": 1, "metadata.uefa_coefficients": 1,
    "metadata.uefa_coefficient_ranks": 1, "metadata.coefficient_version": 1,
    "metadata.team_metadata": 1, "metadata.teams_metadata": 1, "metadata.team_logos": 1,
    "official_order": 1, "disciplinary_scores": 1, "uefa_coefficients": 1,
    "uefa_coefficient_ranks": 1, "coefficient_version": 1,
    "team_metadata": 1, "teams_metadata": 1, "team_logos": 1,
    "data.id": 1, "data.match_id": 1, "data.event_id": 1, "data.completed": 1,
    "data.home_team": 1, "data.away_team": 1, "data.actual_score": 1,
    "data.score_90": 1, "data.score": 1, "data.status": 1,
    "data.round": 1, "data.stage": 1, "data.phase": 1, "data.knockout_stage": 1,
    "data.home_disciplinary_score": 1, "data.away_disciplinary_score": 1,
    "data.home_discipline": 1, "data.away_discipline": 1, "data.home_cards": 1,
    "data.away_cards": 1, "data.disciplinary_score": 1, "data.discipline": 1,
    "data.home_logo": 1, "data.away_logo": 1,
    "data.raw_match.round": 1, "data.raw_match.home_logo": 1, "data.raw_match.away_logo": 1,
    "data.post_match_result.status": 1, "data.post_match_result.actual_score": 1,
    "data.post_match_result.score_90": 1, "data.post_match_result.score": 1,
    "data.odds_status": 1,
    "data.odds_observed_at": 1, "data.odds_provenance.source": 1,
}
_STANDINGS_PROJECTION = {
    "status": 1, "source": 1, "observed_at": 1, "last_attempt_at": 1,
    "last_successful_at": 1, "last_attempt_status": 1, "error": 1,
    "coverage": 1, "data.rows.team": 1, "data.rows.pos": 1,
}


def init_router(
    cache_collections,
    *,
    odds_provider=None,
    team_form_providers=None,
    lineup_providers=None,
    ucl_standings_validator=None,
    ucl_standings_deriver=None,
    now_fn=None,
):
    router = APIRouter(prefix="/api")
    configured_form = team_form_providers or {}
    configured_lineups = lineup_providers or {}

    @router.get("/data-status")
    def get_data_status(competition: str | None = None):
        comp = require_competition(competition)
        cache = collection_for(cache_collections, comp)
        current = _as_datetime(now_fn() if now_fn else datetime.now(timezone.utc))
        matches, matches_error = _find_doc(cache, comp, "matches_cache", _MATCH_PROJECTION)
        matches_data = matches.get("data") if isinstance(matches, dict) else None
        fixtures = [row for row in matches_data if isinstance(row, dict)] if isinstance(matches_data, list) else []
        match_source = _provider(matches.get("source")) if isinstance(matches, dict) else None
        match_times = _document_times(matches, current)
        fixture_data = isinstance(matches, dict) and bool(fixtures)
        datasets = []

        datasets.append(_dataset(
            "fixtures_results", "Spiele & Ergebnisse", ["espn"], [match_source] if match_source else [],
            "provider", matches, fixture_data, current, matches_error,
            coverage={"available": len(fixtures), "required": None, "unit": "matches"} if fixtures else None,
            observed_at=match_times[0], last_attempt_at=match_times[1], last_successful_at=match_times[2],
            missing_status="unavailable",
        ))

        standings, standings_error = _find_doc(cache, comp, "standings_cache", _STANDINGS_PROJECTION)
        if comp.id == "ucl2026":
            table_data = standings.get("data") if isinstance(standings, dict) else None
            valid_cached = bool(ucl_standings_validator and ucl_standings_validator(table_data))
            if valid_cached:
                standings_doc = standings
                standings_kind = "provider"
                standings_count = _standings_count(standings)
                standings_available = _coverage_count(standings, "available", standings_count)
                standings_required = _coverage_count(standings, "required", 36)
                times = _document_times(standings, current)
                standings_observed, standings_attempt, standings_success = times
                standings_has_data = True
                standings_read_failed = False
                standings_observed_providers = [_provider(standings.get("source"))] if _provider(standings.get("source")) else []
            else:
                try:
                    derived_rows = ucl_standings_deriver(matches or {}) if ucl_standings_deriver else []
                except Exception:
                    derived_rows = []
                derived_rows = derived_rows if isinstance(derived_rows, list) else []
                standings_doc = matches if derived_rows else None
                standings_kind = "derived"
                standings_available = len(derived_rows) if derived_rows else None
                standings_required = 36 if derived_rows else None
                standings_observed, standings_attempt, standings_success = match_times if derived_rows else (None, None, None)
                standings_has_data = bool(derived_rows)
                standings_read_failed = matches_error or (standings_error and not matches)
                standings_observed_providers = [match_source] if match_source else []
            standings_error_for_row = standings_read_failed
        else:
            standings_doc = standings
            standings_source = _provider(standings.get("source")) if isinstance(standings, dict) else None
            standings_kind = "provider"
            row_count = _standings_count(standings)
            standings_available = _coverage_count(standings, "available", row_count)
            standings_required = _coverage_count(standings, "required", None)
            times = _document_times(standings, current)
            standings_observed, standings_attempt, standings_success = times
            standings_has_data = bool(row_count)
            standings_error_for_row = standings_error
            standings_observed_providers = [standings_source] if standings_source else []
        standings_coverage = {
            "available": standings_available, "required": standings_required, "unit": "rows",
        } if standings_available is not None else None
        datasets.append(_dataset(
            "standings", "Tabelle", ["espn"] if comp.id in {"wc2026", "epl2026"} else [],
            standings_observed_providers, standings_kind, standings_doc, standings_has_data, current,
            standings_error_for_row, coverage=standings_coverage, observed_at=standings_observed,
            last_attempt_at=standings_attempt, last_successful_at=standings_success,
            missing_status="unavailable",
        ))

        form_sync, form_sync_error = _find_doc(cache, comp, "team_form_sync", {
            "status": 1, "source": 1, "provider": 1, "last_attempt_at": 1,
            "last_successful_at": 1, "observed_at": 1, "teams_total": 1,
            "teams_failed": 1, "teams_unavailable": 1, "error": 1,
        })
        form_teams, form_teams_error = _find_doc(cache, comp, "team_form_teams", {
            "status": 1, "source": 1, "provider": 1, "observed_at": 1,
            "last_attempt_at": 1, "last_successful_at": 1, "coverage": 1,
            "teams.team_id": 1,
        })
        form_source = _provider((form_sync or {}).get("source") or (form_teams or {}).get("source"))
        form_times = _document_times(form_sync or form_teams, current)
        form_total = _nonnegative_int((form_sync or {}).get("teams_total"))
        form_failed = _nonnegative_int((form_sync or {}).get("teams_failed")) or 0
        form_unavailable = _nonnegative_int((form_sync or {}).get("teams_unavailable")) or 0
        form_available = max(0, form_total - form_failed - form_unavailable) if form_total is not None else None
        form_coverage = {"available": form_available, "required": form_total, "unit": "teams"} if form_available is not None else None
        datasets.append(_dataset(
            "team_form", "Teamform", _configured(configured_form, comp.id),
            [form_source] if form_source else [], "provider", form_sync or form_teams,
            form_sync is not None or form_teams is not None, current,
            form_sync_error or form_teams_error, coverage=form_coverage,
            observed_at=form_times[0], last_attempt_at=form_times[1], last_successful_at=form_times[2],
            missing_status="unavailable",
        ))

        rating_key = "clubelo_ratings" if comp.is_club_competition else "elo_ratings"
        ratings, ratings_error = _find_doc(cache, comp, rating_key, {
            "status": 1, "source": 1, "observed_at": 1, "last_attempt_at": 1,
            "last_successful_at": 1, "error": 1, "coverage": 1,
            "rows.team": 1, "rows.team_name": 1,
        })
        if not ratings and comp.is_club_competition:
            ratings, fallback_error = _find_doc(cache, comp, "elo_ratings", {
                "status": 1, "source": 1, "observed_at": 1, "last_attempt_at": 1,
                "last_successful_at": 1, "error": 1, "coverage": 1,
                "rows.team": 1, "rows.team_name": 1,
            })
            ratings_error = ratings_error or fallback_error
        rating_source = _provider((ratings or {}).get("source"))
        rating_count = len((ratings or {}).get("rows") or []) if isinstance(ratings, dict) else 0
        rating_available = _coverage_count(ratings, "available", rating_count)
        rating_required = _coverage_count(ratings, "required", None)
        rating_coverage = {"available": rating_available, "required": rating_required, "unit": "rows"} if rating_available is not None else None
        rating_times = _document_times(ratings, current)
        datasets.append(_dataset(
            "ratings", "Elo-Werte", ["clubelo"] if comp.is_club_competition else [],
            [rating_source] if rating_source else [],
            "provider" if comp.is_club_competition or rating_source else "local",
            ratings, bool(rating_count), current, ratings_error, coverage=rating_coverage,
            observed_at=rating_times[0], last_attempt_at=rating_times[1], last_successful_at=rating_times[2],
            missing_status="unknown" if comp.id == "wc2026" else "unavailable",
        ))

        odds_times, odds_sources, odds_attempt_failed = _odds_metadata(fixtures)
        odds_state, odds_state_error = _find_doc(cache, comp, "odds_bucket_state", {"events": 1})
        bucket_times, bucket_sources, bucket_failed, bucket_success_times, bucket_events = _bucket_metadata(odds_state)
        odds_observed = _latest([*odds_times, *bucket_success_times], current)
        odds_attempt = _latest([*odds_times, *bucket_times], current)
        odds_success = odds_observed
        odds_sources = sorted(set(odds_sources + bucket_sources))
        odds_event_ids = {
            str(row.get("id") or row.get("event_id"))
            for row in fixtures if _row_has_odds(row) and (row.get("id") or row.get("event_id"))
        }
        odds_available = len(odds_event_ids | bucket_events)
        odds_read_failed = matches_error or odds_state_error
        datasets.append(_dataset(
            "odds", "Buchmacherquoten", [odds_provider] if _provider(odds_provider) else [],
            odds_sources, "provider", None if odds_read_failed else {"status": "failed" if odds_attempt_failed or bucket_failed else "fresh"},
            odds_available > 0, current, odds_read_failed, coverage={"available": odds_available, "required": None, "unit": "matches"}
            if odds_available else None, observed_at=odds_observed, last_attempt_at=odds_attempt,
            last_successful_at=odds_success, missing_status="unavailable",
        ))

        lineup_ids = [str(row.get("id") or row.get("event_id")) for row in fixtures if row.get("id") or row.get("event_id")]
        intelligence_docs, intelligence_error = _find_many(cache, comp, lineup_ids)
        lineup_summary = _lineup_metadata(intelligence_docs, current)
        lineup_doc = {"status": lineup_summary["status"]}
        lineup_read_failed = intelligence_error or matches_error
        datasets.append(_dataset(
            "lineups", "Aufstellungen", _configured(configured_lineups, comp.id),
            lineup_summary["providers"], "provider", None if lineup_read_failed else lineup_doc,
            lineup_summary["available"] > 0, current, lineup_read_failed, coverage=lineup_summary["coverage"],
            observed_at=lineup_summary["observed_at"], last_attempt_at=lineup_summary["last_attempt_at"],
            last_successful_at=lineup_summary["last_successful_at"], missing_status="unavailable",
        ))

        maintenance_doc, maintenance_error = _find_doc(cache, comp, "maintenance_status", {
            "status": 1, "last_run_at": 1, "last_successful_at": 1,
            "next_due_at": 1, "interval_seconds": 1, "error": 1,
        })
        lease, lease_error = _find_doc(cache, comp, "maintenance_lease", {
            "lease_until": 1, "lease_token": 1, "competition": 1,
        })
        maintenance = _maintenance_summary(maintenance_doc, lease, current, comp.id)
        if maintenance_error or lease_error:
            maintenance["error"] = "Wartungsdaten sind vorübergehend nicht verfügbar."

        try:
            quota_snapshot = quota_store.read_status_snapshot()
        except Exception:
            quota_snapshot = {"mongo_available": False, "providers": {}}
        quotas = {
            "scope": "global_shared_all_competitions",
            "providers": {
                provider: quota_store.read_status(provider, snapshot=quota_snapshot, now=current.timestamp())
                for provider in ("odds", "football")
            },
        }
        return {
            "competition": comp.id,
            "generated_at": current.isoformat(),
            "datasets": datasets,
            "maintenance": maintenance,
            "quotas": quotas,
        }

    return router


def _find_doc(collection, competition, key, projection=None):
    failed = False
    for doc_id in document_ids(competition, key):
        try:
            document = collection.find_one({"_id": doc_id}, projection) if projection is not None else collection.find_one({"_id": doc_id})
        except TypeError:
            try:
                document = collection.find_one({"_id": doc_id})
            except Exception:
                failed = True
                continue
        except Exception:
            failed = True
            continue
        if document:
            return document, failed
    return None, failed


def _find_many(collection, competition, event_ids):
    if not event_ids or not hasattr(collection, "find"):
        return [], False
    ids = [f"{competition.id}:match_intelligence:{event_id}" for event_id in event_ids]
    projection = {
        "data.status": 1, "data.source": 1, "data.observed_at": 1,
        "data.lineups": 1, "last_attempt.status": 1, "last_attempt.source": 1,
        "last_attempt.observed_at": 1, "updated_at": 1,
    }
    try:
        try:
            return list(collection.find({"_id": {"$in": ids}}, projection)), False
        except TypeError:
            return list(collection.find({"_id": {"$in": ids}})), False
    except Exception:
        return [], True


def _dataset(
    dataset_id, label, configured, observed, source_kind, document, has_data, now, read_failed,
    *, coverage=None, observed_at=None, last_attempt_at=None, last_successful_at=None,
    missing_status="unknown",
):
    if observed_at is None:
        times = _document_times(document, now)
        observed_at = observed_at or times[0]
        last_attempt_at = last_attempt_at or times[1]
        last_successful_at = last_successful_at or times[2]
    if document is None:
        status = "unknown" if read_failed else missing_status
    else:
        status = _freshness(document.get("status"), observed_at, has_data, now)
    error = None
    if read_failed:
        error = "Gespeicherte Daten sind derzeit nicht lesbar."
    elif document and document.get("error"):
        error = "Die letzte Aktualisierung war fehlerhaft; gespeicherte Daten können veraltet sein."
    elif status == "stale":
        error = "Gespeicherte Daten können veraltet sein."
    elif status == "unknown" and has_data and observed_at is None:
        error = "Ein gültiger Erfassungszeitpunkt ist nicht verfügbar."
    return {
        "id": dataset_id,
        "label": label,
        "providers": {
            "configured": _provider_list(configured),
            "observed": _observed_provider_list(observed),
        },
        "source_kind": source_kind,
        "status": status,
        "observed_at": observed_at,
        "last_attempt_at": last_attempt_at,
        "last_successful_at": last_successful_at,
        "error": error,
        "coverage": coverage,
    }


def _freshness(declared, observed_at, has_data, now):
    if not has_data:
        return declared if declared in {"failed", "partial", "unavailable"} else "unavailable"
    timestamp = _parse_time(observed_at)
    if timestamp is None:
        return declared if declared in {"failed", "unavailable"} else "unknown"
    age = now - timestamp
    if age.total_seconds() < 0 or age > MAX_SOURCE_AGE:
        return "stale"
    if declared == "unavailable":
        return "unavailable"
    if declared == "partial":
        return "partial"
    if declared in {"failed", "stale"}:
        return "stale"
    return "fresh"


def _document_times(document, now=None):
    if not isinstance(document, dict):
        return None, None, None
    current = _as_datetime(now)
    raw_observed = _before_or_at(document.get("observed_at"), current)
    explicit_success = _before_or_at(document.get("last_successful_at"), current)
    provenance = document.get("provenance") if isinstance(document.get("provenance"), dict) else {}
    provenance_success = _before_or_at(provenance.get("observed_at"), current)
    status = document.get("status")
    attempt = _before_or_at(document.get("last_attempt_at"), current)
    if status == "failed":
        attempt = attempt or raw_observed
        observed = explicit_success or provenance_success
    elif status == "partial":
        observed = raw_observed or explicit_success or provenance_success
    elif status == "stale" and provenance_success:
        observed = provenance_success
        if raw_observed and raw_observed != provenance_success:
            attempt = attempt or raw_observed
    else:
        observed = raw_observed or explicit_success or provenance_success
    success = explicit_success or provenance_success
    if success is None and status not in {"failed", "partial"}:
        success = observed
    return observed, attempt, success


def _parse_time(value):
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _iso(value):
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else None


def _before_or_at(value, current):
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed and parsed <= current else None


def _as_datetime(value):
    parsed = _parse_time(value)
    return parsed or datetime.now(timezone.utc)


def _provider(value):
    if not isinstance(value, str):
        return None
    return value if value in _KNOWN_PROVIDERS or value in _KNOWN_COMBINED_PROVIDERS else None


def _provider_list(values):
    if isinstance(values, str):
        values = [values]
    return sorted({value for value in values or [] if isinstance(value, str) and value in _CONFIGURED_PROVIDERS})


def _observed_provider_list(values):
    if isinstance(values, str):
        values = [values]
    observed = set()
    for value in values or []:
        if isinstance(value, str) and value in _KNOWN_COMBINED_PROVIDERS:
            observed.update(_KNOWN_COMBINED_PROVIDERS[value])
        elif isinstance(value, str) and value in _KNOWN_PROVIDERS:
            observed.add(value)
    return sorted(observed)


def _configured(mapping, competition):
    return _provider_list(mapping.get(competition, [])) if isinstance(mapping, dict) else []


def _nonnegative_int(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _coverage_count(document, key, fallback):
    if not isinstance(document, dict):
        return fallback
    coverage = document.get("coverage")
    value = coverage.get(key) if isinstance(coverage, dict) else None
    return _nonnegative_int(value) if value is not None else fallback


def _standings_count(document):
    if not isinstance(document, dict):
        return 0
    tables = document.get("data")
    if not isinstance(tables, list):
        return 0
    return sum(len(table.get("rows") or []) for table in tables if isinstance(table, dict))


def _row_has_odds(row):
    return bool(row.get("odds_provenance") or row.get("odds_observed_at") or row.get("odds_status") in {"fresh", "stale"})


def _odds_metadata(fixtures):
    times, providers = [], []
    failed = False
    for row in fixtures:
        timestamp = _iso(row.get("odds_observed_at"))
        if timestamp:
            times.append(timestamp)
        provenance = row.get("odds_provenance")
        provider = _provider((provenance or {}).get("source")) if isinstance(provenance, dict) else None
        if provider and _row_has_odds(row):
            providers.append(provider)
        failed = failed or row.get("odds_status") == "failed"
    return times, providers, failed


def _bucket_metadata(document):
    times, providers, successful_times, successful_events, failed = [], [], [], set(), False
    events = document.get("events") if isinstance(document, dict) else None
    if isinstance(events, dict):
        for event_id, buckets in events.items():
            if not isinstance(buckets, dict):
                continue
            for value in buckets.values():
                if not isinstance(value, dict):
                    continue
                timestamp = _iso(value.get("observed_at"))
                if timestamp:
                    times.append(timestamp)
                provider = _provider(value.get("source"))
                if provider and value.get("status") == "fresh":
                    providers.append(provider)
                    successful_events.add(str(event_id))
                    if timestamp:
                        successful_times.append(timestamp)
                failed = failed or value.get("status") == "failed"
    return times, providers, failed, successful_times, {event for event in successful_events if event}


def _latest(values, now=None):
    current = _as_datetime(now)
    valid = [(parsed, value) for value in values if (parsed := _parse_time(value)) and parsed <= current]
    return max(valid, default=(None, None), key=lambda pair: pair[0])[1]


def _lineup_metadata(documents, now=None):
    current = _as_datetime(now)
    providers, observed, attempts, successes = set(), [], [], []
    available = 0
    failed = 0
    attempted = 0
    partial = False
    for document in documents:
        data = document.get("data") if isinstance(document.get("data"), dict) else {}
        attempt = document.get("last_attempt") if isinstance(document.get("last_attempt"), dict) else {}
        data_source = _provider(data.get("source"))
        attempt_source = _provider(attempt.get("source"))
        if data_source:
            providers.add(data_source)
        if attempt_source:
            providers.add(attempt_source)
        attempt_at = _before_or_at(attempt.get("observed_at"), current) or _before_or_at(document.get("updated_at"), current)
        if attempt_at:
            attempts.append(attempt_at)
            attempted += 1
        lineups = data.get("lineups") if isinstance(data.get("lineups"), dict) else {}
        complete = len(lineups) >= 2 and all(
            isinstance(value, dict) and bool(value.get("starters")) for value in lineups.values()
        )
        observed_at = _before_or_at(data.get("observed_at"), current)
        if complete:
            available += 1
            if observed_at:
                successes.append(observed_at)
        elif attempt.get("status") == "failed":
            failed += 1
        elif data.get("status") == "partial":
            partial = True
    if available and (failed or partial):
        status = "partial"
    elif available:
        status = "fresh"
    elif attempted and failed == attempted:
        status = "failed"
    elif attempted:
        status = "partial"
    else:
        status = "unavailable"
    return {
        "status": status,
        "available": available,
        "coverage": {"available": available, "required": attempted, "unit": "matches"} if attempted else None,
        "providers": sorted(providers),
        "observed_at": _latest(successes, current),
        "last_attempt_at": _latest(attempts, current),
        "last_successful_at": _latest(successes, current),
    }


def _maintenance_summary(document, lease, now, competition):
    document = document if isinstance(document, dict) else {}
    lease_until = _parse_time((lease or {}).get("lease_until")) if isinstance(lease, dict) else None
    return {
        "status": document.get("status") if isinstance(document.get("status"), str) else None,
        "last_run_at": _before_or_at(document.get("last_run_at"), now),
        "last_successful_at": _before_or_at(document.get("last_successful_at"), now),
        "next_due_at": _iso(document.get("next_due_at")),
        "interval_seconds": _nonnegative_int(document.get("interval_seconds")),
        "error": "Bei der Wartung ist ein Fehler aufgetreten." if document.get("error") else None,
        "running": bool(
            lease_until and lease_until > now
            and (lease or {}).get("lease_token")
            and (lease or {}).get("competition") == competition
        ),
    }
