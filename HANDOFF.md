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

A frozen attack model then made 20 attack choices during a retained 29-decision
six-on-six episode. A fixed baseline declined four optional switches and used
the first living forced replacement five times. It defeated four opponents,
lost all six party members, and stopped with an explicit `party_defeated`
receipt. This is a useful failure, **not** learned switching or a win. The
training lab can now expose the consequential decisions; the next work is
outcome-matched switch/control training across varied rosters and a disjoint
natural development comparison. No fit, promotion or transfer claim occurred.

The broader non-integration suite was interrupted after 2,688 passes and three
unrelated dashboard-fixture failures; it is not a full-suite pass. Focused
tests, real-cartridge trainer integration, lint and type checking passed.

Red remains 96/124 with 74 specimens and 198 cash. Model137 remains 137
examples, 92 successes and 58 economy-qualified; fresh Red acceptance is 0/5.
Gameplay is stopped. No full Red run, ROM hack, Crystal execution or GitHub
push. Recommended next: Sol High, Fast off, about 90–120 minutes for the
switch-learning and held-out comparison gate.
