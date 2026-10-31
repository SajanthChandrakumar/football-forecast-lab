# Club Fast Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** Serve PL/UCL overview and selected-match core data from small prepared records, retaining current data honesty and all frozen predictions.
**Architecture:** Existing protected/in-process maintenance prepares fenced, versioned persisted read views; public GETs only read them. Individual game core and analysis endpoints replace full-season detail downloads; archive reads can be bounded to one game.
**Tech Stack:** Existing FastAPI/PyMongo, React/React Query, pytest, Playwright. No new dependency.
**Spec:** docs/superpowers/specs/2026-10-28-club-fast-views-design.md

## Global Constraints

All requirements in Spec apply. Use Luna xhigh for all delegated tasks. Worktree /Users/Sajanth/.codex/worktrees/pl-ucl-quality/wm2026_predictor, branch codex/club-fast-views, base f9f5494. Original checkout has 39 changed tracked paths, patch SHA256 bcb6e89334f8868b71e58dc3f286188625be752b1cce5bb517c0a97ebe348a50. No product data migrations or paid refresh during acceptance. Reversible derived-cache warmup may only read stored sources and write namespaced derived records through protected/background preparation.

## Task 1: Backend prepared views and bounded game reads

Owner backend agent: Python files only. Create src/services/club_views.py and test_club_views.py; modify routes/matches.py, services/maintenance.py, services/forecast_worker.py, services/user_tips.py and api.py only as required. Do not change math/forecast semantics.

Interfaces for frontend:
- Existing GET /api/matches?overview=true&competition=club returns the same Match[] fields with detail_level='overview', now from compact materialization. No season read/enrichment/archive join in public overview path. Missing initial snapshot returns HTTP202 JSON {status:'processing',data:[],source:'club_views',reason:'preparing',retry_after:2}; actual outage remains error/last valid state, no hidden synchronous rebuild.
- GET /api/matches/{match_id}?competition=club returns one core Match with latest prepared readiness/tips/chances/provenance and detail_level='core'; no matrix/forms/lineups. Include archived_prediction (Prediction-shaped, without heavyweight matrices) when a frozen completed-game prediction exists. HTTP404 if proven absent; HTTP202 processing if initial views not ready.
- GET /api/matches/{match_id}/analysis?competition=club returns one full Match enriched for just its two teams and selected intelligence; preserve kickoff cutoff and frozen values. Same processing/not-found contract; request timeouts/cancel in frontend. Source core + analysis must be identity/version checked so late responses cannot overwrite another match/newer core.
- GET /api/archive?competition=...&match_id=... is additive, returns Archive object keyed by requested canonical ID; bounded DB read. Omitting match_id preserves current contract and shared write handling.
- Public GETs perform no provider requests or mutations. Default full season and WM remain unchanged.

Steps:
- [x] Write/run failing tests for small query reads, exact IDs/aliases, fixture/source/version changes, fencing/parallel writers, failures preserving prior data, readiness, frozen archives and no public writes/providers.
- [x] Implement prepared overview and per-game records. Use same known presentation logic or small extracted shared seam, no duplicate math. Publish compact payload atomically; prevent old builders overwriting newer data; skip unchanged data and bound old records.
- [x] Connect startup/cache-only preparation plus maintenance/results/odds/prediction/manual and shared-tip seams. Saved tips must be visible immediately without waiting for the worker. Retain real source dates.
- [x] Add public bounded endpoints and optional archive match_id. Cover cold preparation202 and selected-match form history cutoff.
- [x] Run focused and entire backend suites; report RED/GREEN evidence and unresolved operational limitations. No commit until controller review.

## Task 2: Frontend targeted detail and freshness

Owner frontend agent: frontend-v2 source/tests/e2e only; controller owns dist/build/browser.
- [x] Add API/hooks for core/analysis and bounded per-game archive with separate invalidation-safe query keys. New route visits revalidate stored state; active view refetch interval60s. Match detail never downloads full season merely to find one match or fill logos. WC uses existing flow.
- [x] Load core first and render real tip/chances without waiting for heavy analysis. Load form/lineups/model detail when needed, merge only matching canonical identity/input version, retain drafts and errors. Missing data is distinct from loading or failed request.
- [x] Handle overview/core HTTP202 processing explicitly with bounded automatic polling and retry. Default last good query payload stays visible if refresh fails; stop polling on inactive/expired status; no provider refresh from GET.
- [x] Save invalidation updates own tip and correct competition/archive/core/overview immediately; hidden views do not continue heavy work. Scope keys avoid truncating full data.
- [x] Write RED/GREEN regression cases using realistic mocked core/analysis responses, blocked heavy requests, failure/retry and aliases. Update old request-shape tests to new intentional contracts, preserve all previous workflows.
- [x] Run unit/type/lint checks only; no build/browser while controller owns immutable browser build.

## Task 3: Independent review, integration and release

- [x] Independent Luna xhigh preflight and final reviews; fix blocking findings and re-review.
- [x] Controller runs backend, frontend unit/type/lint/build and full Playwright suite across five widths, preserving immutable build.
- [ ] Commit/push scoped code, docs and dist; create/attach PR; wait exact-head green CI and merge under prior release authorization.
- [ ] Verify deployed revision/assets and cache-only background preparation; measure warm PL/UCL overview and representative core reads >=5 samples each, including first ready reads. Record p95/worst, unavailable/processing responses and hosting wake separately. No paid/prod shared-write tests. Report target honestly if unmet.
- [ ] Preserve release evidence outside scratch, remove only this plan's scratch workspace and retain worktree/unrelated files.

## Preflight ruling

Publication must fence against input/archive changes as well as other view builders. Maintenance lease alone is insufficient because forecast capture and shared-tip archive writes have separate paths. Cover paused old build -> newer source/archive notification -> old publish rejection, even before a replacement view publishes. Connect results_only and idle/error returns when they mutate stored results/predictions. A view_version is deterministic per canonical prepared match and shared by core/analysis; freshness dates never stand in for that token.

## Live acceptance follow-up: lossless database transfer

PR #28 passed local/CI verification and deployed as `4825cb3`. Repeated production core reads met the two-second target (PL <=0.54s; UCL <=0.31s), but overview reads did not (PL up to9.22s; UCL up to4.48s). Those unsuccessful measurements remain in release evidence; the initial PL HTTP202 preparation responses are not counted as ready successes.

Retain all presentation/provenance/frozen fields and atomically store a gzip JSON representation beside the canonical overview array in the same derived head. Clean schema2 readers project only those bytes, then decode and re-age freshness per request. Publish and tip patches update both representations together. Schema/encoding checks and an array fallback for legacy or dirty heads preserve rolling-deployment compatibility with old publishers/tip writers; transitional fallback reads may remain slower. Idle worker checks verify BSON field presence/type without transferring the payload. Split database-read, preparation and serialization Server-Timing measurements. Validate regressions, run the full backend suite, obtain scoped independent review, then repeat the already authorized push/CI/merge/live measurements. No frontend, WM, provider, model or historical archive changes are needed for this follow-up.
