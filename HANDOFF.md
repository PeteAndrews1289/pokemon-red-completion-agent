# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer practice: instrumented, challenger not yet fitted

The [latest evidence](docs/evidence/red-trainer-practice-telemetry-and-varied-train-2026-09-17.json)
records a durable hash-chained battle log. Each model decision retains the
visible observation, legal alternatives, selected action, feature vectors,
available head probabilities, policy/execution time, frames, HP/PP/status
changes, outcome and terminal. A failure retains its completed prefix and
unresolved selected choice; future runtime failures also preserve the existing
bounded diagnostic. The read-only cohort reporter counts upstream roots and
exact repeats separately from run count. A hash-bound three-head runner is
available for future TRAIN or DEVELOPMENT model artifacts; TEST remains closed.

One authentic lab-rival TRAIN source supplied the prior six-on-six state and
two new assisted three-on-three configurations. All variants share **one**
upstream root. The logged six-on-six frozen baseline made 29 decisions, beat
four opponents and lost all six party members. Its 110-event chain verified;
11 selected attacks did not execute, nine PP were spent, and the run took
28,518 emulator frames. This is a retained loss, not a learner gain.

The low-HP configuration compared all four legal attacks and two switches
under the same two-player-turn horizon. Opening move 1 defeated two opponents
without HP loss; switch to slot 2 cost 21 HP with no knockout, and switch to
slot 3 caused one faint. The six branches are alternatives within one TRAIN
example, not six independent cases. The full frozen baseline lost the
three-on-three battle. A later Ground-immunity configuration stopped at
decision 12 when selected-turn PP accounting failed; 11 completed decisions
and the selected unresolved action survive in a 47-event log. The exact run
was not replayed, its cause remains unproven, and it yielded no matched
branches. The new diagnostic-retention code was added after this failure.

No switch-aware challenger was fitted, no natural DEVELOPMENT comparison
ran, and there was no authority promotion. Status moves and items remain
outside the qualified attack/switch trainer. Model137 remains 137 examples,
92 successes and 58 economy-qualified; Red remains 96/124, fresh acceptance
0/5. Gameplay is stopped. No full Red run, ROM hack, Crystal execution or
GitHub push occurred.

Next bounded work: diagnose the PP-boundary failure from retained evidence or
a ROM-free reproducer without replaying it. Continue prospective varied TRAIN
contrasts only if the turn boundary is sound, then fit one switch-aware model
on TRAIN and compare with frozen/fixed controls on untouched natural
DEVELOPMENT roots. Sol High, Fast off for implementation; Astra High only for
the eventual promotion review.

[Prior model-boundary qualification](docs/evidence/red-trainer-practice-model-boundary-2026-09-17.json)
