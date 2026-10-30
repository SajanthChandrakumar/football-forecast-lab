from copy import deepcopy

from fastapi import HTTPException

from src.competitions import competition_document_id
from src.routes.matches import init_router
from src.services.club_views import (
    build_match_views,
    club_view_input_write,
    game_view_id,
    load_archive_match,
    overview_view_id,
    prepare_club_views,
    publish_club_views,
)


def _path(document, dotted):
    value = document
    for key in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _set_path(document, dotted, value):
    parts = dotted.split(".")
    for key in parts[:-1]:
        document = document.setdefault(key, {})
    document[parts[-1]] = deepcopy(value)


def _unset_path(document, dotted):
    parts = dotted.split(".")
    for key in parts[:-1]:
        document = document.get(key, {}) if isinstance(document, dict) else {}
    if isinstance(document, dict):
        document.pop(parts[-1], None)


class ViewCollection:
    """Small Mongo-shaped collection that exercises projections and CAS filters."""

    def __init__(self, documents=()):
        self.documents = {row["_id"]: deepcopy(row) for row in documents}
        self.find_one_calls = []
        self.find_calls = []
        self.writes = []
        self.fail_overview_publish = False

    def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        row = self.documents.get(query.get("_id"))
        if row is None or not _matches(row, query):
            return None
        if not projection:
            return deepcopy(row)
        return _project(row, projection)

    def find(self, query=None, projection=None):
        self.find_calls.append((deepcopy(query), deepcopy(projection)))
        query = query or {}
        return [
            _project(row, projection) for row in self.documents.values()
            if _matches(row, query)
        ]

    def update_one(self, query, update, upsert=False):
        self.writes.append(("update_one", deepcopy(query), deepcopy(update), upsert))
        paths = [path for operator, values in update.items() if operator.startswith("$")
                 for path in values]
        for index, path in enumerate(paths):
            if any(other == path or other.startswith(path + ".") or path.startswith(other + ".")
                   for other in paths[index + 1:]):
                raise AssertionError(f"conflicting Mongo update paths: {paths}")
        key = query.get("_id")
        if self.fail_overview_publish and "overview" in update.get("$set", {}):
            return type("Result", (), {"matched_count": 0, "upserted_id": None})()
        row = self.documents.get(key)
        inserted = row is None
        if inserted and upsert:
            row = {"_id": key}
            self.documents[key] = row
        if row is None or not _matches(row, query):
            if inserted:
                self.documents.pop(key, None)
            return type("Result", (), {"matched_count": 0, "upserted_id": None})()
        for path, value in update.get("$setOnInsert", {}).items() if inserted else ():
            _set_path(row, path, value)
        for path, value in update.get("$set", {}).items():
            _set_path(row, path, value)
        for path, value in update.get("$inc", {}).items():
            _set_path(row, path, (_path(row, path) or 0) + value)
        for path in update.get("$unset", {}):
            _unset_path(row, path)
        return type("Result", (), {"matched_count": 0 if inserted else 1, "upserted_id": key if inserted else None})()

    def replace_one(self, query, replacement, upsert=False):
        self.writes.append(("replace_one", deepcopy(query), deepcopy(replacement), upsert))
        key = query.get("_id")
        row = self.documents.get(key)
        if row is not None and _matches(row, query):
            self.documents[key] = deepcopy(replacement)
            return type("Result", (), {"matched_count": 1, "upserted_id": None})()
        if row is None and upsert:
            self.documents[key] = deepcopy(replacement)
            return type("Result", (), {"matched_count": 0, "upserted_id": key})()
        return type("Result", (), {"matched_count": 0, "upserted_id": None})()

    def bulk_write(self, operations, ordered=True):
        for operation in operations:
            self.replace_one(operation._filter, operation._doc, upsert=operation._upsert)
        return type("Result", (), {"matched_count": len(operations), "upserted_count": 0})()

    def delete_many(self, query):
        self.writes.append(("delete_many", deepcopy(query)))
        removed = [key for key, row in self.documents.items() if _matches(row, query)]
        for key in removed:
            del self.documents[key]
        return type("Result", (), {"deleted_count": len(removed)})()


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, part) for part in expected):
                return False
            continue
        actual = _path(document, key)
        if isinstance(expected, dict):
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$regex" in expected and (
                not isinstance(actual, str)
                or __import__("re").search(expected["$regex"], actual) is None
            ):
                return False
            if "$exists" in expected and (actual is not None) != expected["$exists"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
        elif actual != expected:
            return False
    return True


def _project(document, projection):
    if not projection:
        return deepcopy(document)
    included = [key for key, value in projection.items() if value and key != "_id"]
    if included:
        result = {"_id": document["_id"]}
        for key in included:
            value = _path(document, key)
            if value is not None:
                _set_path(result, key, value)
        return result
    if projection.get("_id"):
        return {"_id": document["_id"]}
    result = deepcopy(document)
    for key, value in projection.items():
        if not value:
            parts = key.split(".")
            parent = result
            for part in parts[:-1]:
                parent = parent.get(part, {}) if isinstance(parent, dict) else {}
            if isinstance(parent, dict):
                parent.pop(parts[-1], None)
    return result


def _fixture(match_id="game-1", *, completed=False, user_tip=None):
    matrix = {"0": {"0": 0.4, "1": 0.2}, "1": {"0": 0.3, "1": 0.1}}
    return {
        "id": match_id, "home_team": "Arsenal", "away_team": "Chelsea",
        "commence_time": "2026-11-01T19:00:00Z", "round": "Matchday 3",
        "completed": completed, "actual_score": "1:0" if completed else None,
        "home_logo": "home.png", "away_logo": "away.png", "user_tip": user_tip,
        "model_tip": "1:0", "top_tip": "1:0", "max_xp": 2.5,
        "probabilities": {"home": 0.5, "draw": 0.25, "away": 0.25},
        "xg_home": 1.4, "xg_away": 0.9, "source_mode": "odds+elo",
        "status": "fresh", "source_status": "fresh", "observed_at": "2026-10-28T12:00:00Z",
        "model_version": "prediction-club-v2",
        "input_provenance": {"odds": {"status": "fresh", "observed_at": "2026-10-28T12:00:00Z"}},
        "matrix": matrix, "score_matrix": matrix, "regulation_matrix": matrix,
        "home_form": {"form": ["W"]}, "away_form": {"form": ["D"]},
        "match_intelligence": {"lineups": {"home": {"starters": ["cached"]}}},
        "bookmakers": [{"title": "large"}],
        "raw_match": {"id": match_id, "commence_time": "2026-11-01T19:00:00Z", "bookmakers": [{"history": [1, 2]}]},
    }


def _endpoint(cache, archive, *, competition="epl2026"):
    router = init_router(None, object(), {competition: cache}, {competition: archive})
    return {route.path: route.endpoint for route in router.routes}


def test_prepared_match_views_are_compact_and_share_a_content_version():
    fixture = _fixture(completed=True)
    archive = {
        "prediction": {
            "top_tip": "0:1", "model_tip": "0:1", "user_tip": "1:1",
            "frozen_at": "2026-10-31T18:00:00Z", "matrix": {"huge": True},
            "probabilities": {"home": 0.2, "draw": 0.3, "away": 0.5},
            "evaluation_forecast": {"matrix": {"huge": True}},
        },
        "pre_match_snapshot": {
            "source_mode": "frozen", "observed_at": "2026-10-31T18:00:00Z",
            "max_xp": 3.1, "xg_home": 1.2, "xg_away": 0.8,
            "model_version": "archived-model", "input_provenance": {"odds": {"source": "archive"}},
        },
        "post_match_result": {"status": "completed", "actual_score": "1:0"},
    }

    built = build_match_views([fixture], {"game-1": archive}, "epl2026")
    overview = built["overview"][0]
    game = built["games"]["game-1"]

    assert overview["detail_level"] == "overview"
    assert overview["top_tip"] == "0:1"  # completed forecast is frozen
    assert overview["user_tip"] == "1:1"
    for key in ("matrix", "score_matrix", "regulation_matrix", "home_form", "away_form", "match_intelligence", "bookmakers"):
        assert key not in overview
    assert game["core"]["detail_level"] == "core"
    assert game["core"]["top_tip"] == "0:1"
    assert game["core"]["archived_prediction"]["top_tip"] == "0:1"
    assert game["core"]["archived_prediction"]["max_xp"] == 3.1
    assert game["core"]["archived_prediction"]["model_version"] == "archived-model"
    assert "evaluation_forecast" not in game["core"]["archived_prediction"]
    assert "matrix" not in game["core"]["archived_prediction"]
    assert game["analysis"]["matrix"]
    assert game["view_version"] == game["core"]["view_version"] == game["analysis"]["view_version"]


def test_match_view_version_hashes_the_prepared_core_and_prediction_inputs():
    first = build_match_views([_fixture()], {}, "epl2026")["games"]["game-1"]["view_version"]
    same_inputs_new_source_time = _fixture()
    same_inputs_new_source_time["observed_at"] = "2026-10-28T13:00:00Z"
    same_time_version = build_match_views([same_inputs_new_source_time], {}, "epl2026")["games"]["game-1"]["view_version"]
    changed_prediction = _fixture()
    changed_prediction["probabilities"] = {"home": 0.6, "draw": 0.2, "away": 0.2}
    changed_version = build_match_views([changed_prediction], {}, "epl2026")["games"]["game-1"]["view_version"]

    assert first != same_time_version
    assert changed_version != first


def test_prepared_version_does_not_duplicate_or_hash_live_form_and_lineup_enrichment():
    first = _fixture()
    second = _fixture()
    second["home_form"] = {"form": ["L", "L", "W"]}
    second["match_intelligence"] = {"observed_at": "newer", "lineups": {"home": {"starters": ["live"]}}}

    first_version = build_match_views([first], {}, "epl2026")["games"]["game-1"]["view_version"]
    second_version = build_match_views([second], {}, "epl2026")["games"]["game-1"]["view_version"]
    assert first_version == second_version
    assert "home_form" not in build_match_views([second], {}, "epl2026")["games"]["game-1"]["analysis"]


def test_public_club_view_routes_use_prepared_records_and_return_processing_for_cold_cache():
    cache = ViewCollection()
    archive = ViewCollection()
    routes = _endpoint(cache, archive)
    overview = routes["/api/matches"](competition="epl2026", overview=True)

    assert overview.status_code == 202
    assert overview.body
    assert cache.find_one_calls == [({"_id": overview_view_id("epl2026")}, {
        "overview": 1, "published_revision": 1, "input_revision": 1, "active_writers": 1,
    })]
    assert cache.find_calls == archive.find_calls == []
    assert cache.writes == archive.writes == []


def test_public_match_core_and_analysis_are_single_game_reads_with_same_version():
    fixture = _fixture()
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 4, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-4",
    }])
    archive = ViewCollection()
    bundle = build_match_views([fixture], {}, "epl2026")
    assert publish_club_views(cache, "epl2026", bundle, generation=4, lease_token="gen-4")
    routes = _endpoint(cache, archive)

    core = routes["/api/matches/{match_id}"](match_id="game-1", competition="epl2026")
    analysis = routes["/api/matches/{match_id}/analysis"](match_id="game-1", competition="epl2026")

    assert core["detail_level"] == "core"
    assert analysis["detail_level"] == "analysis"
    assert core["id"] == analysis["id"] == "game-1"
    assert core["view_version"] == analysis["view_version"]
    assert core["view_version"] == bundle["games"]["game-1"]["view_version"]
    assert cache.find_calls[0][0] == {"kind": "club_game_view", "competition": "epl2026"}
    assert "analysis" not in cache.find_calls[0][1]
    assert cache.find_calls[-1] == ({"_id": {"$in": ["epl2026:match_intelligence:game-1"]}}, None)
    assert archive.find_calls == []


def test_older_preparer_cannot_overwrite_a_newer_generation():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 8, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-8",
    }])
    old = build_match_views([_fixture()], {}, "epl2026")
    new_fixture = _fixture()
    new_fixture["model_tip"] = new_fixture["top_tip"] = "2:0"
    new = build_match_views([new_fixture], {}, "epl2026")

    assert publish_club_views(cache, "epl2026", new, generation=8, lease_token="gen-8")
    assert not publish_club_views(cache, "epl2026", old, generation=7)

    assert cache.documents[game_view_id("epl2026", "game-1")]["view_version"] == new["games"]["game-1"]["view_version"]
    assert cache.documents[overview_view_id("epl2026")]["generation"] == 8


def test_late_old_publish_cleanup_cannot_delete_game_reintroduced_by_newer_head():
    class InterleavingCollection(ViewCollection):
        callback = None

        def update_one(self, query, update, upsert=False):
            result = super().update_one(query, update, upsert)
            if self.callback and query.get("generation") == 2 and "overview" in update.get("$set", {}):
                callback, self.callback = self.callback, None
                callback()
            return result

    cache = InterleavingCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    fixtures = [_fixture("game-1"), _fixture("game-x")]
    initial = build_match_views(fixtures, {}, "epl2026")
    assert publish_club_views(cache, "epl2026", initial, generation=1, lease_token="gen-1")
    old_bundle = build_match_views(fixtures[:1], {}, "epl2026")
    new_bundle = build_match_views(fixtures, {}, "epl2026")

    def publish_newer():
        head = cache.documents[overview_view_id("epl2026")]
        head.update({"generation": 3, "lease_token": "gen-3"})
        assert publish_club_views(cache, "epl2026", new_bundle, generation=3, lease_token="gen-3")

    cache.documents[overview_view_id("epl2026")].update({"generation": 2, "lease_token": "gen-2"})
    cache.callback = publish_newer
    assert publish_club_views(cache, "epl2026", old_bundle, generation=2, lease_token="gen-2")

    head, selected, canonical_id = __import__("src.services.club_views", fromlist=["published_match_view"]).published_match_view(
        cache, "epl2026", "game-x",
    )
    assert canonical_id == "game-x"
    assert head["match_versions"]["game-x"] == new_bundle["games"]["game-x"]["view_version"]
    assert selected["view_version"] == head["match_versions"]["game-x"]


def test_provider_id_tip_uses_same_archive_row_as_view_when_legacy_duplicate_exists():
    from datetime import datetime, timezone
    from src.services.user_tips import save_shared_tip

    fixture = _fixture("provider-1")
    dated_metadata = {
        "home_team": "Arsenal", "away_team": "Chelsea",
        "commence_time": fixture["commence_time"],
    }
    cache = ViewCollection([{"_id": "ucl2026:matches_cache", "data": [fixture]}])
    archive = ViewCollection([
        {"_id": "provider-1", "metadata": dated_metadata,
         "prediction": {"top_tip": "2:0", "user_tip": None},
         "post_match_result": {"status": "pending", "actual_score": None}},
        {"_id": "legacy-1", "metadata": dated_metadata,
         "prediction": {"top_tip": "1:0", "frozen_at": "2026-10-31T18:00:00Z", "user_tip": None},
         "post_match_result": {"status": "pending", "actual_score": None}},
    ])
    bundle = build_match_views([fixture], archive.documents, "ucl2026")
    assert bundle["archive_ids"]["provider-1"] == "provider-1"

    result = save_shared_tip(
        archive, cache, "provider-1", "2:1", "ucl2026",
        now=datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
    )

    assert result["match_id"] == bundle["archive_ids"]["provider-1"]
    assert archive.documents["provider-1"]["prediction"]["user_tip"] == "2:1"
    assert archive.documents["legacy-1"]["prediction"].get("user_tip") is None


def test_forced_audit_repairs_a_missing_derived_match_record():
    cache = ViewCollection([{"_id": "epl2026:matches_cache", "data": [_fixture()]}])
    archive = ViewCollection()
    prepared = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    match_id = "game-1"
    cache.delete_many({"_id": game_view_id("epl2026", match_id)})

    result = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026", force=True)

    assert prepared["status"] == "success"
    assert result["status"] == "unchanged"
    assert cache.documents[game_view_id("epl2026", match_id)]["view_version"] == (
        cache.documents[overview_view_id("epl2026")]["match_versions"][match_id]
    )


def test_archived_and_unknown_identifiers_do_not_resolve_by_team_names_only():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    archive = ViewCollection()
    bundle = build_match_views([_fixture()], {}, "epl2026")
    assert publish_club_views(cache, "epl2026", bundle, generation=1, lease_token="gen-1")
    routes = _endpoint(cache, archive)

    with __import__("pytest").raises(HTTPException) as error:
        routes["/api/matches/{match_id}"](match_id="different-id", competition="epl2026")

    assert error.value.status_code == 404


def test_paused_builder_cannot_publish_between_source_write_notifications():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    stale_source = _fixture()

    with club_view_input_write(cache, "epl2026"):
        # Simulate a builder reading the old source after the pre-write fence.
        bundle = build_match_views([stale_source], {}, "epl2026")
        changed_source = _fixture()
        changed_source["model_tip"] = changed_source["top_tip"] = "2:0"
        cache.update_one({"_id": "epl2026:matches_cache"}, {"$set": {"data": [changed_source]}}, upsert=True)
        assert not publish_club_views(
            cache, "epl2026", bundle, generation=1, input_revision=1, lease_token="gen-1",
        )

    # Once the source write completes, the intermediate revision is stale too.
    assert not publish_club_views(
        cache, "epl2026", bundle, generation=1, input_revision=1, lease_token="gen-1",
    )


def test_expired_writer_recovery_unsets_only_its_unique_token():
    from datetime import datetime, timedelta, timezone

    cache = ViewCollection()
    first = club_view_input_write(cache, "epl2026")
    second = club_view_input_write(cache, "epl2026")
    first.__enter__()
    second.__enter__()
    head = cache.documents[overview_view_id("epl2026")]
    head["active_writers"][first.token] = "2000-01-01T00:00:00+00:00"
    head["active_writers"][second.token] = "2099-01-01T00:00:00+00:00"

    from src.services.club_views import claim_club_view_build
    assert claim_club_view_build(cache, "epl2026", now=datetime(2026, 10, 28, tzinfo=timezone.utc)) is None
    first.__exit__(None, None, None)

    assert set(cache.documents[overview_view_id("epl2026")]["active_writers"]) == {second.token}
    second.__exit__(None, None, None)
    assert cache.documents[overview_view_id("epl2026")]["active_writers"] == {}


def test_two_failed_generations_preserve_the_last_published_game_record():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    original = build_match_views([_fixture()], {}, "epl2026")
    assert publish_club_views(cache, "epl2026", original, generation=1, lease_token="gen-1")
    original_version = original["games"]["game-1"]["view_version"]
    cache.fail_overview_publish = True

    for generation, tip in ((2, "2:0"), (3, "3:0")):
        head = cache.documents[overview_view_id("epl2026")]
        head.update({"generation": generation, "lease_token": f"gen-{generation}"})
        changed = _fixture()
        changed["model_tip"] = changed["top_tip"] = tip
        assert not publish_club_views(
            cache, "epl2026", build_match_views([changed], {}, "epl2026"),
            generation=generation, lease_token=f"gen-{generation}",
        )

    head, record, canonical_id = __import__("src.services.club_views", fromlist=["published_match_view"]).published_match_view(
        cache, "epl2026", "game-1",
    )
    assert canonical_id == "game-1"
    assert record["view_version"] == original_version
    assert record["core"]["model_tip"] == "1:0"
    routes = _endpoint(cache, ViewCollection())
    core = routes["/api/matches/{match_id}"](match_id="game-1", competition="epl2026")
    assert "analysis" not in cache.find_one_calls[-1][1]
    analysis = routes["/api/matches/{match_id}/analysis"](match_id="game-1", competition="epl2026")
    assert core["view_version"] == original_version
    assert core["model_tip"] == "1:0"
    assert analysis["view_version"] == original_version
    assert analysis["model_tip"] == "1:0"


def test_changed_game_reads_analysis_only_for_records_that_need_previous_snapshots():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    original = build_match_views([_fixture()], {}, "epl2026")
    assert publish_club_views(cache, "epl2026", original, generation=1, lease_token="gen-1")
    cache.find_calls.clear()

    changed_fixture = _fixture()
    changed_fixture["model_tip"] = changed_fixture["top_tip"] = "2:0"
    changed = build_match_views([changed_fixture], {}, "epl2026")
    head = cache.documents[overview_view_id("epl2026")]
    head.update({"generation": 2, "lease_token": "gen-2"})
    assert publish_club_views(cache, "epl2026", changed, generation=2, lease_token="gen-2")

    assert len(cache.find_calls) == 2
    assert "analysis" not in cache.find_calls[0][1]
    assert cache.find_calls[1] == (
        {"_id": {"$in": [game_view_id("epl2026", "game-1")]}},
        {"_id": 1, "analysis": 1, "previous.analysis": 1},
    )
    previous = cache.documents[game_view_id("epl2026", "game-1")]["previous"]
    assert previous["analysis"]["model_tip"] == "1:0"


def test_archive_alias_requires_exact_fixture_date_and_archived_chances_are_not_substituted():
    fixture = _fixture("provider-1", completed=True)
    alias_archive = {
        "legacy-1": {
            "metadata": {
                "home_team": "Arsenal", "away_team": "Chelsea",
                "commence_time": "2026-11-01T18:00:00Z",
            },
            "prediction": {"top_tip": "0:1", "model_tip": "0:1", "frozen_at": "2026-11-01T17:45:00Z"},
            "post_match_result": {"status": "completed", "actual_score": "1:0"},
        },
    }
    built = build_match_views([fixture], alias_archive, "epl2026")
    game = built["games"]["provider-1"]

    assert built["aliases"] == {"legacy-1": "provider-1"}
    assert game["core"]["archived_prediction"]["top_tip"] == "0:1"
    assert game["core"]["probabilities"] is None
    assert game["core"]["xg_home"] is None
    assert "probabilities" not in game["core"]["archived_prediction"]

    other_date = {"legacy-2": {**alias_archive["legacy-1"], "metadata": {
        **alias_archive["legacy-1"]["metadata"], "commence_time": "2026-11-02T18:00:00Z",
    }}}
    assert build_match_views([fixture], other_date, "epl2026")["aliases"] == {}


def test_undated_archive_alias_does_not_attach_frozen_prediction_to_new_provider_id():
    fixture = _fixture("new-provider-id", completed=True)
    archive = {
        "legacy-undated": {
            "metadata": {"home_team": "Arsenal", "away_team": "Chelsea"},
            "prediction": {
                "top_tip": "0:1", "model_tip": "0:1", "frozen_at": "2026-11-01T17:45:00Z",
                "user_tip": "1:1",
            },
            "post_match_result": {"status": "completed", "actual_score": "0:1"},
        },
    }

    built = build_match_views([fixture], archive, "epl2026")

    assert built["aliases"] == {}
    assert "new-provider-id" not in built["archive_ids"]
    assert "archived_prediction" not in built["games"]["new-provider-id"]["core"]


def test_unknown_match_stays_processing_while_prepared_inputs_are_dirty():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 4,
        "input_revision": 5, "published_revision": 4,
        "active_writers": {}, "aliases": {}, "match_versions": {},
    }])
    routes = _endpoint(cache, ViewCollection())

    result = routes["/api/matches/{match_id}"](match_id="newly-added", competition="epl2026")

    assert result.status_code == 202
    cache.documents[overview_view_id("epl2026")]["published_revision"] = 5
    with __import__("pytest").raises(HTTPException) as error:
        routes["/api/matches/{match_id}"](match_id="newly-added", competition="epl2026")
    assert error.value.status_code == 404


def test_bounded_archive_lookup_uses_exact_id_then_explicit_prepared_alias():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "archive_ids": {"provider-1": "legacy-1"},
    }])
    archive = ViewCollection([{"_id": "legacy-1", "prediction": {"user_tip": "2:1"}}])

    result = load_archive_match(archive, cache, "epl2026", "provider-1")

    assert result == {"provider-1": {"prediction": {"user_tip": "2:1"}}}
    assert archive.find_one_calls == [({"_id": "provider-1"}, None), ({"_id": "legacy-1"}, None)]


def test_background_preparation_reads_only_cached_sources_and_skips_unchanged_view_writes():
    cache = ViewCollection([{
        "_id": "epl2026:matches_cache", "data": [_fixture()],
        "observed_at": "2026-10-28T12:00:00Z",
    }])
    archive = ViewCollection()

    first = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    stored = deepcopy(cache.documents[overview_view_id("epl2026")]["overview"])
    writes_after_build = deepcopy(cache.writes)
    second = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")

    assert first == {"status": "success", "reason": None, "matches": 1}
    assert second == {"status": "unchanged", "matches": 1}
    assert cache.documents[overview_view_id("epl2026")]["overview"] == stored
    assert [row["kind"] for row in cache.documents.values() if row.get("kind") == "club_game_view"] == ["club_game_view"]
    assert archive.find_calls == [({}, __import__("src.services.club_views", fromlist=["_archive_projection"])._archive_projection())]
    assert cache.writes == writes_after_build
    assert [query for query, _projection in cache.find_one_calls if query == {"_id": "epl2026:matches_cache"}] == [
        {"_id": "epl2026:matches_cache"},
    ]


def test_source_revision_bump_rebuilds_without_waiting_for_periodic_audit():
    from src.services.club_views import club_view_input_write

    cache = ViewCollection([{
        "_id": "epl2026:matches_cache", "data": [_fixture()],
    }])
    archive = ViewCollection()
    first = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    assert first["status"] == "success"

    changed = _fixture()
    changed["model_tip"] = changed["top_tip"] = "2:0"
    with club_view_input_write(cache, "epl2026"):
        cache.update_one(
            {"_id": "epl2026:matches_cache"}, {"$set": {"data": [changed]}}, upsert=False,
        )

    second = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")

    assert second["status"] == "success"
    head = cache.documents[overview_view_id("epl2026")]
    assert head["overview"][0]["model_tip"] == "2:0"
    assert head["published_revision"] == head["input_revision"]
    assert len(archive.find_calls) == 2


def test_schema_mismatch_and_force_each_trigger_a_stored_source_audit():
    cache = ViewCollection([{"_id": "epl2026:matches_cache", "data": [_fixture()]}])
    archive = ViewCollection()
    prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    head = cache.documents[overview_view_id("epl2026")]
    head["schema_version"] = -1

    migrated = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    forced = prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026", force=True)

    assert migrated["status"] == "unchanged"
    assert forced["status"] == "unchanged"
    assert len(archive.find_calls) == 3


def test_view_worker_forces_startup_audit_and_uses_ten_second_elapsed_cadence(monkeypatch):
    import asyncio
    import src.services.club_views as club_views
    from src.competitions import get_competition

    calls = []
    delays = []

    def prepare(_cache, _archive, _competition, *, force=False):
        calls.append(force)
        return {"status": "unchanged"}

    async def immediate_to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    class StopWorker(Exception):
        pass

    async def stop_after_cycle(delay):
        delays.append(delay)
        raise StopWorker

    monkeypatch.setattr(club_views, "prepare_club_views", prepare)
    monkeypatch.setattr(club_views, "COMPETITIONS", {"epl2026": get_competition("epl2026")})
    monkeypatch.setattr(club_views.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(club_views.asyncio, "sleep", stop_after_cycle)

    with __import__("pytest").raises(StopWorker):
        asyncio.run(club_views.run_club_views_worker({}, {}))

    assert calls == [True]
    assert len(delays) == 1 and 0 <= delays[0] <= 10


def test_shared_archive_sync_fences_a_club_archive_mutation():
    from src.routes.matches import _sync_archive_tips

    cache = ViewCollection()

    class FencedArchive(ViewCollection):
        def replace_one(self, query, replacement, upsert=False):
            assert cache.documents[overview_view_id("epl2026")]["active_writers"]
            return super().replace_one(query, replacement, upsert)

    archive_store = FencedArchive()
    archive = {
        "game-1": {
            "prediction": {"top_tip": "1:0"},
            "post_match_result": {"status": "pending"},
        },
    }

    _sync_archive_tips(
        [{"id": "game-1", "top_tip": "2:0", "max_xp": 3.5}], archive,
        archive_store, competition="epl2026", cache_collection=cache,
    )

    assert archive_store.documents["game-1"]["prediction"]["top_tip"] == "2:0"
    assert cache.documents[overview_view_id("epl2026")]["input_revision"] == 2


def test_freeze_route_fences_club_archive_write_but_not_world_cup(monkeypatch):
    from src.routes import predict

    class Limiter:
        def limit(self, _limit):
            return lambda function: function

    caches = {competition: ViewCollection() for competition in ("epl2026", "wc2026")}
    writes = {}
    archives = {}
    def tracking_archive(comp):
        class TrackingArchive(ViewCollection):
            def update_one(self, query, update, upsert=False):
                head = caches[comp].documents.get(overview_view_id(comp), {})
                writes.setdefault(comp, []).append(bool(head.get("active_writers")))
                return super().update_one(query, update, upsert)

        return TrackingArchive([{
            "_id": "game-1", "prediction": {"user_tip": None},
        }])

    for competition in caches:
        archives[competition] = tracking_archive(competition)

    def fake_freeze(_cache, archive, _service, match_id, **_kwargs):
        archive.update_one(
            {"_id": match_id}, {"$set": {"prediction.frozen_at": "frozen"}}, upsert=False,
        )
        return {"ok": True}

    monkeypatch.setattr(predict, "freeze_prediction", fake_freeze)
    router = predict.init_router(object(), None, caches, Limiter(), archives)
    freeze = next(route.endpoint for route in router.routes if route.path == "/api/predict/freeze")

    assert freeze({"match_id": "game-1"}, competition="epl2026") == {"ok": True}
    assert freeze({"match_id": "game-1"}, competition="wc2026") == {"ok": True}

    assert writes == {"epl2026": [True], "wc2026": [False]}
    assert caches["wc2026"].documents == {}


def test_saved_tip_updates_the_persisted_overview_and_core_immediately():
    from datetime import datetime, timezone
    from src.services.user_tips import save_shared_tip

    fixture = _fixture()
    cache = ViewCollection([{"_id": "epl2026:matches_cache", "data": [fixture]}])
    archive = ViewCollection()
    bundle = build_match_views([fixture], {}, "epl2026")
    claim = {"_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
             "published_revision": None, "active_writers": {}, "lease_token": "gen-1"}
    cache.documents[claim["_id"]] = claim
    assert publish_club_views(cache, "epl2026", bundle, generation=1, lease_token="gen-1")
    old_version = cache.documents[game_view_id("epl2026", "game-1")]["view_version"]

    save_shared_tip(
        archive, cache, "game-1", "2:1", "epl2026",
        now=datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
    )

    head = cache.documents[overview_view_id("epl2026")]
    game = cache.documents[game_view_id("epl2026", "game-1")]
    assert head["overview"][0]["user_tip"] == "2:1"
    assert game["core"]["user_tip"] == "2:1"
    assert game["analysis"]["user_tip"] == "2:1"
    assert game["view_version"] != old_version
    assert head["input_revision"] != head["published_revision"]



def test_saved_tip_head_race_preserves_the_matching_published_core_and_analysis():
    from src.services.club_views import patch_saved_tip, published_match_view

    class WriterRaceCollection(ViewCollection):
        race_armed = False

        def update_one(self, query, update, upsert=False):
            if self.race_armed and "overview" in update.get("$set", {}):
                self.race_armed = False
                head = self.documents[overview_view_id("epl2026")]
                head["input_revision"] += 1
                head["active_writers"] = {"concurrent-source-write": "2099-01-01T00:00:00Z"}
            return super().update_one(query, update, upsert)

    cache = WriterRaceCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    bundle = build_match_views([_fixture()], {}, "epl2026")
    assert publish_club_views(cache, "epl2026", bundle, generation=1, lease_token="gen-1")
    original = deepcopy(bundle["games"]["game-1"])
    cache.race_armed = True

    assert not patch_saved_tip(cache, "epl2026", "game-1", "2:1")

    for analysis, key in ((False, "core"), (True, "analysis")):
        _head, selected, canonical_id = published_match_view(cache, "epl2026", "game-1", analysis=analysis)
        assert canonical_id == "game-1"
        assert selected["view_version"] == original["view_version"]
        assert selected[key] == original[key]


def test_saved_tip_during_unpublished_build_retains_the_published_fallback():
    from src.services.club_views import patch_saved_tip, published_match_view

    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    original = build_match_views([_fixture()], {}, "epl2026")
    assert publish_club_views(cache, "epl2026", original, generation=1, lease_token="gen-1")
    head = cache.documents[overview_view_id("epl2026")]
    head.update({"generation": 2, "lease_token": "gen-2"})
    changed = _fixture()
    changed["model_tip"] = changed["top_tip"] = "3:0"
    cache.fail_overview_publish = True
    assert not publish_club_views(cache, "epl2026", build_match_views([changed], {}, "epl2026"),
                                  generation=2, lease_token="gen-2")

    assert not patch_saved_tip(cache, "epl2026", "game-1", "2:1")

    for analysis, key in ((False, "core"), (True, "analysis")):
        _head, selected, _canonical = published_match_view(cache, "epl2026", "game-1", analysis=analysis)
        assert selected[key] == original["games"]["game-1"][key]


def test_provider_id_tip_save_updates_the_prepared_legacy_archive_row_without_duplicate():
    from datetime import datetime, timezone
    from src.services.user_tips import save_shared_tip

    fixture = _fixture("provider-1")
    cache = ViewCollection([
        {"_id": "ucl2026:matches_cache", "data": [fixture]},
        {"_id": overview_view_id("ucl2026"), "archive_ids": {"provider-1": "legacy-1"}},
    ])
    archive = ViewCollection([{
        "_id": "legacy-1",
        "metadata": {
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": fixture["commence_time"],
        },
        "pre_match_snapshot": {"observed_at": "2026-10-31T18:00:00Z"},
        "prediction": {
            "top_tip": "1:0", "model_tip": "1:0", "frozen_at": "2026-10-31T18:00:00Z",
            "matrix": {"0": {"0": 0.5}}, "user_tip": None,
        },
        "post_match_result": {"status": "pending", "actual_score": None},
    }])

    result = save_shared_tip(
        archive, cache, "provider-1", "2:0", "ucl2026",
        now=datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
    )

    assert set(archive.documents) == {"legacy-1"}
    saved = archive.documents["legacy-1"]
    assert saved["prediction"]["user_tip"] == "2:0"
    assert saved["prediction"]["top_tip"] == "1:0"
    assert saved["prediction"]["frozen_at"] == "2026-10-31T18:00:00Z"
    assert saved["prediction"]["matrix"] == {"0": {"0": 0.5}}
    assert result["match_id"] == "legacy-1"
    assert result["canonical_match_id"] == "provider-1"


def test_stale_prepared_archive_alias_is_verified_before_tip_write():
    from datetime import datetime, timezone
    from src.services.user_tips import save_shared_tip

    fixture = _fixture("provider-1")
    cache = ViewCollection([
        {"_id": "ucl2026:matches_cache", "data": [fixture]},
        {"_id": overview_view_id("ucl2026"), "archive_ids": {"provider-1": "stale-archive-id"}},
    ])
    archive = ViewCollection([
        {
            "_id": "stale-archive-id",
            "metadata": {
                "home_team": "Arsenal", "away_team": "Chelsea",
                "commence_time": "2026-10-25T19:00:00Z",
            },
            "prediction": {"top_tip": "0:1", "frozen_at": "2026-10-25T18:00:00Z"},
            "post_match_result": {"status": "pending", "actual_score": None},
        },
        {
            "_id": "legacy-1",
            "metadata": {
                "home_team": "Arsenal", "away_team": "Chelsea",
                "commence_time": fixture["commence_time"],
            },
            "prediction": {"top_tip": "1:0", "frozen_at": "2026-10-31T18:00:00Z"},
            "post_match_result": {"status": "pending", "actual_score": None},
        },
    ])

    result = save_shared_tip(
        archive, cache, "provider-1", "2:0", "ucl2026",
        now=datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
    )

    assert result["match_id"] == "legacy-1"
    assert archive.documents["legacy-1"]["prediction"]["user_tip"] == "2:0"
    assert archive.documents["stale-archive-id"]["prediction"].get("user_tip") is None
    assert "provider-1" not in archive.documents


def test_preparation_keeps_archived_historical_match_context_from_projected_metadata():
    fixture = _fixture("game-1", completed=True)
    cache = ViewCollection([{"_id": "ucl2026:matches_cache", "data": [fixture]}])
    archive = ViewCollection([{
        "_id": "game-1",
        "metadata": {
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": fixture["commence_time"], "competition": "ucl2026",
            "stage": "final", "tie_id": "tie-9", "leg": "second",
            "first_leg_score": "1:0", "first_leg_home_score": 1,
            "first_leg_away_score": 0, "score_90": "2:1", "score_aet": "3:1",
            "shootout_winner": "Arsenal", "extra_time_eligible": True,
        },
        "prediction": {"top_tip": "1:0", "model_tip": "1:0", "frozen_at": "2026-10-31T18:00:00Z"},
        "post_match_result": {"status": "completed", "actual_score": "3:1"},
    }])

    result = prepare_club_views({"ucl2026": cache}, {"ucl2026": archive}, "ucl2026")

    assert result["status"] == "success"
    context = cache.documents[game_view_id("ucl2026", "game-1")]["core"]["context"]
    assert context == {
        "competition": "ucl2026", "stage": "final", "tie_id": "tie-9", "leg": "second",
        "first_leg_score": "1:0", "first_leg_home_score": 1, "first_leg_away_score": 0,
        "score_90": "2:1", "score_aet": "3:1", "shootout_winner": "Arsenal",
        "extra_time_eligible": True, "commence_time": fixture["commence_time"],
    }


def test_historical_tip_by_provider_id_updates_prepared_legacy_archive_id():
    from datetime import datetime, timezone
    from src.services.user_tips import save_historical_tip

    fixture = _fixture("provider-1", completed=True)
    fixture["actual_score"] = "2:1"
    cache = ViewCollection([
        {"_id": "ucl2026:matches_cache", "data": [fixture]},
        {"_id": overview_view_id("ucl2026"), "archive_ids": {"provider-1": "legacy-done"}},
    ])
    archive = ViewCollection([{
        "_id": "legacy-done",
        "metadata": {
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": fixture["commence_time"], "is_ko_phase": False,
        },
        "prediction": {"top_tip": "1:0", "user_tip": None},
        "post_match_result": {"status": "completed", "actual_score": "2:1"},
    }])

    result = save_historical_tip(
        archive, "provider-1", "2:1", "ucl2026", cache_store=cache,
        now=datetime(2026, 11, 2, 12, tzinfo=timezone.utc),
    )

    assert set(archive.documents) == {"legacy-done"}
    assert archive.documents["legacy-done"]["prediction"]["user_tip"] == "2:1"
    assert result["match_id"] == "legacy-done"
    assert result["canonical_match_id"] == "provider-1"
