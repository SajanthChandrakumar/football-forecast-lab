# UCL All-Competition Team Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache and display each current UCL club's five latest completed competitive matches from API-Football without spending provider quota on public reads or changing prediction formulas.

**Architecture:** A dedicated `TeamFormService` owns API-Football parsing, cache documents, bootstrap resume state, daily catch-up, and stale fallback. Authenticated maintenance is the only recurring provider boundary. Match presentation performs cache-only UCL enrichment; WC retains its current in-memory form behavior. The frontend consumes an additive form payload for compact card badges and an expanded detail list.

**Tech Stack:** Python 3, FastAPI, MongoDB/PyMongo-compatible collections, requests, React/TypeScript/Vite, Node tests.

**Spec:** `/Users/Sajanth/.codex/attachments/45d680b4-5dcd-4b19-9b1d-e0d4df3da824/pasted-text.txt`

## Global Constraints

- Use API-Football v3 through `API_FOOTBALL_KEY`; never expose the key to the frontend.
- The form provider is independent of `USE_API_FOOTBALL`.
- Public UI and `force=true` requests must never call API-Football.
- Respect 100 requests/day and at most 9 requests/minute for bootstrap; daily refresh requests only pages that exist and catches up at most seven dates.
- Store competition-scoped documents and preserve successful data on provider failure.
- Only `FT`, `AET`, and `PEN` competitive fixtures count; friendlies and duplicate fixture IDs do not.
- Form is display-only and must not affect Elo, xG, probabilities, or tips.
- WC behavior must remain unchanged.
- Tests use complete fake responses and no real provider calls.

---

### Task 1: API-Football Team Form Service

**Files:**
- Create: `src/services/team_form.py`
- Create: `test_team_form.py`

**Interfaces:**
- Produce `ApiFootballClient(api_key, request_fn=None)` with `request(path, params) -> dict`, recording quota headers through `write_quota("football", ...)`.
- Produce `TeamFormService(cache_collection, client, competition="ucl2026", now_fn=None)`.
- Produce parsing/merge methods returning normalized matches with `fixture_id`, `played_at`, `competition_name`, `opponent_id`, `opponent_name`, `venue`, `goals_for`, `goals_against`, `score`, and `result`.
- Store teams in `ucl2026:team_form_teams`, form rows in `ucl2026:team_form:<team_id>`, and sync state in `ucl2026:team_form_sync`.

- [ ] Add failing fake-response tests for team parsing, stable IDs, home/away perspective, allowed statuses, friendly exclusion, sorting, five-item limit, and fixture-ID deduplication.
- [ ] Implement the smallest service/parser that satisfies those tests.
- [ ] Run `python -m pytest -q test_team_form.py`.

### Task 2: Resumable Bootstrap CLI

**Files:**
- Create: `scripts/bootstrap_ucl_team_form.py`
- Modify: `src/services/team_form.py`
- Modify: `test_team_form.py`

**Interfaces:**
- Extend `ApiFootballClient` with injectable pacing, API-error validation, a maximum of nine requests per minute, and a persisted daily request guard capped at 100 requests across CLI and maintenance.
- `TeamFormService.bootstrap(season=2026, sleep_fn=time.sleep, min_interval_seconds=7) -> dict` dynamically fetches `/teams?league=2&season=2026`, then `/fixtures?team=<id>&last=5`.
- Progress persists in `ucl2026:team_form_bootstrap` with completed team IDs and can resume without refetching completed teams.

- [ ] Add failing tests for dynamic team count, resume, no duplicates, API error payloads, daily budget, and at least seven-second pacing between fixture requests.
- [ ] Implement bootstrap and a CLI that creates the Mongo collection only after validating `MONGO_URI` and `API_FOOTBALL_KEY`.
- [ ] Run the focused tests without any real network access.

### Task 3: Daily Authenticated Maintenance

**Files:**
- Modify: `src/services/team_form.py`
- Modify: `src/services/maintenance.py`
- Modify: `src/routes/maintenance.py`
- Modify: `src/api.py`
- Modify: `test_team_form.py`

**Interfaces:**
- `TeamFormService.refresh_daily(now=None, max_catchup_days=7) -> dict` reads `last_successful_date`, fetches yesterday/catch-up dates with Europe/Zurich semantics, follows `paging.current < paging.total`, filters stored UCL team IDs, merges idempotently, and caps five matches per team.
- `run_maintenance(..., team_form_service=None)` invokes that method for UCL only and reports `team_form_status` without coupling it to odds calls.
- Failures mark existing form documents stale with `error` and `observed_at`; they never clear `matches`.
- With no prior successful date, refresh yesterday only. With a gap, process the oldest pending dates first and advance `last_successful_date` only after every page for that date succeeds.
- Missing `API_FOOTBALL_KEY` leaves the feature explicitly unavailable and must not prevent application startup or WC maintenance.

- [ ] Add failing tests for paging, idempotence, oldest-first seven-day catch-up, stored-team filtering, missing-key startup, and stale fallback preserving successful rows.
- [ ] Wire the service into authenticated maintenance independently of the selected odds engine.
- [ ] Run focused maintenance and authorization tests.

### Task 4: Cache-Only Match Enrichment

**Files:**
- Modify: `src/services/team_form.py`
- Modify: `src/routes/matches.py`
- Modify: `test_team_form.py`

**Interfaces:**
- `TeamFormService.cached_form_for_match(team_name, fallback_team_id=None) -> dict` returns `{status, source, observed_at, error, form, on_fire, matches}`.
- UCL presentation enriches copies of cached fixtures with `home_form` and `away_form`; missing data is an explicit `unavailable` payload.
- WC continues using `math_engine.team_forms` exactly as before.
- Resolve names only through exact provider names or existing `TEAM_MAPPING` canonical aliases; unresolved teams remain unavailable and never use fuzzy matching.
- Stored `matches` remain newest-first; the compact `form` sequence is oldest-to-newest so the newest badge is on the right.

- [ ] Add failing tests proving cache-only UCL reads, explicit unavailable form, and unchanged WC behavior.
- [ ] Implement additive enrichment without mutating prediction inputs or calling providers.
- [ ] Run focused route tests.

### Task 5: Frontend Form Display

**Files:**
- Modify: `frontend-v2/src/lib/types.ts`
- Modify: `frontend-v2/src/components/shared/Badges.tsx`
- Modify: `frontend-v2/src/features/dashboard/FixtureRow.tsx`
- Modify: `frontend-v2/src/features/detail/DetailView.tsx`
- Create or modify: `frontend-v2/tests/team-form-match-display.test.mjs`

**Interfaces:**
- Extend `TeamForm` additively with `status`, `source`, `observed_at`, `error`, and `matches`; keep `form` and `on_fire` for compatibility.
- Match cards render the last five textual result badges for both teams and `Form nicht verfügbar` when unavailable.
- Detail view renders opponent, score/result, competition, and localized date per recent match.

- [ ] Add failing source/behavior tests for compact cards, accessible non-color labels, detail rows, unavailable copy, and mobile-safe layout classes.
- [ ] Implement the compact presentation without crowding the primary tip.
- [ ] Run frontend Node tests and typecheck.

### Task 6: Configuration, Documentation, CI, and Acceptance

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `.github/workflows/*` only where the existing workflow needs the new test file or environment placeholders.

- [ ] Document bootstrap, daily request budget, cache IDs, recovery behavior, and that no public request spends quota.
- [ ] Ensure examples contain placeholders only and no secret values.
- [ ] Run `python -m pytest -q`.
- [ ] Run frontend Node tests, `npm run typecheck`, `npm run lint`, and `npm run build`.
- [ ] Browser-check Dashboard and Match Detail at mobile and desktop sizes with cached fixtures; confirm no provider request is caused by viewing either page.
