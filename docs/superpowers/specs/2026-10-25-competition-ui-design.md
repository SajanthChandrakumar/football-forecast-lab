# Appweite UI: gemeinsamer Aufbau und drei Themes

Approved in the design interview on 2026-10-25. All WM, UCL and PL views are in scope for presentation changes. Calculations, data sources, historical forecasts, saved tips and APIs remain unchanged.

## User decisions
- Shared application/navigation with recognizable competition themes.
- WM: deep green/gold. UCL: midnight blue/silver. PL: purple/turquoise. All support light/dark.
- Calm, high-quality sporting appearance: clear typography, restrained surfaces and animation.
- Match list is the entry point, with compact rows and details on demand.
- Directly visible WM/UCL/PL competition controls in the header.
- Phone and desktop equally important.
- All existing functions remain accessible. Missing/stale data stays apparent.
- Live visual verification remains deferred at the user's request; do not claim it occurred.

## Behavior
Shared header and primary navigation (Spiele, Gemeinsame Tipps, Tabellen) remain consistent. Additional analyses stay in the existing menu. Competition and appearance preferences remain stored using the existing keys. Theme/competition changes must not produce extra provider refreshes or mix competition data.

Fixture rows show date/time or status, actual crests/fallbacks, teams, actual result or explicitly labelled model tip, and concise data status. Outcome probabilities, form and tip editing are progressively disclosed. Mobile stacks team names while keeping time/result readable. Existing tip workflow, T-5 lock, save feedback, keyboard access and save-and-next are preserved.

Every page uses the shared hierarchy: one title/description, essential summary first, optional analysis in existing tabs/disclosures. Form history remains unchanged in meaning. Tables align numeric values and retain labels; wide tables scroll within their own container. Charts show clear axes/units/legends and stable semantic series colors. Warning/error/outcome colors retain meaning independently of competition accent.

## Acceptance
Frontend unit tests, app/E2E typechecks, lint and build; regressions for existing backend calculations/data; isolated browser tests for three competitions times two appearances at 375, 390, 768, 1024 and 1440 widths. Cover long names, missing crests, stale/missing inputs, switching/reload, focus/keyboard, save/reject/T-5 and no horizontal page overflow. Screenshots are local fixture-based evidence, not live inspection.
