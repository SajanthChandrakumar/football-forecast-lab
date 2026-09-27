# Data Pipeline Repair Implementation Plan

**Goal:** Restore reliable UCL data refresh, make the simulator consume the same predictions as the dashboard, and keep every screen competition-correct and truthful.

**Architecture:** ESPN remains the fixture source, ClubElo remains the rating source, and The Odds API remains the only bookmaker source. Authenticated maintenance computes and stores open-match predictions once; public reads present cached data without provider calls or expensive recomputation.

**Tech stack:** FastAPI, MongoDB-shaped cache collections, React/TypeScript, Node test runner, pytest.

## Global constraints

- Preserve real bookmaker odds and archived pre-match snapshots; never replace them with model odds.
- Do not invent Elo ratings, odds, history, or performance results.
- Public endpoints stay read-only with respect to provider credits.
- Keep WC behavior working while repairing UCL behavior.
- Preserve unrelated user changes in the primary checkout.
- Use test-first changes and verify each task independently.

### Task 1: Repair ESPN UCL refresh and logo parsing

**Files:**
- Modify: `src/services/espn_data.py`
- Modify: `src/services/maintenance.py`
- Test: `test_task2_providers.py`

**Behavior:**
- Fetch UCL scoreboards by supported calendar-year values (`dates=2026`, then `dates=2027` only when the requested window crosses years) instead of unsupported hyphenated ranges.
- Filter the returned season payload back to the requested date interval and keep event-id deduplication.
- Keep WC's existing range behavior unchanged.
- Read logos from either the current ESPN `team.logo` field or legacy `team.logos[0].href`.
- Maintenance merges refreshed fixtures with existing cached odds and predictions.

**Verification:** focused provider tests must fail before the fix and pass after it; all provider/maintenance tests pass.

### Task 2: Persist UCL predictions and make reads/simulation consistent

**Files:**
- Modify: `src/services/maintenance.py`
- Modify: `src/routes/matches.py`
- Modify: `src/routes/simulate.py` only if a cache-only fallback remains necessary
- Test: `test_ucl_coverage_plan.py`
- Test: `test_task6_integration.py`

**Behavior:**
- After fresh ClubElo ingestion, maintenance runs the existing UCL enrichment pipeline for open fixtures and stores probabilities, xG, model tip, provenance, and score matrix in `matches_cache.data`.
- Existing bookmaker odds remain unchanged.
- `/api/matches` uses already complete cached UCL predictions without recomputing every fixture, while retaining fallback enrichment for legacy/incomplete caches.
- `/api/simulate_ucl` succeeds from the same stored matrices shown by match detail and stays explicitly unavailable if a required matrix truly cannot be produced.

**Verification:** regression tests prove matrices are stored, odds survive, cached reads avoid prediction recomputation, and the simulator receives valid matrices.

### Task 3: Fix competition-scoped and truthful frontend views

**Files:**
- Modify: `frontend-v2/src/components/shared/PageTransition.tsx`
- Modify: `frontend-v2/src/features/dashboard/DashboardView.tsx`
- Modify: `frontend-v2/src/features/value-bets/ValueBetsView.tsx`
- Modify: `frontend-v2/src/features/team-form/useTeamFormData.ts`
- Modify: `frontend-v2/src/features/team-form/EloChart.tsx`
- Modify: `frontend-v2/src/features/performance/PerformanceView.tsx`
- Modify: `frontend-v2/src/lib/competition.mjs`
- Modify: `frontend-v2/src/lib/performance.mjs`
- Modify: `frontend-v2/tests/competition-api.test.mjs`

**Behavior:**
- Page kickers derive from the active competition; no UCL page says WM and no WC dashboard says UCL.
- Value Bets contains only upcoming, unplayed fixtures.
- UCL Team Form is limited to the 36 teams in the UCL standings and explicitly says when only a current rating exists instead of drawing invented history.
- Official algorithm totals count only saved pre-match predictions. Elo reconstructions remain visible as estimates in a separate line but do not inflate the official total or official hit rate.

**Verification:** Node behavior tests fail first and pass after implementation; typecheck, lint, and production build pass.

### Task 4: Full-system acceptance

**Files:** none unless acceptance finds a regression.

**Behavior:**
- Run the full backend and frontend suites.
- Start the isolated app with the configured local database.
- Trigger authenticated UCL maintenance once when credentials are available.
- Browser-check dashboard, detail, performance, value bets, edge, team form, table, and simulator in UCL and WC modes at mobile width.
- Confirm no JavaScript errors or failing API responses; confirm UCL fixture count, logos, model odds, simulator results, and honest unavailable states.
