from datetime import datetime, timezone

from src.services.team_form import TeamFormService


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}

    def find_one(self, query):
        document = self.documents.get(query.get("_id"))
        return document if document and all(document.get(k) == v for k, v in query.items()) else None

    def find(self, query=None):
        documents = list(self.documents.values())
        if not query:
            return documents
        expected = query.get("_id", {}).get("$in")
        return [doc for doc in documents if expected is None or doc.get("_id") in expected]

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise ValueError("duplicate key")
        self.documents[document["_id"]] = dict(document)

    def update_one(self, query, update, upsert=False):
        key = query["_id"]
        existing = self.documents.get(key)
        if existing and any(existing.get(k) != v for k, v in query.items()):
            return type("Result", (), {"matched_count": 0})()
        document = dict(existing or {"_id": key})
        document.update(update.get("$set", {}))
        self.documents[key] = document
        return type("Result", (), {"matched_count": 1})()

    def delete_one(self, query):
        document = self.find_one(query)
        if document:
            self.documents.pop(query["_id"], None)


NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def fixture(
    event_id="e1", *, home_id="10", away_id="20", home_name="Arsenal", away_name="Chelsea",
    date="2026-10-20T18:00:00Z", status="FT", competition_id="eng.1",
    competition_name="English Premier League", competition_type="League", competition_slug="eng.1",
    home_logo="https://a.espncdn.com/arsenal.png", away_logo="https://a.espncdn.com/chelsea.png",
    home_goals=2, away_goals=1, score_90=None, score_aet=None, penalties=None, cancelled=False,
):
    score = {}
    if score_90 is not None:
        score["fulltime"] = score_90
    if score_aet is not None:
        score["extratime"] = score_aet
    if penalties is not None:
        score["penalty"] = penalties
    return {
        "fixture": {
            "id": event_id, "date": date,
            "status": {"short": status, "cancelled": cancelled},
        },
        "league": {
            "id": competition_id, "slug": competition_slug,
            "name": competition_name, "type": competition_type,
        },
        "teams": {
            "home": {"id": home_id, "name": home_name, "logo": home_logo},
            "away": {"id": away_id, "name": away_name, "logo": away_logo},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "score": score,
    }


class EspnClient:
    provider = "espn"
    provider_namespace = "espn:team-id"

    def __init__(self, schedules, *, roster=None, fixture_index=None):
        self.schedules = schedules
        self.roster = roster or [
            {"team": {"id": team_id, "name": name, "logo": f"https://a.espncdn.com/{team_id}.png"}}
            for team_id, name in (
                ("10", "Arsenal"), ("20", "Chelsea"),
                *((f"extra-{index}", f"Team {index}") for index in range(3, 21)),
            )
        ]
        self.fixture_index = fixture_index or {}
        self.calls = []
        self.fail_team = None

    def request(self, path, params=None):
        params = params or {}
        self.calls.append((path, dict(params)))
        if path == "/teams":
            return {"response": self.roster, "fixture_index": self.fixture_index}
        if path == "/fixtures":
            team_id = str(params["team"])
            if team_id == self.fail_team:
                raise RuntimeError("ESPN schedule unavailable")
            return {"response": self.schedules.get(team_id, [])}
        raise AssertionError(path)


def test_form_rows_require_exact_provider_team_identity_and_verified_senior_competition():
    service = TeamFormService(MemoryCollection(), EspnClient({}), competition="epl2026")
    candidates = [
        # A same-name women's team has a distinct provider identity.
        fixture("wrong-id", home_id="11", home_name="Arsenal"),
        fixture("women", competition_id="eng.w.1", competition_slug="eng.w.1",
                competition_name="Women's Super League"),
        fixture("liga-f", competition_id="esp.liga.f", competition_slug="esp.liga.f",
                competition_name="Liga F"),
        fixture("youth", competition_id="eng.u18", competition_slug="eng.u18",
                competition_name="Premier League U18"),
        fixture("development-league", competition_id="eng.pl2", competition_slug="eng.pl2",
                competition_name="Premier League 2"),
        fixture("wrong-gender-on-known-league", competition_id="740", competition_slug="esp.1",
                competition_name="Women's Spanish LALIGA"),
        fixture("liga-f-on-known-league", competition_id="740", competition_slug="esp.1",
                competition_name="Liga F"),
        fixture("league-id-slug-mismatch", competition_id="740", competition_slug="ita.1",
                competition_name="Italian Serie A"),
        fixture("friendly", competition_id="club.friendly", competition_slug="club.friendly",
                competition_name="Club Friendlies"),
        fixture("unknown-id-with-known-name", competition_id="999", competition_slug="unknown.1",
                competition_name="English Premier League"),
        fixture("unknown", competition_id=None, competition_slug=None,
                competition_name="Unclassified Competition", competition_type=""),
        fixture("cancelled", status="PST", cancelled=True),
        fixture("valid"),
    ]

    rows = service.parse_fixtures("10", {"response": candidates}, provider="espn", now=NOW)

    assert [row["fixture_id"] for row in rows] == ["valid"]
    assert rows[0]["identity_verified"] is True
    assert rows[0]["provider_namespace"] == "espn:team-id"
    assert rows[0]["competition_id"] == "eng.1"
    assert rows[0]["competition_slug"] == "eng.1"
    assert rows[0]["competition_kind"] == "league"
    assert rows[0]["home_id"] == "10" and rows[0]["away_id"] == "20"
    assert rows[0]["home_team"] == "Arsenal" and rows[0]["away_team"] == "Chelsea"
    assert rows[0]["home_logo"].endswith("arsenal.png")
    assert rows[0]["away_logo"].endswith("chelsea.png")
    assert rows[0]["provider"] == "espn"
    assert rows[0]["result_type"] == "FT"


def test_known_espn_senior_league_and_cup_slugs_are_classified_by_provider_identity():
    service = TeamFormService(MemoryCollection(), EspnClient({}), competition="ucl2026")
    fixtures = [
        fixture("spanish", competition_id="740", competition_slug="esp.1",
                competition_name="Spanish LALIGA", competition_type=""),
        fixture("italian", competition_id="730", competition_slug="ita.1",
                competition_name="Italian Serie A", competition_type=""),
        fixture("german", competition_id="720", competition_slug="ger.1",
                competition_name="German Bundesliga", competition_type=""),
        fixture("french", competition_id="710", competition_slug="fra.1",
                competition_name="French Ligue 1", competition_type=""),
        fixture("dutch", competition_id="725", competition_slug="ned.1",
                competition_name="Dutch Eredivisie", competition_type=""),
        fixture("portuguese", competition_id="715", competition_slug="por.1",
                competition_name="Portuguese Primeira Liga", competition_type=""),
        fixture("turkish", competition_id="3946", competition_slug="tur.1",
                competition_name="Turkish Super Lig", competition_type=""),
        fixture("fa-cup", competition_id="3918", competition_slug="eng.fa",
                competition_name="English FA Cup", competition_type=""),
        fixture("copa-del-rey", competition_id="3951", competition_slug="esp.copa_del_rey",
                competition_name="Copa del Rey", competition_type=""),
        fixture("coppa-italia", competition_id="3956", competition_slug="ita.coppa_italia",
                competition_name="Coppa Italia", competition_type=""),
        fixture("carabao", competition_id="3920", competition_slug="eng.league_cup",
                competition_name="English Carabao Cup", competition_type=""),
        fixture("german-cup", competition_id="3954", competition_slug="ger.dfb_pokal",
                competition_name="German Cup", competition_type=""),
        fixture("europa-league", competition_id="776", competition_slug="uefa.europa",
                competition_name="UEFA Europa League", competition_type=""),
    ]

    rows = [
        *service.parse_fixtures("10", {"response": fixtures[:10]}, provider="espn", now=NOW),
        *service.parse_fixtures("10", {"response": fixtures[10:]}, provider="espn", now=NOW),
    ]

    assert {row["fixture_id"] for row in rows} == {item["fixture"]["id"] for item in fixtures}
    assert {row["fixture_id"]: row["competition_kind"] for row in rows} == {
        "spanish": "league", "italian": "league", "german": "league", "french": "league",
        "dutch": "league", "portuguese": "league", "turkish": "league",
        "fa-cup": "cup", "copa-del-rey": "cup", "coppa-italia": "cup",
        "carabao": "cup", "german-cup": "cup", "europa-league": "europe",
    }
    numeric_espn_id_without_slug = dict(fixtures[0])
    numeric_espn_id_without_slug["league"] = {key: value for key, value in fixtures[0]["league"].items() if key != "slug"}
    assert service.parse_fixtures(
        "10", {"response": [numeric_espn_id_without_slug]}, provider="api_football", now=NOW,
    ) == []


def test_espn_uid_supplies_verified_competition_id_when_event_has_no_league_node():
    from test_team_form import _espn_event
    from src.services.team_form import EspnTeamFormClient

    event = _espn_event(competition="Copa del Rey")
    event.pop("league")
    event["uid"] = "s:600~l:3951~e:401"
    event["season"] = {"year": 2026, "type": 13733, "slug": "round-of-32"}
    event["competitions"][0]["altGameNote"] = "Copa del Rey, Round of 32"
    normalized = EspnTeamFormClient._normalize_event(event)
    service = TeamFormService(MemoryCollection(), EspnClient({}), competition="ucl2026")

    rows = service.parse_fixtures("359", {"response": [normalized]}, provider="espn", now=NOW)

    assert len(rows) == 1
    assert rows[0]["competition_id"] == "3951"
    assert rows[0]["competition_slug"] == "esp.copa_del_rey"
    assert rows[0]["competition_kind"] == "cup"


def test_form_parser_excludes_future_matches_and_keeps_explicit_extra_time_and_shootout_scores():
    service = TeamFormService(MemoryCollection(), EspnClient({}), competition="ucl2026")
    aet = fixture(
        "aet", status="AET", competition_id="uefa.champions", competition_slug="uefa.champions",
        competition_name="UEFA Champions League", competition_type="Cup",
        home_goals=2, away_goals=1, score_90={"home": 1, "away": 1},
        score_aet={"home": 2, "away": 1},
    )
    pen = fixture(
        "pen", status="PEN", competition_id="uefa.champions", competition_slug="uefa.champions",
        competition_name="UEFA Champions League", competition_type="Cup",
        home_goals=1, away_goals=1, penalties={"home": 5, "away": 4},
    )
    future = fixture("future", date="2026-10-25T12:00:00Z")

    rows = service.parse_fixtures("10", {"response": [aet, pen, future]}, provider="espn", now=NOW)

    assert [row["fixture_id"] for row in rows] == ["aet", "pen"]
    assert rows[0]["competition_kind"] == rows[1]["competition_kind"] == "europe"
    assert rows[0]["result"] == "W"
    assert rows[1]["score"] == "1:1"
    assert rows[1]["penalties"] == {"home": 5, "away": 4}
    assert rows[0]["score_90"] == {"home": 1, "away": 1}
    assert rows[0]["score_aet"] == {"home": 2, "away": 1}


def test_duplicate_fixture_ids_collapse_without_name_based_cross_provider_deduplication():
    service = TeamFormService(MemoryCollection(), EspnClient({}), competition="epl2026")
    primary = fixture("same", date="2026-10-20T18:00:00Z")
    duplicate = fixture("same", date="2026-10-20T18:00:00Z", home_goals=3)
    same_game_from_other_provider = fixture("other-provider:99", date="2026-10-19T18:00:00Z")

    rows = service.parse_fixtures(
        "10", {"response": [primary, duplicate, same_game_from_other_provider]},
        provider="espn", now=NOW,
    )

    assert [row["fixture_id"] for row in rows] == ["same", "other-provider:99"]
    assert next(row for row in rows if row["fixture_id"] == "same")["score"] == "3:1"


def test_cached_form_uses_only_verified_rows_before_the_target_kickoff():
    cache = MemoryCollection([
        {"_id": "epl2026:team_form_teams", "provider_namespace": "espn:team-id",
         "teams": [{"team_id": "10", "name": "Arsenal"}]},
        {"_id": "epl2026:team_form:10", "team_id": "10", "status": "fresh", "scope": "all_competitions",
         "provider_namespace": "espn:team-id",
         "observed_at": "2026-10-24T00:00:00+00:00", "validation_version": "senior-men-v1",
         "coverage": {"available": 2, "required": 10, "complete": False},
         "matches": [
             {"fixture_id": "before", "played_at": "2026-09-01T12:00:00Z", "result": "W",
              "identity_verified": True, "provider": "espn", "provider_namespace": "espn:team-id", "home_id": "10",
              "away_id": "20", "competition_id": "eng.1", "competition_name": "English Premier League",
              "competition_kind": "league", "score": "2:0"},
             {"fixture_id": "during", "played_at": "2026-10-01T12:00:00Z", "result": "L",
              "identity_verified": False, "provider": "espn", "provider_namespace": "espn:team-id", "home_id": "10",
              "away_id": "20", "competition_id": "eng.1", "competition_name": "English Premier League",
              "competition_kind": "league", "score": "0:1"},
             {"fixture_id": "after", "played_at": "2026-11-01T12:00:00Z", "result": "L",
              "identity_verified": True, "provider": "espn", "provider_namespace": "espn:team-id", "home_id": "10",
              "away_id": "20", "competition_id": "eng.1", "competition_name": "English Premier League",
              "competition_kind": "league", "score": "0:3"},
         ]},
    ])
    service = TeamFormService(cache, EspnClient({}), competition="epl2026")

    form = service.cached_form_for_match("Arsenal", "10", before="2026-10-01T12:00:00Z")

    assert [row["fixture_id"] for row in form["matches"]] == ["before"]
    assert form["form"] == ["W"]
    assert form["scope"] == "all_competitions"
    assert form["coverage"] == {"available": 1, "required": 10, "complete": False}
    assert form["validation_version"] == "senior-men-v1"


def test_bulk_cached_form_resolves_ids_from_exact_fixture_identity_not_display_names():
    cache = MemoryCollection([
        {"_id": "epl2026:team_form_teams", "provider_namespace": "espn:team-id", "teams": [
            {"team_id": "10", "name": "Same Name"}, {"team_id": "11", "name": "Same Name"},
        ], "fixture_index": {"target": {"home_id": "11", "away_id": "20"}}},
        {"_id": "epl2026:team_form:10", "team_id": "10", "status": "fresh", "scope": "all_competitions",
         "provider_namespace": "espn:team-id", "matches": [
            {"fixture_id": "men", "played_at": "2026-09-01T12:00:00Z", "result": "W", "identity_verified": True,
             "provider": "espn", "provider_namespace": "espn:team-id", "home_id": "10", "away_id": "20",
             "competition_id": "eng.1", "competition_name": "English Premier League", "competition_kind": "league"},
        ]},
        {"_id": "epl2026:team_form:11", "team_id": "11", "status": "fresh", "scope": "all_competitions",
         "provider_namespace": "espn:team-id", "matches": [
            {"fixture_id": "women", "played_at": "2026-09-01T12:00:00Z", "result": "L", "identity_verified": True,
             "provider": "espn", "provider_namespace": "espn:team-id", "home_id": "11", "away_id": "20",
             "competition_id": "eng.w.1", "competition_name": "Women's Super League", "competition_kind": "league"},
        ]},
    ])
    service = TeamFormService(cache, EspnClient({}), competition="epl2026")

    rows = service.cached_forms_for_matches([{
        "id": "target", "home_team": "Same Name", "away_team": "Chelsea",
        "commence_time": "2026-10-01T12:00:00Z",
    }])

    assert rows[0]["home_form"]["matches"] == []
    assert rows[0]["away_form"]["matches"] == []


def test_bulk_form_rejects_same_numeric_ids_from_a_different_provider_namespace():
    verified = {
        **fixture("known"),
        "fixture_id": "known", "played_at": "2026-09-01T12:00:00Z",
        "competition_name": "English Premier League", "competition_id": "eng.1",
        "competition_kind": "league", "opponent_id": "20", "opponent_name": "Chelsea",
        "venue": "home", "goals_for": 2, "goals_against": 1, "score": "2:1", "result": "W",
        "home_id": "10", "away_id": "20", "home_team": "Arsenal", "away_team": "Chelsea",
        "result_type": "FT", "provider": "espn", "provider_namespace": "espn:team-id",
        "identity_verified": True,
    }
    cache = MemoryCollection([
        {"_id": "epl2026:team_form_teams", "scope": "all_competitions",
         "provider_namespace": "espn:team-id", "teams": [{"team_id": "10", "name": "Arsenal"}]},
        {"_id": "epl2026:team_form:10", "team_id": "10", "scope": "all_competitions",
         "provider_namespace": "espn:team-id", "matches": [verified]},
    ])
    service = TeamFormService(cache, EspnClient({}), competition="epl2026")
    match = {
        "home_team": "Arsenal", "away_team": "Chelsea", "home_team_id": "10",
        "provider_namespace": "api_football:team-id", "commence_time": "2026-10-01T12:00:00Z",
    }

    row = service.cached_forms_for_matches([match])[0]

    assert row["home_form"]["matches"] == []


def test_bulk_form_reuses_identical_history_cutoffs_and_keeps_historical_cutoffs_exact(monkeypatch):
    def history_match(team_id, fixture_id, played_at, result):
        opponent_id = "20" if team_id == "10" else "10"
        return {
            "fixture_id": fixture_id, "played_at": played_at, "result": result,
            "provider": "espn", "provider_namespace": "espn:team-id", "identity_verified": True,
            "home_id": team_id, "away_id": opponent_id,
            "competition_id": "eng.1", "competition_name": "English Premier League",
            "competition_kind": "league",
        }

    team_10_history = [
        history_match("10", "a", "2026-09-10T00:00:00Z", "W"),
        history_match("10", "b", "2026-09-20T00:00:00Z", "D"),
        history_match("10", "edge", "2026-09-21T00:00:00Z", "L"),
        history_match("10", "c", "2026-09-30T00:00:00Z", "W"),
        history_match("10", "cutoff", "2026-10-01T00:00:00Z", "D"),
        history_match("10", "future", "2026-10-02T00:00:00Z", "W"),
    ]
    team_20_history = [history_match("20", "opponent-edge", "2026-09-21T00:00:00Z", "D")]
    cache = MemoryCollection([
        {"_id": "epl2026:team_form_teams", "provider_namespace": "espn:team-id", "teams": [
            {"team_id": "10", "name": "Arsenal"}, {"team_id": "20", "name": "Chelsea"},
        ]},
        {"_id": "epl2026:team_form:10", "team_id": "10", "provider": "espn",
         "provider_namespace": "espn:team-id", "scope": "all_competitions", "status": "fresh",
         "matches": team_10_history},
        {"_id": "epl2026:team_form:20", "team_id": "20", "provider": "espn",
         "provider_namespace": "espn:team-id", "scope": "all_competitions", "status": "fresh",
         "matches": team_20_history},
    ])
    service = TeamFormService(cache, client=None, competition="epl2026")
    display_calls, player_calls = [], []
    original_display, original_player = service._display_form, service._player_form

    def count_display(document, roster, *, before=None):
        display_calls.append((document.get("team_id"), before))
        return original_display(document, roster, before=before)

    def count_player(document, team_name, history_by_event):
        player_calls.append((document.get("team_id"), tuple(
            match.get("fixture_id") for match in document.get("matches", [])
        )))
        return original_player(document, team_name, history_by_event)

    monkeypatch.setattr(service, "_display_form", count_display)
    monkeypatch.setattr(service, "_player_form", count_player)
    matches = [
        {"home_team": "Arsenal", "away_team": "Chelsea", "home_team_id": "10", "away_team_id": "20",
         "provider_namespace": "espn:team-id", "commence_time": "2026-10-01T00:00:00Z"},
        {"home_team": "Arsenal", "away_team": "Chelsea", "home_team_id": "10", "away_team_id": "20",
         "provider_namespace": "espn:team-id", "commence_time": "2026-10-01T00:00:00Z"},
        {"home_team": "Arsenal", "away_team": "Chelsea", "home_team_id": "10", "away_team_id": "20",
         "provider_namespace": "espn:team-id", "commence_time": "2026-09-21T00:00:00Z"},
        {"home_team": "Arsenal", "away_team": "Chelsea", "home_team_id": "10", "away_team_id": "20",
         "provider_namespace": "espn:team-id"},
    ]

    rows = service.cached_forms_for_matches(matches)

    assert rows[0]["home_form"] is rows[1]["home_form"]
    assert rows[0]["away_form"] is rows[1]["away_form"]
    assert len(display_calls) == len(player_calls) == 5
    assert [match["fixture_id"] for match in rows[0]["home_form"]["matches"]] == ["c", "edge", "b", "a"]
    assert [match["fixture_id"] for match in rows[0]["away_form"]["matches"]] == ["opponent-edge"]
    assert [match["fixture_id"] for match in rows[2]["home_form"]["matches"]] == ["b", "a"]
    assert rows[2]["away_form"]["matches"] == []
    assert rows[3]["home_form"]["matches"] == []
    assert rows[3]["away_form"]["matches"] == []
    assert "cutoff" not in {match["fixture_id"] for match in rows[0]["home_form"]["matches"]}
    assert "future" not in {match["fixture_id"] for match in rows[0]["home_form"]["matches"]}


def test_refresh_all_competitions_stores_verified_coverage_and_preserves_last_good_rows_on_failure():
    schedules = {
        "10": [fixture("new", date="2026-10-20T18:00:00Z"), fixture("old", date="2026-10-19T18:00:00Z")],
        "20": [fixture("opponent", home_id="20", away_id="10", home_name="Chelsea", away_name="Arsenal")],
    }
    client = EspnClient(
        schedules,
        fixture_index={"target": {"home_id": "10", "away_id": "20"}},
    )
    cache = MemoryCollection()
    service = TeamFormService(cache, client, competition="epl2026", now_fn=lambda: NOW)

    refreshed = service.refresh_all_competitions(now=NOW)

    assert refreshed["status"] == "fresh"
    assert client.calls[0] == ("/teams", {"season": 2026})
    assert refreshed["provider_calls"] == 21
    form_doc = cache.find_one({"_id": "epl2026:team_form:10"})
    assert form_doc["scope"] == "all_competitions"
    assert form_doc["coverage"] == {"available": 2, "required": 10, "complete": False}
    assert form_doc["last_successful_at"] == NOW.isoformat()
    assert all(row["identity_verified"] is True for row in form_doc["matches"])

    previous_rows = list(form_doc["matches"])
    previous_success = form_doc["last_successful_at"]
    client.fail_team = "10"
    failed = service.refresh_all_competitions(now=NOW.replace(hour=13))
    unchanged = cache.find_one({"_id": "epl2026:team_form:10"})

    assert failed["status"] == "stale"
    assert unchanged["matches"] == previous_rows
    assert unchanged["last_successful_at"] == previous_success
    assert unchanged["observed_at"] == NOW.isoformat()
    assert unchanged["last_attempt_at"] == "2026-10-24T13:00:00+00:00"
    assert failed["observed_at"] == NOW.isoformat()
    assert cache.find_one({"_id": "epl2026:team_form_teams"})["last_successful_at"] == NOW.isoformat()


def test_refresh_does_not_use_a_paid_provider_for_club_form():
    class PaidClient(EspnClient):
        provider = "api_football"

    service = TeamFormService(MemoryCollection(), PaidClient({}), competition="ucl2026")

    result = service.refresh_all_competitions(now=NOW)

    assert result["status"] == "unavailable"
    assert "provider" in result["error"].casefold()


def test_refresh_requires_exact_full_competition_roster_before_marking_cache_fresh():
    old_success = "2026-10-23T10:00:00+00:00"
    old = {"fixture_id": "known-good", "played_at": "2026-10-20T12:00:00Z"}
    cache = MemoryCollection([
        {"_id": "ucl2026:team_form_teams", "scope": "all_competitions", "observed_at": old_success,
         "last_successful_at": old_success, "teams": [{"team_id": "1", "name": "Team 1"}]},
        {"_id": "ucl2026:team_form:1", "team_id": "1", "matches": [old],
         "last_successful_at": old_success, "observed_at": old_success, "scope": "all_competitions"},
    ])
    roster = [
        {"team": {"id": str(index), "name": f"Team {index}"}}
        for index in range(1, 36)
    ]
    client = EspnClient({}, roster=roster)
    result = TeamFormService(cache, client, competition="ucl2026").refresh_all_competitions(now=NOW)

    assert result["status"] == "stale"
    assert result["provider_calls"] == 1
    assert result["observed_at"] == old_success
    assert cache.find_one({"_id": "ucl2026:team_form:1"})["matches"] == [old]
    assert cache.find_one({"_id": "ucl2026:team_form:1"})["last_successful_at"] == old_success


def test_first_failed_refresh_upserts_throttle_state_without_advancing_success_times():
    class FailedEspnClient:
        provider = "espn"

        def request(self, path, params):
            raise RuntimeError("scoreboard unavailable")

    cache = MemoryCollection()
    result = TeamFormService(cache, FailedEspnClient(), competition="epl2026").refresh_all_competitions(now=NOW)

    state = cache.find_one({"_id": "epl2026:team_form_sync"})
    assert result["status"] == "unavailable"
    assert state["status"] == "stale"
    assert state["last_attempt_at"] == NOW.isoformat()
    assert state["last_attempt_provider"] == "espn"
    assert "observed_at" not in state
    assert "last_successful_at" not in state


def test_blocked_refresh_retries_share_bounded_workers_and_ignore_late_rosters(monkeypatch):
    import threading
    import time

    from src.services import team_form

    monkeypatch.setattr(team_form, "CLUB_FORM_REFRESH_DEADLINE_SECONDS", 0.12)
    release = threading.Event()
    started = threading.Event()
    inactive = threading.Event()
    active_lock = threading.Lock()
    active = 0
    peak_active = 0
    roster = [
        {"team": {"id": str(index), "name": f"Team {index}"}}
        for index in range(1, 21)
    ]

    class BlockedRosterClient:
        provider = "espn"

        def request(self, path, params):
            nonlocal active, peak_active
            assert path == "/teams"
            with active_lock:
                active += 1
                peak_active = max(peak_active, active)
                inactive.clear()
            started.set()
            try:
                release.wait()
                return {"response": roster}
            finally:
                with active_lock:
                    active -= 1
                    if active == 0:
                        inactive.set()

    worker_count = team_form.CLUB_FORM_REFRESH_WORKERS + 8
    barrier = threading.Barrier(worker_count + 1)
    client = BlockedRosterClient()
    caches = [MemoryCollection() for _ in range(worker_count)]
    results = [None] * worker_count
    finished = 0
    finished_lock = threading.Lock()
    all_finished = threading.Event()

    def refresh(index):
        nonlocal finished
        barrier.wait(timeout=3)
        try:
            results[index] = TeamFormService(
                caches[index], client, competition="epl2026",
            ).refresh_all_competitions(now=NOW)
        finally:
            with finished_lock:
                finished += 1
                if finished == worker_count:
                    all_finished.set()

    callers = [threading.Thread(target=refresh, args=(i,)) for i in range(worker_count)]
    for caller in callers:
        caller.start()
    started_at = time.monotonic()
    barrier.wait(timeout=3)
    snapshots = None
    try:
        assert started.wait(timeout=1)
        assert all_finished.wait(timeout=1), "blocked roster calls outlived the provider deadline"
        assert time.monotonic() - started_at < 1
        assert all(result["status"] == "unavailable" for result in results)
        assert all(result["provider_calls"] == 1 for result in results)
        assert peak_active <= team_form.CLUB_FORM_REFRESH_WORKERS
        snapshots = [dict(cache.documents) for cache in caches]
        assert all("epl2026:team_form_teams" not in cache.documents for cache in caches)
    finally:
        release.set()
        for caller in callers:
            caller.join(timeout=2)

    assert all(not caller.is_alive() for caller in callers)
    assert inactive.wait(timeout=2)
    assert [cache.documents for cache in caches] == snapshots
    worker_threads = [
        thread for thread in threading.enumerate()
        if thread.name.startswith("club-form-refresh")
    ]
    assert len(worker_threads) <= team_form.CLUB_FORM_REFRESH_WORKERS
    assert all(
        cache.find_one({"_id": "epl2026:team_form_sync"})["status"] == "stale"
        for cache in caches
    )


def test_blocked_schedule_timeout_preserves_good_forms_and_discards_late_payloads(monkeypatch):
    import threading
    import time

    from src.services import team_form

    monkeypatch.setattr(team_form, "CLUB_FORM_REFRESH_DEADLINE_SECONDS", 0.12)
    release = threading.Event()
    started = threading.Event()
    inactive = threading.Event()
    inactive.set()
    active_lock = threading.Lock()
    active = 0
    old_success = "2026-10-23T10:00:00+00:00"
    roster = [
        {"team": {"id": str(index), "name": f"Team {index}"}}
        for index in range(1, 21)
    ]
    documents = [{
        "_id": "epl2026:team_form_teams", "scope": "all_competitions",
        "provider_namespace": "espn:team-id", "teams": [
            {"team_id": str(index), "name": f"Team {index}"}
            for index in range(1, 21)
        ],
        "observed_at": old_success, "last_successful_at": old_success,
    }, {
        "_id": "epl2026:team_form_sync", "last_successful_at": old_success,
        "observed_at": old_success,
    }]
    sentinel = {"fixture_id": "known-good", "played_at": "2026-10-20T12:00:00Z"}
    documents.extend({
        "_id": f"epl2026:team_form:{index}", "team_id": str(index),
        "matches": [dict(sentinel)], "observed_at": old_success,
        "last_successful_at": old_success, "scope": "all_competitions",
    } for index in range(1, 21))
    cache = MemoryCollection(documents)

    class BlockedScheduleClient:
        provider = "espn"

        def request(self, path, params):
            nonlocal active
            if path == "/teams":
                return {"response": roster}
            assert path == "/fixtures"
            with active_lock:
                active += 1
                inactive.clear()
            started.set()
            try:
                release.wait()
                return {"response": []}
            finally:
                with active_lock:
                    active -= 1
                    if active == 0:
                        inactive.set()

    started_at = time.monotonic()
    try:
        result = TeamFormService(cache, BlockedScheduleClient(), competition="epl2026").refresh_all_competitions(
            now=NOW.replace(hour=13),
        )
        assert started.wait(timeout=1)
        assert time.monotonic() - started_at < 1
        assert result["status"] == "stale"
        assert result["provider_calls"] == 17
        assert result["teams_failed"] == 20
        assert result["observed_at"] == old_success
        assert cache.find_one({"_id": "epl2026:team_form:1"})["matches"] == [sentinel]
        assert cache.find_one({"_id": "epl2026:team_form:1"})["last_successful_at"] == old_success
        snapshot = dict(cache.documents)
    finally:
        release.set()

    assert inactive.wait(timeout=2)
    assert cache.documents == snapshot
    assert cache.find_one({"_id": "epl2026:team_form_teams"})["last_successful_at"] == old_success
    assert cache.find_one({"_id": "epl2026:team_form_sync"})["last_successful_at"] == old_success


def test_verified_conference_league_and_qualifiers_are_competitive_european_form():
    service=TeamFormService(MemoryCollection(),EspnClient({}),competition='epl2026')
    matches=[fixture('conference',competition_id='20296',competition_slug='uefa.europa.conf',competition_name='UEFA Conference League'),
             fixture('qualifier',competition_id='20221',competition_slug='uefa.europa.conf_qual',competition_name='UEFA Conference League Qualifying')]
    rows=service.parse_fixtures('10',{'response':matches},provider='espn',now=NOW)
    assert {row['fixture_id'] for row in rows}=={'conference','qualifier'}
    assert {row['competition_kind'] for row in rows}=={'europe'}
