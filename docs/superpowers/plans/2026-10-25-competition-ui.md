# Competition UI implementation plan

Goal: cleaner, elegant full-app UI with competition themes and compact match-first information hierarchy.
Architecture: extend the existing CSS token system and shared React components. Preserve backend/public interfaces and all existing feature logic.
Spec: docs/superpowers/specs/2026-10-25-competition-ui-design.md

## Global Constraints
- WM/UCL/PL presentation only; no model/math/provider/database writes or production actions.
- All functions, warnings, source provenance, historical forecasts, tips and T-5 behavior remain intact.
- No added dependencies or fabricated logos/measurements.
- Shared existing worktree; changes in the original checkout must remain untouched.
- All delegated agents use gpt-6-luna with xhigh, no nested agents. Run implementers sequentially.

### Task 1: Themes and app shell
Own src/index.css, src/hooks/useTheme.ts, src/state/AppState.tsx, src/components/layout/AppShell.tsx, src/components/layout/Navigation.tsx, index.html, e2e/fixtures.ts competition helper, new e2e/competition-themes.spec.ts. Paths under frontend-v2 unless stated.
Implement six coherent competition/appearance combinations with separate accent and semantic tokens; remove hardcoded green shell styling. Preserve current light/dark and competition storage, initialize without wrong-theme flash, synchronize html data-competition. Replace select with three accessible buttons ordered WM/UCL/PL, with competition labels and aria-pressed, keep room for readable mobile branding. Preserve menu focus/escape, supported routes, settings and state isolation. Update chooseCompetition helper to buttons without altering fixture API behavior. Add behavior-level failing E2E before implementing: switch changes competition/appearance independently, reload persists selection, switches are keyboard accessible, no extra refresh/mixed data. Run focused tests/typecheck and self review; building dist for the focused browser checks is allowed; no commit (controller integrates).

### Task 2: Compact fixtures and progressive disclosure
Own src/features/dashboard/FixtureRow.tsx, DashboardView.tsx if necessary, new features/dashboard/fixtures.css imported once by FixtureRow, new e2e/compact-fixtures.spec.ts, necessary updates to fixture-specific E2E only. Do not edit index.css, fixtures.ts, or other task-owned files.
Replace match cards in the fixture list with compact rows while preserving props and every caller. Show time/status, team crests/names, clearly labelled actual result vs model tip, concise data warning; put chances and optional details behind an accessible disclosure. Keep detail link immediately available and saved-tip status visible. Shared-tip mode editor must remain immediately accessible/open for focus and save-and-next; preserve callbacks and deadlines. Mobile names stacked with readable adjacent result, desktop aligned rows; long names wrap rather than truncate essential content. Outcomes/provenance not lost. Add behavior test before implementation: default compact/probabilities hidden until disclosure, home-away order and result label, keyboard disclosure, open tips autofocused/save callback preserved; test fresh/pending/played/missing data. Use existing shared components/math untouched. Run focused E2E/typecheck and self-review; building dist for focused browser checks is allowed; no commit.

### Task 3: Consistent data views and charts
Own targeted presentation changes in features/detail (except math), groups, team-form, performance, edge, value-bets, simulator, shared MatchDataStatus and presentation helpers; new src/data-views.css imported by App.tsx; new e2e/data-views.spec.ts. May also adjust presentation-only classes in features/dashboard/MatchdayRadar.tsx and MatchdayAssistant.tsx (not FixtureRow/DashboardView/fixtures.css). Do not edit index.css/layout/state/lib API/model files or other task tests.
Use existing view/tab structures, add a consistent restrained visual hierarchy across every page, concise descriptions, readable summaries and numeric tables, chart legends and units. Remove fixed decorative green accents; use accent tokens for UI and stable semantic/series colors for data. Keep every function/data value/status/callback. Avoid introducing duplicate summaries or speculative abstractions. Ensure existing WM tab labels are not clipped and source warnings stay apparent. Where behavior is changed add focused failing tests first; simple visual styles verified by screenshots, no tests mirroring CSS values. Chart series need contrast on light/dark and non-color legend identification. Run focused tests/typechecks and self-review; building dist for focused browser checks is allowed; no commit.

### Task 4: Integration, review and acceptance
Controller adapts existing tests to the approved layout without weakening behavioral assertions, audits six theme combos, snapshots main routes at five widths, verifies keyboard/contrast/data truth and save states. Run complete frontend unit/browser suites, typechecks/lint/build, backend regressions isolated from local credentials. Independent Luna xhigh review of final diff; address real findings. Preserve preexisting files. Produce acceptance report with local results and explicit deferred live check, final scoped commit with source and generated dist. No automatic production release for this UI request.
