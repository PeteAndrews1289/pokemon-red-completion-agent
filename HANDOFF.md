# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Battle learning improved; no candidate is qualified

The extended session collected 128 new TRAIN contexts and 3755 complete matched
branches, then made four declared fits: two terminal curricula, one control-only
successor and one expected-return successor. All candidates/logs remain retained.
No additional fit or replay follows the last successor in this sequence.

[Terminal curricula](docs/evidence/red-trainer-terminal-learning-result-2026-09-17.json):
five-member reserved TRAIN wins improved3/8 to8/8, party faints35 to8. The hard
original battle still lost. Short opening labels were replaced with complete
branches and authenticated intermediate learner states.

[Concrete-action control](docs/evidence/red-trainer-proposed-control-result-2026-09-17.json):
control now compares the actual proposed move/reserve with a public-stat damage
estimate. The original13-HP premature switch was fixed: Bulbasaur attacked and
finished the opponent. The battle still lost after27 decisions/three opponent
faints. Fresh paired wins7/8 to8/8; party faints16 to9. Attack retention passes,
combined retained52 regret0.340996420 fails the unchanged0.1609 gate.

[Expected-return successor](docs/evidence/red-trainer-return-objective-result-2026-09-17.json):
all three heads now support an opt-in measured expected-regret loss, with a
numerically verified gradient and legacy serialization preserved. One180-context
fit won8/8 fresh harder TRAIN variants versus6/8 for the previous candidate:
165 versus172 decisions,9 versus13 party faints,1120 versus1239 HP lost.
The original hard battle still lost after28 decisions and three opponent faints.

The final successor failed ALL retained gates: original44 attack0.175005484
(limit0.0554), all52 attack0.146977995 (limit0.0648), and all52 composed0.174618828
(limit0.1609). It improved newer full-battle choices while forgetting older
attacks. Do not promote it, waive gates or claim the model/player is finished.
The control-only predecessor preserves attacks but also remains unqualified.

Private final candidate: red-trainer-return-objective-20260917-v1/model.json;
SHA256 df1182c3893715b9e4e4ea6c33bf2b6b59e2781664f683d0a8a9b9e7abb88957.
Predecessor: red-trainer-proposed-control-20260917-v1/model.json.
Both have explicit candidate-verdict.json qualification failures.
All34 new successor evaluation logs completed with zero teacher queries,
memory edits or invalid actions. These assisted variants share four TRAIN
origins; none is independent natural transfer.

Next: retention-constrained learning with a ROM-free feasibility check on the
existing180 contexts. Do not recollect the corpus or rebuild the trainer.
Mixed short-horizon and full-battle return scales are a plausible contributor,
not an isolated causal proof. Natural-origin qualification and final-player
integration remain after an actually qualified candidate.

Checks:121 focused/docs tests passed,13 integration skips; mypy539 source files.
The earlier full-suite result was12420 passed with9 pre-existing failures
(dashboard receipt projections7, timing golden hash1, local runtime fingerprint1).
That full suite was not rerun after the two successor changes.

Model137 remains137 examples/92 successes/58 economy-qualified. Red96/124;
fresh acceptance0/5. Gameplay stopped. No full game, ROM hack, Crystal or GitHub
push. Pete decides publication. No Flash or Claude review was used this turn.

Recommended next session: Astra High, Fast off for the retention-constrained
objective and qualification judgment. No standing extra review gate.
