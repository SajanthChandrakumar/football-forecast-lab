"""Lossless compact storage for the prepared overview's database transfer."""
import gzip
import json

import pytest
from fastapi import HTTPException

from src.services.club_views import build_match_views, overview_view_id, patch_saved_tip, prepare_club_views, publish_club_views
from test_club_views import ViewCollection, _endpoint, _fixture


def _published():
    cache = ViewCollection([{
        "_id": overview_view_id("epl2026"), "generation": 1, "input_revision": 0,
        "published_revision": None, "active_writers": {}, "lease_token": "gen-1",
    }])
    assert publish_club_views(cache, "epl2026", build_match_views([_fixture()], {}, "epl2026"),
                              generation=1, lease_token="gen-1")
    return cache, cache.documents[overview_view_id("epl2026")]


def test_publication_stores_a_lossless_compressed_overview():
    _cache, head = _published()
    assert isinstance(head["overview_gzip"], bytes)
    assert json.loads(gzip.decompress(head["overview_gzip"])) == head["overview"]


def test_public_read_projects_compressed_bytes_without_the_array():
    cache, head = _published()
    head["overview_gzip"] = gzip.compress(json.dumps(head["overview"]).encode())
    head["overview"] = [{"id": "must-not-read-the-array"}]
    cache.find_one_calls.clear()
    rows = _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert rows[0]["id"] == "game-1"
    assert len(cache.find_one_calls) == 1
    assert cache.find_one_calls[0][1].get("overview_gzip") == 1
    assert "overview" not in cache.find_one_calls[0][1]


def test_tip_patch_updates_the_compressed_and_array_views_atomically():
    cache, head = _published()
    head["overview_gzip"] = gzip.compress(json.dumps(head["overview"]).encode())
    assert patch_saved_tip(cache, "epl2026", "game-1", "2:1")
    assert json.loads(gzip.decompress(head["overview_gzip"])) == head["overview"]
    assert head["overview"][0]["user_tip"] == "2:1"


@pytest.mark.parametrize("invalid_payload", [None, "invalid-bson-type"])
def test_missing_compressed_payload_is_repaired_without_waiting_for_audit(invalid_payload):
    cache = ViewCollection([{"_id": "epl2026:matches_cache", "data": [_fixture()]}])
    archive = ViewCollection()
    prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    head = cache.documents[overview_view_id("epl2026")]
    if invalid_payload is None:
        head.pop("overview_gzip", None)
    else:
        head["overview_gzip"] = invalid_payload
    prepare_club_views({"epl2026": cache}, {"epl2026": archive}, "epl2026")
    assert json.loads(gzip.decompress(head["overview_gzip"])) == head["overview"]


def test_legacy_array_is_read_only_as_a_rollout_fallback():
    cache, head = _published()
    head.pop("overview_gzip", None)
    cache.find_one_calls.clear()
    rows = _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert rows[0]["id"] == "game-1"
    assert len(cache.find_one_calls) == 2
    assert "overview" not in cache.find_one_calls[0][1]
    assert cache.find_one_calls[1][1].get("overview") == 1


def test_corrupt_compressed_payload_is_an_explicit_error():
    cache, head = _published()
    head["overview_gzip"] = b"not-gzip"
    with pytest.raises(HTTPException) as error:
        _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert error.value.status_code == 503


def test_failed_tip_head_switch_retains_the_published_compressed_payload():
    cache, head = _published()
    original = head["overview_gzip"]
    cache.fail_overview_publish = True
    assert not patch_saved_tip(cache, "epl2026", "game-1", "2:1")
    assert head["overview_gzip"] == original
    rows = _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert rows[0]["user_tip"] is None
    assert rows[0]["view_version"] == head["match_versions"]["game-1"]


def test_decoded_overview_ages_status_and_marks_refresh_without_mutating_storage():
    from src.services.club_views import encode_overview

    cache, head = _published()
    for metadata in head["overview"][0]["input_provenance"].values():
        metadata.update({"observed_at": "2020-01-01T00:00:00Z", "status": "fresh"})
    head["overview_gzip"] = encode_overview(head["overview"])
    original = head["overview_gzip"]
    head["input_revision"] += 1
    rows = _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert rows[0]["status"] == "stale"
    assert rows[0]["input_provenance"]["odds"]["status"] == "stale"
    assert rows[0]["view_status"] == "refreshing"
    assert head["overview_gzip"] == original
    assert json.loads(gzip.decompress(original))[0]["input_provenance"]["odds"]["status"] == "fresh"


def test_old_publisher_during_rollout_cannot_leave_a_stale_gzip_view_visible():
    cache, head = _published()
    # The previous deployed publisher updates the array/schema, not the new bytes.
    head["overview"][0]["user_tip"] = "3:1"
    head["schema_version"] = 1
    rows = _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert rows[0]["user_tip"] == "3:1"


def test_old_tip_writer_on_a_new_schema_uses_the_updated_array_while_dirty():
    cache, head = _published()
    # An old accepted-tip patch preserves unknown gzip/schema fields.
    head["overview"][0]["user_tip"] = "3:1"
    head["input_revision"] += 2
    rows = _endpoint(cache, ViewCollection())["/api/matches"](competition="epl2026", overview=True)
    assert rows[0]["user_tip"] == "3:1"
    assert rows[0]["view_status"] == "refreshing"
