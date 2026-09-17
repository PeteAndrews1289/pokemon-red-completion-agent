# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer review repaired; challenger not promoted

The [Astra review](docs/reviews/red-trainer-astra-review-2026-09-17.md) led to
[measured remediation](docs/evidence/red-trainer-astra-remediation-2026-09-17.json).
Damage scoring now follows the attacked opponent through a living switch;
fit and live control inputs agree; an observed send-out event distinguishes
same-species opponents; Counter is consistently excluded from the initial
attack/switch scope. The runtime also survives a sleeping battler fainting
before its selected move spends PP. Focused ROM-free regressions and real
post-fix Agatha play verify these changes.

Four independent clean-power TRAIN roots now provide 44 bounded contexts:
28 retained, eight distinct-pilot additions and eight decisive type-pair
additions. The same small three-head model was fitted from graded timing
returns for 2400 epochs without additional gameplay. Move inputs increased
from four to 20 unique candidate matrices. It learned two of three clear
type-reversal pairs; its mean TRAIN move regret is 0.0354 versus 0.1750 for
always choosing the first candidate. This is training progress, not a natural
generalization claim. Frozen challenger SHA-256:
`5142af9d2dce76f455bdaf2b3230fa025956e6c1aa3ba3c73d47700dd6942c0d`.

Five previously unused natural DEVELOPMENT battles tested that frozen model.
Cinnabar was a no-regression easy fight. Lorelei showed five voluntary switches
and 13 attacks versus 25 for the older frozen control, but cost 424 versus
341 party HP. A [predeclared League cohort](configs/red-trainer-league-development-cohort-2026-09-17.json)
used Bruno, Agatha and Lance from one unresolved historical progression. Its
first Agatha arm failed on a sleep/faint runtime defect, so the original cohort
failed. After the mechanics-only fix, all Agatha arms finished; these results
remain descriptive, not a retroactive cohort pass. Across Bruno, post-fix
Agatha and Lance, the challenger won all three but used 27 attacks, lost one
party member and 552 HP; the older frozen control won all three with 24
attacks, zero faints and 340 HP lost. Bruno improved, Agatha and Lance
regressed. All arms used zero teacher queries and zero invalid actions.

Do not fit to, replay-tune or promote from these consumed DEVELOPMENT battles.
All natural checkpoints share unresolved historical Red ancestry; no
independent natural replication is claimed. The old frozen control retains
authority. This trainer model is runnable and ready for further TRAIN work,
not qualified for the final player. Model137 stays 137 examples / 92 successes
/ 58 economy-qualified; Red remains 96/124 and fresh acceptance 0/5. No full
game, ROM hack, Crystal work or GitHub push occurred. Pete decides publication.

Next bounded objective: Sol High, Fast off. Expand independent TRAIN scenarios
with varied full teams, opponent types, switch costs and adverse statuses
without reading these DEVELOPMENT outcomes into labels. Freeze a new fit and
test on a genuinely new-origin natural trainer source. Stop if it cannot beat
the older frozen control on the declared outcome vector; do not begin a full
game run yet.
