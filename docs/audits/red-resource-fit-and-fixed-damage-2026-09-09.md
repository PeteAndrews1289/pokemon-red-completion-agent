# Final Agatha resource batch and reusable fixed-damage repair

## Learning result

All four prepared attempts executed once on the original `669cefa3` controller.
They cost 830 actions / 76,202 frames and made eight genuine choices, with no
forced singletons, teacher substitutions or lost specimens. Two heal/story
sequences defeated Agatha; two heal/heal sequences exhausted their decision
budget. All four first choices were healing. There is no changed-context
first-action contrast and no independent evaluation.

The separate shadow fit retained all seven attempted returns: four completions,
two decision-budget misses and the original known controller stop. Original
trial04 stays cancelled; both earlier first-head probes stay excluded. No
native82 row or authority changed. Model `4167759a` has seven settled returns,
one correlated root and three distinct selected inputs. Dataset fingerprint:
`1f1d27afb90eb2bcdfe2c96081872b558d19cb9fc5587627c2f3f1f6e6caa6e4`.

Independent reopening verified every original outcome, artifact digest, dataset
fingerprint and weighted diagnostic. Completion training MSE changed from
0.2499663 to 0.1221152; cost MSE from 0.0139085 to 0.0032795. These are training
diagnostics, not calibrated confidence or measured advantage. The new context's
healing estimate is about0.509, with differing outcomes after identical first
actions because later sampled choices differ. Old controller stops remain
controller-return targets, not evidence that a Pokémon battle was unwinnable.

See the [path-free receipt](../evidence/red-agatha-resource-coverage-fit-2026-09-09.json).
The optional updated-head probe is deferred: it would repeat healing with no new
first-action contrast, and the following repair changes the controller contract.
No replacement cohort is planned. This local checklist closes at2/3, with the
unexecuted item explicitly preserved—not marked complete or made a Phase4 gate.

## Narrow engineering result

The switch-entry screen previously sent every incoming move through an ordinary
type-only interface. That correctly refused fixed damage, but the caller had no
separate HP-loss path, stopping otherwise supported later battles. The shared
catalog now exposes a distinct incoming fixed-damage resolver:

- SonicBoom:20HP; Dragon Rage:40HP.
- Night Shade:the observed enemy level, exact integer1..100.
- Unknown effects remain unknown; no zero-damage fallback.

The [pinned cartridge source](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/engine/battle/core.asm)
stores these values in `ApplyAttackToPlayerPokemon.specialDamage`, outside
ordinary type/STAB/critical arithmetic. Misses and immunity never discount the
conservative bound. Seismic Toss, Psywave and other special effects are not
qualified by this slice.

Both incoming damage estimation and reserve-entry screening share that resolver.
A reserve must have strictly more HP than the fixed hit and still pass ordinary
coverage and existing health/level/status/offense requirements. Fresh enemy level,
HP and switch target are rechecked before input. Existing residual and confusion
allowances, bag checks, identity guards, switch limits and learner authority are
unchanged. The strict type-only API still refuses fixed damage; outgoing Night
Shade support was not added. Existing outgoing20/40 support is unchanged.

This is deterministic-mechanics maintenance that unblocks model-led story
composition, not a new learned battle policy or evidence of a live repaired win.
The old seven-return fit retains its original controller fingerprint; repaired
execution cannot silently share that contract.

## Validation and review

168 focused ROM-free tests passed, including literal HP20/21,40/41,55/56,
enemy-versus-reserve level, invalid observed level, party permutations, mixed
Thunderbolt coverage, unsupported effects, residual/confusion, actual controller
switch requests and fresh-observation rejection. Mypy checked452 source files.
The broader suite is recorded separately at session closeout.

The independent internal reviewer found no production blocker but caught a test
overclaim: the switch fixture initially did not apply incoming damage. The fixed
test now subtracts the actual hit and proves continued fighting only with healthy
post-hit HP; a separate1HP aftermath test proves the next attack is refused.
Initial local collection errors used the wrong editable-package path; the corrected
test command explicitly selects this checkout. No hosted retry was used for that.
No new Claude/Antigravity review or external quota measurement is claimed.

## Reorientation

Phase4 is still open. The final criterion remains model-directed story completion
with concurrent current Champion and Hall-of-Fame evidence, preserving the living
collection. Neither seven fitted returns nor green tests substitute for that.
Next inspect the existing bounded story-composition seam and use the smallest
declared current-source model-led continuation. Do not build per-boss head after
per-boss head or recursively apply a head outside its fitted goal/horizon/tail.
Full replay, sealed Red and Crystal remain outside this development session.
