"""Back up, repair, or restore only EPL/UCL derived form cache records."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from bson import json_util

from src.competitions import COMPETITIONS
from src.services.team_form import EspnTeamFormClient, TeamFormService

COMPETITION_IDS = ("epl2026", "ucl2026")
FORMAT_VERSION = "club-form-backup-v1"
LEASE_SECONDS = 300


def _form_document_pattern(competition):
    return rf"^{re.escape(competition)}:team_form(?::[^:]+|_(?:teams|sync|bootstrap))$"


def _is_form_document(document, competition):
    document_id = document.get("_id")
    return isinstance(document_id, str) and re.fullmatch(
        _form_document_pattern(competition), document_id,
    ) is not None


def inventory_form_documents(collections):
    """Read only the allow-listed form cache IDs from EPL and UCL."""
    snapshot = {}
    for competition in COMPETITION_IDS:
        collection = collections[competition]
        documents = list(collection.find({"_id": {"$regex": _form_document_pattern(competition)}}))
        snapshot[competition] = sorted(
            (dict(document) for document in documents if _is_form_document(document, competition)),
            key=lambda document: document["_id"],
        )
    return snapshot


def _canonical_document_hash(document):
    serialized = json_util.dumps(document, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def write_backup(snapshot, backup_path, *, now=None):
    path = Path(backup_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = now or datetime.now(timezone.utc)
    payload = {
        "format": FORMAT_VERSION,
        "created_at": current.isoformat(),
        "collections": snapshot,
    }
    serialized = json_util.dumps(
        payload, json_options=json_util.CANONICAL_JSON_OPTIONS,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    sha256 = hashlib.sha256(serialized).hexdigest()
    document_hashes = {
        competition: {document["_id"]: _canonical_document_hash(document) for document in documents}
        for competition, documents in snapshot.items()
    }
    manifest = {
        "format": FORMAT_VERSION,
        "sha256": sha256,
        "document_counts": {competition: len(documents) for competition, documents in snapshot.items()},
        "document_sha256": document_hashes,
    }
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    contents = (
        (path, serialized),
        (manifest_path, json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")),
    )
    if any(target.exists() for target, _ in contents):
        raise FileExistsError(f"Backup or manifest already exists: {path}")
    temporaries = []
    created = []
    try:
        for target, content in contents:
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            temporaries.append((temporary, target))
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, target in temporaries:
            os.link(temporary, target)
            created.append(target)
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _ in temporaries:
            temporary.unlink(missing_ok=True)
    return manifest, manifest_path


def preview_repair(snapshot):
    """Count existing rows the ESPN-backed repair can safely retain or will quarantine."""
    preview = {}
    for competition, documents in snapshot.items():
        team_documents = [
            document for document in documents
            if re.fullmatch(rf"{re.escape(competition)}:team_form:[^:]+", str(document.get("_id") or ""))
        ]
        counts = {
            "team_documents": len(team_documents),
            "affected_teamdocs": 0,
            "verified_rows_retained": 0,
            "legacy_or_unverified_rows_excluded": 0,
            "raw_legacy_rows_preserved": 0,
            "namespace_mismatches": 0,
            "category_mismatches": 0,
        }
        for document in team_documents:
            rows = document.get("matches") if isinstance(document.get("matches"), list) else []
            excluded = 0
            for row in rows:
                provider_namespace = (row or {}).get("provider_namespace") if isinstance(row, dict) else None
                provider_namespace_expected = TeamFormService.PROVIDER_NAMESPACES.get(
                    (row or {}).get("provider") if isinstance(row, dict) else None
                )
                if provider_namespace != "espn:team-id" or provider_namespace != provider_namespace_expected:
                    counts["namespace_mismatches"] += 1
                details = TeamFormService._competition_details({
                    "id": (row or {}).get("competition_id") if isinstance(row, dict) else None,
                    "slug": (row or {}).get("competition_slug") if isinstance(row, dict) else None,
                    "name": (row or {}).get("competition_name") if isinstance(row, dict) else None,
                }, provider=(row or {}).get("provider") if isinstance(row, dict) else None)
                if (
                    details is None
                    or details[0] != str((row or {}).get("competition_id"))
                    or details[2] != (row or {}).get("competition_kind")
                ):
                    counts["category_mismatches"] += 1
                if TeamFormService._verified_match(
                    row, "espn:team-id", team_id=document.get("team_id"),
                ):
                    counts["verified_rows_retained"] += 1
                else:
                    excluded += 1
            counts["legacy_or_unverified_rows_excluded"] += excluded
            counts["raw_legacy_rows_preserved"] += len(document.get("raw_legacy_matches") or [])
            if (
                excluded
                or document.get("scope") != "all_competitions"
                or document.get("validation_version") != TeamFormService.VALIDATION_VERSION
            ):
                counts["affected_teamdocs"] += 1
        preview[competition] = counts
    return preview


def read_verified_backup(backup_path):
    path = Path(backup_path)
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    try:
        serialized = path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Backup or manifest cannot be read: {exc}") from exc
    if manifest.get("format") != FORMAT_VERSION:
        raise ValueError("Backup manifest format is unsupported")
    if hashlib.sha256(serialized).hexdigest() != manifest.get("sha256"):
        raise ValueError("Backup hash verification failed")
    try:
        payload = json_util.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Backup is not valid Extended JSON: {exc}") from exc
    if payload.get("format") != FORMAT_VERSION:
        raise ValueError("Backup format is unsupported")
    snapshot = payload.get("collections")
    if not isinstance(snapshot, dict) or set(snapshot) != set(COMPETITION_IDS):
        raise ValueError("Backup must contain exactly the EPL and UCL form collections")
    counts, hashes = {}, {}
    for competition, documents in snapshot.items():
        if not isinstance(documents, list) or any(
            not isinstance(document, dict) or not _is_form_document(document, competition)
            or document.get("competition") not in (None, competition)
            for document in documents
        ):
            raise ValueError(f"Backup contains an out-of-scope {competition} document")
        ids = [document["_id"] for document in documents]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Backup contains duplicate {competition} form IDs")
        counts[competition] = len(documents)
        hashes[competition] = {document["_id"]: _canonical_document_hash(document) for document in documents}
    if counts != manifest.get("document_counts") or hashes != manifest.get("document_sha256"):
        raise ValueError("Backup document manifest verification failed")
    return snapshot, manifest


def _lease_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


@contextmanager
def maintenance_leases(collections, *, now=None):
    """Fence repair against normal maintenance using its existing lease keys."""
    current = now or datetime.now(timezone.utc)
    token = uuid4().hex
    lease_until = (current + timedelta(seconds=LEASE_SECONDS)).isoformat()
    acquired = []
    try:
        for competition in COMPETITION_IDS:
            collection = collections[competition]
            lease_id = f"{competition}:maintenance_lease"
            lease = {
                "_id": lease_id, "competition": competition,
                "lease_token": token, "lease_until": lease_until,
            }
            try:
                collection.insert_one(lease)
            except Exception:
                existing = collection.find_one({"_id": lease_id}) or {}
                expiry = _lease_time(existing.get("lease_until"))
                if expiry is not None and expiry > current:
                    raise RuntimeError(f"Maintenance lease is held for {competition}")
                result = collection.update_one(
                    {"_id": lease_id, "lease_token": existing.get("lease_token"),
                     "lease_until": existing.get("lease_until")},
                    {"$set": {key: value for key, value in lease.items() if key != "_id"}},
                    upsert=False,
                )
                if getattr(result, "matched_count", 0) != 1:
                    raise RuntimeError(f"Could not claim maintenance lease for {competition}")
            acquired.append((collection, lease_id, token))
        yield
    finally:
        for collection, lease_id, lease_token in reversed(acquired):
            collection.delete_one({"_id": lease_id, "lease_token": lease_token})


def _restore_snapshot(collections, snapshot):
    for competition in COMPETITION_IDS:
        collection = collections[competition]
        existing = collection.find({"_id": {"$regex": _form_document_pattern(competition)}})
        for document in list(existing):
            if _is_form_document(document, competition):
                collection.delete_one({"_id": document["_id"]})
        for document in snapshot[competition]:
            collection.insert_one(dict(document))


def _default_backup_path(now):
    return Path.cwd() / f"club-form-backup-{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.extjson"


def _service_for(collection, competition):
    season = int(COMPETITIONS[competition].season.split("/", 1)[0])
    return TeamFormService(
        collection,
        EspnTeamFormClient(season=season, competition=competition),
        competition=competition,
    )


def run_repair(
    collections, *, mode="dry-run", backup_path=None, restore_path=None, now=None,
    service_factory=None,
):
    """Execute a dry-run, backup-first repair, or a checksum-verified restore."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if mode not in {"dry-run", "apply", "restore"}:
        raise ValueError("mode must be dry-run, apply, or restore")

    if mode == "restore":
        if restore_path is None:
            raise ValueError("restore mode requires restore_path")
        snapshot, manifest = read_verified_backup(restore_path)
        with maintenance_leases(collections, now=current):
            _restore_snapshot(collections, snapshot)
        return {"status": "restored", "inventory": manifest["document_counts"], "backup": str(restore_path)}

    backup_path = Path(backup_path) if backup_path is not None else _default_backup_path(current)
    if mode == "dry-run":
        snapshot = inventory_form_documents(collections)
        preview = preview_repair(snapshot)
        manifest, _ = write_backup(snapshot, backup_path, now=current)
        # Read it back before presenting it as restorable.
        read_verified_backup(backup_path)
        return {
            "status": "dry-run", "inventory": manifest["document_counts"],
            "backup": str(backup_path), "sha256": manifest["sha256"],
            "database_writes": 0, "preview": preview,
        }

    with maintenance_leases(collections, now=current):
        snapshot = inventory_form_documents(collections)
        manifest, _ = write_backup(snapshot, backup_path, now=current)
        read_verified_backup(backup_path)
        results = {}
        for competition in COMPETITION_IDS:
            service = (service_factory or _service_for)(collections[competition], competition)
            results[competition] = service.refresh_all_competitions(now=current)
        status = "fresh" if all(result.get("status") == "fresh" for result in results.values()) else "stale"
        return {
            "status": status, "inventory": manifest["document_counts"],
            "backup": str(backup_path), "sha256": manifest["sha256"],
            "results": results,
        }


def _collections_from_mongo():
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise ValueError("MONGO_URI environment variable is required")
    import certifi
    from pymongo import MongoClient

    client = MongoClient(uri, tlsCAFile=certifi.where())
    database = client["wm2026_db"]
    return client, {
        competition: database[COMPETITIONS[competition].cache_collection]
        for competition in COMPETITION_IDS
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="inventory and write a verified backup (default)")
    mode.add_argument("--apply", action="store_true", help="rebuild verified EPL/UCL form caches from free ESPN data")
    mode.add_argument("--restore", metavar="BACKUP", help="restore only form cache documents from a verified backup")
    parser.add_argument("--backup", help="Extended JSON backup path for dry-run/apply")
    args = parser.parse_args(argv)
    selected_mode = "restore" if args.restore else "apply" if args.apply else "dry-run"
    if selected_mode != "restore" and args.backup is None:
        args.backup = str(_default_backup_path(datetime.now(timezone.utc)))
    if selected_mode == "restore" and args.backup:
        parser.error("--backup cannot be combined with --restore")
    try:
        from dotenv import load_dotenv
        load_dotenv()
        client, collections = _collections_from_mongo()
        try:
            result = run_repair(
                collections, mode=selected_mode,
                backup_path=args.backup,
                restore_path=args.restore,
            )
        finally:
            client.close()
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result["status"] in {"dry-run", "restored", "fresh"} else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
