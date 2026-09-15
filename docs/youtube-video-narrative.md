# Video narrative: test the failure recorder before the next cartridge case

This is an AI-assisted engineering project directed by Pete Andrews.

## Latest episode

Open with the previous campaign's stop: three Route11 successes, followed by a Diglett setup
failure whose phase and cost did not survive. The case is consumed, not patched and replayed.

Show the replacement journal following source inspection, relocation, encounter setup, battle
and settlement. Inject errors at each stage without opening a ROM. Distinguish an attempted
action from a completed action, and demonstrate a partial tick retaining its actual frame cost.
Then change emulator sessions and show cumulative cost remaining correct.

The turning point is the real battle-runtime test: its saved diagnostic uses JSON lists where
the in-memory version used tuples. The new regression detects the mismatch before cartridge play.
The executor-boundary check also caught misplaced primitive calls; the code moved, not the rule.

371 focused tests pass. Be explicit: this locally qualifies accounting, not Pokémon competence.
The next episode should be a short newly frozen cartridge campaign, with no replay of the old case.

## The finish line remains unchanged

Model121 remains at 121 examples/83 successes; local registrations remain 86/151 (56.95%).
This session added zero examples or registrations and used zero cartridge actions.
The final fresh-Red gate remains 0/5.

Complete a fresh model-directed Red run and its full local Pokédex before any ROM hack,
then proceed through Crystal and at least Emerald.

[Session](work-sessions/2026-09-15-cartridge-journal-v2.md) ·
[Project story](project-narrative.md) · [Roadmap](development-roadmap.md)
