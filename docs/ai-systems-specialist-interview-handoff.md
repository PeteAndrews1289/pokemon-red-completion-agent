# AI systems interview handoff

Updated November 19, 2026.

## A 30-second introduction

> I’m building a local agent that can finish Pokémon Red and register 124 obtainable species on one save. I define what counts as success, direct the engineering and review work, and use the emulator's own records to test our claims. Four fresh development runs finished the route. Every one needed intervention. We can now point to the exact moments and costs that stand between mechanical completion and an autonomous run.

## The numbers worth remembering

| Question | What the evidence says |
|---|---|
| How far has it gone? | Each of four same-seed starts reached eight badges, Champion, Hall of Fame and 124 required registrations on its own save. |
| Did it do that uninterrupted? | Each run needed external continuations. The counts were 14, 12, 10 and 15, including host and game-runner interruptions. The subsequent solo attempt also needed one before Brock. |
| How fast was it? | The fastest took 8h 12m 59s of active campaign time and 10h 52m 12s from launch to exit. Recorded frames represent 442h 29m at original hardware speed for that run. All four cartridge clocks reached their 255h display limit. |
| How fast was the story itself? | Red recorded 71:16:47 at the quickest Hall of Fame entry. The solo took 83:23:08 in-game and 2:22:09 of active wall time. Its save is parked at 26/124. |
| Have the weights learned to play faster? | The fitted battle weights preserved four out of four held-out practice wins and saved 1m 26s across them. On Erika and Blaine, both models won and their times matched. |
| What is the largest shared cost? | Across the four, 63.3% of active time came after the Hall of Fame. Run 3 took 165 minutes for registrations 75–100. Run 2 took 75 minutes. |
| Does it generalize? | These four starts used one seed. Held-out clean completion and cross-game transfer still need independent evidence. |

The public comparison contains the full 40-split table, clock definitions and timing differences. [Four-run results](work-sessions/four-run-splits-2026-11-19.md)

## One incident to tell in detail

**The failure.** The solo player selected healing. Its poisoned Squirtle fainted on the way. Red had a legal next action, its blackout sequence, and the runner already knew how to settle it after a restart. In the live emulator the two pieces never connected. Hashes showed the same cartridge state at the first stop in all four earlier campaigns.

**The change.** The runner checks that the failed choice was routed healing, the whole party fainted, controls were released and the retained state matches the live emulator. It exposes the one compulsory recovery. The model resumes strategic control when the game returns to the field.

**The test.** On an isolated copy we replayed the three preceding choices to the same state, observed Red deduct ₽633 from ₽1,265, and saw the model choose to advance the story. A second copy started at the stopped state and produced the same settlement. The real campaign resumed from its own save and beat Brock. The original interruption remains in the result. [Repair evidence](work-sessions/solo-field-blackout-2026-11-19.md)

## What Pete did

- Defined same-save completion and required the project to keep unsuccessful runs, cash losses and operator repairs in the record.
- Watched the player leave the Safari Zone and switch between unfinished goals. Asked for milestone splits, trainee-specific XP and comparable runs to distinguish poor decisions from emulator overhead.
- Directed Codex, Claude and Antigravity during engineering and review. The runtime player uses local models and declared execution skills. [Project narrative](project-narrative.md)

## Architecture in one minute

Python and PyBoy run the game locally. The observation layer reads cartridge state and exposes facts such as party health, reachable locations and inventory. A goal model scores available work. Battle policies choose moves and switches. The executor sends controller inputs. A verifier compares before and after states, including Pokémon identity, real money, target XP and registered species. Hash-bound checkpoints link a save to its decision history and costs. Offline training uses separately admitted examples. [Architecture](architecture.md) · [Assistance policy](assistance-policy.md)

## What I would do next

Our immediate speed target is a six-hour Hall of Fame clear on Red’s clock. All five same-seed starts reached Misty at 6:08:52. In the solo, seven preparation decisions before Misty consumed 4:18:37. We can compare preparing with taking the available story action through the same badge on eligible training copies. A successful fresh run measures the eventual impact on the story. The separate delivery benchmark still requires one uninterrupted 124-registration finish. [Speed training results](work-sessions/hall-of-fame-speed-2026-11-19.md) · [Cartridge splits](work-sessions/cartridge-splits-2026-11-19.md)

[Frozen blackout repair and build fingerprint](releases/red-solo-2026-11-19/README.md)

[Full development project](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/codex/red-development-20261119) · [Exact frozen player and file hashes](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/bc5b05a0463ebbcb3c2139211b99ea2baa147b22/docs/releases/red-solo-2026-11-19)
