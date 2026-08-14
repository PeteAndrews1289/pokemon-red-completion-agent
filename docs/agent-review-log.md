# Agent review and adjudication log

This log records material external-agent findings and Codex's disposition. Review process and memo
format are defined in [three-agent-workflow.md](three-agent-workflow.md).

## Model-first roadmap reviews received — 2026-08-14

Reviewed source: commit `9d6777231110fb503064fb76e65613225a4a40cc`.

Both read-only reviewers returned **approve with conditions**. Their private scratch memos remain
untracked; the durable adjudication is recorded here.

### Claude findings

| Finding | Decision | Consequence |
| --- | --- | --- |
| C1: 13 of 2,260 battle decisions are unaccounted for and the two rates use different denominators | Accept | The correction-only artifact cannot type those exits, so the historical 13 are explicitly unclassified. New runtime reports carry terminal accounting, fail-closed invariants, and exact numerator/denominator evidence. |
| C2: dashboard tests cannot distinguish the rate formulas | Accept | Add deliberately unequal denominators, execution-rate assertions, rejection tests, and mutation probes. |
| C3: teacher agreement is not competence and the 600 disagreements have no outcome labels | Accept | Treat corrections as diagnostic covariate-shift evidence only; do not refit until bounded causal outcomes exist. |
| C4: decision counts overstate independent validation sample size | Accept | Publish trajectory counts and per-lineage results; do not compute decision-level confidence intervals over correlated turns. |
| C5: the frozen Crystal v2 endpoint is underpowered | Accept | Keep every Crystal partition closed and replace the zero-loss conjunction with a powered preregistered paired endpoint before access. |
| C6: destination performance is at chance on binary menus | Accept after reproduction | Already-open development evidence reproduced 8/13 versus 8/13 in train and 2/4 versus 2/4 in validation, with 0 paired wins and 0 losses. No sealed Red access occurred. |
| C7: confidence abstention was selected for coverage and never fired live | Accept with evidence limit | All 600 corrections exceed the threshold, but the correction-only artifact has no agreement rows, so confidence AUC is unknowable. Do not call the threshold a safety discriminator. |
| C8: Milestone 2–4 gates lack sample sizes, comparators, or power | Accept | Every frozen gate must declare n, statistic, comparator, decision rule, and power or precision target. |
| C9: Milestone 1 authorizes more infrastructure than its exit gate needs | Accept | Limit the first laboratory to navigation, battle, and party development in one process; defer parallel workers and the broad dashboard redesign. |
| C10–C11: deterministic re-execution and mismatched denominators are presented too strongly | Accept | Mark repeated trajectories explicitly and publish integer numerator/denominator pairs for every comparison. |

### Antigravity findings

| Finding | Decision | Consequence |
| --- | --- | --- |
| Static Red level targets do not represent readiness in another title | Accept | Define readiness relative to the next declared challenge and required role, not a global level constant. Test synthetically; do not open Crystal to prove a known representation defect. |
| Economic state is insufficient for autonomous collection/resupply | Accept with refinement | Preserve identity-free inputs. Expose portable purchasing power, affordability, replenishment options, and blocker semantics rather than raw title-specific money. First falsifier is a bankrupt acquisition state. |
| Coordinate and timing strings do not transfer | Accept | Retain old routes only as teacher/oracle evidence. Add no new route strings; closed-loop navigation must pass randomized displacement and collision tests. |
| Zero faints is always optimal | Reject as a policy assumption | Blackouts and unrecoverable loss remain hard failures; an individual faint is a cost the outcome policy may trade against progress and efficiency. |

### Combined execution decision

Measurement repair precedes new learner authority because a scenario result cannot be promoted if
its accounting and gate are unsound. The economic falsifier follows as a synthetic design test, not
as a fourth scenario platform. The first laboratory remains only navigation, battle, and party
development. No full Red replay, sealed Red access, Crystal context access, or correction refit is
authorized by this work.

Mission check for this implementation:

- **Capability:** trustworthy outcome measurement plus the minimal laboratory needed to teach
  transferable navigation, battle, and party-development skills.
- **Learned authority:** this maintenance lane unlocks later authority over movement recovery,
  battle actions, and train/rotate/heal/stop choices; it does not itself claim promotion.
- **Transfer test:** all interfaces and gates use semantic pressures, challenge-relative readiness,
  randomized starts, and a Red-init versus zero-init comparator rather than Red identities.
- **Cheapest falsifier:** reconcile the retained 600 corrections, run the binary-menu audit, and
  present a synthetic bankrupt state before any cartridge experiment.
- **Time box:** one focused implementation checkpoint. Defer workers, broad dashboards, and extra
  scenario families if the three core families are not yet producing bounded evidence.
- **Stop condition:** stop if accounting cannot close, if the retained artifact lacks the required
  fields, or if a proposed gate has no defensible denominator/comparator; record the limitation
  instead of collecting more data.

### Implementation result awaiting second review

- Exact live accounting now distinguishes 1,647 model executions over 2,260 decisions from 1,647
  teacher agreements over 2,247 classified comparisons; the 13 historical exits remain visibly
  unknown rather than guessed.
- The 600 corrections form 349 exact feature clusters and 206 quantized semantic clusters. They
  contain no counterfactual outcomes and are not refit-eligible.
- Dashboard component rows now publish exact correct/total pairs, independent validation units,
  paired results and candidate-count subsets.
- The initial laboratory is one process and exactly three families. Its 200 synthetic episodes per
  family prove contracts only; real snapshot-backed adapters and learner updates remain open work.
- The new bankrupt-resource contract blocks acquisition when no purchase, sale, earning or finding
  route exists, and the readiness contract is relative to the next declared challenge rather than
  a Red level constant. Both are proven synthetically; live title-adapter migration remains open.
- Crystal v2 is retired at zero access. Prospective V3 uses a 54-context zero-shot paired endpoint
  with 82.3% power at the declared useful effect and a mandatory prior-preserving three-label
  secondary analysis. Its canonical file commits all 81 assignments and both partitions exercise
  all 36 pairwise menu-order reversals. V3 remains closed pending publication and fresh
  Claude/Antigravity review.
- No ROM, sealed Red destination, Crystal experiment context, teacher execution or model promotion
  occurred in this implementation checkpoint.
- Final ROM-free validation: 3,242 passed, three integration tests deselected, one expected failure.

## Model-first pivot — 2026-08-14

- Finding: the permanent mission rejected fixed-route optimization, while the newest operational
  checkpoint instructed another full clean-power replay.
- Evidence: `MISSION.md`, the superseded top sections of `AGENT_COORDINATION.md`, `HANDOFF.md`, and
  `docs/roadmap.md`, plus the failed 85,058,060-frame Red shadow run.
- Decision: accept the owner's criticism and replace route-first iteration with short authenticated
  scenarios, interactive correction, outcome learning, and progressive authority.
- Result: mission authority is explicit; full runs require a six-part gate; Claude and Antigravity
  review read-only while Codex owns implementation and publication.
- Validation required: both external roadmap reviews and a ROM-free documentation/privacy check
  before implementation begins.

Mission check for this planning task:

- **Capability:** governance and experimental infrastructure that keeps future work aligned to a
  transferable player.
- **Learned authority:** none in this documentation-only task; Milestone 0 is the final maintenance
  gate before scenario-based authority work.
- **Transfer test:** independent Claude and Antigravity reviews must challenge Red-specific design.
- **Cheapest falsifier:** ask each reviewer to name roadmap work that cannot increase learned
  authority or cross-title reuse.
- **Time box:** one Codex planning session plus one memo from each reviewer.
- **Stop condition:** do not implement a disputed expensive lane or run a cartridge until critical
  roadmap findings are adjudicated.
