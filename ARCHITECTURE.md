# Architecture & Prediction Pipeline

This document explains how **Football Forecast Lab** works under the hood — from ingesting match odds and Elo ratings to calculating expected points (xP) and custom bot strategies.

## Integration boundaries

Public match reads are cache-only. Provider collection runs through the
authenticated `POST /api/internal/maintenance` route, which refreshes bounded
ESPN windows, stores append-only odds observations, and writes UCL ClubElo data
only to competition-scoped Mongo documents. Snapshot/source states are limited
to `fresh`, `stale`, `unavailable`, and `failed`, with source and timestamps
retained for unavailable or failed results. Legacy WC documents can be migrated
with `scripts/migrate_wc_legacy.py`; the operation is idempotent, copy-first,
preserves match IDs/user tips, and does not delete the source documents.

## Integration boundaries

Public match reads are cache-only. Provider collection runs through the
authenticated `POST /api/internal/maintenance` route, which refreshes bounded
ESPN windows, stores append-only odds observations, and writes UCL ClubElo data
only to competition-scoped Mongo documents. Snapshot/source states are limited
to `fresh`, `stale`, `unavailable`, and `failed`, with source and timestamps
retained for unavailable or failed results. Legacy WC documents can be migrated
with `scripts/migrate_wc_legacy.py`; the operation is idempotent, copy-first,
preserves match IDs/user tips, and does not delete the source documents.

---

## Pipeline Overview

```
Raw Bookmaker Odds (H2H + O/U 2.5)  +  Live Elo Ratings
                   │                                │
                   ▼                                ▼
         1. Remove Bookie Margin           2. Elo Win Probabilities
                   │                                │
                   └───────────────┬────────────────┘
                                   ▼
                   3. Blend Probabilities (70% Odds / 30% Elo)
                                   │
                                   ▼
                   4. Solve for xG (SciPy L-BFGS-B)
                                   │
                                   ▼
                   5. Generate Score Matrix (Dixon-Coles ρ = -0.15)
                                   │
                                   ▼
                   6. Calculate Expected Points (xP per SRF Rules)
                                   │
                                   ▼
                   7. Rank Best Tips & Run Bot Strategies
```

---

## 1. Odds Processing & Probability Blending

### Consensus Odds & Margin Removal
Different bookmakers price matches differently. For upcoming matches, we collect odds across available bookmakers from The Odds API and take the median price per outcome. 

Bookmaker odds include vigorish (margin). To get true probabilities, we remove the margin proportionally:

```python
raw_probs = { "home": 1 / odds_home, "draw": 1 / odds_draw, "away": 1 / odds_away }
total = sum(raw_probs.values())
true_probs = { k: v / total for k, v in raw_probs.items() }
```

### 70/30 Odds–Elo Blend
We track live Elo ratings ($K=60$, adjusted for goal differences and +80 host advantage for USA/CAN/MEX). 

Because market odds already price in home advantage and injuries, we blend 70% bookmaker odds with 30% pure Elo probabilities across the win/loss pool. We keep the draw probability fixed to market consensus to avoid deflating draws:

```python
win_loss_pool = true_probs["home"] + true_probs["away"]
prob_home = (true_probs["home"] / win_loss_pool * 0.7 + elo_home_prob * 0.3) * win_loss_pool
prob_away = (true_probs["away"] / win_loss_pool * 0.7 + elo_away_prob * 0.3) * win_loss_pool
```

---

## 2. Solving for Expected Goals (xG)

With target probabilities for Home Win, Draw, Away Win (and Over 2.5 goals when available), we solve for the underlying Expected Goals ($\lambda_{\text{home}}, \lambda_{\text{away}}$).

We use `scipy.optimize.minimize` (L-BFGS-B) to find the pair of lambdas whose bivariate Poisson distribution produces outcome probabilities closest to our target probabilities:

```python
error = (calc_home - target_home)**2 + (calc_draw - target_draw)**2 + (calc_away - target_away)**2
```

In knockout rounds, extra-time xG is scaled up proportionally based on the probability of a draw after 90 minutes (`1 + p_draw_90 / 3`).

---

## 3. Score Matrix & Dixon-Coles Adjustment

Independent Poisson distributions tend to under-predict low-scoring draws and 1-0 games. We apply the standard **Dixon-Coles correction** ($\rho = -0.15$) to adjust probabilities for `0:0`, `1:0`, `0:1`, and `1:1`:

- `P(0:0) *= 1 - (λ_h * λ_a * ρ)`
- `P(1:0) *= 1 + (λ_h * ρ)`
- `P(0:1) *= 1 + (λ_a * ρ)`
- `P(1:1) *= 1 - ρ`

This generates a normalized $10 \times 10$ scoreline probability matrix for the match.

---

## 4. Expected Points (xP) Calculation

In the SRF Tippspiel pool, points are awarded based on how close your tip is to the actual score:
- **10 points**: Exact score
- **8 points**: Correct goal difference (except draws)
- **6 points**: Correct tendency + correct goals for one team
- **5 points**: Correct tendency (Win/Draw/Loss)
- *(Points are doubled in knockout rounds)*

To find the optimal tip, we evaluate all 36 possible tips (`0:0` through `5:5`). For each candidate tip, we multiply its reward across every possible actual scoreline in the score matrix by that scoreline's probability:

```python
xP(tip) = sum( probability(score) * points_earned(tip, score) for score in score_matrix )
```

The tip with the highest `xP` is recommended as the top algorithm tip.

---

## 5. House Bots & Build-a-Bot

We benchmark our predictions against four fixed-strategy house bots:

| Bot | Strategy |
|---|---|
| **Broker** | 100% market odds (0% Elo blend), selecting the highest xP tip. |
| **Professor** | 100% Elo form (0% market blend), selecting the highest xP tip. |
| **X-Sniper** | Scans candidate tips and picks the draw (`X:X`) with the highest xP. |
| **Gambler** | Weighted-random selection from the top 10 xP tips, deterministically seeded by match ID. |

### Build-a-Bot Sandbox
The dashboard also includes a **Build-a-Bot** tool that lets users customize tipping rules (e.g. adjusting market vs. Elo weights, scaling xG, or nudging draw bias) and backtest them against historical tournament results.

---

## 6. Engineering & Storage

- **API Layer**: Built with **FastAPI** and **SlowAPI** rate limiting.
- **Data Persistence**: **MongoDB Atlas** stores match archives, user tips, bot tips, and cached computations.
- **Caching**: Dynamic TTLs preserve external odds API quota (>24h out: 12h cache; 2–24h out: 1h cache; <2h out: 15m cache).
