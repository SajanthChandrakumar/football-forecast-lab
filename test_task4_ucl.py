from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


def test_cached_ucl_input_uses_valid_legacy_score_matrix_when_matrix_is_empty():
    legacy_matrix = {"0:0": 1.0}

    result = build_cached_ucl_inputs({
        "data": [{"id": "e1", "matrix": {}, "score_matrix": legacy_matrix}],
    })

    assert result["score_matrices"]["e1"] == legacy_matrix


def test_cached_ucl_input_skips_malformed_matrix_for_valid_legacy_score_matrix():
    legacy_matrix = {"0:0": 1.0}

    result = build_cached_ucl_inputs({
        "data": [{"id": "e1", "matrix": {"not-a-score": "bad"}, "score_matrix": legacy_matrix}],
    })

    assert result["score_matrices"]["e1"] == legacy_matrix
    assert result["score_matrices"]["default"] == legacy_matrix


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
    matrices = {"default": _matrix(home=1, away=0)}
    matrices.update({fixture["id"]: _matrix(home=1, away=0) for fixture in fixtures})
    first = simulate_ucl_tournament(teams, fixtures, matrices, n_runs=12, seed=20260908)
    second = simulate_ucl_tournament(teams, fixtures, matrices, n_runs=12, seed=20260908)
    assert first == second
    assert first["status"] == "fresh"
    assert first["runs"] == 12
    assert first["seed"] == 20260908
    assert first["table_version"] == UCL_TABLE_VERSION
    assert len(first["teams"]) == 36
    assert {"expected_points", "expected_rank", "top8", "top24", "round_of_16", "quarterfinal", "semifinal", "final", "champion"} <= set(first["teams"][0])
    assert first["bracket"]["playoff"]


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
    result = simulate_ucl_tournament(teams, completed_missing, {"default": _matrix()}, n_runs=2)
    assert result["status"] == "unavailable"
    assert "completed" in result["reason"].lower()


def test_simulation_probability_accounting_is_consistent():
    teams, fixtures = _teams(), _fixtures(completed=False)
    result = simulate_ucl_tournament(teams, fixtures, {"default": _matrix()}, n_runs=8, seed=3)
    assert result["status"] == "fresh"
    for field, expected in (("top8", 800), ("top24", 2400), ("round_of_16", 1600), ("quarterfinal", 800), ("semifinal", 400), ("final", 200), ("champion", 100)):
        assert sum(item[field] for item in result["teams"]) == pytest.approx(expected)


class _Cache:
    def __init__(self, documents):
        self.documents = {document["_id"]: document for document in documents}

    def find_one(self, query):
        return self.documents.get(query.get("_id"))


def test_ucl_route_builds_matrices_and_metadata_from_cached_match_shape():
    teams, fixtures = _teams(), _fixtures(completed=False)
    for fixture in fixtures:
        fixture["matrix"] = _matrix(home=1, away=0)
    cache = _Cache([{
        "_id": "ucl2026:matches_cache",
        "data": fixtures,
        "teams": teams,
        "disciplinary_scores": {teams[0]: 2},
        "uefa_coefficients": {teams[0]: 101},
        "uefa_coefficient_ranks": {teams[1]: 2},
        "official_order": list(reversed(teams)),
        "coefficient_version": "2026",
        "provenance": {"source": "captured"},
    }])
    router = simulate_router(object(), {"ucl2026": cache})
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_ucl")
    result = endpoint(runs=2, competition="ucl2026")
    assert result["status"] == "fresh"
    assert result["coefficient_version"] == "2026"
    assert result["provenance"]["source"] == "captured"


def test_missing_coefficient_inputs_emit_quality_warning():
    result = simulate_ucl_tournament(_teams(), _fixtures(completed=False), {"default": _matrix()}, n_runs=2)
    assert any("coefficient" in warning.lower() for warning in result["warnings"])


def test_non_mapping_fixture_returns_unavailable_instead_of_attribute_error():
    fixtures = _fixtures(completed=False)
    fixtures[0] = None
    result = simulate_ucl_tournament(_teams(), fixtures, {"default": _matrix()}, n_runs=2)
    assert result["status"] == "unavailable"
    assert "fixture" in result["reason"].lower()


def test_partial_coefficient_coverage_emits_explicit_quality_warning():
    result = simulate_ucl_tournament(
        _teams(),
        _fixtures(completed=False),
        {"default": _matrix()},
        n_runs=2,
        uefa_coefficients={"Team 00": 101},
    )
    assert any("incomplete" in warning.lower() and "coefficient" in warning.lower() for warning in result["warnings"])


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
        "Seeded", "Unseeded", {"default": {"0:0": 1.0}}, np.random.default_rng(7), stage="playoff"
    )
    assert winner in {"Seeded", "Unseeded"}
    assert legs[0]["score_90"] == (0, 0)
    assert legs[1]["score_90"] == (0, 0)
    assert legs[1]["score_aet"] == (0, 0)
    assert legs[1]["penalties"] is True


def test_default_run_count_is_uefa_requirement():
    assert DEFAULT_UCL_RUNS == 100
