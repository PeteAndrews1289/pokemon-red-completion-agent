# Pokémon Red Completion Agent

> **Working on this repository?** Start with [HANDOFF.md](HANDOFF.md).

[![CI](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: Hall of Fame verified](https://img.shields.io/badge/status-Hall_of_Fame_verified-16a34a.svg)](docs/roadmap.md)

**A completion-first autonomous system for Pokémon Red: verified quest planning, deterministic
control, and progressively trained specialists.**

## Current position

The deterministic teacher is a complete, reproducible expert oracle: **312/312 semantic
checkpoints**, **36/36 objectives**, a six-member final-form team, the Champion, and the Hall of
Fame in one clean-power process. The portable clean-start player now also selects objectives from
fresh semantic observations without receiving expected labels. In one explicitly uncounted
baseline, the objective and trainee/venue models completed all 36 objectives through Hall of Fame
with **114,831 controlled training choices**, **400 executed disagreements**, and no fallback.

The stricter five-role rehearsal then did exactly what a useful evaluation should do: it rejected a
win. Its historical controller defeated Lorelei but used only party slot 1 for all 19 attacks. That
failure drove feature schema v3, which represents every reserve through identity-free health,
level, usable moves, type advantage, defensive resistance, and PP, then binds a semantic switch to
the actual live party target.

Four complete clean-power v3 teacher lineages now exist. The newest records **3,166** high-level
labels, **13 explicitly targeted switches**, **1,808 development battles**, a final
60/55/55/55/55/55 team, and Hall of Fame. A replacement controller trained on two whole lineages
scores **98.2394% accuracy / 94.7537% balanced accuracy** on the untouched third split, with 10/13
deterministic switch targets correct. Causal execution has progressed through Rock Tunnel, Lorelei,
Bruno, and an Agatha win while preserving every rejected contract: initial-role residency, status
safety, specialist residency, bounded setup, and exact observed-role switching. The latest replay
passed all of those constraints together but failed because the model requested a switch while the
hand-written target scorer chose Blastoise instead of the demonstrated Jolteon role for Golbat.

That failure is now an explicit learning seam. The first identity-free, permutation-equivariant
switch-target head improved an untouched lineage from **10/13 (76.9%)** deterministic agreement to
**11/13 (84.6%)**. On the fresh fourth lineage it again scored 11/13, while the deterministic
resolver fell to 9/13; the same Bruno and Agatha transitions remained. After that one-time test was
opened as development evidence, plan-balanced training and lower preregistered regularization
reached **54/54** across four leave-one-whole-lineage-out folds. The frozen second candidate fits
41/41 development targets and scores 13/13 on the existing whole-lineage validation set, but it
remains `deployment_authority: false` until a new unopened lineage passes. See the
[third lineage](docs/evidence/battle-control-reserve-matchup-v3-lineage-03-2026-08-09.json),
[candidate](docs/evidence/battle-control-reserve-matchup-v3-lineage-candidate-02-2026-08-09.json),
[latest preserved failure](docs/evidence/battle-control-reserve-matchup-v3-causal-13-failure-2026-08-09.json),
[offline target-head receipt](docs/evidence/battle-switch-target-offline-candidate-2026-08-09.json),
[fourth complete lineage](docs/evidence/battle-control-reserve-matchup-v3-lineage-06-2026-08-09.json),
[second target candidate](docs/evidence/battle-switch-target-development-candidate-02-2026-08-09.json),
and [Crystal transfer benchmark](docs/crystal-transfer-benchmark.md).

Two failed timing/RNG attempts remain preserved and excluded from fitting: one stopped at 275/312
on a third legal Route 11 sleep episode, and the next reached 284/312 before an overstrict receipt
misclassified opponent-inflicted poison. The fourth complete lineage independently qualified both
repairs through Hall of Fame. The global sleep bound remains conservative, and the pre-Giovanni
Center boundary still requires full HP, clear status, and restored PP.

Seed `990006` stopped before that test boundary after 1,500 zero-faint training wins: four members
were level 55, two were level 54, and the old 1,250-trip recovery cap expired. Its partial labels
are excluded. Fresh seed `990007` then qualified the recovery repair and produced 17 authenticated
target rows through an Agatha win. The unchanged frozen candidate passed **17/17** with 0.07965
cross-entropy versus **12/17** for the deterministic resolver, including all seven Agatha targets.
The route stopped at 306/312 because its terminal receipt reconstructed only five of seven executed
role switches from move turns; explicit live switch receipts now fix that referee boundary. The
authenticated target-artifact format and runtime binding are now implemented. The loader binds the
canonical payload to its feature schema, disjoint development lineages, and the 17/17 prospective
test. The exact frozen payload has now been privately published and independently loaded; see the
[sanitized runtime-artifact receipt](docs/evidence/battle-switch-target-runtime-artifact-2026-08-09.json).
Runtime can shadow the target head or let it replace only the reserve bound to a
teacher-authored switch request while ordinary moves remain teacher-gated. Canonical shadow then
completed Red with **13/13** target agreement and no unavailable projection; a fresh isolated causal
run completed the same **45,819,749-frame** route through Hall of Fame with **13/13 learned target
rebindings and zero target fallback**. See the
[canonical runtime qualification](docs/evidence/battle-switch-target-canonical-runtime-qualification-2026-08-09.json).

The first six-role teacher-free composition exposed the next interface gap at the S.S. Anne rival:
after seven valid learned HP recoveries and two learned switches, the chapter recognized an eighth
complete recovery request but still required its teacher-only exception subclass. That uncounted
failure is preserved, the executor now accepts only a complete learned lead-HP target under the
existing bounded inventory and exact recovery proofs. Fresh seed `990012` qualified that repair,
then exposed a Route 11 intent that advertised status and HP recovery before the Mart stock-up even
though only protected status copies existed and HP allowance was zero. Capabilities now recompute
from live surplus and remaining allowance before every dispatch. Seed `990013` qualified both
repairs and advanced through all eight badges, balanced development, Victory Road, and a Lorelei
win with zero battle-teacher queries. The verifier still rejected it: the controller attacked at
59 HP even though Lorelei's teacher and receipt require 70. That floor is now an explicit typed
intent, unavailable action classes are masked before ranking, and the final report independently
requires every requested model role to exercise authority. See the
[third preserved failure](docs/evidence/portable-clean-start-six-role-rehearsal-03-failure-2026-08-09.json).
Fresh seed `990014` qualified that HP/action-mask boundary and reached Lance's room after defeating
Lorelei, Bruno, and Agatha. Across 3,286 battle decisions it made 51 typed high-level requests with
zero teacher, safety, or low-confidence fallback; the target head owned 21/21 switch bindings and
both training models retained causal authority. The evaluator again rejected the result, this time
because Agatha's receipt treated one valid learned pivot to another real party member as though it
had to equal the fixed teacher's preferred specialist. Specialist attack coverage had already
passed. The repaired receipt now proves every target against the observed party and leaves the
strategy lesson to the independent turn trace; see the
[fourth preserved failure](docs/evidence/portable-clean-start-six-role-rehearsal-04-failure-2026-08-09.json).
Fresh canonical seed `990015` then completed all 36 objectives and Hall of Fame with the exact
six-role stack: 3,315 battle decisions, 21/21 learned switch bindings, 64,337 training-control
choices, 125,800 trainee/venue choices, and zero teacher query, teacher fallback, safety fallback,
or low-confidence fallback. The
[canonical qualification](docs/evidence/portable-clean-start-six-role-canonical-qualification-2026-08-09.json)
is the first source-bound terminal proof for the combined stack.

The paired timing root `990016` correctly prevented promotion. It failed before any learned battle
or training decision because the lab-rival verifier hard-coded one legal Squirtle HP determinant
outcome and exhausted its post-win dialogue cap. Direct reproduction proved a real victory: battle
result zero, the rival event set, level 6, and a legal 23/23 HP Squirtle. The repaired gate retains
the cartridge win, event, species, level, map, script, and released-control proofs while accepting
the legal 21–23 max-HP range; see the
[perturbation failure](docs/evidence/portable-clean-start-six-role-perturbation-01-failure-2026-08-09.json).
Navigation, menus, chapter mechanics, and resource execution remain authored. The counted v95
reliability campaign remains unopened at
**0/10**, and no Crystal or living-Pokédex result is claimed.

That distinction is the heart of the project and its public story. The teacher supplies verified
demonstrations and a referee; it is not the final autonomous player.

### Capability snapshot

| Layer | Best verified evidence | Honest boundary |
| --- | --- | --- |
| Deterministic teacher and referee | Clean power-on, 312/312 semantic checkpoints, 36/36 objectives, Champion and Hall of Fame | Expert oracle, not a learned player |
| Learned objective dispatch | One clean-start run selected 21 composite objectives and verified 15 automatic effects through Hall of Fame | Many choices remain affordance-masked; mechanics are fixed skills |
| Learned training control | The trainee/venue ranker beat its shape baseline and completed clean start with 114,831 controlled choices and 400 disagreements | One uncounted Red root; navigation and menus remain authored |
| Strict learned-stack composition | Seed 990015 completed 36/36 objectives and Hall of Fame with 3,315 battle decisions, 21/21 learned target bindings, and both training heads in live control | One canonical root; authored route and menu skills still execute mechanics |
| Reserve-aware battle control | Frozen target head passed 17/17 prospective targets, 13/13 isolated causal bindings, and 21/21 bindings inside the combined canonical completion | The first paired timing root exposed an early deterministic-referee defect before model decisions; fresh perturbation qualification remains |
| Multi-root evaluation | Source/model/root-bound 8-of-10 registry and independent checker are implemented | Counted campaign remains 0/10 until a repaired perturbation rehearsal passes |
| Transfer | Identity-free observation contracts, typed skills and authenticated artifact boundaries | No second-title result yet |
| Living Pokédex / level 100 | Target definition and planning foundations only | Autonomous collection and long-horizon development remain future work |

The project is therefore past “can automation finish Red?” and at the more useful question:
**which decisions can a learned, portable controller own without an answer key?** Every promotion
receipt separates teacher, shadow, constrained, and model-controlled authority so a green result
cannot blur that boundary.

For a compact technical review, read the
[current capability and portfolio audit](docs/current-audit-2026-08-09.md). The complete evidence
log is preserved below for reproducibility, but collapsed so the repository's first screen states
the result and boundary before the experiment history.

For a hiring-manager-friendly version, use the
[one-page portfolio brief](docs/portfolio-brief.md): verified results, architecture, strongest
debugging story, interview topics, resume bullets, and a two-minute demo outline.

<details>
<summary>Current research evidence log (full metrics and claim boundaries)</summary>

The portable loop now has one uninterrupted Hall-of-Fame integration proof. Starting from an
authenticated Celadon capture, the learned objective ranker dispatched **20 objectives** in the
same emulator process: Rocket Hideout through the Mansion, the six-member development block, the
final two Gyms, Victory Road, the Elite Four, and the Champion. Registered fixed skills executed
**502,175 actions / 37,369,283 frames** with zero expected-route labels, teacher fallbacks, or
replans. Fresh observations verified all **36 completed graph objectives** and the Hall-of-Fame
terminal. The model made one genuine ranking choice—Koga versus Strength, selecting Koga at
**96.41% confidence**—while the other 19 dispatches had one executable candidate. The run begins
from a captured state, and mechanics remain teacher-authored, so this proves continuous objective
dispatch and integration rather than clean-start or end-to-end learned play. See the
[twenty-decision receipt](docs/evidence/affordance-masked-twenty-objective-hall-of-fame-2026-08-08.json).

The training bottleneck is now measured inside that same uninterrupted run. The post-Mansion
Blaine skill used **469,232 actions / 31,883,961 frames** to develop the six final-form members to
**60/55/55/55/55/55**, clear the quizzes and two intentional trainer lessons, defeat Blaine, collect
TM38, and return healed. That one skill consumed **93.44% of all actions** in the twenty-dispatch
run, making learned training control the next concrete replacement target. See
the [post-Mansion Blaine receipt](docs/evidence/affordance-masked-post-mansion-blaine-2026-08-08.json).

That replacement now has a data boundary. The live teacher can emit every strategic training
choice as one of `seek`, `fight`, `flee`, `heal`, or `stop` before executing it. Its 25 normalized
features describe party readiness, relative matchup safety, resources, venue suitability, and
bounded progress without retaining Red map IDs, species IDs, move IDs, or memory addresses. The
captured-state replay tool can preserve successful or failed decision streams for later lineage
splits. This is instrumentation, not a trained training policy; the next gate is to collect complete
disjoint lineages and fit a candidate without mixing one run across train and validation.

The first diagnostic collection has now completed from the authenticated Secret Key boundary:
**48,156 decisions** across **1,716 battles**, **885 healing trips**, zero faints, and a final
`55/55/55/55/55/55` party. It contains 44,882 seek, 1,710 fight, 1,064 flee, 499 heal, and one stop
label, with zero phase-legality violations and 47,370 unique feature vectors. Because `seek` is
93.2% of the stream and this is only one unassigned lineage, no model or held-out score is claimed.
See the [sanitized lineage receipt](docs/evidence/training-control-lineage-01-2026-08-08.json).

The offline candidate implementation is ready for those future v2 lineages. It trains a small
class-balanced nonlinear classifier, masks actions that are illegal in the current phase, refuses
root-state overlap across training and validation, and reports balanced accuracy alongside ordinary
accuracy. Candidate summaries remain `promotion_eligible: false` until a frozen model passes real
lineage-held-out, shadow, and model-controlled emulator gates.

The first counted v2 training lineage is now qualified. A retained 17-frame-perturbed root produced
**46,687 decisions**, all five action classes, **1,726 battles**, **815 healing trips**, zero faints,
and an all-level-55 terminal. The production loader verified its clean source commit, distinct root
digest, phase legality, and exact terminal stop. Of 45,902 unique action-feature pairs, **45,831
(99.85%)** were absent from diagnostic lineage 01. This is accepted training data, not yet a model
result; independent v2 train and validation roots remain required. See the
[counted lineage receipt](docs/evidence/training-control-v2-train-01-2026-08-08.json).

A second idle-wait attempt exposed an important collection trap. Waiting 43 frames produced the
same saved root as the 17-frame attempt and replayed the exact same 46,687 teacher decisions, with
zero novel action-feature pairs. It is a useful reproducibility control, not another lineage, and
has been rejected from the learning split. New roots must now prove semantic equivalence after a
reversible perturbation and byte-level distinction before collection. See the
[idle-equivalence receipt](docs/evidence/training-control-idle-wait-equivalence-2026-08-08.json).

The first honest motion-root replay demonstrated that the difference mattered. It produced 11,122
decisions before a trainee fainted during a durable matchup; 10,375 of its 10,431 unique pairs were
new versus train lineage 01. The failed stream remains diagnostic and cannot enter a model split.
The repair applies the declared health retreat floor before every in-battle move, then uses the
existing bounded escort-and-flee path. See the
[failed-lineage receipt](docs/evidence/training-control-v2-train-02-motion-failure-2026-08-08.json).

The same motion root then passed under the repaired teacher: **60,192 decisions**, **1,740
battles**, **1,017 healing trips**, zero faints, and all six at level 55. Its five-class stream is
production-loader qualified, and 59,303 of 59,368 unique action-feature pairs (**99.89%**) are new
versus train lineage 01. Two training roots now exist; a disjoint validation root is the last data
gate before fitting the first real candidate. See the
[repaired motion-lineage receipt](docs/evidence/training-control-v2-train-02-motion-repair-2026-08-08.json).

The first preregistered validation root remained honestly held out and failed after 17,751
decisions. It had already completed 725 battles and was still gaining levels, but 33 consecutive
safe exits tripped a 32-flee anti-loop bound. The failed root will not be rerun as validation. The
repair keeps consecutive flees as a saturated model feature, preserves the early no-win venue
check, and relies on the global step budget for later non-progress; a fresh validation root is now
required. See the
[failed-validation receipt](docs/evidence/training-control-v2-validation-01-failure-2026-08-08.json).

Fresh validation root 02 then completed with 60,459 decisions, 1,767 battles, 1,021 healing trips,
zero faints, and all level 55. The leakage audit passed with no root overlap and all five classes
covered. The predeclared default MLP achieved **75.62% raw / 76.91% balanced accuracy** on this
untouched lineage; 99.72% of its unique pairs were absent from training. This is the first real
offline training-control model, but it remains non-promotable until shadow and model-controlled
emulator runs pass. See the [validation receipt](docs/evidence/training-control-v2-validation-02-2026-08-08.json)
and [candidate receipt](docs/evidence/training-control-candidate-v1-2026-08-08.json).

The next gate is implemented. Private model loading now requires an exact SHA-256, a regular
non-symlink file, the complete feature/class schema, finite correctly shaped parameters, and the
declared model format. `replay_training.py` can run that authenticated model in shadow mode: it
records confidence, raw and balanced agreement, per-phase accuracy, action distributions, and the
full teacher-to-model confusion matrix while the teacher alone retains execution authority. The
next fresh root will produce the first live shadow receipt.

That fresh-root shadow is now complete. Across **55,904 live decisions**, the authenticated model
reached **75.57% raw / 76.73% balanced agreement**, closely matching held-out validation, while the
teacher completed 1,743 battles with zero faints and all six at level 55. Battle agreement was
65.42% and overworld agreement 76.23%. The confusion matrix exposes the control risks: fight recall
is only 42.05% because 1,134 safe fights became conservative flees, while 12,285 seeks became
unnecessary heals. Stop recall was exact. The model still had no authority. See the
[live shadow receipt](docs/evidence/training-control-shadow-01-2026-08-08.json).

The first authority boundary is now implemented as battle-only control. The authenticated model may
choose `fight` or `flee`; overworld seeking, healing, and stopping remain teacher-controlled. A
model-selected safe flee is executed even when the teacher would fight. A model-selected fight at
any volatile, excluded, unsafe-health, capped-escort, or exhausted-PP boundary fails the run closed
instead of substituting the teacher action. The control audit states its authority phase and that
no teacher fallback occurred. This is intentionally narrower than full training control, but it is
real model authority over the measured weakest phase.

The first battle-controlled root failed closed after 480 decisions. The model agreed on 479, then
requested `fight` when the live move policy had exhausted or disabled every admissible training
attack; the referee terminated with no fallback. The preceding safe fight and failing flee had the
same feature vector, proving the legal candidate set had not been updated when runtime authority
changed. The repair removes `fight` from candidates at volatile, excluded, unsafe, capped-escort,
and unavailable-attack boundaries. This is an affordance-mask correction, not a hidden teacher
override. See the
[controlled failure receipt](docs/evidence/training-control-battle-control-01-failure-2026-08-08.json).

The corrected second controlled root passed that unsafe-action boundary, then exposed the model's
other measured weakness causally. Across 77,538 decisions it replaced 1,963 of 2,690 safe teacher
fights with real flees, stretched the lesson to the healing limit, and stopped before readiness.
No teacher fallback concealed the failure. The learner had masked unavailable actions at inference
but not inside its training loss, so it spent capacity predicting decisions for singleton candidate
sets. The loss now normalizes only over each observation's actual candidates; fresh lineages are
required before fitting the replacement. See the
[under-fighting receipt](docs/evidence/training-control-battle-control-02-failure-2026-08-08.json).

The replacement campaign now closes that failure. Two fresh training roots and one untouched
validation root all reached level 55 with zero faints and 99.86% of validation's unique tuples
absent from training. With the candidate mask applied inside the loss, the unchanged 24-unit MLP
reached **78.06% raw / 89.25% balanced validation accuracy** and 100% fight/flee recall. A fresh
57,342-decision shadow again achieved 100% battle agreement. Under real battle authority, the model
then completed a fresh 59,137-decision lesson with 1,743 battles, zero faints, all six at level 55,
and no fallback. Overworld remains teacher-controlled because 12,405 safe seeks were still
predicted as unnecessary heals. See the [candidate](docs/evidence/training-control-candidate-v2-2026-08-08.json),
[shadow](docs/evidence/training-control-shadow-02-2026-08-08.json), and
[controlled success](docs/evidence/training-control-battle-control-success-2026-08-08.json) receipts.

The first overworld-control collection was stopped before producing a training artifact. The audit
found that 356 required heals in a representative lineage were caused by the safety escort, while
the v1 observation exposed only the trainee's health and PP. That missing cause explains why held-out
heal precision was only 3.49%. Feature schema v2 now adds game-neutral safety-reserve health,
status, attack PP, and PP margin; the three exposed roots are excluded rather than replayed. See the
[observation audit](docs/evidence/training-control-overworld-observation-audit-2026-08-08.json).

The replacement promotion is now preregistered before opening validation: whole-lineage
train-to-train selection fixes the class-balance power, then one sealed validation lineage must
clear explicit false-heal, missed-heal, missed-stop, accuracy, and causal budget gates. The
authenticated controller can now be injected into the portable Red loop's `defeat_blaine` skill;
battle and overworld authority are enabled separately, every decision is audited, and disagreement
never falls back to the teacher. See the
[promotion plan](docs/evidence/training-control-overworld-promotion-plan-2026-08-08.json).
Two replacement roots failed before qualification under teacher authority—not model authority. One
exposed a rare direct-fight knockout; the other confirmed the escort switch in memory but never
re-exposed the battle menu inside the bounded settle loop. Both partial streams are excluded, their
fresh replacements were preregistered before collection, and the failures remain visible in the
[teacher-failure audit](docs/evidence/training-control-v5-teacher-failures-2026-08-08.json).

The preregistered feature-v2 candidate did not pass. Its untouched validation lineage reached
96.18% raw / 98.33% balanced accuracy and perfect battle accuracy, but still missed 26 mandatory
heals and predicted 2,219 unnecessary heals—4.06% of safe seeks. Heal precision was only 20.72%,
well below the 92% gate, so shadow and causal control were not attempted. The
[offline rejection](docs/evidence/training-control-candidate-v3-rejected-2026-08-08.json) retires
that validation lineage. V6 applies the same safety-affordance principle already proven in battle:
mandatory recovery exposes only `heal`, verified readiness exposes only `stop`, and genuinely safe
overworld states retain the causal `seek`/optional-`heal` choice. Five fresh roots, their split,
unchanged gates, and the no-reuse rule are frozen in the
[v6 promotion plan](docs/evidence/training-control-affordance-v6-promotion-plan-2026-08-08.json).
Candidate summaries now expose authenticated lineage/root identities, and the offline gate checker
authenticates both the plan and summary before scoring all eight thresholds. It exits nonzero and
forbids shadow automatically when any operational gate fails.

The fresh v6 offline campaign now clears those eight gates. Two training lineages contributed
120,214 decisions; one untouched validation lineage contributed 60,164, with zero root overlap and
an all-level-55, zero-faint terminal in every run. The selected model made zero validation errors.
The equally important negative result is that a candidate-set-only baseline also scored 100%:
`fight/flee` was always labeled `fight`, `seek/heal` was always labeled `seek`, and every other
candidate set was a singleton. This qualifies the candidate to enter live shadow, but it does not
show that the other 25 features add predictive value or that training strategy is learned. See the
[offline qualification](docs/evidence/training-control-affordance-v6-offline-2026-08-08.json).

The preregistered v6 live campaign now clears its shadow and full-authority causal gates. The
causal controller owned all **57,644** strategic decisions across both battle and overworld phases:
**1,365 evolution battles, 56,279 balancing decisions, 1,801 total battles, 1,046 heals, zero
faints, and a 55/55/55/55/55/55 terminal**, with no teacher fallback. All seven operational gates
passed. This is strong evidence that the authenticated authority path and safety affordances work;
because the choice-only baseline is still perfect, it is deliberately **not** evidence that the 25
state features drive the policy. The next dataset records candidate-relative trainee and venue
choices—the first interface designed to make state-dependent strategy identifiable. See the
[causal qualification](docs/evidence/training-control-affordance-v6-causal-2026-08-08.json) and its
[frozen candidate-ranker plan](docs/evidence/training-candidate-ranker-v1-promotion-plan-2026-08-08.json).

The strategic replacement has now passed its offline gate. Two complete training roots fixed the
model configuration before the sealed validation root opened. On that untouched lineage, the
shared identity-free scorer reached **99.9004% on 7,030 genuine multi-candidate decisions**, versus
**95.6615%** for a baseline that sees only choice kind and candidate count. Trainee accuracy was
**99.7727%** and venue accuracy was **100%**; all three lineages ended at level 55 across all six
members with zero faints. This is the first current training result where state-relative features
demonstrably beat choice shape.

The separately preregistered shadow then passed: **119,353 genuine choices**, **99.9941% genuine
agreement**, both choice kinds exercised, **1,802 battles / 1,098 heals**, all six at level 55, and
zero faints. The first causal root did not pass. It stopped after 15,449 model-authority decisions
when the training lesson exhausted its healing budget, ending at 51/32/32/31/31/31. Crucially, the
model agreed with the teacher on every candidate choice before termination. The failed root remains
an immutable operational rejection—not evidence of a bad prediction and not permission to weaken
the gate. See the
[offline strategic-ranker receipt](docs/evidence/training-candidate-ranker-v1-offline-2026-08-08.json)
and [runtime rejection](docs/evidence/training-candidate-ranker-v1-runtime-rejection-2026-08-08.json).

The same-root teacher diagnostic then completed normally, exposing an authority-wrapper defect:
even an agreeing callback recomputed the downstream directive and changed mechanics. The repair
makes teacher agreement a behavioral no-op and pins that invariant in a ROM-free regression test.
On a newly preregistered byte-distinct root, the unchanged authenticated model then controlled
**119,668 choices**, executed **191 real trainee disagreements** with no fallback, completed
**1,803 battles / 1,114 heals**, and ended at **55/55/55/55/55/55 with zero faints**. All 19 runtime
gates passed. See the
[runtime qualification](docs/evidence/training-candidate-ranker-v1-runtime-qualification-2026-08-08.json).

The same ranker is now qualified inside the portable objective loop. From the authenticated
post-Secret-Key capture, the objective model dispatched `defeat_blaine`; the strategic model then
controlled **114,831 trainee/venue choices**, executed **400 teacher disagreements** with no
fallback, and completed **1,803 development battles / 1,048 heals**. The fixed skill defeated
Blaine and returned a fully healed **60/55/55/55/55/55** party; fresh observation added the Volcano
Badge and opened Giovanni. The objective dispatch was a singleton and mechanics remain authored.
See the
[portable strategic qualification](docs/evidence/training-candidate-ranker-v1-portable-qualification-2026-08-08.json).

The clean-power `play` command can now authenticate the same candidate-model file by exact SHA-256,
observe it in shadow or grant it trainee/venue authority, thread it through both Cinnabar party-
development passes, and publish controlled-decision and fallback accounting in the completion
report. Completion fails if requested authority never executes. This closes the code-level
injection gap. One explicitly uncounted clean-power rehearsal then passed all **312 checkpoints / 36
objectives** through Hall of Fame: **114,831 controlled choices, 400 executed disagreements, zero
fallback, 1,803 development battles**, and a fully healed 60/55/55/55/55/55 party. The fixed
objective sequence remains outside the learned denominator, and the run did not launch inside the
prospective ten-root campaign envelope. See the
[clean-power rehearsal receipt](docs/evidence/training-candidate-ranker-v1-clean-power-rehearsal-2026-08-08.json).

That controller has now passed the final captured-state integration check inside the portable
objective loop. Starting from the authenticated Secret Key terminal, the model controlled all
**57,548** exposed training decisions across battle and overworld phases. The registered skill
completed **1,796 development battles / 1,074 healing trips**, defeated Blaine, finished with a
fully healed **60/55/55/55/55/55** party, and returned control to a fresh observation that opened
Giovanni. All ten authority-chain checks passed; the objective dispatch itself was a singleton and
the candidate-only training baseline remains perfect, so clean-start, branching-planner,
state-feature-value, cross-title, and end-to-end claims remain closed. See the
[portable authority receipt](docs/evidence/training-control-affordance-v6-portable-2026-08-08.json).

The next bounded dispatch is also qualified. From the authenticated post-Blaine capture, the model
selected `defeat_giovanni`; its fixed skill used **1,409 actions / 156,305 frames** to sell the
declared capacity TM, clear six exact Viridian Gym lessons while bypassing two optional trainers,
defeat Giovanni's exact party, collect TM27 and the Earth Badge, and return the full team healed.
Fresh observation opened Victory Road. See the
[post-Blaine Giovanni receipt](docs/evidence/affordance-masked-post-blaine-giovanni-2026-08-08.json).

Victory Road is now qualified from the next authenticated terminal: **3,857 actions / 453,733
frames**, the exact Route 22 rival party, seven badge gates, five Strength-switch invariants, exact
League supply reserves, and a fully healed Indigo terminal. Fresh observation opened Lorelei. See
the [Victory Road receipt](docs/evidence/affordance-masked-post-giovanni-victory-road-2026-08-08.json).

The portable loop now continues through the first four League rooms from authenticated terminals:
Lorelei **480 actions / 42,783 frames**, Bruno **328 / 32,538**, Agatha **466 / 45,854**, and Lance
**582 / 51,905**. Lorelei, Bruno, and Agatha each verify two real party roles; Lance remains an
honestly labeled single-member lesson. Each fresh observation opened the next room. See the
[Lorelei](docs/evidence/affordance-masked-post-victory-road-lorelei-2026-08-08.json),
[Bruno](docs/evidence/affordance-masked-post-lorelei-bruno-2026-08-08.json),
[Agatha](docs/evidence/affordance-masked-post-bruno-agatha-2026-08-08.json), and
[Lance](docs/evidence/affordance-masked-post-agatha-lance-2026-08-08.json) receipts.

The final dispatch defeats the Champion in **567 actions / 45,216 frames** and
reaches the Hall of Fame. Red exposes no stable state between the victory event and Hall-of-Fame
map, so the skill declares `game:hall_of_fame` as a coupled cartridge side effect rather than
inventing a second model decision. It is now qualified both independently and inside the
uninterrupted twenty-dispatch run. See the
[Champion receipt](docs/evidence/affordance-masked-post-lance-champion-2026-08-08.json).

</details>

- [Current technical handoff](HANDOFF.md)
- [Dependency-ordered roadmap](docs/roadmap.md)
- [Current capability and portfolio audit](docs/current-audit-2026-08-08.md)
- [Evidence-first project narrative](docs/project-narrative.md)
- [Potential YouTube video narrative](docs/youtube-video-narrative.md)

<details>
<summary>Historical milestone archive</summary>

> **Current status:** the deterministic teacher completes Pokémon Red from clean power-on through
> the Hall of Fame in one uninterrupted, no-save-restore emulator session while developing a real
> six-member party. Its team curriculum uses **1,716 battles** and **885 healing trips**, evolves
> Diglett, and passes the readiness gate at levels **60/55/55/55/55/55** with every member in its
> final form. The latest exact-source run verified **312/312 checkpoints**, **36/36 objectives**,
> Champion, and Hall of Fame in **539,957 actions**. This is verified deterministic-teacher
> completion—not a learned-policy or unseen-seed generalization claim. See the
> [full-route balanced-team receipt](docs/evidence/measured-balanced-team-full-route-success-2026-08-07.json)
> and the earlier
> [captured-state diagnostic](docs/evidence/measured-balanced-team-captured-state-success-2026-08-07.json).
> Whole-League instrumentation first exposed a **49/49 single-carry baseline**. Three genuine role
> lessons now replace much of that sweep. Jolteon handles Lorelei's Water core, Hitmonlee attacks
> Bruno's opening Onix, and Agatha is assigned entirely to type-advantaged specialists: Jolteon uses
> Thunder against Golbat while Dugtrio uses immediate Earthquake against both Gengar opponents,
> Haunter, and Arbok. The latest clean-power proof records **4/6 participating members**,
> `[24, 0, 4, 0, 5, 1]` decisions, and a **70.59%** whole-League busiest-member share. Agatha alone
> improves from 15 Blastoise decisions and ten healing items to a six-decision
> `[0, 0, 4, 0, 2, 0]` split with one healing item and three verified switches. This is expanding
> non-cosmetic team play, not yet a complete six-member League curriculum. See the
> [single-carry baseline](docs/evidence/measured-whole-league-participation-2026-08-07.json), the
> [qualified Bruno receipt](docs/evidence/measured-bruno-team-participation-2026-08-07.json), and the
> [qualified Lorelei receipt](docs/evidence/measured-lorelei-team-participation-2026-08-07.json), and
> the [qualified Agatha receipt](docs/evidence/measured-agatha-team-participation-2026-08-07.json).
> **August 5 collection update:** the first battle model is trained from five complete teacher
> lineages and reaches **85.8% held-out validation accuracy** across two validation lineages. Its
> sealed test partition remains unopened. Broader teacher stress then exposed a legitimate
> high-capture-cost economy lineage. The route deliberately fights two source-pinned Cinnabar
> Gym Burglars for **₽6,930** and four additional Fire-type opponents instead of depending on lucky
> captures or selling useful supplies. The exact formerly failing schedule now completes **312/312
> checkpoints**, **36/36 objectives**, all **71/71 scheduled battles**, the Champion, and Hall of
> Fame. Subsequent stress schedules exposed an unconditional Route 24 recovery and a fixed-delay
> Celadon walker loop. Both now use live game state, and the exact Celadon failure subsequently
> completed **312/312**, **36/36**, **71/71**, and Hall of Fame.
> **August 5 learned-policy update:** a shared nonlinear battle ranker now completes the same
> **312/312 checkpoints**, **36/36 objectives**, Champion, and Hall of Fame with **669 of 709**
> reported battle decisions (**94.36% coverage**), zero teacher move fallbacks, and nine shadow
> disagreements. It reaches **98.66%** unchanged validation accuracy. The route, navigation,
> objective selection, items, switching, recovery, and required-move constraints remain scripted;
> this is learned battle-move completion, not fully autonomous game completion. See the
> [nonlinear completion receipt](docs/evidence/nonlinear-battle-policy-hall-of-fame-2026-08-05.json).
> **August 5 planner update:** the authenticated semantic objective ranker now authorizes all
> **36/36 live objectives** with zero objective fallbacks before the fixed specialists execute
> them. The resulting clean-power run completed **312/312 checkpoints**, defeated the Champion,
> and entered the Hall of Fame. Mean objective confidence was **98.14%** and the minimum was
> **79.83%**. Navigation, menus, resource handling, and other bounded skills remain deterministic;
> this is learned objective dispatch, not autonomous unseen-game completion. See the
> [model-authorized objective receipt](docs/evidence/model-authorized-objective-hall-of-fame-2026-08-05.json).
> V48 remains historical; the repaired
> v49 rehearsal exposed one remaining late-corridor condition and was retired without opening a
> counted slot. The exact schedule then completed under the corrected rule. V50's first counted
> lineage exposed a lower-level-Diglett economy branch and is preserved as a failed immutable
> attempt. V51 conditionally liquidates the already-supported Bide capacity token when live cash
> plus obsolete Potions cannot fund the fixed Tunnel safety reserve; its fresh slots remain unopened.
> The first private, integrity-audited trajectory reproduced the same terminal in 4,796,436 frames
> while recording **41,330 executor actions**, **300 events**, and **14,760 deduplicated semantic
> snapshots**. The 14-action difference closes a previously uncounted menu-control path; it is not
> a route change. See the
> [sanitized trajectory-foundation receipt](docs/evidence/private-trajectory-foundation-2026-07-30.json).
> The subsequent robustness lineage has now also completed two clean-power rehearsals with the
> same **299/299 checkpoints**, **36/36 objectives**, **5,163,657 frames**, and **43,005 actions**.
> Those different totals reflect the deliberately changed route, recovery, economy, and battle
> policy documented in the [Project Narrative](docs/project-narrative.md); they do not rewrite the
> historical receipt. Broad validation passed and the source-bound collection registry was
> published at commit `58c3dbd`. Its first uncounted 63-battle schedule rehearsal exposed a
> held-out Route 25 failure at checkpoint 49/299; the campaign remains unopened and all twelve
> declared collection slots remain pending. Uncommitted diagnostic hardening now carries the same
> declared offsets through Route 25, the S.S. Anne, Vermilion, and Route 9 before stopping in Rock
> Tunnel. This is progress evidence, not a replacement qualification; see the living narrative for
> the exact distinction.
> The current robustness branch now adds a bounded, semantic Pokémon Mansion training skill. Two
> clean-power replays reproduced **301/301 checkpoints**, **36/36 objectives**, **6,581,531
> frames**, and **54,261 actions**, ending with the Champion event and Hall-of-Fame map together.
> In each run the lead trained from level 46 to 55 through 115 wild wins, 1,862 bounded encounter
> steps, five healing trips, and zero faints; it reached Indigo at level 58 and the Hall of Fame at
> level 61. This is still deterministic-teacher evidence, not a learned-policy claim.
> The balanced-team curriculum now catches Route 12 Snorlax, obtains and evolves Jolteon, clears
> all five Fighting Dojo trainers, and chooses Hitmonlee to complete its declared six-member
> roster. Its newest uninterrupted clean-power run completes **312/312 checkpoints** and **36/36
> objectives**. The zero-faint training block stops after 5,445 wins and 529 healing trips with
> every member at level 82–87, satisfying the strict five-level spread before the same lineage
> clears Giovanni, Victory Road, the Elite Four, the Champion, and Hall of Fame in **516,338
> actions**. This qualifies the deterministic six-member teacher; collection and learned-policy
> evaluation remain open. See the
> [sanitized six-member receipt](docs/evidence/qualified-play-balanced-six-2026-08-01.json).
> The active curriculum now separates **evolution readiness** from **equal-level grinding**. It
> requires the complete declared final-form roster and a level-60 Blastoise workhorse, while the
> older five-level-spread policy remains available as an optional experiment. This directly
> supports the future Pokédex curriculum and removes roughly five thousand redundant Mansion wins
> from each prospective teacher trajectory. The level-60 target is supported by an earlier
> three-member run that entered the Hall of Fame at level 61 and has now passed a clean-power
> six-member replay: **312/312 checkpoints**, **36/36 objectives**, and Hall of Fame in **87,020
> actions**. Mansion development required 177 workhorse wins plus 24 targeted evolution battles.
> A fresh source-bound 69/69 scheduled qualification is still required before collection slot
> `01` can open. Its first uncounted rehearsal reached checkpoint 75 and exposed a harbor sailor
> deadlock. A finite, coordinate-gated step-aside maneuver now lets that left/right patrol pass;
> the next rehearsal cleared that gate and exposed an obsolete Spearow weakening rule at checkpoint
> 86. Because the level-30 workhorse has no nonlethal damaging move, the capture lesson now uses a
> verified five-throw direct-capture bound. The next run caught Spearow on throw four and exposed
> the old one-throw assumption in the Rock Tunnel budget; supply planning now sells only the
> observed obsolete-Potion shortfall. All twelve counted v8 slots remain unopened while the exact
> source requalifies. That funded replay reached Safari checkpoint 194 and taught Surf correctly;
> its stale gate expected unrelated moves to have maximum PP immediately after teaching. The lesson
> now proves observed PP preservation at the HM boundary. The following replay exposed that the
> later nurse loop stopped on already-full HP before restoring PP; it now requires the complete
> post-Surf PP vector before calling the Center recovery finished. The fully restored replay then
> reached Lance at checkpoint 308, where a forced-switch helper rejected a valid slot-4 party
> cursor inherited from the old three-member route. Cursor validation now uses the live party size.
> The repaired switch defeated Lance but exposed three helper sacrifices against two Revives;
> helper pivots now stop at the declared two-Revive budget and later recovery heals Blastoise.
> That repaired v8 source qualified at **312/312 checkpoints**, **36/36 objectives**, **68/68
> scheduled battles**, and Hall of Fame. Its first immutable training run then failed honestly at
> checkpoint 90: variable capture spending left TM28 above the bag cursor, while the selector could
> only move downward. V8 is retired with that artifact preserved and eleven slots unopened. The
> v9 teacher navigates the absolute bag index in either direction, uses exposed seed `18001` only
> for its uncounted rehearsal, and reserves fresh counted seeds beginning at `19001`.
> Its first rehearsal proved that fix through checkpoint 91, then a third Rock Tunnel paralysis
> exhausted the historical two-cure allowance. Tunnel preparation and Lavender replenishment now
> carry three cures in the same bag stack; that failed rehearsal remained uncounted.
> V9 subsequently qualified its full 312/36/68 Hall-of-Fame rehearsal, but fresh counted seed
> `19001` encountered a high-level Dugtrio during pre-ship training and fainted before attacking.
> That root is preserved and v9 is retired. V10 flees the evolved cave ambush while training only
> on safe Diglett, rehearses on exposed seed `19001`, and reserves fresh counted seeds at `20001+`.
> Its first rehearsal passed the Dugtrio branch, then exposed an off-by-one policy replan after the
> final allowed cocoon-weakening hit. V10 now replans once at the same attack cap before throwing.
> The following replay reached Route 9, where Wrap fainted DUX after its required Peck. The shared
> trainer controller now continues through the verified party menu with a living teammate.
> Its first handoff exposed forced-party dialogue rather than a normal voluntary switch; the shared
> primitive now observes and handles both menu paths separately.
> The repaired handoff defeated the opponent, then exposed a stale fainted-lead HP view during the
> final-KO transition. Terminal enemy-zero evidence now settles before the nonterminal faint gate.
> The completionist foundation now defines an auditable **124-registration** Red-only target and names
> all **27** exclusions imposed by a one-save, no-link-cable Squirtle/Helix/Hitmonlee/Jolteon run.
> It reads the cartridge's seen/owned Pokédex flags and performs a checksum-verified census of the
> party and all twelve PC boxes through a bounded read-only port. Registration, living retention,
> and level 100 remain separate gates. Because unique Squirtle, Eevee, and Helix Fossil evolutions
> consume four earlier forms, the honest maximum is **120 simultaneously living level-100
> species**, not 124. Exact deposit, withdraw, and verified switch-box execution now exist;
> a source-pinned catalog now covers all **124 registrations** through **102 direct methods** and
> **22 transformations**, derives the necessary duplicate precursors and evolution-item budget,
> and drives a bounded semantic area-survey loop. Map-specific live execution beyond the already
> qualified gifts, trades, captures, evolution, and storage actions remains future work. The first
> uninterrupted Hall-of-Fame census measured
> **12 owned, 85 seen, 7 living, and 0 at level 100**, with all twelve boxes verified; see the
> [sanitized collection-census receipt](docs/evidence/qualified-play-collection-census-2026-08-01.json).
> The corrected perfect-save foundation has now passed a newer uninterrupted clean-power replay:
> **312/312 checkpoints**, **36/36 objectives**, and a zero-faint six-member gate after **6,493
> wins**, with levels **88–93**. The route initialized PC storage, completed and reversed a box
> switch without losing Zubat, verified all twelve boxes, and entered the Hall of Fame. Its honest
> terminal census is **12/124 registered, 7/120 living, and 0/120 at level 100**. This qualifies
> the storage and contract foundation—not the still-unbuilt acquisition or learned-policy claims.
> See the [sanitized perfect-save foundation receipt](docs/evidence/qualified-play-perfect-save-foundation-2026-08-01.json).
> The first live acquisition slice is now qualified as well. The teacher crosses Diglett's Cave
> and Route 2, catches Route 1 Pidgey and Rattata through ordinary encounters, verifies their
> Pokédex flags, deposits both exact specimens, returns to the Lt. Surge route, and completes the
> same **312/312 checkpoints** and Hall-of-Fame gate. The uninterrupted run used **758,430
> actions**, passed the zero-faint six-member gate at levels **77–82**, and finished with
> **14/124 registered, 9/120 living, and 0/120 at level 100**. This is one complete acquisition
> slice, not a claim that the remaining collection or learned agent is finished. See the
> [sanitized Route 1 receipt](docs/evidence/qualified-play-route1-acquisition-2026-08-02.json).
> Route 1 now runs through the same reusable semantic source-survey controller as the game-neutral
> planner rather than a chapter-local target loop. The live adapter reads the Pokédex, full party,
> and all twelve verified boxes; preserves a declared capture order when deterministic downstream
> storage requires one; and proves bounded seek, capture, flee, progress, and endpoint-normalization
> behavior. A new route-agnostic priority view counts duplicate root specimens required by later
> evolutions. The refactored lineage reproduced the exact **83,835,201 frames** and **758,430
> actions** and passed the complete private integration contract. See the
> [sanitized reusable-source receipt](docs/evidence/qualified-play-reusable-wild-source-2026-08-02.json).
> The same reusable controller now also surveys Viridian Forest, retaining Caterpie, two Metapod,
> two Kakuna, and Pikachu before returning to the story route. Two independent clean-power replays
> reproduced **312/312 checkpoints**, **36/36 objectives**, **83,619,428 frames**, and **765,088
> actions** through the Hall of Fame. The terminal census is **18/124 registered, 13/120 distinct
> living species, and 0/120 at level 100**, with nine specimens in Box 1 and the six-member story
> party intact. Fifteen specimens are physically retained; the duplicate Metapod and Kakuna roots
> intentionally do not inflate the distinct-species count. This qualifies the Forest source, not
> the remaining collection or a learned completion agent. See the
> [sanitized Viridian Forest receipt](docs/evidence/qualified-play-viridian-forest-2026-08-02.json).
> A first slot-equivariant battle ranker now reaches **72.5% teacher-choice agreement** versus a
> **50.5% fold-local majority baseline** across 422 decisions; its hard legality and PP mask keeps
> every output valid by construction. This is a grouped diagnostic from one lineage, not a learned
> gameplay rollout or held-out result. See the
> [sanitized battle-imitation receipt](docs/evidence/private-battle-imitation-diagnostic-2026-07-30.json).
> The formal v3 teacher rehearsal subsequently completed **312/312 checkpoints**, **36/36
> objectives**, and **68/68 scheduled battles**, with a balanced level **75–81** party and Hall of
> Fame verification. Its first immutable training root then failed honestly at Route 24 trainer 2:
> accuracy loss produced repeated Water Gun misses while poison and enemy attacks fainted
> Wartortle with 4 enemy HP remaining. V3 is retired rather than rerun. V4 subsequently qualified
> its full 312-checkpoint/68-battle rehearsal, but its immutable first training root fainted at the
> final Route 24 bridge trainer. V4 is preserved and retired. V5 subsequently qualified its full
> 312-checkpoint/68-battle rehearsal, but its immutable first training root failed at the S.S. Anne
> rival. V5 remains preserved and retired. V6 then qualified its complete 312-checkpoint,
> 68-battle rehearsal, but immutable train slot 01 exposed a safe full-HP Cerulean outcome that
> retained five Potions while the route required exactly four. V6 remains failed and retired. The
> v8 teacher carried a bounded four-to-seven Potion reserve across the following chapters and
> qualified its rehearsal before the bidirectional-bag defect retired its first counted root. V9
> uses that exposed v8 seed only for an uncounted rehearsal and preregisters twelve fresh counted
> seeds. At that historical stage, V9 still required qualification and no learned model had yet
> completed the game.

</details>

## The goal

Reach the Hall of Fame from clean power-on with:

- a fingerprinted Pokémon Red ROM supplied privately by the user;
- frozen source, configuration, objective graph, and model weights;
- no human controller input;
- no save-state restoration during evaluation;
- no online code or prompt modification; and
- concurrent Champion-event and Hall-of-Fame verification.

Training may use walkthrough knowledge, read-only game state, demonstrations, private snapshots,
teacher corrections, and local reinforcement learning. Those resources are disclosed rather than
presented as learning from nothing.

The ambition beyond this first contract is deliberately larger: finish each supported Pokémon
title, satisfy its published perfect-save contract, and train every specimen that can coexist in
that save to level 100. A separate multi-lineage portfolio combines versions, starters, fossils,
branches, and supported trades toward the broader all-species goal. Unsupported online services,
expired events, and unavailable distributions stay visible as exclusions instead of being hidden
behind the phrase “100%."

## Why this project exists

The predecessor, [Pokémon Red AI](https://github.com/PeteAndrews1289/pokemon-red-ai), processed
8.24 million self-generated actions and discovered seven milestones, but finished frozen
evaluation with zero durable skills. Its result was that discovery and training activity did not
become cumulative competence.

This successor changes the objective and architecture:

1. make reliable game completion the primary target;
2. represent the known long-horizon route explicitly;
3. use deterministic solutions for pathfinding, menus, and verification;
4. train bounded specialists where learned decisions are valuable; and
5. replace teacher components only after learned alternatives pass frozen reliability gates.

For the full engineering story—including what the completed run established, which assumptions
failed under changed lineages, how those failures became reusable capabilities, and what remains
unproven—see the [Project Narrative](docs/project-narrative.md).

## Architecture

```mermaid
flowchart LR
    Game["PyBoy + private ROM"] --> State["Validated semantic state"]
    State --> Planner["Learned objective ranker"]
    Planner --> Skills["Affordance-masked bounded skills"]
    Skills --> Strategy["Learned trainee / venue ranker"]
    Skills --> Control["Learned training-action controller"]
    Skills --> Mechanics["Fixed navigation, menus, recovery"]
    Strategy --> Mechanics
    Control --> Mechanics
    Mechanics --> Executor["Sole frame-safe executor"]
    Executor --> Game
    State --> Referee["Independent completion + safety referee"]
    Planner --> Evidence["Authenticated authority receipts"]
    Strategy --> Evidence
    Control --> Evidence
    Referee --> Evidence
```

The diagram is also the claim boundary: learned policies choose objectives and bounded training
decisions; fixed skills still perform most Red-specific navigation, dialogue, inventory, recovery,
and battle mechanics. The referee independently reobserves effects instead of trusting the actor.

See [Architecture](docs/architecture.md), the
[Completion Contract](docs/completion-contract.md), and the
[Assistance Policy](docs/assistance-policy.md).

## Planned training ladder

1. A deterministic teacher completes three clean runs.
2. Teacher trajectories train goal-conditioned specialists with behavioral cloning.
3. DAgger adds corrections from states caused by the learner's own mistakes.
4. Snapshot curriculum RL is used only for skills that remain below their reliability gates.
5. Teacher fallback is removed one specialist at a time.
6. A distilled local macro-policy attempts the full game.

Each stage retains its complete success and failure denominator. Hybrid completion, learned-module
completion, learned-stack completion, and distilled-model completion are separate claims.

## Does it need a completed run?

Not to begin. The deterministic teacher is built chapter-by-chapter from disclosed route knowledge,
verified maps and state, and closed-loop objective checks. This project requires a full teacher
completion before training or evaluating full-game composition.

A single completed video or button trace would help with route review, but it would not teach
recovery from mistakes. Behavioral cloning needs action-aligned demonstrations; DAgger needs a
queryable teacher that can correct states the learner actually reaches. See the
[Teaching and Data Plan](docs/teaching-plan.md).

## Public verification

The default checks require no ROM:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

python scripts/check_public_artifacts.py
python scripts/check_docs.py
ruff check .
pytest -m "not integration"
```

Battle-learning development additionally uses the optional NumPy dependency:

```bash
python -m pip install -e ".[dev,learning]"
```

## Private emulator setup

PyBoy integration is optional so public tests remain redistribution-safe:

```bash
python -m pip install -e ".[dev,emulator]"
export POKEMON_RED_ROM="/absolute/path/to/Pokemon Red.gb"

pokemon-red-completion doctor
pokemon-red-completion bootstrap
pokemon-red-completion opening
pokemon-red-completion opening --watch --speed 4
pokemon-red-completion play
pokemon-red-completion play --watch --speed 4

# Deploy an authenticated battle model and retain live teacher interventions:
pokemon-red-completion play \
  --battle-model /absolute/private/model-artifact/model.jsonl \
  --battle-corrections-root /absolute/private/trajectory-directory

# Strict evaluation: execute the model without querying the teacher or collecting labels:
pokemon-red-completion play \
  --battle-model /absolute/private/model-artifact/model.jsonl \
  --allow-model-disagreement \
  --require-teacher-free-battle

# One-time setup for an existing directory on a separate private volume:
pokemon-red-completion private-data init --private-root /absolute/private/trajectory-directory

# Record one full teacher episode there:
pokemon-red-completion record --private-root /absolute/private/trajectory-directory

# After the exact source/config commit is committed and pushed, run the required
# unassigned, non-counted 74-battle schedule rehearsal before slot 01:
pokemon-red-completion record \
  --private-root /absolute/private/trajectory-directory \
  --schedule-dry-run

# Before freezing another campaign, fuzz arbitrary uncounted timing schedules:
pokemon-red-completion record \
  --private-root /absolute/private/trajectory-directory \
  --diagnostic-schedule-seed 61001

# Only after that rehearsal succeeds, consume one declared training slot:
pokemon-red-completion record \
  --private-root /absolute/private/trajectory-directory \
  --collection-run red-battle-v95-01-train

# Fit the first whole-game objective ranker from one completed labeled episode.
# This lane is explicitly diagnostic until separate train/validation lineages exist:
pokemon-red-completion learn planner train \
  --private-root /absolute/private/trajectory-directory \
  --episode-id COMPLETE_EPISODE_ID \
  --diagnostic

# Require the sealed planner to authorize every live objective before the
# corresponding deterministic specialist may run:
pokemon-red-completion play \
  --objective-model /absolute/private/red-objective-planner-artifact

# After all five train and two validation roots complete, fit without opening test:
pokemon-red-completion learn battle fit \
  --private-root /absolute/private/trajectory-directory

# Refit with one completed correction artifact. Supply the original five train
# episode IDs and two validation episode IDs with repeated arguments:
pokemon-red-completion learn battle correct \
  --private-root /absolute/private/trajectory-directory \
  --base-model /absolute/private/model-artifact/model.jsonl \
  --corrections /absolute/private/correction-artifact \
  --train-episode TRAIN_EPISODE_1 --train-episode TRAIN_EPISODE_2 \
  --train-episode TRAIN_EPISODE_3 --train-episode TRAIN_EPISODE_4 \
  --train-episode TRAIN_EPISODE_5 \
  --validation-episode VALIDATION_EPISODE_1 \
  --validation-episode VALIDATION_EPISODE_2

# Inspect all twelve slots and reconcile a power-loss partial without starting a run:
pokemon-red-completion collection status \
  --private-root /absolute/private/trajectory-directory
```

`bootstrap` starts PyBoy headlessly from immutable verified ROM bytes, disables human window input,
loads no adjacent save data, reaches the bedroom with the built-in RED/BLUE names, verifies one
movement action, and exits without saving. Its JSON report contains hashes and semantic evidence,
not the ROM path or game assets.

`opening` runs the bounded teacher through six closed-loop checkpoints: bedroom input, downstairs,
outside, Oak's trigger, starter-selection readiness, and verified Squirtle. It is headless and
uncapped by default. `--watch --speed 4` instead opens a local PyBoy window at 4× speed and prints
checkpoint progress before the final JSON report. Watch mode changes presentation only: keyboard
input remains disabled, while the window itself stays responsive and can be closed with Escape or
its red close button. The same semantic gates choose every action, and the emulator still exits
without saving.

`play` is the recommended continuous command. It uses one clean emulator session for the opening,
the verified rival win, both Route 1 crossings, the parcel handoff, Viridian Forest, Brock, Route
3, Mt. Moon, Cerulean City, Nugget Bridge, Bill, Misty, Route 5, the Underground Path, Route 6,
Vermilion City, the S.S. Anne through HM01, Vermilion Gym through the Thunder Badge, Route 9,
Rock Tunnel, Lavender Town, Route 8, the west-east Underground Path, Route 7, and Celadon City.
It then reveals and clears the Rocket Hideout, defeats Giovanni, obtains the Silph Scope, crosses
Pokémon Tower, calms Marowak, rescues Mr. Fuji, receives the Poké Flute, and heals in Lavender
Center. It then wakes and catches the level-30 Route 12 Snorlax with a bounded Great Ball/Poké Ball
policy, clears the four mandatory Route 12/13 trainers, bypasses every other Route 12–15 trainer
and progression pickup, and heals the complete party in Fuchsia Center.
It then returns to Celadon, defeats Erika, buys exactly one Fresh Water on the Department Store
roof, proves the guard consumes it before the global Saffron-access flag is set, crosses the
Route 7 gate without battle, and heals in Saffron Center.
It then buys a bounded recovery reserve, obtains and teaches TM13 Ice Beam, enters Silph Co.,
obtains the Card Key, clears the required warp route and trainers, defeats the rival and Giovanni,
receives the Master Ball, leaves optional Lapras untouched, and returns to a healed Saffron
Center boundary.
It then follows a live-qualified trainer-free Saffron Gym warp route, defeats Sabrina with a
physical Strength and Ice Beam policy, verifies TM46 plus both Marsh Badge lanes, and heals.
It then obtains HM02 Fly, reaches Cinnabar by way of Pallet and Route 21, traverses Pokémon
Mansion with one Max Repel and no trainer battles, recovers the Secret Key, clears all six Gym
quizzes without a regular-trainer battle, defeats Blaine with Surf, receives TM38 plus both
Volcano Badge lanes, and returns to a healed Cinnabar Center.
It then flies to Viridian, frees one bag slot by selling TM46, solves the spinner floor, clears
the six route-gating trainers with Strength and Ice Beam, heals before the leader, defeats
Giovanni with Surf, verifies TM27, both Earth Badge lanes, and both Route 22 rival events, then
returns to a healed Viridian Center with all eight badges.
It then teaches Toxic, prepares a bounded Saffron recovery and repel reserve, defeats the final
Route 22 rival with state-aware healing, verifies all seven remaining Route 23 badge checks,
solves every Strength boulder and switch in Victory Road, reaches Indigo Plateau, heals, and buys
the declared Full Restore, Full Heal, Hyper Potion, X Special, and Max Repel reserve.
It then defeats Lorelei, Bruno, Agatha, Lance, and the Champion, enters the Hall of Fame, and
reports completion only when the Champion event and Hall-of-Fame map are simultaneously true.
The League contract protects two Full Restores across Lance for the Champion, including the final
Venusaur contingency, rather than compensating for resource variance with additional workhorse
grinding.
The forest
segment deliberately trains against three verified Kakuna encounters and one mandatory Bug
Catcher. Later gates require the declared trainer identities and event order, Bill's complete
transformation and S.S. Ticket sequence, the mandatory Cerulean Gym trainer, Misty's live trainer
identity, the Cerulean Rocket thief and TM28, and both required lower Route 6 trainers. A bounded
heal-and-replay recovery explicitly records and flees three exact Route 6 Pidgey encounters while
proving unchanged PP and trainer events. The S.S. Anne chapter verifies the required RIVAL2
identity, stages the workhorse to level 30 through a bounded Diglett's Cave training receipt,
records a live win, the Captain's rub event, the separate HM01 event, HM01 inventory presence,
and the derived Cut fact. The Surge chapter buys bounded capture and recovery supplies, captures
Spearow and a source-valid Diglett, trades for DUX, teaches Cut and Dig when needed, adapts to the
live Gym switch pair, and verifies a Dig-only Surge win plus TM24 and mirrored badge evidence.
The Lavender chapter teaches BubbleBeam, purchases an exact recovery reserve, proves all 11
required Route 9/Rock Tunnel trainer identities and PP decrements, retries a movement step only
after a qualified wild flee, bypasses the optional south Route 10 trainer, and heals the complete
three-Pokémon party in Lavender Center.
The Celadon chapter bypasses eight optional Route 8 trainers, proves the single required Lass
identity and event transition with selected-move PP evidence, preserves the exact recovery
inventory, and heals the complete party in Celadon Center. After the later qualified Tower
evolution, the exact route ends with a full-health, status-free Blastoise restored as party lead.
The Hideout chapter proves five exact trainer identities, bypasses all eight optional basement
trainers, verifies the poster switch, Lift Key, elevator floor, boss-door, Giovanni, and Silph
Scope gates, and explicitly records the pinned source's known `EVENT_ENTERED_ROCKET_HIDEOUT`
callback bug without weakening any required event.
The Tower chapter proves the exact scripted rival, five required Channelers, level-30 Marowak,
and three Rocket identities; bypasses eight optional Channelers; verifies all three purified-zone
heals, both blocking item pickups, the mirrored and world Fuji rescue events, and the Poké Flute;
and qualifies the natural Wartortle-to-Blastoise evolution without changing party order or moves.
Its adaptive battle and navigation selection reacts to bounded state, but the
three-run result evaluates one frozen teacher route and does not yet show held-out timing or RNG
generalization.
The Fuchsia chapter verifies the Poké Flute wake transition, exact Snorlax species and level,
capture, party growth, event transition, removed-object tile, and retained Flute; records five
exact battle PP receipts;
performs a disclosed resource-neutral Lavender Center recovery; flees four bounded wild
encounters; and proves 35 optional events plus five optional items remain untouched.

The ROM, saves, snapshots, recordings, datasets, and model checkpoints are ignored and must remain
outside Git. The visible window is not recorded or uploaded by the project. The supported revision
is identified by public hashes in the source; reports omit the private ROM path, and no game data
is distributed.

`private-data init` deliberately requires an existing directory on a separately mounted volume.
It places a tamper-evident sentinel there but never creates a missing mount point. `record` refuses
uninitialized, same-device, symlinked, Git-controlled, or overlapping destinations. It also
requires an identified, clean Git checkout so every accepted episode names the exact source
commit. Output contains only a path-free episode identifier and aggregate summary. The first
recorder is an executor-aligned teacher trace. The next layer records zero-based battle move
decisions from the shared adaptive runtime and links their full execution spans. The first
single-lineage battle-imitation diagnostic groups 422 decisions into 63 encounter proxies and
reaches 72.5% teacher-choice agreement versus a 50.5% fold-local majority-slot baseline. A hard
legality and PP mask makes all outputs valid by construction; that safety invariant is not a
learned success metric. This is not battle win rate or a learned gameplay rollout.

New recordings bind each adaptive decision to an explicit physical battle instance, one of 71
stable public battle-plan identities, planner objective, win goal, and required-move policy. The
current `pokemon.core.battle.move-ranker.v2` schema adds
`constraint.matches_required_move`; receipts report free-choice and forced-choice accuracy
separately so constraint-following cannot be mistaken for autonomous move selection. The recorded
teacher recovery marker is descriptive only, is not a model feature, and does not yet encode a
typed recovery budget.

The committed collection protocol preregisters twelve immutable one-attempt root-lineage
slots—five train, two validation, and five test—with partition-local ordinals and a different
71-battle timing schedule for each. The exact source/configuration commit must be committed and
pushed before collection. A registry-declared, unassigned, non-counted dry run must then attest all
71 schedule applications before slot `01`. Counted runs emit per-battle and terminal schedule
attestations; a private campaign seal and outcome ledger preserve every success, failure,
interruption, and invalid result. An interruption consumes its slot rather than authorizing a
rerun. The successful rehearsal produces an immutable private qualification that every counted
run reopens and audits before it can seal the campaign or create an episode. That episode start is
synchronously persisted before play, so a shutdown cannot erase a one-shot attempt claim.
Policy-visible semantic overlap across partitions is disclosed but is not hard leakage by
itself; copied identities, manifests, assignments, schedules, or lineages are.

The first Forest-lineage rehearsal exposed a moving-NPC collision at the Route 24 entrance at
checkpoint 38/312. The repaired crossing then passed clean-power qualification and cleared the
former failure under the same rehearsal schedule. That second rehearsal reached checkpoint
109/312 before a final Rock Tunnel trapping sequence crossed the battle policy's 40-HP recovery
gate and fainted the lead. Neither rehearsal qualified or consumed a declared slot. Subsequent
clean diagnostics hardened the tunnel with type-aware attacks and a prepared DUX sleep pivot,
removed a wasteful Tower top-off, broke an Alakazam healing loop, and excluded two-turn Fly from
the one-turn Mansion grinding policy. The combined source then passed an uninterrupted clean-power
replay at **312/312 checkpoints**, entering the Hall of Fame after **84,632,189 frames**. It was
then committed, pushed, and bound to a regenerated registry before the rehearsal was retried.
All twelve slots remain pending and the test partition remains unopened, so there is still no
held-out or promoted-policy result.

The first rehearsal of that published source cleared the former Route 24 and Route 25 failures,
then stopped at checkpoint 109/312 when Bellsprout began Wrap with 20/57 HP and trapped Wartortle
until it fainted. A later published candidate cleared that matchup but its uncounted rehearsal
stopped when an unsafe low-HP DUX finisher fainted in the tunnel; neither failure consumed a
campaign slot. The current teacher removes that finisher, budgets the tunnel's healing reserve,
uses type-aware Bite after required Slowpoke evidence, escapes a status-locked DUX to the healthy
story lead, accepts natural evolution without falsely requiring candy consumption, and uses any
surplus Rare Candy at the level-41 lesson boundary. It also releases movement input around moving
Celadon NPCs and uses Ice Beam plus bounded recovery against the Silph rival. The next uncounted
rehearsal proved the DUX escape but then put replacement Blastoise to sleep and fainted it because
battle healing targeted only party slot one. The current teacher buys one additional Awakening in
Vermilion, preserves one for Tower, cures the actual active party member, and targets Super Potions
to that same live party index under a two-use cap. This exact source passed a new uninterrupted
**312/312-checkpoint**, **36/36-objective** clean-power replay through the Hall of Fame in
**771,022 actions**. Its Mansion curriculum exceeded **4,000 battles** with a six-member minimum
level of **77** and a five-level spread. The regenerated source identity is the next uncounted
rehearsal candidate. That rehearsal cleared all nine tunnel trainers, then exposed a $200
schedule-specific recovery shortfall during the Lavender restock. The current teacher legally
liquidates the already-proven, unused TM28 for $1,000 before restoring the full downstream safety
reserve. That correction carried the rehearsal to checkpoint 202/312, where Juggler 4 exposed a
low-HP lead assumption. The current policy protects the story lead by handing the finish to the
healthiest living reserve and choosing from that reserve's own legal moves. All twelve counted
slots remain pending. That repair reached checkpoint 261/312, where an attempted Sabrina Hyper
Potion outlasted the shared routine's 24-frame menu-settling window. Battle-item recovery now uses
a bounded 720-frame, cancel-safe observation window that cannot accidentally re-enter ITEM. That
repair passed Sabrina and reached the balanced-team curriculum, where a member eventually lost
every usable preferred attack to PP exhaustion or Disable. The trainer now pivots through the safe
escort, flees, and lets the game-neutral planner schedule restoration instead of forcing a move.
That repair completed the entire scheduled rehearsal at **312/312 checkpoints**, defeated the
Champion, and entered the Hall of Fame. Promotion then failed closed because the 4,000-battle wild
curriculum had no explicit training intent and repeated progress reports reused one event identity.
The recorder retained roughly **848,000 records / 506 MB**, the failed run consumed no slot, and
the current source gives every wild-training decision a portable objective, assigns each physical
battle its own lifecycle, and keys repeated progress events to their execution step.
The next exact-source rehearsal again completed **312/312 checkpoints** and Hall of Fame. It
accepted 4,789 move labels and every lifecycle/progress event, reducing the remaining rejection to
209 early switch-training decisions. Those decisions selected Blastoise's move after a weak field
lead switched out, while the semantic snapshot still described the field lead. Battle snapshots
now describe the currently controlled battler during combat and the field lead outside combat,
which makes switch training truthful and portable. The second failed rehearsal also consumed no
slot. The corrected source then passed the complete scheduled rehearsal at **312/312 checkpoints**,
**36/36 objectives**, and Hall of Fame, promoting **4,998 decisions** and **870,460 total records**
with all 68 scheduled-battle attestations intact. The first genuinely held-out v1 training run then
failed honestly at checkpoint 41 when a poisoned 17/54-HP Wartortle was trapped by Ekans's Wrap;
that one-shot outcome remains sealed and v1 cannot be used for fitting. Moving the already-planned
Route 24 Center recovery before that trainer cleared the exact exposed schedule through the next
checkpoint. A separately identified v2 campaign now preregisters fresh train, validation, test,
and rehearsal seeds; it must pass its own uncounted full rehearsal before any v2 slot is consumed.
The first v2 rehearsal reached checkpoint 70 before a walking Cerulean NPC occupied the Route 6
healing-replay corridor. That uncounted artifact is retained. A bounded yield-and-retry maneuver
then cleared the exact exposed schedule through checkpoint 71; v2 remains unopened with all twelve
counted roots untouched pending a new full rehearsal. That replay then reached checkpoint 91 and
exposed a second uncounted stress case: the six-capture Viridian Forest curriculum exhausted its
25-ball budget on Pikachu. The legal early-game reserve is now 30, with the later bounded cleanup
gate updated to match; the larger purchase must prove both capture and downstream economy in the
next full rehearsal. Its added purchase timing shifted the Route 11 encounter stream and exposed
the old 72-encounter Spearow search cap. A source-specific 96-encounter cap now retains the exact
level-17 Spearow requirement without loosening any other encounter bound.
That rehearsal then cleared the Forest and Route 11 curricula and reached Lt. Surge. Diglett
finished the first opponent at 10/30 HP but was knocked out before its next Dig. The teacher now
uses its reserved Super Potion from a strictly proven low-HP battle-menu state, verifies the heal
and inventory change, and resumes the Dig-only plan. The counted v2 campaign remains pristine while
the repaired teacher awaits another complete rehearsal.
The next exact replay proved the recovery and Dig-only win through the complete Surge chapter. It
then exposed a stale Lavender entrance assumption that required the reserved potion to remain in
the bag. The handoff now accepts the proven zero-or-one outcome and retains the later exact
money-and-inventory proof when topping up to the fixed twelve-potion reserve.
The following replay reached checkpoint 102 and exposed the associated ₽700 replacement cost. Its
intermediate repair retained the planned allocation while the evidence
report records the observed starting reserve and proves exact potion conservation. The later TM28
sale funds any required Lavender top-up, preserving the fixed downstream reserve.
The 30-ball curriculum also displaced the ₽1,400 required for four Rock Tunnel Repels. The tunnel
allocation is now ten Super Potions—twice the proven five-potion Route 9 floor—plus all four Repels,
with the unchanged Lavender top-up restoring twelve for downstream chapters.
The next rehearsal proved that repair through Rock Tunnel and reached Celadon Gym at checkpoint
220. It also revealed that Koga's terminal mutual-KO recovery completed the game battle outside the
adaptive loop without closing its schedule entry. Externally settled trainer exits now close the
matching applied schedule entry exactly once before the next planned battle.
That repair then passed Erika and reached checkpoint 230, where a moving department-store customer
blocked the evolution-stone clerk aisle. The route now uses a bounded eastward yield maneuver and
proves it returns to the exact approach coordinate before continuing.
The repaired route then reached Silph Co. checkpoint 243, where the rival knocked out Blastoise
with 17 HP left on its active Pokémon. The teacher now selects the healthiest living reserve from
the forced-switch menu and continues from that battler's real move PP, adding a concrete full-team
recovery lesson instead of relying exclusively on the lead.
The first replay reached that branch and exposed Gen I's faint dialogue before the party cursor.
The selector now periodically advances only that bounded dialogue while continuing to verify the
living reserve cursor and the eventual return to the battle's main menu.
The following replay exposed the terminal variant where the rival's final Pokémon also reached zero
HP. The teacher now accepts a proven post-selection battle exit for that mutual knockout and closes
the exact Silph schedule entry, while ordinary knockouts still require a restored main menu.
That repair proved checkpoint 244, then exposed lingering post-rival text before the elevator route.
Terminal recovery now requires two consecutive field-control observations before issuing movement,
the same completion gate used by ordinary adaptive battles.
The current uncounted v10 rehearsal subsequently cleared the hardened Route 9 continuation and
reached Koga at checkpoint 205/312. When the workhorse fainted with a living opponent and trained
teammates still available, the boss adapter stopped on its old single-carry assumption. It now
selects the healthiest living teammate through the verified forced-party menu, resumes from that
member's own legal moves and PP under a party-depth bound, and records the handoff separately from
mutual-KO recovery. Collection remains closed until the exact republished source passes the full
312-checkpoint and 69-schedule rehearsal.
That replay defeated Koga and fully healed the party, then exposed a different downstream effect:
Blastoise reached level 42 against Muk and naturally learned Skull Bash over Bite before the
curriculum's controlled TM40 lesson. Koga now assigns Muk to the healthiest living teammate before
Blastoise attacks, preserving the staged move lesson while avoiding the faint proactively. The
uncounted run stopped at 208/312; all counted v10 roots remain untouched.
The next run made the Muk handoff, but the reserve later fainted and Blastoise returned to finish at
14 HP, so level 42 could still be reached legally. The teacher now supports both exact capability
paths: preserve Bite and teach TM40 later, or retain naturally learned Skull Bash and archive the
redundant TM40. Strength and Erika verify the appropriate move/PP lineage and converge on the same
terminal move set; the unchanged Center proof restores the whole party. No counted root was opened.
The combined v10 source then qualified at **312/312 checkpoints**, **36/36 objectives**, Hall of
Fame, and **68/68** schedule attestations. Its first fresh counted seed (`20001`) failed honestly at
Misty: Wartortle was still the only party member and fainted before a finishing hit with Starmie at
10/59 HP. V10 is retired with that root sealed. V11 qualified but its first immutable training run
found a moving Cerulean Mart customer blocking the repeat clerk stance, so v11 is also retired.
V12 rehearses that exposed `21001` seed, reserves fresh counted seeds at `22001+`, and may spend only Misty's Potion surplus above the exact
four-Potion Rocket reserve from a verified low-HP battle state.
Its first uncounted replay cleared the repaired Mart and reached the level-17 Spearow lesson at
checkpoint 86, where capture settling consumed two Poké Balls inside one requested throw. The
dialogue loop now advances with the non-selecting B button so crossing an unobserved battle-menu
boundary cannot issue a second item command.
That repair passed the capture, Diglett, trade, Cut, and Dig gates through checkpoint 91. The
following Route 1 survey then met the source-defined horizontal youngster on the only northbound
tile at `(14, 14)`. The survey now uses a finite eastward yield, restores the exact approach, and
retries north without consuming the route step or weakening any encounter/capture bound.
The next replay proved that crossing and reached the Rock Tunnel supply gate at checkpoint 102.
Worst-case early capture spending left a ₽2,109 shortfall, beyond the five obsolete Potions still
held. The teacher now earns a source-exact ₽1,260 from one bounded Route 11 Gambler battle and sells
the unused TM24 for ₽1,000 at the point liquidity is needed. That battle is the 69th scheduled
identity, turning resource acquisition into explicit training evidence instead of assuming lucky
Ball resale or cutting the ten-Super-Potion Tunnel reserve.

The latest uncounted v38 stress replay cleared the repaired Cerulean, S.S. Anne, and Route 11
branches and passed checkpoint 91, then reached the final required Viridian Forest species with no
Poké Balls remaining. Its trace showed the deeper cause: Route 1's newly caught Pidgey and Rattata
entered the six-capture survey without a source-boundary recovery, leaving too little safe low-power
HP and PP for the cocoon weakening curriculum. The teacher now visits Viridian Center, proves the
whole party healthy and both 35-PP helper moves restored, returns to the exact boundary, and only
then begins the Forest survey. The attempt remains diagnostic-only; no v38 counted root is open.
That repair completed the Forest, but the Center visit correctly changed Dig's return anchor from
Vermilion to Viridian. The handoff now proves that actual field-move consequence, then uses the same
bounded, encounter-safe Route 2 approach and replays the exact proven Diglett's Cave path in reverse
to regain Vermilion before storage. The shortcut is no longer allowed to assume an obsolete healing
anchor or rediscover a static corridor from the wrong entrance orientation.
The inverse-path replay then passed every chapter through the Champion at checkpoint 311. With all
five Blizzard PP still reserved, the six-boost workhorse used Strength against Pidgeot, left it at
57 HP, and was knocked out before a second attack; five Full Restores could not revive it. The
matchup policy now spends one X-Accuracy-backed, six-boost Blizzard on that dangerous fast opener.
Four Ice PP remain—twice the observed two-hit Venusaur requirement—so the change reallocates an
existing combat resource instead of adding grinding, items, retries, or sacrificial teammates.
That replay confirmed the new opener swept Pidgeot and the next four opponents, but exposed the
remaining obsolete sacrifice tactic at Venusaur. Two helper pivots erased all six X Special stages
under Gen I switch rules; Blizzard damage fell to 64–65 while Venusaur recovered, and the helpers
fainted. Champion healing is now direct: Full Restore preserves the boosted workhorse's stat stages
and the developed teammates, aligning the final battle with the balanced-party curriculum.
That source subsequently completed both the exposed diagnostic and the official clean-power
qualification at 312/312 checkpoints, 36/36 objectives, and 69/69 scheduled battle attestations.
The first immutable v38 training root then exposed the fifth-floor Celadon customer from the
opposite direction: after buying X Specials, the player at `(13,2)` could not cross the occupied
`(14,2)` tile on the return route. V38 is sealed with that failed root. V39 adds the symmetric,
bounded west-side yield, retains the same fail-closed map and coordinate proofs, and reserves wholly
fresh `340001`/`350001`/`360001` train, validation, and test seed ranges.
The first v39 reproduction engaged that branch but showed the proposed downward yield tile was not
traversable. The west-side recovery now retreats along the open aisle to `(12,2)`, verifies its
west/east transitions, and only then attempts the crossing.
That repair crossed the customer and exited the Mart. The following fixed Celadon-to-Route-7 trace
then lost its vertical alignment and stopped at `(19,14)`. V39 now verifies every coordinate change
on that city return instead of accepting an unobserved 38-input trace.
The next replay localized the loss to a pedestrian blocking the initial eastbound staging step at
`(13,14)`. The route now retreats to `(12,14)`, waits with a finite observed reentry loop, proves
the crossing to `(14,14)`, and resumes the verified north/east route.
That replay cleared both navigation defects and reached Sabrina. Her Alakazam used Recover at low
HP and then landed an observed 94-HP critical hit, fainting the lead from 94 HP. The Sabrina
recovery floor now protects 95 HP against Alakazam while retaining the ordinary 70-HP threshold
for the other opponents and the existing seven-item total bound.
That source completed both qualification replays. The first v39 counted run then exposed the same
fourth-floor customer at a second corridor gate, blocking the evolution-stone approach from
`(2,2)` toward `(1,2)`. V39 is sealed with that failed outcome. V40 extends the bounded eastward
yield to both observed gates and reserves fresh `370001`/`380001`/`390001` train, validation, and
test seed ranges; exposed seed `340001` must pass diagnostically before the official rehearsal.
That exact diagnostic has now passed 312/312 checkpoints and entered the Hall of Fame; the v40
clean-power rehearsal is the remaining gate before fresh counted collection begins.
V40 subsequently passed that rehearsal, but train slot 01 used 19 Poké Balls on Snorlax and arrived
at Cinnabar with three Antidotes. The capacity controller already sells the whole obsolete stack,
yet its input proof only admitted quantities zero through two. The failed root is sealed and v40 is
retired. V41 admits the legal 0–99 item-stack range, preserves the exact sale and money proofs, and
reserves fresh `400001`/`410001`/`420001` train, validation, and test seeds. Retired v40 schedules
are stress-only and cannot enter the new dataset.
The first retired schedule completed; the second exposed Diglett at 12/32 HP between Surge
opponents, below an observed 20-damage reply but above the old one-third healing floor. V41 now uses
its same single bounded Super Potion at or below two-thirds HP and must replay that exact schedule.
The replay then proved the heal and delayed inventory decrement can appear on adjacent frames after
the opponent replies. V41 latches those two effects independently while still rejecting an extra
item spend or a nonliving battle state.
That Surge schedule now completes. The next retired schedule showed the evolution-stone return
waiting at `(1,2)` could itself block the fourth-floor customer. The recovery now yields into the
proven `(1,3)` alcove, verifies corridor reentry, and retries east under finite coordinate bounds.
That fix passed, but the same stress schedule later left Bruno's level-55 Machoke at 8 HP with
unboosted Mega Punch before a critical Submission knocked out the workhorse. Bruno now prefers
STAB Surf above the already-declared one-use Lance reserve, with no extra grinding or item spend.
Retired schedules `370004`, `370005`, `380001`, and `380002` then exercised the final source across
variable capture, status, inventory, and battle lineages. They produced reusable repairs for
liquidity-aware TM28 sale timing, a fourth tunnel-only paralysis contingency with a three-cure
downstream reserve, bounded repeated-sleep recovery during Route 11 training, direct-exit Koga
mutual-KO recognition, a reserve-safe 15-PP Route 13 accuracy budget, and observed Celadon Mart
door transitions. Each exact failing schedule subsequently completed **312/312 checkpoints**,
**36/36 objectives**, all **69** scheduled battles, and Hall of Fame. V41 then passed its official
rehearsal and completed three counted training episodes; its immutable fourth slot exposed a
33-throw Snorlax schedule that exhausted the 24-Great-Ball plus one-Poké-Ball reserve. V41 is
preserved and retired. The v42 teacher funded all 32 Great Balls needed to cover the already-declared
33-throw ceiling by selling only the exact obsolete Potion/Antidote shortfall, records those sales
as evidence, and completed two counted training episodes before train seed `400003` exposed a
fixed-cadence collision with the Celadon Mart 2F shopper. V42 is preserved and retired. The v43
teacher observes that shopper frame-by-frame and permits four bounded Hyper Potions against the
Silph rival; the exact `400003` schedule completed 312/312 checkpoints and Hall of Fame. V43 then
completed all five train slots and its first validation slot before validation seed `410002`
exposed a consecutive random-wild-to-scripted-Marowak transition that the flee normalizer treated
as one battle. V43 is preserved and retired. The v44 teacher distinguishes a changed wild-battle
identity, preserves the scripted Marowak encounter for its dedicated policy, and has replayed the
exact `410002` schedule through 312/312 checkpoints, 36/36 objectives, and Hall of Fame.

## Evidence and project status

- [Roadmap](docs/roadmap.md) — milestone gates and current implementation status
- [Completion contract](docs/completion-contract.md) — what qualifies as completion
- [Architecture](docs/architecture.md) — authority and subsystem boundaries
- [Assistance policy](docs/assistance-policy.md) — permitted training and evaluation resources
- [Teaching and data plan](docs/teaching-plan.md) — references, demonstrations, and DAgger order
- [Cross-game transfer plan](docs/transfer-learning.md) — shared ontology and promotion gates
- [Battle-learning design](docs/battle-learning.md) — private data boundary, feature schema, model,
  and split rules
- [Preregistered battle collection](docs/collection-protocol.md) — frozen route identities,
  train/validation/test assignments, and timing derivation
- [First trajectory receipt](docs/evidence/private-trajectory-foundation-2026-07-30.json) —
  sanitized integrity, privacy, and scope evidence
- [First battle-decision receipt](docs/evidence/private-battle-decisions-2026-07-30.json) —
  422 privacy-safe adaptive move labels with exact execution linkage
- [First battle-imitation diagnostic](docs/evidence/private-battle-imitation-diagnostic-2026-07-30.json) —
  aggregate same-lineage teacher-choice agreement with explicit non-promotion limits
- [V44 learned battle validation](docs/evidence/private-battle-imitation-v44-validation-2026-08-05.json)
  — five training lineages, two held-out validation lineages, 85.8% accuracy, and unopened tests
- [V48 expensive-lineage stress receipt](docs/evidence/private-stress-v48-seed-61002-2026-08-05.json)
  — 312/312 checkpoints, 36/36 objectives, 71/71 scheduled battles, and Hall of Fame after the
  source-pinned Cinnabar income curriculum
- [Post-v48 state-observation stress receipt](docs/evidence/private-stress-post-v48-seed-61005-2026-08-05.json)
  — the exact Route 24/Celadon timing lineage completes 312/312 checkpoints, 36/36 objectives,
  71/71 scheduled battles, and Hall of Fame after state-based recovery and walker handling
- [Optional upstream baseline](docs/upstream-baseline.md) — pinned, isolated comparison boundary
- [Contributing](CONTRIBUTING.md) — safety and evidence requirements

## Attribution

The design is informed by the author's concluded Pokémon Red AI study, the MIT-licensed
[Continual Harness/PokéAgent](https://github.com/sethkarten/continual-harness), the
[PyBoy](https://github.com/Baekalfen/PyBoy) emulator, and the
[pret Pokémon Red disassembly](https://github.com/pret/pokered). The qualified opening corridors,
warps, events, and starter layout are pinned to pret/pokered commit
`1e96034092686d006e863cace09e87273051a3d8`; the route was independently exercised against the
supported private ROM. Any other imported or adapted code will be pinned and attributed before
use.

Pokémon is owned by Nintendo, Game Freak, and The Pokémon Company. This independent educational
project is not affiliated with or endorsed by them.
