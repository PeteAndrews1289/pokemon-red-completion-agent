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

Model119's genuine resupply-versus-restore menu was reconstructed without input and sampled once.
It selected restoration at probability0.5524737204. The field-item executor consumed one Full Heal
and cured one status in58 actions/4776 frames while preserving86 registrations,66 living species,
70 specimens and cash346.

The runner first rejected the terminal because it applied a whole-party Center postcondition to a
single-item binding. The failure remains immutable; a zero-input audit passed the original binding's
own verifier without retry. The eligible success became row120. Model120 has120 examples/82
successes, and its action-free successor exposes routed restoration and trainer resupply.

The next session reconstructed that menu without input and queried Model120 once, but a wrapper
attribute error happened before the answer was written. No one knows which option was selected.
The seed was retired without replay, gameplay or fitting, and the next-session mechanism was
hardened with a pre-query tombstone and write-ahead receipt. This is also part of genuine learning
engineering: inconvenient missing evidence stays missing instead of becoming a favorable redraw.

This is the intended learning loop: choose, act, measure, retain, learn and continue from
the real terminal. It is not independent proof that the policy is good, a fresh-game autonomous
playthrough, or cross-title transfer. Deterministic mechanics still control low-level play.

[Latest session evidence](evidence/red-model120-freeze-instrumentation-failure-2026-09-14.json) ·
[Detailed session](work-sessions/2026-09-14-model120-freeze-instrumentation-failure.md) ·
[Latest measured evidence](evidence/red-model120-frozen-field-restore-2026-09-13.json)

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

The current38-entry remaining counter describes a124-entry native-availability scope, not the
full Red finish line. The player still needs broad acquisition mechanics, sustainable resources,
genuine model-directed story choices and an authenticated full run. A collection of related
training outcomes does not establish generalization.

Claude and Flash both agreed that the unretained sample must be consumed rather than redrawn. Their
review exposed a second crash window before receipt durability; the repaired next-session freeze
now writes a tombstone before querying and hashes the selected option. These reviews guard the
evidence boundary; no learning counter advanced in the failure session.

[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Roadmap](development-roadmap.md) · [Authorship and public overview](../README.md)
