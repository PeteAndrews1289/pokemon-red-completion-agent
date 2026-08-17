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
- Next decision: After one 22-question train-only fit and one five-question newly completed-label comparison, either retain the candidate for goal-manager shadow integration or stop collection and redesign the learner.

### Mandatory mission check

| Question | Current answer |
| --- | --- |
| Reusable capability | Choose trainee, venue, and fight, rotate, heal, or stop actions from completion, party, resource, and risk state. |
| Authority now | One eight-question outcome-trained development baseline and one rejected 26-question candidate exist; the recovery adds data but no model or live authority. |
| Authority target | Fit a candidate on 22 complete joined scale-train questions, pass the frozen descriptive rule on five newly completed, never-scored development labels, then evaluate its recommendations in goal-manager shadow mode before any authority or Crystal probe. |
| Transfer test | Use the same identity-free state and action contract on an unseen Crystal development slice and compare Red initialization with zero initialization. |
| Cheapest falsifier | Fit once on the 22 complete joined scale-train questions and compare the existing baseline with the frozen update on only the five newly completed, never-scored development questions. |
| Time box | 1 sessions / 8 hours |

### Required learning outputs

| Output | Current | Minimum for the next decision |
| --- | ---: | ---: |
| Outcome Question · train | 30 | 32 |
| Outcome Question · development | 15 | 16 |
| Model Fit · train | 2 | 2 |
| Unseen Comparison · development | 2 | 2 |

Each counter changes only when tracked, path-free evidence supports it.
Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not learning
outputs.

### Latest session reorientation

**2026-08-17-recovery-successor-v1** · status **active** · evidence [outcome question](docs/evidence/repeatable-party-outcome-recovery-successor-v1-2026-08-17.json)

| Check | Session conclusion |
| --- | --- |
| Product alignment | The recovered collection, evolution, balance and role-coverage choices are identity-free outcome evidence for deciding how to develop a party. That skill is required to evolve and retain a living Pokedex across titles, while the bounded comparison prevents Red teacher reliability from becoming the product. |
| Learning output | The immutable recovery successor measured 10 of the 15 previously invalid candidate trials. This completed four additional train and five additional development questions, advancing cumulative evidence to 30/32 train and 15/16 development while retaining five invalid trials and three censored questions honestly. |
| Authority delta | The recovery added nine measured outcome questions but fit no model and granted no authority. The eight-question outcome model remains the development baseline; live party-development authority remains zero. |
| Transfer result | Not run. Crystal remains closed until the Red outcome representation produces a clear development gain and earns a title-neutral shadow-transfer design. |
| Blocker | Five successor trials remain invalid, leaving two train and one development questions censored. They do not block the 22-train plus five-newly-completed-development learner falsifier; the remaining uncertainty is whether the larger, more diverse outcome set improves the model. |
| Decision | Stop repairing teacher mechanics. Authenticate and fit one fixed candidate on the 22 complete joined scale-train questions, exclude all six previously scored development questions, and compare once on only the five newly completed labels. Retain for a later shadow design only if paired updated wins exceed base wins, accuracy does not decrease, cross-entropy decreases, and mean winner probability increases; every mixed result requires learner redesign before more data. |
| Next session | Publish the fail-closed joined fitter, require green exact-head CI, execute one offline fit and newly completed-label comparison, then adjudicate the learner before any more collection or teacher work. |
| Next falsifier | One published offline runner must authenticate the 88 measured plus five invalid joined denominator, train only on 22 complete scale-train questions, exclude six previously observed development questions, and compare once on five newly completed, never-scored development labels. |
| Stop condition | Treat the candidate as failed if paired updated wins do not exceed base wins, accuracy falls, cross-entropy does not fall, mean winner probability does not rise, or the metrics are mixed. Preserve that result and do not run another recovery campaign, promote, open sealed Red, or execute Crystal. |

### Stop conditions

- The 22-question train-only update cannot pass the frozen descriptive rule on five newly completed, never-scored Red development labels.
- Another recovery or teacher-repair campaign is proposed before the current learner result identifies missing data as the bottleneck.
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

Current evidence entries: **3**.
