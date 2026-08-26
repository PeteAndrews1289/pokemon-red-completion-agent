# Red living-Pokédex setup-binding materialization V1

Status: published ROM-free implementation. Source `89f967f9` merged through PR 73 as main
`ad0e6049` and passed exact-main CI `32971132659/1`; see the
[qualification](evidence/red-living-dex-setup-binding-materialization-v1-qualification-2026-08-26.json).
This document does not authorize a private binding read, ROM access, setup execution, controller
authority, frame advance, behavior draw, learner action, outcome, fit, sealed Red evaluation,
Crystal execution, promotion, or replay. It is subordinate to [MISSION.md](../MISSION.md),
[NORTH_STAR.md](../NORTH_STAR.md), the generated
[active product state](../ACTIVE_PRODUCT_STATE.md), and the published
[setup campaign](red-living-dex-setup-campaign-v1.md).

## Why this exists

The setup runner can safely consume an exact private fifteen-slot plan, but it deliberately knows
nothing about the source of that plan. The remaining action-free bridge must authenticate approved
private Red inputs, derive every real slot and semantic arm, prove that no protected effect moved,
and seal the complete plan before any later setup-execution decision.

This module defines that bridge. It does not implement the private Red source adapter and does not
read private inputs itself. ROM-free fixtures simulate the protocol only; they cannot become
authentic binding evidence.

## Mission check

| Question | Answer |
| --- | --- |
| Reusable capability | Turn an authenticated title-private source into one complete, sealed semantic setup plan while a shared independent meter proves zero controller, learner, teacher, model, outcome, and claim effects. The source protocol can later sit in front of another title adapter. |
| Learned authority | None. Materialization creates no setup capture, choice, action, label, outcome, or fit. It only unlocks a later Red setup decision. |
| Transfer test | Preserve the shared fifteen-slot curriculum semantics and setup-plan boundary while confining Red routes, providers, states, and paths to the private adapter. A later Crystal adapter should satisfy the same action-free source shape. |
| Cheapest falsifier | Reject a different meter, missing or malformed source attestation, changed protected input set, missing/reordered/cross-joined slot, incomplete or synthetic arm, any protected-effect delta, plan replacement, or identity-bearing public result. |
| Time box | One implementation session, publish, and reorient before private input. |
| Stop condition | Stop if materialization needs controller authority, a frame, teacher directions, an invented menu arm, an outcome, a retry identity, a public path, or setup execution. |

## Action-free protocol

One private adapter must expose the same independent protected-effect meter given to the
materializer. The meter covers controller-authority attempts, controller actions, emulator frames,
behavior draws, learner labels and outcomes, predictions, fits, root claims, and teacher queries.

The materializer then:

1. records the initial protected-effect checkpoint;
2. authenticates the complete approved private input set;
3. requests exactly the canonical fifteen Red slots in frozen 10+5 order;
4. checks the meter after every slot;
5. authenticates the same private input set again and requires byte-equivalent attestation;
6. validates all fifteen slots, forty-five semantic provider arms, one local slot, and fourteen
   routed slots through the published setup contract;
7. seals the exact private source attestation and binding plan in the private artifact store; and
8. verifies the seal and zero protected-effect checkpoint once more.

A source error before sealing leaves no record and may be retried because the shared meter proves
that the failed attempt was action-free. A different complete plan cannot replace an existing
sealed plan. This differs from setup execution: once the later runner claims a slot before input,
that slot can never retry.

## Public boundary

The public projection contains only aggregate counts and protected-effect zeroes: 15 slots, 10
train, 5 development, 45 provider arms, 1 local slot, and 14 routed slots. It says private bindings
were authenticated but routes were not executed and setup execution is not authorized. It omits
the materialization digest, source manifest, protected input-set digest, binding-plan digest, slot
and state identities, routes, terminal boundaries, observations, providers, paths, and episode IDs.

## Next gate

Implement the concrete private Red source adapter and adversarially qualify its readers without
opening controller authority. Then, under a separate private action-free gate, freeze exactly one
real fifteen-slot plan or stop with finite aggregate reasons. Publish and reorient again before
calling the setup runner. Trade remains a separate requirement before full living-Pokédex
authority.
