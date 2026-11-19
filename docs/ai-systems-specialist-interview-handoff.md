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

First, demonstrate a clean completion on one unchanged build. Then compare complete candidates on matched seeds using all milestones, frames and active time. An apparent speed gain can come from running one emulator instead of four. The first two solo badge splits used exactly the same frame counts as the four-player runs. The solo process reached them sooner in real time. Held-out seeds and independent origins matter once reliability is repeatable. [Roadmap](model-first-roadmap.md) · [Completion criteria](completion-contract.md)

[Frozen blackout repair and build fingerprint](releases/red-solo-2026-11-19/README.md)

[Full development project](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/codex/red-development-20261119) · [Exact frozen player and file hashes](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/bc5b05a0463ebbcb3c2139211b99ea2baa147b22/docs/releases/red-solo-2026-11-19)
