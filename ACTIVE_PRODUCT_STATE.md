<!-- Generated from configs/active-product-focus.json by scripts/product_focus.py. -->
<!-- Edit the JSON source, then run scripts/check_product_focus.py. -->
# Active product state

This is the compact answer to **what are we building, what are we doing now, and what
evidence must exist before we move on?** It is subordinate only to [MISSION.md](MISSION.md)
and [NORTH_STAR.md](NORTH_STAR.md). Older roadmap and handoff sections are history when
they conflict with this page.

## Product

Build a transferable Pokemon agent that can finish stories and create a living Pokedex across mainline games, versions, trades, and legitimate event inputs.

**Environment role:** Red is the first curriculum and Crystal is the first transfer test; neither title is the product.

Success means:

- Complete each title's story and supported mechanics under declared learned authority.
- Acquire, retain, evolve, and trade every legitimately obtainable species required by the living collection contract.
- Transfer shared navigation, battle, party, resource, planning, and collection knowledge into later titles with less teaching.
- Explain version, trade, event, one-shot, and unsupported-mechanic blockers without fabricating availability.

Not the product:

- A perfect fixed Pokemon Red walkthrough.
- An overleveled teacher replay that removes the decisions the model should learn.
- Process, provenance, or CI evidence without measured learner outcomes.
- A separate hand-scripted teacher for every game.

## One active lane

**Generic fresh-root preflight failure observability** (`generic-fresh-root-preflight-observability-v1`)

- Kind: **maintenance**
- Rigor: **development**
- Next decision: If the bounded failure envelope passes ROM-free injected tests and exact-head CI, close maintenance and separately design a V3 qualification around a different fresh root; otherwise close this composition direction without another root.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Make every caught in-process composition-runner preclaim failure emit exactly one canonical, path-free, sanitized terminal before process exit without exposing a root identity or requiring a live root. |
| Authority now | The promoted Red goal manager retains bounded same-context goal-selection authority. Existing verified skills retain low-level execution; party development has no learned authority and Crystal remains closed. |
| Authority target | Permit only a separately frozen V3 fresh-root qualification design after generic preclaim failure observability is published under green CI; no new root is authorized here. |
| Transfer test | Only after a separately qualified and successful future Red composition episode, design a matched open Crystal development comparison between the frozen Red initialization and an identical zero-initialized goal scorer. |
| Cheapest falsifier | Use ROM-free fault injection at every caught pre-prediction gate. Each forced failure must emit one canonical allowlisted-stage terminal, expose no private path or identity, make no root claim, and record zero predictions, controller actions, frames, gameplay, outcomes, or episodes. |
| Time box | 1 session / 1 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-17-fresh-composition-preflight-failure** · status **closed** · evidence [qualification](docs/evidence/fresh-goal-manager-composition-execution-preflight-v2-failure-2026-08-17.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | A diagnosable fail-closed preflight prevents additional fresh roots from being consumed opaquely, while the one-session cap and ROM-free tests keep infrastructure subordinate to the transferable learned-play goal. |
| Learning output | No measured learning output. The V2 preflight made zero predictions, controller actions, advanced frames, gameplay outcomes, fits, comparisons, authority, or transfer results. Its root is permanently closed and cannot retry. Cumulative counters stay train 30, development 15, fits 3, comparisons 3, authority 0, transfer 0. |
| Authority delta | None. The failed V2 preflight grants no fresh-context, party, Crystal, sealed, or full-game authority; the promoted Red goal manager retains only its prior bounded same-context authority. |
| Transfer result | Not run. Crystal remains closed. The failed V2 preflight and the observability seam are not transfer evidence and authorize no later-title execution. |
| Blocker | Published source 3c9ea925 passed CI 32086166416/1, but its one exact V2 preflight returned nonzero before emitting a success receipt. The internal stage is not attested, the root is permanently closed, and retry or root-specific rescue is forbidden. |
| Decision | Retire the failed root and V2 attempt, then add one small root-agnostic failure envelope for caught in-process preclaim failures. Do not diagnose or reuse the root and do not open another root in this lane. |
| Next session | Implement and publish only the bounded ROM-free failure envelope. On pass, close this maintenance lane and separately freeze a V3 qualification design around a different fresh root; on failure, close composition execution and return to offline goal-manager design. |
| Next falsifier | With public injected failures only, prove that every caught in-process composition-runner preclaim failure emits one canonical allowlisted-stage envelope and never emits private data or changes a learning counter. |
| Stop condition | Stop after one engineering session or on any private-root, ROM, emulator, model, teacher, sealed Red, or Crystal access. Do not infer the failed stage, retry the root, or build repository-wide telemetry. |

### Stop conditions

- Any access to the closed V2 root, a new private root, ROM, emulator, model, teacher, sealed Red, or Crystal ends the lane.
- Any exception text, private path or identity, non-allowlisted stage, missing terminal, duplicate terminal, or learning-counter change ends the lane.
- Stop after one session; do not infer the prior failure stage, patch a route, profile, skill, party, or model, or expand into repository-wide telemetry.

### Hard boundaries for this lane

- **Prohibited:** consumed trial retry
- **Prohibited:** crystal execution
- **Prohibited:** full game replay
- **Prohibited:** sealed red evaluation
- **Prohibited:** teacher route hardening

## Rigor belongs to the risk

| Tier | Repeatable | Per-case owner authorization | Exact source/CI binding | External review |
| --- | --- | --- | --- | --- |
| Development | Yes | No | No | design freeze or promotion only |
| Benchmark | No | No | Yes | before execution |
| Sealed | No | Yes | Yes | before execution |

Development is the fast learning loop. Benchmark and sealed rigor are reserved for
claims that justify their cost; they must not be copied into routine data generation.

## Session allocation and alarms

- **10%** data and scenarios
- **75%** model and evaluation
- **15%** maintenance and documentation

Stop and reassess after **1** session without a measured learning output, after **1** consecutive CI-only repair, or before any full replay. Repeated fixed-route patches
and unmeasured teacher-label copying are also hard alarms.

## Reviewer use

- **Codex:** Own implementation, measurement, adjudication, documentation, publication, and the active-lane counter.
- **Claude:** Audit frozen benchmark or sealed designs, statistics, leakage, and claims; routine development does not wait for a forensic review.
- **Antigravity:** Challenge architecture and cross-game transfer at milestone decisions, with at most three falsifiable claims and explicit work to delete.

## Retired leading edges

- **Fresh Red field-composition execution qualification V2:** Published source 3c9ea92562163e41e5045b0ac837dd1b6ca959fb passed CI 32086166416/1, but its one exact preflight returned nonzero before emitting a success receipt. It was not retried, no execution identity was authorized, all learning and authority counters remained unchanged, and project policy permanently closed the attempted root without root-specific rescue. Evidence is preserved; retry is no.
- **Fresh Red goal-manager composition execution qualification V1:** Its initial menu was statically impossible under the existing verified skill boundaries: capture self-excluded storage or resupply and their execution locations were incompatible. It closed before root inspection, model prediction, emulator frames, controller input, or gameplay and may not be rescued with a route, profile, or composite skill. Evidence is preserved; retry is no.
- **Fresh Red goal-manager composition design:** Its contract and ROM-free core were published after independent review. No root, prediction, controller input, outcome, fit, comparison, authority, or transfer result was created; execution prerequisites move to a separate qualification lane. Evidence is preserved; retry is no.
- **Bounded party-representation collision postmortem:** Its single report completed: all six conflicting clusters had exactly identical raw and projected contrasts, leaving semantic aliasing versus outcome instability unresolved but excluding any same-evidence optimizer or projection rescue. Party v2 and its missing-cell slice remain closed. Evidence is preserved; retry is no.
- **Protocol-consistent title-neutral party utility learning:** Its frozen v2 representation produced 28 contradictory row-pair comparisons and lacked venue-cost contrast in every observed goal slice, so the consumed gate stopped before fit and the design is closed. Evidence is preserved; retry is no.
- **One-shot 14-question party outcome campaign:** Its provenance cost and non-retryable failures dominate the learning signal, so it is no longer the development leading edge. Evidence is preserved; retry is no.

## Required status report

Counter source: Tracked path-free evidence only; inputs, preflights, CI passes, and teacher runs do not advance learning counters.

Every meaningful update reports:

- product goal
- active lane
- learning output
- current counters
- authority delta
- transfer result
- blocker
- next decision
- time box
- stop condition

Current evidence entries: **4**.
