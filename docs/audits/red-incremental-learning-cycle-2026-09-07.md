# Incremental regional learning cycle — September 7

## Starting point and mission

P completed the affordable-capture milestone3/3: model54 chose Route24, caught Abra10
using one ball, and fitted55 with all54 earlier rows retained. Exact save restoration:
21living/23specimens/26registered,4balls109currency. The prior support episode O added
zero eligible rows. This is a bounded local milestone, not the sustained-Red stage exit.
[Evidence](../evidence/red-affordable-capture-learning-result-2026-09-07.json).

The named next bottleneck is manual per-example orchestration. Reconstruct the prior
explicit training inventory, reuse the existing chooser and fitter, and continue from
the actual new checkpoint/model. Do not build another policy, teacher or trust framework.

## Implementation and limits

`red_player_incremental_fit.py` authenticates the prior corpus, manifests, plans and declared
behavior models. It passes every retained episode and regional choice plus one new outcome
to the existing fitter. That fitter still owns admission, row retention and label checks.
No private-root inventory scan or success-only filtering is introduced.

`run_red_regional_learning_cycle.py` limits a cycle to1–4 single-choice training episodes.
The first real cycle is prospectively limited to two. Each receives the existing30000-action/
3000000-frame cap. After success it fits the actual row and carries both the new model and
checkpoint to the next step. A failed step is retained/fitted then stops; fitting errors
prevent further gameplay. Existing immutable source/episode claims reject replay.
Zero/one remaining source produces a normal stop, never an invented strategic choice.

This is destination-choice orchestration, not a general autonomous game loop. Resource
recovery and new unsupported mechanics still require an explicit next development step.
All continuation states are correlated training data; no independent evaluation or transfer.

## Qualification and next falsifier

82 focused checks passed, including actual saved corpus reconstruction, changed manifests,
wrong behavior records, duplicate outcomes, no-alternative stops and a two-step fake runtime
that verifies checkpoint/model continuity. The existing fitter's separate tests retain
negative outcomes and reject discarded rows.411-module type checking and a broader256-test
protocol/continuation check passed. Lint/docs/focus/public checks precede publication and
the real two-step attempt. This is not a claim that the complete suite ran on this source.

Stop the session at10:50UTC if the bounded cycle is not executable; overall safe closeout
is10:57UTC. Preserve every consumed state. No replay, sealed test or Crystal execution.
