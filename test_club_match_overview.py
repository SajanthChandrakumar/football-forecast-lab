from copy import deepcopy
from datetime import datetime, timezone
import json

from src.routes import matches as matches_module
from src.routes.matches import init_router
from src.services.club_views import game_view_id, overview_view_id, build_match_views


NOW = datetime.now(timezone.utc).isoformat()
_OVERVIEW_PROJECTION = {
    "data.home_form": 0,
    "data.away_form": 0,
    "data.match_intelligence": 0,
    "data.bookmakers": 0,
    "data.raw_match.bookmakers": 0,
    "data.regulation_matrix": 0,
}


class MongoAwareCollection:
    def __init__(self, documents=()):
        self.documents = {document["_id"]: deepcopy(document) for document in documents}
        self.find_one_calls = []
        self.find_calls = []
        self.writes = []

    def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        document = self.documents.get(query.get("_id"))
        return _project(document, projection) if document is not None else None

    def find(self, query=None, projection=None):
        self.find_calls.append((deepcopy(query), deepcopy(projection)))
        query = query or {}
        documents = list(self.documents.values())
        if "post_match_result.status" in query:
            documents = [
                document for document in documents
                if _path_value(document, "post_match_result.status") == query["post_match_result.status"]
            ]
        return [_project(document, projection) for document in documents]

    def insert_one(self, document):
        self.writes.append(("insert_one", deepcopy(document)))

    def update_one(self, query, update, **kwargs):
        self.writes.append(("update_one", deepcopy(query), deepcopy(update), deepcopy(kwargs)))


def _path_value(source, path):
    value = source
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        elif isinstance(value, list) and isinstance(target.get(key), list):
            for index, item in enumerate(value):
                if index >= len(target[key]):
                    target[key].append(item)
                elif isinstance(item, dict) and isinstance(target[key][index], dict):
                    _merge(target[key][index], item)
                else:
                    target[key][index] = item
        else:
            target[key] = value


def _project_path(source, parts):
    if isinstance(source, list):
        return [value for item in source if (value := _project_path(item, parts)) is not None]
    if not isinstance(source, dict) or parts[0] not in source:
        return None
    key = parts[0]
    if len(parts) == 1:
        return {key: deepcopy(source[key])}
    nested = _project_path(source[key], parts[1:])
    return {key: nested} if nested is not None else None


def _unset_path(source, parts):
    if isinstance(source, list):
        for item in source:
            _unset_path(item, parts)
    elif isinstance(source, dict):
        if len(parts) == 1:
            source.pop(parts[0], None)
        elif parts[0] in source:
            _unset_path(source[parts[0]], parts[1:])


def _project(document, projection):
    if not projection:
        return deepcopy(document)
    fields = {key: value for key, value in projection.items() if key != "_id"}
    if fields and all(value == 0 for value in fields.values()):
        result = deepcopy(document)
        for path in fields:
            _unset_path(result, path.split("."))
        if projection.get("_id", 1) == 0:
            result.pop("_id", None)
        return result
    result = {"_id": deepcopy(document["_id"])} if projection.get("_id", 1) else {}
    for path, include in fields.items():
        if include:
            projected = _project_path(document, path.split("."))
            if projected:
                _merge(result, projected)
    return result


def _ready_match(match_id, home, away, *, completed=False):
    matrix = {"0": {"0": 0.4, "1": 0.2}, "1": {"0": 0.3, "1": 0.1}}
    return {
        "id": match_id,
        "home_team": home,
        "away_team": away,
        "home_logo": f"https://img.example/{home}.png",
        "away_logo": f"https://img.example/{away}.png",
        "home_team_id": f"{home}-id",
        "away_team_id": f"{away}-id",
        "commence_time": "2026-11-01T19:00:00Z",
        "round": "Matchday 3",
        "completed": completed,
        "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
        "odds_status": "fresh",
        "odds_observed_at": NOW,
        "odds_provenance": {"source": "odds_api", "observed_at": NOW},
        "home_form": {"form": ["W", "D"], "extra": "cached"},
        "away_form": {"form": ["L", "W"], "extra": "cached"},
        "match_intelligence": {"lineups": {"home": {"starters": ["cached"]}}},
        "matrix": matrix,
        "score_matrix": matrix,
        "regulation_matrix": {"0:0": 0.4, "1:0": 0.6},
        "bookmakers": [{"title": "Bookmaker", "markets": [{"key": "h2h"}]}],
        "raw_match": {
            "id": match_id,
            "commence_time": "2026-11-01T19:00:00Z",
            "round": "Matchday 3",
            "home_logo": f"https://img.example/{home}.png",
            "away_logo": f"https://img.example/{away}.png",
            "bookmakers": [{"title": "Raw bookmaker", "history": [1, 2, 3]}],
        },
        "model_tip": "1:0",
        "top_tip": "1:0",
        "probabilities": {"home": 0.5, "draw": 0.25, "away": 0.25},
        "xg_home": 1.4,
        "xg_away": 0.9,
        "max_xp": 2.5,
        "source_mode": "odds+elo",
        "status": "fresh",
        "source_status": "fresh",
        "source": "club-model",
        "observed_at": NOW,
        "model_version": "prediction-club-v2",
        "input_provenance": {
            "odds": {"status": "fresh", "observed_at": NOW},
            "elo": {"status": "fresh", "observed_at": NOW},
        },
        "context": {"stage": "league", "round": "Matchday 3"},
        "match_context": {"stage": "league", "round": "Matchday 3"},
    }


def _endpoint(cache, archive, *, competition="epl2026", team_form_service=None):
    router = init_router(None, object(), {competition: cache}, {competition: archive},
                         team_form_service=team_form_service)
    return next(route.endpoint for route in router.routes if route.path == "/api/matches")


def _seed_prepared_views(cache, archive, competition):
    source = cache.documents[f"{competition}:matches_cache"].get("data") or []
    archived = {
        row["_id"]: {key: value for key, value in row.items() if key != "_id"}
        for row in archive.documents.values()
    }
    bundle = build_match_views(source, archived, competition)
    cache.documents[overview_view_id(competition)] = {
        "_id": overview_view_id(competition), "competition": competition,
        "generation": 1, "input_revision": 0, "published_revision": 0,
        "active_writers": {}, "overview": bundle["overview"],
        "aliases": bundle["aliases"], "archive_ids": bundle["archive_ids"],
        "match_versions": {key: row["view_version"] for key, row in bundle["games"].items()},
        "source_hash": bundle["source_hash"],
    }
    for match_id, row in bundle["games"].items():
        cache.documents[game_view_id(competition, match_id)] = {
            "_id": game_view_id(competition, match_id), "kind": "club_game_view",
            "competition": competition, "match_id": match_id, **row,
        }


def test_pl_overview_projects_and_strips_details_while_full_response_keeps_them(monkeypatch):
    cache = MongoAwareCollection([{
        "_id": "epl2026:matches_cache",
        "data": [
            _ready_match("pl-1", "Arsenal", "Chelsea"),
            _ready_match("pl-2", "Liverpool", "Everton"),
        ],
    }])
    archive = MongoAwareCollection()
    form_calls = []
    intelligence_calls = []

    class FormService:
        def cached_forms_for_matches(self, matches):
            form_calls.append(len(matches))
            return [
                {**match, "home_form": {"form": ["W"]}, "away_form": {"form": ["D"]}}
                for match in matches
            ]

    def attach_intelligence(matches, *_args):
        intelligence_calls.append(len(matches))
        return [{**match, "match_intelligence": {"attached": True}} for match in matches]

    monkeypatch.setattr(matches_module, "attach_cached_match_intelligence", attach_intelligence)
    endpoint = _endpoint(cache, archive, team_form_service=FormService())
    _seed_prepared_views(cache, archive, "epl2026")

    full = endpoint(competition="epl2026")
    overview = endpoint(competition="epl2026", overview=True)
    forced_overview = endpoint(competition="epl2026", overview=True, force=True)

    assert [match["id"] for match in full] == ["pl-1", "pl-2"]
    assert full[0]["home_form"] == {"form": ["W"]}
    assert full[0]["match_intelligence"] == {"attached": True}
    assert full[0]["matrix"] and full[0]["score_matrix"] and full[0]["regulation_matrix"]
    assert full[0]["bookmakers"] and full[0]["raw_match"]["bookmakers"]
    assert [match["id"] for match in overview] == ["pl-1", "pl-2"]
    assert [match["id"] for match in forced_overview] == ["pl-1", "pl-2"]
    for row in overview + forced_overview:
        assert row["detail_level"] == "overview"
        assert row["model_tip"] == row["top_tip"] == "1:0"
        assert row["probabilities"] == {"home": 0.5, "draw": 0.25, "away": 0.25}
        assert row["source_status"] == "fresh"
        assert row["input_provenance"]["odds"]["status"] == "fresh"
        assert row["home_logo"] and row["away_logo"]
        assert row["commence_time"] == "2026-11-01T19:00:00Z"
        assert row["round"] == "Matchday 3"
        assert row["match_context"] == {"stage": "league", "round": "Matchday 3"}
        assert "home_form" not in row and "away_form" not in row
        assert "match_intelligence" not in row and "bookmakers" not in row
        assert "matrix" not in row and "score_matrix" not in row and "regulation_matrix" not in row
        assert "bookmakers" not in row["raw_match"]

    assert cache.find_one_calls == [
        ({"_id": "epl2026:matches_cache"}, None),
        ({"_id": overview_view_id("epl2026")}, {
            "overview": 1, "published_revision": 1, "input_revision": 1, "active_writers": 1,
        }),
        ({"_id": overview_view_id("epl2026")}, {
            "overview": 1, "published_revision": 1, "input_revision": 1, "active_writers": 1,
        }),
    ]
    assert form_calls == [2]
    assert intelligence_calls == [2]
    assert cache.writes == archive.writes == []


def test_ucl_overview_keeps_completed_archive_tip_and_wm_ignores_overview(monkeypatch):
    cache = MongoAwareCollection([{
        "_id": "ucl2026:matches_cache",
        "data": [_ready_match("ucl-done", "Bayern Munich", "Arsenal", completed=True)],
    }])
    archive = MongoAwareCollection([{
        "_id": "ucl-done",
        "prediction": {"top_tip": "0:1", "model_tip": "0:1", "max_xp": 3.0},
        "pre_match_snapshot": {"source_mode": "archived", "provenance": {"source": "archive"}},
        "post_match_result": {"status": "completed", "actual_score": "1:2"},
        "metadata": {"competition": "ucl2026"},
    }])
    monkeypatch.setattr(matches_module, "attach_cached_match_intelligence", lambda rows, *_args: rows)
    ucl_endpoint = _endpoint(cache, archive, competition="ucl2026")
    _seed_prepared_views(cache, archive, "ucl2026")

    ucl = ucl_endpoint(competition="ucl2026", overview=True, force=True)

    assert ucl[0]["top_tip"] == ucl[0]["model_tip"] == "0:1"
    assert ucl[0]["completed"] is True
    assert ucl[0]["post_match_result"] == {"status": "completed", "actual_score": "1:2"}
    assert ucl[0]["source_mode"] == "archived"
    assert ucl[0]["archived_prediction"]["top_tip"] == "0:1"
    assert ucl[0]["probabilities"] is None
    assert "matrix" not in ucl[0] and "score_matrix" not in ucl[0]
    assert cache.find_one_calls == [({"_id": overview_view_id("ucl2026")}, {
        "overview": 1, "published_revision": 1, "input_revision": 1, "active_writers": 1,
    })]
    assert archive.find_calls == []

    world_cup_cache = MongoAwareCollection([{
        "_id": "wc2026:matches_cache",
        "data": [_ready_match("wc-1", "Switzerland", "Brazil")],
    }])
    monkeypatch.setattr(matches_module, "_enrich_edge", lambda rows, *_args: rows)
    monkeypatch.setattr(matches_module, "load_archive_from_db", lambda *_args, **_kwargs: {})
    world_cup_endpoint = _endpoint(world_cup_cache, MongoAwareCollection(), competition="wc2026")

    world_cup = world_cup_endpoint(competition="wc2026", overview=True)

    assert world_cup[0]["matrix"] and world_cup[0]["score_matrix"] and world_cup[0]["regulation_matrix"]
    assert world_cup[0]["bookmakers"] and world_cup[0]["raw_match"]["bookmakers"]
    assert world_cup_cache.find_one_calls == [({"_id": "wc2026:matches_cache"}, None)]


def test_missing_club_overview_cache_stays_unavailable_without_writes():
    cache = MongoAwareCollection()
    archive = MongoAwareCollection()
    endpoint = _endpoint(cache, archive)

    result = endpoint(competition="epl2026", overview=True, force=True)

    assert result.status_code == 202
    assert json.loads(result.body) == {
        "status": "processing", "data": [], "source": "club_views",
        "reason": "preparing", "retry_after": 2,
    }
    assert cache.find_one_calls == [({"_id": overview_view_id("epl2026")}, {
        "overview": 1, "published_revision": 1, "input_revision": 1, "active_writers": 1,
    })]
    assert cache.writes == archive.writes == []


def test_overview_presentation_does_not_mutate_nested_cached_input():
    cached = [_ready_match("pl-1", "Arsenal", "Chelsea")]
    before = deepcopy(cached)
    result = matches_module._present_cached_matches(
        cached, None, None, "epl2026", MongoAwareCollection(), MongoAwareCollection(),
        overview=True,
    )
    assert "bookmakers" not in result[0]["raw_match"]
    assert cached == before
