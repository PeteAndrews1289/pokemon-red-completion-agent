# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Target repair succeeded; refit stopped at retention gate

The [Astra review](docs/reviews/red-trainer-astra-focused-review-2026-09-17.md)
identified two target defects. The local source now averages each executed
action's returns before softmax and before grouping attacks versus switches.
Repeated observable inputs aggregate raw mean returns before transformation.
The fit receipt versions this new target, and diagnostics measure the selected
control plus its chosen move or reserve. Mathematical regressions and 24
focused tests passed. Across all 80 distinct TRAIN head inputs, the corrected
target has zero mean-return ranking mismatches.

One [authenticated 52-context TRAIN refit](docs/evidence/red-trainer-mean-return-refit-2026-09-17.json)
used 2400 epochs and no gameplay. Its model SHA-256 is
`be3a2a3aed8d4fe80ce6a9b084de667cb0fee65afe21f59f9ba6a38382038b26`.
All-52 attack regret improved to 0.0543 (gate <=0.0648), and complete
control-plus-child action regret was 0.1111 (gate <=0.1609). But on the
original 44 TRAIN cases attack regret was 0.0571, above the predeclared
0.0554 ceiling by 0.0017. The model is retained as a failed TRAIN result,
not promoted. No four-scenario HP pilot or new-origin natural comparison ran.

Next bounded objective: Sol High, Fast off. Prospectively declare and run one
ROM-free continuation from the compatible older attack weights under the
corrected targets, or an equivalently narrow optimization test, using the
same three gates. The older weights already outperformed the failed 52-case
fit; this is an optimization question, not evidence for a larger model.
Only after all gates pass should the [four-case terminal HP pilot](docs/reviews/red-trainer-astra-focused-review-2026-09-17.md)
run. If retention fails again, stop and redesign the corpus/optimizer.

The earlier correlated League DEVELOPMENT comparison remains failed and
consumed; its records cannot enter fitting. The older frozen control retains
authority. Model137 stays 137 examples / 92 successes / 58 economy-qualified,
Red 96/124 and fresh acceptance 0/5. Gameplay is stopped. No ROM hack,
Crystal work, full game or GitHub push occurred. Pete decides publication.
