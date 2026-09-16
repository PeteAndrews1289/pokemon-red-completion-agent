# Agent roles and coordination

Pete owns requirements, acceptance and GitHub publication. Codex owns local
implementation, verification and handoffs. Read [MISSION.md](MISSION.md),
[NORTH_STAR.md](NORTH_STAR.md), [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md)
and [HANDOFF.md](HANDOFF.md).

- No push or other publication without Pete's explicit instruction.
- Use Gemini3.8 Flash High through Antigravity, not the Flash CLI.
- Flash and Claude are bounded read-only reviewers, not standing execution gates.

## Current assignment

The natural near-boundary battle experiment yielded five complete train
examples from eight selected captures; three were excluded by player faints
or unequal pre-attack timing. There was too little baseline regret to justify
a fit, so the eight held-out development captures were not opened. The
bounded-turn executor retained six actual cartridge player-faint outcomes
in 2/2 fresh trials, but all choices tied before move execution. This proves
the loss representation, not battle learning. Player model and Red progress
are unchanged; gameplay stopped and no GitHub push.

The separate five timing mismatches have no per-candidate frame receipts, so
their cause remains unknown; future errors now include candidate counts. Next:
prospectively diagnose timing on a distinct train state, then seek a meaningful
move-value contrast before fitting or opening development. Sol High, Fast off.

## Reviewer contribution

Flash3.8 High completed two bounded Antigravity reviews. Accepted candidate/slot
mapping, turn settling, faint/no-alternative stops, and outcome-training direction.
Rejected unnecessary counterfactual timing, fitting development captures, and
unverified corpus/linear-weight explanations. This fitted battle model is an MLP.
One success does not prove the entire harness or a guaranteed Vicegrip outcome.
Claude unused; refreshed Flash quota unavailable.

[Evidence](docs/evidence/red-earned-learned-battle-2026-09-16.json) ·
[OHKO experiment](docs/evidence/red-ohko-expected-utility-2026-09-16.json) ·
[Natural battle evidence](docs/evidence/red-natural-battle-boundary-2026-09-16.json) ·
[Live faint evidence](docs/evidence/red-live-faint-outcome-2026-09-16.json) ·
[Workflow](docs/three-agent-workflow.md) · [Reviewer handoff](docs/current-agent-handoffs.md)
