# Capture-Helper Readiness Diagnostic and Seam Analysis

## Codex adjudication

Accepted the diagnostic/test draft after25 actual targeted test passes; corrected
nullable typing, an unused import, formatting and broad exception swallowing.
The exact live helper was asleep with27/27 HP and15 Sing PP. This establishes
persistent status after this withdrawal, not every proposed boxed-health claim.
Rejected the suggested boxed HP-ratio filter as ready to implement: this box
view does not expose maximum HP. Do not use the speculative nurse coordinates
below as a route. Existing observation-backed Center routing owns that boundary.

Codex separately added explicit, verified Center restoration inside the selected
capture preparation, with counted actions/frames, no extra label, and fresh
readiness/inventory checks.218 integration tests and four-module typing passed
before gameplay. This is not a new successful live recovery claim yet.

The remaining memo is Flash's advisory draft, not independent gameplay evidence.

- Branch: `agent/flash-capture-readiness-20260909`
- Baseline: `209558a8`
- Date: 2026-09-09
- Author: Flash 3.8 High (drafting for Codex review)

## Context and Product Alignment

Under [MISSION.md](../../MISSION.md), [NORTH_STAR.md](../../NORTH_STAR.md), and the active
product state ([ACTIVE_PRODUCT_STATE.md](../../ACTIVE_PRODUCT_STATE.md)), the project's goal
is a transferable learned player that accumulates one verified shared registered Pokédex
across mainline titles. Living-specimen completion and level-100 stretch targets were
retired on September 9, 2026: acquisition routes capture missing lines, evolve only as
necessary for missing entries, and deposit unneeded specimens.

Live registered-objective learning is currently active: three real outcomes, two fits,
and a saved `model3` that has not yet played. Deterministic capture helper preparation
(PC substitution for sleep/paralysis support) is oracle execution support, not learned combat
or policy decisions.

## Prior Attempt Failure Analysis

Live session sequence 3 stopped during capture party preparation with:
`RedCapturePartyError: withdrawn capture helper is not actually ready`
(177 actions, 10,896 frames; recorded in
[evidence](../evidence/red-registered-live-learning-2026-09-09.json)).
The failure safely halted execution before entering wild encounter routing, preserving both
the durable ledger and cartridge inventory. However, the exception string provided zero
diagnostic context regarding *why* the party failed readiness.

### Root Cause Asymmetry: Box Selection vs. Party Readiness

Inspection of `red_capture_party.py`, `capture_support.py`, and `red_capture_support.py`
reveals a fundamental observational asymmetry:

1. **Boxed Helper Selection (`plan_capture_party`)**:
   Inspects `RedBoxMoveMember` instances from `reader.read_current_box_move_members()`.
   `RedBoxMoveMember` exposes only `(box_slot, species_id, level, moves, pp)`.
   It checks only whether a boxed Pokémon knows a move with `pp > 0` that
   `RED_BATTLE_CATALOG.capture_status_effect` classifies as sleep or paralysis.
   It has **no visibility** into boxed HP, maximum HP, or status condition.

2. **Party Readiness Evaluation (`capture_party_ready` / `choose_capture_status`)**:
   Evaluates `party: PartyObservation` against strict battle safety criteria:
   - Move has `current_pp > 0` and pure sleep/paralysis effect (`red_capture_status_options`).
   - Party member status is strictly `StatusCondition.HEALTHY`.
   - Party member HP ratio satisfies `member.hp_ratio > 0.50` (strictly greater than 50%).

In Gen 1 Pokémon Red, withdrawing a Pokémon from the PC storage box does not restore health
or cure status conditions. If the candidate was previously boxed while fainted (`hp == 0`),
damaged (`hp / max_hp <= 0.50`), or statused (poison, burn, sleep, paralysis, freeze),
withdrawing it produces an active party member that is immediately rejected by
`capture_party_ready`.

Codex is independently inspecting the saved cartridge state. We do not assume which specific
defect occurred in the retained endpoint; instead, we address the complete space of failure modes.

## Anti-Drift and Non-Negotiable Boundaries

1. **Do NOT weaken readiness predicates**:
   Relaxing the `hp_ratio > 0.50` threshold or allowing non-healthy status conditions would
   send vulnerable Pokémon into wild encounters, causing immediate faints, tempo loss, or party
   wipes. The readiness threshold exists for battle survivability.
2. **Do NOT introduce hidden healing or save edits**:
   Fabricating boxed HP, resetting party HP/status in memory, or bypassing game mechanics
   violates the anti-drift contract. All recovery must use legitimate in-game actions.
3. **Do NOT rewrite routers or inject automatic healing**:
   The PC withdrawal executor operates at the PC tile `(4, 13)`. Arbitrarily scripting nurse
   interactions within `execute_capture_party_at_pc` would blur component boundaries and risk
   unhandled menu or position drift.

## Changes Made in this Draft

### 1. Semantic Error Diagnostics (`src/pokemon_red_completion/red_capture_party.py`)

Added `explain_capture_party_unready(party, expected_helper)`:
- Examines semantic observations only: species ID, slot, level, HP, max HP, status condition,
  known move IDs, remaining PP, and battle catalog effects.
- Contains no file paths, ROM offsets, memory addresses, or private coordinates.
- Specifically distinguishes:
  - Fainted helpers (`fainted (hp 0/{max_hp})`).
  - Low HP with exact percentage vs. threshold (`low HP (20/40 = 50.0%, requires > 50.0%)`).
  - Specific persistent status conditions (`status condition 'poison'`).
  - PP exhaustion on status moves (`status moves out of PP (move 95)`).
  - Unsuitable move sets (`unsuitable moves (no sleep/paralysis move)`).
  - Expected helper species mismatch or empty party state.
  - Whole-party disqualification breakdown.
- Updated `execute_capture_party_at_pc`:
  `raise RedCapturePartyError(f"withdrawn capture helper is not actually ready: {diagnostic}")`
- Preserves existing regex matching (`match='not actually ready'`) in all callers and tests.

### 2. Discriminating Regression Suite (`tests/test_red_capture_readiness_regression.py`)

Added 13 comprehensive unit and mock PC execution tests covering:
- `test_zero_pp_helper_fails_capture_readiness`: Verifies 0 PP status moves fail readiness and diagnostic reports PP exhaustion.
- `test_unsuitable_moves_helper_fails_capture_readiness`: Verifies damaging/non-status moves fail readiness.
- `test_fainted_helper_fails_capture_readiness`: Verifies `hp == 0` fails readiness with fainted diagnostic.
- `test_low_hp_helper_below_half_fails_capture_readiness`: Verifies `hp_ratio < 0.50` fails with percentage diagnostic.
- `test_exact_half_hp_threshold_boundary`: Verifies exact boundary condition—`25/50 (50.0%)` strictly fails while `26/50 (52.0%)` succeeds.
- `test_status_afflicted_helper_fails_capture_readiness`: Parametrized across `POISON`, `BURN`, `SLEEP`, `PARALYSIS`, `FREEZE`, and `TOXIC`.
- `test_changed_party_state_species_mismatch`: Verifies diagnostic on unexpected party composition.
- `test_empty_party_state_diagnostic`: Verifies diagnostic on empty party.
- `test_execute_capture_party_at_pc_reports_*`: Five end-to-end mock PC tests verifying that `execute_capture_party_at_pc` raises `RedCapturePartyError` with the exact corresponding diagnostic string.
- `test_execute_capture_party_at_pc_succeeds_when_helper_is_ready`: Verifies happy path completion when withdrawn helper is fully ready.

## Architectural Seam Analysis for Codex Review

To resolve the underlying live failure without weakening readiness or faking state, two
complementary seams should be considered in Codex's session:

1. **Boxed Health/Status Observation Seam**:
   In Gen 1, the 33-byte `box_struct` stores current HP at offset 1–2 and status condition at
   offset 4 (matching `party_struct`). Currently, `observation.py`'s `read_current_box_move_members()`
   intentionally reads only moves and PP. If an extended box reader observes stored HP and status,
   `plan_capture_party` can pre-filter candidates in the PC box, selecting only helpers that are
   *already* healthy and above 50% HP. If no healthy helper exists in storage, the goal is
   correctly marked unavailable before traveling to the PC.

2. **Legitimate In-Center Recovery Seam**:
   When a player is standing at the PC in a Pokémon Center (`map_id`, `(4, 13)`), Nurse Joy is
   accessible within the same room (`(3, 1)` or `(3, 3)` depending on the center). If a withdrawn
   helper is damaged or statused, the router can sequence an ordinary, legitimate Pokémon Center
   healing interaction to restore the entire party before departing for wild encounters.

## Six-Part Mission Check

1. **Capability**: Clear semantic diagnostics and discriminating verification for capture helper readiness.
2. **Learned authority**: Preserves model-directed capture goal choice without falsifying failure outcomes.
3. **Transfer test**: ROM-free semantic party structures applicable across titles; no revision-specific hacks.
4. **Cheapest falsifier**: `test_exact_half_hp_threshold_boundary` and mock PC diagnostic tests.
5. **Time box**: Single isolated drafting pass.
6. **Stop condition**: Clean diagnostic integration, comprehensive regression suite, and zero uncommitted files outside scope.

## Exact Changed Files

1. `src/pokemon_red_completion/red_capture_party.py` (edited)
2. `tests/test_red_capture_readiness_regression.py` (new file)
3. `docs/audits/flash-capture-readiness-2026-09-09.md` (new file)

## Unrun Tests for Codex Verification

Per instructions, no shell or terminal commands were executed. The following test files
must be run by Codex:
- `pytest tests/test_red_capture_readiness_regression.py`
- `pytest tests/test_red_capture_party.py`
- Full regression suite / typecheck: `pytest` and `mypy src/pokemon_red_completion/red_capture_party.py`
