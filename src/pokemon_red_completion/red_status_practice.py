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
from .red_battle_practice_factory import WritableRedMemory, _put_u16, _u16
from .scenario_lab import ScenarioPartition

STATUSES = {"none": 0, "sleep": 2, "poison": 8, "burn": 16, "freeze": 32, "paralysis": 64}


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
    if partition is not ScenarioPartition.TRAIN or not isinstance(
        conditions, StatusPracticeConditions
    ):
        raise BattlePracticeError("status conditioning is TRAIN-only")
    before = reader.read()
    if (
        before.battle_state != 2
        or before.party_count != 1
        or before.active_party_index != 0
        or before.enemy_party_count != 1
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
        raise BattlePracticeError("status conditioning needs a clean single-member MAIN boundary")
    if conditions.disabled_slot and (
        not before.battler_moves or not before.battler_moves[conditions.disabled_slot - 1]
    ):
        raise BattlePracticeError("disabled slot has no move")
    expected_stats = {}
    for player, status in ((True, conditions.player_status), (False, conditions.opponent_status)):
        value = STATUSES[status]
        battle_status = 0xD018 if player else int(RamAddress.ENEMY_STATUS)
        party_base = int(RamAddress.PARTY_MON_1 if player else RamAddress.ENEMY_PARTY_MON_1)
        for address in (battle_status, party_base + PARTY_STATUS_OFFSET):
            memory[address] = value
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
            _put_u16(memory, address, expected_stats[address])
    memory[int(RamAddress.PLAYER_ACCURACY_STAGE)] = conditions.player_accuracy + 7
    memory[int(RamAddress.ENEMY_DEFENSE_STAGE) + 3] = conditions.opponent_accuracy + 7
    memory[int(RamAddress.PLAYER_DISABLED_MOVE)] = (
        conditions.disabled_slot * 16 + 3 if conditions.disabled_slot else 0
    )
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
    return {
        "schema": "pokemon.red.status-practice-intervention.v1",
        "partition": "train",
        "conditions": {name: getattr(conditions, name) for name in conditions.__dataclass_fields__},
        "actor_memory_writes": 0,
        "teacher_memory_writes": True,
        "fit_allowed": True,
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
