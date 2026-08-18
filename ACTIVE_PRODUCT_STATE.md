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

**Goal-manager acquisition successor learning V1** (`goal-manager-acquisition-successor-learning-v1`)

- Kind: **learning**
- Rigor: **development**
- Next decision: Pass retains a shadow-only successor and opens design of an 8-train/4-development resettable multi-root curriculum. Failure closes this exact update without retry and redirects to representation/data redesign.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Assimilate one already-collected safe retained-acquisition outcome into the shadow Red goal manager while proving that its earlier storage and restoration choices do not regress. |
| Authority now | The shadow candidate safely retained one acquisition on one disclosed Red train root and previously learned from one storage/restoration episode. It has no replanning, fresh-context, completion, Crystal, or living-Pokedex authority. |
| Authority target | Produce one distinct shadow successor that improves the known acquisition target without regressing the two earlier outcomes. Grant no gameplay, promotion, completion, or transfer authority. |
| Transfer test | Not in this lane. The next resettable curriculum must reserve root-disjoint development episodes; Crystal remains closed until Red demonstrates broader learned decisions. |
| Cheapest falsifier | Run one fixed train-only successor update from the candidate acquisition arm. Stop without retry if acquisition probability or loss fails to improve, either evaluation-only anchor regresses, a protected semantic winner flips, or the existing weight/KL cap fails. |
| Time box | 1 session / 4 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Outcome Question · train | 30 | 30 |
| Model Fit · train | 4 | 5 |
| Unseen Comparison · development | 3 | 3 |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-18-acquisition-freeze-failed-successor-fit-next** · status **active** · evidence [qualification](docs/evidence/acquisition-replanning-campaign-freeze-failure-v1-2026-08-18.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | This is actual model training on collection-relevant causal outcome evidence. It remains deliberately small: its purpose is to prove safe assimilation before a broader resettable acquisition/storage/team/recovery curriculum. |
| Learning output | No new measured learning output from the failed freeze; every counter remains unchanged at 30 train outcomes, 15 development outcomes, 4 fits, 3 comparisons, 14 development attempts, 4 verified examples, and 1 verified composition. The successor plan freezes one new acquisition target and two evaluation-only anchors. |
| Authority delta | None. The published acquisition-replanning campaign failed during its single action-free freeze at action_free_root_inventory. No campaign plan, preflight, prediction, controller action, outcome, fit, promotion, or transfer result occurred. |
| Transfer result | Not run. Crystal remains closed; title neutrality is an engineering requirement here, not measured cross-title transfer. |
| Blocker | The four-root acquisition-replanning design is closed without retry or root/menu/skill repair. The existing shadow candidate has one separately collected safe retained-acquisition outcome that has not yet been assimilated. |
| Decision | Run exactly one frozen offline successor update from the candidate acquisition outcome, with the two earlier storage/restoration targets used only as no-regression anchors. Then proceed to a separately designed resettable multi-root curriculum rather than another scarce-root qualification loop. |
| Next session | Complete one offline successor fit from the already-collected candidate acquisition outcome. Do not collect new gameplay, reuse the duplicate base arm, decode failed prefixes, tune hyperparameters, evaluate on sealed data, promote authority, or execute Crystal. |
| Next falsifier | Publish and preflight the fixed successor fitter, then consume exactly one fit identity. Reject the exact update on any acquisition, anchor, protected-winner, KL, weight, provenance, or durability failure. |
| Stop condition | Stop after one fit result, or immediately on a failed gate, consumed identity, anchor regression, tuning request, new gameplay proposal, or scope beyond four hours. |

### Stop conditions

- Any new controller action, emulator advancement, teacher query, failed-prefix decode, duplicate base-arm training use, validation reuse, or hyperparameter search stops the lane.
- Any anchor regression, protected-winner flip, KL or weight-cap breach, sealed Red access, Crystal access, promotion, or full replay stops the lane.
- Stop after exactly one consumed fit identity or a documented falsification within four hours.

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

- **Fresh Red acquisition-replanning execution qualification V1:** Published source 458d47eace849d55712ff12e7a93f7ca5439579c passed CI 32147795552/1, but its single action-free freeze failed at action_free_root_inventory. No campaign plan, preflight, prediction, action, outcome, or fit occurred; the exact campaign is closed without retry or root/menu/skill repair. Evidence is preserved; retry is no.
- **Red encounter-source development execution qualification V1:** Published source 944fdc5b79aa240fb42084e47913f9446883e739 passed CI 32135801933/1. The Red adapter binds the title-neutral seam to a hard-limited four-battle, zero-heal, source-local executor; successful capture and development return to the same source boundary, and unsafe starts fail closed. No game ran and all learning counters remain unchanged. Evidence is preserved; retry is no.
- **Title-neutral encounter-source development capability V1:** Published source 6d028ea2003a4520b93a47d0607f5af01f8969e4 passed CI 32132328658/1. The ROM-free core and Red observation adapter expose an action-free, title-neutral DEVELOP_TEAM offer with strict collection-safe readiness verification. No game ran and execution integration remains separate. Evidence is preserved; retry is no.
- **Fresh Red acquisition-replanning curriculum design V1:** The action-free inventory and reviewed contract froze sixteen prospective episodes across four unused roots. Existing contexts cannot yet expose a multi-choice post-acquisition replan, so the design is complete, no gameplay or learning counter advanced, and the next work is a separate reusable capability lane. Evidence is preserved; retry is no.
- **Paired Red goal-manager outcome screen V1:** The exact pair is consumed and strictly admitted. Base and candidate each safely retained one acquisition with identical action/frame cost, producing a tie; both stopped after one decision, so composition and changed-state replanning remain unproved. No retry is allowed. Evidence is preserved; retry is no.
- **Paired Red goal-manager screen execution qualification V1:** The exact successor executor passed green CI and one zero-action preflight with the pair and both arm identities still unclaimed. It enforces pair-before-arm claims, identical resets, base-then-candidate order, three-decision hard stops, durable failure retention, and strict endpoint-only admission. Evidence is preserved; retry is no.
- **Paired Red goal-manager outcome screen design V1:** The action-free design froze one development-outcome-unused acquisition train root with three initial goals, two identical-reset arms, a three-decision cap, and safe retained acquisition as the only primary endpoint. The runner made zero predictions or controller actions; execution remains separate. Evidence is preserved; retry is no.
- **Teacher-free Red goal-manager outcome fit V1:** Its one allowed capped inverse-propensity update completed from two authenticated positive targets in one episode. The candidate passed all frozen train-only loss, probability, weight, KL, round-trip, and protected-winner guards; it remains shadow-only and the consumed fit identity may never retry. Evidence is preserved; retry is no.
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

Current evidence entries: **6**.
