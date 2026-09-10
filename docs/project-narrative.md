# Project story: from finishing Red to learning useful choices

## The question

Can a model learn to play Pokémon well enough to finish its story, seek out missing species and carry useful knowledge into another game?

Red is a manageable first environment, but a fixed walkthrough is not the desired product. The long-term objective is one verified registered Pokédex across games, with explicit version, trade and event dependencies.

## What changed during development

**A reliable teacher was necessary, but not sufficient.** Scripted completion showed that observation, controls and story verification could work. It did not prove the model could plan. Overpowered battles and single-option decisions offered little meaningful choice.

**The project moved to short, saved-state lessons.** Rather than repeatedly replaying the whole game to investigate a local failure, the system chooses a bounded goal, executes it, checks the result and retains the terminal state. Failed attempts and spending remain visible.

**Learning moved into actual goal and destination choices.** The active model ranks useful acquisition, evolution and resource tasks. Mechanics are still deterministic. This hybrid boundary makes the current capability smaller than “AI plays Pokémon,” but it is something concrete to test.

**Collection became registration-first.** Pete removed the level-100 and simultaneous-living-form requirements. Once a species is legitimately registered, later runs should not repeat its evolution solely to earn the same global credit. Global registration, local owned flags and physical inventory remain separate.

## Results we can show

- Checkpoint-based story integration reached the Champion and Hall of Fame with disclosed deterministic battle execution. The final episode contained two learned recovery choices and a forced boss continuation—not an autonomous fresh-game win. [Story audit](audits/red-phase4-closeout-2026-09-09.md).
- The latest collection batch caught Onix, reaching59 registered species and51 physical specimens.
- Three of four goals succeeded. Both actual destination outcomes—one failed search and one successful capture—were fitted; two safety-driven resupply steps were excluded. The model grew from54 to56 examples. [Collection report](work-sessions/2026-09-10-post-merge-collection.md).

These are related development experiences, not an independent success rate or evidence of cross-game transfer.

## What the failures taught us

Navigation could propose an apparently connected route that was blocked by actual game state. Capture verification could misinterpret the way a new boxed Pokémon shifts existing slots. Resource recovery could be necessary even when its action should not be counted as learned judgment.

The engineering lesson is to verify the consequence, preserve the failed trace and repair a reusable boundary—not conceal a failed attempt with a reset or claim every successful action as model progress.

## Human and AI contributions

Pete defines the objective, observes gameplay, challenges priorities and directs acceptance decisions. Codex performs much of the implementation and integration; Claude and Antigravity provide selected drafts and reviews. This is AI-assisted engineering with human product direction, not an ambiguous claim of sole manual authorship.

Pete also challenged the repository's presentation: thousands of lines of accumulated status reports made the work difficult to understand. In September2026, public summaries were rewritten and detailed reports moved to historical archives. Documentation repair is not a learning milestone.

## What comes next

Sustain useful collection, close real mechanic gaps, evaluate on separate situations and broaden model authority. Then integrate Blue's shared registration, test a compatible unfamiliar Red modification and investigate Crystal transfer.

The unresolved question is not whether code can finish Red. It is how much useful decision-making the model has learned—and whether that knowledge survives a different situation.

[Roadmap](model-first-roadmap.md) · [Full historical narrative](history/project-narrative-through-2026-09-10.md)
