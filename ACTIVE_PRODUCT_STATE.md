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

**Protocol-consistent title-neutral party utility learning** (`repeatable-party-outcome-learning-v1`)

- Kind: **learning**
- Rigor: **development**
- Next decision: After one leave-one-root-out train-only falsifier, either freeze a small balanced Red development slice or stop fitting and perform a representation-collision audit on the same evidence.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Learn title-neutral trainee and venue utility from completion, party, resource, escort, feasibility, and cost state; fight, rotate, heal, and stop remain fixed-policy responsibilities. |
| Authority now | One eight-question outcome-trained baseline and two rejected sequential updates exist. None has shadow or live authority; fight, rotate, heal, and stop remain fixed policy. |
| Authority target | Pass a train-only protocol-consistent utility-learning gate, then pass at most twelve separately frozen balanced Red development questions before any bounded model-controlled party integration or Crystal probe. |
| Transfer test | Use the same identity-free state and action contract on an unseen Crystal development slice and compare Red initialization with zero initialization. |
| Cheapest falsifier | Using only the 22 complete scale-train menus, fit one low-capacity protocol-consistent residual ranker with separate trainee and venue heads, then require deterministic leave-one-root-out gains on every frozen metric without opening or reusing development labels. |
| Time box | 1 sessions / 4 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Outcome Question · train | 30 | 32 |
| Outcome Question · development | 15 | 16 |
| Model Fit · train | 3 | 2 |
| Unseen Comparison · development | 3 | 2 |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-17-recovery-fit-negative-v1** · status **active** · evidence [unseen comparison](docs/evidence/repeatable-party-outcome-recovery-fit-result-v1-2026-08-17.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | Separating portable trainee and venue utility from Red execution mechanics directly supports evolving and retaining a balanced living collection across titles. Train-only falsification prevents the project from buying another Red-specific dataset before the representation earns it. |
| Learning output | One preregistered update fit on 22 train questions. Training loss fell 1.667 to 0.594, but development stayed 3/5 while cross-entropy worsened 0.633 to 1.116 and mean winner probability fell 0.657 to 0.441. All five probability comparisons regressed, so the candidate failed and was rejected. |
| Authority delta | The 30-example candidate was rejected and gained no shadow or live authority. The original eight-question model remains only a frozen development baseline; learned party-development authority remains zero. |
| Transfer result | Not run. Crystal remains closed until a protocol-consistent learner first passes train-only falsification and then a separately frozen fresh Red development slice. |
| Blocker | The shared small-data MLP reduced training loss but made confidence worse on all five newly completed labels. The immediate bottleneck is the learner and protocol representation, not Red outcome volume or the five remaining mechanical failures. |
| Decision | Close the shared-MLP update path. Build one low-capacity, protocol-consistent residual ranker with separate trainee and venue heads, title-neutral feature groups, strong fixed regularization, and menu-normalized pairwise targets. Select nothing on consumed development; use deterministic leave-one-root-out predictions over only the 22 scale-train roots. |
| Next session | Implement and test the protocol-consistent trainee/venue residual ranker and its leakage-safe leave-one-root-out evaluator, run exactly one frozen train-only falsifier, then reorient before any new data or integration. |
| Next falsifier | Run one deterministic leave-one-root-out train-only evaluation of the frozen low-capacity design. Pass only if accuracy rises, cross-entropy falls, mean winner probability rises, paired wins exceed losses, and neither action head nor the collection/evolution slice regresses. |
| Stop condition | If the leave-one-root-out gate is mixed or worse, stop fitting and audit representation collisions on the same evidence. Do not collect new outcomes, reuse consumed development, repair teacher routes, promote, open sealed Red, or execute Crystal. |

### Stop conditions

- The leave-one-root-out ranker cannot improve every frozen aggregate without regressing either action head or the collection/evolution slice.
- Consumed development labels are reused for architecture, feature, regularization, or threshold selection.
- Any apparent gain comes from species, map, title, route, teacher, or fixed-walkthrough identity leakage.
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
