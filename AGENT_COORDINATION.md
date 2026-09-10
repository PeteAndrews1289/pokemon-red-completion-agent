# Agent roles and coordination

## Ownership

Pete owns requirements and acceptance decisions. Codex owns integration, verification and GitHub publication. External agents supplement that work; they do not create mandatory review gates for every small change.

- **Codex:** implement the active bounded task, inspect actual outcomes, keep claims factual, test locally and publish useful batches.
- **Antigravity / Flash:** bounded drafts or targeted reviews when they save work. Use an isolated branch/worktree for explicitly delegated edits; review and test before integration.
- **Claude:** selective architecture, experiment-design and adversarial review when its usage allows. Review findings are proposals, not automatic instructions.
- **Pete:** sets priorities, observes runs, challenges scope drift and approves material direction changes.

Consult [the handoff](HANDOFF.md) and [active state](ACTIVE_PRODUCT_STATE.md) for current work, and [three-agent workflow](docs/three-agent-workflow.md) for detailed isolation rules. Do not let agents concurrently edit the execution worktree.

## Current assignment

Public documentation repair and merge, at Pete's request. Gameplay is paused at X/model54. The latest Claude feedback was supplied by Pete; no new external review was commissioned in this session.

Accepted: the README and handoffs had accumulated contradictory status reports and needed replacement with concise current summaries.

Not adopted: archiving or privatizing the repository. It remains an active project; honest scope, readable evidence and clear AI-assisted authorship are the appropriate presentation.

## Reviewer brief

Review the active task against the shared registered-Pokédex goal. Distinguish learned choices from deterministic skills, and training outcomes from independent performance. Identify a concrete defect and the shortest test that could expose it. Do not propose another full teacher replay or extensive experiment bureaucracy without a specific learning benefit.

Report accepted/rejected findings and reasons after any external review. Check service usage if available; otherwise state that it is unavailable. No external quota was checked or consumed by this documentation session.

[Current reviewer entry point](docs/current-agent-handoffs.md) · [Historical coordination](docs/history/agent-coordination-through-2026-09-10.md)
