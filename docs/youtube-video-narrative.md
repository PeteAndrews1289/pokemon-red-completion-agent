# Video narrative: one lost choice and no favorable redraw

This is an AI-assisted engineering project directed by Pete Andrews, with implementation
and review contributions from Codex, Claude and Antigravity. Show what the software actually
did, including failures; do not present coding assistants as the live Pokémon policy.

## Latest episode

Open on the same Model120 routed-restoration-versus-trainer-resupply menu. The freeze reconstructs
it with zero input and asks the model once—then the wrapper crashes before saving the answer. Do not
claim which option won. Show the immutable failure receipt: one consumed query, zero controller
actions, zero frames, zero labels and zero training examples. Explain why rerunning the seed would
silently turn missing evidence into a redraw.

Then show the repair prepared for the next session: a tombstone is durably written before the query,
and a returned choice is written ahead of later validation with a content hash of the selected
option. End before running that successor. Model120 and the collection counters do not change.

[Latest session and evidence](work-sessions/2026-09-14-model120-freeze-instrumentation-failure.md)

## Prior measured episode

Start with Model119's real two-option resupply-versus-restore menu. Show the single sample selecting
restoration at probability0.5524737204, then the field-item executor consuming one Full Heal and
curing one status in58 actions/4776 frames. There was no redraw, teacher fallback or retry.

Do not hide the wrapper failure. Explain that a reused Center postcondition expected unchanged
inventory and whole-party restoration. Preserve that failure, then show the zero-input audit passing
the exact field-item verifier against the retained terminal. The eligible success produces Model120
with120 examples/82 successes while the save remains at86 registrations/66 living species/70
specimens. End on the next action-free menu—routed restoration versus trainer resupply—before a
Model120 sample or execution.

[Prior session and evidence](work-sessions/2026-09-13-model120-frozen-field-restore.md)

## The real finish line

State Pete's requirement directly: finish Red from a fresh game with model-directed decisions
and the full local Red Pokédex before trying a ROM hack. The earlier checkpoint-based story
result is not that full run. The current native-availability checklist is not the full Dex.
Version, trade and event dependencies must be resolved openly.

Then show the long horizon: complete Red → compatible unfamiliar Red modification →
Crystal → at least Emerald, with one shared registration ledger that never fabricates local flags.

## Useful flashbacks

- [Model114 fishing success](work-sessions/2026-09-13-model114-frozen-fishing-learning.md):
  one learned destination choice adds a missing registration.
- [Automatic fishing failure](work-sessions/2026-09-13-model112-automatic-fishing-failure-learning.md):
  a route failure becomes an honest learning example.
- [Checkpoint story audit](audits/red-phase4-closeout-2026-09-09.md):
  show the achievement and the forced/deterministic authority caveat together.

Never loop old footage as current gameplay. Do not convert120 training examples into a
whole-project completion percentage or imply that low-level control is learned.
[Project story](project-narrative.md) · [Current roadmap](development-roadmap.md)
