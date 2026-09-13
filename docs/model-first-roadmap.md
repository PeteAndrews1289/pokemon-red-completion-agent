# Model-first development roadmap

The product is a model that plays Pokémon and accumulates a shared, verified Pokédex across games,
not a fixed Red walkthrough. The [mission](../MISSION.md) and [North Star](../NORTH_STAR.md) are
stable; the [active state](../ACTIVE_PRODUCT_STATE.md) owns the current decision and the
[development infographic](development-roadmap.md) owns the current checklist.

## Where we are

The Red observation, checkpoint, high-level choice, deterministic execution, outcome verification
and incremental fitting loop works. The current registered-objective model contains **111 settled
examples**. Its retained save has **83 registered species**, **63 living species**, **67 specimens**
and **41 required Red registrations remaining**.

The latest cycle contains two real four-way destination choices. Model109 selected a fishing
destination and the generic executor added registration83; that success became row110. Model110's
next choice crossed a scripted dialogue that the route runner did not advertise as supported. The
consumed failure became row111, and its exact terminal reopened as a durable checkpoint. This is
same-lineage bounded development, not an independent policy comparison, but it demonstrates a
useful loop: preserve gain, update, preserve failure, update and continue without rewriting either
outcome.

This is bounded development progress. It is not a fresh-game autonomous player, independent
reliability result or learned low-level controller.

## Next sequence

1. **Route capability before ranking — qualified.** Resource routes now fail closed unless the
   configured executor declares wild, trainer and scripted-dialogue support. Map/species identity
   remains outside policy features.
2. **Recover model111 generically — next.** Dismiss the retained scripted dialogue through the
   existing control-recovery boundary, with zero learning credit and no retry of the consumed
   choice.
3. **Resume model-directed collection.** Rebuild the menu, execute one bounded selected goal,
   retain success or failure and fit it. Keep forced support outside training.
4. **Finish Red registrations.** Iterate by reusable family and expose resource, storage and
   dependency choices naturally. A repeated empty menu is a planner falsifier, not a reason to
   reset or hand-script the target.
5. **Measure fresh-game composition.** Connect the already authenticated story checkpoints to the
   same model-facing vocabulary, then test increasingly long Red segments without hidden choices.
6. **Test an unfamiliar compatible Red modification.** Freeze the Red policy and measure initial
   competence separately from adaptation. This is the first meaningful portability test.
7. **Integrate Blue and shared memory.** Reuse global registrations while keeping local flags,
   owned specimens and version-only availability truthful.
8. **Adapt to Crystal, then later titles.** Add genuinely new mechanics through adapters and
   measure what transferred rather than assuming it.

## Immediate session boundary

Publish source `07fbfbbd767e5648a03be955e93b888f97ed02c3` and require one green GitHub
qualification. Restore the exact model111 interruption without input, recover ordinary control
through generic zero-label support and rebuild the next menu. Execute at most one fresh committed
choice. Stop if recovery requires a route-specific patch, the menu is forced-only, or route
eligibility still claims unsupported dialogue handling.

[Latest qualification](evidence/red-model111-route-capability-gate-2026-09-12.json) ·
[Latest session](work-sessions/2026-09-12-model111-route-capability-gate.md) ·
[Latest learning evidence](evidence/red-model111-fishing-learning-loop-2026-09-12.json)

## How to stay focused

Every session names one reusable capability, one model-controlled decision, one cheapest falsifier,
one time box and one stop condition. Data collection and executable scenarios take priority over
process. CI runs once after a meaningful verified change; documentation is updated after measured
progress, not instead of it.
