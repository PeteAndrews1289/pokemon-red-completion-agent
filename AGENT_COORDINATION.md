# Agent roles and coordination

Pete owns requirements, acceptance and GitHub publication. Codex owns local
implementation, verification and handoffs. Read [MISSION.md](MISSION.md),
[NORTH_STAR.md](NORTH_STAR.md), [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md)
and [HANDOFF.md](HANDOFF.md).

- No push or other publication without Pete's explicit instruction.
- Use Gemini3.8 Flash High through Antigravity, not the Flash CLI.
- Flash and Claude are bounded read-only reviewers, not standing execution gates.

## Current assignment

The local-only OHKO training cycle is complete. Teacher-assisted cartridge
states yielded three eligible train roots and four distinct development roots;
one train capture was quarantined after a battler fainted. A last-layer update
reduced train loss, but both models made the same four held-out choices. On an
older, retrospective development set the candidate lost one choice with no
wins. It is **not promoted**. The consumed Route11 Kingler case flips to
Vicegrip under the candidate, but that is a diagnostic only. No player-model,
Red completion, fresh-acceptance or gameplay delta; no GitHub push.

Next: build a prospective harder battle set with *natural* OHKO-versus-reliable
choices or other near-boundary decisions, fit only on train, and require a
held-out win without regression before changing battle authority. Do not reuse
the consumed Route11 state for fitting or prospective testing. Sol High, Fast
off is sufficient for this bounded next session.

## Reviewer contribution

Flash3.8 High completed two bounded Antigravity reviews. Accepted candidate/slot
mapping, turn settling, faint/no-alternative stops, and outcome-training direction.
Rejected unnecessary counterfactual timing, fitting development captures, and
unverified corpus/linear-weight explanations. This fitted battle model is an MLP.
One success does not prove the entire harness or a guaranteed Vicegrip outcome.
Claude unused; refreshed Flash quota unavailable.

[Evidence](docs/evidence/red-earned-learned-battle-2026-09-16.json) ·
[OHKO experiment](docs/evidence/red-ohko-expected-utility-2026-09-16.json) ·
[Workflow](docs/three-agent-workflow.md) · [Reviewer handoff](docs/current-agent-handoffs.md)
