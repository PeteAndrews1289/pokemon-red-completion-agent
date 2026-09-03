# Repeatable battle development loop

This loop is the fast path for improving the title-neutral move ranker. It is intentionally separate
from sealed Red evaluation and may be repeated on development captures.

## Data flow

1. `train_repeatable_battle_model.py` initializes the MLP from randomized semantic states and the
   disclosed Red mechanics oracle. These labels are simulated and grant no gameplay authority.
2. `collect_repeatable_battle_outcomes.py` authenticates each Red capture, restores it once per
   usable move, executes the real controller turn, and writes semantic features plus measured
   outcomes. It requires clean published source and durably claims each capture before controller
   input. Bad or interrupted captures are quarantined individually and never replayed; untouched
   sibling captures continue on restart.
3. `fit_repeatable_battle_train_only.py` equalizes example counts across train roots and adapts the
   MLP output layer without accepting development or test records.
4. `commit_repeatable_battle_development_predictions.py` opens untouched development captures only
   through the read-only observation boundary and durably records the base model, fitted model and
   fixed heuristic choices. It has no controller call and opens no outcome. Collect development
   outcomes only after this artifact exists.
5. `evaluate_repeatable_battle_outcomes.py` compares models on one or more additional development
   datasets without fitting.
6. `run_repeatable_battle_policy.py` lets the model select and execute one move on each development
   capture with no teacher query.

The JSON artifacts contain no ROM bytes, save-state bytes, controller-input labels, or private
paths. They remain private development artifacts because their semantic state and outcomes derive
from the cartridge.

## Example sequence

```bash
python scripts/train_repeatable_battle_model.py \
  --train-examples 2000 --development-examples 500 --seed 1289 \
  --out-model "$BATTLE_WORK/model-base.json" \
  --out-report "$BATTLE_WORK/pretraining-report.json"

python scripts/collect_repeatable_battle_outcomes.py \
  --rom "$POKEMON_RED_ROM" \
  --capture-dir "$RED_TRAIN_CAPTURES" \
  --output "$BATTLE_WORK/train-dataset.jsonl"

python scripts/fit_repeatable_battle_train_only.py \
  --base-model "$BATTLE_WORK/model-base.json" \
  --dataset "$BATTLE_WORK/train-dataset.jsonl" \
  --out-model "$BATTLE_WORK/model-authentic.json" \
  --out-report "$BATTLE_WORK/train-only-fit-report.json"

python scripts/commit_repeatable_battle_development_predictions.py \
  --rom "$POKEMON_RED_ROM" \
  --base-model "$BATTLE_WORK/model-base.json" \
  --updated-model "$BATTLE_WORK/model-authentic.json" \
  --capture-dir "$RED_FRESH_DEVELOPMENT_CAPTURES" \
  --output "$BATTLE_WORK/development-predictions.json"

python scripts/run_repeatable_battle_policy.py \
  --rom "$POKEMON_RED_ROM" \
  --model "$BATTLE_WORK/model-authentic.json" \
  --capture-dir "$RED_FRESH_DEVELOPMENT_CAPTURES" \
  --output "$BATTLE_WORK/policy-execution.json"
```

All variables above point outside the repository. Never store private cartridge or capture paths in
the working tree. The development-policy example belongs only after its candidate choices have been
committed and the development outcomes have been opened under that commitment.

## Interpretation

- Synthetic accuracy measures whether the representation can learn the disclosed mechanics prior.
- Authentic development accuracy and selected utility measure cartridge-grounded move preference.
- A model-selected execution proves bounded controller authority for that move decision.
- None of these proves multi-turn battle competence, switch/item/capture competence, full-game
  autonomy, living-Pokédex completion, or cross-title transfer.

The next scale gate should vary opponent, HP, PP, status, matchup and move-set pressure across
disjoint upstream roots. If model advantage does not persist under that variation, redesign the
scenario distribution before adding full-run cost.

## First authentic result and V2 direction

The first run produced 41 train examples and fit on 40 lineage-balanced rows. On 21 retained
development outcomes the adapted model improved over its base from 16 to 17 preferred choices, but
the fixed heuristic reached 18. The model therefore remains shadow-only.

The decisive disagreements showed why a second one-shot batch is the wrong response. A charge
move's realized utility changed with cartridge RNG even when the learner could not observe the
future roll. V2 must execute several observation-preserving RNG trajectories for every usable move,
aggregate expected utility per candidate, and train on that distribution. The next comparison must
use newly sourced upstream roots because the first four development roots are now calibration data.
