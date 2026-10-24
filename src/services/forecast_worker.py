"""Record pre-kickoff forecasts while the API is running, using cached inputs only."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from src.competitions import competition_document_id, find_competition_document, get_competition
from src.services.model_evaluation import freeze_due_comparisons
from src.services.prediction import PredictionService
from src.services.snapshots import parse_time

logger = logging.getLogger(__name__)


def claim_capture(cache, competition, current):
    """Acquire a short Mongo compare-and-set lease, shared by every process."""
    key = competition_document_id(competition, 'forecast_capture_lease')
    token = uuid4().hex
    initial = {'lease_token': token, 'lease_until': (current + timedelta(seconds=120)).isoformat()}
    cache.update_one({'_id': key}, {'$setOnInsert': initial}, upsert=True)
    saved = cache.find_one({'_id': key}) or {}
    if saved.get('lease_token') == token:
        return token
    try:
        expired = parse_time(saved.get('lease_until')) <= current
    except (ValueError, TypeError):
        expired = True
    if not expired:
        return None
    result = cache.update_one({'_id': key, 'lease_token': saved.get('lease_token'),
        'lease_until': saved.get('lease_until')}, {'$set': initial})
    return token if getattr(result, 'matched_count', 0) else None


def capture_competition(cache, archive, service, competition, *, now=None):
    current = now or datetime.now(timezone.utc)
    token = claim_capture(cache, competition, current)
    if token is None:
        return {'status': 'skipped', 'reason': 'lease_held', 'forecasts_frozen': 0, 'evaluation_captured': 0}
    try:
        return _capture_competition(cache, archive, service, competition, now=current)
    finally:
        cache.update_one({'_id': competition_document_id(competition, 'forecast_capture_lease'),
            'lease_token': token}, {'$set': {'lease_until': current.isoformat()}})


def _capture_competition(cache, archive, service, competition, *, now=None):
    current = now or datetime.now(timezone.utc)
    frozen = freeze_due_comparisons(service, cache, archive, competition, current, require_complete_capture=True)
    windows = []
    fixtures = find_competition_document(cache, competition, 'matches_cache') or {}
    for fixture in fixtures.get('data') or []:
        try:
            kickoff = parse_time(fixture.get('commence_time') or (fixture.get('raw_match') or {}).get('commence_time'))
        except (TypeError, ValueError):
            continue
        if not fixture.get('completed') and not fixture.get('actual_score') and current < kickoff - timedelta(minutes=5):
            windows.append(max(current, kickoff - timedelta(minutes=15)))
    status = {
        'status': 'success', 'last_run_at': current.isoformat(),
        'forecasts_frozen': frozen, 'evaluation_captured': frozen,
        'next_capture_at': min(windows).isoformat() if windows else None,
        'interval_seconds': 60, 'last_successful_at': current.isoformat(), 'error': None,
    }
    cache.update_one({'_id': competition_document_id(competition, 'forecast_capture_status')}, {'$set': status}, upsert=True)
    return status


async def run_forecast_worker(cache_collections, archive_collections, math_engine):
    while True:
        for competition, cache in cache_collections.items():
            if not get_competition(competition).is_club_competition:
                continue
            try:
                await asyncio.to_thread(capture_competition, cache, archive_collections[competition], PredictionService(math_engine), competition)
            except Exception as exc:
                # Do not log provider URLs or connection credentials.
                logger.warning('Forecast capture failed for %s (%s)', competition, type(exc).__name__)
                try:
                    await asyncio.to_thread(cache.update_one,
                        {'_id': competition_document_id(competition, 'forecast_capture_status')},
                        {'$set': {'status': 'failed', 'last_run_at': datetime.now(timezone.utc).isoformat(),
                                  'error': 'Vorab-Erfassung fehlgeschlagen; erneuter Versuch folgt.'}}, upsert=True)
                except Exception:
                    pass  # A storage outage must not stop retries or the other competitions.
        await asyncio.sleep(60)


async def run_result_worker(cache_collections, archive_collections):
    """Refresh free ESPN results independently of time-sensitive forecast capture."""
    from src.competitions import get_competition
    from src.services.maintenance import run_maintenance
    from src.services.espn_data import get_scoreboard
    while True:
        for competition in cache_collections:
            if not get_competition(competition).is_club_competition:
                continue
            try:
                await asyncio.to_thread(
                    run_maintenance, cache_collections, None,
                    archive_collections=archive_collections, competition=competition,
                    results_only=True, fixture_fetcher=get_scoreboard,
                )
            except Exception as exc:
                logger.warning('Result sync failed for %s (%s)', competition, type(exc).__name__)
        await asyncio.sleep(60)


async def run_club_maintenance_worker(cache_collections, archive_collections, odds_provider,
                                      math_engine, team_form_services, intelligence_refresher):
    """Provider calls run on this bounded schedule, never on public page requests."""
    from src.services.maintenance import run_tracked_maintenance
    from src.services import espn_data
    from src.services.ucl_providers import ingest_clubelo
    while True:
        for competition in cache_collections:
            if not get_competition(competition).is_club_competition:
                continue
            try:
                await asyncio.to_thread(
                    run_tracked_maintenance, cache_collections, odds_provider,
                    archive_collections=archive_collections, competition=competition,
                    fixture_fetcher=espn_data.get_scoreboard, clubelo_ingestor=ingest_clubelo,
                    math_engine=math_engine, team_form_service=team_form_services.get(competition),
                    match_intelligence_refresher=intelligence_refresher,
                    standings_fetcher=espn_data.get_standings_groups if competition == "epl2026" else None,
                )
            except Exception as exc:
                logger.warning('Club maintenance failed for %s (%s)', competition, type(exc).__name__)
        await asyncio.sleep(60)
