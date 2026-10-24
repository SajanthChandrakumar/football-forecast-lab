import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.math_engine import MathEngine

@pytest.fixture
def math_engine():
    # We can mock the CSV by creating a tiny dummy file or just testing methods that don't need it.
    # For testing get_elo_probability and static methods, the CSV content doesn't matter unless we call merge_odds_and_elo.
    dummy_csv = "data/elo_ratings.csv" 
    return MathEngine(dummy_csv)

def test_remove_margin():
    odds = MathEngine.remove_margin(2.5, 3.2, 2.8)
    assert "home" in odds
    assert "draw" in odds
    assert "away" in odds
    assert abs(odds["home"] + odds["draw"] + odds["away"] - 1.0) < 1e-6

def test_get_elo_probability(math_engine):
    # Equal ratings -> 0.5 probability
    prob = math_engine.get_elo_probability(1500, 1500)
    assert prob == 0.5
    
    # Higher rating -> higher probability
    prob2 = math_engine.get_elo_probability(1600, 1500)
    assert prob2 > 0.5

def test_derive_xg_from_odds():
    # If probs are completely symmetrical, xG should be roughly identical
    xg_home, xg_away = MathEngine.derive_xg_from_odds(0.4, 0.2, 0.4, 0.5)
    assert abs(xg_home - xg_away) < 0.1

def test_generate_exact_score_matrix():
    matrix = MathEngine.generate_exact_score_matrix(1.5, 1.2, max_goals=3)
    assert isinstance(matrix, pd.DataFrame)
    assert matrix.shape == (4, 4)
    # Total probability up to 3 goals should be less than 1, but individually valid
    assert (matrix.values >= 0).all() and (matrix.values <= 1).all()

def test_calculate_expected_points(math_engine):
    # Create a dummy 6x6 score matrix with 100% probability on 2:1
    matrix = pd.DataFrame(np.zeros((6, 6)), index=[str(i) for i in range(6)], columns=[str(i) for i in range(6)])
    matrix.loc["2", "1"] = 1.0 
    
    xp_df = math_engine.calculate_expected_points(matrix, is_ko_phase=False)
    
    assert isinstance(xp_df, pd.DataFrame)
    assert len(xp_df) == 5
    assert "Tipp" in xp_df.columns
    assert "xP" in xp_df.columns
    
    # The best tip should be 2:1, earning exactly 10 points (5 for tendency, 1 for home, 1 for away, 3 for diff)
    assert xp_df.iloc[0]["Tipp"] == "2:1"
    assert xp_df.iloc[0]["xP"] == 10.0

def test_host_advantage_elo(math_engine):
    # Equal ratings without host advantage -> exactly 0.5
    prob_neutral = math_engine.get_elo_probability(1500, 1500)
    assert prob_neutral == 0.5

    # With host advantage (+80 Elo applied to team A) -> must be > 0.5
    prob_host = math_engine.get_elo_probability(1500, 1500, is_a_host=True)
    assert prob_host > 0.5

    # Mathematically verify the +80 Elo boost: 1 / (10^(-80/400) + 1) ≈ 0.613
    assert round(prob_host, 3) == 0.613

def test_dixon_coles_adjustment():
    # rho=0.0 -> pure independent Poisson (no adjustment)
    matrix_indep = MathEngine.generate_exact_score_matrix(1.2, 0.9, max_goals=3, rho=0.0)

    # rho=-0.15 -> Dixon-Coles correction applied
    matrix_dc = MathEngine.generate_exact_score_matrix(1.2, 0.9, max_goals=3, rho=-0.15)

    # Low-scoring draws must be boosted by the correction
    assert matrix_dc.loc["0", "0"] > matrix_indep.loc["0", "0"], "0:0 should be boosted by Dixon-Coles"
    assert matrix_dc.loc["1", "1"] > matrix_indep.loc["1", "1"], "1:1 should be boosted by Dixon-Coles"

    # Narrow wins (1:0) must be slightly penalized by the correction
    assert matrix_dc.loc["1", "0"] < matrix_indep.loc["1", "0"], "1:0 should be penalized by Dixon-Coles"


def test_club_dixon_coles_policy_uses_away_lambda_for_one_nil():
    legacy = MathEngine.generate_exact_score_matrix(2.0, 0.5, max_goals=3)
    club = MathEngine.generate_exact_score_matrix(2.0, 0.5, max_goals=3, dc_policy="clubs")
    independent = MathEngine.generate_exact_score_matrix(2.0, 0.5, max_goals=3, rho=0.0)

    # Ratios against an untouched cell remove the common normalization factor.
    legacy_tau_10 = (legacy.loc["1", "0"] / independent.loc["1", "0"]) / (legacy.loc["2", "2"] / independent.loc["2", "2"])
    club_tau_10 = (club.loc["1", "0"] / independent.loc["1", "0"]) / (club.loc["2", "2"] / independent.loc["2", "2"])
    club_tau_01 = (club.loc["0", "1"] / independent.loc["0", "1"]) / (club.loc["2", "2"] / independent.loc["2", "2"])

    assert legacy_tau_10 == pytest.approx(1 + 2.0 * -0.15)
    assert club_tau_10 == pytest.approx(1 + 0.5 * -0.15)
    assert club_tau_01 == pytest.approx(1 + 2.0 * -0.15)


def test_club_dixon_coles_xg_fit_uses_same_asymmetric_factors(monkeypatch):
    observed = []

    class Result:
        success = True
        x = np.array([2.0, 0.5])

    def minimize(objective, *_args, **_kwargs):
        observed.append(objective([2.0, 0.5]))
        return Result()

    monkeypatch.setattr("src.math_engine.optimize.minimize", minimize)
    probs = {"home": 0.52, "draw": 0.28, "away": 0.20}
    MathEngine.derive_xg_from_odds(**{
        "prob_home": probs["home"], "prob_draw": probs["draw"], "prob_away": probs["away"],
        "dc_policy": "clubs",
    })

    goals = np.arange(10)
    matrix = np.outer(
        __import__("scipy").stats.poisson.pmf(goals, 2.0),
        __import__("scipy").stats.poisson.pmf(goals, 0.5),
    )
    rho = -0.15
    matrix[0, 0] *= 1 - 2.0 * 0.5 * rho
    matrix[1, 0] *= 1 + 0.5 * rho
    matrix[0, 1] *= 1 + 2.0 * rho
    matrix[1, 1] *= 1 - rho
    matrix /= matrix.sum()
    expected = (
        (np.tril(matrix, -1).sum() - probs["home"]) ** 2
        + (np.diag(matrix).sum() - probs["draw"]) ** 2
        + (np.triu(matrix, 1).sum() - probs["away"]) ** 2
    )
    assert observed == pytest.approx([expected])
