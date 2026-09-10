# Flash safe capture-lead prototype — September 7

## Latest — direct-write recovery draft reviewed, live qualification pending

User-authorized scoped file permissions resolved the earlier access limitation below.
Flash wrote a routed Center recovery adapter and tests directly in the isolated tree.
The first draft failed collection on nonexistent imports. After concrete feedback,
the revision passed 11 tests and failed four on invented controller-action fields.
Draft commit `10f346f5` preserves that state. Codex brought it into an integration
branch, corrected it, and added independent protection against changed member levels,
PP, moves, max HP, counts and player position.

Codex also connected an opt-in recovery mode, authenticated parent-mode restoration,
an actual escort swap with fresh verification, and source admission that refuses
a fainted party before prediction, commitment or controller input. No changed
historical checkpoint hashes, old-outcome deletion or manufactured recovery labels.

The combined targeted suite passes **272 tests**. This includes simulated Center
provider execution and independent failures, not a private-ROM or live battle test.
The source remains local/unpublished. No gameplay or fitting occurred this turn.
Capture lead qualification before hazardous capture travel/search and after PC
changes remains unfinished; legitimate AA recovery and model63 execution follow
only after that connected path is qualified. Raw draft claims below are historical
agent reports and are superseded by these independently checked results.

Flash's revision took about twelve minutes and still needed Codex correction:
use smaller interface-bounded tasks, not sweeping architecture generation. No Claude
review was spent. Service quota after completion: Gemini 82.97% five-hour / 94.58%
weekly remaining; separate Claude 83% / 92%. Reset times are in the current handoff.

## Earlier pure-planner session

Advisory prototype from Gemini 3.8 Flash High, transcribed and compacted by Codex
into an isolated branch. Not integrated or live-qualified. This is maintenance
unblocking the next learned acquisition, not a learning result.

## Mission check

1. Capability: connect recovery, escort preparation and capture without inheriting an unsafe lead.
2. Learned authority: unchanged by this component; unblock model63's next genuine source choice.
3. Transfer test: altered party orders, health, PP and duplicate same-species individuals.
4. Cheapest falsifier: reject a Harden-only lead and distinguish the actual selected escort
   from an incorrect same-species swap in ROM-free tests, before any retained-state play.
5. Time box: 20-minute prototype/review; stop and hand off remaining integration.
6. Stop condition: absent suitable escort, stale plan or incorrect swap. No artificial model row.

## Integration blueprint

- `RedFieldRestoreGoalProvider` cannot revive fainted members. `RedCenterRestoreGoalProvider`
  can heal them, but needs the existing nurse boundary. Compose walking transport to that
  boundary; do not confuse missing routing with missing healing mechanics.
- `RedResourceGoalRouter` routes capture, Mart and evolution, not Center restore.
- `gen1_party_menu.swap_party_slots` is an existing indexed swap verifying species, HP and moves.
  Reuse its executor only after qualifying its real menu behavior; this pure planner executes nothing.
- Qualify an escort before the recovery trip and any other hazardous travel. A healthy escort
  alongside a fainted member permits guarded recovery, not ordinary capture permission.
- Reobserve and replan after any party swap or PC substitution: previously recorded slots are stale.
- Heal first when mandatory, then let the model choose genuine destination alternatives BEFORE
  destination-specific travel. Do not manufacture training examples for forced preparation.
- Requalify after helper withdrawal and before source search, including the helper-already-present
  path that currently returns without preparation. Preserve the selected source when rebinding.
- All composed opportunities affect historical fingerprints. Verify the old save with its original
  observer behavior, then enable new execution behavior; an old profile alone does not freeze code.
- Refusal before a meaningful attempt is not source-performance evidence. Codex owns that admission
  fix separately. Keep the actual AA failed attempt and model63 intact.

Selection is a conservative health/offense heuristic, not proof of route safety or the best escort.
Fixed-damage moves with zero catalog power remain unsupported. No specimen identity is invented
for two members identical in every observed field. No runtime integration, gameplay or fitting here.

## Codex review

The first draft passed its 11 proposed tests. Independent review tests exposed two
self-destructive-only move cases and an inconsistent preparation-error contract:
three failures, twelve passes. Codex excluded self-destructive moves from qualifying
offensive capacity, translated only the catalog's known error into the preparation
error, and added an oversized-threshold rejection test. This does not prevent an
executor from choosing a dangerous move later; battle safety remains a separate
integration requirement, especially for a member with both normal and dangerous moves.

The raw blueprint's Drowzee-specific expectation and statement that Center healing
rejects fainted members were corrected during transcription. No species is prescribed
by the selector. Center healing is precisely the existing means to revive this party.

CLI file access was denied in the new worktree. No permission bypass was used:
Flash produced source from a bounded code packet, and Codex transcribed/compacted it
into the isolated branch before testing. Do not describe this as autonomous repository
editing or a repository-wide architecture audit. The raw draft and reviewed successor
are kept in separate local commits; neither is a live gameplay result.

Final local ROM-free check: 39 tests passed across the new planner/review tests and
existing capture-party, routed-support and indexed party-menu tests. This establishes
the isolated planning behavior, not safe live transport. Next Codex must connect the
recovery and execution boundaries, exercise stale plans across actual swaps, and verify
the old-save/new-runtime boundary before promoting this into the active player.

## Routed Center recovery prototype

- Implemented `bind_routed_center_recovery` in `src/pokemon_red_completion/red_routed_recovery.py`.
- Connects escort preparation with walking transport to a real Center nurse boundary (x=3, y=7), nursing approach, dialogue handling, and independent state verification.
- Replaces/creates unavailable `RESTORE_TEAM` without overwriting available skills or duplicating kind.
- Enforces strict pre-input state verification (rejecting stale HP/traversal/ledger/resources before escort callback).
- Meters all prep, transport, and heal frames and actions from before execution.
- Halts transport immediately if a post-battle new faint occurs or field does not settle.
- Verifies full party restoration (`_raw_party_restored`), genuine HP change, and strict preservation of living Pokédex ledger, bag, and money.
- Verified by ROM-free tests in `tests/test_red_routed_recovery.py`.
