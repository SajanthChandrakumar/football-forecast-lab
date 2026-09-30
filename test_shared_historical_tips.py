from src.services.archive import seed_shared_historical_ucl_tips


class MemoryCollection:
    name = "test_shared_historical_tips"

    def __init__(self, documents):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}

    def find(self):
        return list(self.documents.values())

    def replace_one(self, query, document, upsert=False):
        self.documents[query["_id"]] = dict(document)

    def find_one(self, query):
        return self.documents.get(query["_id"])


TIP_DATA = [
    ("401915452", "2026-09-08", "AEK Athens", "LASK Linz", "2:1", "1:0", 8),
    ("401915426", "2026-09-08", "Club Brugge", "Aston Villa", "1:2", "2:3", 8),
    ("401915451", "2026-09-08", "Real Madrid", "Internazionale", "2:1", "2:1", 10),
    ("401915450", "2026-09-08", "Lille", "Real Betis", "1:1", "2:3", 0),
    ("401915425", "2026-09-08", "FC Porto", "Manchester City", "1:2", "0:2", 6),
    ("401915449", "2026-09-08", "Borussia Dortmund", "Villarreal", "2:0", "3:2", 5),
    ("401915424", "2026-09-09", "Barcelona", "Feyenoord Rotterdam", "3:1", "5:1", 6),
    ("401915448", "2026-09-09", "VfB Stuttgart", "Viking FK", "2:1", "3:1", 6),
    ("401915423", "2026-09-09", "Napoli", "Arsenal", "1:2", "0:1", 8),
    ("401915447", "2026-09-09", "Sporting CP", "Galatasaray", "2:1", "3:1", 6),
    ("401915446", "2026-09-09", "Liverpool", "Atlético Madrid", "2:1", "2:1", 10),
    ("401915445", "2026-09-09", "Paris Saint-Germain", "Slovan Bratislava", "3:0", "6:1", 5),
    ("401915422", "2026-09-10", "PSV Eindhoven", "Shakhtar Donetsk", "2:1", "1:1", 1),
    ("401915444", "2026-09-10", "Fenerbahce", "AS Roma", "1:2", "1:1", 1),
    ("401915440", "2026-09-10", "Slavia Prague", "Lens", "1:1", "2:3", 0),
    ("401915443", "2026-09-10", "Bayern Munich", "Bodo/Glimt", "4:1", "5:0", 5),
    ("401915441", "2026-09-10", "Como", "RB Leipzig", "1:2", "4:1", 0),
    ("401915442", "2026-09-10", "Manchester United", "Sabah FK", "4:0", "4:0", 10),
]


def _archive(rows=TIP_DATA):
    return MemoryCollection([{
        "_id": match_id,
        "metadata": {
            "commence_time": f"{date}T18:45:00+02:00",
            "home_team": home,
            "away_team": away,
            "is_ko_phase": False,
        },
        "prediction": {"top_tip": "1:1"},
        "post_match_result": {"status": "completed", "actual_score": actual, "algo_points": 7},
    } for match_id, date, home, away, _tip, actual, _points in rows])


def test_shared_historical_tips_seed_once_and_use_srf_points():
    from src.math_engine import MathEngine

    collection = _archive()
    first = seed_shared_historical_ucl_tips(collection, MathEngine.calculate_actual_points)

    assert first == {"updated": 18, "skipped": 0, "points_added": 95}
    for match_id, _date, _home, _away, tip, actual, points in TIP_DATA:
        saved = collection.find_one({"_id": match_id})
        assert saved["prediction"]["user_tip"] == tip
        assert saved["prediction"]["user_tip_source"] == "shared_historical"
        assert saved["post_match_result"]["points_earned"] == points
        assert saved["post_match_result"]["actual_score"] == actual
        assert saved["post_match_result"]["algo_points"] == 7

    assert seed_shared_historical_ucl_tips(collection, MathEngine.calculate_actual_points) == {
        "updated": 0, "skipped": 18, "points_added": 0,
    }


def test_shared_historical_seed_never_overwrites_existing_tip_or_mismatched_match():
    from src.math_engine import MathEngine

    collection = _archive(TIP_DATA[:2])
    existing = collection.find_one({"_id": "401915452"})
    existing["prediction"]["user_tip"] = "0:0"
    collection.replace_one({"_id": "401915452"}, existing)
    wrong = collection.find_one({"_id": "401915426"})
    wrong["post_match_result"]["actual_score"] = "0:0"
    collection.replace_one({"_id": "401915426"}, wrong)

    result = seed_shared_historical_ucl_tips(collection, MathEngine.calculate_actual_points)

    assert result == {"updated": 0, "skipped": 18, "points_added": 0}
    assert collection.find_one({"_id": "401915452"})["prediction"]["user_tip"] == "0:0"
    assert "user_tip" not in collection.find_one({"_id": "401915426"})["prediction"]
