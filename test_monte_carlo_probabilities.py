from src.services.monte_carlo import ROUND_OF_16, simulate_knockout


def test_round_probabilities_are_nested_and_sum_to_stage_counts():
    teams = [team for pair in ROUND_OF_16 for team in pair]
    ratings = {team: 1650.0 for team in teams}
    results = simulate_knockout(ratings, n_runs=20_000, seed=42)["results"]

    for row in results:
        assert row["reached_qf"] >= row["reached_sf"] >= row["reached_final"] >= row["champion"]

    # Each run has 8 quarterfinalists, 4 semifinalists, 2 finalists and 1 champion.
    expected_totals = {"reached_qf": 800, "reached_sf": 400, "reached_final": 200, "champion": 100}
    for stage, expected in expected_totals.items():
        actual = sum(row[stage] for row in results)
        assert abs(actual - expected) < 3, f"{stage} sums to {actual:.1f}%, expected about {expected}%"
