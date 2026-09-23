# Balanced status applicability experiment

## Prospective mission check

1. Capability: choose status/recovery versus damage from observable conditions,
   including the changed situation after a status move has already been used.
2. Learned authority: a learned status selector competes with frozen K's best
   legal damaging move. No hand-coded remedy, ineffective-move mask or teacher
   substitution. K's damage, control and switching components remain unchanged.
3. Transfer test: freeze different generated species/move/level configurations
   before collection; fit only the new TRAIN examples. These share existing TRAIN
   ancestry and cannot qualify independent natural transfer or live promotion.
4. Cheapest falsifier: the frozen selector still repeats already-applied effects,
   wastes full-HP recovery or loses more withheld battles than K.
5. Time box: one session, at most two hours including implementation and audit;
   one fit, no hyperparameter search or heldout-informed second fit.
6. Stop condition: reject on invalid execution, missing provenance, regression,
   no useful learned status choices, or persistent ineffective repetitions.
   Retain all losses. Never rerun either prior packet's holdouts.

## Frozen design, before collection

Use eight existing effect families: sleep, paralysis, poison, confusion,
accuracy reduction, Disable, Recover and Rest. For each, construct two TRAIN
matchups and one new withheld matchup with four prospectively specified
contrasts. Contrasts vary current HP, opponent HP, existing afflictions and
accuracy floors; poison and electric paralysis include type-immune opponents.
Use natural species stats and teachable moves, not outcome-selected matchups.
Retain all cases even if neither action can win.

64 opening TRAIN contexts plus up to 16 native post-action contexts. Compare
the legal status move and K's frozen best damage choice at three timing offsets
for up to eight turns with common K damage continuation. Preserve all 16
preparation episodes, including censored losses. All targets derive from played
returns; no reward or label bonus for choosing a status move.

Fit one small selector on compact candidate-condition interactions, padded with
zero weights for the legacy prefix. This prevents species/type nuisance features
from substituting for applicability. Version the schema; v1 models remain intact.
Mechanics facts are inputs, not action restrictions or hand-assigned preferences.
Freeze candidate before 32 new paired full-battle evaluations (64 episodes).
Maximum 560 gameplay episodes, 80 decisions/120,000 frames/5,000 controller
actions/45 seconds each. Overall runner deadline 60 minutes. No campaign access.

Success requires no win regression, no invalid actions, at least one won case
with status use and paired return improvement above 0.05, and no already-afflicted/confused or
full-HP recovery choices in eligible observed situations. A pass opens a separate
disjoint-origin multi-party qualification, not live integration. A failure closes
this packet without refitting or consuming more heldout configurations.

Logs retain recipes, starting conditions, ancestry, source/model identities,
per-choice observations/probabilities/actions/latency, native post-action results,
frame/controller budgets, event hashes, exact terminals and all failures.

Mechanics references: pinned [effect handlers](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/engine/battle/effects.asm),
[paralysis](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/engine/battle/move_effects/paralyze.asm)
and [healing](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/engine/battle/move_effects/heal.asm).
Condition features are partial, not a universal move-success oracle. In particular,
Substitute, recharge exceptions, Disable's enemy duration and later-generation
rules are not new observed inputs. A no-concern flag does not guarantee success.

## Result — experiment completed, candidate rejected

Source d8782e4d; candidate 7df8772dab63. All 64 starting and 16 native post-action
contexts completed; no censored preparation. 480 comparative branches, 16
preparations and 64 paired evaluation episodes: **560 episodes**, 1,693 recorded
decisions (496 prescribed first choices; 1,197 learned continuation/evaluation
choices). Runtime was 158 seconds, excluding implementation and audit. This is
not 560 independent battles: configurations and branches share TRAIN ancestry.

One fit reduced TRAIN regret from 0.413504 to 0.152093. On 32 new withheld
configurations the candidate won **13/32 versus K's 12/32**. One confusion case
changed a loss into a win. No other paired win/loss changed. This small, correlated
screen does not establish statistically reliable superiority or natural transfer.

The candidate nevertheless failed the frozen behavior gate:

- 40 major-status selections while the opponent was already afflicted;
- four confusion selections while the opponent was already confused;
- 196 decisions versus K's 76, including long losing Recover loops;
- no concerning poison/paralysis/full-HP recovery selections in this cohort,
  but avoiding those choices is not proof of useful mastery of their effects.

The 44 flags describe the observed situation at selection time, not 44 verified
native failure messages. Turn ordering and special mechanics can matter. The
legacy `move_suppressed_or_failed` metric instead tracks `move_executed == False`;
it is not an effect-success counter and must not substitute for these diagnostics.

## What the label audit actually establishes

Of 24 TRAIN contexts flagged for applicability concerns, ten have an absolute
status-versus-damage return gap no larger than 0.05; three favor status by more
than 0.05. For example, sleep-1-1 starts with an already-paralyzed opponent, yet
its measured short branch returns favor the ineffective sleep opening by about
2.30. Those are retained outcomes, not labels to rewrite into preferred answers.

The current objective credits one prescribed action followed by frozen K damage
continuation. Small wasted-turn costs plus stochastic/horizon effects can give
nearly tied or misleading targets; soft labels then supply little pressure against
repetition. Actual closed-loop behavior differs from that assumed continuation.
This supports a credit-assignment/continuation mismatch, but does not prove it is
the sole cause; limited matchup coverage and approximate features also remain.

No second fit, heldout replay, changed acceptance rule or retrospective label edit.
The candidate and all losses remain available as evidence; live K is unchanged.

## Verification and protected state

The read-only audit verified all 9,092 event records, 560 terminal hashes,
480 branch label/feature reconciliations and all 196 candidate move predictions.
It confirms excluded heldout capture IDs, zero legacy-prefix fit weights and exact
K damage/control/switch preservation. Zero invalid actions or actor memory writes.
804 targeted tests passed, as did targeted type checks and Ruff. The prior
whole-package type-check debt is not repaired or represented as a full pass.

Earned campaign35feb8fa, primary collectionbf603930, Model141 record4ab0e75f and
K e626e343 hashes are unchanged. No registrations, story progress, main-save
actions, external model use or GitHub publication. Gameplay is stopped.
[Path-free evidence](../evidence/red-balanced-status-learning-2026-09-21.json).

## Next bounded work

Do not produce another larger random opening batch. Design one closed-loop TRAIN
packet that samples states visited by a frozen learner, compares its actual
continuations, and accounts for observed ineffective turns, elapsed turns and
finite PP alongside terminal wins/HP. Any outcome definition change must be
versioned prospectively; preserve old rewards and do not add a status-use bonus.
Consider observed previous-turn effects/incoming damage if they resolve concrete
state aliasing; do not add hidden opponent information or a repeated-move ban.

First demonstrate that the revised TRAIN targets distinguish stopping a repeated
effect from repeating it before spending another fit or withheld inventory.
Then one fit and a newly frozen comparison; independent-origin multi-party
qualification and live integration remain later gates. Budget 45–90 minutes for
that target/continuation experiment, not a guarantee of status mastery or Giovanni.
Next-session recommendation: Astra High, Fast off, for the credit-assignment work.
