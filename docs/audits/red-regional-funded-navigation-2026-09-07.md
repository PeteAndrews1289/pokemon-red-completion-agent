# Funded regional navigation — September7

Outcome: safe replenishment worked; two new learned destination choices failed navigation.
Model47→49 retains both failures and every prior row,16successful examples total.
[Path-free evidence](../evidence/red-regional-funded-navigation-2026-09-07.json).

- F:191actions/11,676frames; sell3surplus Hyper Potions, preserve8, buy10balls,379cash.
  Deterministic safety,zero eligible examples; all other items and20specimens preserved.
- G: model47 chose Route10;1148actions/76,180frames; failed north cave doorway arrival.
  No balls consumed. Trainer battles earned2330currency. Exactly one negative source row.
- H: model48 chose Route4;368actions/24,204frames; failed south cave doorway arrival.
  Exactly one negative source row.18living/20specimens,10balls2709currency retained.

## Root cause and bounded repair

The planner inferred a downward exit from source direction/geometry. Cartridge
`PlayerStepOutFromDoor` instead checks the destination's door tile. Both live failures
show the same automatic downward step; the strict executor correctly rejected the bad plan.
Separate the door table from generic automatic warp tiles. Project explicit settled
arrivals in original warp order across the Red adapter. Metadata-free graph compatibility
remains; qualified but inconsistent arrival metadata fails closed. No coordinate exception
or relaxed acknowledgement was added.

The private real-cartridge read classifies220maps and202doorway-offset warps; both failed
exits now have the observed terminal coordinates. This read uses zero controller input.
The nine-transition H successor also needs a bounded metadata limit above the original8:
new limit32, with9/32accepted and33rejected; controller budgets are unchanged.

## Qualification and limits

Prior source323bcc06:7367ROM-free tests passed,one skipped,one expected failure,996.95s.
Repair:180focused tests,50protocol tests,402-source-file types and lint passed.
No live execution under the repair yet. The regional checklist remains4/5 pending
variation/repair closeout, not a percentage of Red completion. No outside reviewer was used.

## Reorientation

Do not spend another trial on the known uncorrected doorway bug. Publish tested source,
then one newly declared model49 continuation from H's actual endpoint; no rewind/retry.
Preserve all source failures and resource costs. Next success must be an actual played
capture or another truthful settled outcome, not a prettier dashboard or more green tests.

Candid concern: four new source choices are all failures. More training rows alone is not
evidence of a better player. Practical navigation and capture yield now matter more than
expanding the model or launching a larger campaign. Finite surplus sales are not renewable
income; trainer proceeds are observed, not a learned funding policy.
