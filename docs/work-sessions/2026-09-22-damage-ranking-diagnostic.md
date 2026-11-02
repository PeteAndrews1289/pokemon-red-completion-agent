# Damage ranking: reproduced weakness, rejected shortcut

[Evidence](../evidence/red-damage-ranking-diagnostic-2026-09-22.json).
Development diagnostic, not a trained improvement or story qualification.

## Mission check

- Capability: rank attacks by observable mechanics and measured outcomes.
- Authority: diagnose existing learned proposals; no replacement actor or promotion.
- Transfer check:16new TRAIN configurations exclude all11Route22 roster species.
- Cheapest falsifier: removing raw move-type inputs fails native damage comparison.
- Time box:60minutes,144branches maximum,20minute execution deadline;
  each branch at most one player turn,5000actions,120000frames,45seconds.
- Stop: close after the sole ablation; reject aggregate or material paired regression.

## Findings

The earlier loss was not an unsupported-move mask or swapped slot. Type effectiveness,
STAB and attack categories were correctly projected. The frozen damage head ranked
Quick Attack above ThunderShock, Cut above Peck/Fly, and Strength above Ice Beam.
The additive status selector receives only its best damaging proposal plus status moves,
so it cannot rescue excluded attacks. No production selector was changed.

Exact tanh secant decomposition showed raw-type/category/effect contributions outweighing
correct effectiveness contributions. For Quick Attack minus ThunderShock, the electric-type
input contributed+9.98 versus effectiveness−5.87. These are network score units, not damage,
causal interventions or proof another move would win. The K receipt already retained a
weak13-example move slice with regret1.2492; its canonical control update left the damage
head unchanged. The original training-data cause has not been established.

## Prospective native comparison

16configurations ×3attacks ×3timing siblings =144branches. Levels31/37/43/49;
cartridge-learnable moves, all Route22 species excluded. Four existing TRAIN origins;
teacher-only isolated setup and forced first attacks. No story capture supplied targets.
The sole candidate zeroed raw move-type one-hot weights; no fit, sweep or retry.
Effectiveness,STAB,category,stats and every other weight stayed fixed.

| Measured quantity | Frozen K | Raw-type ablation |
| --- | ---: | ---: |
| Empirical best one-turn damage choices |10/16|9/16|
| Mean missed damage, opponent maximum-HP fraction |0.067936|0.077727|
| Changed recommendations |—|2, both worse|

The ablation failed its frozen rule: aggregate regret increased and case07 regressed
0.12564foeHP. Rejected, not shipped. Six K choices missed empirical best damage;
this noisy short-horizon diagnostic does not prove all six reduce battle win rate.

144hash-chained logs/terminal hashes independently verified;197602frames,
16.72seconds collection wall time. Stops:136turn-budget,6battle-won,2party-defeated.
These are branch endpoints, not a144-battle policy win rate. Two move suppressions
retained, zero illegal choices or actor memory writes.46/48attack cells varied across
timing siblings;144unique terminal hashes do not create independent evaluation roots.
32offline recommendations, zero learned native decisions, fitted models or registrations.

Story stage328,19693cash and primary collection bytes unchanged;stage329 unused.
Executed driver is SHA-pinned; original source retained privately before import sorting
and formatting. No mechanics or selection changes followed the outcomes.
All144logged first observations separately reproduced the scored vectors exactly;
the executed and formatted driver ASTs match excluding import order.
87targeted ROM-free tests pass, including8new diagnostic tests; no full-suite claim.
Lint, documentation, active-focus and collection-registry checks pass.

## Next decision

One fresh TRAIN outcome-trained mechanics-aware damage-proposal experiment:
prospectively freeze fitting/withheld configurations, one fit and retention criteria.
No further input-deletion trials on this packet. Shared-root configuration holdouts
remain development evidence, not independent evaluation. Test composed control/switch
behavior before story admission: changing the move changes control inputs too.
Switch attrition remains open. Budget45–90minutes, not a promise of rival victory.
No rematch, new story input, grinding, save edit, sale or publication this session.
