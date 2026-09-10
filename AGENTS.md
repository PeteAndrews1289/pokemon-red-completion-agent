# Repository instructions

Read [MISSION.md](MISSION.md) first — it states the product every change is judged against. Then
read [NORTH_STAR.md](NORTH_STAR.md), whose anti-drift contract outranks every roadmap, handoff, and
dated checkpoint. Then read [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md), the generated
one-page answer for the single active lane, learning counters, time box, and forbidden work. Read
[docs/model-first-roadmap.md](docs/model-first-roadmap.md) for the broader strategy and
[AGENT_COORDINATION.md](AGENT_COORDINATION.md) for ownership. A newer dated checkpoint may not
override the mission, north star, or active product state.

Before implementation, add the six-part mission check from `NORTH_STAR.md` to the working plan:
reusable capability, learned authority, transfer test, cheapest falsifier, time box, and stop
condition. Do not start a full-game run unless every full-run gate in `NORTH_STAR.md` is recorded.
The default development loop uses short authenticated scenarios; full runs are final exams.
Run `python scripts/check_product_focus.py` before committing. It rejects multiple active lanes,
learning work without measurable outputs, maintenance without a named unblock, weakened alarms,
unsupported counters, and a stale generated active-state page.

Before publishing executable-source changes, regenerate the existing prospective
collection registry with `PYTHONPATH=src python scripts/regenerate_collection_registry.py`,
then run the same command with `--check` and include its two generated metadata files.
This is metadata maintenance only: it does not authorize or launch a collection run.
Do not repeatedly discover stale registry hashes through hosted CI emails.

Batch ordinary implementation commits into a tested publication at a useful session
boundary; do not push every small repair or manually rerun unchanged failing CI.
Fix relevant failures locally, preserve safety assertions, and distinguish a targeted
pass from a full-suite pass. Development gameplay does not wait on hosted CI.

At session closeout and after substantial verified progress, refresh the
[development infographic](docs/development-roadmap.md), its status/review log, handoffs and
project/video narrative under the North Star's closeout rules. Regenerate with
`python scripts/development_roadmap.py --write`; `scripts/check_docs.py` checks freshness.
Keep stage IDs and exit criteria stable; log material deviations in `docs/roadmap-decisions.md`.
Do not create a new CI workflow or count documentation work as model progress.

This is the completion-first successor to the concluded `pokemon-red-ai` research project.

## User-facing session closeout

After each session, provide a concise outcome-first update: verified work, learning
and collection deltas, whether gameplay is running or stopped, failures/limitations,
next bounded objective and estimate, and candid suggestions when useful. End with
the recommended next-session model, reasoning effort and whether Fast is worthwhile,
with a task-specific reason. Never imply a recommendation changed the selected model.
When Flash or Claude was used, identify its actual contribution, accepted/rejected
findings, completion status and refreshed service quota (or explicitly unavailable).
Use bounded Flash drafts/reviews when they save real work; do not add a standing
external-review gate to ordinary development. Keep roadmap, handoff and narrative
aligned with verified evidence; tests and documentation are not learning progress.

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
- Codex owns implementation and publication. Claude and Antigravity are read-only reviewers by
  default under `docs/three-agent-workflow.md`; do not let concurrent agents edit this worktree.
