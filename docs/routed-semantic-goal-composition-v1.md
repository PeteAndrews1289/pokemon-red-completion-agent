# Routed semantic goal composition V1

Status: ROM-free implementation candidate. Publication, exact-head CI, and a separate public
qualification are still required before this can requalify the Red 10+5 plan. This document is
subordinate to [MISSION.md](../MISSION.md), [NORTH_STAR.md](../NORTH_STAR.md), and the
[purpose-built capture contract](living-dex-purpose-built-capture-contract.md).

## Result first

The missing reusable route-to-skill boundary now has a title-neutral contract and a thin Red
adapter. A learner-facing binding keeps the **destination semantic kind**—for example acquire,
evolve, develop, manage storage, resupply, unlock access, or explore—while private transport gets
the game to that skill's physical boundary. Travel is never relabelled as the destination outcome
and never becomes an `explore` choice unless exploration itself is the selected goal.

This closes an engineering abstraction, not the Red campaign. No concrete private route or setup
root is bound here. No ROM, emulator, controller, teacher, model, capture, outcome, fit, sealed Red
case, Crystal case, promotion, or replay is opened by this work.

## Portable execution boundary

One composite binding enforces this order:

1. execute a private bounded transport binding;
2. verify its exact terminal from a fresh action-free observation;
3. stop immediately if transport failed, drifted, exceeded budget, or misreported its counters;
4. take a fresh destination observation whose identity differs from the origin and whose terminal
   boundary digest matches the route;
5. ask the existing destination provider for the unchanged declared goal kind;
6. execute that destination at most once;
7. reconcile route, destination, and total action/frame reports against one independent meter;
8. invoke the destination's independent verifier without permitting verifier-side actions.

The public contract contains the destination kind and bounded aggregate mechanics only. It omits
route references, destination references, observation identities, maps, coordinates, raw controller
sequences, filesystem paths, and teacher directions.

## Red adapter

Red contributes only title-specific mechanics:

- an authenticated semantic-router `RoutePlan` with zero profile or curriculum direction steps;
- the existing closed-loop route executor and its exact coordinate/mode acknowledgements;
- one `CountingExecutor` and emulator frame counter shared by transport and destination;
- a coherent fresh pair of `RedGoalObservation` and `TraversalSnapshot` at the route terminal; and
- an existing `RedGoalBindingProvider` for the real semantic destination.

The adapter deliberately does **not** reuse `RedRouteGoalProvider` as transport. That provider is a
genuine exploration skill whose success requires increased world knowledge. Transport to a Mart,
PC, evolution boundary, or encounter source is not exploration and cannot inherit that outcome.

## Failure and interruption behavior

Bindings are single-use. Once execution begins, the same transport or destination cannot be
retried through the object. A route failure never asks the destination provider to bind. A stale
origin observation, mismatched terminal, changed goal kind, substituted report, separate controller
counter, actionful verifier, counter drift, unavailable destination, or whole-composite budget
overrun fails closed. Process-level interruption propagates rather than being converted into a
successful or retryable learner example.

## Current proof and remaining gate

The implementation has dedicated ROM-free tests for execution order, exact terminal checks, fresh
observation coherence, kind preservation, route-source provenance, path-free public projections,
single-use behavior, report substitution, unavailable destinations, shared counters, independent
budget reconciliation, budget exhaustion, verifier side effects, state drift, and interruption.

The next gate is publication and repository-wide qualification. Only after that may the prospective
Red plan be re-audited. That re-audit must still report fourteen concrete private route/terminal
bindings and a durable setup runner as missing until they actually exist. Repeatable semantic trade
also remains a separate full-living-Pokédex blocker; this seam does not erase it.
