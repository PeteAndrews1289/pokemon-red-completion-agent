# Finish native verification after a runtime-owned prompt failure

The exact candidate passed independent TRAIN verification: 38 checkpoints,
35 retained checks, 591 unchanged status choices and 40.2% full-control improvement.
The first comparison is closed incomplete: 25 completed episodes, then the parent
reference actor's voluntary switch failed. No candidate update or evaluation fit.

The retained endpoint shows the selected battler entered correctly, an opponent
fainted, the enemy advanced, and the switch primitive never returned to MAIN.
Its settlement loop recognizes MAIN/faint/end but not a new trainer replacement
prompt. It can therefore press buttons belonging to the next model choice.
The interrupted endpoint is not continuation-qualified; do not resume or replay it.

Mission check: repair the generic switch-to-next-decision boundary; the model
still owns all switch/prompt choices; use isolated TRAIN mechanics probes followed
by an untouched comparison; first falsifier is a residual-damage knockout during
a voluntary switch; same 02:18 UTC cutoff and per-episode bounds; stop on unowned
actions, failed mechanics, exhausted bounds or failed unchanged comparison gates.

Add an explicit prompt-outcome opt-in to voluntary switching. Yield only at a
visible trainer prompt with the requested battler active; all other callers fail
closed without answering it. The trainer episode then requests a new learned
prompt decision. Validate synthetic gates and bounded TRAIN-only burn/poison
switch probes. No model fitting, deployment or campaign advancement.

The three opened comparison teams are consumed, including their successful arms.
Do not cherry-pick/replay them or count the interrupted episode as a loss or win.
For a separately frozen repaired-runtime screen keep the 21 entirely unopened
teams and replace the three consumed teams input-only, preserving their family,
size and level positions. Exclude prior TRAIN and comparison species pairs and
teams; use fixed seed 2026092501 and at most 12 input-only allocations/300 seconds.
No outcome-based allocation. Freeze all 24 setups before play. If replacements
cannot be built under those rules, report the limitation rather than weaken it.

The exact three model hashes and original 24-team/three-timing/three-actor gates
remain: noninferior wins and common-win costs, improved risk, zero invalid actions
or teacher interventions. Save every outcome, audit logs and retained endpoints,
and disclose both the consumed incomplete screen and repaired-runtime screen.
This is a runtime validation deviation, not another fit or a replayed evaluation.
