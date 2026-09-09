# Forward-goal learning: a separate target, not a renamed Red success

## Result and limits

A new two-output learner predicts **completion within a declared budget** and
**total attempt cost** from the state before a genuine first choice. It learned
to restore resources when necessary and skip optional restoration in a controlled
toy environment: eight supported new test states completed at the toy-optimal
cost; three unsupported states abstained. This is a working fitted actor in a
synthetic task, **not Pokémon gameplay, Red calibration or transfer**.

The [reproducible report](../evidence/synthetic-forward-goal-qualification-2026-09-09.json)
records 128 settled training episodes plus one censored episode, from only four
repeated start states and eight distinct selected inputs. These are not 129
independent environments. Qualification used separate energy values; test values
were not fitted. The actor saw initial energy and available option descriptions,
not future goal outcomes. Tests deliberately poison its predictions and observe
the resulting wrong actions, ruling out a hidden oracle replacing the choice.

Training completion MSE fell from 0.1618652344 to 0.0016251101; cost MSE from
0.0084027778 to about 6.37e-12. These are training diagnostics. Maximum error on
the controlled qualification values was 0.0472282 completion and 0.000005054 cost.
The stated support regions and error/equivalence bounds are explicit toy-task
assumptions, not statistical confidence intervals or live Red defaults.

Red model82 and all82 existing outcomes remain unchanged. The Champion failure
is still the current game state. No new Red forward episode, fit, authority
promotion, story completion, sealed test, Crystal run or full-game replay occurred
in this slice. The native-story submilestone remains 2/3; this is not a whole-phase
percentage and synthetic results do not advance it.

## What changed

- `forward_goal.py`: prospective declaration, first-choice anchor, cumulative
  action/frame/consumable budgets and a single terminal return. Failed attempts
  keep their full cost. Interrupted/unreadable outcomes have no fit label.
- `forward_goal_learning.py`: separate weighted ridge heads with observed
  state-by-candidate interactions. Shared additive state alone would cancel when
  ranking options. First-choice inverse-propensity weights are capped; they do
  not correct changed continuation policies or create independent roots.
- `forward_goal_records.py`: exact model/record round trips and chronological
  replay of recorded evidence. Derived target/cost fields are reconstructed.
- `red_forward_goal.py`: fresh HP/PP/resource observations, current semantic goal
  evidence and boundary consumable spending. Champion success requires concurrent
  Champion event, Hall-of-Fame fact **and mode**, not a historical tracker latch.
- `red_forward_training.py` and the existing bounded runner: optional forward
  stream alongside unchanged immediate outcomes. The current sampler retains
  control; a later honest singleton is not another learned choice. A declared
  stop can end an attempt without falsely declaring completion.
- `red_forward_dataset.py`: existing whole-episode and sampler authentication,
  exact first-row join, separate prospective header, current verifier evidence,
  consumable deltas, and actual execution-prefix checks.
- `fit_red_forward_goal.py`: fit only opted-in episodes into a separate immutable
  private shadow artifact. It neither opens an emulator nor replaces model82.
- `qualify_forward_goal_synthetic.py`: executable inexpensive falsifier.

The Red opt-in currently permits only two macros, an actual sampled story/recovery
choice, cartridge-bound story objectives and single-item field HP/PP restoration.
No buying or within-macro replenishment is admitted: boundary stock changes would
otherwise undercount gross consumption. The continuation binds the existing
stochastic policy, behavior model, executable source and profile. Each episode's
existing plan separately binds its seed; different RNG realizations need not be
different continuation contracts. There is no silent forced-story tail.

## Review and corrections

### Real-context qualification correction

The first read-only Red preparation rejected an attempted rollback of inherited
regional-funding capability. No episode or controller input occurred. Preserving
the inherited flags authenticated the same post-Lorelei checkpoint and its real
story/field-healing menu, still with zero actions and frames. The runner now keeps
historical restoration checks unchanged and binds nine execution flags into the
forward continuation identity. Admission reconstructs those flags from the
authenticated header.

The reviewer identified a second, related risk: after field items become
unavailable, routed recovery can offer a Center trip with the same semantic kind.
Before each prediction, the opt-in player validates exact private direct-provider
profile/configuration identities. Unsupported menus are rejected whole, not
filtered. This guard does not obstruct post-macro observations or successful
terminal recording. These checks are recording-scope safety, not model knowledge.
The corrective batch passes511 focused tests, targeted typing and lint checks.
This is not a substitute for the separately running frozen full regression.

The internal reviewer supplied bounded test drafts; Codex independently reviewed
and executed them. Important corrections made before publication:

1. A variable cost denominator could perversely reduce cost when a zero-allowance
   attempt spent an item. Cost now always averages three fixed terms.
2. Current completion evidence must bypass latched semantic history.
3. Deterministic development probes must report one-hot behavior; the censored
   training sample must actually use the declared random sampler too.
4. Admission must bind the first native row exactly, not substitute a later
   eligible row when an earlier nontraining decision was excluded.

Positive admission tests use complete temporary private episodes, the real
sampler, controller recorder, trajectory wrapper, collector and existing native
reader. They contain simulated transitions, not ROM execution. Separate runner
wiring tests use a fake emulator, with the actual forward collector and failure
retention owner. No test pass is counted as Red competence.

Flash's preceding conceptual review is recorded in the
[PP/Champion audit](red-pp-choice-champion-stop-2026-09-09.md). No further external
review was required for this slice. Claude was not used. Neither service exposes
a fresh usable subscription quota reading here; five-hour/weekly remaining remain
unknown, not inferred from token counts.

## Next meaningful decision

Local verification at this boundary:394 focused learner/runtime/legacy tests
plus151 separate native-admission/product/roadmap tests pass. Targeted typing of
ten affected production modules/scripts, lint, registry freshness, documentation,
active-focus and public-artifact checks pass. These are545 focused tests, not a
new full-suite verdict. The previous published8a130429 hosted CI is green; a new
full regression will use a frozen copy after this batch is committed.

The implementation can now collect and fit prospective Red forward outcomes,
but it has **zero real examples for this objective**. The next experiment must
expose a real story-versus-recovery choice under a useful bounded continuation,
keep every outcome and expense, and test on a different known-training context
before any authority change. Two labels or a low training error alone cannot
establish reliable policy behavior. Do not copy toy support bounds into Red.

The current Champion battle has neither an available field restoration option
nor a new first-choice anchor. Finishing it through deterministic repair would
not supply the missing comparative dataset. Reorient before more boss repair;
do not retry its consumed plan or splice earlier resource states into that run.
The permanent story/living-Pokédex/transfer mission and stage exits are unchanged.
