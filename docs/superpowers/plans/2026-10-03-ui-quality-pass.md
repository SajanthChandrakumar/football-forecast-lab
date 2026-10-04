# UI quality pass

Goal: Make the existing football dashboard reliable and readable on small phones, tablets and desktop, and protect its main workflows with browser regressions.

Architecture: Keep React, TanStack Query and the existing API. Run Playwright against the production build with isolated API fixtures; no live database, provider or shared tip writes. Use native layout and existing components.

Tech stack: React 19, TypeScript, Vite, Playwright Chromium, GitHub Actions.

Scope approved in chat: mobile polish, error handling and automated browser tests. No new accounts, favorites, deployment or scheduler changes.

## 1. Reproduce and protect behavior
- Add a Playwright development dependency, configuration and deterministic fixtures.
- Cover saving/retrying tips, rejected submissions, the T−5 cutoff and distant fixtures.
- Cover archive/history failures, competition switching and persistent team comparisons.
- Check each route at 375, 390, 768 and 1440 pixels for horizontal overflow.
- Run the cases against the current build and confirm concrete failures before fixing them.

## 2. Fix observed problems
- Repair cutoff timing and lock controls after an authoritative rejection.
- Preserve inputs and distinguish failed requests from missing data.
- Fix the overflowing elements at their source; retain readable touch controls.
- Re-run the affected tests after each change and inspect light/dark views visually.

## 3. Verify and wire CI
- Add browser tests to the existing workflow with trace/screenshot artifacts on failure.
- Run backend tests, existing frontend unit tests, typecheck, lint, production build and browser regressions.
- Document browser-test commands and provide a local preview of the tested changes.
- Check that unrelated files in the original checkout remain unchanged.

## Result

Completed: mobile input and touch improvements; timer overflow and authoritative cutoff handling; archive/history retry states; storage fallback; unavailable refresh preservation; competition-scoped refresh results. Added production-build browser tests and CI diagnostics. Compatible dependency patches removed the four reported high-severity vulnerabilities.

Verified locally: 373 backend tests; 103 frontend unit tests; 61 Chromium browser tests passing with three device-inapplicable cases skipped; strict application/browser-test typecheck; production build; lint with no errors and the five existing Fast Refresh warnings; npm audit with zero known vulnerabilities. Both themes inspected visually. The original checkout's 12 unrelated files retained their original hashes.

Browser tests use API fixtures and do not establish live deployment, scheduler or database integration status. Local preview uses disposable test data. Changes remain on codex/ui-quality-pass for the user's test.
