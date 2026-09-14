# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 14, 2026.

## Current boundary: the mixed-acquisition gate failed safely

The full-151 local Red inventory now feeds a strict goal-proposal boundary. It proposes only
locally missing targets whose pinned acquisition method matches an exact profile-bound executable,
requires physical precursors for evolution, and refuses menus with fewer than two acquisition
families. Shared registration and physical possession never grant local completion credit.

One authenticated historical train state outside the Model106–121 checkpoint lineage was inspected
with zero input. It had 18 local registrations, missing Mansion wild targets 77/88/110, a physical
species 11 precursor and missing evolution target 12. Its live goal menu exposed acquisition,
restoration and exploration, so the full-Pokédex proposal contained only the wild family. The
required two-family gate failed with zero controller actions, frames, model queries or claims.

The incompatibility is structural: current wild capture is executable only at its encounter source,
while native boxed evolution is executable only from a supported Pokémon Center boundary. Missing
targets and resources alone do not make both executors simultaneously available.

## Learning and completion status

Model121 remains at 121 examples, 83 successes and 86 local registrations. This session produced no
outcome, example, fit, authority promotion, independent evaluation or transfer result. It is the
second consecutive session without measured learning output, so the North Star anti-drift alarm is
active. Gameplay is stopped.

Pete requires a fresh start-to-finish non-deterministic model-directed Red run with concurrent
Champion/Hall-of-Fame evidence and all 151 local registrations before any ROM hack. Version, trade,
supporting-save and event dependencies must be resolved legitimately. After full Red: compatible
unfamiliar Red modification, Crystal, then at least Emerald.

## Exact next task

Settle one reusable shared-departure collection contract. A Pokémon Center state should be able to
offer both a travel-capable wild capture and native boxed level evolution before the model chooses;
travel and target identity remain private to each executor. Do not inspect another historical menu,
add another inventory wrapper, or write a route-specific policy feature.

Run only the action-free gate first. Gameplay is permitted only if one authenticated state exposes
at least two independently verified acquisition families from the full-151 inventory and the bounded
run can produce a measured outcome. Otherwise stop again.

## Verification and reviewers

Implementation commit `17eab16f` passed 21 focused tests, Ruff, mypy and collection-registry checks.
The full suite had 11,619 passes and the known unrelated local Mac PyBoy metadata-digest failure.
All 150 documentation/focus tests passed. These checks are not model progress.

Gemini 3.8 Flash High supplied the accepted inventory-to-binding and fail-closed invariant review.
Claude Sonnet 4.6 completed read-only through `agy` and agreed with the gameplay stop; two findings
that contradicted profile uniqueness and the pinned Mansion catalog were rejected. The standalone
Claude CLI binary is present at version 2.1.197 but still requests login. Reviewer quotas are not
available from `agy`.

Next-session recommendation: **GPT-6 Astra / High / Fast off** for the authority and executor-boundary
redesign. Return to Sol High after the shared-departure contract is settled.

[Session](docs/work-sessions/2026-09-14-full-pokedex-goal-proposal-falsification.md) ·
[Evidence](docs/evidence/red-full-pokedex-goal-proposal-falsification-2026-09-14.json) ·
[Prior refocus](docs/work-sessions/2026-09-14-model121-full-pokedex-refocus.md)
