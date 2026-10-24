# PL/UCL release check — 24 October 2026

Scope: PL/UCL only. Existing green UI retained; the World Cup keeps its legacy model/default calculations and presentation. This document records the verified release candidate; deployed HTTP/data acceptance is recorded separately after rollout.

## Changes

- Verified senior-men ESPN participant namespaces, IDs and explicit competition registry; league, cup and European games share one form implementation. Unverified legacy rows are preserved as raw data and excluded from statistics. Shared form rows show provider crests, both teams, home-away scores, sample size, 5/10 expansion and competition filters. Historical forms stop before kickoff.
- `prediction-club-v2` corrects Dixon-Coles in the fitting and matrix paths. Regulation probabilities, regulation matrix and scoring matrix have explicit time bases. No additional form weighting was introduced. Completed club details use archived predictions; maintenance and club Elo sync do not reconstruct completed forecasts or replace World Cup ratings. Existing historical points remain unchanged.
- UCL simulation uses verified ClubElo pair matrices, 5,000 default runs, bounded background jobs and version/input-specific caches. Missing coefficients/ranks or necessary verified knockout draw data return unavailable. Timeouts can retry. Coefficient vintages must agree. Known regulation/AET/shootout results are respected by the match/tie helpers.
- Club source freshness uses 24 hours and rejects missing/future time evidence. Radar/assistant confidence is constrained by that status. Maintenance/capture jobs are leased, show attempts/successes/errors separately, and do not run on public reads. Provider budgets are unchanged. Long maintenance leases renew with owner fencing.
- Club key entry is masked and held in memory. Request timeouts, partial-save feedback, verified historical edge samples, tab wrapping, chart timestamps and archived-detail navigation guards were tested.

## Evidence before publication

- Final backend full suite: 487 passed in 10.85 seconds; syntax compilation and whitespace checks passed, including club Elo-sync preservation.
- Frontend: 124 unit tests; application/E2E types, lint and production build passed. Lint reports five existing Fast Refresh warnings.
- Full browser suite: 267 passed, 13 deliberate viewport-specific skips across 375/390/768/1024/1440, light/dark and keyboard coverage. Final mobile-form CSS change: 50 focused layout/form tests passed, 5 expected skips. Screenshots were inspected locally.
- Real MongoDB persistence through a local HTTP instance of the production save/auth/archive services was checked using isolated temporary collections: valid save/reload/reconnect, 401 rejection, invalid scores, T−5 and forecast preservation passed for both competitions. Temporary collections were removed; actual shared tips were not changed by this test.
- Read-only rebuild with actual ESPN data: 20 PL teams/190 verified rows; 36 UCL teams/345 verified rows. All teams have data; depth is incomplete for some clubs. Shakhtar and Slavia have three supplied competitive games, Slovan nine; direct schedule checks exposed no additional completed competitive events for them.
- Original checkout source diff remains byte-identical to the pre-task capture. Private verified form backups and protected historical/World Cup fingerprints exist locally under ignored data paths. The repair CLI defaults to dry-run, refuses backup overwrites, verifies hashes, and shares maintenance leases. No archives or World Cup collections are in its repair allow-list.

## Limits that remain explicit

- The user accepted temporarily proceeding without a live visual browser check because local browser control is disabled. Local browser fixtures do not prove deployed-browser behavior.
- Existing free ESPN coverage can omit games, lineups and player statistics. No invented data, badges or substitute ratings fill those gaps. No new paid source was added.
- Current production caches have no complete UEFA coefficient/rank evidence. The UCL title simulation must therefore report unavailable until the necessary inputs exist; fixture-specific helpers passing tests are not a live title forecast.
- In-process maintenance works while the service is awake. The external scheduler configuration is not verified here; free-host sleeping and cold starts remain possible.
- Actual hosted positive editor writes require the separately configured editor key. The isolated database test is not represented as a positive production editor-key check.
- Small verified pre-match samples do not establish superiority, a particular hit rate or guaranteed forecast accuracy.
