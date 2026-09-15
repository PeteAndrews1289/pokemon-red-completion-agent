# Project story: learning to play, not repeat a walkthrough

Pete's goal is a model that genuinely plays Pokémon: it must make useful decisions, react to
unfamiliar situations and carry learned skills forward. AI coding assistants—including Codex,
Claude and Antigravity—help build and review the system; they do not secretly choose live actions.

The first finish line is a fresh start-to-finish model-directed Red run with concurrent Champion
and Hall-of-Fame evidence and all 151 local registrations, before any ROM hack. Version, trade,
supporting-save and event dependencies remain requirements. After full Red comes a compatible
unfamiliar hack, then Crystal and at least Emerald.

## Latest chapter: make the third guardrail catalog-wide

The second direct-origin source exposed a catalog edge case before its action-free menu appeared:
Tentacool's valid water encounter was sent into a grass-only corridor sorter. That source remains
consumed, but the repair session spent no additional source and opened no ROM or private payload.

The direct profile now asks the existing grass resolver to qualify each candidate before sorting.
It caches the valid map for deterministic priority and protects the corridor loop if an invalid
source somehow bypasses the first filter. Water stays water; the repair does not fabricate surfing
as a walking corridor.

Five new ROM-free tests cover the entire public catalog, Route21 water/grass coexistence, a real
unmocked catalog-to-corridor derivation, clean water-only exhaustion and the defensive bypass. The
named rehearsal now passes17 tests, while model, gameplay and collection counters remain unchanged.

Flash3.8 High and Claude Opus4.6 Thinking both reviewed the final change and returned PASS without
findings. The remaining question is no longer the code fix; it is whether that stronger guardrail
justifies spending a third scarce source after two failures.

[Latest evidence](evidence/red-direct-profile-encounter-media-repair-2026-09-14.json) ·
[Detailed session](work-sessions/2026-09-14-direct-profile-encounter-media-repair.md) ·
[Latest measured fit](work-sessions/2026-09-14-model121-frozen-resupply.md)

## What earlier chapters established

- [Checkpoint story completion](audits/red-phase4-closeout-2026-09-09.md) reached the Champion
  and Hall of Fame under declared hierarchical authority. It is not the required fresh run.
- [Cross-box capability retrieval](work-sessions/2026-09-13-model111-cross-box-capture-support.md)
  made capture preparation reusable rather than a named-species route.
- [Automatic fishing failure](work-sessions/2026-09-13-model112-automatic-fishing-failure-learning.md)
  demonstrated retaining an inconvenient outcome instead of retrying it.
- [Model114 fishing success](work-sessions/2026-09-13-model114-frozen-fishing-learning.md)
  added a registration through a real model-selected destination.

## What matters next

The next episode begins with exact-head CI and a source-risk re-audit. If the strengthened gate now
justifies one more attempt, select one distinct unused source prospectively, claim it exactly once
and stop action-free unless capture and evolution are both executable. Do not reopen either
consumed source, select a fallback or return to the Model121 resource loop.

Only after the bounded story, navigation, battle, resource and collection components pass unseen
gates should the project begin the fresh-start Red final exam. A growing same-lineage training set
does not establish that readiness.

[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Roadmap](development-roadmap.md) · [Authorship and public overview](../README.md)
