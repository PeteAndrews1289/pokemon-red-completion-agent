# Project story: learning to play, not repeat a walkthrough

Pete's goal is a model that genuinely plays Pokémon. It must make useful decisions, respond
to unfamiliar situations and carry learned skills forward. AI coding assistants—including
Codex, Claude and Antigravity—help build and review the system; they do not secretly choose
each live action.

The required first finish line is now explicit: a fresh start-to-finish model-directed Red
run with story completion and the full local Red Pokédex, before any ROM hack. Version,
trade and event dependencies remain real requirements, not excluded entries. After full
Red comes a compatible unfamiliar hack, then Crystal and at least Emerald.

## Latest measured chapter

Model114 chose earning money from six alternatives. The bounded attempt used160 actions
and10633 frames, then failed verification: the expected balance was2088 but the game showed2146,
up from58. That extra money was not used to disguise the failure.

The actual failed outcome became row115. Model115 preserves all114 earlier examples;
successful examples remain78. The retained save still has84 registrations,64 living species
and68 specimens. It reopened without gameplay, and the new six-option menu selected another
income opportunity. That choice remains frozen while the accounting discrepancy is diagnosed.

This is the intended learning loop: choose, act, measure, retain, learn and continue from
the real terminal. It is not independent proof that the policy is good, a fresh-game autonomous
playthrough, or cross-title transfer. Deterministic mechanics still control low-level play.

[Latest measured evidence](evidence/red-model115-frozen-resupply-learning-2026-09-13.json) ·
[Detailed session](work-sessions/2026-09-13-model115-frozen-resupply-learning.md)

## What earlier chapters established

- [Checkpoint story completion](audits/red-phase4-closeout-2026-09-09.md) reached the Champion
  and Hall of Fame under declared hierarchical authority. Forced boss continuation and
  deterministic battles mean it does not satisfy the fresh-run acceptance gate.
- [Cross-box capability retrieval](work-sessions/2026-09-13-model111-cross-box-capture-support.md)
  made capture preparation reusable rather than a named-species route.
- [Automatic fishing failure](work-sessions/2026-09-13-model112-automatic-fishing-failure-learning.md)
  demonstrated retaining an inconvenient outcome instead of retrying it.
- [Model114 fishing success](work-sessions/2026-09-13-model114-frozen-fishing-learning.md)
  added registration84 and exposed a subsequent resource decision.

## What still matters most

The current40-entry remaining counter describes a124-entry native-availability scope, not the
full Red finish line. The player still needs broad acquisition mechanics, sustainable resources,
genuine model-directed story choices and an authenticated full run. A collection of related
training outcomes does not establish generalization.

Flash supplied this session's admission proposal; Codex corrected and tested it. Claude
reviewed the consequential source boundary. Useful collaboration means finding and correcting
errors, not taking a vote or counting review volume as learning progress.

[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Roadmap](development-roadmap.md) · [Authorship and public overview](../README.md)
