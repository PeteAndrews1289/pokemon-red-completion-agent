# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer review repaired; challenger not promoted

### September 17 follow-up: five-on-five HP pilot is a no-go

A [prospective TRAIN pilot](docs/evidence/red-trainer-full-team-hp-pilot-2026-09-17.json)
added eight healthy/critical lead-HP pairs from the same four independent
clean-power origins, with five members on each side. The earlier 44 contexts
were reused without gameplay. Switching won the measured attack-versus-switch
choice in all eight new cases, so the intended HP-dependent control reversal
was not present. A 2400-epoch refit on the 52 contexts improved over an
always-first-move baseline on its full TRAIN corpus (move regret 0.1200 versus
0.1470), but regressed on the **same original 44 TRAIN cases**: move regret
0.1392 versus 0.0354 for the earlier 44-context model. Its SHA-256 is
`7193887eb3720ff447a6c8e383c937eeb578ecc974f35f6053f1942284d956a5`.
It is a rejected fit, not a new frozen challenger. There was no new natural
evaluation or authority promotion.

The [next Astra brief](docs/reviews/red-trainer-next-astra-brief-2026-09-17.md)
asks for a bounded design decision about real switch/stay reversals and
attack-head interference. Review is warranted as a **no-go diagnosis**, not as
a final approval to start training or a full Red run. Do not use scarce quota
to scale this failed recipe. The older frozen control still retains authority.

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

Next bounded objective: focused Astra design review, with no gameplay or fit.
Then use Sol High, Fast off for one prospectively balanced TRAIN contrast that
actually reverses switch/stay while preserving the original 44-case attack
skill. Only after passing that gate should a frozen challenger face a genuinely
new-origin natural comparison. Do not begin a full game run yet.
