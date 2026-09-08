# Confusion-aware recovery — working plan

## Mission check before implementation

1. Capability: tolerate a supported confusion turn using observed battle state,
   conservative self-hit damage and truthful selected-versus-executed move evidence.
2. Learned authority: unchanged maintenance, solely to unblock the named genuine
   story-versus-preparation lesson. No recovery choice is a fit label.
3. Transfer test: varied ROM-free confusion, HP, stats, menu and PP cases, including
   unchanged menus, wrong-slot PP changes and opponent replacement. No transfer claim.
4. Cheapest falsifier: first inspect pinned mechanics and test existing runtime;
   then zero-input qualification of retained Lapras2e9, not another game replay.
5. Time box: one focused session, at most two active hours before reorientation.
6. Stop: unsupported effect, ambiguous turn evidence, exhausted cumulative resources,
   lost specimen, unsafe HP or mismatched retained state. Preserve failures, no retry.

## Inspection correction

The existing runtime already returns move_executed=False after a cursor-confirmed
move transitions back to MAIN with the complete PP vector unchanged. The prior
handoff overstated PP consumption as an unconditional requirement. Qualify this
existing behavior with distinguishing tests rather than create a second turn engine.
The live stop was the incoming-damage model rejecting Confuse Ray.

Pinned pret/pokered commit1e96034092686d006e863cace09e87273051a3d8,
engine/battle/core.asm: confusion precedes the paralysis check and PP decrement;
HandleSelfConfusionDamage uses40power, current Attack/Defense, no critical/STAB/
type multiplier/random roll, but the enemy Reflect flag can affect the substituted
defense. engine/items/item_effects.asm does not clear the confusion volatile flag
when using Full Restore. Do not copy the reviewer's proposed confusion cure test.

Execution, if qualified, must use a new declared identity from2e9 only and carry
one already-spent Full Restore and prior switches[2,4,1]. No Jynx replay, sealed
access, Crystal, full game, model query or fit is part of this recovery scope.

## Pre-input qualification

630 focused ROM-free tests pass, including unchanged PP after confirmed MOVE-to-MAIN,
HP-only ambiguity rejection, wrong-slot PP, literal confusion/Reflect/stat reads,
stale flags and cumulative healing claims. Lint passes. A timeout diagnostic now
refreshes its raw observation after the final pulse rather than masking the bounded
failure with a stale menu read. No second turn engine was introduced.

Zero-input inspection of2e9 observes incoming bounds[97,148,345,401,668,459].
Active Blastoise has198HP, actual self-hit Attack/Defense180/194, and is not currently
confused. The bound includes possible confusion self-hit anyway. First qualified
decision is attack. Prior switches[2,4,1] and one healing claim are authenticated;
only one additional Full Restore may be requested. Save bytes are unchanged.
