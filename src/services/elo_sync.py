import os
import json
import time
import logging
from datetime import datetime, timezone

from src.constants import DISPLAY_MAPPING, SCORES_CACHE_TTL, _is_ko_round
from src.competitions import competition_document_id, find_competition_document, get_competition
from src.services.archive import (
    load_archive_from_db, upsert_archive_entry,
    build_archive_id_index, resolve_archive_id,
)
from src.services import espn_data
from src.services.prediction import PredictionService, _all_snapshots
from src.services.snapshots import select_t15_snapshot

logger = logging.getLogger(__name__)


def _remap_to_archive_ids(scores: list, archive: dict) -> list:
    """
    ESPN's fixture IDs don't match the IDs the odds engine used when entries
    were first written to the archive. Swap each ESPN match's `id` for the
    existing archive ID (resolved by home/away/date) so grading finds the
    right `pending` entry and `processed_matches.json` stays idempotent.
    Matches with no archive entry keep the ESPN id (retro-entry branch).
    """
    index = build_archive_id_index(archive)
    for s in scores:
        archived_id = resolve_archive_id(index, s.get("home_team"), s.get("away_team"), s.get("commence_time"))
        if archived_id:
            s["id"] = archived_id
    return scores


def _reconstruct_completed_entries(
    prediction_service,
    archive,
    changed_entries,
    MathEngine,
    competition,
    commence_times=None,
    cache_collection=None,
) -> tuple[int, int]:
    """Backfill completed tips, preferring saved pre-match odds over Elo."""
    commence_times = commence_times or {}
    reconstructed = 0
    snapshot_predictions = 0
    for mid, entry in archive.items():
        if entry.get("post_match_result", {}).get("status") != "completed":
            continue
        if entry.get("pre_match_snapshot") is not None:
            continue
        actual = entry.get("post_match_result", {}).get("actual_score")
        if not actual:
            continue

        metadata = entry.get("metadata") or {}
        home, away = metadata.get("home_team"), metadata.get("away_team")
        if not home or not away:
            continue
        match_context = dict(metadata)
        commence_time = metadata.get("commence_time") or commence_times.get(mid)
        match_context.setdefault("commence_time", commence_time)
        is_ko = bool(match_context.get("is_ko_phase", False))
        snapshot = None
        if cache_collection is not None and commence_time:
            snapshot = select_t15_snapshot(
                _all_snapshots(cache_collection, mid, competition),
                commence_time,
            )
        if snapshot:
            result = prediction_service.predict(
                odds=snapshot,
                elo=None,
                competition=competition,
                context=match_context,
                observed_at=snapshot.get("observed_at"),
                provenance={
                    "snapshot_id": snapshot.get("_id"),
                    "snapshot_bucket": snapshot.get("bucket"),
                },
            )
        else:
            result = prediction_service.reconstruct(
                home,
                away,
                commence_time=commence_time,
                competition=competition,
                is_ko=is_ko,
                context=match_context,
            )
        tip = result.get("model_tip")
        if not tip:
            continue

        prediction = entry.setdefault("prediction", {})
        bots = result.get("bots") or {}
        if snapshot and not bots:
            try:
                import pandas as pd
                matrix = result.get("score_matrix_df")
                xp = pd.DataFrame(result.get("xp_tips") or [])
                odds = result.get("source_inputs", {}).get("odds") or {}
                prob_over25 = None
                if odds.get("over25") and odds.get("under25"):
                    raw_over, raw_under = 1.0 / odds["over25"], 1.0 / odds["under25"]
                    prob_over25 = raw_over / (raw_over + raw_under)
                if matrix is not None and not xp.empty:
                    bots = prediction_service.math_engine.compute_bot_tips(
                        score_matrix=matrix,
                        base_xp_df=xp,
                        true_probs=result.get("probabilities") or {},
                        prob_over25=prob_over25,
                        home_team=home,
                        away_team=away,
                        match_id=mid,
                        is_ko_phase=is_ko,
                    )
            except Exception:
                bots = {}
        if (
            snapshot is None
            and prediction.get("top_tip") == tip
            and prediction.get("algo_reconstructed") is True
            and prediction.get("bots")
        ):
            continue

        prediction.update({
            "top_tip": tip,
            "model_tip": tip,
            "pool_tip": result.get("pool_tip"),
            "pool_status": result.get("pool_status", "unavailable"),
            "status": result.get("status"),
            "source_status": result.get("source_status", result.get("status")),
            "source": result.get("source"),
            "observed_at": result.get("observed_at"),
            "source_mode": result.get("source_mode"),
            "model_version": result.get("model_version"),
            "input_provenance": result.get("input_provenance"),
            "provenance": result.get("provenance"),
            "source_inputs": result.get("source_inputs"),
            "context": result.get("context", match_context),
            "max_xp": result.get("max_xp", 0),
            "algo_reconstructed": snapshot is None,
            "tip_source": "pre_match_odds_snapshot" if snapshot else "elo_reconstruction",
            "bots": bots,
        })
        if snapshot:
            entry["pre_match_snapshot"] = {
                "timestamp_recorded": snapshot.get("observed_at"),
                "odds": result.get("source_inputs", {}).get("odds"),
                "elo_state": None,
                "source_mode": result.get("source_mode"),
                "status": result.get("status"),
                "source_status": result.get("source_status", result.get("status")),
                "source": result.get("source"),
                "observed_at": result.get("observed_at"),
                "model_version": result.get("model_version"),
                "input_provenance": result.get("input_provenance"),
                "provenance": result.get("provenance"),
                "context": result.get("context", match_context),
            }
        post_match = entry.setdefault("post_match_result", {})
        post_match["algo_points"] = MathEngine.calculate_actual_points(tip, actual, is_ko)
        post_match["bot_points"] = {
            name: MathEngine.calculate_actual_points(info["tip"], actual, is_ko)
            for name, info in bots.items() if info.get("tip")
        }
        user_tip = prediction.get("user_tip")
        if user_tip:
            post_match["points_earned"] = MathEngine.calculate_actual_points(user_tip, actual, is_ko)
        changed_entries[mid] = entry
        if snapshot:
            snapshot_predictions += 1
        else:
            reconstructed += 1
    return reconstructed, snapshot_predictions


def perform_elo_sync(math_engine, odds_engine, cache_collection, archive_collection, data_dir, scores_cache_path, MathEngine, force: bool = False, competition=None) -> dict:
    print("Elo sync triggered...")
    competition = get_competition(competition)
    if competition.is_club_competition:
        # Club ratings are owned by the competition-scoped ClubElo cache.
        # Never reuse the WC CSV/history/processed files for a club league.
        document = find_competition_document(cache_collection, competition, "clubelo_ratings") or {}
        rows = document.get("rows") or []
        if competition.id == "ucl2026" and rows:
            try:
                import pandas as pd
                math_engine.elo_df = pd.DataFrame(rows)
            except Exception:
                pass
        observed_at = document.get("observed_at") or datetime.now(timezone.utc).isoformat()
        status = document.get("status") if document else "unavailable"
        if status not in {"fresh", "stale", "unavailable", "failed"}:
            status = "unavailable"
        error = document.get("error") or ("ClubElo ratings cache is unavailable" if status == "unavailable" else None)
        reconstructed = snapshot_predictions = 0
        if competition.id == "ucl2026":
            archive = load_archive_from_db(archive_collection, force=True)
            changed_entries = {}
            reconstructed, snapshot_predictions = _reconstruct_completed_entries(
                PredictionService(math_engine),
                archive,
                changed_entries,
                MathEngine,
                competition,
                cache_collection=cache_collection,
            )
            for mid, entry in changed_entries.items():
                upsert_archive_entry(archive_collection, mid, entry)
        return {
            "status": status,
            "source": document.get("source", "clubelo"),
            "observed_at": observed_at,
            "error": error,
            "provenance": {"source": document.get("source", "clubelo"), "observed_at": observed_at},
            "updates": reconstructed + snapshot_predictions,
            "snapshot_predictions": snapshot_predictions,
            "competition": competition.id,
        }
    prediction_service = PredictionService(math_engine)
    cache_document_id = lambda key: competition_document_id(competition, key)
    processed_json_path = os.path.join(data_dir, 'processed_matches.json')

    # Fetch and cache group standings from ESPN — reuse if < 30 min old
    try:
        _st_doc = find_competition_document(cache_collection, competition, "standings_cache")
        if not force and _st_doc and time.time() - _st_doc.get("timestamp", 0) < SCORES_CACHE_TTL:
            print("Standings: using cache (< 30 min old)")
        else:
            groups = espn_data.get_standings_groups(competition=competition)
            if groups:
                cache_collection.update_one(
                    {"_id": cache_document_id("standings_cache")},
                    {"$set": {"timestamp": time.time(), "data": groups}},
                    upsert=True,
                )
                print(f"Standings cached: {len(groups)} groups")
    except Exception as e:
        print(f"Standings fetch failed: {e}")

    try:
        scores_cache = {}
        try:
            _sc_doc = find_competition_document(cache_collection, competition, "scores_cache")
            if _sc_doc:
                scores_cache = {"timestamp": _sc_doc.get("timestamp", 0), "data": _sc_doc.get("data", [])}
        except Exception:
            if os.path.exists(scores_cache_path):
                try:
                    with open(scores_cache_path, 'r', encoding='utf-8') as f:
                        scores_cache = json.load(f)
                except Exception:
                    pass

        if not force and time.time() - scores_cache.get("timestamp", 0) < SCORES_CACHE_TTL:
            completed_matches = scores_cache.get("data", [])
            print("Elo sync: using cached scores (< 30 min old)")
        else:
            if force:
                print("Elo sync: force=true — bypassing scores cache")
            # Source: ESPN scoreboard (public, no quota). API-Football dropped
            # WC access on this tier, so its `get_completed_scores` returns 0.
            completed_matches = espn_data.get_completed_scores(days_from=30, competition=competition)
            completed_matches = _remap_to_archive_ids(completed_matches, load_archive_from_db(archive_collection))
            print(f"Elo sync: ESPN returned {len(completed_matches)} completed fixtures")
            try:
                cache_collection.update_one(
                    {"_id": cache_document_id("scores_cache")},
                    {"$set": {"timestamp": time.time(), "data": completed_matches}},
                    upsert=True,
                )
            except Exception as e:
                print(f"Scores cache write failed: {e}")

        updates = math_engine.update_elo_from_api_scores(
            api_scores=completed_matches,
            processed_matches_file=processed_json_path
        )
        if updates > 0:
            math_engine.elo_df.to_csv(math_engine.elo_csv_path, index=False)
            print(f"Elo sync completed: {updates} updates.")

            try:
                cache_collection.update_one(
                    {"_id": cache_document_id("elo_ratings")},
                    {"$set": {"rows": math_engine.elo_df.to_dict("records")}},
                    upsert=True,
                )
                if os.path.exists(processed_json_path):
                    with open(processed_json_path, 'r', encoding='utf-8') as pf:
                        processed_ids = json.load(pf)
                    cache_collection.update_one(
                        {"_id": cache_document_id("processed_match_ids")},
                        {"$set": {"ids": processed_ids}},
                        upsert=True,
                    )
                history_path = os.path.join(data_dir, 'elo_history.json')
                if os.path.exists(history_path):
                    with open(history_path, 'r', encoding='utf-8') as hf:
                        history_data = json.load(hf)
                    cache_collection.update_one(
                        {"_id": cache_document_id("elo_history")},
                        {"$set": {"data": history_data}},
                        upsert=True,
                    )
                print("Elo state persisted to MongoDB (ratings, history, processed IDs)")
            except Exception as persist_err:
                print(f"Warning: MongoDB persist failed (local files still updated): {persist_err}")

        # Post-match grading
        try:
            archive = load_archive_from_db(archive_collection)
            changed_entries = {}
            graded = 0
            retro = 0

            for match in completed_matches:
                match_id = match.get("id")
                if not match_id or not match.get("completed"):
                    continue

                home_team = match.get("home_team")
                away_team = match.get("away_team")
                scores = match.get("scores") or []
                home_score = next((s["score"] for s in scores if s["name"] == home_team), None)
                away_score = next((s["score"] for s in scores if s["name"] == away_team), None)
                if home_score is None or away_score is None:
                    continue
                try:
                    home_score = int(home_score)
                    away_score = int(away_score)
                except ValueError:
                    continue

                actual_score_str = f"{home_score}:{away_score}"

                if match_id not in archive:
                    new_entry = {
                        "metadata": {
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_disp": DISPLAY_MAPPING.get(home_team, home_team),
                            "away_disp": DISPLAY_MAPPING.get(away_team, away_team),
                            "is_ko_phase": _is_ko_round(match.get("round", "")),
                            "round": match.get("round", ""),
                            "commence_time": match.get("commence_time"),
                        },
                        "pre_match_snapshot": None,
                        "prediction": {"top_tip": None, "max_xp": None},
                        "post_match_result": {
                            "status": "completed",
                            "actual_score": actual_score_str,
                            "points_earned": None
                        }
                    }
                    archive[match_id] = new_entry
                    changed_entries[match_id] = new_entry
                    retro += 1
                    continue

                algo_tip  = archive[match_id]["prediction"].get("top_tip")
                user_tip  = archive[match_id]["prediction"].get("user_tip")
                is_ko     = archive[match_id]["metadata"]["is_ko_phase"]
                active_tip = user_tip if user_tip else algo_tip

                old_score = archive[match_id]["post_match_result"].get("actual_score")
                score_changed = old_score != actual_score_str

                if archive[match_id]["post_match_result"]["status"] == "pending" or score_changed:
                    archive[match_id]["post_match_result"]["status"]        = "completed"
                    archive[match_id]["post_match_result"]["actual_score"]  = actual_score_str
                    archive[match_id]["post_match_result"]["points_earned"] = (
                        MathEngine.calculate_actual_points(active_tip, actual_score_str, is_ko)
                        if active_tip else None
                    )
                    archive[match_id]["post_match_result"]["algo_points"] = (
                        MathEngine.calculate_actual_points(algo_tip, actual_score_str, is_ko)
                        if algo_tip else None
                    )
                    bots = archive[match_id]["prediction"].get("bots", {})
                    if bots:
                        archive[match_id]["post_match_result"]["bot_points"] = {
                            bot: MathEngine.calculate_actual_points(info["tip"], actual_score_str, is_ko)
                            for bot, info in bots.items() if info.get("tip")
                        }
                    changed_entries[match_id] = archive[match_id]
                    graded += 1
                    updates += 1

            # Backfill commence_time
            ct_map = {m.get('id'): m.get('commence_time') for m in completed_matches}
            try:
                mc = find_competition_document(cache_collection, competition, "matches_cache")
                if mc and mc.get("data"):
                    for mm in mc["data"]:
                        mid = mm.get("id") or mm.get("raw_match", {}).get("id")
                        ct = mm.get("commence_time") or mm.get("raw_match", {}).get("commence_time")
                        if mid and ct:
                            ct_map.setdefault(mid, ct)
            except Exception:
                pass

            for mid, entry in archive.items():
                if not entry.get("metadata", {}).get("commence_time") and ct_map.get(mid):
                    entry["metadata"]["commence_time"] = ct_map[mid]
                    changed_entries[mid] = entry

            # Name-based commence_time backfill from the FULL ESPN scoreboard —
            # covers pending/legacy entries whose id isn't in ct_map.
            try:
                from src.services.archive import _canon_team
                name_ct = {}
                for f in espn_data.get_scoreboard(competition=competition):
                    if f.get("commence_time"):
                        name_ct[(_canon_team(f["home_team"]), _canon_team(f["away_team"]))] = f["commence_time"]
                for mid, entry in archive.items():
                    meta = entry.get("metadata", {})
                    if meta.get("commence_time"):
                        continue
                    ct = name_ct.get((_canon_team(meta.get("home_team", "")), _canon_team(meta.get("away_team", ""))))
                    if ct:
                        entry["metadata"]["commence_time"] = ct
                        changed_entries[mid] = entry
            except Exception as e:
                print(f"commence_time name-backfill failed: {e}")

            # Backfill is_ko_phase
            round_map = {m.get("id"): m.get("round", "") for m in completed_matches if m.get("round")}
            try:
                mc = find_competition_document(cache_collection, competition, "matches_cache")
                if mc and mc.get("data"):
                    for mm in mc["data"]:
                        mid = mm.get("id") or mm.get("raw_match", {}).get("id")
                        rnd = mm.get("raw_match", {}).get("round", "")
                        if mid and rnd:
                            round_map.setdefault(mid, rnd)
            except Exception:
                pass

            ko_backfilled = 0
            for mid, entry in archive.items():
                meta = entry.get("metadata", {})
                round_str = meta.get("round", "") or round_map.get(mid, "")
                if round_str and _is_ko_round(round_str) and not meta.get("is_ko_phase"):
                    entry["metadata"]["is_ko_phase"] = True
                    if not meta.get("round"):
                        entry["metadata"]["round"] = round_str
                    actual = entry.get("post_match_result", {}).get("actual_score")
                    if actual and entry.get("post_match_result", {}).get("status") == "completed":
                        algo_tip = entry.get("prediction", {}).get("top_tip")
                        user_tip = entry.get("prediction", {}).get("user_tip")
                        if algo_tip:
                            entry["post_match_result"]["algo_points"] = MathEngine.calculate_actual_points(algo_tip, actual, True)
                        if user_tip:
                            entry["post_match_result"]["points_earned"] = MathEngine.calculate_actual_points(user_tip, actual, True)
                        bots = entry.get("prediction", {}).get("bots", {})
                        if bots:
                            entry["post_match_result"]["bot_points"] = {
                                name: MathEngine.calculate_actual_points(info["tip"], actual, True)
                                for name, info in bots.items() if info.get("tip")
                            }
                    changed_entries[mid] = entry
                    ko_backfilled += 1

            if ko_backfilled:
                print(f"KO phase backfilled: {ko_backfilled} matches updated to is_ko_phase=True.")

            reconstructed, _ = _reconstruct_completed_entries(
                prediction_service,
                archive,
                changed_entries,
                MathEngine,
                competition,
                ct_map,
            )

            for mid, entry in changed_entries.items():
                upsert_archive_entry(archive_collection, mid, entry)

            if graded:
                print(f"Archive grading completed: {graded} predictions scored.")
            if retro:
                print(f"Retroactive archive entries created: {retro} matches.")
            if reconstructed:
                print(f"Algo tips reconstructed: {reconstructed} matches (Elo-only pipeline).")
        except Exception as e:
            print(f"Archive grading failed: {e}")

        if updates > 0:
            return {"status": "success", "updates": updates}
        else:
            print("Elo sync completed: No new matches.")
            return {"status": "info", "message": "No new matches."}
    except Exception as e:
        print(f"Elo sync failed: {str(e)}")
        raise e
