# WM 2026 Predictor

<div align="center">

**A quantitative prediction engine and analytics dashboard for the FIFA World Cup 2026**

[**Live Demo**](https://wc2026-predictor-8skd.onrender.com/)

[![Tests](https://github.com/SajanthChandrakumar/wm2026_predictor/actions/workflows/test.yml/badge.svg)](https://github.com/SajanthChandrakumar/wm2026_predictor/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?style=flat&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb?style=flat&logo=react)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

</div>

A full-stack quantitative prediction engine built for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a competitive closed prediction pool during the FIFA World Cup 2026. The system reverse-engineers bookmaker odds into Expected Goals, applies a Dixon-Coles–corrected bivariate Poisson model, blends in a live Elo rating system, and computes the mathematically optimal tip for each match.

> See [ARCHITECTURE.md](ARCHITECTURE.md) for the full mathematical derivation.
> See [ANALYSIS.md](ANALYSIS.md) for the post-tournament performance analysis and global ranking.

---

## Motivation

In a prediction pool, picking the most likely scoreline is only part of the puzzle. While raw Expected Points (**xP**) maximize your theoretical baseline, competitive pool dynamics often require balancing chalk predictions against alternative strategies.

This system provides both rigorous expected-point optimization across the full bivariate Poisson score matrix and a **Build-a-Bot** sandbox where users can design, backtest, and simulate custom tipping strategies (adjusting market vs. Elo weighting, goal scaling, and draw bias) against the field.

---

## ⚠️ Disclaimer

This project is developed **strictly for scientific, educational, and research purposes** as a companion tool for the [SRF Tippspiel](https://wmtippspiel.srf.ch) — a free, non-monetary prediction competition. It does **not** constitute financial, investment, or betting advice; all probability estimates are model outputs subject to uncertainty. Using this software to place real-money wagers is entirely at the user's own risk and explicitly not the intended use case. The author accepts no liability for losses or damages arising from its use.

---

## Technical Highlights

| Component | Detail |
|---|---|
| **Prediction model** | Dixon-Coles bivariate Poisson (ρ = −0.15); SciPy L-BFGS-B reverse-engineer solver for xG |
| **Fixtures & results** | ESPN public scoreboard — full played + upcoming fixture list, live scores, KO-round detection, group standings (no auth, no quota) |
| **Odds ingestion** | The Odds API — consensus **median** across all bookmakers (H2H + O/U 2.5) for upcoming games; ESPN/DraftKings odds as fallback; proportional margin removal |
| **Elo system** | Dynamic ratings for all 48 qualified nations; K = 60; margin-of-victory multiplier; +80 host bonus (USA/CAN/MEX) on post-match updates only |
| **Probability blend** | 70 % bookmaker odds / 30 % Elo, restricted to the win/loss pool — draw probability held fixed to prevent deflation |
| **K.O. phase** | Extra-time xG inflation weighted by P(draw after 90 min) — conditional, not a flat 1.33× multiplier |
| **xP optimiser** | Evaluates all 36 possible tips (0:0 – 5:5) against the full score matrix using the exact SRF Tippspiel scoring rules |
| **Build-a-Bot strategy** | Customizable tipping engine: adjustable market vs. Elo weighting, xG scaling, and draw bias with historical backtesting |
| **Monte Carlo simulator** | Full knockout-bracket simulation (default 20 000 runs) from live Elo ratings — per-team title odds and round-reach probabilities |
| **House bots** | Four fixed-strategy agents: Broker (pure market), Professor (pure Elo), X-Sniper (highest-xP draw), Gambler / Zocker (weighted-random, seeded by match ID) |
| **Caching** | Dynamic TTL: >24 h to kick-off → 12 h; 2–24 h → 1 h; <2 h → 15 min |
| **Elo sync** | On-demand synchronization via `GET /api/sync_elo`; tracks processed match IDs and warms downstream caches post-sync |

---

## Screenshots

<details>
<summary><strong>Score Matrix — Dixon-Coles bivariate Poisson heatmap</strong></summary>

![Score Matrix](docs/screenshot_matrix.png)
</details>

<details>
<summary><strong>Performance View — You vs Algo head-to-head & bot scoreboard</strong></summary>

![Performance View](docs/screenshot_performance.png)
</details>

<details>
<summary><strong>Build-a-Bot — design your own tipping strategy</strong></summary>

![Build-a-Bot](docs/screenshot_build_a_bot.png)
</details>

<details>
<summary><strong>Dashboard — live fixtures with probabilities and algo tips</strong></summary>

![Dashboard](docs/screenshot_dashboard.png)
</details>

---

## Dashboard Views

| View | Description |
|---|---|
| **Dashboard** | All tournament fixtures grouped by day with live probabilities, algo tips, and team form badges |
| **Top Value Bets** | Fixtures ranked by Expected Points — highest xP tip first |
| **Model Edge** | Where Elo diverges most from market consensus — visualised as paired probability bars |
| **Team Form** | Per-team Elo trajectory across the tournament; compare up to 4 teams simultaneously |
| **Groups** | All 12 group standings dynamically computed from the completed-match archive — no extra API call |
| **Performance** | Full analytics: your SRF points, hit rate, You vs Algo head-to-head, bot scoreboard, Build-a-Bot, cumulative points race, and editable match history |
| **K.O. Simulator** | Monte Carlo knockout-bracket simulation — title odds and round-reach probabilities per team |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/matches` | Cache-only fixture/prediction view with odds, Elo, top tip, xP, and model edge; a missing cache returns an explicit `unavailable` payload |
| `POST` | `/api/predict` | Full prediction for one match: xG, score matrix, ranked tips; accepts K.O. toggle |
| `GET` | `/api/archive` | Complete prediction archive: all matches, user tips, algo tips, bot tips, results, and points |
| `POST` | `/api/archive/user_tip` | Save or update a user tip; recalculates points if result is already known |
| `GET/POST` | `/api/custom_bot` | Load / save the Build-a-Bot strategy |
| `POST` | `/api/custom_bot/simulate` | Backtest a bot parameter set against all completed matches |
| `GET` | `/api/simulate_knockout` | Monte Carlo knockout simulation; `?runs=` controls sample size |
| `GET` | `/api/elo_history` | Per-team Elo snapshots across the tournament (powers Team Form chart) |
| `GET` | `/api/elo_ratings` | Current Elo table for all qualified teams |
| `GET` | `/api/match-history/{event_id}` | Cached historical lineup and match statistics; never calls a provider |
| `GET` | `/api/sync_elo` | Trigger an immediate Elo sync from completed match scores; warms all downstream caches |
| `GET` | `/api/recalculate_points` | Recalculates all algorithm and bot points in the archive for completed matches |
| `GET` | `/api/rebuild_honest_tips` | Rebuilds historical pre-match predictions from snapshots and regrades points |
| `GET` | `/api/standings` | Group standings for all 12 WC 2026 groups; 1 h MongoDB cache |
| `GET` | `/api/quota` | Remaining requests for The Odds API and API-Football (ESPN is unmetered) |
| `GET` | `/api/ping` | Keep-alive endpoint (prevents Render free-tier cold starts) |

Provider collection is restricted to authenticated maintenance. Set `CRON_SECRET`
and call `POST /api/internal/maintenance` with `Authorization: Bearer <secret>`.
Maintenance refreshes bounded ESPN fixture windows, stores ClubElo ratings in the
UCL-scoped cache, and makes at most one `h2h,totals` bulk odds request per run.
Snapshot statuses are exactly `fresh`, `stale`, `unavailable`, or `failed`; every
failure payload includes its source and observation/error metadata.

### Provider request schedule and budget

The application has no internal timer. External provider traffic starts only
when an authenticated scheduler calls `POST /api/internal/maintenance`; opening
the dashboard, match detail, simulator, or performance pages uses MongoDB and
makes **zero provider requests**. A MongoDB lease also prevents overlapping
maintenance runs.

| Trigger | Provider calls |
|---|---:|
| UCL fixtures older than 24 hours | 2 ESPN season-scoreboard calls (2026 and 2027); recent results stay in MongoDB between runs |
| Unfinished UCL match from one hour before until six hours after kickoff | ESPN fixtures refresh every 15 minutes at most, so completed results appear promptly |
| ClubElo ratings older than 24 hours | 1 conditional ranking request, plus one team-page request only for each rating missing from the ranking response; stale ratings retry after one hour |
| First maintenance run per Zurich day | 1 ESPN daily team-form scoreboard call; teams previously requiring supplementation add 1 ESPN schedule + 2 FotMob calls each. The current 36-team cache has two such teams, so this is 7 calls normally |
| Team-form catch-up after downtime | At most 7 ESPN daily scoreboard calls plus the same supplemented-team refreshes; 13 calls with the current two supplemented teams |
| Gradual last-10 history fill | At most 6 underfilled ESPN team schedules per Zurich day; one ESPN roster lookup is cached when API-Football and ESPN team IDs must first be mapped |
| Lineups before kickoff | ESPN summary once around T-35 and, only while still unavailable, once around T-15 per match. A confirmed lineup is never fetched again; each run is capped at 12 summaries |
| Final player/team statistics | 1 ESPN summary per completed match |
| Historical lineups | Share the same 12-summary cap with current matches; current fixtures are processed first and cached history fills gradually |
| ESPN lineup fallback | At most 1 API-Football `/fixtures` call per maintenance run and matchday; the response is shared by every due match |
| Odds discovery or any due snapshot | 1 The Odds API bulk call for all events, never one call per match. With one region (`eu`) and two markets (`h2h,totals`), that call costs 2 credits |
| No discovery and no due snapshot | 0 The Odds API calls |

Odds snapshots become due at T-24h, T-6h, T-75m, T-30m, and T-15m. All events
and all buckets due in the same maintenance run share the one bulk response.
Therefore the scheduler should call maintenance around those windows for each
kickoff group and once daily otherwise, rather than run a blind every-minute
job. A late call records earlier uncaptured buckets as `unavailable` instead of
spending extra credits to reconstruct them.

API-Football calls used by team form are serialized across workers, separated
by at least seven seconds, limited to nine per minute, and hard-stopped at 100
per UTC day. If the configured plan rejects the current UCL season, only the
first team-form request after a process start reaches API-Football; the process
then remains on the ESPN fallback. The current fallback bootstrap uses 1 failed
API-Football attempt, 1 ESPN roster call, 36 ESPN schedule calls, and 4 FotMob
calls for the two supplemented teams: 42 one-time outbound requests. Bootstrap
progress is resumable, so completed teams are not fetched again.

The UCL match response reads the team roster once, loads the required form
documents in one indexed MongoDB query, and loads their cached historical match
summaries in one further indexed bulk query. The existing `_id` keys already
provide the required index; no data migration or new collection is needed.

Lineups and match statistics follow the same rule: only authenticated
maintenance contacts a provider. ESPN is the primary source. If ESPN has not
published a due lineup and an API-Football key is configured, one day-level
request first caches API-Football's fixture IDs. The next due run requests up to
20 cached IDs together, including their available lineups and statistics. A
late T-15 discovery schedules exactly one enrichment retry. Every call passes
through the same shared 100-per-day request gate as team form. Match-detail page
loads only read the cached `match_intelligence:<event_id>` document and clearly
show when a lineup or injury information is not available.

### Champions League team form

The dashboard and match detail read each club's last ten competitive matches
from MongoDB; public page loads never call a provider. Initialise or resume the
cache with:

```bash
.venv/bin/python scripts/bootstrap_ucl_team_form.py
```

API-Football is the primary source. Its requests are shared across concurrent
workers, spaced by at least seven seconds, capped at nine per minute and 100 per
day, and progress is stored after every club so an interrupted run can resume.
If that subscription rejects season 2026 or the `last` fixture parameter, the
same bootstrap transparently switches to ESPN's current UCL roster and each
club's all-competition schedule. If ESPN exposes fewer than ten completed
matches for a club, an exact-name FotMob lookup supplements only that club.
Stored rows identify their source as `api_football`, `espn`, or
`espn+fotmob`; no synthetic form or historical season is substituted.
The detail view derives goals scored/conceded, per-match averages, clean sheets,
and both-teams-to-score counts directly from those rows. A player is labelled
in form only after at least three cached ESPN match summaries with explicit
individual statistics and only from recorded goals, assists, and confirmed
starts or goal-contributing substitute appearances; otherwise the UI reports
the current sample size instead of guessing.

The authenticated daily maintenance refreshes yesterday's fixtures and catches
up at most seven missed days. It also deepens at most six incomplete team
histories per Zurich day. Historical ESPN event IDs then enter the existing
match-intelligence queue after current fixtures, sharing its cap of twelve
summary calls per run. The UI can therefore reveal archived old lineups without
ever contacting a provider during a page view; rows without a compatible event
ID remain explicitly unavailable. Clubs that needed the FotMob supplement also
get one team-specific refresh per Zurich day. Provider errors keep the last
successful rows visible as `stale`; without a cached row the UI shows an
explicit unavailable state. `USE_API_FOOTBALL` selects the optional odds engine
only and does not disable this cache reader. ESPN and FotMob's public endpoints
are undocumented fallbacks, so their availability remains an operational risk.

For an existing deployment, run `.venv/bin/python scripts/migrate_wc_legacy.py`.
The migration is copy-first and idempotent: it tags legacy archive/cache/custom
bot documents as `competition=wc2026`, preserves IDs and user tips, and never
deletes the legacy documents.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, SlowAPI |
| Math | NumPy, SciPy (`optimize.minimize`, L-BFGS-B), Pandas |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router |
| Charts | Recharts (Elo trajectory, cumulative bot race, simulation odds) |
| Data | ESPN public API (fixtures, scores, standings, KO rounds), The Odds API / API-Football (multi-bookmaker odds), MongoDB Atlas (archive, cache, bot states) |

---

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/SajanthChandrakumar/wm2026_predictor.git
cd wm2026_predictor

# 2. Backend: virtual environment + dependencies
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment variables
echo "ODDS_API_KEY=your_key_here" > .env
echo "MONGO_URI=mongodb+srv://..." >> .env
echo "API_FOOTBALL_KEY=your_api_football_key" >> .env

# 4. Frontend: build the React app (FastAPI serves the dist/ folder)
cd frontend-v2 && npm install && npm run build && cd ..

# 5. Start
uvicorn src.api:app --reload
```

Open **http://127.0.0.1:8000**. For frontend development with hot reload, run `npm run dev` inside `frontend-v2` (proxies `/api` to port 8000).

---

## Project Structure

```
wm2026_predictor/
├── src/
│   ├── api.py                     # FastAPI app: init, middleware, router wiring
│   ├── math_engine.py             # Elo, xG solver, Dixon-Coles, xP, pool optimiser
│   ├── constants.py               # Team mappings, cache TTLs, score helpers
│   ├── odds_engine.py             # The Odds API client & consensus odds parsing
│   ├── odds_engine_apifootball.py # API-Football (api-sports.io) alternative engine
│   ├── quota_store.py             # API request quota persistence
│   ├── routes/                    # matches, predict, custom_bot, simulate
│   └── services/                  # ESPN data, odds helpers, archive, Elo sync, Monte Carlo
├── frontend-v2/                   # React 19 + Vite + Tailwind SPA (live frontend, served from dist/)
├── data/                          # Elo ratings, caches, backups
└── ARCHITECTURE.md                # Full mathematical derivation
```

---

## Running Tests

```bash
.venv/bin/python -m pytest -q
cd frontend-v2
node --test tests/*.test.mjs
npm run typecheck && npm run lint && npm run build
```
