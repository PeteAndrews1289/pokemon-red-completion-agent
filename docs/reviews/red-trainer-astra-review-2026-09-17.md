# Astra review of the Red battle trainer — September 17, 2026

Reviewed local commit `5127cef4`. [Measured review evidence](../evidence/red-trainer-astra-review-2026-09-17.json).

**Decision: repair the issues below before a large training campaign.** The
emulator factory, isolated teaching interventions, capture provenance, branch
logs and actor/executor separation are worth keeping. The present data cannot
tell us that a larger model is needed. Its attack learner sees only four
distinct candidate matrices.

This review read existing states, authenticated records and model weights. It
made no gameplay actions, fitted no model, and did not push to GitHub. The two
consumed DEVELOPMENT battles remain evaluation evidence only.

## What passed review

- All four fresh source chains passed the current source validator.
- All 140 timing trials and 500 branches in the 28-context corpus passed
  existing execution and return admission when reconstructed from their records.
- Independent boot origins are recorded separately from their synthetic
  training configurations; the historical goal-bank aliases are conservatively
  grouped together.
- The six natural comparison arms have complete logs and retain wins, action
  counts and HP losses. The unfavorable results were not promoted.
- The model chooses semantic actions. State editing remains in the disclosed
  training factory; opponent hidden reserve data is excluded from actor inputs.

Thirty-eight focused existing tests also passed. These do not cover the
reproduced defects below; this was not a full-suite run.

Passing the existing admission checks establishes consistency with the current
code. It does not establish that its reward arithmetic is correct.

## Findings in repair order

### R1 — High: damage attribution breaks when the opponent switches

[Return calculation](../../src/pokemon_red_completion/red_trainer_practice_returns.py), lines 105–111,
compares active-opponent HP before and after the complete decision. It handles
a faint followed by replacement but not a living opponent's switch.

In the retained Fuchsia fixed-control battle, the first move dealt 52/83 HP
damage. The opponent then changed from party position 0 to 1; both the old
starting HP and the new opponent's HP are 83. The selected-turn outcome records
the damage, while the training return records zero. Over the completed battle,
it credits 3.37349 opponent HP-bars instead of 4. The challenger is credited 3.5
instead of 4. Applying the training scorer to these retained logs gives the
challenger 8.70270 and the control 8.68569, despite the challenger's extra turn and
22 HP lost. The difference is inside the current 0.02 tie threshold.

**Repair:** retain damage against a stable opponent instance through turn
settling, switching and faint replacement. Use referee-only roster information
where needed without adding hidden reserve information to the actor's inputs.
Verify same-species switches, different-species switches, replacement after a
KO, and terminal battle exit. A no-healing four-opponent knockout must conserve
four opponent HP-bars regardless of switch order.

No such non-faint switching boundary occurs among the current 500 TRAIN
branches, so this finding alone does not invalidate those fitted targets. The
original natural win/HP/action measurements remain valid.

### R2 — High: context counts hide repetition and conflicting targets

The [curriculum extension](../../scripts/extend_fresh_red_trainer_curriculum.py),
lines 65–75, repeats the same four MAIN configurations on the four fresh starts.
The projected input audit found:

| Head | Recorded examples | Distinct candidate matrices | Training winner hits |
| --- | ---: | ---: | ---: |
| Attack | 16 | 4 | 14/16 |
| Attack/switch control | 20 | 5 | 20/20 |
| Switch target | 28 | 7 | 27/28 |

An always-first-candidate rule also gets 14/16 attack labels. The learned attack
head chooses candidate zero on all 16 training examples. All 28 scenarios have
three-member actor parties and no initial status on either active combatant.
These facts explain why a high training hit rate is weak evidence here.

One identical attack input is labeled best candidate 2, then 0, then 2, then a
tie between 0 and 1 across the four roots. The
[fit adapter](../../src/pokemon_red_completion/red_trainer_practice_fit.py), lines 243–267,
passes hard winner indices into the head; the
[optimizer](../../src/pokemon_red_completion/red_trainer_practice_head.py), lines 174–177,
does not use the measured return magnitudes or their uncertainty. Hidden timing
cannot be recovered from identical actor inputs.

**Repair:** count semantic configurations separately from roots and repeats.
Add paired cases where the preferred decision reverses when one observable
factor changes. Aggregate repeated evidence with its return magnitude and
uncertainty before deciding targets; report contradictory identical inputs,
training regret and simple-control performance. Preserve all failures.
Keep the small network initially and test whether the corrected dataset can
teach the intended contrasts before increasing its size.

### R3 — Medium: the control head uses untrained history during live play

[Training projection](../../src/pokemon_red_completion/red_trainer_practice_fit.py), lines 251–255,
omits history, making it zero in every training example.
[Inference](../../src/pokemon_red_completion/red_trainer_practice_outcome_policy.py), lines 75–81,
supplies changing battle history. All 57 history-related input-weight rows in
the retained control model exactly match their random initialization.

For the same TRAIN observation, attack probability changes from 0.18723 with
empty history to 0.18923 after one attack and 0.19398 after one switch. This is
measured untrained influence; it is not proof that history caused the natural
performance deficits.

**Repair:** make the input contract identical. For an initial stateless segment,
remove these features from both sides. If history is needed, retain it in
training records and train it. Log each head's actual projected input and legal
candidates so fit/inference parity can be checked without reconstruction.

### R4 — Medium: different opponents can share the same history identity

[The tracker](../../src/pokemon_red_completion/battle_control_features.py), line 160,
identifies an opponent by species and level. In the retained Fuchsia battle,
party positions 0 and 1 both have species 048 at level 31. Reconstructing the
tracker leaves `opponent_index=0` and `opponent_turn=1` after the new opponent
appears. The post-switch guard uses that index too.

**Repair:** track an observed send-out instance or explicit replacement event,
including same-species opponents. Do not use a hidden full opposing roster as
a policy feature. Test repeated species, switches back to an earlier foe and
replacement after a faint.

### R5 — Medium: the evaluation cohort cannot yet answer the promotion question

Celadon begins at actor level 44 against level 23; the control defeats both
opponents with one attack each. It already reaches the attack-count floor.
Fuchsia begins at 40 versus 31. Both captures descend from historically
correlated saves, and the two comparisons used different challengers. Neither
challenger voluntarily switched.

**Repair:** freeze one challenger for a prospectively specified cohort with
useful alternatives. Easy fights should require no regression; designated
difficult slices should demonstrate an advantage in the stated outcome.
Include a natural situation where switching can help. Report ancestry and
encounter clusters rather than treating multiple saves as replication.
These two consumed battles remain smoke/negative evidence; do not tune to them.

### R6 — Medium: all-species setup is broader than the learner's move support

The current [move-support rule](../../src/pokemon_red_completion/red_battle_scenario.py),
lines 69–73, accepts 106 of 165 move IDs and excludes 59. Status/recovery/boost
strategies and all-party Struggle are outside this segment. Counter is counted
as supported by that rule, but the
[projector](../../src/pokemon_red_completion/battle_semantics.py), lines 366–367,
raises as soon as an active moveset contains positive-PP Counter, even if a
different move could be selected. Existing tests confirm this deliberate stop.

**Repair:** align generation, preflight and actor support checks, with explicit
exclusion reasons. Declare the initial attack-and-switch scope. Full status,
recovery and Struggle support can be later expansions; complete move support
need not block an honest initial training pilot.

## Concrete next work

1. Repair R1, R3 and R4 and reconcile the Counter support discrepancy in R6.
   Use recorded evidence and ROM-free reproductions first. Verify cartridge
   behavior with new bounded mechanic fixtures only when needed. Estimate:
   one to two implementation sessions; no new large data campaign yet.
2. Freeze a curriculum of distinct paired decisions: physical versus special
   damage, type resistance/immunity, HP/speed tradeoffs, scarce PP, switch versus
   stay, optional versus forced replacement, and different party sizes.
   Count unique inputs and uncertainty, and preserve TRAIN/DEVELOPMENT ancestry.
   Run a small pilot before expanding. Estimate: one implementation/data session.
3. Freeze one challenger and a natural comparison cohort after the pilot
   demonstrates the intended decision reversals and sound scoring. Larger
   training depends on those measured results, not a promised success date.

The immediate goal is trustworthy feedback and useful variation. Further
review should respond to a concrete result or architectural change; no extra
standing review gate is needed.

Model137 stays 137 examples/92 successes/58 economy-qualified outcomes. Red
stays 96/124 registrations; fresh acceptance stays 0/5. Recommended next session:
Sol High, Fast off for the specified repairs and focused verification.
