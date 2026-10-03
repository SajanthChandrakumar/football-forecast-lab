# Comparison, tipping and forecast evaluation implementation plan

> **For agentic workers:** Use subagent-driven-development task by task. The user authorized implementation of all five proposed improvements and deferred their own review/testing. Continue without another approval gate.

**Goal:** Make comparing teams, entering shared tips and understanding/evaluating forecasts useful without explanation.

**Architecture:** Extend the existing React views, query cache and shared tip API. Use competition-scoped browser storage for comparison selections. Add a read-only evaluation of immutable pre-kickoff probabilities, reusing the current prediction service without fetching providers or changing the model.

**Tech Stack:** Existing React, TypeScript, TanStack Query, Recharts, FastAPI, Python and Node test runner. No new dependencies.

**Spec:** The five improvements accepted in the conversation on 2026-10-03: immediately useful team comparison, direct match-list tipping, short evidence-based explanation, consistent charts/mobile tables, visible fair forecast evaluation.

## Global constraints

- Preserve existing uncommitted redesign and unrelated data/elo_history.json, data/elo_ratings.csv and photos.
- Work in the current codex/wm-ux-refresh checkout; no commits, pushes, deployments or live database test writes.
- UI copy is German. Shared tips must be described as shared; cutoff is T-5. Missing timestamps, probabilities and historical data remain explicit.
- Keep current dark green/lime design and light/dark themes. All meaningful actions and fields must work on a 390px screen and with keyboard navigation.
- Never equate outcome probability with confidence in the exact score. Never claim form or lineup data was a model input if it was not.
- Evaluation uses only timestamp-verified pre-kickoff probability vectors and the same matches for all compared methods; exclude reconstructions and ambiguous extra-time outcomes. Keep probability metrics separate from tip-game points.
- Use isolated runtime/test data under /private/tmp. Never print or include .env or credentials in outputs.

### Task 1: Comparison and tipping workflows (proposals 1 through 4)

**Files:** AppState.tsx, team-form views/helpers, DashboardView.tsx, FixtureRow.tsx, DetailView.tsx, hooks/queries.ts, MatchHintCard.tsx, matchHint.ts, chart components and index.css; focused Node behavioral tests.

- [x] Persist sanitized competition-scoped selections (unique strings, max four) and expose setSelectedTeams. On first use select both teams of the next valid fixture; fall back to the two highest available ratings. Explicit user clearing must stay empty rather than automatically reselecting.
- [x] Keep team search visible; show selected chips, side-by-side Elo/results and recent dated archive games. Explain sparse samples. Add a comparison entry from match detail using both canonical team names.
- [x] Use theme-aware chart colors, honest timestamp labels, accessible legends and mobile rank-list layout without page overflow. Sort recent results chronologically.
- [x] Add direct shared-score input to the overview using the existing API, open/unsubmitted filter, saved state, clear pending/error states and an optional save-and-next action. Scores are nonnegative integers. Read-only after T-5. Never announce save success before API success; retain input on failure. Invalidate archive and matches caches after saving.
- [x] Add concise outcome probabilities, source/age and evidence-based context near the recommendation. Reuse existing helpers and keep detailed data collapsible. Avoid implying unverified causal relationships or exact-score certainty.
- [x] Run focused behavioral tests, typecheck and build. Report file list and any remaining browser verification needs.

### Task 2: Fair forecast evaluation (proposal 5)

**Files:** src/services/prediction.py, src/services/maintenance.py, new focused model-evaluation service/router and Python tests, src/api.py, frontend API/types/query and a forecast-evaluation component in PerformanceView.

- [x] Capture an immutable evaluation_forecast at the existing freeze point containing capture time, kickoff, model version and model/market/Elo 1X2 probabilities from that run's known inputs. Reuse the service's probability calculation. Enforce the existing T-15 to T-5 window before any new freeze; preserve existing frozen entries and user tips.
- [x] Capture the same evaluation record during authenticated maintenance when an eligible fixture falls within T-15 through before T-5. This path writes only prediction.evaluation_forecast through a conditional update; it must preserve top_tip, model_tip, user_tip, bots and result fields. It adds no provider calls. Public reads remain read-only. Do not retrofit already frozen historical records.
- [x] Add a competition-scoped, cache/archive-only GET endpoint. Include only completed matches with valid pre-kickoff captures and valid model, market and Elo vectors on a common sample. Reject invalid vectors, after-kickoff capture, reconstruction and ambiguous KO result basis. Report counts and exclusion reasons.
- [x] Compute multiclass Brier (sum of three squared errors, range 0–2) and natural-log loss with a documented probability floor. No empty-sample zero metrics. Do not retrofit older records using today's inputs.
- [x] Show a German evaluation panel alongside existing point scoring, with common sample count, forecast coverage/exclusions, all three methods, metric definitions and an honest empty state. No unsupported superiority claim.
- [x] Add focused Python tests for scoring, timestamp exclusion, common sample and capture immutability; build and run the relevant suites in an environment without the real .env.

### Task 3: Integration and visible verification

- [x] Rebuild frontend-v2/dist, update the isolated preview runtime and restart it if backend files changed.
- [x] Exercise default selection, explicit clearing, selection persistence, detail-to-comparison, tip filter, score validation and saving against disposable test fixtures only.
- [x] Check 390px and desktop layouts plus dark/light charts and the evaluation empty/populated states.
- [x] Record final test evidence and remaining limits. Hand the user the working preview and a concise summary.
