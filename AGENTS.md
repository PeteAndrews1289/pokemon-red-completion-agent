# Repository instructions

Read [MISSION.md](MISSION.md) first — it states the goal every change is judged against. Then
[AGENT_COORDINATION.md](AGENT_COORDINATION.md) for lanes, collision rules, and current open work.
This file holds the standing engineering constraints; those two hold the direction and the plan.

This is the completion-first successor to the concluded `pokemon-red-ai` research project.

- Do not copy experimental claims or results from the predecessor into this repository.
- Never commit ROMs, saves, snapshots, recordings, datasets, checkpoints, credentials, or private
  machine paths.
- Keep revision-specific memory reads inside the observation adapter.
- High-level planning must consume semantic state, not raw addresses.
- Only the executor may translate macro-actions into controller inputs.
- The referee may observe and verify outcomes but may not choose or replace actor actions.
- Training may use disclosed teachers, walkthroughs, snapshots, and corrections.
- Official evaluation must follow `docs/completion-contract.md`.
- Do not claim completion without concurrent Champion-event and Hall-of-Fame evidence.
- Add ROM-free tests for every change; private-ROM integration tests must use the `integration`
  marker.
