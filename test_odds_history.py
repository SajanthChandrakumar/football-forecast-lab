from datetime import datetime, timedelta, timezone

import pytest

from src.competitions import competition_document_id
from src.services.odds_history import get_odds_history


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}
        self.queries = []

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def find(self, query=None):
        self.queries.append(query)
        def matches(document, key, expected):
            return document.get(key) in expected["$in"] if isinstance(expected, dict) and "$in" in expected else document.get(key) == expected
        return [
            document for document in self.documents.values()
            if all(matches(document, key, value) for key, value in (query or {}).items())
        ]


def test_history_returns_only_valid_pre_kickoff_bookmaker_observations_and_probability_change():
    kickoff = datetime(2026, 10, 1, 19, tzinfo=timezone.utc)
    documents = [
        {
            "_id": competition_document_id("ucl2026", "matches_cache"),
            "data": [{"id": "fixture-1", "commence_time": kickoff.isoformat()}],
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t24h:1",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t24h",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(),
            "odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t15m:2",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t15m",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
            "odds": {"home": 1.8, "draw": 3.8, "away": 4.5},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t30m:duplicate",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t30m",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
            "odds": {"home": 1.9, "draw": 3.6, "away": 4.3},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t75m:invalid",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t75m",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(minutes=75)).isoformat(),
            "odds": {"home": float("nan"), "draw": 3.6, "away": 4.3},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t6h:model",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t6h",
            "source": "elo_model", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=6)).isoformat(),
            "odds": {"home": 1.8, "draw": 3.8, "away": 4.5},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t15m:3",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t15m",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff + timedelta(minutes=1)).isoformat(),
            "odds": {"home": 1.7, "draw": 3.9, "away": 4.8},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-1:t30m:4",
            "competition": "ucl2026", "event_id": "fixture-1", "bucket": "t30m",
            "source": "failed-source", "status": "failed",
            "observed_at": (kickoff - timedelta(minutes=30)).isoformat(),
            "odds": {"home": 1.01, "draw": 1.02, "away": 1.03},
        },
    ]
    cache = MemoryCollection(documents)

    result = get_odds_history(cache, "fixture-1", competition="ucl2026")

    assert result["status"] == "available"
    assert [item["bucket"] for item in result["observations"]] == ["t24h", "t15m"]
    assert result["observations"][0]["probabilities"] == pytest.approx({
        "home": 14 / 29, "draw": 8 / 29, "away": 7 / 29,
    })
    assert result["probability_change_pp"] == pytest.approx({
        "home": 5.094924, "draw": -2.305308, "away": -2.789616,
    })
    query = cache.queries[-1]
    assert query["competition"] == "ucl2026"
    assert query["event_id"] == "fixture-1"


def test_history_is_unavailable_without_a_known_kickoff():
    cache = MemoryCollection([{
        "_id": "ucl2026:odds_snapshot:fixture-2:t24h:1",
        "competition": "ucl2026", "event_id": "fixture-2", "bucket": "t24h",
        "source": "odds_api", "status": "fresh",
        "observed_at": "2026-09-30T19:00:00+00:00",
        "odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
    }])

    result = get_odds_history(cache, "fixture-2", competition="ucl2026")

    assert result["status"] == "unavailable"
    assert result["observations"] == []
    assert cache.queries == []


def test_known_kickoff_with_no_usable_snapshot_is_unavailable():
    kickoff = datetime(2026, 10, 1, 19, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {
            "_id": competition_document_id("ucl2026", "matches_cache"),
            "data": [{"id": "fixture-3", "commence_time": kickoff.isoformat()}],
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-3:t24h:1",
            "competition": "ucl2026", "event_id": "fixture-3", "bucket": "t24h",
            "source": "odds_api", "status": "unavailable",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(), "odds": {},
        },
    ])

    result = get_odds_history(cache, "fixture-3", competition="ucl2026")

    assert result["status"] == "unavailable"
    assert result["observations"] == []


def test_one_valid_snapshot_is_available_without_a_trend():
    kickoff = datetime(2026, 10, 1, 19, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {
            "_id": competition_document_id("ucl2026", "matches_cache"),
            "data": [{"id": "fixture-4", "commence_time": kickoff.isoformat()}],
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-4:t6h:1",
            "competition": "ucl2026", "event_id": "fixture-4", "bucket": "t6h",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=6)).isoformat(),
            "odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
        },
    ])

    result = get_odds_history(cache, "fixture-4", competition="ucl2026")

    assert result["status"] == "available"
    assert len(result["observations"]) == 1
    assert "probability_change_pp" not in result


def test_archived_kickoff_is_used_to_exclude_observations_after_start():
    kickoff = datetime(2026, 10, 1, 19, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {
            "_id": "ucl2026:odds_snapshot:fixture-5:t24h:1",
            "competition": "ucl2026", "event_id": "fixture-5", "bucket": "t24h",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(),
            "odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
        },
        {
            "_id": "ucl2026:odds_snapshot:fixture-5:t15m:2",
            "competition": "ucl2026", "event_id": "fixture-5", "bucket": "t15m",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff + timedelta(minutes=2)).isoformat(),
            "odds": {"home": 1.8, "draw": 3.8, "away": 4.5},
        },
    ])
    archive = MemoryCollection([{
        "_id": "fixture-5", "competition": "ucl2026",
        "metadata": {"commence_time": kickoff.isoformat()},
    }])

    result = get_odds_history(cache, "fixture-5", competition="ucl2026", archive_collection=archive)

    assert [point["bucket"] for point in result["observations"]] == ["t24h"]


def test_archive_alias_resolves_snapshot_event_id_without_leaking_opposite_fixture():
    kickoff = datetime(2026, 10, 1, 19, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {
            "_id": competition_document_id("ucl2026", "matches_cache"),
            "data": [
                {
                    "id": "provider-home-away",
                    "home_team": "Alpha FC",
                    "away_team": "Beta FC",
                    "commence_time": kickoff.isoformat(),
                },
                {
                    "id": "provider-away-home",
                    "home_team": "Beta FC",
                    "away_team": "Alpha FC",
                    "commence_time": kickoff.isoformat(),
                },
            ],
        },
        {
            "_id": "ucl2026:odds_snapshot:provider-home-away:t24h:1",
            "competition": "ucl2026", "event_id": "provider-home-away", "bucket": "t24h",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(),
            "odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
        },
        {
            "_id": "ucl2026:odds_snapshot:provider-away-home:t24h:1",
            "competition": "ucl2026", "event_id": "provider-away-home", "bucket": "t24h",
            "source": "odds_api", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(),
            "odds": {"home": 1.2, "draw": 4.0, "away": 8.0},
        },
    ])
    archive = MemoryCollection([{
        "_id": "archive-alias",
        "competition": "ucl2026",
        "metadata": {
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "commence_time": kickoff.isoformat(),
        },
    }])

    result = get_odds_history(cache, "archive-alias", competition="ucl2026", archive_collection=archive)

    assert result["match_id"] == "archive-alias"
    assert [point["odds"]["home"] for point in result["observations"]] == [2.0]
    assert cache.queries[-1]["event_id"] == "provider-home-away"
