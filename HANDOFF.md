# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September19,2026.

## Trainer works; battler still fails qualification

[Session evidence](docs/evidence/red-battler-readiness-result-2026-09-19.json)
and [declared plan](docs/evidence/red-battler-readiness-plan-2026-09-19.json).
Four bounded fits followed specific TRAIN diagnoses, not a hyperparameter sweep.
All candidates and failed comparisons are retained. No player promotion or push.

Added138 fitted contexts to the previous180:318 total, across four existing
fresh TRAIN roots. Three collections completed3265 matched terminal branches,
31752decisions and37904062frames; observed active/opponent union111species.
Five timing offsets per context. New data includes openings, forced/prompt
switches, final-opponent attacks and last-survivor attacks. These are generated
TRAIN battles, not independent natural qualification or species mastery.

Reference candidate H passed all13 TRAIN/retention checks. New late90 composed
regret fell1.241603499→0.636730179. In its new24-battle comparison H won14 versus
G11, with47 versus50faints and5888 versus6121HP lost. Teacher reference won17.
H therefore remains unqualified, despite its useful within-cohort improvement.
Private directory: red-trainer-late-fit-20260919-v1.
H SHA256: ca8728daf4182fc712a4d6713a85a241398e0be376b54c2d6fd986fda084574b.

Candidate I fixed vanishing gradients for confidently wrong return rankings
using a finite-difference-tested pairwise loss. Same318 examples; no new labels.
Late90 attack regret fell0.172015109→0.000602133, control regret to0, composed
to0.046204062. Switch head retained epoch0 because alternatives failed retention.
But its fresh comparison regressed to7/24wins versus H14/24 and teacher17/24;
58 versus49faints. Reject I, not its failure logs. No further blind fit.
Private directories: red-trainer-pairwise-fit-20260919-v1 and
red-trainer-pairwise-qualification-20260919-v1.

## Important diagnosis and next work

The labels measure first actions followed by a strong teacher, not the deployed
learner. Existing matched-first-action TRAIN traces: G wins18/32; teacher
continuation wins27/32. This alone does not prove the action ranking changes.

A separately declared four-root audit then executed every opening action at
five timings with frozen H continuing:120 complete branches. The best measured
action changed in4/4 preselected contexts (including switch→attack reversals).
The audit is diagnostic, not an admitted fit or independent transfer result.
Do not merge its four alternate-continuation target sets into the teacher corpus.
Private directory: red-trainer-continuation-audit-20260919-v1.
Reusable runner: scripts/audit_red_trainer_continuation.py.

Next bounded objective,30–60minutes: bind continuation policy/model in the
target contract and declare a useful four-root learner-continuation curriculum
(at least16 contexts, with openings/replacements/endgames) before another fit.
Freeze the learner during collection. Decide target migration explicitly;
preserve old measurements and numeric retention gates. Then one declared fit
and unused paired full-battle comparison with a separate teacher reference.
This is not another final-review gate or a mandate to rebuild the framework.

Independent natural full-party qualification and bounded player integration
still remain. Pete has been asked for permission to prepare two bounded,
genuinely separate fresh-start natural test saves; no answer yet, no execution.
Early one-Pokemon tests alone would not qualify full-party switching.
Never replay/fit consumed Champion, League, Celadon, Fuchsia or Cinnabar tests.
No routine clean-power teacher factory, full Red run, ROM hack or Crystal.

## Runtime, verification and status

Fixed two actual cartridge learning transitions: decline replacement prompts
to preserve the existing moveset; account for automatic learning into an empty
slot after level-up while keeping exact PP checks on every existing move.
The interrupted H qualification remains failed/incomplete. Its one mechanic
regression is separate; the later comparison used a new seed with no refit.

1159focused/documentation tests pass;13optional integration skips. Mypy541
source files passes. Full suite not rerun; historical9failures remain unclaimed.
Final registry/focus/documentation/public checks must accompany this handoff.

Claude Opus4.8 High completed a bounded read-only review. Accepted explicit
final switch-retention assertions; did not loosen pulse budgets. Reported
cost$0.6042975; remaining service quota unavailable. Flash not used.

Model137 remains137examples/92successes/58economy-qualified; Red96/124 and
fresh acceptance0/5. No full-player authority gained. All gameplay stopped.
Unsupported status/recovery/boost, Counter, self-destruct and all-party
Struggle remain explicit exclusions. Trainer operational does not mean
battler fully ready. Next: Astra High, Fast off for target-policy semantics;
Sol High suffices for already-declared execution.
