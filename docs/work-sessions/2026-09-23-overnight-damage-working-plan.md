# Overnight damage proposal working plan

This local TRAIN experiment runs from 2026-09-23 04:17:40 UTC until at most
12:17:40 UTC. Reassess at 06:17:40, 08:17:40, and 10:17:40 UTC; stop new native
dispatch at 11:47:40 UTC. The eight-hour limit is a ceiling, not a target.

1. **Capability:** rank supported damaging moves from observable mechanics and
   measured one-turn outcomes.
2. **Learned authority:** train one experimental damage head. Preserve the
   admitted move/status, control, and switch heads byte for byte.
3. **Transfer test:** compare on withheld matchup families, then separately
   frozen team battles if the damage gate passes. All cases reuse four TRAIN
   origins; they do not establish independent-root or cross-title transfer.
4. **Cheapest falsifier:** withheld damage regret does not improve enough, or
   composed battle outcomes regress.
5. **Time box:** one original eight-hour window with two-hour reassessments.
6. **Stop condition:** a provenance/correctness failure, incompatible inputs,
   failed gate, exhausted budget, unsupported redesign, or completed packet.

The private `PLAN.json` freezes recipes, splits, seeds, gates, budgets, and
bindings before any outcome collection. Failed branches and gates remain
retained. No story save, publication, promotion, or new upstream root is in scope.
