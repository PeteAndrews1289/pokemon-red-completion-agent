# Agatha forward returns: keep the controller failure in view

The [batch receipt](../evidence/red-agatha-forward-batch-stop-2026-09-09.json)
records four declared training resets from the actual learner-controlled Bruno
successor. Three were attempted before the first-exception stop closed collection.
The fourth was cancelled without a claim or controller input; it is not an outcome.

| Attempt | Actual sequence | Current Agatha goal | Actions | Frames | Field items |
| --- | --- | --- | ---: | ---: | ---: |
| 01 | Sampled recovery, forced story | Reached | 309 | 28,609 | 1 |
| 02 | Sampled recovery, forced story | Reached | 309 | 28,609 | 1 |
| 03 | Sampled story | Controller stopped | 230 | 21,672 | 0 |

There were three genuine first choices and two forced singleton continuations,
not five learned choices. The successes retained all30 specimens. The failed
state was reopened with zero input/frames and all six party members still alive.
The entry-type screen rejected move101; the subsequent safe-checkpoint rejection
correctly refused to bless a mid-battle save. No game loss or blackout is inferred.

The forward recorder had already retained a known `STOPPED` return: goal false,
cost0.0024817777777777776,230actions/21672frames. That is failure to reach the goal
under this frozen controller, not proof that an ideal player could not win or that
healing is universally preferable. Its physical artifact remains failed.

## Implemented boundary

Native and ordinary forward fitting loaders still open complete episodes only.
Private shared validators now let a separate quarantine diagnostic authenticate
the actual sampler, first-choice join, goal observation, complete execution prefix,
gross resource cost and exact released failure capture. The diagnostic itself is
not a fit-compatible outcome and grants no replay or checkpoint authority.

A separately named controller-return path admits only a known finite `STOPPED`
with observed-goal false under an explicit frozen-controller return contract.
A pinned whole-batch declaration accounts for every attempted and cancelled ID;
an existing complete, failed or partial artifact cannot be hidden as cancelled.
It is fitted through a distinct shadow artifact schema/kind, which the existing
live-probe loader does not accept. Unknown/interrupted returns never become zero.

## Review and validation

The internal reviewer approved the separate finite-controller interpretation and
caught two useful issues: excluded training rows were too loosely labelled as
singleton choices, and an executed episode could be relabelled as cancelled.
Both were corrected with discriminating tests. This is shared-reader extraction,
not a replacement artifact system or a relaxation of ordinary native admission.

The first extraction passed113 focused tests. Expanded forward/native/probe
coverage passed581 tests before the final cancelled-artifact regression was added;
final expanded publication check passed584 tests, with452-source mypy and full
repository lint also passing. Published669cefa3
separately passed9,645 full local tests and hostedCI34331515711. Do not attribute
that earlier full-suite result to this later executable source.

## Next decision and limits

The immediate next step is one all-three-return Agatha shadow fit, ridge1/cap10,
with no success-only subset or gameplay replay. No Agatha fit had occurred when
this collection receipt was written. A later fit gets its own receipt.

The actual Bruno learner-controlled victory remains valid and separate. These
Agatha resets share one already-observed training lineage. No independent
advantage, calibrated probability, cross-goal transfer, full-player promotion,
or Phase4 completion is established. The current Champion failure is untouched.
The long-term living-Pokedex and cross-game mission and stable phase exit remain.
