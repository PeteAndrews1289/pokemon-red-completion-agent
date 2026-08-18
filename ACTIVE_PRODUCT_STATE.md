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

**Teacher-free Red goal-manager outcome fit V1** (`repeatable-goal-manager-outcome-fit-v1`)

- Kind: **learning**
- Rigor: **development**
- Next decision: If the one update passes every frozen train-only guard, retain it as a shadow diagnostic candidate and freeze a separate paired untouched-Red development screen. If it fails, reject this learner design without a second fit or parameter change.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Apply exactly one conservative train-only outcome update to the frozen Red goal manager using the two strictly admitted teacher-free outcomes, while preserving its title-neutral representation and prior acquisition, evolution, and story winners. |
| Authority now | The promoted Red goal manager retains only its prior bounded same-context semantic goal-selection authority. One repeatable composition episode is verified, but it grants no fresh-context, Crystal, acquisition, or living-Pokedex authority. |
| Authority target | Produce one shadow-only outcome-updated diagnostic candidate. A passing fit validates update plumbing only and grants no new gameplay authority. |
| Transfer test | After measured repeatable Red development and a separate promotion gate, compare the frozen Red-initialized goal manager with a zero-initialized scorer on an open matched Crystal development curriculum; no current work executes Crystal. |
| Cheapest falsifier | Publish the frozen one-step capped inverse-propensity learner, pass one label-free preflight, then consume the two-target fit identity once. Reject the candidate if either successful choice loses probability, training loss fails to decrease, any protected train winner flips, or the weight/KL trust caps fail. |
| Time box | 1 session / 4 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Development Episode · development | 12 | 12 |
| Verified Outcome Example · development | 2 | 2 |
| Composition Attempt · development | 1 | 1 |
| Verified Composition Episode · development | 1 | 1 |
| Model Fit · train | 3 | 4 |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-18-repeatable-goal-manager-outcome-fit-v1** · status **active** · evidence [development episode](docs/evidence/repeatable-goal-manager-development-result-v2-2026-08-18.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | This is the first direct teacher-free update to the title-neutral goal manager. It tests whether verified Red storage/restoration outcomes can alter the portable policy safely; it does not yet demonstrate acquisition, robust play, completion, living-Pokedex ability, or transfer. |
| Learning output | The fixed campaign consumed 12/12 trials: 1 complete and 11 failed. Strict admission retained 2 verified outcomes in one composition episode, including specimen-preserving storage followed by restoration; atomic episodes and acquisitions were 0. Across all terminals 21 choices were recorded, but 19 failed-prefix choices remain excluded. Teacher use was 0. |
| Authority delta | None. The campaign created development evidence, not promotion: the existing Red goal manager keeps only its prior bounded same-context authority. |
| Transfer result | Not run. Red development remains the first curriculum only; Crystal and every transfer claim stay closed. |
| Blocker | Operational reliability is poor: eleven of twelve episodes failed. One complete episode still yielded two authenticated positive targets from one root, enough only for the preregistered diagnostic fit. There is no unseen evaluation or acquisition success. |
| Decision | Retire the consumed V2 campaign with its fixed denominator preserved. Publish and preflight one frozen full-batch outcome update, then fit exactly once from the two admitted targets; decode none of the nineteen settled choices in failed episode prefixes. |
| Next session | Publish the diagnostic outcome learner and frozen fit plan, pass exact-head CI and one label-free preflight, execute one two-target fit, and publish the candidate metrics without evaluation, promotion, Crystal, or a game replay. |
| Next falsifier | Run one action-free fit preflight on the published head, then claim and execute the frozen two-target update once. Require finite round-trip weights, probability reinforcement, lower weighted loss, weight-delta L2 <=0.02, train-menu KL <=0.01, and zero acquisition/evolution/story winner flips. |
| Stop condition | Stop on any second fit, failed-prefix target decode, reward relabeling, hyperparameter search, validation/test access, teacher use, trust-cap or protected-winner failure, identity drift, private-data leak, or four hours. |

### Stop conditions

- Any access to validation or test contexts, any failed episode payload, Crystal, sealed Red, teacher outcomes, or unadmitted historical labels ends the lane.
- Any second update, changed step size or trust cap, hyperparameter search, output overwrite, fit-identity reuse, protected train winner flip, private-data leak, or authority promotion ends the lane.
- Stop after one fit or four hours; failure rejects the outcome learner without retry.

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

- **Repeatable Red goal-manager development pilot V2:** All twelve replacement trials were consumed exactly once. Strict admission found one complete two-decision composition episode and eleven failed trials; two verified outcomes are fit-eligible, atomic episodes and acquisitions were zero, and nineteen failed-prefix choices remain excluded. The fixed campaign may not run again. Evidence is preserved; retry is no.
- **Repeatable Red goal-manager development restart:** The old campaign and failed root were durably retired, and replacement campaign 452cff2a... then froze and passed a zero-action preflight under source 1c978fb7f60b41d46a2f74800b28652778d8b8a0 with four lineages and all twelve identities available. Restart maintenance produced no learning output and is complete. Evidence is preserved; retry is no.
- **Repeatable Red goal-manager development pilot V1:** Its first trial encountered a deterministic execution-interface invalid before any model prediction, controller action, or verified outcome. Trial 0 remains an infrastructure invalid, the failed root is closed account-wide, and the eleven untouched identities are durably retired_unexecuted; the campaign may never resume or enter learning counters. Evidence is preserved; retry is no.
- **Repeatable Red goal-manager development qualification:** Published source cfa07f8c29635e759efd7f80b3055518a3ec08a6 passed CI 32101788892/1. Its corrected four-root, twelve-trial campaign froze before prediction and passed the zero-action preflight with all identities available. Qualification is complete with every learning and authority counter unchanged. Evidence is preserved; retry is no.
- **Fresh Red operational-composition execution qualification V4:** Published source 20d4b1532ee78a3ffc5b762b2f90ae536dfa2022 passed CI 32092299544/1. Its single action-free preflight failed at the sanitized readiness_authentication stage before model prediction, controller input, advanced frame, gameplay, or learning output. The exact root is durably closed and may never retry; no private cause is inferred. Evidence is preserved; retry is no.
- **Fresh Red field-composition execution qualification V3:** Published source 1bbc4f34a339db1f861247990a4944053eb5fb3a passed CI 32090038721/1. Its single action-free preflight failed at the sanitized action_free_admission stage before any claim, prediction, controller input, frame, gameplay, or learning result. No private cause is inferred; the exact root was durably closed account-wide and may never retry. Evidence is preserved; retry is no.
- **Generic fresh-root preflight failure observability:** Source af04830fa51cc624a3047822d9fa582163444bea passed CI 32089092868/1. Four allowlisted caught in-process preclaim stages now emit one canonical sanitized nonzero JSON envelope without private exception text or a learning-counter change. The ROM-free lane opened no root and is complete. Evidence is preserved; retry is no.
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
