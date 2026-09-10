# Current development handoff

Updated September 10, 2026. This is the single operational summary; older reports are [historical](docs/history/handoff-through-2026-09-10.md).

## Goal and current scope

Build a learned player that finishes stories and accumulates verified Pokédex registrations across games. Red first; global registration, local owned flags and physical specimens remain distinct. No level-100 quota or simultaneous living-form requirement.

The active lane is registered-objective collection learning. The learned component chooses goals/destinations; deterministic skills execute mechanics. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) before implementation.

## Last verified gameplay: batch Z

- Two of four goals succeeded: safety resupply and sampled team recovery. Both Mt. Moon destination searches exhausted their bounds without a catch.
- **59 registrations, 51 physical specimens, 47 living species** independently verified.
- Three actual outcomes fitted: **56→59 examples**. The first safety step added no example; registrations stayed at59.
- Saved in Mt. Moon B1F, map60 row17 col10; field-ready, outside battle, no pending trainer.
- Supplies: four capture items and138 money. Gameplay is stopped.
- [Collection report](docs/work-sessions/2026-09-10-preparation-collection.md) · [Learning evidence](docs/evidence/red-preparation-collection-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-preparation-collection-saved-2026-09-10.json).

Exact continuation identities:

- Episode: `red-registered-collection-20260910-z-04-causal`
- Checkpoint: `9773887b5aaafe1369fb1d99443c885036d77350028bd2547e3622496ce5c1a5`
- Model: `46967672cce37dc553b01b30f1b81e24d8a8769a9f26bc987164bf0ac31ec7c2`
- Corpus: `468be6be346077edf4602998aad81bf0c187ff58515c0b37f558523bec7b4d53`

Private storage locations and complete continuation arguments remain in private operational notes, not Git.

## This session

PR237 merged as `8431ebe5` after required CI34512379244 passed. Z played published source `6b8ca9eb`, with a small call-local reuse of already-verified episode snapshots. Preparation measured44.830→28.290seconds on the same saved input; this is one comparison, not a whole-batch speed guarantee. Integrity, fresh-read and mismatched-binding regressions passed.

The Z launcher is consumed and must never run again. Z01 was nontraining safety support; Z02 recovery and Z03/Z04 failed searches each added one example. Both destination choices exposed three alternatives. Z04 now owns both the latest save and model59. The batch used1,822actions/81,144frames/900.341seconds. Read-only decoding verified all saved collection and model facts.

## Next bounded development session

1. Confirm this handoff against saved evidence and private operational notes.
2. Continue from Z with all four Z checkpoint/source transitions, including support, and model59. No new Z evolution transition was recorded. Do not restore Y as latest or retry Z.
3. Inspect the64-leg patrol cap: Z's surveys stopped after two/four destination encounters. Test a source-agnostic prospective search dose while preserving old profile identities, resource guards and action/frame limits. Time-box repair to45minutes; do not change historical outcomes.
4. Then play fresh bounded choices and retain actual costs. Allow roughly60–90minutes including audit; stop on safety/authentication failure or the declared bounds. Training-history validation remains costly, but another general caching project is not the next objective.
5. Verify saved collection/model outcomes, then update the current summary and append one dated session report.

Travel capture followed by route resumption remains unqualified: its named checklist is1/3, not a whole-project percentage. Stone evolution and broader collection mechanics remain incomplete. Do not force a destination just to close a checklist.

No full replay, sealed Red evaluation, Crystal execution, consumed-trial retry or automatic specimen release. New independent performance claims need genuinely separate evaluation lineages.

## Documentation and review

Keep this file current by replacing sections, not stacking new “Current” headings. Preserve details in [session reports](docs/work-sessions) and [historical index](docs/history/README.md). See [roles](AGENT_COORDINATION.md) and [next-step strategy](docs/model-first-roadmap.md).
