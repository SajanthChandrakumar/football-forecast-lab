import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
import stat

import pytest
from bson import json_util

from scripts.repair_club_form import run_repair


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}

    def find(self, query=None):
        documents = list(self.documents.values())
        if not query:
            return documents
        pattern = query.get("_id", {}).get("$regex")
        return [doc for doc in documents if pattern and __import__("re").match(pattern, doc.get("_id", ""))]

    def find_one(self, query):
        document = self.documents.get(query.get("_id"))
        return document if document and all(document.get(k) == v for k, v in query.items()) else None

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise ValueError("duplicate key")
        self.documents[document["_id"]] = dict(document)

    def update_one(self, query, update, upsert=False):
        key = query.get("_id")
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


def collections():
    return {
        "epl2026": MemoryCollection([
            {"_id": "epl2026:team_form_teams", "competition": "epl2026", "teams": [{"team_id": "1"}]},
            {"_id": "epl2026:team_form:1", "competition": "epl2026", "matches": [{"fixture_id": "e1"}]},
            {"_id": "epl2026:team_form_sync", "competition": "epl2026", "last_successful_at": "t1"},
            {"_id": "epl2026:elo_ratings", "competition": "epl2026", "rows": [1]},
            {"_id": "wm2026:team_form:1", "competition": "wm2026", "matches": ["untouched"]},
        ]),
        "ucl2026": MemoryCollection([
            {"_id": "ucl2026:team_form_teams", "competition": "ucl2026", "teams": [{"team_id": "2"}]},
            {"_id": "ucl2026:team_form:2", "competition": "ucl2026", "matches": [{"fixture_id": "u1"}]},
            {"_id": "ucl2026:archive:2", "competition": "ucl2026", "prediction": {"tip": "1:0"}},
        ]),
    }


NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def test_dry_run_backs_up_only_epl_and_ucl_form_cache_without_database_writes(tmp_path):
    stores = collections()
    before = {comp: dict(store.documents) for comp, store in stores.items()}
    backup = tmp_path / "forms.extjson"

    result = run_repair(stores, backup_path=backup, now=NOW)

    assert result["status"] == "dry-run"
    assert result["inventory"] == {"epl2026": 3, "ucl2026": 2}
    assert result["preview"]["epl2026"] == {
        "team_documents": 1, "affected_teamdocs": 1, "verified_rows_retained": 0,
        "legacy_or_unverified_rows_excluded": 1, "raw_legacy_rows_preserved": 0,
        "namespace_mismatches": 1, "category_mismatches": 1,
    }
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "forms.extjson.manifest.json").stat().st_mode) == 0o600
    assert {comp: store.documents for comp, store in stores.items()} == before
    assert backup.exists()
    manifest_path = tmp_path / "forms.extjson.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["document_counts"] == {"epl2026": 3, "ucl2026": 2}
    assert manifest["sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
    payload = json_util.loads(backup.read_text())
    assert set(payload["collections"]) == {"epl2026", "ucl2026"}
    assert all("elo_ratings" not in doc["_id"] and "archive" not in doc["_id"]
               for docs in payload["collections"].values() for doc in docs)


def test_dry_run_refuses_to_overwrite_an_existing_backup(tmp_path):
    stores = collections()
    backup = tmp_path / "forms.extjson"
    run_repair(stores, backup_path=backup, now=NOW)
    original = backup.read_bytes()
    manifest = (tmp_path / "forms.extjson.manifest.json").read_bytes()

    with pytest.raises(FileExistsError):
        run_repair(stores, backup_path=backup, now=NOW)

    assert backup.read_bytes() == original
    assert (tmp_path / "forms.extjson.manifest.json").read_bytes() == manifest


def test_restore_replaces_only_form_cache_documents_and_leaves_ratings_and_archives_untouched(tmp_path):
    stores = collections()
    backup = tmp_path / "forms.extjson"
    run_repair(stores, backup_path=backup, now=NOW)
    original_ep = deepcopy(stores["epl2026"].find_one({"_id": "epl2026:team_form:1"}))
    stores["epl2026"].documents["epl2026:team_form:1"]["matches"] = [{"fixture_id": "corrupt"}]
    stores["epl2026"].documents["epl2026:team_form:99"] = {
        "_id": "epl2026:team_form:99", "competition": "epl2026", "matches": [],
    }
    rating = dict(stores["epl2026"].documents["epl2026:elo_ratings"])
    archive = dict(stores["ucl2026"].documents["ucl2026:archive:2"])

    result = run_repair(stores, mode="restore", restore_path=backup, now=NOW)

    assert result["status"] == "restored"
    assert stores["epl2026"].find_one({"_id": "epl2026:team_form:1"}) == original_ep
    assert stores["epl2026"].find_one({"_id": "epl2026:team_form:99"}) is None
    assert stores["epl2026"].documents["epl2026:elo_ratings"] == rating
    assert stores["ucl2026"].documents["ucl2026:archive:2"] == archive


def test_tampered_backup_is_rejected_before_restore_mutates_any_form_document(tmp_path):
    stores = collections()
    backup = tmp_path / "forms.extjson"
    run_repair(stores, backup_path=backup, now=NOW)
    before = {comp: dict(store.documents) for comp, store in stores.items()}
    backup.write_text(backup.read_text() + " ")

    with pytest.raises(ValueError, match="hash"):
        run_repair(stores, mode="restore", restore_path=backup, now=NOW)

    assert {comp: store.documents for comp, store in stores.items()} == before


def test_apply_writes_and_verifies_backup_before_invoking_the_shared_refresh_service(tmp_path):
    stores = collections()
    backup = tmp_path / "before-apply.extjson"
    calls = []

    class Service:
        def refresh_all_competitions(self, *, now):
            assert backup.exists()
            assert json.loads((tmp_path / "before-apply.extjson.manifest.json").read_text())["sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
            calls.append(now)
            return {"status": "fresh", "teams": 1}

    result = run_repair(
        stores, mode="apply", backup_path=backup, now=NOW,
        service_factory=lambda collection, competition: Service(),
    )

    assert result["status"] == "fresh"
    assert calls == [NOW, NOW]
    assert backup.exists()
