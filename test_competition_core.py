import time

import pytest
from fastapi import HTTPException

from src.competitions import (
    DEFAULT_COMPETITION_ID,
    COMPETITIONS,
    competition_document_id,
    get_competition,
    list_competitions,
    find_competition_document,
    require_competition,
)
from src.services import archive
from src.routes.custom_bot import init_router as custom_bot_router
from src.routes.matches import init_router as matches_router
from src.routes.predict import effective_is_ko


class MemoryCollection:
    def __init__(self, name, documents=()):
        self.name = name
        self.documents = {doc["_id"]: dict(doc) for doc in documents}

    def find(self):
        return list(self.documents.values())

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def replace_one(self, query, document, upsert=False):
        self.documents[document["_id"]] = dict(document)


class NoopLimiter:
    def limit(self, *_args, **_kwargs):
        return lambda function: function


class MinimalMathEngine:
    team_forms = {}

    def reload_elo_data(self, **kwargs):
        return None


def test_competition_registry_contains_the_supported_competitions():
    assert set(COMPETITIONS) == {"wc2026", "ucl2026", "epl2026"}
    assert COMPETITIONS["wc2026"].display_name == "FIFA World Cup 2026"
    assert COMPETITIONS["wc2026"].espn_slug == "fifa.world"
    assert COMPETITIONS["wc2026"].odds_api_sport_key == "soccer_fifa_world_cup"
    assert COMPETITIONS["ucl2026"].display_name == "UEFA Champions League 2026/27"
    assert COMPETITIONS["ucl2026"].espn_slug == "uefa.champions"
    assert COMPETITIONS["ucl2026"].odds_api_sport_key == "soccer_uefa_champs_league"


def test_missing_competition_defaults_to_world_cup_and_unknown_is_rejected():
    assert get_competition(None).id == DEFAULT_COMPETITION_ID
    assert get_competition("").id == DEFAULT_COMPETITION_ID
    with pytest.raises(ValueError, match="Unknown competition"):
        get_competition("not-a-competition")
    with pytest.raises(ValueError, match="Unknown competition"):
        get_competition("UCL2026")


def test_require_competition_exposes_unknown_ids_as_http_400():
    with pytest.raises(HTTPException) as exc_info:
        require_competition("bad")
    assert exc_info.value.status_code == 400


def test_wc_state_lookup_prefers_scoped_document_and_falls_back_to_legacy():
    cache = MemoryCollection(
        "cache",
        [
            {"_id": "elo_ratings", "rows": [{"team_name": "legacy"}]},
            {"_id": "wc2026:elo_ratings", "rows": [{"team_name": "scoped"}]},
        ],
    )
    assert find_competition_document(cache, "wc2026", "elo_ratings")["rows"][0]["team_name"] == "scoped"

    del cache.documents["wc2026:elo_ratings"]
    assert find_competition_document(cache, "wc2026", "elo_ratings")["rows"][0]["team_name"] == "legacy"


def test_competition_list_is_safe_api_metadata():
    listed = list_competitions()
    assert {item["id"] for item in listed} == {"wc2026", "ucl2026", "epl2026"}
    assert all("archive_collection" in item for item in listed)
    assert all("cache_collection" in item for item in listed)
    assert all("custom_bot_collection" in item for item in listed)


def test_archive_ram_cache_is_isolated_by_collection():
    wc = MemoryCollection("archive")
    ucl = MemoryCollection("archive_ucl2026")
    archive._archive_mem.clear()
    archive._archive_mem_ts.clear()
    wc.documents["wc-match"] = {"_id": "wc-match", "competition": "wc2026"}
    ucl.documents["ucl-match"] = {"_id": "ucl-match", "competition": "ucl2026"}

    assert set(archive.load_archive_from_db(wc)) == {"wc-match"}
    assert set(archive.load_archive_from_db(ucl)) == {"ucl-match"}


def test_scoped_documents_cannot_collide_between_competitions():
    assert competition_document_id("wc2026", "matches_cache") == "wc2026:matches_cache"
    assert competition_document_id("ucl2026", "matches_cache") == "ucl2026:matches_cache"
    assert competition_document_id("wc2026", "matches_cache") != competition_document_id(
        "ucl2026", "matches_cache"
    )


def test_competition_parser_http_boundary_returns_400_for_unknown_ids():
    with pytest.raises(ValueError):
        get_competition("bad")
    error = HTTPException(status_code=400, detail="Unknown competition: bad")
    assert error.status_code == 400


def test_matches_route_defaults_to_wc_collection_and_rejects_unknown_ids():
    wc = MemoryCollection(
        "archive",
        [{"_id": "wc2026:matches_cache", "timestamp": time.time(), "data": []}],
    )
    ucl = MemoryCollection(
        "archive_ucl2026",
        [{"_id": "ucl2026:matches_cache", "timestamp": time.time(), "data": []}],
    )
    router = matches_router(
        MinimalMathEngine(),
        object(),
        {"wc2026": wc, "ucl2026": ucl},
        {"wc2026": wc, "ucl2026": ucl},
    )
    endpoint = router.routes[0].endpoint
    assert endpoint() == []
    assert endpoint(competition="ucl2026") == []
    with pytest.raises(HTTPException) as exc_info:
        endpoint(competition="bad")
    assert exc_info.value.status_code == 400


def test_custom_bot_state_is_scoped_and_wc_legacy_state_remains_readable():
    wc = MemoryCollection("custom_bot", [{"_id": "default", "name": "WC", "params": {}}])
    ucl = MemoryCollection("custom_bot_ucl2026")
    router = custom_bot_router(
        MinimalMathEngine(),
        {"wc2026": wc, "ucl2026": MemoryCollection("archive_ucl2026")},
        {"wc2026": wc, "ucl2026": ucl},
        NoopLimiter(),
    )
    get_endpoint = router.routes[1].endpoint
    save_endpoint = router.routes[2].endpoint
    assert get_endpoint()["name"] == "WC"
    assert get_endpoint(competition="ucl2026")["exists"] is False
    save_endpoint(None, {"name": "UCL", "params": {}}, competition="ucl2026")
    assert ucl.documents["ucl2026:default"]["competition"] == "ucl2026"
    with pytest.raises(HTTPException) as exc_info:
        get_endpoint(competition="bad")
    assert exc_info.value.status_code == 400


def test_prediction_ko_policy_ignores_ucl_client_flag_but_keeps_wc_legacy_fallback():
    assert effective_is_ko("ucl2026", {"is_ko": True}, {}) is False
    assert effective_is_ko(
        "ucl2026",
        {"is_ko": False},
        {"metadata": {"extra_time_eligible": True}},
    ) is True
    assert effective_is_ko("wc2026", {"is_ko": True}, {}) is True
