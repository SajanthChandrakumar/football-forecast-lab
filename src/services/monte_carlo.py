"""
Monte-Carlo-Simulator für die K.O.-Phase (Rest-of-tournament).

Simuliert ab dem aktuellen Bracket-Stand (Achtelfinale) bis zum Finale, rein
auf Basis der aktuellen Elo-Ratings (kein Markt-Blend — für hypothetische
Spätrunden-Paarungen existieren noch keine Buchmacher-Quoten). Bereits
gespielte Runden (Gruppenphase, Sechzehntelfinale) sind reale Fakten und
werden nicht simuliert.

Der K.O.-Baum für die WM 2026 ist von FIFA fix vorgegeben (siehe
https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage). Da die
Achtelfinal-Paarungen zum Zeitpunkt der Umsetzung feststehen, wird der Baum
als geordnete Liste hinterlegt: Runde n+1 ergibt sich immer aus benachbarten
Paaren der Runde n (Sieger 0 vs Sieger 1, Sieger 2 vs Sieger 3, ...).
"""
from __future__ import annotations

import numpy as np

from src.constants import TEAM_MAPPING
from src.math_engine import HOST_NATIONS

# Achtelfinal-Bracket in Baum-Reihenfolge — Konsekutive Paare treffen sich in
# der jeweils nächsten Runde. Bestätigt gegen zwei unabhängige Quellen
# (Wikipedia + Sky Sports) am 2026-07-04.
ROUND_OF_16 = [
    ("Canada", "Morocco"),
    ("Paraguay", "France"),
    ("Portugal", "Spain"),
    ("United States", "Belgium"),
    ("Brazil", "Norway"),
    ("Mexico", "England"),
    ("Argentina", "Egypt"),
    ("Switzerland", "Colombia"),
]

ROUND_LABELS = ["Achtelfinale", "Viertelfinale", "Halbfinale", "Finale"]


def _elo_win_prob(elo_a: np.ndarray, elo_b: np.ndarray, host_a: np.ndarray, host_b: np.ndarray) -> np.ndarray:
    """Reine Elo-Gewinnwahrscheinlichkeit für Team A, inkl. +80 Gastgeber-Bonus.
    Kein Markt-Blend: für zukünftige K.O.-Paarungen gibt es noch keine Quoten."""
    adj_a = elo_a + np.where(host_a, 80.0, 0.0)
    adj_b = elo_b + np.where(host_b, 80.0, 0.0)
    return 1.0 / (10.0 ** (-(adj_a - adj_b) / 400.0) + 1.0)


def _simulate_round(pairs: np.ndarray, team_elo: np.ndarray, host_mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """pairs: (n_runs, n_matches, 2) Team-Indizes → gibt Sieger-Indizes (n_runs, n_matches) zurück."""
    idx_a, idx_b = pairs[:, :, 0], pairs[:, :, 1]
    p_a = _elo_win_prob(team_elo[idx_a], team_elo[idx_b], host_mask[idx_a], host_mask[idx_b])
    a_wins = rng.random(p_a.shape) < p_a
    return np.where(a_wins, idx_a, idx_b)


def simulate_knockout(elo_ratings: dict[str, float], n_runs: int = 20_000, seed: int | None = 42) -> dict:
    """Simuliert das Bracket ab dem Achtelfinale n_runs mal.

    elo_ratings: {normalisierter Team-Name: aktuelles Elo-Rating}.
    Gibt pro Team die Prozentsätze fürs Erreichen jeder Runde zurück, sowie
    die verwendete Bracket-Struktur (für die Anzeige des Baums im Frontend).
    """
    all_teams = [t for pair in ROUND_OF_16 for t in pair]
    team_to_idx = {t: i for i, t in enumerate(all_teams)}

    default_elo = 1650.0  # neutraler Fallback, falls ein Team fehlt (sollte nicht vorkommen)
    team_elo = np.array([
        elo_ratings.get(TEAM_MAPPING.get(t, t), default_elo) for t in all_teams
    ], dtype=float)
    host_mask = np.array([TEAM_MAPPING.get(t, t) in HOST_NATIONS for t in all_teams])

    rng = np.random.default_rng(seed)
    r16_pairs = np.array([[team_to_idx[a], team_to_idx[b]] for a, b in ROUND_OF_16])
    r16_pairs_tiled = np.broadcast_to(r16_pairs, (n_runs, 8, 2))

    r16_winners = _simulate_round(r16_pairs_tiled, team_elo, host_mask, rng)          # (n_runs, 8)
    qf_winners = _simulate_round(r16_winners.reshape(n_runs, 4, 2), team_elo, host_mask, rng)  # (n_runs, 4)
    sf_winners = _simulate_round(qf_winners.reshape(n_runs, 2, 2), team_elo, host_mask, rng)   # (n_runs, 2)
    champion = _simulate_round(sf_winners.reshape(n_runs, 1, 2), team_elo, host_mask, rng)[:, 0]  # (n_runs,)

    results = []
    for i, team in enumerate(all_teams):
        results.append({
            "team": team,
            "elo": round(float(team_elo[i]), 1),
            "reached_qf": round(float(np.mean(np.any(r16_winners == i, axis=1))) * 100, 1),
            "reached_sf": round(float(np.mean(np.any(qf_winners == i, axis=1))) * 100, 1),
            "reached_final": round(float(np.mean(np.any(sf_winners == i, axis=1))) * 100, 1),
            "champion": round(float(np.mean(champion == i)) * 100, 1),
        })
    results.sort(key=lambda r: r["champion"], reverse=True)

    return {
        "n_runs": n_runs,
        "bracket": [{"home": a, "away": b} for a, b in ROUND_OF_16],
        "round_labels": ROUND_LABELS,
        "results": results,
    }
