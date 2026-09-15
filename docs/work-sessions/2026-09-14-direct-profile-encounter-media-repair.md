# Direct-profile encounter-media repair

## Result

The generic failure that consumed the second direct-origin source is repaired without selecting a
source, opening a ROM or private payload, or running an emulator. Direct profile derivation now
admits only catalog `WILD` methods accepted by the existing grass-only resolver, caches the resolved
map for deterministic sorting, and resolves corridor candidates inside its narrow operational
exception boundary.

The resolver itself was not loosened: `wild:Route21:water` remains water and cannot masquerade as a
walking grass corridor. Current-map priority, minimum species number and source-id tie-breaking are
unchanged for valid grass candidates.

Five new ROM-free regressions cover the complete public catalog, Route 21 water/grass coexistence,
real catalog-to-corridor derivation without mocking `_capture_corridor`, clean exhaustion when only
water remains, and defense if an invalid source bypasses the first filter. The named
`nonconsuming_direct_rehearsal` now passes 17 tests rather than 12.

## Mission check

- Reusable capability: any direct full-local origin can enumerate grass-corridor candidates without
  being aborted by a different encounter medium or malformed catalog source.
- Learned authority: unchanged. Model121 remains at 121 examples, 83 successes and 86 local
  registrations; no model query or outcome occurred.
- Transfer test: none. This is source-independent Red maintenance, not later-title evidence.
- Cheapest falsifier: one complete-catalog candidate fails grass resolution, Route 21 water
  preempts grass, unmocked profile derivation fails, or exhaustion leaks a low-level resolver error.
- Time box: one 45–90 minute repair session through review, verification and publication.
- Stop condition: no source selection, claim, ROM/private payload access, emulator, gameplay or
  model fit. End after exact-head publication; third-source authority requires a later re-audit.

This maintenance unblocks only the named direct full-local gate. It does not count as learner
progress and does not authorize a ROM hack, Crystal, a full replay or another source in this
session.

## Verification

- Focused direct-profile tests: 7 passed.
- Named non-consuming rehearsal: 17 passed, 11,704 deselected.
- Related direct-profile, corridor, proposal, training-plan, continuation and registration suite:
  203 passed.
- Repository Ruff: passed.
- Mypy: passed across 499 source files.
- Prospective collection metadata regenerated and checked: registry
  `60bbbf3f...f903534`, source bundle `ebb73c93...dffd6ab4a`.

An exploratory mypy invocation that included one test file also loaded unrelated test modules and
reported their existing test-only typing issues; the required repository source check passed. No
claim is made that all tests are statically typed.

## External review

Gemini 3.8 Flash High returned PASS with no P0/P1/P2 finding. It confirmed the centralized resolver,
unchanged ordering, narrow exception set and distinct value of all five regressions.

The first Claude invocation inherited the wrong CLI project and was interrupted without a review.
A fresh project-bound Claude Opus4.6 Thinking invocation then inspected the exact diff and returned
PASS with no P0/P1/P2 finding. It independently confirmed that water stays excluded, deterministic
priority survives, programming errors are not swallowed and the unmocked test crosses the formerly
missing catalog-to-corridor boundary. Headless output exposed no reviewer quota percentages or
cost.

## Next bounded action

Publish and require exact-head CI. In a later session, re-audit the two consumed-source failures,
remaining unused-source inventory and strength of the 17-test gate. Only if that review justifies
the cost may one distinct source be prospectively selected and exactly claimed for an action-free
two-family preflight. No fallback source or same-session generic repair is allowed.

[Evidence](../evidence/red-direct-profile-encounter-media-repair-2026-09-14.json) ·
[Triggering failure](2026-09-14-direct-full-local-source-v2-preflight-failure.md)
