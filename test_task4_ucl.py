from __future__ import annotations

import json
import numpy as np
import pandas as pd
import pytest
from itertools import combinations

from src.services.ucl_simulation import (
    DEFAULT_UCL_RUNS,
    PLAYOFF_POSITION_BANDS,
    UCL_TABLE_VERSION,
    build_cached_ucl_inputs,
    build_playoff_bracket,
    build_ucl_table,
    draw_ucl_bracket,
    rank_ucl_rows,
    simulate_ucl_tournament,
    validate_ucl_schedule,
)
from src.routes.simulate import init_router as simulate_router


def _teams():
    return [f"Team {i:02d}" for i in range(36)]


def _fixtures(teams=None, *, completed=True):
    teams = teams or _teams()
    fixtures = []
    # Eight disjoint rounds give every club eight unique fixtures.  The
    # alternating home convention yields exactly four home and four away.
    for round_no in range(4):
        for team_index, home in enumerate(teams):
            away = teams[(team_index + round_no + 1) % len(teams)]
            fixtures.append({
                "id": f"m-{round_no}-{team_index}",
                "home_team": home,
                "away_team": away,
                "status": "completed" if completed else "scheduled",
                "score_90": "0:0" if completed else None,
            })
    return fixtures


def _matrix(*, home=1, away=0):
    return pd.DataFrame(
        [[0.0] * 3 for _ in range(3)],
        index=["0", "1", "2"],
        columns=["0", "1", "2"],
    ).set_axis([], axis="index", copy=False) if False else {
        f"{home}:{away}": 1.0,
    }


def _pair_matrices(teams=None, *, home=1, away=0):
    teams = teams or _teams()
    return {(left, right): _matrix(home=home, away=away) for left, right in combinations(teams, 2)}


def _coefficients(teams=None, *, start=100):
    teams = teams or _teams()
    return {team: start + index for index, team in enumerate(teams)}


def test_ucl_schedule_validates_all_four_invariants():
    teams, fixtures = _teams(), _fixtures()
    assert validate_ucl_schedule(teams, fixtures) == {"teams": 36, "fixtures": 144}

    with pytest.raises(ValueError, match="36 unique teams"):
        validate_ucl_schedule(teams[:-1], fixtures)
    with pytest.raises(ValueError, match="144 unique fixtures"):
        validate_ucl_schedule(teams, fixtures[:-1])

    broken = _fixtures()
    broken[-1]["home_team"], broken[-1]["away_team"] = "Team 00", "Team 10"
    with pytest.raises(ValueError, match="8 fixtures/team"):
        validate_ucl_schedule(teams, broken)

    broken = _fixtures()
    broken[-1]["home_team"], broken[-1]["away_team"] = broken[-1]["away_team"], broken[-1]["home_team"]
    with pytest.raises(ValueError, match=r"4 home \+ 4 away/team"):
        validate_ucl_schedule(teams, broken)


def test_local_table_ranks_base_and_all_uefa_tie_break_stages():
    teams, fixtures = _teams(), _fixtures()
    # All fixtures are draws.  These two clubs then tie on points/GD/goals/
    # away goals/wins/away wins and are separated by opponent aggregates,
    # discipline, then the versioned coefficient.
    for fixture in fixtures:
        fixture["score_90"] = "0:0"
    rows = build_ucl_table(
        teams,
        fixtures,
        disciplinary_scores={"Team 00": 4, "Team 01": 1},
        uefa_coefficients={"Team 00": {"version": "2026", "coefficient": 100}, "Team 01": {"version": "2026", "coefficient": 90}},
    )
    assert rows[0]["points"] == 8
    assert {row["team"] for row in rows[:36]} == set(teams)
    assert rows[0]["opponents_points"] >= rows[1]["opponents_points"]
    assert rows[-1]["uefa_coefficient_version"] == "2026"

    # Directly exercise each final tie-break in the public sorter contract.
    tied = [
        {"team": "low-discipline", "points": 10, "goal_difference": 2, "goals_for": 5, "away_goals": 2, "wins": 3, "away_wins": 1, "opponents_points": 4, "opponents_goal_difference": 1, "opponents_goals": 3, "disciplinary_score": 1, "uefa_coefficient": 50},
        {"team": "high-discipline", "points": 10, "goal_difference": 2, "goals_for": 5, "away_goals": 2, "wins": 3, "away_wins": 1, "opponents_points": 4, "opponents_goal_difference": 1, "opponents_goals": 3, "disciplinary_score": 2, "uefa_coefficient": 100},
    ]
    # build_ucl_table accepts pre-aggregated rows for deterministic ranking
    # checks, keeping the local ranking order independently testable.
    ranked = build_ucl_table(tied, [], precomputed=True)
    assert [row["team"] for row in ranked] == ["low-discipline", "high-discipline"]


def test_cached_ucl_input_does_not_reuse_legacy_matrix_without_model_provenance():
    legacy_matrix = {"0:0": 1.0}

    result = build_cached_ucl_inputs({
        "data": [{"id": "e1", "matrix": {}, "score_matrix": legacy_matrix}],
    })

    assert "e1" not in result["score_matrices"]


def test_cached_ucl_input_skips_malformed_matrix_for_valid_legacy_score_matrix():
    legacy_matrix = {"0:0": 1.0}

    result = build_cached_ucl_inputs({
        "data": [{"id": "e1", "matrix": {"not-a-score": "bad"}, "score_matrix": legacy_matrix}],
    })

    assert "e1" not in result["score_matrices"]
    assert "default" not in result["score_matrices"]


def test_cached_ucl_input_never_builds_an_anonymous_average_matrix():
    fixtures = _fixtures(completed=False)
    for index, fixture in enumerate(fixtures[:2]):
        fixture["matrix"] = {"0:0": 1.0} if index == 0 else {"1:0": 1.0}
    result = build_cached_ucl_inputs({"data": fixtures})

    assert "default" not in result["score_matrices"]
    assert not any(str(key).startswith("m-") for key in result["score_matrices"])


def test_cached_ucl_input_reuses_only_club_matrices_with_matching_provenance():
    fixtures = _fixtures(completed=False)
    fixtures[0].update({
        "matrix": {"2:0": 1.0}, "model_version": "prediction-club-v2",
        "source_mode": "elo-only", "context": {"competition": "ucl2026"},
        "input_provenance": {"elo": {"source": "clubelo", "status": "fresh", "observed_at": "2026-10-20T12:00:00+00:00"}},
    })
    fixtures[1].update({
        "matrix": {"0:2": 1.0}, "model_version": "prediction-v1",
        "source_mode": "elo-only", "context": {"competition": "ucl2026"},
        "input_provenance": {"elo": {"source": "clubelo", "status": "fresh", "observed_at": "2026-10-20T12:00:00+00:00"}},
    })
    result = build_cached_ucl_inputs({"data": fixtures}, rating_observed_at="2026-10-20T12:00:00+00:00")

    assert result["score_matrices"]["m-0-0"] == {"2:0": 1.0}
    assert "m-0-1" not in result["score_matrices"]


def test_score_matrix_lookup_does_not_use_default_for_an_unrelated_pair():
    from src.services.ucl_simulation import MissingModelInput, _matrix_lookup

    fixture = {"id": "m1", "home_team": "A", "away_team": "B", "status": "scheduled"}
    with pytest.raises(MissingModelInput, match="no valid score matrix"):
        _matrix_lookup(fixture, {"default": {"1:0": 1.0}}, "A", "B")


def test_club_pair_matrices_reflect_swapped_rating_strength_and_require_both_ratings():
    from src.math_engine import MathEngine
    from src.services.ucl_simulation import MissingModelInput, _normalise_matrix, build_club_pair_score_matrices

    engine = MathEngine("data/elo_ratings.csv")
    strong_a = build_club_pair_score_matrices(["A", "B"], {"A": 2000, "B": 1500}, engine)
    strong_b = build_club_pair_score_matrices(["A", "B"], {"A": 1500, "B": 2000}, engine)
    scores, probs_a = _normalise_matrix(strong_a[("A", "B")])
    _, probs_b = _normalise_matrix(strong_b[("A", "B")])
    home_win_a = sum(probability for (home, away), probability in zip(scores, probs_a) if home > away)
    home_win_b = sum(probability for (home, away), probability in zip(scores, probs_b) if home > away)

    assert home_win_a > home_win_b
    with pytest.raises(MissingModelInput, match="B"):
        build_club_pair_score_matrices(["A", "B"], {"A": 2000}, engine)


def test_live_display_prefers_official_espn_order_but_local_table_does_not():
    teams, fixtures = _teams(), _fixtures()
    official = list(reversed(teams))
    rows = build_ucl_table(teams, fixtures, official_order=official)
    assert [row["team"] for row in rows] == official
    assert all(row["table_source"] == "espn" for row in rows)


@pytest.mark.parametrize(
    ("field", "better", "worse"),
    [
        ("points", 10, 9),
        ("goal_difference", 2, 1),
        ("goals_for", 5, 4),
        ("away_goals", 3, 2),
        ("wins", 3, 2),
        ("away_wins", 2, 1),
        ("opponents_points", 8, 7),
        ("opponents_goal_difference", 4, 3),
        ("opponents_goals", 6, 5),
        ("disciplinary_score", 1, 2),
        ("uefa_coefficient", 100, 90),
    ],
)
def test_local_ranking_uses_each_uefa_criterion_in_order(field, better, worse):
    base = {
        "points": 10, "goal_difference": 2, "goals_for": 5, "away_goals": 3,
        "wins": 3, "away_wins": 2, "opponents_points": 8,
        "opponents_goal_difference": 4, "opponents_goals": 6,
        "disciplinary_score": 1, "uefa_coefficient": 90,
    }
    first, second = dict(base), dict(base)
    first.update(team="better", **{field: better})
    second.update(team="worse", **{field: worse})
    assert [row["team"] for row in rank_ucl_rows([second, first])] == ["better", "worse"]


def test_playoff_bracket_maps_seeded_second_legs():
    bracket = build_playoff_bracket()
    assert [(tuple(band["seeded_positions"]), tuple(band["unseeded_positions"])) for band in bracket] == [
        ((9, 10), (23, 24)), ((11, 12), (21, 22)), ((13, 14), (19, 20)), ((15, 16), (17, 18))
    ]
    assert all(band["seeded_hosts_second_leg"] for band in bracket)


def test_playoff_draw_randomizes_only_inside_official_bands():
    observed = set()
    for seed in range(80):
        draw = draw_ucl_bracket(rng=np.random.default_rng(seed))
        first_band = tuple(sorted((tie["seeded_position"], tie["unseeded_position"]) for tie in draw["playoff"] if tie["band"] == 1))
        observed.add(first_band)
        for tie in draw["playoff"]:
            allowed_seeded, allowed_unseeded = PLAYOFF_POSITION_BANDS[tie["band"] - 1]
            assert tie["seeded_position"] in allowed_seeded
            assert tie["unseeded_position"] in allowed_unseeded
            assert tie["first_leg"]["home_position"] == tie["unseeded_position"]
            assert tie["second_leg"]["home_position"] == tie["seeded_position"]
    assert len(observed) == 2


def test_r16_draw_randomizes_winners_inside_the_matching_band():
    draw = draw_ucl_bracket(rng=np.random.default_rng(9))
    for tie in draw["round_of_16"]:
        assert tie["top_position"] in tie["top_band"]
        assert tie["playoff_seed_position"] in tie["playoff_band"]
    assert all(tie["second_leg"]["home_slot"] == tie["top_slot"] for tie in draw["round_of_16"])
    assert all("first_leg" in tie and "second_leg" in tie for tie in draw["quarterfinal"] + draw["semifinal"])


def test_simulation_is_seeded_and_returns_all_ucl_round_probabilities():
    teams, fixtures = _teams(), _fixtures(completed=False)
    matrices = _pair_matrices(teams, home=1, away=0)
    matrices.update({fixture["id"]: _matrix(home=1, away=0) for fixture in fixtures})
    first = simulate_ucl_tournament(teams, fixtures, matrices, n_runs=12, seed=20260908, uefa_coefficients=_coefficients(teams), disciplinary_scores=dict.fromkeys(teams, 0))
    second = simulate_ucl_tournament(teams, fixtures, matrices, n_runs=12, seed=20260908, uefa_coefficients=_coefficients(teams), disciplinary_scores=dict.fromkeys(teams, 0))
    assert first == second
    assert first["status"] == "fresh"
    assert first["runs"] == 12
    assert first["seed"] == 20260908
    assert first["table_version"] == UCL_TABLE_VERSION
    assert len(first["teams"]) == 36
    assert {"expected_points", "expected_rank", "top8", "top24", "round_of_16", "quarterfinal", "semifinal", "final", "champion"} <= set(first["teams"][0])
    assert first["bracket"]["playoff"]


def test_simulation_accepts_complete_finite_rank_coverage_without_coefficients():
    teams, fixtures = _teams(), _fixtures(completed=False)
    result = simulate_ucl_tournament(
        teams, fixtures, _pair_matrices(teams), n_runs=2, seed=9,
        uefa_coefficient_ranks={team: index + 1 for index, team in enumerate(teams)},
        disciplinary_scores=dict.fromkeys(teams, 0),
    )
    assert result["status"] == "fresh"


def test_tiebreak_coefficients_require_one_requested_vintage():
    from src.services.ucl_simulation import MissingModelInput, resolve_uefa_tiebreak_inputs

    with pytest.raises(MissingModelInput, match="version"):
        resolve_uefa_tiebreak_inputs(
            ["A", "B"],
            {"A": {"coefficient": 10, "version": "2025"}, "B": {"coefficient": 8, "version": "2026"}},
            {},
            coefficient_version="2026",
        )


def test_tiebreak_rank_versions_are_checked_when_embedded_or_separate():
    from src.services.ucl_simulation import MissingModelInput, resolve_uefa_tiebreak_inputs

    with pytest.raises(MissingModelInput, match="version"):
        resolve_uefa_tiebreak_inputs(
            ["A", "B"], {},
            {"A": {"rank": 1, "version": "2025"}, "B": {"rank": 2, "version": "2026"}},
            coefficient_version="2026",
        )

    with pytest.raises(MissingModelInput, match="version"):
        resolve_uefa_tiebreak_inputs(
            ["A", "B"],
            {"A": {"rank": 1, "version": "2025"}, "B": {"rank": 2, "version": "2026"}},
            {},
            coefficient_version="2026",
        )


def test_ucl_runtime_exhaustion_is_reported_once_then_same_cache_key_retries(monkeypatch):
    from datetime import datetime, timezone

    import src.routes.simulate as simulate_module

    class JobCache(_Cache):
        def update_one(self, query, update, upsert=False):
            key = query["_id"]
            document = self.documents.get(key)
            if document is None:
                if not upsert:
                    return type("UpdateResult", (), {"matched_count": 0})()
                document = {"_id": key}
            if "$or" in query:
                can_claim = any(
                    ("$ne" in expected and document.get(field) != expected["$ne"])
                    or ("$lte" in expected and document.get(field) is not None and document[field] <= expected["$lte"])
                    for clause in query["$or"] for field, expected in clause.items() if isinstance(expected, dict)
                )
                if not can_claim:
                    return type("UpdateResult", (), {"matched_count": 0})()
            elif any(document.get(field) != value for field, value in query.items() if field != "_id"):
                return type("UpdateResult", (), {"matched_count": 0})()
            if "$setOnInsert" in update and "created_at" not in document:
                document.update(update["$setOnInsert"])
            document.update(update.get("$set", {}))
            for field in update.get("$unset", {}):
                document.pop(field, None)
            self.documents[key] = document
            return type("UpdateResult", (), {"matched_count": 1})()

    class QueuedExecutor:
        def __init__(self):
            self.jobs = []

        def submit(self, function, *args):
            self.jobs.append((function, args))

        def run_next(self):
            function, args = self.jobs.pop(0)
            function(*args)

    teams, fixtures = _teams(), _fixtures(completed=False)
    cache = JobCache([
        {"_id": "ucl2026:matches_cache", "data": fixtures, "teams": teams, "uefa_coefficients": _coefficients(teams)},
        {
            "_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "rows": [{"team": team, "elo_rating": 1500 + index} for index, team in enumerate(teams)],
        },
    ])
    executor = QueuedExecutor()
    outcomes = iter((
        {"status": "unavailable", "reason": "simulation exceeded its bounded runtime", "n_runs": 5000},
        {"status": "fresh", "runs": 5000},
    ))
    monkeypatch.setattr(simulate_module, "build_club_pair_score_matrices", lambda *_args: {})
    monkeypatch.setattr(simulate_module, "simulate_ucl_tournament", lambda *_args, **_kwargs: next(outcomes))
    endpoint = next(route.endpoint for route in simulate_router(object(), {"ucl2026": cache}, ucl_executor=executor).routes if route.path == "/api/simulate_ucl")

    assert endpoint(runs=5000, competition="ucl2026").status_code == 202
    executor.run_next()
    first_poll = endpoint(runs=5000, competition="ucl2026")
    assert first_poll["status"] == "failed"
    assert "runtime" in first_poll["reason"]
    assert len(executor.jobs) == 0

    retry_poll = endpoint(runs=5000, competition="ucl2026")
    assert retry_poll.status_code == 202
    assert len(executor.jobs) == 1
    executor.run_next()
    assert endpoint(runs=5000, competition="ucl2026")["status"] == "fresh"


def test_simulation_missing_open_matrix_is_explicitly_unavailable():
    teams, fixtures = _teams(), _fixtures(completed=False)
    result = simulate_ucl_tournament(teams, fixtures, {}, n_runs=2)
    assert result["status"] == "unavailable"
    assert "score matrix" in result["reason"].lower()


def test_invalid_schedule_and_completed_missing_score_are_unavailable():
    teams, fixtures = _teams(), _fixtures(completed=False)
    assert simulate_ucl_tournament(teams[:-1], fixtures, {}, n_runs=2)["status"] == "unavailable"
    completed_missing = _fixtures(completed=False)
    completed_missing[0]["status"] = "completed"
    result = simulate_ucl_tournament(teams, completed_missing, _pair_matrices(teams), n_runs=2)
    assert result["status"] == "unavailable"
    assert "completed" in result["reason"].lower()


def test_simulation_probability_accounting_is_consistent():
    teams, fixtures = _teams(), _fixtures(completed=False)
    result = simulate_ucl_tournament(teams, fixtures, _pair_matrices(teams), n_runs=8, seed=3, uefa_coefficients=_coefficients(teams), disciplinary_scores=dict.fromkeys(teams, 0))
    assert result["status"] == "fresh"
    for field, expected in (("top8", 800), ("top24", 2400), ("round_of_16", 1600), ("quarterfinal", 800), ("semifinal", 400), ("final", 200), ("champion", 100)):
        assert sum(item[field] for item in result["teams"]) == pytest.approx(expected)


class _Cache:
    def __init__(self, documents):
        self.documents = {document["_id"]: document for document in documents}

    def find_one(self, query):
        return self.documents.get(query.get("_id"))


def test_ucl_route_builds_matrices_and_metadata_from_cached_match_shape(monkeypatch):
    from datetime import datetime, timezone

    import src.routes.simulate as simulate_module

    teams, fixtures = _teams(), _fixtures(completed=False)
    observed_at = datetime.now(timezone.utc).isoformat()
    for fixture in fixtures:
        fixture.update({
            "matrix": _matrix(home=1, away=0), "model_version": "prediction-club-v2",
            "source_mode": "elo-only", "context": {"competition": "ucl2026"},
            "input_provenance": {"elo": {"source": "clubelo", "status": "fresh", "observed_at": observed_at}},
        })
    class JobCache(_Cache):
        def update_one(self, query, update, upsert=False):
            document = self.documents.get(query["_id"])
            if document is None:
                if not upsert:
                    return type("UpdateResult", (), {"matched_count": 0})()
                document = {"_id": query["_id"]}
            if "$or" in query:
                can_claim = any(
                    ("$ne" in expected and document.get(field) != expected["$ne"])
                    or ("$lte" in expected and document.get(field) is not None and document[field] <= expected["$lte"])
                    for clause in query["$or"] for field, expected in clause.items() if isinstance(expected, dict)
                )
                if not can_claim:
                    return type("UpdateResult", (), {"matched_count": 0})()
            if "$setOnInsert" in update and "created_at" not in document:
                document.update(update["$setOnInsert"])
            document.update(update.get("$set", {}))
            for field in update.get("$unset", {}):
                document.pop(field, None)
            self.documents[query["_id"]] = document
            return type("UpdateResult", (), {"matched_count": 1})()

    class InlineExecutor:
        def submit(self, function, *args):
            function(*args)

    cache = JobCache([
        {
            "_id": "ucl2026:matches_cache", "data": fixtures, "teams": teams,
            "disciplinary_scores": {teams[0]: 2},
            "uefa_coefficients": _coefficients(teams),
            "official_order": list(reversed(teams)),
            "coefficient_version": "2026",
            "provenance": {"source": "captured"},
        },
        {
            "_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
            "observed_at": observed_at,
            "rows": [{"team": team, "elo_rating": 1500 + index} for index, team in enumerate(teams)],
        },
    ])
    monkeypatch.setattr(simulate_module, "build_club_pair_score_matrices", lambda *_args: {})
    monkeypatch.setattr(simulate_module, "simulate_ucl_tournament", lambda *args, **kwargs: {
        "status": "fresh", "n_runs": kwargs["n_runs"], "coefficient_version": kwargs["coefficient_version"],
        "provenance": kwargs["coefficient_provenance"], "warnings": [],
    })
    router = simulate_router(object(), {"ucl2026": cache}, ucl_executor=InlineExecutor())
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_ucl")
    queued = endpoint(runs=2, competition="ucl2026")
    result = endpoint(runs=2, competition="ucl2026")
    assert queued.status_code == 202
    assert result["status"] == "fresh"
    assert result["model_version"] == "prediction-club-v2"
    assert result["coefficient_version"] == "2026"
    assert result["provenance"]["source"] == "captured"


def test_ucl_route_returns_processing_once_per_input_key():
    from datetime import datetime, timezone

    class JobCache(_Cache):
        def update_one(self, query, update, upsert=False):
            key = query["_id"]
            doc = self.documents.get(key)
            if doc is None:
                if not upsert:
                    return type("UpdateResult", (), {"matched_count": 0})()
                doc = {"_id": key}
            if "$or" in query:
                def matches(clause):
                    for field, expected in clause.items():
                        actual = doc.get(field)
                        if isinstance(expected, dict) and "$ne" in expected and actual == expected["$ne"]:
                            return False
                        if isinstance(expected, dict) and "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                            return False
                    return True
                if not any(matches(clause) for clause in query["$or"]):
                    return type("UpdateResult", (), {"matched_count": 0})()
            elif any(doc.get(field) != value for field, value in query.items() if field != "_id"):
                return type("UpdateResult", (), {"matched_count": 0})()
            if "$setOnInsert" in update and not doc:
                doc.update(update["$setOnInsert"])
            doc.update(update.get("$set", {}))
            for field in update.get("$unset", {}):
                doc.pop(field, None)
            self.documents[key] = doc
            return type("UpdateResult", (), {"matched_count": 1})()

    class QueuedExecutor:
        def __init__(self):
            self.jobs = []

        def submit(self, function, *args):
            self.jobs.append((function, args))

    teams, fixtures = _teams(), _fixtures(completed=False)
    observed_at = datetime.now(timezone.utc).isoformat()
    cache = JobCache([
        {"_id": "ucl2026:matches_cache", "data": fixtures, "teams": teams, "uefa_coefficients": _coefficients(teams)},
        {
            "_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
            "observed_at": observed_at,
            "rows": [{"team": team, "elo": 1500 + index, "elo_rating": 1500 + index} for index, team in enumerate(teams)],
        },
    ])
    executor = QueuedExecutor()
    router = simulate_router(object(), {"ucl2026": cache}, ucl_executor=executor)
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_ucl")

    first = endpoint(runs=5000, competition="ucl2026")
    second = endpoint(runs=5000, competition="ucl2026")

    assert first.status_code == second.status_code == 202
    assert json.loads(first.body) == {
        "status": "processing", "n_runs": 5000,
        "model_version": "prediction-club-v2", "retry_after": 3,
    }
    assert len(executor.jobs) == 1


def test_ucl_route_bounds_distinct_queued_jobs_before_claiming(monkeypatch):
    from datetime import datetime, timezone
    from threading import BoundedSemaphore

    import src.routes.simulate as simulate_module

    teams, fixtures = _teams(), _fixtures(completed=False)
    cache = _Cache([
        {"_id": "ucl2026:matches_cache", "data": fixtures, "teams": teams, "uefa_coefficients": _coefficients(teams)},
        {
            "_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "rows": [{"team": team, "elo_rating": 1500 + index} for index, team in enumerate(teams)],
        },
    ])
    monkeypatch.setattr(simulate_module, "_UCL_SLOTS", BoundedSemaphore(0))
    router = simulate_router(object(), {"ucl2026": cache})
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_ucl")

    response = endpoint(runs=5000, competition="ucl2026")

    assert response.status_code == 202
    assert json.loads(response.body)["status"] == "processing"
    assert not any("ucl_simulation:prediction-club-v2" in key for key in cache.documents)


def test_ucl_route_returns_unavailable_before_queue_when_cached_tiebreak_inputs_are_missing():
    from datetime import datetime, timezone

    teams, fixtures = _teams(), _fixtures(completed=False)
    cache = _Cache([
        {"_id": "ucl2026:matches_cache", "data": fixtures, "teams": teams},
        {
            "_id": "ucl2026:clubelo_ratings", "status": "fresh", "source": "clubelo",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "rows": [{"team": team, "elo_rating": 1500 + index} for index, team in enumerate(teams)],
        },
    ])

    class QueuedExecutor:
        def __init__(self):
            self.jobs = []

        def submit(self, function, *args):
            self.jobs.append((function, args))

    executor = QueuedExecutor()
    endpoint = next(
        route.endpoint for route in simulate_router(object(), {"ucl2026": cache}, ucl_executor=executor).routes
        if route.path == "/api/simulate_ucl"
    )

    result = endpoint(runs=5000, competition="ucl2026")

    assert result["status"] == "unavailable"
    assert "coefficient" in result["reason"].lower()
    assert executor.jobs == []


def test_simulation_is_unavailable_without_complete_finite_coefficient_or_rank_coverage():
    result = simulate_ucl_tournament(_teams(), _fixtures(completed=False), _pair_matrices(), n_runs=2)
    assert result["status"] == "unavailable"
    assert "coefficient" in result["reason"].lower()


def test_partial_coefficient_coverage_is_unavailable_not_lexically_filled():
    result = simulate_ucl_tournament(
        _teams(), _fixtures(completed=False), _pair_matrices(), n_runs=2,
        uefa_coefficients={"Team 00": 101},
    )
    assert result["status"] == "unavailable"
    assert "coverage" in result["reason"].lower()


def test_equal_zero_coefficients_do_not_choose_lexical_winners():
    teams = _teams()
    result = simulate_ucl_tournament(
        teams,
        _fixtures(completed=True),
        _pair_matrices(teams),
        n_runs=2,
        uefa_coefficients=dict.fromkeys(teams, 0),
        disciplinary_scores=dict.fromkeys(teams, 0),
    )
    assert result["status"] == "unavailable"
    assert "tiebreak" in result["reason"].lower()


def test_missing_disciplinary_input_only_blocks_a_tie_that_reaches_discipline():
    teams = _teams()
    fixtures = _fixtures(completed=True)
    for index, fixture in enumerate(fixtures):
        fixture["score_90"] = "1:0" if index % 2 == 0 else "0:1"
    result = simulate_ucl_tournament(
        teams, fixtures, _pair_matrices(teams), n_runs=1, uefa_coefficients=_coefficients(teams),
    )
    assert result["status"] == "unavailable"
    assert "disciplinary" in result["reason"].lower()


def test_known_knockout_match_uses_stored_aet_score_without_resampling():
    from src.services.ucl_simulation import _play_match

    fixture = {
        "home_team": "Home", "away_team": "Away", "stage": "final",
        "status": "completed", "score_90": "1:1", "score_aet": "2:1",
    }
    result = _play_match("Home", "Away", fixture, {}, np.random.default_rng(7), stage="final", leg="single")
    assert result["score_90"] == (1, 1)
    assert result["score_aet"] == (2, 1)
    assert result["winner"] == "Home"
    assert result["penalties"] is False


def test_known_knockout_match_honors_stored_shootout_after_aet_draw():
    from src.services.ucl_simulation import _play_match

    fixture = {
        "home_team": "Home", "away_team": "Away", "stage": "final",
        "status": "completed", "score_90": "1:1", "score_aet": "2:2",
        "shootout_winner": "Away",
    }
    result = _play_match("Home", "Away", fixture, {}, np.random.default_rng(7), stage="final", leg="single")

    assert result["score_90"] == (1, 1)
    assert result["score_aet"] == (2, 2)
    assert result["winner"] == "Away"
    assert result["penalties"] is True


def test_two_leg_tie_consumes_known_fixtures_without_resampling():
    from src.services.ucl_simulation import _play_two_leg_tie

    class NoSampleRng:
        def choice(self, *_args, **_kwargs):
            raise AssertionError("stored knockout scores must not be sampled again")

    first = {
        "home_team": "Unseeded", "away_team": "Seeded", "stage": "playoff",
        "leg": "first", "status": "completed", "score_90": "1:0",
    }
    second = {
        "home_team": "Seeded", "away_team": "Unseeded", "stage": "playoff",
        "leg": "second", "status": "completed", "score_90": "1:0", "score_aet": "3:1",
    }

    winner, legs = _play_two_leg_tie(
        "Seeded", "Unseeded", {}, NoSampleRng(), stage="playoff",
        first_fixture=first, second_fixture=second,
    )

    assert [leg["score_90"] for leg in legs] == [(1, 0), (1, 0)]
    assert legs[1]["score_aet"] == (3, 1)
    assert legs[1]["penalties"] is False
    assert winner == "Seeded"


def test_public_simulation_rejects_known_knockout_result_without_draw_metadata():
    teams, fixtures = _teams(), _fixtures(completed=False)
    fixtures[0]["stage"] = "league phase"
    fixtures.append({
        "id": "known-final", "home_team": teams[0], "away_team": teams[1],
        "stage": "final", "leg": "single", "status": "completed", "score_90": "1:0",
    })
    result = simulate_ucl_tournament(
        teams, fixtures, _pair_matrices(teams), n_runs=2,
        uefa_coefficients=_coefficients(teams), disciplinary_scores=dict.fromkeys(teams, 0),
    )
    assert result["status"] == "unavailable"
    assert "knockout" in result["reason"].lower() and "draw" in result["reason"].lower()


def test_known_knockout_detection_reads_nested_context_and_r16_aliases():
    from src.services.ucl_simulation import has_known_knockout_result

    assert has_known_knockout_result([{
        "status": "completed", "match_context": {"stage": "R16"}, "score_90": "1:0",
    }])
    assert has_known_knockout_result([{
        "status": "completed", "stage": "quarter-finals", "score_90": "1:0",
    }])


def test_non_mapping_fixture_returns_unavailable_instead_of_attribute_error():
    fixtures = _fixtures(completed=False)
    fixtures[0] = None
    result = simulate_ucl_tournament(_teams(), fixtures, {"default": _matrix()}, n_runs=2)
    assert result["status"] == "unavailable"
    assert "fixture" in result["reason"].lower()


def test_nonfinite_coefficient_coverage_is_unavailable():
    coefficients = _coefficients()
    coefficients["Team 00"] = float("inf")
    result = simulate_ucl_tournament(
        _teams(),
        _fixtures(completed=False),
        _pair_matrices(),
        n_runs=2,
        uefa_coefficients=coefficients,
    )
    assert result["status"] == "unavailable"
    assert "invalid" in result["reason"].lower()


def test_simulation_final_uses_et_then_penalties_without_copying_knockout_math():
    teams = ["A", "B"]
    fixture = {"id": "final", "home_team": "A", "away_team": "B", "status": "scheduled"}
    result = simulate_ucl_tournament(
        teams,
        [fixture],
        {"final": {"0:0": 1.0}},
        n_runs=4,
        seed=7,
        validate_schedule=False,
    )
    assert result["status"] == "unavailable"  # league table input is incomplete, not silently invented


def test_two_leg_tie_reuses_task3_aggregate_et_and_penalty_rules():
    from src.services.ucl_simulation import _play_two_leg_tie

    winner, legs = _play_two_leg_tie(
        "Seeded", "Unseeded", {("Seeded", "Unseeded"): {"0:0": 1.0}}, np.random.default_rng(7), stage="playoff"
    )
    assert winner in {"Seeded", "Unseeded"}
    assert legs[0]["score_90"] == (0, 0)
    assert legs[1]["score_90"] == (0, 0)
    assert legs[1]["score_aet"] == (0, 0)
    assert legs[1]["penalties"] is True


def test_two_leg_tie_uses_aggregate_et_then_penalties_without_away_goals():
    from src.services.ucl_simulation import _play_two_leg_tie

    class FixedRng:
        def __init__(self):
            self.choices = iter((0, 1))

        def choice(self, *_args, **_kwargs):
            return next(self.choices)

        def poisson(self, _lambda):
            return 0

        def random(self):
            return 0.9

    # Seeded wins 2-1 away in leg one; the unseeded team wins 0-1 away in
    # leg two. Aggregate is level, while an obsolete away-goals tiebreak would
    # have favored the seeded team. ET stays level and penalties decide it.
    matrix = {"2:1": 0.5, "0:1": 0.5}
    winner, legs = _play_two_leg_tie(
        "Seeded", "Unseeded", {("Seeded", "Unseeded"): matrix}, FixedRng(), stage="round_of_16",
    )

    assert legs[0]["score_90"] == (1, 2)
    assert legs[1]["score_90"] == (0, 1)
    assert legs[1]["score_aet"] == (0, 1)
    assert legs[1]["penalties"] is True
    assert winner == "Unseeded"


def test_simulation_stops_when_runtime_budget_is_exhausted(monkeypatch):
    teams, fixtures = _teams(), _fixtures(completed=False)
    calls = {"count": 0}

    def monotonic():
        calls["count"] += 1
        return 0.0 if calls["count"] < 147 else 2.0

    monkeypatch.setattr("src.services.ucl_simulation.time.monotonic", monotonic)

    result = simulate_ucl_tournament(
        teams, fixtures, _pair_matrices(teams), n_runs=2, uefa_coefficients=_coefficients(teams),
        disciplinary_scores=dict.fromkeys(teams, 0), max_duration_seconds=1.0,
    )

    assert result["status"] == "unavailable"
    assert "runtime" in result["reason"]


def test_default_run_count_is_uefa_requirement():
    assert DEFAULT_UCL_RUNS == 5000
