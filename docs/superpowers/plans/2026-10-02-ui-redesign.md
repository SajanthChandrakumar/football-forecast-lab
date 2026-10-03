# UI redesign implementation plan

**Goal:** Implement the UI audit and give the application a clear visual hierarchy. Following the user's feedback on the first design, use a dark green navigation, sharp typography, lime accents and compact match lists. The user explicitly requested immediate implementation and postponed review.

**Architecture:** Keep the existing routes, API and dependency set. Reuse design tokens, shared cards and native disclosures. Work in the current feature branch, preserving unrelated Elo data and photographs.

**Global constraints:** German product copy, shared tips labelled honestly, no fictional data, no new dependencies, source/age visible, accessible native controls, maintain responsive layouts and dark mode. Rebuild the served `frontend-v2/dist`. No commit, push or deployment requested. Review is deferred at the user's explicit request.

## Tasks and ownership

- [x] Root: shared design tokens, page headers, navigation, scroll restoration, dashboard rows, period-filtered tip chances and uniform query states.
- [x] Performance worker: common-sample comparison, shared-tip language, read-only completed history, empty backtests, German bot/chart copy and progressive disclosure. Own `features/performance/*`, `lib/performance.mjs`, focused tests.
- [x] Detail worker: clear match summary, kickoff and data age, shared/custom tip input, error states, translated advanced information and usable pool form. Own `features/detail/*` and detail-specific helpers/tests.
- [x] Analysis worker: WM probability fix with regression test; readable simulator, labelled model comparison, tables and team coverage. Own `features/{simulator,edge,groups,team-form}/*`, `src/services/monte_carlo.py`, focused helpers/tests.
- [x] Root: run Node tests, Python regression, TypeScript, lint and production build. Resolve integration failures. Verify served assets and basic rendering if browser access is available. Leave user a local runnable result.

## Test contracts

WM probabilities must be nonincreasing across later rounds and sums across teams must be 800/400/200/100 percent. Common performance comparison excludes reconstructed or missing model tips and untipped games. Tip chances default to the next available week and show at most twelve before expansion. Missing data must not produce zero-percent achievement claims. Completed tips have no writable control. Pure styling uses build/typecheck rather than implementation-mirroring tests.

## Execution decisions

Direct implementation without approval gates follows the user's explicit instruction. Technical checks remain required; separate review agents are deferred. Current branch is already `codex/wm-ux-refresh`, with only unrelated data changes before implementation.

## Verification and handoff

62 frontend tests and 241 Python tests pass. The full Python suite ran in a temporary copy without the local `.env`, because three environment-isolation tests otherwise reload local credentials. TypeScript and the production build pass; lint has no errors and five Fast Refresh export warnings. Basic rendering checked for the UCL routes at the normal mobile panel size and the desktop game list at 1440 × 900. The mobile menu's inert background, Tab/Shift+Tab focus trap, Escape and focus return were exercised. Saving shared tips and bots remains for the user's later testing.

The local preview is at `http://127.0.0.1:8000/`, using a temporary runtime copy to preserve local data. `frontend-v2/dist` in the project contains the rebuilt release. No commit, push or deployment was performed.

## Design revision after user feedback

Replaced the pale card layout with a sports data interface: a dark sidebar and SVG icons, a next-matchday summary using actual fixtures, compact rows with aligned time/team/source/tip/action columns, and stronger shared headings. Preserved competition selection, disclosures, cached search/round state, source labels, shared-tip semantics, and the mobile dialog. Removed the obsolete test that asserted the exact colors of the rejected design; 61 functional and existing UI tests remain.
