from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from src.competitions import competition_document_id
from src.services.user_tips import save_shared_tip


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {document["_id"]: document for document in documents}
        self.find_calls = []
        self.update_calls = []
        self.replace_calls = 0

    def find_one(self, query):
        self.find_calls.append(query)
        return self.documents.get(query.get("_id"))

    def update_one(self, query, update, upsert=False):
        self.update_calls.append((query, update, upsert))
        key = query["_id"]
        previous = self.documents.get(key)
        if previous and (
            previous.get("post_match_result", {}).get("status") == "completed"
            or previous.get("post_match_result", {}).get("actual_score")
        ):
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()
        document = previous or {"_id": key}
        if previous is None:
            for path, value in update.get("$setOnInsert", {}).items():
                self._set_path(document, path, value)
        for path, value in update.get("$set", {}).items():
            self._set_path(document, path, value)
        self.documents[key] = document
        return type("Result", (), {
            "matched_count": 0 if previous is None else 1,
            "modified_count": 1,
            "upserted_id": key if previous is None else None,
        })()

    @staticmethod
    def _set_path(document, path, value):
        target = document
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value


def cache_fixture(**overrides):
    kickoff = datetime.now(timezone.utc) + timedelta(hours=1)
    return {
        "id": "fixture-1",
        "home_team": "Team A",
        "away_team": "Team B",
        "home_disp": "A",
        "away_disp": "B",
        "commence_time": kickoff.isoformat(),
        "round": "League phase",
        "is_ko_phase": False,
        "top_tip": "2:1",
        "model_tip": "2:1",
        "max_xp": 4.25,
        "probabilities": {"home": 0.5, "draw": 0.25, "away": 0.25},
        "source_mode": "elo-only",
        "odds": {"home": 2.1, "draw": 3.2, "away": 3.5},
        "raw_match": {"commence_time": kickoff.isoformat(), "round": "League phase"},
        **overrides,
    }


def cache_store(fixture):
    return MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [fixture] if fixture else [],
    }])


def test_unknown_fixture_is_not_inserted_without_a_competition_cached_match():
    archive = MemoryCollection()
    cache = cache_store(None)

    with pytest.raises(HTTPException) as error:
        save_shared_tip(archive, cache, "missing", "1:0", "ucl2026")

    assert error.value.status_code == 404
    assert archive.documents == {}
    assert cache.find_calls == [{"_id": "ucl2026:matches_cache"}]


@pytest.mark.parametrize("overrides", [
    {"completed": True, "actual_score": "1:0"},
    {"actual_score": "1:0"},
])
def test_played_fixtures_are_locked_and_existing_result_is_preserved(overrides):
    fixture = cache_fixture(**overrides)
    archive = MemoryCollection([{
        "_id": "fixture-1",
        "metadata": {"commence_time": fixture["commence_time"]},
        "prediction": {"top_tip": "2:1", "user_tip": None},
        "post_match_result": {"status": "completed", "actual_score": "1:0", "algo_points": 5},
    }])

    with pytest.raises(HTTPException) as error:
        save_shared_tip(archive, cache_store(fixture), "fixture-1", "3:0", "ucl2026")

    assert error.value.status_code == 409
    assert archive.documents["fixture-1"]["post_match_result"] == {
        "status": "completed", "actual_score": "1:0", "algo_points": 5,
    }
    assert archive.update_calls == []


def test_tips_close_at_exactly_five_minutes_before_cached_kickoff():
    fixture = cache_fixture()
    kickoff = datetime.fromisoformat(fixture["commence_time"])
    now = kickoff - timedelta(minutes=5)
    archive = MemoryCollection()

    with pytest.raises(HTTPException) as error:
        save_shared_tip(archive, cache_store(fixture), "fixture-1", "3:0", "ucl2026", now=now)

    assert error.value.status_code == 409
    assert archive.documents == {}


def test_cached_fixture_is_inserted_atomically_and_only_user_tip_is_set():
    fixture = cache_fixture(probabilities={"home": 0.6, "draw": 0.2, "away": 0.2})
    archive = MemoryCollection()
    cache = cache_store(fixture)
    now = datetime.now(timezone.utc)

    result = save_shared_tip(archive, cache, "fixture-1", "03:00", "ucl2026", now=now)
    entry = archive.documents["fixture-1"]

    assert result == {"ok": True, "points_earned": None}
    assert entry["metadata"]["commence_time"] == fixture["commence_time"]
    assert entry["metadata"]["home_team"] == "Team A"
    assert entry["prediction"]["top_tip"] == "2:1"
    assert entry["prediction"]["max_xp"] == 4.25
    assert entry["prediction"]["probabilities"] == {"home": 0.6, "draw": 0.2, "away": 0.2}
    assert entry["prediction"]["user_tip"] == "3:0"
    assert entry["post_match_result"]["status"] == "pending"
    assert cache.find_calls == [{"_id": "ucl2026:matches_cache"}]
    assert archive.replace_calls == 0
    assert len(archive.update_calls) == 1
    assert archive.update_calls[0][1]["$set"] == {"prediction.user_tip": "3:0"}
    assert archive.update_calls[0][2] is True


def test_existing_prediction_and_result_fields_survive_tip_update():
    fixture = cache_fixture()
    existing = {
        "_id": "fixture-1",
        "metadata": {"home_team": "Team A", "commence_time": fixture["commence_time"]},
        "pre_match_snapshot": {"timestamp_recorded": "earlier"},
        "prediction": {"top_tip": "1:1", "model_tip": "1:1", "user_tip": None, "bots": {"broker": {"tip": "2:0"}}},
        "post_match_result": {"status": "pending", "actual_score": None, "algo_points": None},
    }
    archive = MemoryCollection([existing])

    save_shared_tip(archive, cache_store(fixture), "fixture-1", "0:0", "ucl2026")

    saved = archive.documents["fixture-1"]
    assert saved["prediction"]["top_tip"] == "1:1"
    assert saved["prediction"]["bots"] == {"broker": {"tip": "2:0"}}
    assert saved["prediction"]["user_tip"] == "0:0"
    assert saved["post_match_result"] == existing["post_match_result"]
    assert archive.update_calls[0][1]["$set"] == {"prediction.user_tip": "0:0"}


def test_concurrent_archive_insert_keeps_new_forecast_and_sets_only_user_tip():
    class InsertRaceCollection(MemoryCollection):
        def update_one(self, query, update, upsert=False):
            if upsert and query["_id"] not in self.documents:
                self.documents[query["_id"]] = {
                    "_id": query["_id"],
                    "metadata": {"home_team": "Team A", "commence_time": "cached"},
                    "prediction": {"top_tip": "4:0", "user_tip": None},
                    "post_match_result": {"status": "pending", "actual_score": None},
                }
                raise DuplicateKeyError(query["_id"])
            return super().update_one(query, update, upsert)

    fixture = cache_fixture()
    archive = InsertRaceCollection()

    result = save_shared_tip(archive, cache_store(fixture), "fixture-1", "1:0", "ucl2026")

    assert result == {"ok": True, "points_earned": None}
    assert archive.documents["fixture-1"]["prediction"] == {"top_tip": "4:0", "user_tip": "1:0"}
    assert archive.update_calls[-1][1] == {"$set": {"prediction.user_tip": "1:0"}}


def test_archive_id_alias_resolves_provider_cache_fixture_by_trusted_teams_and_date():
    fixture = cache_fixture(id="provider-fixture-99")
    archive = MemoryCollection([{
        "_id": "archive-fixture-1",
        "metadata": {
            "home_team": "Team A", "away_team": "Team B",
            "commence_time": fixture["commence_time"],
        },
        "prediction": {"top_tip": "1:1", "user_tip": None},
        "post_match_result": {"status": "pending", "actual_score": None},
    }])

    save_shared_tip(archive, cache_store(fixture), "archive-fixture-1", "3:0", "ucl2026")

    saved = archive.documents["archive-fixture-1"]
    assert saved["prediction"]["top_tip"] == "1:1"
    assert saved["prediction"]["user_tip"] == "3:0"


def test_archive_id_alias_with_wrong_fixture_date_still_returns_404():
    fixture = cache_fixture(id="provider-fixture-99")
    wrong_date = (datetime.fromisoformat(fixture["commence_time"]) + timedelta(days=1)).isoformat()
    archive = MemoryCollection([{
        "_id": "archive-fixture-1",
        "metadata": {"home_team": "Team A", "away_team": "Team B", "commence_time": wrong_date},
        "prediction": {"top_tip": "1:1", "user_tip": None},
        "post_match_result": {"status": "pending", "actual_score": None},
    }])

    with pytest.raises(HTTPException) as error:
        save_shared_tip(archive, cache_store(fixture), "archive-fixture-1", "3:0", "ucl2026")

    assert error.value.status_code == 404
    assert archive.update_calls == []
