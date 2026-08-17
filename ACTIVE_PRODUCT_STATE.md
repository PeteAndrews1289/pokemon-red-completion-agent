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
- Next decision: After one complete 8-train plus 4-development switch-assisted pilot, fit one train-only scorer and decide from the untouched comparison whether the lane deserves a 32-train plus 16-development scale-up.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Choose trainee, venue, and fight, rotate, heal, or stop actions from completion, party, resource, and risk state. |
| Authority now | Completion-aware party choices remain fixed, teacher-authored, or offline-only; live authority is zero. |
| Authority target | Fit an outcome-trained shadow scorer that selects party-development choices on unseen Red scenarios; live authority stays zero until the benchmark gate. |
| Transfer test | Use the same identity-free state and action contract on an unseen Crystal development slice and compare Red initialization with zero initialization. |
| Cheapest falsifier | Execute one fresh switch-assisted 8-train plus 4-development Red pilot from the exact published preflight; stop if any question is incomplete, if diversity collapses, or if the intervention still depends on direct trainee combat or stale venue-performance priors. |
| Time box | 2 sessions / 16 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Outcome Question · train | 0 | 8 |
| Outcome Question · development | 0 | 4 |
| Model Fit · train | 0 | 1 |
| Unseen Comparison · development | 0 | 1 |

Each counter stays zero until tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-17-switch-assisted-preflight-v1** · status **closed** · evidence [preflight](docs/evidence/repeatable-party-switch-assisted-preflight-v1-2026-08-17.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | Switch-assisted participation teaches portable party rotation, resource use and teammate or venue choice without requiring weak trainees to solo; those capabilities support story completion, evolution and living-Pokedex collection across titles. |
| Learning output | No switch-assisted outcome question exists yet. Earlier direct-combat pilots remain historical falsifier evidence and do not advance the new protocol's counters. |
| Authority delta | None. The outcome-trained scorer remains unfitted and live party-development authority remains zero. |
| Transfer result | Not run. Crystal remains prohibited until Red produces a switch-assisted outcome-trained scorer and an unseen Red comparison. |
| Blocker | The switch-assisted implementation and action-free preflight are not yet published at an exact green head, and no controller execution is authorized. Historical direct-combat outcomes are incompatible with the new intervention and are excluded from its fit. |
| Decision | Publish and verify the repair, regenerate the plan from the exact head, then run one 8-train plus 4-development switch-assisted pilot only after owner authorization. If all twelve questions are complete, fit immediately on train and compare once on untouched development before deciding whether to scale to 32 plus 16. |
| Next session | Publish and pass exact-head CI, regenerate the action-free plan, obtain exact authorization, execute one pilot, and, only if it is complete, fit one train-only scorer and compare it once on untouched development. |
| Next falsifier | The exact published 8-train plus 4-development plan must yield twelve complete, learner-eligible questions under the switch-assisted fixed-dose protocol with no teacher, identity leakage, stale venue prior, or post-selection invalid. |
| Stop condition | Stop before fitting if any of the twelve questions is incomplete; stop the lane if apparent gain depends on fixed-route knowledge, identity leakage, overleveling, teacher labels, or old direct-combat priors. |

### Stop conditions

- The exact switch-assisted pilot cannot produce twelve complete, diverse multi-candidate questions.
- The fit cannot beat the frozen baseline on unseen Red scenarios.
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

Current evidence entries: **0**.
