# Collected Red run data and the next player test

Follow-up: the [review](2026-10-12-collected-run-data-review.md) qualifies the
causal interpretation and replaces the proposed next-session limits. The counts
and original audit evidence below remain unchanged.

The immediate recommendation is to test the existing highest-score goal selection
on a copy of the retained save before doing another fit or fresh campaign. The
deployed model already ranks story/access above every slow evolution choice in
the paused run, but the per-candidate exploration sampler frequently selects the
lower-ranked alternatives. This is a deployment-policy problem worth testing,
not evidence that we need another planner.

There are also real learning gaps: the active goal head has no fitted coefficient
contribution from its opponent-challenge or preparation feature blocks, and its
readiness view designates only the starter as a combat member. Fixing the sampler
would not, by itself, prove general learned party preparation or whole-game
autonomy. The existing battler, executors, learner and lesson recorder should be
reused to address whichever gap the next native test actually exposes.

The game and completion goal remain paused. This audit launched no emulator,
loaded no save, changed no player source or weights, fitted no data, deleted
nothing and published nothing. The retained terminal and context are unchanged.

## Coverage and limits

The census covers 467 directories with recognized metadata across the two retained
data locations, 723 unique root metadata files, and 20 recent declared fresh attempts.
Eighteen have completed goal receipts: 3890 outcomes, including 3492 successes,
381 ordinary setbacks and 17 nonordinary failed boundaries. The two other declarations
have no completed goal receipts; one has a startup KeyError.

The detailed fresh receipt pass reads 3948 files containing 4.78 GB of logical JSON
data. The audit also examines 293 selection diagnostics from the paused attempt,
131 older assisted segment results, selected TRAIN fit/coverage records, model
coefficients and the existing execution/selection implementation. It does not
claim to read every byte of the roughly 50 GB archive, enumerate the raw journal tree,
or benchmark the full battler. Two assisted root reports over 128 MiB are excluded
from that result-summary pass; the final 124-entry outcome is checked directly.

The principal reproducible counts are in
[the audit evidence](../evidence/red-collected-run-data-audit-2026-10-12.json).
Repeated snapshots, copied qualifications and assisted continuations remain separate
from independent evaluation evidence.

## The sampler dilutes the model's story priority

In 293 recorded mixed-menu decisions, the story/access candidate has the highest
model score 289 times. The sampler selects a lower-scoring candidate 158 times.
All 13 selected evolution goals score below an available story/access candidate.

At the first expensive evolution selection, the menu has nine evolution options,
three capture options and one story/access option. The story score is 4.356;
the selected evolution score is 3.015. Yet the combined probability of choosing
any evolution is 62.9%, versus 21.3% for story/access. Multiple lower-ranked candidates
outweigh the single higher-ranked candidate as a family.

The current selector samples a softmax over individual candidates and mixes in
25% uniform exploration. Lowering that uniform mix alone is insufficient: with
the same recorded scores and zero uniform mix, story/access still has only 25.8%
of the selection mass. The softmax also retains the candidate-count effect.

The existing greedy mode selects the highest fitted score without teacher ordering
or new weights. This is not a scripted walkthrough. It changes how the existing
model's rankings are used; normal game randomness remains. Its benefit still needs
native verification because these recorded states were produced by the sampled
trajectory. Offline rankings cannot prove the unexecuted alternative trajectory.

## Early evolution dominates runtime

In the paused run:

| Work | Goals | Recorded execution time | Share |
| --- | ---: | ---: | ---: |
| Evolution | 13 | 56.0 min | 64.7% |
| Capture | 55 | 14.1 min | 16.3% |
| Party development | 24 | 13.1 min | 15.2% |
| Story and transport | 148 | 1.9 min | 2.2% |
| Restoration, supply and exploration | 59 | 1.4 min | 1.6% |

These are measured goal-execution phases, not total machine time or counts of story
chapters. Preparation, capture and evolution together account for 96.2%.

The 13 evolution goals report 1249 completed training battles and 233 healing trips.
Eight evolutions finish; five retain partial XP while correctly remaining failed
goals. This is legitimate progress, but it is an expensive way to spend the early
story while the same model ranks access higher.

The actual frozen evolution module uses a disclosed rule-based inner trainer and
damaging-move selector. Its source matches the current module exactly. The learned
preparation battler is a separate connection; these evolution battles are not new
battler training or evidence that its weights improved. First avoid unnecessary
early evolution. Only then test whether reusing the learned battler inside that
skill is an outcome-relevant improvement; do not redesign the battler.

## The deployed goal model is trained narrowly

The active goal head has 151 settled TRAIN examples, 356 feature rows and 60 rows with
nonzero regression coefficients. Its explicit coverage contains 137 comparative
outcomes across capture, evolution, exploration, restoration and resupply, plus 14 unit
outcomes across capture, evolution and restoration. No direct story or
team-development example appears in this deployed head's coverage.

| Feature block | Rows | Rows with nonzero coefficients |
| --- | ---: | ---: |
| Goal kind | 9 | 5 |
| Readiness | 252 | 28 |
| Opponent challenge | 54 | 0 |
| Preparation | 13 | 0 |

Story/development predictions can generalize through shared learned features;
zero direct examples do not make their entire scores unfitted. However, the
opponent-challenge and preparation blocks cannot contribute through this head's
coefficients. The fresh plan also has no separate readiness refinement configured.

This explains why collecting increasingly detailed diagnostics does not itself
teach those decisions. A frozen run intentionally does not update its weights.
After identifying a real decision gap, the existing TRAIN recorder and fitter need
informative contrasts that exercise these features. Do not fit the development
runs or simply replay the same lessons.

There are existing specialist readiness/branch components and prior preparation
lessons to inspect for reuse. Their historical success is not proof that they are
connected to this deployment or generalize beyond their declared scope.

## Party readiness is not currently full-party readiness

The retained party has levels 38, 16, 16, 18, 36, 36: a physical spread of 22 levels.
Only the starter is declared combat; the other five are undecided. The projected
combat-level spread is consequently zero in the latest menus.

This may be intentional carry-centric scope, not an arithmetic bug. But it does
not support a claim that the model evaluates and develops a balanced six-member
combat team. High levels earned incidentally by evolution helpers are not learned
role selection. Reuse the existing purpose/readiness contracts when testing useful
roles; do not automatically grind every new capture to the carry's level.

## Capture failures mostly occur before a successful acquisition

The latest 55 capture goals produce 15 successes and 40 failures:

- 35 search-exhausted goals;
- 2 capture-item-exhausted goals;
- 3 resource-loss goals.

The journal records 34 completed throws and 15 verified captures. These counts do
not establish a universal catch probability, or imply that the other failures
are lost trainer battles.

There are 6802 completed seek operations, but only four have a known eligible-tile
exposure value, and those four values are zero. Total eligible encounter exposure
and actual RNG-check counts remain unknown. Unknown is not zero. Without that
denominator, we cannot reliably separate unlucky rare encounters from insufficient
effective search or an inefficient corridor.

The existing corridor already maintains search exposure, and the survey diagnostic
already expects before/after exposure. Reconcile that existing connection and
preserve unknowns rather than building another logger or inventing an encounter
probability from button counts. A useful subsequent search test must measure real
eligible steps, encounters, selected-target sightings and route interruptions.

The selected success-score outputs also overpredict completion in this receipt
scope: acquisition averages 0.765 against 15/55 completed goals; evolution averages
0.971 against 8/13. These regression outputs are explicitly not calibrated
probabilities. Partial XP can be valuable even when the declared evolution fails.
The mismatch warrants targeted outcome/cost lessons, not a demand for 100% success.

## Many recent runs repeat the same experience

All 18 recent attempts with goal receipts use the same goal-model digest and seed.
Of 3890 source/terminal/goal transition events, 1147 are distinct and 2743 repeat:
70.5% of these events duplicate another recorded transition. This is not a
whole-archive byte-duplication estimate or an independence test.

The native meters report 3.54 million attempted actions, 290.67 million frames,
624236 diagnostic events and 19.45 hours across these attempts. They provide strong
regression evidence that fixes survive fresh play. They do not demonstrate a new
learner update. The longest recent fresh frontier remains four badges and 35 entries;
the current paused save has two badges and 28 entries.

On a local execution defect, use the exact retained boundary and relevant checks
before another full fresh replay. Full frozen fresh runs remain necessary to
prove final autonomy, but they should follow useful integration readiness rather
than substitute for local diagnosis or learning.

## Better fitting has not always produced better decisions

The October 9 collection candidate adds 11 admitted TRAIN examples, retains the original
151 and lowers new-example training error from 0.0442 to 0.0144. However, the retained
four native comparison arms end at identical terminal states with the same choices.
That candidate is not adopted and is not the head used by these fresh attempts.

The comparison notes that healing collapses the intended condition difference;
route candidates have the same projected party risk and differ mainly in effort.
This is a concrete reason not to repeat that fit or equate lower training error
with better play. Future contrasts must survive the actual execution path and
change an informative input at the next decision.

## Logging contributes overhead but is not the main delay

The latest run records 1036.8 seconds in menu/boundary observation, about 16.4% of its
metered run time. Goal selection and its receipt take 2.06 seconds in total.
The diagnostic journal callback meter records 436.9 seconds, about 6.9% of native
runtime. Across the 18 fresh attempts, the same callback meter totals 3892.5 seconds,
or 5.6% of native runtime.

The callback meter is not all logging overhead, and it can overlap the execution
phase. Do not add these percentages together. A stronger or faster coding model
does not accelerate the local player's already-recorded goal inference time.
Unnecessary long training is the larger immediate lever; static-data caching and
redundant diagnostics are secondary profiling questions.

Some root reports are incomplete even when their basic game facts look current.
One fresh attempt's root spent counter says 414 decisions while its native meters
and outcome receipts establish 456. The paused run's raw interruption label also
looks like an execution error despite its verified safe user-requested stop.
Use the typed receipts and native meters when these summaries disagree; retain
the original reports instead of rewriting history.

## What remains reusable

The assisted reference's final verified outcome has 124 registered species, eight
badges, Champion/Hall-of-Fame objectives and ready control, including all four
legendary registrations. It demonstrates broad mechanical coverage, not final
unassisted acceptance. Its battle, route, PC, evolution, capture, resource and recovery
skills remain useful.

The immediate task does not require replacing that infrastructure, the local
goal head, the battle scenario factory or the battler. It requires using the
existing rankings effectively, then testing the missing readiness and search
connections where the data shows they matter.

## One proposed next experiment

Hypothesis: highest-score selection reduces candidate-family dilution and costly
early evolution, allowing the unchanged player to advance story without an
operator walkthrough.

1. Authenticate the paused state/context and all original members, costs and history
   on a zero-input copy using the existing continuation entry.
2. Declare a separate DEVELOPMENT copy with existing goal_selection.mode=greedy.
   Reuse the immutable source package, goal weights and battlers; do not edit the
   original fresh declaration or add a supplied story order.
3. Allow 20 goal decisions, with model/support attribution, or 30 minutes of
   measured execution in a 90-minute work block. Reassess after 15 minutes or
   two equivalent failures.
4. Accept only actual useful story progress toward Cut/Surge with legitimate
   recovery and verified roster/accounting. Transport microsteps and higher
   offline scores alone are insufficient. Record incidental collection honestly.
5. If it loops, exposes unsafe readiness or hits a real execution failure, retain
   the terminal and classify the failing layer. Use existing TRAIN or execution
   components for the demonstrated gap; explain a new subsystem before building it.

No test is launched by this audit. No copied gains return to the original save,
and a restored DEVELOPMENT continuation is not zero-restoration frozen acceptance.
There is no defensible whole-project percentage or completion date from these
correlated partial runs. Broad mechanical coverage is proven in the assisted
reference; full fresh autonomous story and collection remain the delivery gate.

## Model recommendation

Astra is useful for challenging the synthesis and choosing between competing
causal explanations. Bulk parsing and deterministic aggregation do not require
it. Official guidance places GPT-6.1 Sol at extra-high effort on decisions built
from conflicting evidence, and Astra at extra-high on demanding analysis.

For the next review, I recommend Astra high or max at standard speed, then
GPT-6.1 Sol high/max for a clearly scoped implementation and native test.
This is a workload recommendation, not a measured comparison on this archive
or confirmation of the app's current setting.
[Official model guidance](https://learn.chatgpt.com/docs/model-selection#how-to-think-about-models-and-reasoning-effort).

Audit completed October 12, 2026. All game workers remain stopped; the completion
goal remains paused. No new registrations, TRAIN examples, fits or weight changes
are produced by this analysis.
