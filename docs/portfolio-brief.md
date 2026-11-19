# Portfolio brief

Pete Andrews directs a project to build a local Pokémon player that chooses goals, prepares its party and earns a verified Pokédex across games. Red is the first benchmark. A run must start from power-on, become Champion, enter the Hall of Fame and retain all 124 required registrations on the same save. [Mission](../MISSION.md)

## Demonstrated

Four same-seed development campaigns completed the Red route on four separate saves. The fastest active completion was **8h 12m 59s**. Independent cartridge reads confirmed eight badges and all required registrations. Every run used external continuations. The project records 40 milestone splits, including Bill, the individual badges, story permissions, the League and collection thresholds. [Campaign comparison](work-sessions/four-run-splits-2026-11-19.md)

## An engineering decision

The team measured where the hours went. The first three players reached the Hall of Fame within 25 seconds of each other, then diverged sharply during collection. Across the group, 63.3% of active time came after the Hall of Fame. Run 3 made 328 closed decisions between registrations 75 and 100, compared with Run 2's 110. This points to repeated acquisition and restoration work that a future policy comparison can measure. [Split and cost evidence](evidence/red-campaign-comparison-2026-11-19.json)

## What remains

The immediate test is one uninterrupted completion. The next solo attempt stopped on a normal poison blackout before Brock. Two native copy tests now cover the live transition and its restart, and the original save continued with its cash loss and interruption recorded. Generalization to other seeds and games is still open. [Repair record](work-sessions/solo-field-blackout-2026-11-19.md) · [Roadmap](model-first-roadmap.md)

Pete sets product direction, challenges apparent progress and defines acceptance. AI coding assistants supported engineering and review. The player uses local learned policies, semantic game observations and declared skills, with zero gameplay LLM calls. [Interview handoff](ai-systems-specialist-interview-handoff.md) · [Architecture](architecture.md)
