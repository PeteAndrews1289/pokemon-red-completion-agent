# History-aware learner: engineering ready; new gameplay lesson still pending

## Verdict

The outcome learner can now consume measured search effort, retain unknown history for old
examples, fit mixed old/new data and replay sampled decisions through the actual native episode
reader. This is not yet evidence of improved Red play. No real fit, new example or controller
action happened this session. [Qualification](../evidence/red-history-aware-learner-qualification-2026-09-06.json).

The authenticated 32-example model has a separately published V2 initialization. Its existing
predictions are identical (maximum measured difference 0.0 across the retained menus), all
32 example fingerprints and targets remain unchanged, and new history coefficients start at
zero. Initialization is not a fit or an authority promotion. The original model/corpus remain intact.

## What changed

- V2 adds a tracked-history presence indicator and bounded attempt, exhaustion, action and frame
  counts. Missing history and tracked-zero are different. Earlier unrecorded history stays unknown.
- Counts use fixed bounded transforms: `n/(n+1)` for attempts/exhaustions,
  `actions/(actions+1000)` and `frames/(frames+60000)`. These are feature scales, not penalties.
  Learned coefficients determine the sign and size of history's effect on each predicted outcome.
- Legacy model bytes/menus remain readable and retain their identities. A legacy fit/scorer cannot
  silently drop history-bearing inputs. V2 fitting pads only the representation of old rows;
  it does not rewrite their stored evidence or invent histories.
- The native fitter authenticates the same complete episode inventory and previous fingerprints,
  retains negatives, rejects development fitting and still requires additional settled evidence.
  Comparison against the prior uses the same zero-history-weight initialization, not a reset model.
- A V2 runtime starts tracking after authenticating the original checkpoint. Saved tracking is
  restored rather than reset. The new private bootstrap publisher verifies the retained corpus
  before writing a separately identified model; it never runs the fitter or game.

## Audit finding fixed: a route is not a search source

The previous memory boundary used the execution binding as its source key. Routed bindings
contain the current origin's identity, while the local skill uses a different identifier.
Movement/arrival could therefore hide remembered searches. The fix keeps a stable adapter-private
search-source reference across transport and local execution. Both recording and projection use
it. It never enters policy features; private binding wrappers preserve it.

Regression tests move the starting point, arrive at the local skill and verify the same source;
other tests exercise actual metered recording, observation, persistence and identity-free menus.
The whole collection-objective digest still scopes history conservatively: a changed objective
does not prove a source is productive, and no history is backfilled from coarse old summaries.

## Real saved-state inspection and the remaining bottleneck

The final saved state reopens with identical bytes and ledger, zero input and zero frames:
14 living species, 19 registered, 17 specimens, 106 requirements remaining. The six-member party
is already level 63/55/55/55/55/55; grinding it arbitrarily would not solve the collection problem.

The current box contains duplicate unevolved specimens, including two Metapod and two Kakuna.
These are concrete potential evolution lessons that can preserve one precursor. **They are not
yet executable alternatives in this player.** The targeted provider requires a supported center
boundary and an injected boxed-evolution executor; the current launcher supplies neither from
the saved field endpoint. Separately, the high-level menu deliberately accepts one option per
goal kind, so multiple encounter sources need a subordinate choice rather than duplicate acquire
goals slipped through the existing contract.

## Reorientation

The anti-drift alarm applies: this was another engineering session without a new real learning
outcome. Stop feature/process expansion here. The next session's named unblock is the smallest
connection from current field state to an existing required-precursor evolution/storage skill,
including travel, healing if needed, exact specimen preservation and bounded execution. Reuse
existing routing/PC/training mechanics; do not create another teacher or scenario factory.

1. Authenticate the saved endpoint and select an eligible duplicate precursor from observed
   collection requirements; prove the intended evolution preserves the living collection.
2. Connect existing transport, PC exchange and bounded evolution to the native player. Exercise
   the short skill and retain failures/costs; availability alone is not completion.
3. Once two useful actions actually exist, prospectively collect a short sampled lesson with the
   V2 initialization, fit all retained old plus new outcomes and run a bounded follow-up.
4. Stop if this becomes another acquisition-only loop, arbitrary leveling, fixed-route repair
   spree or receipt campaign. No full replay, sealed Red, ROM-hack or Crystal execution.

The roadmap remains **2/5 (40%)**. The third item says *model trained to use history*, not
*model accepts history*. It stays unfinished until authentic new data train that effect. This
distinction deliberately prevents engineering progress from inflating gameplay completion.

No external reviewer or subagent was invoked. Codex owns this implementation and adjudication.

## Verification closeout

- Full non-integration regression run: **7,172 passed, 1 skipped, 1 expected failure** in 17m44s.
  This was one completed local broad run, not hosted-CI evidence or gameplay execution.
- 157 focused learner, memory, routing, native-training and continuation checks passed; these
  overlap the full suite and are not an additional independent denominator.
- Four targeted in-memory mutations were killed: erased history, unknown treated as tracked
  zero, prediction-time history omission, and memory keyed by the changing execution binding.
  This is targeted coverage, not a whole-repository mutation score. No source was patched during
  the broad test run.
- 399 source files passed configured type checking; lint, public-artifact safety, generated
  documentation/focus and registry checks passed. The updated infographic was visually inspected.
- The model initialization was created from committed source `413aabbb`; it remains separate
  from the original model and is not a new fit. No emulator or fitter is left running.
