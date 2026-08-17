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
- Next decision: After reaching 32 train and 16 untouched development questions total under the switch-assisted protocol, update on train only and decide whether the larger comparison justifies a frozen benchmark and the first title-neutral Crystal development probe.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Choose trainee, venue, and fight, rotate, heal, or stop actions from completion, party, resource, and risk state. |
| Authority now | One outcome-trained completion-aware scorer exists for offline shadow ranking; live party-development authority is zero. |
| Authority target | Demonstrate the outcome-trained scorer on a 32-train plus 16-development Red scale-up, then freeze a benchmark promotion gate and a title-neutral Crystal transfer probe. |
| Transfer test | Use the same identity-free state and action contract on an unseen Crystal development slice and compare Red initialization with zero initialization. |
| Cheapest falsifier | Expand only the authenticated non-sealed Red context inventory needed to reach 32 train and 16 development questions total, then run one action-free 24-train plus 12-development plan rehearsal. Stop if independent roots, multi-candidate menus, completion-goal coverage, or the switch-assisted intervention cannot be preserved. |
| Time box | 2 sessions / 16 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Outcome Question · train | 8 | 32 |
| Outcome Question · development | 4 | 16 |
| Model Fit · train | 1 | 2 |
| Unseen Comparison · development | 1 | 2 |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-17-initial-fit-v1** · status **closed** · evidence [unseen comparison](docs/evidence/repeatable-party-outcome-initial-fit-v1-2026-08-17.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | The first verified-outcome scorer learns portable trainee and venue preferences from completion, party, resource, evolution, and risk state. Scaling independent outcome evidence tests a reusable party-development skill needed for story progression and living-Pokedex evolution across titles. |
| Learning output | Eight train and four untouched development questions were fully measured under one switch-assisted intervention. One train-only fit reduced loss from 8.703 to 0.141; the updated scorer improved development accuracy from 25% to 100% and mean winner probability from 0.250 to 0.711. |
| Authority delta | The project now has one outcome-trained completion-aware shadow scorer, but live party-development authority remains zero until a later benchmark promotion gate. |
| Transfer result | Not run. The Red-initialized scorer now exists, but Crystal remains prohibited until the larger Red development comparison and a frozen title-neutral Crystal development protocol are ready. |
| Blocker | The initial comparison has only four development questions and is descriptive. After excluding every consumed pilot, the current pool has only two unused train roots and four unused development roots. Reaching 32 train and 16 development questions total therefore requires at least twenty-two new train roots and eight new development roots without weakening independence or candidate diversity. |
| Decision | The updated scorer improved from one of four to four of four correct development choices, reduced cross-entropy from 17.377 to 0.365, and improved three discordant correctness pairs with none favoring the base model. This earns a scale-up to 32 train and 16 development questions total, not live authority, a benchmark claim, or Crystal execution. |
| Next session | Expand the non-sealed Red context inventory by at least twenty-two train roots and eight development roots, generate an action-free 24-plus-12 scale-up plan, audit its diversity and leakage boundary, then collect only if the rehearsal passes. |
| Next falsifier | An action-free reconstruction must produce 24 additional train and 12 additional development questions from independent authenticated roots under the same feature and intervention contract, without reusing consumed roots or opening protected data. |
| Stop condition | Stop the scale-up if independent-root coverage requires identity leakage, fixed-route knowledge, overleveling, teacher labels, stale direct-combat priors, or weakened candidate diversity; redesign if the larger untouched comparison no longer favors the updated scorer. |

### Stop conditions

- The scale-up cannot produce 32 train and 16 development questions total from independent, diverse, multi-candidate roots.
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

Current evidence entries: **1**.
