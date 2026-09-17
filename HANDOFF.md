# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Astra review complete: trainer is not cleared for fitting

The [pre-training review](docs/evidence/red-trainer-practice-astra-review-2026-09-17.json)
records ten findings and four ordered repair/qualification packets. This was
a read-only source/evidence review plus in-memory probes: no gameplay, fit,
production-source change, DEVELOPMENT opening or GitHub push.

Confirmed blockers:

- Neutral stats use `2*base+DV` instead of `2*(base+DV)`.
- Native trainer send-out recalculates reserve stats and resets PP. The retained
  Machop entered with maximum HP 89 although materialization recorded 84.
- Admission accepted all ten independently altered reports, including a forged
  win, 999 KOs, missing choices and disconnected state. Original evidence is intact.
- The protected switch helper rejects an immediate switch-in KO as an error;
  an empty supported-attack menu prevents the model choosing a legal switch.
- Features omit actual combat stats. Pikachu/Raichu with matched inputs project
  identically; arbitrary stat variation cannot be learned from invisible values.
- Attack-only utility ignores switch damage; two retained switch branches tie
  by that diagnostic despite party HP losses 0 and 31. No joint fit adapter exists.
- Counterfactual branches lack per-decision failure logs and continuation-history
  synchronization. Only one upstream TRAIN root supports the current trainer data.

The original PP failure and HP 65535 attempt stay excluded and must not replay.
The six-choice contrast remains an executed assisted diagnostic, not automatically
fit-ready evidence. Do not rewrite its historical artifacts or call its stats neutral.
Status moves, items and full special-mechanic coverage are later battle scope;
the first trainable segment is damaging attacks, switches and replacements.

Next: Sol High, Fast off, packet 1: correct and independently test stat computation,
define native reserve stats/PP versus bounded arbitrary override modes, and qualify
level-up/PP boundaries on prospectively declared mechanic cases. Then packet 2 fixes
loss-preserving execution and admission; packet 3 versions observable features and
whole-party targets; packet 4 collects a bounded lineage-balanced corpus and fits.
Keep at least four TRAIN roots with four admitted scenarios each; RNG siblings
never count as new roots. Untouched natural DEVELOPMENT remains for comparison
after a justified challenger, not training.

Verification: 300 targeted ROM-free tests passed, but review probes expose missing
coverage; this is not a full-suite or training-readiness pass. Model137 remains
137 examples/92 successes/58 economy-qualified; Red 96/124; fresh acceptance 0/5.
Gameplay is stopped. No learning or authority delta. Flash/Claude unused this review.
