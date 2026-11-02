"""Teacher-only setup on a newly authenticated opening; never an actor action.

Use the same pinned lab exit layout as the existing gift/Safari adapters.
The cartridge loads the destination. No old save, money or story flags are copied.
"""

from .observation import SQUIRTLE_SPECIES_ID, EventFlag, MapId, RamAddress
from .red_safari_training_setup import RED_ROM_SHA256


def assisted_progress_baseline(
    raw, *, state_sha256, checkpoint_id, earned_objective_ids,
    setup_receipt_sha256, isolated_training_setup, partition,
    synthetic_objective_ids=(),
):
    if isolated_training_setup is not True or partition != "train":
        raise ValueError("assisted progress needs an explicit isolated TRAIN source")
    return _assisted_progress_baseline(raw, state_sha256=state_sha256,
        checkpoint_id=checkpoint_id, earned_objective_ids=earned_objective_ids,
        setup_receipt_sha256=setup_receipt_sha256,
        isolated_training_setup=isolated_training_setup, partition=partition,
        synthetic_objective_ids=synthetic_objective_ids)


def _assisted_progress_baseline(
    raw, *, state_sha256, checkpoint_id, earned_objective_ids,
    setup_receipt_sha256, isolated_training_setup, partition,
    synthetic_objective_ids=(),
):
    """Disclose a synthetic prerequisite baseline; never label it earned play.

    Teacher fixtures can expose a later native event without having played its
    predecessors. Close that *scenario context* over the existing quest graph,
    retaining exactly which facts are synthetic in a source-bound receipt. The
    ordinary observer remains strict. Caller must retain this receipt in the
    lesson's authenticated setup chain before input; no campaign may use it.
    No game bytes, cash, inventory, registrations or model parameters are edited.
    """
    import re

    from .captured_progress import CapturedProgressEnvelope
    from .domain import GameMode, GameState
    from .observation import RawGameState, semantic_facts
    from .route import COMPLETION_QUEST

    if (isolated_training_setup is not True or partition not in ("train", "development")
        or not isinstance(raw, RawGameState) or raw.battle_state != 0
        or type(earned_objective_ids) is not tuple
        or any(not isinstance(x, str) for x in earned_objective_ids)
        or len(set(earned_objective_ids)) != len(earned_objective_ids)
        or type(synthetic_objective_ids) is not tuple
        or any(not isinstance(x, str) for x in synthetic_objective_ids)
        or len(set(synthetic_objective_ids)) != len(synthetic_objective_ids)
        or any(not isinstance(s, str) or not re.fullmatch(r"[0-9a-f]{64}", s)
               for s in (state_sha256, setup_receipt_sha256))):
        raise ValueError("assisted progress needs an explicit isolated TRAIN source")
    graph = COMPLETION_QUEST
    known = {o.id for o in graph}
    earned = set(earned_objective_ids)
    synthetic = set(synthetic_objective_ids)
    if not synthetic <= known or synthetic & earned:
        raise ValueError("declared synthetic prerequisites must be known and not called earned")
    if not earned <= known or any(not graph.objective(i).prerequisites <= earned for i in earned):
        raise ValueError("original earned objective history is inconsistent")
    observed = set(graph.completed_ids(GameState(
        mode=GameMode.OVERWORLD, facts=frozenset(semantic_facts(raw)))))
    baseline = earned | observed | synthetic
    while True:
        expanded = baseline | {p for i in baseline for p in graph.objective(i).prerequisites}
        if expanded == baseline:
            break
        baseline = expanded
    envelope = CapturedProgressEnvelope(
        state_sha256, checkpoint_id,
        f"ASSISTED {partition.upper()} context: synthetic prerequisites, not earned progression",
        len(baseline), len(known), tuple(sorted(baseline)),
    )
    receipt = dict(
        schema="pokemon.red.assisted-player-progress-baseline.v1",
        partition=partition, state_sha256=state_sha256,
        setup_receipt_sha256=setup_receipt_sha256,
        original_earned_objectives=sorted(earned),
        native_visible_objectives=sorted(observed),
        synthetic_baseline_objectives=sorted(baseline - earned),
        inferred_prerequisites=sorted(baseline - earned - observed),
        earned_objective_gain=0, campaign_eligible=False,
        envelope=envelope.to_dict(),
    )
    if synthetic:
        receipt["declared_synthetic_objectives"] = sorted(synthetic)
    return envelope, receipt


def prepare_center_restore_fixture(
    memory, *, rom_sha256, isolated_training_setup, controller_released, battle_state,
):
    if (rom_sha256 != RED_ROM_SHA256 or isolated_training_setup is not True
        or controller_released is not True or type(battle_state) is not int
        or battle_state != 0):
        raise ValueError("Center fixture requires isolated released Red field control")
    expected = {
        int(RamAddress.CURRENT_MAP): int(MapId.OAKS_LAB),
        int(RamAddress.OAKS_LAB_SCRIPT): 10,
        int(RamAddress.PARTY_COUNT): 1,
        int(RamAddress.PARTY_SPECIES): SQUIRTLE_SPECIES_ID,
        int(RamAddress.PARTY_MON_1_STATUS): 0,
        0xD3AE: 2, 0xD365: int(MapId.PALLET_TOWN),
        **{0xD3AF + i: b for i, b in enumerate((11, 4, 2, 255, 11, 5, 2, 255))},
    }
    hp = int(RamAddress.PARTY_MON_1_HP)
    maximum = int(RamAddress.PARTY_MON_1_MAX_HP)
    health = int(memory[hp]) * 256 + int(memory[hp + 1])
    cap = int(memory[maximum]) * 256 + int(memory[maximum + 1])
    if (any(int(memory[a]) != value for a, value in expected.items())
        or not 1 < health <= cap
        or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("Center fixture fresh opening differs")
    changes = {
        int(RamAddress.OAKS_LAB_SCRIPT): 18,
        0xD365: int(MapId.VIRIDIAN_CITY),
        0xD3B1: 0, 0xD3B2: int(MapId.VIRIDIAN_POKECENTER),
        0xD3B5: 0, 0xD3B6: int(MapId.VIRIDIAN_POKECENTER),
        hp: 0, hp + 1: 1,
    }
    receipt = tuple(dict(address=a, before=int(memory[a]), after=value)
                    for a, value in sorted(changes.items()))
    for row in receipt:
        memory[row["address"]] = row["after"]
    if any(int(memory[row["address"]]) != row["after"] for row in receipt):
        raise ValueError("Center fixture write readback failed; retain terminal")
    return receipt


def prepare_mart_fixture(
    memory, *, rom_sha256, isolated_training_setup, controller_released, battle_state,
):
    """Disclosed store prerequisites; native loading and purchase stay in cartridge.

    Does not supply money/items or transplant prior-save bytes. Artificial errand
    flags are baseline fixture facts, never story gains or actual battle history.
    """
    if (rom_sha256 != RED_ROM_SHA256 or isolated_training_setup is not True
        or controller_released is not True or type(battle_state) is not int
        or battle_state != 0):
        raise ValueError("Mart fixture requires isolated released Red field control")
    expected = {
        int(RamAddress.CURRENT_MAP): int(MapId.OAKS_LAB),
        int(RamAddress.OAKS_LAB_SCRIPT): 10,
        int(RamAddress.PARTY_COUNT): 1,
        int(RamAddress.PARTY_SPECIES): SQUIRTLE_SPECIES_ID,
        0xD3AE: 2, 0xD365: int(MapId.PALLET_TOWN),
        **{0xD3AF + i: b for i, b in enumerate((11, 4, 2, 255, 11, 5, 2, 255))},
    }
    if (any(int(memory[a]) != v for a, v in expected.items())
        or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("Mart fixture fresh opening differs")
    changes = {
        int(RamAddress.OAKS_LAB_SCRIPT): 18,
        int(RamAddress.VIRIDIAN_MART_SCRIPT): 2,
        0xD365: int(MapId.VIRIDIAN_CITY),
        0xD3B1: 0, 0xD3B2: int(MapId.VIRIDIAN_MART),
        0xD3B5: 0, 0xD3B6: int(MapId.VIRIDIAN_MART),
    }
    for flag in (EventFlag.GOT_POKEDEX, EventFlag.GOT_OAKS_PARCEL, EventFlag.OAK_GOT_PARCEL):
        address = int(RamAddress.EVENT_FLAGS) + int(flag) // 8
        changes[address] = changes.get(address, int(memory[address])) | 1 << (int(flag) % 8)
    receipt = tuple(dict(address=a, before=int(memory[a]), after=v)
                    for a, v in sorted(changes.items()))
    for row in receipt:
        memory[row["address"]] = row["after"]
    if any(int(memory[row["address"]]) != row["after"] for row in receipt):
        raise ValueError("Mart fixture readback failed; retain terminal")
    return receipt
