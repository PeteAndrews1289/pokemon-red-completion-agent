# Repeatable battle development loop

This loop is the fast path for improving the title-neutral move ranker. It is intentionally separate
from sealed Red evaluation and may be repeated on development captures.

## Data flow

1. `train_repeatable_battle_model.py` initializes the MLP from randomized semantic states and the
   disclosed Red mechanics oracle. These labels are simulated and grant no gameplay authority.
2. `collect_repeatable_battle_outcomes.py` authenticates each Red capture, restores it once per
   usable move, executes the real controller turn, and writes semantic features plus measured
   outcomes. Bad captures are quarantined individually in a sibling failure report.
3. `fit_repeatable_battle_outcomes.py` adapts the MLP output layer on train roots only and compares
   the base and update on development roots.
4. `evaluate_repeatable_battle_outcomes.py` compares models on one or more additional development
   datasets without fitting.
5. `run_repeatable_battle_policy.py` lets the model select and execute one move on each development
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
  --capture-dir "$RED_DEVELOPMENT_CAPTURES" \
  --output "$BATTLE_WORK/dataset.jsonl"

python scripts/fit_repeatable_battle_outcomes.py \
  --base-model "$BATTLE_WORK/model-base.json" \
  --dataset "$BATTLE_WORK/dataset.jsonl" \
  --out-model "$BATTLE_WORK/model-authentic.json" \
  --out-report "$BATTLE_WORK/authentic-fit-report.json"

python scripts/run_repeatable_battle_policy.py \
  --rom "$POKEMON_RED_ROM" \
  --model "$BATTLE_WORK/model-authentic.json" \
  --capture-dir "$RED_FRESH_DEVELOPMENT_CAPTURES" \
  --output "$BATTLE_WORK/policy-execution.json"
```

All variables above point outside the repository. Never store private cartridge or capture paths in
the working tree.

## Interpretation

- Synthetic accuracy measures whether the representation can learn the disclosed mechanics prior.
- Authentic development accuracy and selected utility measure cartridge-grounded move preference.
- A model-selected execution proves bounded controller authority for that move decision.
- None of these proves multi-turn battle competence, switch/item/capture competence, full-game
  autonomy, living-Pokédex completion, or cross-title transfer.

The next scale gate should vary opponent, HP, PP, status, matchup and move-set pressure across
disjoint upstream roots. If model advantage does not persist under that variation, redesign the
scenario distribution before adding full-run cost.
