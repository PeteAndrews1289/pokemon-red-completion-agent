> Codex adjudication: corrected draft passed82 targeted tests including68 existing
> surge cases. Default false-on-no-balls was rejected because it prolongs a survey
> with no supplies. Original resource failure now follows verified battle exit.
> Battle-state zero alone is not input-readiness or cross-game transfer evidence.

# Bounded Capture Ball Exhaustion Repair and Escape Verification

## Memo for Codex Review (Revision 2)

- **Branch**: `agent/flash-capture-exhaustion-20260909`
- **Baseline**: `f9ea06e9`
- **Date**: 2026-09-09
- **Author**: Flash 3.8 High (drafting role authorized by Pete for Codex review)

---

## 1. Context and Product Alignment

Under [MISSION.md](../../MISSION.md), [NORTH_STAR.md](../../NORTH_STAR.md), and [ACTIVE_PRODUCT_STATE.md](../../ACTIVE_PRODUCT_STATE.md), the project product is a transferable hierarchical agent that completes stories and accumulates one verified registered Pokédex across mainline titles. Simultaneous living-form completion and level-100 targets were retired on September 9, 2026.

In the latest session (`2026-09-09-capture-helper-recovery`), Model5 reloaded with 5 registered-objective examples, selected Route 15 from two alternatives, and executed live gameplay. During Attempt 3, ordinary capture balls were exhausted mid-battle. `_try_catch_wild` in `surge.py` immediately raised:
```python
SurgeChapterError(f"{label} capture has no ordinary capture balls remaining.")
```
Because this exception was raised while `raw.battle_state == 1` (mid-encounter), execution terminated inside an active wild battle. The terminal safe-checkpoint guard correctly refused the unfinished battle state (`battle_state != 0`). The raw failure state was preserved with SHA `6c7378f5...` as an unadmitted failure, leaving Attempt 4 unclaimed and the batch stopped.

### Non-Negotiable Operating Boundaries
- **No Checkpoint Weakening**: The safe-checkpoint guard requiring `battle_state == 0` is essential anti-drift protection and must never be weakened or bypassed. Note that `battle_state == 0` alone does not assert an input-ready field; downstream checkpoint guards verify actual input-readiness.
- **No Falsified State or Mechanics**: Never silently flee a trainer battle, throw a Master Ball, fake HP/resources, edit memory, or issue synthetic capture success.
- **Honest Failure Retention**: Attempt 3 remains an unadmitted failure; costs are permanently retained, and retry of consumed attempts is forbidden.
- **Preserve Valid-Capture Path**: Existing valid-capture and throw-exhaustion flee paths remain intact with no new success claims.
- **Strict Role Boundary**: Flash only drafts surgical code modifications and independent ROM-free tests. Codex owns execution, validation, adjudication, and live recovery. Flash ran no shell commands or tests.

---

## 2. Root Cause and Surgical Design

### Root Cause
In `src/pokemon_red_completion/surge.py`, `_try_catch_wild` previously checked:
```python
starting_inventory = _ordinary_capture_ball_inventory(_bag(emulator))
starting_balls = sum(starting_inventory)
starting_specimens = _living_specimen_count(reader)
if starting_balls <= 0:
    raise SurgeChapterError(f"{label} capture has no ordinary capture balls remaining.")
```
If an encounter began with zero ordinary capture balls (e.g., following ball exhaustion in a prior encounter during an area survey), `_try_catch_wild` raised immediately without fleeing the live encounter, leaving the emulator trapped in `battle_state == 1`.

### Surgical Repair in `_try_catch_wild`
Following Codex's adjudication, we implemented the following bounded repair:

1. **Upfront Trainer Battle Rejection (Before Any Capture Inputs)**:
   - At the entry of `_try_catch_wild`, `raw = reader.read()` is immediately inspected.
   - If `raw.battle_state == 2`, raises `SurgeChapterError(f"{label} capture cannot target a trainer battle.")` before attempting any menu navigation, inputs, or throws.
   - Verifies active wild encounter (`raw.battle_state == 1`; rejects `battle_state == 0` or non-wild states).

2. **Bounded Escape on Ball Exhaustion (`starting_balls <= 0`)**:
   - Calls the established `_flee(emulator, executor, reader, raw)` helper to legitimately escape the wild battle.
   - Reuses existing bounded controls in `_flee`: 16 bounded RUN attempts, 128 transition pulses, party species preservation, PP preservation, and forced switch to living team members on faints. Escape failures raise from `_flee` without suppression.

3. **Post-Escape Verification**:
   - Inspects `post_escape = reader.read()` and verifies `post_escape.battle_state == 0`. If active, raises `SurgeChapterError(f"{label} flee did not end the encounter.")`.
   - Verifies living specimen count: `_living_specimen_count(reader) == starting_specimens`. If altered, raises `SurgeChapterError(f"{label} no-balls exit changed the living collection.")`.
   - Verifies ball accounting: `_ordinary_capture_ball_total(_bag(emulator)) == starting_balls` (zero). If altered, raises `SurgeChapterError(f"{label} no-balls exit changed ordinary-ball accounting.")`.

4. **Codex Decision: Unconditional Exhaustion Exception after Safe Exit**:
   - Removed the optional `raise_on_exhaustion` parameter.
   - Rather than returning `False` (which would allow survey walkers to roam and trigger further wild encounters while possessing zero supplies), `_try_catch_wild` safely exits to `battle_state == 0`, validates all invariants, and **unconditionally preserves and raises the original exception**:
     ```python
     raise SurgeChapterError(f"{label} capture has no ordinary capture balls remaining.")
     ```
   - This halts the survey honestly with zero balls at a clean, un-wedged field boundary (`battle_state == 0`).

---

## 3. Fixture and Test Suite Improvements

In response to Codex's review of the initial draft:
1. **Fixture Command Responsiveness (`_StatefulBattleSimulator`)**:
   - Fixed the fixture to respond to actual requested `MOVE` commands via a 2x2 battle-menu grid model (`(0, down)->1`, `(0, right)->2`, `(1, up)->0`, `(1, right)->3`, `(2, left)->0`, `(2, down)->3`, `(3, up)->2`, `(3, left)->1`).
   - Removed the broken `_navigate_main` no-op monkeypatches that previously caused `Flee exceeded 16 RUN attempts`. `_navigate_main` now executes directly against the fixture.
   - Handled cyclic throw confirmations (`throw_confirmations % 2 == 0`) for multi-throw sequences and throw exhaustion flee.
2. **Upfront Trainer Battle Refusal**:
   - Both `test_trainer_battle_refusal_without_balls` and `test_trainer_battle_refusal_with_balls_available` verify immediate rejection before any battle-menu navigation or inputs.
3. **All 14 Test Cases Preserved**:
   - Retained all covered test scenarios (initial zero-ball escape + raise, boundary check, multi-encounter sequence, multi-attempt flee, bounded 16-attempt propagation, post-flee uncleared battle detection, specimen tampering detection, ball tampering detection, trainer battle refusals with/without balls, non-battle refusal, master ball isolation, untouched valid capture, and untouched throw exhaustion flee).

---

## 4. Six-Part Mission Check

1. **Reusable Capability**: Legitimate, bounded escape from wild battles upon capture resource exhaustion, settling at a clean field boundary before signaling exhaustion.
2. **Learned Authority**: Preserves model-directed destination selection without falsifying attempt results or bypassing game mechanics.
3. **Transfer Test**: The invariant check verifies semantic `battle_state`, inventory, and specimen counts in Pokémon Red without leaking raw addresses or title-specific internals into high-level planning.
4. **Cheapest Falsifier**: Independent ROM-free tests asserting upfront refusal of trainer battles, propagation of RUN-attempt exhaustion, and detection of post-escape state mismatches.
5. **Time Box**: 1 single drafting session; bounded surgical edit.
6. **Stop Condition**: Clean field boundary reached (`battle_state == 0`), zero specimen/ball drift, and honest `SurgeChapterError` raised.

---

## 5. Exact Files Modified

1. `src/pokemon_red_completion/surge.py`: Upfront trainer battle rejection in `_try_catch_wild`, removal of `raise_on_exhaustion` argument, safe escape via `_flee`, post-flee invariant checks, and unconditional exhaustion exception.
2. `tests/test_capture_ball_exhaustion.py`: 14 ROM-free tests with responsive 2x2 grid navigation fixture and updated assertions reflecting the unconditional safe-exit raise.
3. `docs/audits/flash-capture-exhaustion-2026-09-09.md`: This audit memo.

---

## 6. Unrun Tests for Codex Verification

Per role instructions, Flash did **not** execute any commands, tests, or shell scripts. Codex owns test execution and live recovery.

Codex should run the following commands locally:
```bash
pytest tests/test_capture_ball_exhaustion.py
pytest tests/test_surge.py
pytest tests/test_red_acquisition.py
python scripts/check_product_focus.py
```
