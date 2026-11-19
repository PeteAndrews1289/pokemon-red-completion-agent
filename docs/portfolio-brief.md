# Portfolio brief

Pete Andrews directs a project to build a local Pokémon player that chooses goals, prepares its party and earns a verified Pokédex across games. Red is the first benchmark. A run must start from power-on, become Champion, enter the Hall of Fame and retain all 124 required registrations on the same save. [Mission](../MISSION.md)

## Demonstrated

Four same-seed development campaigns completed the Red route on four separate saves. The fastest active completion was **8h 12m 59s**. Independent cartridge reads confirmed eight badges and all required registrations. Every run used external continuations. The project records 40 milestone splits, including Bill, the individual badges, story permissions, the League and collection thresholds. [Campaign comparison](work-sessions/four-run-splits-2026-11-19.md)

## An engineering decision

The team measured where the hours went. The first three players reached the Hall of Fame within 25 seconds of each other in active wall time, then diverged sharply during collection. Across the group, 63.3% of active time came after the Hall of Fame. Run 3 made 328 closed decisions between registrations 75 and 100, compared with Run 2's 110. This points to repeated acquisition and restoration work that a future policy comparison can measure. [Split and cost evidence](evidence/red-campaign-comparison-2026-11-19.json)

## What remains

The solo earned all eight badges and entered the Hall of Fame at 83:23:08 in-game. The target is six hours. Fitting the model’s attack-or-switch decision saved 14.0% across four held-out practice fights. Erika and Blaine took the same amount of time with either model. We are testing whether the available story action can earn the same badge sooner than preparing first. A fully uninterrupted run and generalization to other seeds remain open. [Speed training results](work-sessions/hall-of-fame-speed-2026-11-19.md) · [Cartridge splits](work-sessions/cartridge-splits-2026-11-19.md)

Pete sets product direction, challenges apparent progress and defines acceptance. AI coding assistants supported engineering and review. The player uses local learned policies, semantic game observations and declared skills, with zero gameplay LLM calls. [Interview handoff](ai-systems-specialist-interview-handoff.md) · [Architecture](architecture.md)
