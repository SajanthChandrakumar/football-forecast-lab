import pytest
from datetime import datetime, timezone
from starlette.requests import Request

from src.services import team_form
from src.services.team_form import (
    ApiFootballClient,
    EspnTeamFormClient,
    FailoverTeamFormClient,
    TeamFormService,
)
from src.services.maintenance import run_maintenance
from src.routes.matches import init_router as matches_router


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {document["_id"]: dict(document) for document in documents}

    def find_one(self, query):
        document = self.documents.get(query.get("_id"))
        return document if document and all(document.get(key) == value for key, value in query.items()) else None

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise ValueError("duplicate key")
        self.documents[document["_id"]] = dict(document)

    def delete_one(self, query):
        if self.find_one(query):
            del self.documents[query["_id"]]

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        if key in self.documents and self.find_one(query) is None:
            return type("UpdateResult", (), {"matched_count": 0})()
        document = dict(self.documents.get(key, {"_id": key}))
        document.update(update.get("$set", {}))
        self.documents[key] = document
        return type("UpdateResult", (), {"matched_count": 1})()


@pytest.fixture(autouse=True)
def no_real_quota_writes(monkeypatch):
    monkeypatch.setattr(team_form, "write_quota", lambda *args, **kwargs: None)


class FakeResponse:
    headers = {
        "x-ratelimit-requests-remaining": "83",
        "x-ratelimit-requests-limit": "100",
    }

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _fixture(
    fixture_id,
    *,
    status="FT",
    date="2026-09-01T18:00:00+00:00",
    league_name="UEFA Champions League",
    league_type="Cup",
    home_goals=2,
    away_goals=1,
):
    home = {"id": 10, "name": "Team"}
    away = {"id": 20, "name": "Opponent"}
    return {
        "fixture": {
            "id": fixture_id,
            "date": date,
            "status": {"short": status},
            "venue": {"name": "Stadium"},
        },
        "league": {"name": league_name, "type": league_type},
        "teams": {"home": home, "away": away},
        "goals": {"home": home_goals, "away": away_goals},
    }


def _away_fixture(fixture):
    fixture = dict(fixture)
    teams = {key: dict(value) for key, value in fixture["teams"].items()}
    teams["home"]["id"], teams["away"]["id"] = 20, 10
    teams["home"]["name"], teams["away"]["name"] = "Opponent", "Team"
    fixture["teams"] = teams
    return fixture


def test_api_football_client_returns_json_and_records_quota(monkeypatch):
    requests = []
    quota_writes = []

    def request_fn(url, *, headers, params, timeout):
        requests.append((url, headers, params, timeout))
        return FakeResponse({"response": [{"team": {"id": 10, "name": "Team"}}]})

    monkeypatch.setattr(team_form, "write_quota", lambda provider, data: quota_writes.append((provider, data)))
    client = ApiFootballClient("test-key", request_fn=request_fn)

    response = client.request("/teams", {"league": 2, "season": 2026})

    assert response == {"response": [{"team": {"id": 10, "name": "Team"}}]}
    assert requests == [
        (
            "https://v3.football.api-sports.io/teams",
            {"x-apisports-key": "test-key"},
            {"league": 2, "season": 2026},
            10,
        )
    ]
    assert quota_writes == [("football", {"remaining": "83", "used": 17, "limit": "100"})]


def test_api_football_client_records_quota_before_raising_http_error(monkeypatch):
    quota_writes = []

    class ErrorResponse(FakeResponse):
        def raise_for_status(self):
            raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(team_form, "write_quota", lambda provider, data: quota_writes.append((provider, data)))
    client = ApiFootballClient(
        "test-key",
        request_fn=lambda *args, **kwargs: ErrorResponse({"response": []}),
    )

    with pytest.raises(RuntimeError, match="429"):
        client.request("/fixtures", {"date": "2026-09-24"})

    assert quota_writes == [("football", {"remaining": "83", "used": 17, "limit": "100"})]


def _espn_event(
    fixture_id="401",
    *,
    team_id="359",
    team_name="Arsenal",
    opponent_id="331",
    opponent_name="Brighton & Hove Albion",
    completed=True,
    detail="FT",
    competition="2026-27 English Premier League",
    goals_for="3",
    goals_against="1",
):
    return {
        "id": fixture_id,
        "date": "2026-09-19T14:00Z",
        "season": {"year": 2026, "displayName": competition},
        "competitions": [{
            "altGameNote": competition,
            "status": {"type": {"completed": completed, "detail": detail}},
            "competitors": [
                {
                    "id": team_id,
                    "homeAway": "home",
                    "score": goals_for,
                    "team": {"id": team_id, "displayName": team_name, "logo": "arsenal.png"},
                },
                {
                    "id": opponent_id,
                    "homeAway": "away",
                    "score": goals_against,
                    "team": {"id": opponent_id, "displayName": opponent_name, "logo": "brighton.png"},
                },
            ],
        }],
    }


def test_espn_fallback_discovers_current_ucl_teams_and_normalizes_all_competitions():
    calls = []
    ucl_event = _espn_event(opponent_id="83", opponent_name="Barcelona")
    premier_league = _espn_event()
    friendly = _espn_event(
        fixture_id="402", competition="Club Friendly", goals_for="1", goals_against="1"
    )
    future = _espn_event(fixture_id="403", completed=False, detail="Scheduled")

    def request_fn(url, *, params, timeout):
        calls.append((url, params, timeout))
        if url.endswith("/uefa.champions/scoreboard"):
            return FakeResponse({"events": [ucl_event]})
        return FakeResponse({"events": [premier_league, friendly, future]})

    client = EspnTeamFormClient(request_fn=request_fn, season=2026, enable_fotmob_fallback=False)
    service = TeamFormService(MemoryCollection(), client)

    teams = service.parse_teams(client.request("/teams", {"league": 2, "season": 2026}))
    matches = service.parse_fixtures("359", client.request("/fixtures", {"team": "359", "last": 5}))

    assert {team["name"] for team in teams} == {"Arsenal", "Barcelona"}
    assert matches == [{
        "fixture_id": "401",
        "played_at": "2026-09-19T14:00Z",
        "competition_name": "English Premier League",
        "opponent_id": "331",
        "opponent_name": "Brighton & Hove Albion",
        "venue": "home",
        "goals_for": 3,
        "goals_against": 1,
        "score": "3:1",
        "result": "W",
    }]
    assert calls[0][1] == {"dates": "2026"}
    assert calls[1][1] == {"season": 2026}


def test_espn_fallback_normalizes_daily_scoreboard_with_single_page():
    client = EspnTeamFormClient(
        request_fn=lambda *args, **kwargs: FakeResponse({"events": [_espn_event()]}),
        season=2026,
    )

    payload = client.request("/fixtures", {"date": "2026-09-19", "timezone": "Europe/Zurich", "page": 1})

    assert payload["paging"] == {"current": 1, "total": 1}
    assert payload["response"][0]["fixture"]["status"]["short"] == "FT"
    assert payload["response"][0]["league"]["name"] == "English Premier League"


def test_failover_client_uses_espn_only_after_api_football_plan_error():
    primary_calls = []
    fallback_calls = []

    class Primary:
        provider = "api_football"

        def request(self, path, params):
            primary_calls.append((path, params))
            raise RuntimeError("API-Football error: {'plan': 'not available'}")

    class Fallback:
        provider = "espn"

        def request(self, path, params):
            fallback_calls.append((path, params))
            return {"response": []}

    client = FailoverTeamFormClient(Primary(), Fallback())

    assert client.request("/teams", {"season": 2026}) == {"response": []}
    assert client.request("/fixtures", {"team": "359", "last": 5}) == {"response": []}
    assert client.provider == "espn"
    assert len(primary_calls) == 1
    assert len(fallback_calls) == 2


def test_espn_bootstrap_persists_provider_and_does_not_apply_api_pacing():
    cache = MemoryCollection()

    class EspnClient:
        provider = "espn"

        def request(self, path, params):
            if path == "/teams":
                return {"response": [{"team": {"id": "359", "name": "Arsenal"}}]}
            return {"response": [_fixture("401")]}

    sleeps = []
    result = TeamFormService(cache, EspnClient()).bootstrap(
        season=2026, sleep_fn=sleeps.append, min_interval_seconds=7
    )

    assert result == {"teams_total": 1, "teams_skipped": 0, "teams_completed": 1}
    assert sleeps == []
    assert cache.find_one({"_id": "ucl2026:team_form_teams"})["provider"] == "espn"
    assert cache.find_one({"_id": "ucl2026:team_form:359"})["provider"] == "espn"


def test_espn_client_supplements_partial_club_schedule_from_fotmob_without_hardcoded_ids():
    calls = []
    espn_ucl = _espn_event(
        fixture_id="ucl-1", team_id="494", team_name="Slavia Prague",
        opponent_id="16", opponent_name="Lens", competition="2026-27 UEFA Champions League",
    )
    fotmob_fixtures = []
    for index in range(5):
        fotmob_fixtures.append({
            "id": 5000 + index,
            "home": {"id": 7787, "name": "Slavia Prague", "score": 2},
            "away": {"id": 2000 + index, "name": f"Opponent {index}", "score": 1},
            "tournament": {"name": "1. Liga"},
            "status": {
                "utcTime": f"2026-09-{20 - index:02d}T14:00:00.000Z",
                "finished": True,
                "cancelled": False,
                "reason": {"short": "FT"},
            },
        })

    def request_fn(url, *, params, timeout, **kwargs):
        calls.append((url, params))
        if url.endswith("/uefa.champions/scoreboard"):
            return FakeResponse({"events": [espn_ucl]})
        if "/all/teams/494/schedule" in url:
            return FakeResponse({"team": {"displayName": "Slavia Prague"}, "events": [espn_ucl]})
        if url.endswith("/api/data/search/suggest"):
            return FakeResponse([{
                "suggestions": [{"type": "team", "id": "7787", "name": "Slavia Prague"}]
            }])
        if url.endswith("/api/data/teams"):
            return FakeResponse({"fixtures": {"allFixtures": {"fixtures": fotmob_fixtures}}})
        raise AssertionError(url)

    client = EspnTeamFormClient(request_fn=request_fn, season=2026)
    service = TeamFormService(MemoryCollection(), client)
    service.parse_teams(client.request("/teams", {"season": 2026}))
    matches = service.parse_fixtures("494", client.request("/fixtures", {"team": "494", "last": 5}))

    assert len(matches) == 5
    assert matches[0]["competition_name"] == "1. Liga"
    assert matches[0]["opponent_name"] == "Opponent 0"
    assert client.provider == "espn+fotmob"
    assert any(url.endswith("/api/data/search/suggest") for url, _ in calls)
    assert any(url.endswith("/api/data/teams") for url, _ in calls)


def test_team_ids_are_stable_and_teams_use_competition_scoped_storage():
    cache = MemoryCollection()
    service = TeamFormService(cache, client=object(), now_fn=lambda: datetime(2026, 9, 25, tzinfo=timezone.utc))
    response = {
        "response": [
            {"team": {"id": 10, "name": "Shared Name", "country": "Germany", "logo": "logo-10"}},
            {"team": {"id": 20, "name": "Shared Name", "country": "England", "logo": "logo-20"}},
        ]
    }

    teams = service.parse_teams(response)
    service.store_teams(teams)

    assert [team["team_id"] for team in teams] == ["10", "20"]
    assert teams[0]["name"] == teams[1]["name"]
    assert cache.find_one({"_id": "ucl2026:team_form_teams"}) == {
        "_id": "ucl2026:team_form_teams",
        "competition": "ucl2026",
        "teams": teams,
        "status": "fresh",
        "source": "api_football",
        "provider": "api_football",
        "observed_at": "2026-09-25T00:00:00+00:00",
        "last_attempt_at": "2026-09-25T00:00:00+00:00",
        "last_successful_at": "2026-09-25T00:00:00+00:00",
        "coverage": {"teams": 2},
        "error": None,
    }


def test_fixture_normalization_uses_team_home_and_away_perspective():
    service = TeamFormService(MemoryCollection(), client=object())
    home_fixture = _fixture(100, home_goals=3, away_goals=1)
    away_fixture = _away_fixture(_fixture(101, home_goals=1, away_goals=2))

    home = service.parse_fixtures("10", {"response": [home_fixture]})[0]
    away = service.parse_fixtures("10", {"response": [away_fixture]})[0]

    assert home == {
        "fixture_id": "100",
        "played_at": "2026-09-01T18:00:00+00:00",
        "competition_name": "UEFA Champions League",
        "opponent_id": "20",
        "opponent_name": "Opponent",
        "venue": "home",
        "goals_for": 3,
        "goals_against": 1,
        "score": "3:1",
        "result": "W",
    }
    assert away["opponent_id"] == "20"
    assert away["opponent_name"] == "Opponent"
    assert away["venue"] == "away"
    assert away["goals_for"] == 2
    assert away["goals_against"] == 1
    assert away["score"] == "2:1"
    assert away["result"] == "W"


def test_only_full_time_and_extra_time_final_statuses_are_included():
    service = TeamFormService(MemoryCollection(), client=object())
    fixtures = [
        _fixture(1, status="FT"),
        _fixture(2, status="AET"),
        _fixture(3, status="PEN"),
        _fixture(4, status="HT"),
        _fixture(5, status="NS"),
    ]

    matches = service.parse_fixtures("10", {"response": fixtures})

    assert [match["fixture_id"] for match in matches] == ["1", "2", "3"]


def test_penalty_shootout_decides_result_when_goal_totals_are_level():
    service = TeamFormService(MemoryCollection(), client=object())
    fixture = _fixture(3, status="PEN", home_goals=1, away_goals=1)
    fixture["score"] = {"penalty": {"home": 5, "away": 4}}

    match = service.parse_fixtures("10", {"response": [fixture]})[0]

    assert match["score"] == "1:1"
    assert match["result"] == "W"


def test_friendlies_are_excluded_even_when_their_status_is_finished():
    service = TeamFormService(MemoryCollection(), client=object())
    fixtures = [
        _fixture(1, league_name="Club Friendlies", league_type="Cup"),
        _fixture(2, league_name="Summer Series", league_type="Friendly"),
        _fixture(3, league_name="UEFA Champions League", league_type="Cup"),
    ]

    matches = service.parse_fixtures("10", {"response": fixtures})

    assert [match["fixture_id"] for match in matches] == ["3"]


def test_parsed_matches_sort_newest_first_and_are_limited_to_five():
    service = TeamFormService(MemoryCollection(), client=object())
    fixtures = [
        _fixture(
            day,
            date=f"2026-09-{day:02d}T18:00:00+00:00",
        )
        for day in (1, 7, 2, 6, 3, 5, 4)
    ]

    matches = service.parse_fixtures("10", {"response": fixtures})

    assert [match["fixture_id"] for match in matches] == ["7", "6", "5", "4", "3"]


def test_merge_replaces_duplicate_fixture_ids_sorts_and_caps_cached_form():
    old_match = {
        "fixture_id": "1",
        "played_at": "2026-09-01T18:00:00+00:00",
        "competition_name": "Old Competition",
        "opponent_id": "20",
        "opponent_name": "Opponent",
        "venue": "home",
        "goals_for": 1,
        "goals_against": 0,
        "score": "1:0",
        "result": "W",
    }
    cache = MemoryCollection(
        [
            {
                "_id": "ucl2026:team_form:10",
                "competition": "ucl2026",
                "team_id": "10",
                "matches": [old_match],
            }
        ]
    )
    service = TeamFormService(cache, client=object())
    updated_match = {**old_match, "played_at": "2026-09-02T17:00:00+00:00", "score": "2:1", "goals_for": 2}
    incoming = [
        updated_match,
        *[
            {**old_match, "fixture_id": str(fixture_id), "played_at": f"2026-09-{fixture_id:02d}T18:00:00+00:00"}
            for fixture_id in range(2, 6)
        ],
    ]

    matches = service.merge_matches("10", incoming)

    assert [match["fixture_id"] for match in matches] == ["5", "4", "3", "2", "1"]
    assert next(match for match in matches if match["fixture_id"] == "1")["score"] == "2:1"
    stored = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert stored["competition"] == "ucl2026"
    assert stored["matches"] == matches


def test_sync_state_uses_competition_scoped_document_id():
    cache = MemoryCollection()
    service = TeamFormService(cache, client=object())

    service.store_sync_state({"last_successful_date": "2026-09-24"})

    assert service.get_sync_state() == {
        "_id": "ucl2026:team_form_sync",
        "competition": "ucl2026",
        "last_successful_date": "2026-09-24",
    }


def test_api_football_client_rejects_nonempty_api_error_payload():
    client = ApiFootballClient(
        "test-key",
        request_fn=lambda *args, **kwargs: FakeResponse({"errors": {"token": "Invalid key"}, "response": []}),
    )

    with pytest.raises(RuntimeError, match="Invalid key"):
        client.request("/teams", {"league": 2, "season": 2026})


def test_api_football_client_stops_before_exceeding_persisted_daily_budget(monkeypatch):
    cache = MemoryCollection()
    calls = []
    current_time = [0.0]

    def sleep_fn(seconds):
        current_time[0] += seconds

    client = ApiFootballClient(
        "test-key",
        request_fn=lambda *args, **kwargs: (calls.append(args[0]) or FakeResponse({"response": []})),
        cache_collection=cache,
        competition="ucl2026",
        now_fn=lambda: __import__("datetime").datetime(2026, 9, 25, tzinfo=__import__("datetime").timezone.utc),
        monotonic_fn=lambda: current_time[0],
        wall_time_fn=lambda: current_time[0],
        sleep_fn=sleep_fn,
        min_interval_seconds=0,
    )

    for _ in range(100):
        client.request("/fixtures", {"team": 10, "last": 5})

    with pytest.raises(RuntimeError, match="100.*daily|daily.*100"):
        client.request("/fixtures", {"team": 10, "last": 5})

    state = cache.find_one({"_id": "ucl2026:team_form_sync"})
    assert len(calls) == 100
    assert state["api_requests_date"] == "2026-09-25"
    assert state["api_requests_count"] == 100


def test_api_football_client_enforces_nine_requests_per_rolling_minute_with_injected_clock():
    current_time = [0.0]
    sleeps = []
    request_times = []

    def sleep_fn(seconds):
        sleeps.append(seconds)
        current_time[0] += seconds

    client = ApiFootballClient(
        "test-key",
        request_fn=lambda *args, **kwargs: (request_times.append(current_time[0]) or FakeResponse({"response": []})),
        monotonic_fn=lambda: current_time[0],
        wall_time_fn=lambda: current_time[0],
        sleep_fn=sleep_fn,
        min_interval_seconds=0,
    )

    for _ in range(10):
        client.request("/teams", {"league": 2, "season": 2026})

    assert len(request_times) == 10
    assert request_times[9] - request_times[0] >= 60
    assert sleeps and sleeps[-1] >= 60


def test_bootstrap_fetches_provider_team_count_and_paces_fixture_requests():
    cache = MemoryCollection()
    current_time = [0.0]
    sleeps = []
    requests = []
    payloads = {
        ("/teams", None): {"response": [
            {"team": {"id": 10, "name": "A"}},
            {"team": {"id": 20, "name": "B"}},
            {"team": {"id": 30, "name": "C"}},
        ]},
    }

    def sleep_fn(seconds):
        sleeps.append(seconds)
        current_time[0] += seconds

    def request_fn(url, *, headers, params, timeout):
        path = "/" + url.rsplit("/", 1)[-1]
        requests.append((path, dict(params), current_time[0]))
        return FakeResponse(payloads.get((path, params.get("team")), {"response": []}))

    client = ApiFootballClient(
        "test-key",
        request_fn=request_fn,
        cache_collection=cache,
        monotonic_fn=lambda: current_time[0],
        wall_time_fn=lambda: current_time[0],
        sleep_fn=sleep_fn,
        min_interval_seconds=7,
    )
    service = TeamFormService(cache, client)

    result = service.bootstrap(season=2026, sleep_fn=sleep_fn, min_interval_seconds=7)

    fixture_times = [at for path, _, at in requests if path == "/fixtures"]
    assert [params for path, params, _ in requests] == [
        {"league": 2, "season": 2026},
        {"team": "10", "last": 5},
        {"team": "20", "last": 5},
        {"team": "30", "last": 5},
    ]
    assert [team["team_id"] for team in cache.find_one({"_id": "ucl2026:team_form_teams"})["teams"]] == ["10", "20", "30"]
    assert [later - earlier for earlier, later in zip(fixture_times, fixture_times[1:])] == [7, 7]
    assert result["teams_total"] == 3
    assert cache.find_one({"_id": "ucl2026:team_form_bootstrap"})["completed_team_ids"] == ["10", "20", "30"]


def test_bootstrap_resumes_only_unfinished_team_and_deduplicates_fixtures():
    cache = MemoryCollection([{
        "_id": "ucl2026:team_form_bootstrap",
        "competition": "ucl2026",
        "season": 2026,
        "completed_team_ids": ["10"],
    }])
    requests = []
    current_time = [0.0]
    client = ApiFootballClient(
        "test-key",
        request_fn=lambda url, *, headers, params, timeout: (
            requests.append((url.rsplit("/", 1)[-1], dict(params)))
            or FakeResponse({"response": [
                {"team": {"id": 10, "name": "A"}},
                {"team": {"id": 20, "name": "B"}},
            ]} if url.endswith("/teams") else {
                "response": [_fixture(201), _fixture(201)]
            })
        ),
        cache_collection=cache,
        monotonic_fn=lambda: current_time[0],
        wall_time_fn=lambda: current_time[0],
        sleep_fn=lambda seconds: current_time.__setitem__(0, current_time[0] + seconds),
        min_interval_seconds=0,
    )

    result = TeamFormService(cache, client).bootstrap(sleep_fn=lambda seconds: None, min_interval_seconds=0)

    assert requests == [
        ("teams", {"league": 2, "season": 2026}),
        ("fixtures", {"team": "20", "last": 5}),
    ]
    assert [match["fixture_id"] for match in cache.find_one({"_id": "ucl2026:team_form:20"})["matches"]] == ["201"]
    assert result["teams_skipped"] == 1


def test_bootstrap_records_only_successful_teams_and_can_resume_after_api_error():
    cache = MemoryCollection()
    requests = []
    fail_second = [True]
    current_time = [0.0]

    def request_fn(url, *, headers, params, timeout):
        path = url.rsplit("/", 1)[-1]
        requests.append((path, params.get("team")))
        if path == "teams":
            return FakeResponse({"response": [
                {"team": {"id": 10, "name": "A"}},
                {"team": {"id": 20, "name": "B"}},
            ]})
        if params["team"] == "20" and fail_second[0]:
            return FakeResponse({"errors": {"plan": "Forbidden"}, "response": []})
        return FakeResponse({"response": [_fixture(200 + int(params["team"]))]})

    def sleep_fn(seconds):
        current_time[0] += seconds

    client = ApiFootballClient(
        "test-key",
        request_fn=request_fn,
        cache_collection=cache,
        monotonic_fn=lambda: current_time[0],
        wall_time_fn=lambda: current_time[0],
        sleep_fn=sleep_fn,
        min_interval_seconds=0,
    )
    service = TeamFormService(cache, client)

    with pytest.raises(RuntimeError, match="Forbidden"):
        service.bootstrap(sleep_fn=sleep_fn, min_interval_seconds=0)

    assert cache.find_one({"_id": "ucl2026:team_form_bootstrap"})["completed_team_ids"] == ["10"]
    fail_second[0] = False
    requests.clear()

    service.bootstrap(sleep_fn=sleep_fn, min_interval_seconds=0)

    assert requests == [("teams", None), ("fixtures", "20")]
    assert cache.find_one({"_id": "ucl2026:team_form_bootstrap"})["completed_team_ids"] == ["10", "20"]


def test_two_clients_share_persisted_minute_gate_and_daily_budget():
    cache = MemoryCollection()
    current_time = [0.0]
    request_times = []

    def sleep_fn(seconds):
        current_time[0] += seconds

    def request_fn(*args, **kwargs):
        request_times.append(current_time[0])
        return FakeResponse({"response": []})

    clients = [ApiFootballClient(
        "test-key", request_fn=request_fn, cache_collection=cache,
        now_fn=lambda: __import__("datetime").datetime(2026, 9, 25, tzinfo=__import__("datetime").timezone.utc),
        wall_time_fn=lambda: current_time[0], sleep_fn=sleep_fn,
        min_interval_seconds=0,
    ) for _ in range(2)]

    for index in range(100):
        clients[index % 2].request("/fixtures", {"team": 10, "last": 5})

    assert request_times[9] - request_times[0] >= 60
    assert cache.find_one({"_id": "ucl2026:team_form_sync"})["api_requests_count"] == 100
    with pytest.raises(RuntimeError, match="100.*daily|daily.*100"):
        clients[1].request("/fixtures", {"team": 10, "last": 5})
    assert len(request_times) == 100
    assert "ucl2026:team_form_request_gate" not in cache.documents


def test_bootstrap_cli_requires_both_secrets_before_opening_mongo(monkeypatch):
    from scripts import bootstrap_ucl_team_form as script

    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.setattr(script, "MongoClient", lambda *args, **kwargs: pytest.fail("Mongo opened without credentials"))
    with pytest.raises(SystemExit, match="MONGO_URI"):
        script.main([])

    monkeypatch.setenv("MONGO_URI", "mongodb://example.invalid")
    with pytest.raises(SystemExit, match="API_FOOTBALL_KEY"):
        script.main([])


def test_bootstrap_cli_applies_environment_and_command_line_overrides(monkeypatch, capsys):
    from scripts import bootstrap_ucl_team_form as script

    cache = MemoryCollection()
    calls = []
    monkeypatch.setenv("MONGO_URI", "mongodb://example.invalid")
    monkeypatch.setenv("API_FOOTBALL_KEY", "key")
    monkeypatch.setenv("UCL_TEAM_FORM_LEAGUE", "3")
    monkeypatch.setenv("UCL_TEAM_FORM_SEASON", "2025")

    class FakeDatabase:
        def __getitem__(self, key):
            calls.append(("collection", key))
            return cache

    class FakeMongo:
        def __init__(self, uri, **kwargs):
            calls.append(("mongo", uri))

        def __getitem__(self, key):
            return FakeDatabase()

    class FakeClient:
        def __init__(self, key, **kwargs):
            calls.append(("provider", key))

    class FakeService:
        def __init__(self, collection, client):
            assert collection is cache

        def bootstrap(self, **kwargs):
            calls.append(("bootstrap", kwargs))
            return {"teams_total": 0}

    monkeypatch.setattr(script, "MongoClient", FakeMongo)
    monkeypatch.setattr(script, "ApiFootballClient", FakeClient)
    monkeypatch.setattr(script, "TeamFormService", FakeService)
    script.main([])
    assert ("bootstrap", {"league": 3, "season": 2025}) in calls
    calls.clear()
    script.main(["--league", "4", "--season", "2027"])

    assert ("collection", "cache_ucl2026") in calls
    assert ("bootstrap", {"league": 4, "season": 2027}) in calls
    assert "teams_total" in capsys.readouterr().out


def test_bootstrap_cli_reports_provider_plan_errors_without_traceback(monkeypatch):
    from scripts import bootstrap_ucl_team_form as script

    monkeypatch.setenv("MONGO_URI", "mongodb://example.invalid")
    monkeypatch.setenv("API_FOOTBALL_KEY", "key")

    class FakeMongo:
        def __init__(self, *args, **kwargs):
            pass

        def __getitem__(self, key):
            return self

        def close(self):
            pass

    class FailingService:
        def __init__(self, collection, client):
            pass

        def bootstrap(self, **kwargs):
            raise RuntimeError("API-Football error: plan unavailable")

    monkeypatch.setattr(script, "MongoClient", FakeMongo)
    monkeypatch.setattr(script, "TeamFormService", FailingService)
    with pytest.raises(SystemExit, match="Team-form bootstrap failed.*plan unavailable"):
        script.main([])


class DailyClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def request(self, path, params):
        assert path == "/fixtures"
        assert set(params) == {"date", "timezone", "page"}
        assert params["timezone"] == "Europe/Zurich"
        self.requests.append(dict(params))
        response = self.responses[(params["date"], params["page"])]
        if isinstance(response, Exception):
            raise response
        return response


def _daily_payload(fixtures=(), current=1, total=1):
    return {"response": list(fixtures), "paging": {"current": current, "total": total}}


def test_daily_refresh_uses_zurich_yesterday_pages_and_only_stored_teams():
    cache = MemoryCollection([{
        "_id": "ucl2026:team_form_teams", "competition": "ucl2026",
        "teams": [{"team_id": "10", "name": "Team"}],
    }])
    client = DailyClient({
        ("2026-09-24", 1): _daily_payload([_fixture(101)], 1, 2),
        ("2026-09-24", 2): _daily_payload([_fixture(102), _away_fixture(_fixture(103))], 2, 2),
    })
    service = TeamFormService(cache, client)

    result = service.refresh_daily(now=datetime(2026, 9, 24, 22, 30, tzinfo=timezone.utc))

    assert [(item["date"], item["page"]) for item in client.requests] == [
        ("2026-09-24", 1), ("2026-09-24", 2),
    ]
    assert result["status"] == "fresh"
    assert cache.find_one({"_id": "ucl2026:team_form_sync"})["last_successful_date"] == "2026-09-24"
    stored = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert [match["fixture_id"] for match in stored["matches"]] == ["101", "102", "103"]
    assert "ucl2026:team_form:20" not in cache.documents
    assert stored["status"] == "fresh"
    assert stored["source"] == "api_football"
    assert stored["provider"] == "api_football"
    assert stored["last_successful_at"] == stored["observed_at"]
    assert stored["coverage"]["matches"] == 3


def test_daily_refresh_catches_up_oldest_seven_dates_and_is_idempotent():
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form_sync", "last_successful_date": "2026-09-10"},
    ])
    dates = [f"2026-09-{day:02d}" for day in range(11, 25)]
    responses = {
        (date, 1): _daily_payload([_fixture(day, date=f"{date}T18:00:00+00:00")])
        for day, date in enumerate(dates, start=11)
    }
    client = DailyClient(responses)
    service = TeamFormService(cache, client)
    now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)

    first = service.refresh_daily(now=now)
    first_state = dict(cache.find_one({"_id": "ucl2026:team_form_sync"}))
    first_row = dict(cache.find_one({"_id": "ucl2026:team_form:10"}))
    second = service.refresh_daily(now=now)
    third = service.refresh_daily(now=now)

    assert first["dates_processed"] == dates[:7]
    assert first["status"] == "stale"
    assert first["remaining_dates"] == 7
    assert "catch-up pending" in first["error"]
    assert first_state["status"] == first_row["status"] == "stale"
    assert first_state["last_successful_date"] == dates[6]
    assert second["dates_processed"] == dates[7:]
    assert second["status"] == "fresh"
    assert third["status"] == "fresh"
    assert third["dates_processed"] == []
    assert [item["date"] for item in client.requests] == dates
    final_sync = cache.find_one({"_id": "ucl2026:team_form_sync"})
    assert final_sync["last_successful_date"] == "2026-09-24"
    assert final_sync["remaining_dates"] == 0
    assert [match["fixture_id"] for match in cache.find_one({"_id": "ucl2026:team_form:10"})["matches"]] == [
        "24", "23", "22", "21", "20",
    ]


def test_daily_refresh_failure_keeps_rows_and_checkpoint_and_marks_stale():
    old_match = TeamFormService(MemoryCollection(), object()).parse_fixtures("10", {"response": [_fixture(1)]})[0]
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form_sync", "last_successful_date": "2026-09-23"},
        {"_id": "ucl2026:team_form:10", "team_id": "10", "matches": [old_match],
         "status": "fresh", "last_successful_at": "2026-09-23T08:00:00+00:00"},
    ])
    client = DailyClient({
        ("2026-09-24", 1): _daily_payload([_fixture(2)], 1, 2),
        ("2026-09-24", 2): RuntimeError("provider timeout"),
    })

    result = TeamFormService(cache, client).refresh_daily(now=datetime(2026, 9, 25, tzinfo=timezone.utc))

    stored = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert result["status"] == "stale"
    assert result["error"] == "provider timeout"
    assert stored["matches"] == [old_match]
    assert stored["last_successful_at"] == "2026-09-23T08:00:00+00:00"
    assert stored["status"] == "stale"
    assert stored["source"] == stored["provider"] == "api_football"
    assert stored["error"] == "provider timeout"
    assert stored["last_attempt_at"] == stored["observed_at"]
    assert cache.find_one({"_id": "ucl2026:team_form_sync"})["last_successful_date"] == "2026-09-23"


def test_missing_client_marks_cached_form_stale_and_keeps_matches():
    match = {"fixture_id": "1", "played_at": "2026-09-23T18:00:00+00:00"}
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form:10", "team_id": "10", "matches": [match], "status": "fresh"},
    ])

    result = TeamFormService(cache, client=None).refresh_daily(now=datetime(2026, 9, 25, tzinfo=timezone.utc))

    assert result["status"] == "stale"
    stored = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert stored["matches"] == [match]
    assert stored["status"] == "stale"
    assert "API_FOOTBALL_KEY" in stored["error"]
    assert stored["last_attempt_at"] == stored["observed_at"]
    assert cache.find_one({"_id": "ucl2026:team_form_teams"})["status"] == "stale"


def test_missing_client_without_cached_form_is_unavailable():
    result = TeamFormService(MemoryCollection(), client=None).refresh_daily(
        now=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    assert result["status"] == "unavailable"


def test_daily_successful_empty_fixture_response_is_unavailable_for_new_team():
    cache = MemoryCollection([{
        "_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}],
    }])
    client = DailyClient({("2026-09-24", 1): _daily_payload()})

    result = TeamFormService(cache, client).refresh_daily(now=datetime(2026, 9, 25, tzinfo=timezone.utc))

    row = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert result["status"] == "fresh"
    assert row["status"] == "unavailable"
    assert row["matches"] == []
    assert row["coverage"] == {"matches": 0, "limit": 5}
    assert "no completed" in row["error"].lower()


def test_daily_successful_empty_day_keeps_existing_nonempty_row_fresh():
    match = {"fixture_id": "1", "played_at": "2026-09-23T18:00:00+00:00"}
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form:10", "team_id": "10", "matches": [match], "status": "stale"},
    ])
    client = DailyClient({("2026-09-24", 1): _daily_payload()})

    TeamFormService(cache, client).refresh_daily(now=datetime(2026, 9, 25, tzinfo=timezone.utc))

    row = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert row["status"] == "fresh"
    assert row["matches"] == [match]


def test_daily_refresh_updates_supplemented_teams_once_per_zurich_day():
    old_match = TeamFormService(MemoryCollection(), object()).parse_fixtures(
        "10", {"response": [_fixture(1, date="2026-09-20T18:00:00+00:00")]},
    )[0]
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form_sync", "last_successful_date": "2026-09-25"},
        {"_id": "ucl2026:team_form:10", "team_id": "10", "matches": [old_match],
         "status": "fresh", "source": "espn+fotmob", "provider": "espn+fotmob"},
    ])

    class SupplementalClient:
        provider = "espn"

        def __init__(self):
            self.requests = []

        def request(self, path, params):
            self.requests.append((path, dict(params)))
            self.provider = "espn+fotmob"
            return {"response": [_fixture(2, date="2026-09-25T18:00:00+00:00")]}

    client = SupplementalClient()
    service = TeamFormService(cache, client)
    now = datetime(2026, 9, 26, 9, tzinfo=timezone.utc)

    first = service.refresh_daily(now=now)
    second = service.refresh_daily(now=now)

    assert client.requests == [("/fixtures", {"team": "10", "last": 5})]
    assert first["status"] == second["status"] == "fresh"
    assert cache.find_one({"_id": "ucl2026:team_form_sync"})["supplemental_refresh_date"] == "2026-09-26"
    row = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert [match["fixture_id"] for match in row["matches"]] == ["2", "1"]
    assert row["provider"] == row["source"] == "espn+fotmob"


@pytest.mark.parametrize("paging", [None, {}, {"current": 0, "total": 1}, {"current": 1, "total": 0}, {"current": 2, "total": 1}, {"current": "1", "total": 1}, {"current": 2, "total": 2}])
def test_daily_malformed_paging_keeps_checkpoint_and_cached_rows(paging):
    match = {"fixture_id": "old", "played_at": "2026-09-23T18:00:00+00:00"}
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form_sync", "last_successful_date": "2026-09-23"},
        {"_id": "ucl2026:team_form:10", "team_id": "10", "matches": [match], "status": "fresh"},
    ])
    client = DailyClient({("2026-09-24", 1): {"response": [_fixture(2)], "paging": paging}})

    result = TeamFormService(cache, client).refresh_daily(now=datetime(2026, 9, 25, tzinfo=timezone.utc))

    assert result["status"] == "stale"
    assert "paging" in result["error"].lower()
    assert cache.find_one({"_id": "ucl2026:team_form_sync"})["last_successful_date"] == "2026-09-23"
    row = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert row["matches"] == [match]
    assert row["status"] == "stale"


def test_bootstrap_rows_record_fresh_provider_metadata():
    cache = MemoryCollection()
    client = type("Client", (), {"request": lambda self, path, params: (
        {"response": [{"team": {"id": 10, "name": "Team"}}]} if path == "/teams"
        else {"response": [_fixture(10)]}
    )})()

    TeamFormService(cache, client, now_fn=lambda: datetime(2026, 9, 25, tzinfo=timezone.utc)).bootstrap(min_interval_seconds=0)

    stored = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert stored["status"] == "fresh"
    assert stored["provider"] == stored["source"] == "api_football"
    assert stored["last_successful_at"] == "2026-09-25T00:00:00+00:00"
    assert stored["coverage"]["matches"] == 1
    assert cache.find_one({"_id": "ucl2026:team_form_teams"})["status"] == "fresh"
    bootstrap_state = cache.find_one({"_id": "ucl2026:team_form_bootstrap"})
    assert bootstrap_state["status"] == "fresh"
    assert bootstrap_state["provider"] == bootstrap_state["source"] == "api_football"
    assert bootstrap_state["last_successful_at"] == "2026-09-25T00:00:00+00:00"


def test_bootstrap_valid_empty_fixture_response_records_unavailable_row():
    cache = MemoryCollection()

    class Client:
        def request(self, path, params):
            return {"response": [{"team": {"id": 10, "name": "Team"}}]} if path == "/teams" else {"response": []}

    TeamFormService(cache, Client(), now_fn=lambda: datetime(2026, 9, 25, tzinfo=timezone.utc)).bootstrap(min_interval_seconds=0)

    row = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert row["status"] == "unavailable"
    assert row["matches"] == []
    assert row["coverage"] == {"matches": 0, "limit": 5}
    assert "no completed" in row["error"].lower()


def test_bootstrap_provider_error_marks_existing_rows_stale_without_clearing_matches():
    match = {"fixture_id": "1", "played_at": "2026-09-23T18:00:00+00:00"}
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}]},
        {"_id": "ucl2026:team_form:10", "team_id": "10", "matches": [match], "status": "fresh"},
    ])

    class Client:
        def request(self, path, params):
            if path == "/teams":
                return {"response": [{"team": {"id": 10, "name": "Team"}}]}
            raise RuntimeError("bootstrap unavailable")

    with pytest.raises(RuntimeError, match="bootstrap unavailable"):
        TeamFormService(cache, Client(), now_fn=lambda: datetime(2026, 9, 25, tzinfo=timezone.utc)).bootstrap(min_interval_seconds=0)

    stored = cache.find_one({"_id": "ucl2026:team_form:10"})
    assert stored["matches"] == [match]
    assert stored["status"] == "stale"
    assert stored["error"] == "bootstrap unavailable"
    assert stored["last_attempt_at"] == "2026-09-25T00:00:00+00:00"


def test_bootstrap_roster_fetch_error_marks_existing_bootstrap_state_stale():
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Team"}], "status": "fresh"},
        {"_id": "ucl2026:team_form_bootstrap", "completed_team_ids": ["10"], "status": "fresh"},
    ])

    class Client:
        def request(self, path, params):
            raise RuntimeError("roster timeout")

    with pytest.raises(RuntimeError, match="roster timeout"):
        TeamFormService(cache, Client(), now_fn=lambda: datetime(2026, 9, 25, tzinfo=timezone.utc)).bootstrap()

    state = cache.find_one({"_id": "ucl2026:team_form_bootstrap"})
    assert state["completed_team_ids"] == ["10"]
    assert state["status"] == "stale"
    assert state["error"] == "roster timeout"


def test_maintenance_runs_form_for_ucl_even_when_odds_fail_and_skips_wc_and_force():
    cache = MemoryCollection()
    called = []

    class Form:
        def refresh_daily(self, now=None):
            called.append(now)
            return {"status": "fresh", "source": "api_football"}

    class BrokenOdds:
        def get_competition_odds(self, competition, market):
            raise RuntimeError("odds down")

    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    ucl = run_maintenance({"ucl2026": cache}, BrokenOdds(), competition="ucl2026", now=now, team_form_service=Form())
    wc = run_maintenance({"wc2026": MemoryCollection()}, BrokenOdds(), competition="wc2026", now=now, team_form_service=Form())
    forced = run_maintenance({"ucl2026": cache}, BrokenOdds(), competition="ucl2026", force=True, team_form_service=Form())

    assert ucl["status"] == "failed"
    assert ucl["team_form_status"]["status"] == "fresh"
    assert len(called) == 1 and called[0] == now
    assert "team_form_status" not in wc
    assert forced["team_form_status"]["status"] == "skipped"


def test_form_exception_does_not_abort_ucl_odds_maintenance():
    cache = MemoryCollection()
    calls = []

    class Form:
        def refresh_daily(self, now=None):
            raise RuntimeError("form down")

    class Odds:
        def get_competition_odds(self, competition, market):
            calls.append(competition)
            return []

    result = run_maintenance({"ucl2026": cache}, Odds(), competition="ucl2026", now=datetime(2026, 9, 25, tzinfo=timezone.utc), team_form_service=Form())

    assert calls
    assert result["status"] == "success"
    assert result["team_form_status"]["status"] == "stale"
    assert result["team_form_status"]["error"] == "form down"


def test_authenticated_maintenance_route_forwards_form_service(monkeypatch):
    from src.routes import maintenance as route

    cache = MemoryCollection()
    calls = []

    class Form:
        def refresh_daily(self, now=None):
            calls.append(now)
            return {"status": "unavailable", "source": "api_football"}

    class Odds:
        def get_competition_odds(self, competition, market):
            return []

    monkeypatch.setattr(route.espn_data, "get_scoreboard", lambda *args, **kwargs: [])
    monkeypatch.setattr(route, "ingest_clubelo", lambda *args, **kwargs: {"status": "unavailable", "rows": []})
    endpoint = route.init_router({"ucl2026": cache}, Odds(), cron_secret="test-secret", team_form_service=Form(), now_fn=lambda: datetime(2026, 9, 25, tzinfo=timezone.utc)).routes[0].endpoint
    request = Request({
        "type": "http", "method": "POST", "path": "/api/internal/maintenance",
        "headers": [(b"authorization", b"Bearer test-secret")], "query_string": b"",
        "scheme": "http", "server": ("test", 80), "client": ("test", 1),
        "root_path": "", "http_version": "1.1",
    })

    result = endpoint(request, competition="ucl2026")

    assert result["team_form_status"]["status"] == "unavailable"
    assert calls == [datetime(2026, 9, 25, tzinfo=timezone.utc)]


def test_api_startup_without_form_key_keeps_cache_readable(monkeypatch):
    import importlib

    monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=50")
    monkeypatch.setenv("ODDS_API_KEY", "test-only-key")
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.setenv("USE_API_FOOTBALL", "false")
    from src import api
    importlib.reload(api)

    assert isinstance(api.team_form_service.client, FailoverTeamFormClient)
    assert api.team_form_service.client.primary is None
    assert api.team_form_service.competition.id == "ucl2026"


def test_cached_form_resolves_existing_alias_and_keeps_newest_match_details():
    matches = [
        {"fixture_id": "2", "played_at": "2026-09-24T18:00:00+00:00", "result": "W"},
        {"fixture_id": "1", "played_at": "2026-09-20T18:00:00+00:00", "result": "L"},
    ]
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "teams": [{"team_id": "10", "name": "Paris Saint Germain"}]},
        {"_id": "ucl2026:team_form:10", "status": "stale", "source": "api_football",
         "observed_at": "2026-09-25T08:00:00+00:00", "error": "provider down", "matches": matches},
    ])

    result = TeamFormService(cache, client=None).cached_form_for_match("Paris Saint-Germain")

    assert result == {
        "status": "stale",
        "source": "api_football",
        "observed_at": "2026-09-25T08:00:00+00:00",
        "error": "provider down",
        "form": ["L", "W"],
        "on_fire": False,
        "matches": matches,
    }


def test_cached_form_supports_provider_id_and_explicit_unavailable_state():
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form:10", "status": "fresh", "source": "api_football",
         "observed_at": "2026-09-25T08:00:00+00:00", "matches": []},
    ])
    service = TeamFormService(cache, client=None)

    by_id = service.cached_form_for_match("Unknown alias", fallback_team_id=10)
    missing = service.cached_form_for_match("Unknown alias")

    assert by_id["status"] == "unavailable"
    assert by_id["form"] == by_id["matches"] == []
    assert missing["status"] == "unavailable"
    assert missing["source"] == "api_football"
    assert missing["error"]


def test_ucl_match_route_adds_cached_form_without_provider_calls_or_cache_mutation():
    source_match = {
        "id": "ucl-1", "home_team": "Paris Saint-Germain", "away_team": "Arsenal",
        "completed": True, "actual_score": "2:1", "top_tip": "2:1", "raw_match": {},
    }
    cache = MemoryCollection([
        {"_id": "ucl2026:matches_cache", "data": [source_match]},
        {"_id": "ucl2026:team_form_teams", "teams": [
            {"team_id": "10", "name": "Paris Saint Germain"}, {"team_id": "20", "name": "Arsenal"},
        ]},
        {"_id": "ucl2026:team_form:10", "status": "fresh", "source": "api_football",
         "observed_at": "2026-09-25T08:00:00+00:00", "matches": [
             {"fixture_id": "f1", "played_at": "2026-09-24T18:00:00+00:00", "result": "W"},
         ]},
    ])

    class Engine:
        team_forms = {}

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            raise AssertionError("public reads must not call providers")

    service = TeamFormService(cache, client=Provider())
    endpoint = matches_router(
        Engine(), Provider(), {"ucl2026": cache}, {"ucl2026": MemoryCollection()},
        team_form_service=service,
    ).routes[0].endpoint

    normal = endpoint(competition="ucl2026")
    forced = endpoint(force=True, competition="ucl2026")

    assert normal[0]["home_form"]["form"] == ["W"]
    assert normal[0]["away_form"]["status"] == "unavailable"
    assert forced[0]["home_form"] == normal[0]["home_form"]
    assert "home_form" not in source_match
    assert "home_form" not in cache.find_one({"_id": "ucl2026:matches_cache"})["data"][0]


def test_wc_match_route_keeps_legacy_math_engine_form_unchanged():
    cache = MemoryCollection([{
        "_id": "wc2026:matches_cache",
        "data": [{"id": "wc-1", "home_team": "France", "away_team": "Spain",
                  "completed": True, "actual_score": "1:0", "top_tip": "1:0", "raw_match": {}}],
    }])

    class Engine:
        team_forms = {
            "France": {"form": ["W", "D"], "on_fire": False},
            "Spain": {"form": ["L"], "on_fire": False},
        }

        def reload_elo_data(self):
            return None

    class ForbiddenFormService:
        def cached_form_for_match(self, *args, **kwargs):
            raise AssertionError("WC must not read UCL form cache")

    endpoint = matches_router(
        Engine(), object(), {"wc2026": cache}, {"wc2026": MemoryCollection()},
        team_form_service=ForbiddenFormService(),
    ).routes[0].endpoint

    result = endpoint(competition="wc2026")

    assert result[0]["home_form"] == {"form": ["W", "D"], "on_fire": False}
    assert result[0]["away_form"] == {"form": ["L"], "on_fire": False}
