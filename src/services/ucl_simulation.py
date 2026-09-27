"""Local UCL league-table and tournament simulation.

The service accepts provider-shaped fixtures, but does not fetch providers or
invent ratings.  A stored score matrix is the only input used for an open
match.  WC simulation remains in :mod:`src.services.monte_carlo`.
"""

from __future__ import annotations

from collections import defaultdict
from numbers import Real
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from src.services.prediction import (
    advancement_probabilities,
    build_match_context,
    extra_time_eligible_for_score,
)


DEFAULT_UCL_RUNS = 100
DEFAULT_UCL_SEED = 20260908
UCL_TEAM_COUNT = 36
UCL_MATCH_COUNT = 144
UCL_FIXTURES_PER_TEAM = 8
UCL_HOME_FIXTURES = 4
UCL_AWAY_FIXTURES = 4
UCL_TABLE_VERSION = "ucl-table-2026.1"
UCL_COEFFICIENT_VERSION = "2026"

RANKING_CRITERIA = (
    "points",
    "goal_difference",
    "goals_for",
    "away_goals",
    "wins",
    "away_wins",
    "opponents_points",
    "opponents_goal_difference",
    "opponents_goals",
    "disciplinary_score",
    "uefa_coefficient",
)

PLAYOFF_POSITION_BANDS = (
    ((9, 10), (23, 24)),
    ((11, 12), (21, 22)),
    ((13, 14), (19, 20)),
    ((15, 16), (17, 18)),
)

# The four position bands are the official draw path.  A lower-ranked team
# in a band is not allowed to escape that band's quarter of the bracket.
R16_POSITION_BANDS = (
    ((1, 2), (15, 16)),
    ((3, 4), (13, 14)),
    ((5, 6), (11, 12)),
    ((7, 8), (9, 10)),
)

# Legacy import compatibility. Runtime draws use PLAYOFF_POSITION_BANDS.
PLAYOFF_POSITION_PAIRS = tuple(
    (seeded[0], unseeded[0])
    for seeded, unseeded in PLAYOFF_POSITION_BANDS
)


class MissingModelInput(ValueError):
    """Raised internally when an open match has no valid stored matrix."""


def _score_pair(value: Any) -> tuple[int, int] | None:
    if isinstance(value, str):
        parts = value.strip().split(":")
        if len(parts) == 2 and all(part.strip().isdigit() for part in parts):
            return int(parts[0]), int(parts[1])
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            home, away = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        if home >= 0 and away >= 0:
            return home, away
    if isinstance(value, Mapping):
        for home_key, away_key in (("home", "away"), ("home_score", "away_score")):
            if home_key in value and away_key in value:
                return _score_pair((value[home_key], value[away_key]))
    return None


def _fixture_teams(fixture: Mapping[str, Any]) -> tuple[str, str]:
    if not isinstance(fixture, Mapping):
        raise ValueError("Fixture must be a mapping")
    home = fixture.get("home_team", fixture.get("home"))
    away = fixture.get("away_team", fixture.get("away"))
    if not home or not away:
        raise ValueError("Fixture must contain home_team and away_team")
    return str(home), str(away)


def _fixture_id(fixture: Mapping[str, Any], index: int) -> str:
    value = fixture.get("id", fixture.get("match_id", fixture.get("event_id")))
    return str(value) if value is not None else f"{_fixture_teams(fixture)[0]}::{_fixture_teams(fixture)[1]}::{index}"


def validate_ucl_schedule(teams: Sequence[str], fixtures: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Validate the fixed 36-team, eight-match UCL league phase shape."""
    team_list = [str(team) for team in teams]
    if len(team_list) != UCL_TEAM_COUNT or len(set(team_list)) != UCL_TEAM_COUNT:
        raise ValueError("UCL invariant violated: 36 unique teams required")
    if len(fixtures) != UCL_MATCH_COUNT:
        raise ValueError("UCL invariant violated: 144 unique fixtures required")

    ids: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    appearances = defaultdict(int)
    home_count = defaultdict(int)
    away_count = defaultdict(int)
    known = set(team_list)
    for index, fixture in enumerate(fixtures):
        home, away = _fixture_teams(fixture)
        fixture_id = _fixture_id(fixture, index)
        pair = (home, away)
        if fixture_id in ids or pair in pairs:
            raise ValueError("UCL invariant violated: 144 unique fixtures required")
        ids.add(fixture_id)
        pairs.add(pair)
        if home not in known or away not in known or home == away:
            raise ValueError("UCL invariant violated: fixtures must use the 36 unique teams")
        appearances[home] += 1
        appearances[away] += 1
        home_count[home] += 1
        away_count[away] += 1

    if any(appearances[team] != UCL_FIXTURES_PER_TEAM for team in team_list):
        raise ValueError("UCL invariant violated: 8 fixtures/team required")
    if any(home_count[team] != UCL_HOME_FIXTURES or away_count[team] != UCL_AWAY_FIXTURES for team in team_list):
        raise ValueError("UCL invariant violated: 4 home + 4 away/team required")
    return {"teams": len(team_list), "fixtures": len(fixtures)}


def _fixture_score(fixture: Mapping[str, Any]) -> tuple[int, int] | None:
    post = fixture.get("post_match_result")
    if isinstance(post, Mapping):
        for key in ("actual_score", "score_90", "score"):
            score = _score_pair(post.get(key))
            if score is not None:
                return score
    for key in ("actual_score", "score_90", "score"):
        score = _score_pair(fixture.get(key))
        if score is not None:
            return score
    return None


def _is_completed(fixture: Mapping[str, Any]) -> bool:
    if _fixture_score(fixture) is not None:
        return True
    post = fixture.get("post_match_result")
    if isinstance(post, Mapping) and str(post.get("status", "")).lower() in {"completed", "final", "post"}:
        return True
    status = str(fixture.get("status", "")).lower()
    return bool(fixture.get("completed")) or status in {"completed", "final", "post"}


def _discipline_value(fixture: Mapping[str, Any], side: str) -> float:
    keys = (
        f"{side}_disciplinary_score",
        f"{side}_discipline",
        f"{side}_cards",
    )
    for key in keys:
        value = fixture.get(key)
        if isinstance(value, Real) and not isinstance(value, bool):
            return float(value)
    discipline = fixture.get("disciplinary_score", fixture.get("discipline"))
    if isinstance(discipline, Mapping):
        value = discipline.get(side)
        if isinstance(value, Real) and not isinstance(value, bool):
            return float(value)
    return 0.0


def _coefficient_data(value: Any, version: str) -> tuple[float, float | None, str]:
    if isinstance(value, Mapping):
        actual_version = str(value.get("version", value.get("coefficient_version", version)))
        coefficient = value.get("coefficient", value.get("points", value.get("rating")))
        rank = value.get("rank", value.get("coefficient_rank", value.get("uefa_coefficient_rank")))
        try:
            coefficient_value = float(coefficient) if coefficient is not None else 0.0
        except (TypeError, ValueError):
            coefficient_value = 0.0
        try:
            rank_value = float(rank) if rank is not None else None
        except (TypeError, ValueError):
            rank_value = None
        return coefficient_value, rank_value, actual_version
    try:
        return float(value), None, version
    except (TypeError, ValueError):
        return 0.0, None, version


def _sort_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    def key(row: Mapping[str, Any]):
        # ``uefa_coefficient`` is the higher-is-better value.  If a provider
        # only supplies a one-based rank, lower rank is equivalent to higher
        # coefficient and is used as the fallback.
        coefficient = row.get("uefa_coefficient")
        rank = row.get("uefa_coefficient_rank")
        coefficient_key = -float(coefficient or 0.0)
        if (coefficient is None or float(coefficient or 0.0) == 0.0) and rank is not None:
            coefficient_key = float(rank)
        return (
            -float(row.get("points", 0)),
            -float(row.get("goal_difference", 0)),
            -float(row.get("goals_for", 0)),
            -float(row.get("away_goals", 0)),
            -float(row.get("wins", 0)),
            -float(row.get("away_wins", 0)),
            -float(row.get("opponents_points", 0)),
            -float(row.get("opponents_goal_difference", 0)),
            -float(row.get("opponents_goals", 0)),
            float(row.get("disciplinary_score", 0)),
            coefficient_key,
            str(row.get("team", "")),
        )

    return [dict(row) for row in sorted(rows, key=key)]


def rank_ucl_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Sort already aggregated rows using the complete local UEFA order."""
    ranked = _sort_rows(rows)
    for position, row in enumerate(ranked, 1):
        row["rank"] = position
    return ranked


def build_ucl_table(
    teams: Sequence[str] | Sequence[Mapping[str, Any]],
    fixtures: Sequence[Mapping[str, Any]],
    *,
    official_order: Sequence[str] | None = None,
    disciplinary_scores: Mapping[str, Any] | None = None,
    uefa_coefficients: Mapping[str, Any] | None = None,
    uefa_coefficient_ranks: Mapping[str, Any] | None = None,
    coefficient_version: str = UCL_COEFFICIENT_VERSION,
    precomputed: bool = False,
) -> list[dict[str, Any]]:
    """Build a local table, or sort pre-aggregated rows for integrations."""
    if precomputed:
        return rank_ucl_rows(teams)  # type: ignore[arg-type]
    team_list = [str(team) for team in teams]
    validate_ucl_schedule(team_list, fixtures)
    disciplinary_scores = disciplinary_scores or {}
    uefa_coefficients = dict(uefa_coefficients or {})
    for team, rank in (uefa_coefficient_ranks or {}).items():
        if team not in uefa_coefficients:
            uefa_coefficients[team] = {"rank": rank}
    rows: dict[str, dict[str, Any]] = {
        team: {
            "team": team,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "away_goals": 0,
            "wins": 0,
            "away_wins": 0,
            "disciplinary_score": float(disciplinary_scores.get(team, 0) or 0),
            "opponents_points": 0,
            "opponents_goal_difference": 0,
            "opponents_goals": 0,
        }
        for team in team_list
    }
    opponents: dict[str, list[str]] = defaultdict(list)
    for fixture in fixtures:
        home, away = _fixture_teams(fixture)
        opponents[home].append(away)
        opponents[away].append(home)
        score = _fixture_score(fixture)
        if score is None:
            if _is_completed(fixture):
                raise ValueError(f"completed fixture {home} vs {away} has no valid score")
            continue
        # Unplayed fixtures contribute no cards.  This keeps future discipline
        # tied in every simulation run, while completed discipline remains a
        # deterministic table input.
        rows[home]["disciplinary_score"] += _discipline_value(fixture, "home")
        rows[away]["disciplinary_score"] += _discipline_value(fixture, "away")
        home_goals, away_goals = score
        rows[home]["goals_for"] += home_goals
        rows[home]["goals_against"] += away_goals
        rows[home]["away_goals"] += 0
        rows[away]["goals_for"] += away_goals
        rows[away]["goals_against"] += home_goals
        rows[away]["away_goals"] += away_goals
        rows[home]["goal_difference"] += home_goals - away_goals
        rows[away]["goal_difference"] += away_goals - home_goals
        if home_goals > away_goals:
            rows[home]["points"] += 3
            rows[home]["wins"] += 1
            rows[away]["away_goals"] += 0
        elif away_goals > home_goals:
            rows[away]["points"] += 3
            rows[away]["wins"] += 1
            rows[away]["away_wins"] += 1
        else:
            rows[home]["points"] += 1
            rows[away]["points"] += 1

    for team, row in rows.items():
        row["uefa_coefficient"], row["uefa_coefficient_rank"], row["uefa_coefficient_version"] = _coefficient_data(
            uefa_coefficients.get(team, 0), coefficient_version
        )
        for opponent in opponents[team]:
            opponent_row = rows[opponent]
            row["opponents_points"] += opponent_row["points"]
            row["opponents_goal_difference"] += opponent_row["goal_difference"]
            row["opponents_goals"] += opponent_row["goals_for"]

    local = _sort_rows(rows.values())
    official_map = {str(team): index for index, team in enumerate(official_order or (), 1)}
    if official_map:
        local.sort(key=lambda row: (official_map.get(row["team"], len(official_map) + 1), row["rank"] if "rank" in row else 0))
        table_source = "espn"
    else:
        table_source = "local"
    for position, row in enumerate(local, 1):
        row["rank"] = position
        row["local_rank"] = next(i for i, candidate in enumerate(_sort_rows(rows.values()), 1) if candidate["team"] == row["team"])
        row["official_rank"] = official_map.get(row["team"])
        row["table_source"] = table_source
        row["goals_against"] = int(row["goals_against"])
    return local


def _rng(value: np.random.Generator | None) -> np.random.Generator:
    return value or np.random.default_rng(DEFAULT_UCL_SEED)


def build_playoff_bracket(standings: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Describe permitted playoff bands without pretending a draw occurred."""
    rows = list(standings or ())
    by_position = {int(row.get("rank", index + 1)): row.get("team") for index, row in enumerate(rows)}
    return [
        {
            "band": index,
            "seeded_positions": list(seeded),
            "unseeded_positions": list(unseeded),
            "allowed_pairs": [[seed, challenger] for seed in seeded for challenger in unseeded],
            "seeded_hosts_second_leg": True,
            "seeded_teams": [by_position.get(position) for position in seeded],
            "unseeded_teams": [by_position.get(position) for position in unseeded],
        }
        for index, (seeded, unseeded) in enumerate(PLAYOFF_POSITION_BANDS, 1)
    ]


def draw_ucl_bracket(
    standings: Sequence[Mapping[str, Any]] | None = None,
    rng: np.random.Generator | None = None,
) -> dict[str, Any]:
    """Draw every permitted playoff/R16 pairing using the supplied seed."""
    # Accept draw_ucl_bracket(rng) for small integrations.
    if isinstance(standings, np.random.Generator) and rng is None:
        rng, standings = standings, None
    generator = _rng(rng)
    rows = list(standings or ())
    by_position = {int(row.get("rank", index + 1)): row.get("team") for index, row in enumerate(rows)}

    playoff = []
    for band, (seeded_band, unseeded_band) in enumerate(PLAYOFF_POSITION_BANDS, 1):
        seeded_positions = list(generator.permutation(seeded_band))
        unseeded_positions = list(generator.permutation(unseeded_band))
        for index, (seeded, unseeded) in enumerate(zip(seeded_positions, unseeded_positions), 1):
            playoff.append({
                "tie_id": f"playoff-{band}-{index}",
                "band": band,
                "seeded_position": int(seeded),
                "unseeded_position": int(unseeded),
                "seeded_team": by_position.get(int(seeded)),
                "unseeded_team": by_position.get(int(unseeded)),
                "first_leg": {"leg": "first", "home_position": int(unseeded), "away_position": int(seeded), "home": by_position.get(int(unseeded)), "away": by_position.get(int(seeded))},
                "second_leg": {"leg": "second", "home_position": int(seeded), "away_position": int(unseeded), "home": by_position.get(int(seeded)), "away": by_position.get(int(unseeded))},
            })

    r16 = []
    for band, (top_band, playoff_band) in enumerate(R16_POSITION_BANDS, 1):
        top_positions = list(generator.permutation(top_band))
        playoff_positions = list(generator.permutation(playoff_band))
        for top_position, playoff_position in zip(top_positions, playoff_positions):
            tie_id = f"round-of-16-{len(r16) + 1}"
            r16.append({
                "tie_id": tie_id,
                "band": band,
                "top_band": list(top_band),
                "playoff_band": list(playoff_band),
                "top_position": int(top_position),
                "playoff_seed_position": int(playoff_position),
                "top_slot": f"league:{int(top_position)}",
                "playoff_slot": f"playoff-seed:{int(playoff_position)}",
                "first_leg": {"home_slot": f"playoff-seed:{int(playoff_position)}", "away_slot": f"league:{int(top_position)}"},
                "second_leg": {"home_slot": f"league:{int(top_position)}", "away_slot": f"playoff-seed:{int(playoff_position)}"},
            })
    qf = []
    for index in range(0, len(r16), 2):
        left, right = r16[index]["tie_id"], r16[index + 1]["tie_id"]
        qf.append({"tie_id": f"quarterfinal-{len(qf) + 1}", "left": left, "right": right, "first_leg": {"home_slot": right, "away_slot": left}, "second_leg": {"home_slot": left, "away_slot": right}})
    sf = []
    for index in range(0, len(qf), 2):
        left, right = qf[index]["tie_id"], qf[index + 1]["tie_id"]
        sf.append({"tie_id": f"semifinal-{len(sf) + 1}", "left": left, "right": right, "first_leg": {"home_slot": right, "away_slot": left}, "second_leg": {"home_slot": left, "away_slot": right}})
    return {"playoff": playoff, "round_of_16": r16, "quarterfinal": qf, "semifinal": sf, "final": {"tie_id": "final", "single_leg": True}}


def build_ucl_bracket(standings: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Describe allowed bands and the downstream bracket slot path."""
    draw = draw_ucl_bracket(standings)
    return {
        "playoff": build_playoff_bracket(standings),
        "round_of_16": [{"band": band, "top_positions": list(top), "playoff_seed_positions": list(playoff), "seeded_hosts_second_leg": True} for band, (top, playoff) in enumerate(R16_POSITION_BANDS, 1)],
        "quarterfinal": [{"tie_id": tie["tie_id"], "left": tie["left"], "right": tie["right"], "first_leg": tie["first_leg"], "second_leg": tie["second_leg"]} for tie in draw["quarterfinal"]],
        "semifinal": [{"tie_id": tie["tie_id"], "left": tie["left"], "right": tie["right"], "first_leg": tie["first_leg"], "second_leg": tie["second_leg"]} for tie in draw["semifinal"]],
        "final": draw["final"],
    }


def draw_playoff_bracket(
    standings: Sequence[Mapping[str, Any]] | None = None,
    rng: np.random.Generator | None = None,
) -> list[dict[str, Any]]:
    return draw_ucl_bracket(standings, rng)["playoff"]


def _normalise_matrix(value: Any) -> tuple[list[tuple[int, int]], np.ndarray]:
    if isinstance(value, pd.DataFrame):
        items = []
        for home in value.index:
            for away in value.columns:
                try:
                    items.append((int(home), int(away), float(value.loc[home, away])))
                except (TypeError, ValueError):
                    continue
    elif isinstance(value, Mapping):
        items = []
        for key, probability in value.items():
            score = _score_pair(key)
            if score is None and isinstance(probability, Mapping):
                for away, nested_probability in probability.items():
                    score = _score_pair((key, away))
                    if score is not None:
                        items.append((score[0], score[1], float(nested_probability)))
                continue
            if score is not None:
                try:
                    items.append((score[0], score[1], float(probability)))
                except (TypeError, ValueError):
                    continue
    else:
        items = []
    clean = [(home, away, probability) for home, away, probability in items if probability >= 0 and np.isfinite(probability)]
    if not clean or sum(item[2] for item in clean) <= 0:
        raise MissingModelInput("valid score matrix required")
    scores = [(home, away) for home, away, _ in clean]
    probabilities = np.array([probability for _, _, probability in clean], dtype=float)
    return scores, probabilities / probabilities.sum()


def _matrix_lookup(fixture: Mapping[str, Any], matrices: Any, home: str, away: str) -> tuple[list[tuple[int, int]], np.ndarray]:
    candidates = []
    for key in ("score_matrix", "matrix"):
        if fixture.get(key) is not None:
            candidates.append((fixture[key], False))
    prediction = fixture.get("prediction")
    if isinstance(prediction, Mapping):
        for key in ("score_matrix", "matrix"):
            if prediction.get(key) is not None:
                candidates.append((prediction[key], False))
    if isinstance(matrices, pd.DataFrame):
        candidates.append((matrices, False))
    elif isinstance(matrices, Mapping):
        fixture_id = fixture.get("id", fixture.get("match_id", fixture.get("event_id")))
        keys = (fixture_id, str(fixture_id) if fixture_id is not None else None, (home, away), f"{home}::{away}", f"{home}:{away}", (away, home), f"{away}::{home}", f"{away}:{home}", "default")
        for key in keys:
            if key is not None and key in matrices:
                candidates.append((matrices[key], key in ((away, home), f"{away}::{home}", f"{away}:{home}")))
    for value, transpose in candidates:
        try:
            scores, probabilities = _normalise_matrix(value)
        except (MissingModelInput, TypeError, ValueError):
            continue
        if transpose:
            scores = [(away_goals, home_goals) for home_goals, away_goals in scores]
        return scores, probabilities
    raise MissingModelInput(f"no valid score matrix for {home} vs {away}")


def _fixture_matrix(fixture: Mapping[str, Any]) -> Any:
    for key in ("matrix", "score_matrix"):
        value = fixture.get(key)
        if value is not None and _normalised_matrix_dict(value) is not None:
            return value
    prediction = fixture.get("prediction")
    if isinstance(prediction, Mapping):
        for key in ("matrix", "score_matrix"):
            value = prediction.get(key)
            if value is not None and _normalised_matrix_dict(value) is not None:
                return value
    return None


def _normalised_matrix_dict(value: Any) -> dict[str, float] | None:
    try:
        scores, probabilities = _normalise_matrix(value)
    except (MissingModelInput, TypeError, ValueError):
        return None
    return {f"{home}:{away}": float(probability) for (home, away), probability in zip(scores, probabilities)}


def build_cached_ucl_inputs(cached: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize cache fixture matrices and pass through simulation metadata."""
    if not isinstance(cached, Mapping):
        raise ValueError("UCL fixture cache is unavailable")
    metadata = cached.get("metadata") if isinstance(cached.get("metadata"), Mapping) else {}
    fixtures = cached.get("data")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("UCL fixture cache contains no fixtures")
    matrices = dict(cached.get("score_matrices") or {}) if isinstance(cached.get("score_matrices"), Mapping) else {}
    open_matrices: list[dict[str, float]] = []
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise ValueError("UCL fixture cache contains an invalid fixture")
        fixture_id = fixture.get("id", fixture.get("match_id", fixture.get("event_id")))
        fixture_matrix = _fixture_matrix(fixture)
        if fixture_matrix is None and fixture_id is not None:
            fixture_matrix = matrices.get(str(fixture_id), matrices.get(fixture_id))
        matrix = _normalised_matrix_dict(fixture_matrix)
        if matrix and fixture_id is not None:
            matrices[str(fixture_id)] = matrix
        if matrix and not _is_completed(fixture):
            open_matrices.append(matrix)

    explicit_default = cached.get("default_score_matrix", cached.get("default_matrix"))
    if explicit_default is None and isinstance(cached.get("score_matrices"), Mapping):
        explicit_default = cached["score_matrices"].get("default")
    default_matrix = _normalised_matrix_dict(explicit_default) if explicit_default is not None else None
    if default_matrix is None and open_matrices:
        aggregate: defaultdict[str, float] = defaultdict(float)
        for matrix in open_matrices:
            for score, probability in matrix.items():
                aggregate[score] += probability
        default_matrix = {score: probability / len(open_matrices) for score, probability in aggregate.items()}
    if default_matrix:
        matrices["default"] = default_matrix
    official_order = cached.get("official_order", metadata.get("official_order"))
    if isinstance(official_order, list) and official_order and isinstance(official_order[0], Mapping):
        official_order = [row.get("team", row.get("team_name")) for row in official_order]
    return {
        "fixtures": fixtures,
        "teams": cached.get("teams"),
        "score_matrices": matrices,
        "disciplinary_scores": cached.get("disciplinary_scores", metadata.get("disciplinary_scores")) or {},
        "uefa_coefficients": cached.get("uefa_coefficients", metadata.get("uefa_coefficients")) or {},
        "uefa_coefficient_ranks": cached.get("uefa_coefficient_ranks", metadata.get("uefa_coefficient_ranks")) or {},
        "official_order": official_order,
        "coefficient_version": cached.get("coefficient_version", cached.get("uefa_coefficient_version", metadata.get("coefficient_version", UCL_COEFFICIENT_VERSION))),
        "provenance": cached.get("provenance", cached.get("input_provenance", metadata.get("provenance"))) or {},
    }


def _sample_score(fixture: Mapping[str, Any], matrices: Any, home: str, away: str, rng: np.random.Generator) -> tuple[int, int, tuple[float, float]]:
    scores, probabilities = _matrix_lookup(fixture, matrices, home, away)
    index = int(rng.choice(len(scores), p=probabilities))
    selected = scores[index]
    xg_home = float(sum(home_goals * probability for (home_goals, _), probability in zip(scores, probabilities)))
    xg_away = float(sum(away_goals * probability for (_, away_goals), probability in zip(scores, probabilities)))
    return selected[0], selected[1], (xg_home, xg_away)


def _play_match(
    home: str,
    away: str,
    fixture: Mapping[str, Any],
    matrices: Any,
    rng: np.random.Generator,
    *,
    stage: str,
    leg: str,
    first_leg_score: tuple[int, int] | None = None,
) -> dict[str, Any]:
    fixed = _fixture_score(fixture)
    if fixed is None:
        home_score, away_score, xg = _sample_score(fixture, matrices, home, away, rng)
    else:
        home_score, away_score = fixed
        # Completed games do not need a model.  ET still needs a deterministic
        # neutral increment if the stored fixture carries one.
        try:
            _, _, xg = _sample_score(fixture, matrices, home, away, rng)
        except MissingModelInput:
            xg = (0.0, 0.0)
    context_first = None
    if first_leg_score is not None:
        # Task 3's aggregate helper uses the current home/away orientation;
        # the second leg reverses the first leg's hosts.
        context_first = f"{first_leg_score[1]}:{first_leg_score[0]}"
    context = build_match_context({"competition": "ucl2026", "stage": stage, "leg": leg, "first_leg_score": context_first})
    score_90 = (home_score, away_score)
    aet_score = None
    penalties = False
    if extra_time_eligible_for_score(context, home_score, away_score):
        extra_home = int(rng.poisson(max(0.0, xg[0]) / 3.0))
        extra_away = int(rng.poisson(max(0.0, xg[1]) / 3.0))
        home_score += extra_home
        away_score += extra_away
        aet_score = (home_score, away_score)
        if home_score == away_score:
            penalties = True
            advancement = advancement_probabilities(context, home_score, away_score)
            winner = home if rng.random() < advancement["home"] else away
        else:
            winner = home if home_score > away_score else away
    elif stage != "league" and leg == "single" and home_score == away_score:
        # A final draw always reaches ET; the branch above handles it.  This
        # guard keeps malformed future contexts from producing a fake winner.
        winner = home if rng.random() < 0.5 else away
        penalties = True
    elif home_score == away_score:
        winner = None
    else:
        winner = home if home_score > away_score else away
    return {"home": home, "away": away, "score_90": score_90, "score_aet": aet_score, "winner": winner, "penalties": penalties}


def _play_two_leg_tie(
    seeded: str,
    unseeded: str,
    matrices: Any,
    rng: np.random.Generator,
    *,
    stage: str,
) -> tuple[str, list[dict[str, Any]]]:
    first = _play_match(unseeded, seeded, {"home_team": unseeded, "away_team": seeded}, matrices, rng, stage=stage, leg="first")
    first_score = first["score_90"]
    second = _play_match(seeded, unseeded, {"home_team": seeded, "away_team": unseeded}, matrices, rng, stage=stage, leg="second", first_leg_score=first_score)
    first_seeded, first_unseeded = first_score[1], first_score[0]
    second_seeded, second_unseeded = second["score_90"]
    seeded_total = first_seeded + second_seeded
    unseeded_total = first_unseeded + second_unseeded
    if seeded_total > unseeded_total:
        winner = seeded
    elif unseeded_total > seeded_total:
        winner = unseeded
    elif second.get("winner") in {seeded, unseeded}:
        winner = second["winner"]
    else:
        winner = seeded if rng.random() < 0.5 else unseeded
    return winner, [first, second]


def _unavailable(teams: Sequence[str], runs: int, seed: int, reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "source": "ucl_simulation_cache",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "error": reason,
        "reason": reason,
        "runs": runs,
        "n_runs": runs,
        "run_count": runs,
        "seed": seed,
        "table_version": UCL_TABLE_VERSION,
        "teams": [{"team": str(team)} for team in teams],
        "results": [],
        "bracket": build_ucl_bracket(),
    }


def simulate_ucl_tournament(
    teams: Sequence[str],
    fixtures: Sequence[Mapping[str, Any]],
    score_matrices: Any = None,
    *,
    n_runs: int = DEFAULT_UCL_RUNS,
    runs: int | None = None,
    seed: int = DEFAULT_UCL_SEED,
    disciplinary_scores: Mapping[str, Any] | None = None,
    uefa_coefficients: Mapping[str, Any] | None = None,
    uefa_coefficient_ranks: Mapping[str, Any] | None = None,
    official_order: Sequence[str] | None = None,
    coefficient_version: str = UCL_COEFFICIENT_VERSION,
    coefficient_provenance: Mapping[str, Any] | None = None,
    validate_schedule: bool = True,
) -> dict[str, Any]:
    """Run a seeded UCL league/table/playoff/knockout simulation."""
    if runs is not None:
        n_runs = runs
    n_runs = int(n_runs)
    if n_runs <= 0:
        raise ValueError("Simulation runs must be positive")
    try:
        team_list = [str(team) for team in teams]
        if not isinstance(fixtures, Sequence) or isinstance(fixtures, (str, bytes)):
            raise ValueError("UCL fixtures must be a sequence")
        for fixture in fixtures:
            if not isinstance(fixture, Mapping):
                raise ValueError("UCL fixture must be a mapping")
            _fixture_teams(fixture)
        if validate_schedule:
            validate_ucl_schedule(team_list, fixtures)
        for fixture in fixtures:
            if _is_completed(fixture) and _fixture_score(fixture) is None:
                home, away = _fixture_teams(fixture)
                raise ValueError(f"completed fixture {home} vs {away} has no valid score")
        for fixture in fixtures:
            if not _is_completed(fixture):
                _matrix_lookup(fixture, score_matrices, *_fixture_teams(fixture))
    except (MissingModelInput, TypeError, ValueError, KeyError) as exc:
        team_list = [str(team) for team in teams] if teams is not None else []
        return _unavailable(team_list, n_runs, seed, str(exc))

    rng = np.random.default_rng(seed)
    stats = {
        team: {"points": 0.0, "rank": 0.0, "top8": 0, "top24": 0, "round_of_16": 0, "quarterfinal": 0, "semifinal": 0, "final": 0, "champion": 0}
        for team in team_list
    }
    sample_draw = None
    for _ in range(n_runs):
        sampled_fixtures = []
        for fixture in fixtures:
            copy = dict(fixture)
            if not _is_completed(fixture):
                home, away = _fixture_teams(fixture)
                home_score, away_score, _ = _sample_score(fixture, score_matrices, home, away, rng)
                copy["score_90"] = f"{home_score}:{away_score}"
                copy["status"] = "completed"
            sampled_fixtures.append(copy)
        try:
            table = build_ucl_table(team_list, sampled_fixtures, disciplinary_scores=disciplinary_scores, uefa_coefficients=uefa_coefficients, uefa_coefficient_ranks=uefa_coefficient_ranks, coefficient_version=coefficient_version)
        except ValueError as exc:
            if not validate_schedule:
                return _unavailable(team_list, n_runs, seed, str(exc))
            raise
        for position, row in enumerate(table, 1):
            team = row["team"]
            stats[team]["points"] += row["points"]
            stats[team]["rank"] += position
            if position <= 8:
                stats[team]["top8"] += 1
                stats[team]["round_of_16"] += 1
            if position <= 24:
                stats[team]["top24"] += 1

        by_rank = {position: row["team"] for position, row in enumerate(table, 1)}
        draw = draw_ucl_bracket(table, rng=rng)
        if sample_draw is None:
            sample_draw = draw
        playoff_winners: dict[int, str] = {}
        for tie in draw["playoff"]:
            seeded_position = tie["seeded_position"]
            unseeded_position = tie["unseeded_position"]
            try:
                winner, _ = _play_two_leg_tie(by_rank[seeded_position], by_rank[unseeded_position], score_matrices, rng, stage="playoff")
            except MissingModelInput as exc:
                return _unavailable(team_list, n_runs, seed, str(exc))
            playoff_winners[seeded_position] = winner
            stats[winner]["round_of_16"] += 1

        r16_winners = []
        for tie in draw["round_of_16"]:
            top_position = tie["top_position"]
            playoff_position = tie["playoff_seed_position"]
            seeded, challenger = by_rank[top_position], playoff_winners[playoff_position]
            try:
                winner, _ = _play_two_leg_tie(seeded, challenger, score_matrices, rng, stage="round_of_16")
            except MissingModelInput as exc:
                return _unavailable(team_list, n_runs, seed, str(exc))
            r16_winners.append(winner)
        for team in r16_winners:
            stats[team]["quarterfinal"] += 1

        qf_winners = []
        for index in range(0, len(r16_winners), 2):
            try:
                winner, _ = _play_two_leg_tie(r16_winners[index], r16_winners[index + 1], score_matrices, rng, stage="quarterfinal")
            except MissingModelInput as exc:
                return _unavailable(team_list, n_runs, seed, str(exc))
            qf_winners.append(winner)
        for team in qf_winners:
            stats[team]["semifinal"] += 1

        sf_winners = []
        for index in range(0, len(qf_winners), 2):
            try:
                winner, _ = _play_two_leg_tie(qf_winners[index], qf_winners[index + 1], score_matrices, rng, stage="semifinal")
            except MissingModelInput as exc:
                return _unavailable(team_list, n_runs, seed, str(exc))
            sf_winners.append(winner)
        for team in sf_winners:
            stats[team]["final"] += 1

        final_fixture = {"home_team": sf_winners[0], "away_team": sf_winners[1]}
        try:
            final = _play_match(sf_winners[0], sf_winners[1], final_fixture, score_matrices, rng, stage="final", leg="single")
        except MissingModelInput as exc:
            return _unavailable(team_list, n_runs, seed, str(exc))
        champion = final["winner"]
        if champion is None:
            champion = sf_winners[0] if rng.random() < 0.5 else sf_winners[1]
        stats[champion]["champion"] += 1

    output_teams = []
    for team in team_list:
        item = {"team": team}
        item["expected_points"] = round(stats[team]["points"] / n_runs, 4)
        item["expected_rank"] = round(stats[team]["rank"] / n_runs, 4)
        for field in ("top8", "top24", "round_of_16", "quarterfinal", "semifinal", "final", "champion"):
            item[field] = round(100.0 * stats[team][field] / n_runs, 4)
        output_teams.append(item)
    output_teams.sort(key=lambda item: (-item["champion"], item["expected_rank"], item["team"]))
    bracket = build_ucl_bracket()
    bracket["sample_draw"] = sample_draw
    warnings = []
    coefficient_teams = set(uefa_coefficients or {}) | set(uefa_coefficient_ranks or {})
    covered_teams = set(team_list) & {str(team) for team in coefficient_teams}
    if not coefficient_teams:
        warnings.append("UEFA coefficient input unavailable; lexical name is only a deterministic final fallback")
    elif len(covered_teams) < len(team_list):
        warnings.append(f"UEFA coefficient coverage incomplete: {len(covered_teams)}/{len(team_list)} teams; lexical fallback remains for missing teams")
    if not official_order:
        warnings.append("ESPN official order unavailable; local ranking is used for simulation")
    result = {
        "status": "fresh",
        "runs": n_runs,
        "n_runs": n_runs,
        "run_count": n_runs,
        "seed": seed,
        "table_version": UCL_TABLE_VERSION,
        "coefficient_version": coefficient_version,
        "coefficient_provenance": dict(coefficient_provenance or {}),
        "provenance": dict(coefficient_provenance or {}),
        "official_order": list(official_order or []),
        "ranking_source": "local",
        "warnings": warnings,
        "teams": output_teams,
        "results": output_teams,
        "bracket": bracket,
    }
    result["probabilities"] = {item["team"]: {field: item[field] for field in ("top8", "top24", "round_of_16", "quarterfinal", "semifinal", "final", "champion")} for item in output_teams}
    result["by_team"] = {item["team"]: item for item in output_teams}
    return result


def simulate_ucl(*args, **kwargs):
    """Compatibility alias for callers that use the shorter service name."""
    return simulate_ucl_tournament(*args, **kwargs)


def compute_ucl_table(*args, **kwargs):
    return build_ucl_table(*args, **kwargs)


class UCLTableEngine:
    def __init__(self, teams: Sequence[str], fixtures: Sequence[Mapping[str, Any]] | None = None, **kwargs):
        self.teams = teams
        self.fixtures = fixtures
        self.kwargs = kwargs

    def build(self, fixtures: Sequence[Mapping[str, Any]] | None = None, **kwargs):
        options = dict(self.kwargs)
        options.update(kwargs)
        return build_ucl_table(self.teams, fixtures if fixtures is not None else self.fixtures or (), **options)

    def validate(self, fixtures: Sequence[Mapping[str, Any]] | None = None):
        return validate_ucl_schedule(self.teams, fixtures if fixtures is not None else self.fixtures or ())

    compute = build
    build_table = build


UCLLeagueTable = UCLTableEngine

# Descriptive aliases used by small route/integration consumers.
validate_ucl_fixtures = validate_ucl_schedule
build_table = build_ucl_table
simulate_ucl_season = simulate_ucl_tournament
