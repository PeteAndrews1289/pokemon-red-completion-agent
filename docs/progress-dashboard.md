# Pokémon Learning Observatory

> **Model-first pivot:** the first Red shadow dashboard stopped safely after 1,250 team-training
> battles. It retained the failed state and correction count, but exposed two missing diagnostics:
> the exact exception message was not retained, and live heal/party/efficiency data was too sparse
> to explain the long training block. The next dashboard iteration follows
> [model-first-roadmap.md](model-first-roadmap.md): scenario throughput, unseen success,
> interventions, collisions/path overhead, battle outcomes, experience per frame, battles per heal,
> party rotations, collection dependencies, and transfer replace whole-route percentage as the
> primary progress view. Do not start another full run merely to populate this dashboard.
> Future private failure records preserve exact path-free text and replace path tokens inside
> otherwise useful messages instead of discarding the entire diagnostic.

The dashboard is the human view of a run. It combines the live emulator screen with the evidence
needed to understand what the agent is doing and how far the experiment has progressed.

The v1 bounded curve stopped before fitting when one selected development turn was mechanically
suppressed; no model or evaluation exists for that attempt. V2 completed from four train captures
and four fresh development captures. The dashboard now shows all 1/2/4 points, exact correct/total
results, fit loss, paired prior wins/update wins/ties, outcome diversity, the shared development
denominator, and zero authority. Its most important result is the ceiling warning: the prior and
all updates were 4/4, three development contexts were completely flat, and 26/32 branches were
one-turn knockouts. It must not turn a descriptive eight-context curve into the 200-battle
promotion gate.

The first party-development result has its own completed-experiment failure view. It shows both
same-trainee trials, exact target-XP rates, battles, encounter steps, controller actions, frames,
rotations and Center-route accounting. It makes the key tradeoff visible: the higher encounter band
finished 11.4% faster but reported 42 aggregate Center calls against a configured 40-trip policy.
Because phase accounting was absent, the page labels the target rejected, with no learner example,
fitted party model or authority.

The default party page now shows the corrected V2 result. Both fresh clones evolved safely and the
phase counters close exactly. It reports the accepted lower-band target, 10/50 versus 40/50
budgeted Center calls, one cleanup each and the higher band's 39 venue transitions. The page also
states the limit: this is one source-bound example under the current executor, with no fitted party
model, generalization result or authority.

The subsequent traversal repair does not rewrite that completed page. Its current status is
source/test qualified and live pending: exact commit `51f0912` passed CI, but no repaired cartridge
trial has run. A future independent live party outcome will add movement attempts, successful
steps, blocked attempts, excluded-transition skips and no-progress cycles to the public summary.
Until then, the dashboard must continue to show the V2 execution under its original source and must
not imply that the 39 transitions have already disappeared in game.

## What it shows

- the rendered game frame, run state, current stage, progress, actions, frames and emulation speed;
- the model's current goal choice, confidence, teacher-query count and fallback count;
- registered, living and level-cap collection totals, capture supplies and free storage;
- party levels, health and status plus the currently available goal pressures;
- either the prospective Crystal V3 27-adaptation/54-sealed boundary or the Red
  fitted/gated/live-run counters;
- each Red learned head's role, authority, exact correct/total pair, independent validation units,
  paired comparison, candidate-count subset and model fingerprint;
- live Red teacher agreement over classified comparisons, execution over all decisions, saved
  corrections, low-confidence, unsupported, non-move, failed and unclassified decisions, plus
  exact team-development agreement; and
- recent identity-safe evidence events.

The initial Crystal preview intentionally shows zero model and experiment progress. It authenticates
the 1.1 cartridge and proves the display path without opening a context, asking the teacher, making
a prediction, sending controller input or saving cartridge state.

## Show the latest Red outcome-learning curve

The current dashboard is a completed experiment view, not another full run. It shows eight
authenticated captures, 32 selected-turn outcomes, all three from-prior fits, the frozen-prior
comparison, outcome-diversity diagnostics, zero protected-access counters and the held-authority
state. With only the public receipt it shows a neutral screen; optionally supply any authenticated
v2 private capture to show its exact in-game battle frame. Loading that frame sends no controller
input and saves nothing.

```sh
source .venv/bin/activate
python scripts/run_battle_outcome_dashboard.py \
  --rom "$POKEMON_RED_ROM" \
  --capture-state /private/path/to/v2-development.state \
  --capture-manifest /private/path/to/v2-development.manifest.json
```

The capture is accepted only when its manifest digest appears in the tracked v2 result. Use
`--no-browser` if the existing browser tab already points at `http://127.0.0.1:8765/`. The page is
view-only and remains open until `Ctrl-C`. Learned-stack rows wrap at ordinary desktop widths and
label all three candidates and frozen-prior scores explicitly so a ceiling cannot be mistaken for
improvement.

## Show the party-development outcome

The party view uses only the tracked, path-free result by default. Optionally pass the exact
authenticated source state and private Red cartridge to display the starting Cinnabar frame. The
state and ROM must match the published SHA-256 bindings; loading the frame sends no controller
input and saves nothing.

```sh
source .venv/bin/activate
python scripts/run_party_outcome_dashboard.py \
  --rom "$POKEMON_RED_ROM" \
  --state /private/path/to/authenticated-evolution-training.state
```

Use `--no-browser` when the existing browser tab already points at
`http://127.0.0.1:8765/`. The headline result is 108 battles / 1,050,047 frames in the lower band
versus 69 / 1,158,371 in the higher band, with both trainees evolving at level 26 and zero faints.
It displays one accepted learner target plus the 39-transition caveat—not a fitted model, a
generalization result or a new run.

## Historical Red full-run harness — not currently authorized

The command below produced the failed 85-million-frame shadow evidence. It is retained for
reproducibility, but `NORTH_STAR.md` prohibits another full run until the bounded scenario gates
pass. Do not launch it merely to populate the dashboard:

```sh
source .venv/bin/activate
python scripts/run_red_training_dashboard.py \
  --rom "$POKEMON_RED_ROM" \
  --battle-model /private/path/to/battle-model/model.jsonl \
  --training-candidate-model /private/path/to/team-development-model.json \
  --training-candidate-file-sha256 53104c999f0289f8a1dcef9816c34e6963963a047bf710a05544e383c328fdd3 \
  --corrections-root /private/path/to/initialized-artifact-root
```

The page opens at `http://127.0.0.1:8765/` and stays available after the run until `Ctrl-C`.
`--no-browser` reuses a window already showing that address; `--hold-seconds 300` closes five
minutes after the terminal result.

The historical run was deliberately teacher-supervised. A confident battle proposal executed only when the
teacher agrees; disagreement or low confidence executes the teacher's choice and saves a private
correction. The team-development ranker is measured but has no execution authority. The fitted
goal manager and destination ranker appear in the learned-stack table but remain offline in this
fixed full-game route. A green Hall-of-Fame result therefore proves fresh-model compatibility and
correction coverage—not an autonomous end-to-end player. The frozen plan is
[`configs/red-player-training-v1.json`](../configs/red-player-training-v1.json).

## Start the authenticated preview

From the repository folder, activate the project environment, provide the path to a private,
lawfully obtained international Crystal 1.1 cartridge, and start the preview:

```sh
source .venv/bin/activate
export POKEMON_CRYSTAL_ROM="/Users/user/path/to/private-crystal-1.1.gbc"
python scripts/run_crystal_dashboard.py
```

The browser opens automatically. Stop the preview with `Ctrl-C`. Use `--no-browser` when another
browser window already has the displayed local address, or `--duration-seconds 60` for a bounded
one-minute preview.

After an exact source commit is pushed and its GitHub checks pass, the official banked-memory
qualification can show the real setup and its semantic result in the same view:

```sh
COMMIT=$(git rev-parse HEAD)
python scripts/qualify_crystal_banked_observation.py \
  --expected-source-commit "$COMMIT" \
  --dashboard \
  --hold-seconds 30
```

This is an adapter test, not a lesson. It starts from clean power, performs a bounded new-game
setup and real in-game save, then compares two complete semantic reads. All zero-shot, adaptation,
sealed-test, prediction and teacher counters remain zero.

The first official run passed in 46 inputs / 33,276 frames after exact-commit CI. Its identity-safe
result is preserved in the
[Crystal banked-observation qualification receipt](evidence/crystal-banked-observation-qualification-2026-08-14.json).

Once the starting vertical-slice source is published and green, its two real goal bindings use the
same view:

```sh
COMMIT=$(git rev-parse HEAD)
python scripts/qualify_crystal_starting_vertical_slice.py \
  --expected-source-commit "$COMMIT" \
  --dashboard \
  --hold-seconds 30
```

This highlights executable story/exploration pressures while the model remains **not executed**.
It is a binding qualification, not a zero-shot prediction or teaching example.

The first exact-commit run passed with 75 total controller inputs. Its two binding results and
all-zero experiment counters are preserved in the
[starting vertical-slice qualification receipt](evidence/crystal-starting-vertical-slice-qualification-2026-08-14.json).

## Safety boundary

The dashboard binds only to this computer at `127.0.0.1`. Its server supports view-only GET
requests and has no controller, teacher, prediction or save endpoint. Runtime code publishes a
validated, identity-safe snapshot to the display; the display never feeds data or instructions
back into the agent. Private paths, raw memory addresses and binding identities are excluded from
the status document.

The next active display target is the single-process battle scenario adapter. It should show
bounded episode throughput, learner-update eligibility, untouched-lineage outcomes, interventions
and exact failures only after the real snapshot-backed adapter exists. Navigation and
party-development views follow only after that first loop closes; synthetic contract tests must
not move a training counter.

The same observer boundary is intended for live qualification, demonstration collection, model
fitting, zero-shot evaluation and later causal runs. A counter advances only when the corresponding
authenticated workflow publishes real progress. Crystal V3 remains at zero and private-context
access remains false until the published plan passes both external reviews.
