# Codex, Claude, and Antigravity collaboration workflow

This project benefits from independent criticism, but three agents editing the same checkout at the
same time would create conflicts and unclear ownership. The default arrangement is one implementer
and two read-only reviewers.

The durable role definitions live here. The exact current assignments, gate order, deliverables and
stop conditions live in [current-agent-handoffs.md](current-agent-handoffs.md). Read both before
dispatching work; a dated audit does not silently reactivate an older assignment.

## Roles

### Codex — implementation owner

- owns the active implementation plan;
- performs the major coding, tests, experiments, documentation, commits, and pushes;
- maintains [NORTH_STAR.md](../NORTH_STAR.md),
  [AGENT_COORDINATION.md](../AGENT_COORDINATION.md), and [HANDOFF.md](../HANDOFF.md);
- turns review findings into accepted, rejected, or deferred decisions with reasons;
- never treats reviewer agreement as a substitute for measured evidence.

Codex is the workhorse, integrator and sole default publisher. It may disagree with either reviewer,
but must resolve material disagreement with evidence and record the adjudication.

### Claude — forensic and experimental auditor

Primary emphasis:

- correctness of claims and receipts;
- data leakage and partition integrity;
- mutation resistance and tests that truly distinguish behavior;
- statistical power and evaluation design;
- hidden teacher assumptions and semantic overclaiming;
- failure evidence sufficient to reproduce a conclusion.

Claude is read-only by default. It returns an audit memo rather than changing source.
Claude should prefer an immutable exact-commit mutation or evidence audit over broad architecture
redesign. It may recommend rejection or a cheaper experiment; it does not grant model authority.

### Antigravity — architecture and generalization challenger

Primary emphasis:

- whether work increases model authority;
- whether the representation can transfer across games;
- simpler or higher-leverage designs;
- efficiency of data generation, training, and evaluation;
- brittle Red-specific assumptions;
- adversarial scenarios and missing capabilities;
- whether the current task should be stopped entirely.

Antigravity is read-only by default. It returns an architecture/red-team memo rather than changing
source.
Antigravity should prefer mission alignment, transfer falsifiers and capability prioritization over
repeating Claude's byte-level provenance work. It is explicitly expected to recommend deleting or
stopping low-value lanes.

Current Antigravity access is deliberately weighted below Codex and Claude for repository-scale
reasoning. Do not compensate by requesting a second full audit. Once a concrete catalog is frozen,
Codex prepares a compact public-safe challenge packet: North Star, learner schema, aggregate menu
coverage, declared metrics, exact transfer questions and no private identities. Antigravity returns
at most three claims, each with a cross-title counterexample, missing shared observable, smallest
Red/Crystal falsifier, decision impact and work to delete. Claude audits evidence; Codex adjudicates
and implements. There is no three-agent vote.

## Source of truth and write safety

- Codex's active branch is the only branch pushed by default.
- Claude and Antigravity inspect the exact commit named in the review request.
- They do not edit the active worktree, run a counted or sealed experiment, open private evaluation
  contexts, push, merge, or delete artifacts.
- If an external agent must prototype code, create a separate worktree and branch after Codex has
  recorded the scope. The prototype is advisory until Codex audits and ports it deliberately.
- Private ROMs, saves, datasets, model artifacts, and machine paths never enter review memos or Git.

Claude and Antigravity are separate applications. Normally the owner opens each application on the
repository and gives it the corresponding prompt below. When the owner explicitly authorizes local
desktop control and leaves the reviewer windows open, Codex may dispatch exact-commit prompts and
monitor completion; that does not broaden either reviewer's read-only scope. Review results can be
pasted into the Codex task or saved under the ignored local inbox:

- `scratch/agent-inbox/claude/`
- `scratch/agent-inbox/antigravity/`

Codex promotes accepted findings into tracked audits, decisions, handoffs, and narratives. The
scratch inbox is intentionally not versioned.

## Review cadence

Use reviews at decisions, not continuously:

1. **Roadmap review:** both reviewers challenge this strategy before implementation begins.
2. **Design review:** review the scenario schema, metrics, thresholds, partitions, and stop rules
   before a milestone is frozen.
3. **Implementation audit:** inspect code and ROM-free tests before an expensive or sealed run.
4. **Evidence audit:** inspect the path-free result and claims after the run.
5. **Transfer review:** challenge Red-specific assumptions before opening any Crystal partition.

Codex may continue low-risk implementation while a read-only review is pending, but it may not open
a sealed context or start an expensive full run until relevant critical findings are resolved.

## Required review memo format

Each review must contain:

1. exact commit and documents reviewed;
2. verdict: approve, approve with conditions, reject, or insufficient evidence;
3. mission alignment: what learned authority or transfer evidence increases;
4. critical findings, each tied to evidence;
5. likely false assumptions or overclaims;
6. cheapest experiment that could falsify the design;
7. recommended stop conditions;
8. what not to spend time on;
9. unresolved questions;
10. concise handoff to Codex.

Reviewers should distinguish defects from preferences and label inferences explicitly.

## Prompt for Claude

```text
You are the forensic and experimental auditor for pokemon-red-completion-agent.

Read completely, in order:
1. MISSION.md
2. NORTH_STAR.md
3. docs/model-first-roadmap.md
4. docs/three-agent-workflow.md
5. AGENT_COORDINATION.md
6. HANDOFF.md (newest checkpoint first; use older sections only as history)
7. docs/current-agent-handoffs.md (use only the Claude assignment)

Work read-only. Do not edit code, run a ROM, open sealed or counted contexts, create predictions,
push, or mutate artifacts. Audit the exact current commit and the model-first roadmap.

Focus on claim correctness, test distinguishability, teacher-label validity, dataset leakage,
partition design, statistical power, causal evidence, failure diagnostics, and whether the proposed
gates can actually support their claims. Explicitly attack the assumption that high teacher
agreement means competent play. Identify any task that is maintenance disguised as learning.

Return the required review memo from docs/three-agent-workflow.md. Include the cheapest bounded
experiment for every critical finding and a list of work Codex should not do.
```

## Prompt for Antigravity

```text
You are the architecture and generalization challenger for pokemon-red-completion-agent.

Read completely, in order:
1. MISSION.md
2. NORTH_STAR.md
3. docs/model-first-roadmap.md
4. docs/three-agent-workflow.md
5. AGENT_COORDINATION.md
6. HANDOFF.md (newest checkpoint first; use older sections only as history)
7. docs/current-agent-handoffs.md (use only the Antigravity assignment)

Work read-only. Do not edit code, run a ROM, open sealed or counted contexts, create predictions,
push, or mutate artifacts. Red-team the exact current architecture and the model-first roadmap.

Focus on transferable representations, learned authority, sample efficiency, scenario generation,
hierarchical control, navigation, outcome learning, party development, living-Pokédex planning,
and Red-to-Crystal transfer. Search for Red-specific scaffolding that will fail in another game.
Propose simpler or higher-leverage alternatives and adversarial tests. You are explicitly allowed
to recommend stopping or deleting a planned lane if it does not serve the product.

Return the required review memo from docs/three-agent-workflow.md. Include the cheapest bounded
experiment for every critical finding and a list of work Codex should not do.
```

## Codex adjudication format

For every material reviewer finding, Codex records:

- finding and author;
- evidence checked;
- decision: accept, reject, or defer;
- reason in terms of the mission and measured risk;
- resulting roadmap or implementation change;
- validation required before closure.

Disagreement between reviewers is useful. Codex should resolve it with the cheapest discriminating
experiment, not by averaging opinions.

## End-of-session definition of done

After a meaningful job, Codex updates as applicable:

- `HANDOFF.md` with the newest factual checkpoint;
- `AGENT_COORDINATION.md` with active ownership and next work;
- `docs/model-first-roadmap.md` when strategy or gates change;
- the current audit and path-free evidence;
- project narrative, story, and video narrative;
- review adjudications and unresolved questions;
- exact commit, tests, CI state, private-artifact status, and sealed counters.

Documentation is part of completion, not cleanup left to the next agent.
