# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## The packaged trainer player fails sustained full-party control

The frozen attack plus corrected control/switch package is still a TRAIN
candidate, not a promoted player. The [retained diagnostic](docs/evidence/red-trainer-packaged-rollout-diagnostic-result-2026-09-17.json)
tested the actual integrated policy on two existing assisted TRAIN captures.
It chose an attack and won one easy battle in a single decision. In a separate
five-member battle it chose an opening switch, then lost after 16 decisions:
five party faints, zero opponent faints, zero teacher interventions or memory
edits. Both event logs verified. These were in-sample diagnostics, not
independent transfer tests; no weights changed.

The 52 retained aggregate contexts include both attack- and switch-favored
openings, but 965 of 1,110 matched branches stopped at a short player-turn
budget. Opening-label retention did not predict a complete battle. The earlier
terminal HP pair remains retired after failing its declared reversal; do not
replay or tune it, nor refit these consumed diagnostic captures.

Next: inventory genuinely distinct TRAIN battle origins. If sufficient supply
exists, freeze one bounded terminal multi-turn curriculum that measures
intermediate attacks, switches and replacement choices under unchanged reward
and horizon. Stop before a fit if the supply is absent or outcomes remain
truncated. Any candidate still needs separate natural-origin evaluation before
authority promotion. No standing Astra review gate is required.

Model137 remains 137 examples / 92 successes / 58 economy-qualified.
Red remains 96/124; fresh acceptance remains 0/5. No full game, ROM hack,
Crystal work or GitHub push occurred. Pete decides publication.

Recommended next session: Sol High, Fast off for the bounded supply audit and
curriculum freeze; it requires careful causal boundaries, not a broad refit.
