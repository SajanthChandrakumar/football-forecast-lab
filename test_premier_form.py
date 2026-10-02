from datetime import datetime, timezone

from src.services.team_form import TeamFormService
from src.odds_engine_apifootball import OddsApiEngine
from test_task2_providers import MemoryCollection


def test_premier_form_uses_completed_cached_league_results_only():
    service = TeamFormService(MemoryCollection(), None, competition="epl2026")
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    fixtures = [{
        "id": "pl1", "home_team": "AFC Bournemouth", "away_team": "Arsenal",
        "commence_time": "2026-09-12T14:00:00Z", "completed": True, "actual_score": "2:1",
    }, {
        "id": "pl2", "home_team": "Arsenal", "away_team": "AFC Bournemouth",
        "commence_time": "2026-10-03T14:00:00Z", "completed": False,
    }]
    assert service.ingest_league_fixtures(fixtures, now=now)["provider_calls"] == 0
    home = service.cached_form_for_match("Bournemouth")
    away = service.cached_form_for_match("Arsenal")
    assert home["scope"] == away["scope"] == "league"
    assert home["form"] == ["W"] and away["form"] == ["L"]
    assert home["matches"][0]["score"] == "2:1"
    assert away["matches"][0]["score"] == "1:2"
    assert away["source"] == "espn"
    assert service.ingest_league_fixtures([], now=now)["status"] == "unavailable"
    assert len(service.cached_form_for_match("Arsenal")["matches"]) == 1


def test_alternative_odds_provider_selects_epl_without_mutating_shared_engine(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-only")
    engine = OddsApiEngine()
    calls = []
    engine._request = lambda path, params: calls.append((path, params)) or {"response": []}
    assert engine.get_competition_odds("epl2026") == []
    assert len(calls) == 2
    assert all(params["league"] == 39 and params["season"] == 2026 for _, params in calls)
    assert engine.WC_LEAGUE_ID == 1
    assert engine.get_competition_odds("ucl2026") == []
    assert all(params["league"] == 2 for _, params in calls[2:])
