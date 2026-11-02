"""TRAIN-only initial afflictions in an isolated, freshly materialized battle.

No writable interface is exposed to a policy. These are disclosed starting
conditions, never changes to an earned campaign or post-decision outcomes.
"""

from dataclasses import dataclass

from .battle_practice_factory import BattlePracticeError
from .observation import (
    PARTY_STATUS_OFFSET,
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
)
from .red_battle_practice_factory import WritableRedMemory, _u16
from .scenario_lab import ScenarioPartition

STATUSES = {"none": 0, "sleep": 2, "poison": 8, "burn": 16, "freeze": 32, "paralysis": 64}


def condition_train_trainer_class(reader, memory, *, partition, trainer_class_id):
    """Choose native opponent AI only in a disclosed, materialized TRAIN opener.

    Trainer class is a Red adapter detail, not a policy input or action. Classes
    1..47 index the cartridge's native move/item AI; no fabricated move outcome
    or campaign identity is supplied. The capture/recipe must bind this receipt.
    """
    if (partition is not ScenarioPartition.TRAIN or type(trainer_class_id) is not int
            or not 1 <= trainer_class_id <= 47):
        raise BattlePracticeError("trainer-class setup requires TRAIN and a native class")
    before = reader.read()
    if (before.battle_state != 2 or not 1 <= before.party_count <= 6
            or not 1 <= (before.enemy_party_count or 0) <= 6
            or before.active_party_index != 0 or before.enemy_party_position != 0
            or not before.party_hp or any(hp <= 0 for hp in before.party_hp)
            or before.battler_hp is None or before.battler_hp <= 0
            or before.enemy_hp is None or before.enemy_hp <= 0
            or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN):
        raise BattlePracticeError("trainer-class setup needs a living materialized TRAIN MAIN")
    address = int(RamAddress.TRAINER_CLASS)
    original = memory[address]
    if not 1 <= original <= 47:
        raise BattlePracticeError("source trainer class is not a native trainer")
    memory[address] = trainer_class_id
    if memory[address] != trainer_class_id or reader.read() != before:
        raise BattlePracticeError("trainer-class setup changed visible state or failed readback")
    return {"schema": "pokemon.red.train-trainer-class-intervention.v1",
            "partition": "train", "before": original, "after": trainer_class_id,
            "teacher_memory_write_count": 1, "actor_memory_writes": 0,
            "semantic_battle_state_unchanged": True,
            "campaign_identity_promoted": False, "native_opponent_ai_condition": True}


def condition_train_struggle(reader, memory, *, partition):
    """Disclosed zero-PP setup, after ordinary TRAIN materialization succeeds."""
    from .observation import PARTY_PP_OFFSET
    from .red_battle_practice_factory import _BATTLE_PP

    before = reader.read()
    if (partition is not ScenarioPartition.TRAIN or before.battle_state != 2
            or before.party_count != 1 or before.active_party_index != 0
            or before.battler_hp is None or before.battler_hp <= 0
            or before.battler_pp != before.active_party_pp
            or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN):
        raise BattlePracticeError("Struggle setup requires single-member TRAIN MAIN")
    addresses = [base + i for base in (_BATTLE_PP, int(RamAddress.PARTY_MON_1) + PARTY_PP_OFFSET)
                 for i in range(4)]
    original = [memory[a] for a in addresses]
    for address in addresses:
        memory[address] = 0
    after = reader.read()
    if (after.battler_pp != (0,) * 4 or after.active_party_pp != (0,) * 4
            or after.battler_moves != before.battler_moves
            or after.party_hp != before.party_hp or after.battler_status != before.battler_status
            or any(memory[a] != 0 for a in addresses)):
        raise BattlePracticeError("Struggle setup failed semantic readback")
    return {"schema": "pokemon.red.train-struggle-intervention.v1", "partition": "train",
            "before": original, "after": [0] * 8,
            "teacher_memory_write_count": 8, "actor_memory_writes": 0}


def condition_train_randomness(reader, memory, *, partition, seed):
    """Teacher-only initial RNG fork; callers authenticate and save a TRAIN child.

    No frames execute here and no policy receives this writable interface. This
    varies native randomness, not semantic state or the result of an action.
    """
    if partition is not ScenarioPartition.TRAIN or type(seed) is not int or not 0 <= seed < 65536:
        raise BattlePracticeError("randomness setup requires TRAIN and a sixteen-bit seed")
    before = reader.read()
    if (before.battle_state != 2 or before.party_count != 1 or before.enemy_party_count != 1
            or before.active_party_index != 0 or before.enemy_party_position != 0
            or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN):
        raise BattlePracticeError("randomness setup requires a single-member MAIN boundary")
    addresses = (int(RamAddress.RANDOM_ADD), int(RamAddress.RANDOM_SUB))
    original = [memory[a] for a in addresses]
    values = [seed >> 8, seed & 255]
    for address, value in zip(addresses, values, strict=True):
        memory[address] = value
    if [memory[a] for a in addresses] != values or reader.read() != before:
        raise BattlePracticeError("randomness setup altered visible state or failed readback")
    return {"schema": "pokemon.red.train-rng-intervention.v1", "partition": "train",
            "seed": seed, "before": original, "after": values,
            "teacher_memory_write_count": 2, "actor_memory_writes": 0}


@dataclass(frozen=True)
class StatusPracticeConditions:
    player_status: str = "none"
    opponent_status: str = "none"
    player_accuracy: int = 0
    opponent_accuracy: int = 0
    disabled_slot: int | None = None

    def __post_init__(self):
        if self.player_status not in STATUSES or self.opponent_status not in STATUSES:
            raise BattlePracticeError("unsupported initial major status")
        if any(
            type(x) is not int or not -6 <= x <= 6
            for x in (self.player_accuracy, self.opponent_accuracy)
        ):
            raise BattlePracticeError("initial accuracy stage differs")
        if self.disabled_slot is not None and (
            type(self.disabled_slot) is not int or not 1 <= self.disabled_slot <= 4
        ):
            raise BattlePracticeError("initial disabled slot differs")


def condition_train_status(
    reader: PokemonRedStateReader,
    memory: WritableRedMemory,
    conditions: StatusPracticeConditions,
    *,
    partition: ScenarioPartition,
) -> dict[str, object]:
    return _condition_train_status(reader, memory, conditions, partition=partition, team=False)


def condition_train_team_status(
    reader: PokemonRedStateReader,
    memory: WritableRedMemory,
    conditions: StatusPracticeConditions,
    *,
    partition: ScenarioPartition,
) -> dict[str, object]:
    """Explicit team TRAIN setup; reserves and every non-status party byte stay fixed.

    This is a freshly materialized starting condition, not a mid-battle repair.
    The single-member API deliberately keeps its original scope.
    """
    return _condition_train_status(reader, memory, conditions, partition=partition, team=True)


def _condition_train_status(reader, memory, conditions, *, partition, team):
    from .observation import PARTY_STRUCT_STRIDE

    if partition is not ScenarioPartition.TRAIN or not isinstance(
        conditions, StatusPracticeConditions
    ):
        raise BattlePracticeError("status conditioning is TRAIN-only")
    before = reader.read()
    if (
        before.battle_state != 2
        or not (2 <= before.party_count <= 6 if team else before.party_count == 1)
        or before.active_party_index != 0
        or not (1 <= (before.enemy_party_count or 0) <= 6
                if team else before.enemy_party_count == 1)
        or before.enemy_party_position != 0
        or before.battler_status != 0
        or before.enemy_status != 0
        or before.player_stat_stages != (7,) * 6
        or before.enemy_stat_stages != (7,) * 6
        or before.player_confused is not False
        or before.enemy_confused is not False
        or before.player_disabled_move_slot
        or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN
    ):
        raise BattlePracticeError("status conditioning needs a clean scoped MAIN boundary")
    party_bytes = {}
    if team:
        if (not before.party_hp or len(before.party_hp) != before.party_count
                or any(hp <= 0 for hp in before.party_hp)
                or before.party_status != (0,) * before.party_count
                or before.enemy_hp is None or before.enemy_hp <= 0):
            raise BattlePracticeError("team status setup needs living clean party members")
        for base, count in ((int(RamAddress.PARTY_MON_1), before.party_count),
                            (int(RamAddress.ENEMY_PARTY_MON_1), before.enemy_party_count)):
            for index in range(count):
                start = base + index * PARTY_STRUCT_STRIDE
                if memory[start + PARTY_STATUS_OFFSET] != 0:
                    raise BattlePracticeError("team status setup needs clean reserve statuses")
                for offset in range(PARTY_STRUCT_STRIDE):
                    party_bytes[start + offset] = memory[start + offset]
    if conditions.disabled_slot and (
        not before.battler_moves or not before.battler_moves[conditions.disabled_slot - 1]
    ):
        raise BattlePracticeError("disabled slot has no move")
    expected_stats = {}
    writes = []
    def put(address, value):
        writes.append({"address": address, "before": memory[address], "after": value})
        memory[address] = value
    for player, status in ((True, conditions.player_status), (False, conditions.opponent_status)):
        value = STATUSES[status]
        battle_status = 0xD018 if player else int(RamAddress.ENEMY_STATUS)
        party_base = int(RamAddress.PARTY_MON_1 if player else RamAddress.ENEMY_PARTY_MON_1)
        for address in (battle_status, party_base + PARTY_STATUS_OFFSET):
            put(address, value)
        # Gen I immediate status penalties affect live stats, not the stored
        # unmodified/party stat blocks. Native turns own all subsequent changes.
        if status in {"burn", "paralysis"}:
            address = int(
                (RamAddress.BATTLE_MON_ATTACK if player else RamAddress.ENEMY_ATTACK)
                if status == "burn"
                else (RamAddress.BATTLE_MON_SPEED if player else RamAddress.ENEMY_SPEED)
            )
            expected_stats[address] = max(
                1, _u16(memory, address) // (2 if status == "burn" else 4)
            )
            put(address, expected_stats[address] >> 8)
            put(address + 1, expected_stats[address] & 255)
    put(int(RamAddress.PLAYER_ACCURACY_STAGE), conditions.player_accuracy + 7)
    put(int(RamAddress.ENEMY_DEFENSE_STAGE) + 3, conditions.opponent_accuracy + 7)
    put(int(RamAddress.PLAYER_DISABLED_MOVE), (
        conditions.disabled_slot * 16 + 3 if conditions.disabled_slot else 0
    ))
    after = reader.read()
    if (
        after.battler_status != STATUSES[conditions.player_status]
        or memory[0xD018] != STATUSES[conditions.player_status]
        or after.enemy_status != STATUSES[conditions.opponent_status]
        or after.player_accuracy_stage != conditions.player_accuracy + 7
        or after.enemy_stat_stages is None
        or len(after.enemy_stat_stages) != 6
        or after.enemy_stat_stages[4] != conditions.opponent_accuracy + 7
        or after.player_disabled_move_slot != conditions.disabled_slot
        or after.player_disable_turns != (3 if conditions.disabled_slot else 0)
        or any(_u16(memory, address) != value for address, value in expected_stats.items())
        or after.party_hp != before.party_hp
        or after.battler_pp != before.battler_pp
    ):
        raise BattlePracticeError("status conditioning readback differs")
    if team:
        expected_party = dict(party_bytes)
        expected_party[int(RamAddress.PARTY_MON_1) + PARTY_STATUS_OFFSET] = (
            STATUSES[conditions.player_status])
        expected_party[int(RamAddress.ENEMY_PARTY_MON_1) + PARTY_STATUS_OFFSET] = (
            STATUSES[conditions.opponent_status])
        if (any(memory[a] != value for a, value in expected_party.items())
                or any(memory[w["address"]] != w["after"] for w in writes)
                or after.party_status != ((STATUSES[conditions.player_status],)
                                          + (0,) * (before.party_count - 1))
                or after.enemy_hp != before.enemy_hp):
            raise BattlePracticeError("team status setup altered protected party bytes")
    return {
        "schema": ("pokemon.red.team-status-practice-intervention.v1" if team
                   else "pokemon.red.status-practice-intervention.v1"),
        "partition": "train",
        "conditions": {name: getattr(conditions, name) for name in conditions.__dataclass_fields__},
        "actor_memory_writes": 0,
        "teacher_memory_writes": True,
        "fit_allowed": True,
        **({"writes": writes, "teacher_memory_write_count": len(writes),
            "party_count": before.party_count, "opponent_party_count": before.enemy_party_count,
            "protected_party_bytes": len(party_bytes) - 2,
            "reserve_bytes_unchanged": True} if team else {}),
    }


def condition_train_effect_state(reader, memory, *, partition,
                                opponent_confusion_turns=0, opponent_disabled_slot=None):
    """Extra isolated setup for measured-effect contrasts, never a policy action.

    Pinned wEnemyConfusedCounter=D070, wEnemyDisabledMove=D072, and
    wEnemyDisabledMoveNumber=CCEF. Keep both Disable representations consistent.
    """
    if partition is not ScenarioPartition.TRAIN:
        raise BattlePracticeError("effect conditioning is TRAIN-only")
    if (type(opponent_confusion_turns) is not int or not 0 <= opponent_confusion_turns <= 4
            or (opponent_disabled_slot is not None and
                (type(opponent_disabled_slot) is not int or
                 not 1 <= opponent_disabled_slot <= 4))):
        raise BattlePracticeError("invalid effect starting condition")
    raw = reader.read()
    if (raw.battle_state != 2 or raw.party_count != 1 or raw.enemy_party_count != 1
            or raw.active_party_index != 0 or raw.enemy_party_position != 0
            or raw.enemy_confused is not False or memory[0xD070] or memory[0xD072]
            or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN):
        raise BattlePracticeError("effect setup requires a clean single-member boundary")
    move = 0
    if opponent_disabled_slot is not None:
        move = memory[int(RamAddress.ENEMY_MOVES) + opponent_disabled_slot - 1]
        if not move:
            raise BattlePracticeError("opponent disabled slot has no move")
    before = {address: memory[address] for address in (0xD067, 0xD070, 0xD072, 0xCCEF)}
    memory[0xD067] = before[0xD067] | (0x80 if opponent_confusion_turns else 0)
    memory[0xD070] = opponent_confusion_turns
    memory[0xD072] = 0 if opponent_disabled_slot is None else opponent_disabled_slot * 16 + 3
    memory[0xCCEF] = move
    if (reader.read().enemy_confused != bool(opponent_confusion_turns)
            or memory[0xD070] != opponent_confusion_turns
            or memory[0xD072] != (0 if opponent_disabled_slot is None else
                                    opponent_disabled_slot * 16 + 3)
            or memory[0xCCEF] != move):
        raise BattlePracticeError("effect starting condition readback differs")
    return {"schema": "pokemon.red.effect-practice-intervention.v1", "partition": "train",
            "opponent_confusion_turns": opponent_confusion_turns,
            "opponent_disabled_slot": opponent_disabled_slot,
            "teacher_memory_writes": True, "actor_memory_writes": 0}
