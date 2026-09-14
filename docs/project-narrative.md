# Project story: learning to play, not repeat a walkthrough

Pete's goal is a model that genuinely plays Pokémon: it must make useful decisions, react to
unfamiliar situations and carry learned skills forward. AI coding assistants—including Codex,
Claude and Antigravity—help build and review the system; they do not secretly choose live actions.

The first finish line is a fresh start-to-finish model-directed Red run with concurrent Champion
and Hall-of-Fame evidence and all 151 local registrations, before any ROM hack. Version, trade,
supporting-save and event dependencies remain requirements. After full Red comes a compatible
unfamiliar hack, then Crystal and at least Emerald.

## Latest chapter: proving that missing targets are not enough

Model120's crash-safe choice selected trainer resupply once and earned exactly 360 cash. Its
verified result became row121, leaving the save at 86 registrations and cash 706. Model121 then
reopened without input into only resupply and restoration, with no acquisition candidate.

That is where the roadmap mattered. Another row would have exercised the same checkpoint lineage
and resource loop, not proved broader Pokémon play. The session stopped before a model query,
controller action, emulator frame, label or fit.

The project now has a ROM-free inventory for the full 151-entry local Red gate. It says exactly what
the old “38 remaining” counter omitted: the current save actually lacks 65 registrations. Thirty-
eight have plans in the solo catalog; 11 need Blue plus trade, 4 need link evolution, 11 need
supporting-save choices plus trade, and Mew needs a legitimate event input. Shared credit and a
physical specimen remain separate from a local Red owned flag.

That inventory now controls goal proposal. The first action-free test used an authenticated older
state with three missing Mansion encounters and a physical precursor for another missing evolution.
Even so, only wild capture was executable: capture starts at the encounter source, while boxed
evolution starts at a Pokémon Center. The required two-family menu failed with zero input, so the
system did not turn “could eventually obtain” into “can execute now.”

[Latest evidence](evidence/red-full-pokedex-goal-proposal-falsification-2026-09-14.json) ·
[Detailed session](work-sessions/2026-09-14-full-pokedex-goal-proposal-falsification.md) ·
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

The next design must give collection options a shared departure boundary. From one authenticated
Pokémon Center state, travel-capable capture and native boxed evolution should both be offered
before the model chooses, with routes and species kept out of policy features. The action-free menu
must pass before gameplay resumes.

Only after the bounded story, navigation, battle, resource and collection components pass unseen
gates should the project begin the fresh-start Red final exam. A growing same-lineage training set
does not establish that readiness.

[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Roadmap](development-roadmap.md) · [Authorship and public overview](../README.md)
