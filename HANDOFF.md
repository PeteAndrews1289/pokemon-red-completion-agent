# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Frozen attack package passed; terminal switching recipe stopped

[Evidence](docs/evidence/red-trainer-frozen-composition-terminal-hp-2026-09-17.json).
The older attack head and corrected control/switch heads were packaged as one
authenticated TRAIN candidate. Source receipts, model hashes, lineage and a
model serialization round-trip were checked. The packaged model reproduced
all three unchanged TRAIN gates: original-44 attack regret 0.035384769 <=0.0554,
all-52 attack 0.044750856 <=0.0648 and composed-action regret 0.112597023
<=0.1609. No weights were refit. The inherited warm-start-settings bug was fixed.
Seventeen focused tests, lint, registry check and documentation checks passed.

The first declared terminal HP scenario ran on an isolated TRAIN cartridge.
It retained five timings for five opening choices: 25 matched branches. Fifteen
won; ten remained in battle at the four-player-turn limit. Every switch branch
was truncated. At timing zero, switching to the reserve and making three attacks
left the opponent at 41 of 70 HP. The terminal gate failed. The runner stopped
before the critical-HP version or second matchup, and before any fit. This exact
four-case recipe is closed. No switching target was admitted or authority promoted.

Next bounded decision: design one prospective small curriculum with an after-
switch continuation that can finish within the common horizon. Use retained
branch damage and opponent HP to set the new recipe before playing it. Keep the
frozen attack head and three retention gates. Reserve semantic variations before
training; a genuinely new natural source is still needed for promotion.
Do not replay the failed recipe or consumed DEVELOPMENT cohort.

Model137 remains 137 examples / 92 successes / 58 economy-qualified.
Red remains 96/124; fresh acceptance remains 0/5. No full game, ROM hack,
Crystal work or GitHub push occurred. Pete decides publication.

Recommended next session: Sol High, Fast off, for one bounded switching-curriculum
design and execution. Escalate only a failed predeclared gate or material design.
