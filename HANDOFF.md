# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer battle lab: model boundary qualified, learner still weak

The [retained qualification](docs/evidence/red-trainer-practice-model-boundary-2026-09-17.json)
starts from one clean-opening, authenticated Red lab-rival **TRAIN** capture. A
teacher-only isolated copy can configure both six-member teams with any of the
151 cartridge species, declared levels, stats, HP, and moves/PP. The original
capture is unchanged. All derived variants inherit its one train lineage; no
new independent evaluation root is created.

The runner lets a policy select each legal attack, voluntary switch,
between-opponent prompt response and forced replacement. It does not read
private opponent reserve identities, choose for the policy, or write memory
after episode start. Real-cartridge tests cover two and six opponents, prompt
accept/decline, voluntary and forced switches, terminal roster verification,
and every species' readback. A clean six-on-six state produced four measured
opening move outcomes from the same starting state. The composed model-head
adapter also executed a diagnostic voluntary switch to slot 6 and a subsequent
frozen-model attack in the real emulator; its control and target heads were
test stubs, not learned models.

The matched TRAIN collector then branched that same state into one opening
attack and all five voluntary switch targets. Each branch ran for **two actual
player turns** (prompts and forced replacements do not count), retained its
visible starting and terminal observations, and wrote a separate outcome. One
root remains one root. Remaining player HP ranged from 431 to 499, and branches
defeated either zero or one opponent. These are train comparisons, not an
independent development result or an automatically chosen best action.

An authenticated capture at the first trainer replacement prompt likewise
compared **decline** with all five replacement targets. Each branch included
one actual player turn after answering the prompt, with terminal observations
and separate receipts. Remaining player HP ranged from 476 to 498. These
branches share the same TRAIN root as the opening choices.

A frozen attack model then made 20 attack choices during a retained 29-decision
six-on-six episode. A fixed baseline declined four optional switches and used
the first living forced replacement five times. It defeated four opponents,
lost all six party members, and stopped with an explicit `party_defeated`
receipt. All 29 decisions retain their visible semantic observations and
outcomes for future fitting, with no hidden opponent roster or private path.
This is a useful failure, **not** learned switching or a win. The
trainer lab is ready to supply attack-versus-switch and switch-target data;
the next work is varied-roster training and a disjoint natural development
comparison. No fit, promotion or transfer claim occurred. Status moves and
items remain outside this attack/switch trainer's qualified scope.

The broader non-integration suite was interrupted after 2,688 passes and three
unrelated dashboard-fixture failures; it is not a full-suite pass. Focused
tests, real-cartridge trainer integration, lint and type checking passed.

Red remains 96/124 with 74 specimens and 198 cash. Model137 remains 137
examples, 92 successes and 58 economy-qualified; fresh Red acceptance is 0/5.
Gameplay is stopped. No full Red run, ROM hack, Crystal execution or GitHub
push. Recommended next: Sol High, Fast off, about 90–120 minutes for the
switch-learning and held-out comparison gate.
