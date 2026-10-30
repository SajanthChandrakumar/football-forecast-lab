# PL/UCL: schnelle Übersicht und gezielte Spieldetails

Approved in this conversation on 2026-10-28 (Q1–Q8, final user: "y los").

- PL/UCL only; existing WC calculation/UI data contracts and frozen historical predictions remain unchanged.
- Immediately show the newest successfully stored provider state; real source timestamps and stale warnings remain. No provider fetch on page opening, no new subscriptions, dependencies, or recurring costs.
- Warm-server target: overview and individual-game core data within two seconds, measured on production repeatedly. This is an acceptance target, not a guarantee. Hosting wake latency is measured separately. Live visual browser control remains deferred; distinguish HTTP evidence from fixture browser tests.
- Open visible pages adopt stored updates within 60 seconds; own saved tips appear immediately and are always validated against current server deadline/archive state.
- Core game content loads first; team form/lineups/model detail load independently, with loading/error/retry states rather than false missing-data messages.
- A compact persisted overview is prepared from cached fixtures/predictions and reconciled frozen archive entries. Per-game records enable bounded reads. Publication must prevent old parallel builders replacing newer data, preserve last good data on failure, and avoid unlimited obsolete generations. All actual successful update seams (fixtures/odds/predictions/results/shared tips/manual maintenance) must reach the read views.
- Default full matches endpoint remains compatible. Derived snapshots must never invent rating/source/coverage/computation readiness. Check real cached matrices during preparation, retain the resulting readiness/model/input identity in the small view, and age input freshness on reads.
- Game/provider/archive IDs must be resolved explicitly; names alone are not proof. Archive aliases, cross-competition isolation, failed saves and T−5 are covered by tests.
- Preserve existing dirty source checkout (now /Users/Sajanth/Desktop/Git/wm2026_predictor) and the unrelated untracked docs/pl-ucl-abnahme-2026-10-25.md in the isolated checkout.
