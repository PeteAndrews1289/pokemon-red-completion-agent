# Project story: learning to play, not repeat a walkthrough

Pete's goal is a model that genuinely plays Pokémon: it must make useful decisions, react to
unfamiliar situations and carry learned skills forward. AI coding assistants—including Codex,
Claude and Antigravity—help build and review the system; they do not secretly choose live actions.

The first finish line is a fresh start-to-finish model-directed Red run with concurrent Champion
and Hall-of-Fame evidence and all 151 local registrations, before any ROM hack. Version, trade,
supporting-save and event dependencies remain requirements. After full Red comes a compatible
unfamiliar hack, then Crystal and at least Emerald.

## Latest chapter: the rehearsal found two bugs, but not the third

After two generic preparation defects consumed the first source, the project built a 12-test
ROM-free rehearsal and published it green. The second source passed that rehearsal, was selected
prospectively and claimed exactly once, then exposed another generic defect before the action-free
menu appeared.

The acquisition catalog correctly records Tentacool as `wild:Route21:water`, but the direct profile
sent every method with kind `WILD` through a resolver that accepts only grass sources. Sorting
therefore crashed before a valid grass corridor could be tried. The claimed source was opened, but
there were still zero model queries, controller actions, emulator frames, registration sessions,
outcomes, examples or fits.

Flash independently confirmed that failure and a second uncaught resolver boundary in the corridor
loop. The source remains consumed without retry or replacement. This is not evidence that its game
state lacked capture and evolution choices; the program failed before it could ask.

The next guardrail expands the non-consuming test from known seams to the complete public catalog:
exclude water from grass candidates, preserve Route21 grass when water and grass coexist, run real
unmocked profile derivation and fail cleanly when no grass source remains. No third source is spent
while that repair is built.

[Latest evidence](evidence/red-direct-full-local-source-v2-preflight-failure-2026-09-14.json) ·
[Detailed session](work-sessions/2026-09-14-direct-full-local-source-v2-preflight-failure.md) ·
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

The next episode is ROM-free: repair encounter-media filtering and add complete-catalog regression
coverage, then publish it under exact-head CI. Do not reopen either consumed source, select a
fallback, claim a third source or return to the Model121 resource loop. A later session must decide
whether another scarce claim is justified.

Only after the bounded story, navigation, battle, resource and collection components pass unseen
gates should the project begin the fresh-start Red final exam. A growing same-lineage training set
does not establish that readiness.

[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Roadmap](development-roadmap.md) · [Authorship and public overview](../README.md)
