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

**Repeatable completion-aware party outcome learning** (`repeatable-party-outcome-learning-v1`)

- Kind: **learning**
- Rigor: **development**
- Next decision: After recovering the six missing train and six still-unscored development questions, select the next model using train evidence only and compare once on the newly completed development slice before deciding on a benchmark or Crystal probe.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Choose trainee, venue, and fight, rotate, heal, or stop actions from completion, party, resource, and risk state. |
| Authority now | One outcome-trained development baseline and one non-authoritative 26-question candidate exist for offline analysis; live party-development authority is zero. |
| Authority target | Demonstrate the outcome-trained scorer on a 32-train plus 16-development Red scale-up, then freeze a benchmark promotion gate and a title-neutral Crystal transfer probe. |
| Transfer test | Use the same identity-free state and action contract on an unseen Crystal development slice and compare Red initialization with zero initialization. |
| Cheapest falsifier | Repair the four observed mechanical execution classes, freeze a successor that claims only the 15 invalid assignments, and recover six train plus six still-unscored development preferences without changing learner-visible semantics. |
| Time box | 2 sessions / 16 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Outcome Question · train | 26 | 32 |
| Outcome Question · development | 10 | 16 |
| Model Fit · train | 2 | 2 |
| Unseen Comparison · development | 2 | 2 |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-17-scale-fit-v2** · status **closed** · evidence [unseen comparison](docs/evidence/repeatable-party-outcome-scale-fit-v2-2026-08-17.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | The campaign measured portable trainee and venue choices from completion, party, resource, evolution, and risk state. Its negative comparison and missing collection-goal targets directly identify what must improve before this skill can support living-Pokedex evolution across titles. |
| Learning output | The scale campaign added 18 complete train and six untouched development questions, bringing cumulative evidence to 26 train and 10 development. Training loss fell from 1.663 to 0.533, but the new candidate tied the baseline at four of six correct while cross-entropy worsened from 0.667 to 0.728 and mean winner probability fell from 0.654 to 0.619. |
| Authority delta | A second outcome-trained candidate now exists with 26 cumulative train questions, but it did not beat the existing eight-question outcome baseline. Live party-development authority remains zero. |
| Transfer result | Not run. Crystal remains closed because the larger Red candidate did not improve and the scale curriculum is still missing six train and six development preferences. |
| Blocker | Fifteen mechanical invalid trials censored six train and six development questions, including every new collection-goal train question. The 18-question sequential update tied the baseline at four of six correct and worsened aggregate calibration, so it cannot be promoted. |
| Decision | Preserve the existing outcome-trained model as the development baseline and the 26-question update as a non-authoritative negative result. Repair only the four observed execution classes, recover only the 15 invalid assignments under a new frozen successor, then use train-only model selection before comparing once on the six newly completed development questions. |
| Next session | Implement semantic tests and bounded recovery for the Celadon Dig destination, no-Fly transition, required-recovery budget, and conservative escort fallback; then action-free reconstruct a 15-trial successor before any new controller input. |
| Next falsifier | A successor must authenticate and recover only the 15 invalid assignments, complete six train and six development preferences without changing the frozen menus, and leave the original 78 measured trials untouched. |
| Stop condition | Do not promote, open sealed Red, or execute Crystal if the completed 32-train plus 16-development curriculum still fails on fresh development questions, or if recovery changes learner-visible semantics, replays measured trials, leaks identity, or copies teacher labels. |

### Stop conditions

- The 15 invalid assignments cannot be recovered without replaying measured trials or changing learner-visible semantics.
- The larger train-only update cannot beat the frozen baseline on untouched Red development scenarios.
- Any apparent gain comes from overleveling, teacher labels, identity leakage, fixed-route knowledge, or stale direct-combat evidence.
- Infrastructure work exceeds the maintenance budget without unblocking a measured learning output.

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

- **60%** data and scenarios
- **25%** model and evaluation
- **15%** maintenance and documentation

Stop and reassess after **1** session without a measured learning output, after **1** consecutive CI-only repair, or before any full replay. Repeated fixed-route patches
and unmeasured teacher-label copying are also hard alarms.

## Reviewer use

- **Codex:** Own implementation, measurement, adjudication, documentation, publication, and the active-lane counter.
- **Claude:** Audit frozen benchmark or sealed designs, statistics, leakage, and claims; routine development does not wait for a forensic review.
- **Antigravity:** Challenge architecture and cross-game transfer at milestone decisions, with at most three falsifiable claims and explicit work to delete.

## Retired leading edges

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

Current evidence entries: **2**.
