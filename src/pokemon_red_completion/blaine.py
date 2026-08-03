"""Qualified Pokémon Mansion, Secret Key, Cinnabar Gym, and Blaine chapter.

The map routes, quiz answers, event IDs, trainer identity, party, and reward
order are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
    run_adaptive_wild_battle,
)
from pokemon_red_completion.celadon import (
    DEFAULT_CELADON_TIMING,
    CeladonTiming,
    CeladonWildFleeEvidence,
    _bag,
    _flee,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
    _RunState,
)
from pokemon_red_completion.cinnabar import _four
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING, DIG
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
    _use_bag_item,
)
from pokemon_red_completion.observation import (
    Badge,
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.party import PartyMemberObservation, StatusCondition
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    DUX_SPECIES_ID,
    HITMONLEE_SPECIES_ID,
    SNORLAX_SPECIES_ID,
    PokemonRedPartyReader,
)
from pokemon_red_completion.silph import DEFAULT_SILPH_TIMING, _await_trainer_battle
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    BalancedTeamReport,
    TeamTrainingDirective,
    TeamTrainingProgress,
    is_matchup_acceptable,
    plan_team_training,
    summarize_team_readiness,
)
from pokemon_red_completion.tower import party_core_intact
from pokemon_red_completion.training import (
    TrainingDirective,
    TrainingObservation,
    TrainingPolicy,
    TrainingReport,
    choose_training_directive,
    choose_training_move_slot,
)

BLAINE_CHECKPOINT_COUNT = 9
BLAINE_CAPACITY_SALE_ITEM = ItemId.ANTIDOTE
BLAINE_INPUT_BAG_SLOT_BOUNDS = (16, 19)
BLAINE_MONEY_DELTA = 5_003
BLAINE_ANTIDOTE_SALE_VALUE = 50
MAX_REPEL_PRICE = 700
ULTRA_BALL_PRICE = 1_200
BLAINE_MAX_WILD_FLEES = 3
MANSION_TRAINING_FLEE_TIMING = CeladonTiming(flee_pulses=96)
BLAINE_OPPONENT = 0xEF
BLAINE_TRAINER_CLASS = 0xEF
BLAINE_TRAINER_SET = 1
BLAINE_PARTY = ((0x21, 42), (0xA3, 40), (0xA4, 42), (0x14, 47))
HYDRO_PUMP_MOVE_ID = 0x38
HYDRO_PUMP_LEARN_LEVEL = 52
# No trainer switch prompt can occur in this wild-only block.  Keeping CANCEL
# outside the bounded runtime therefore accepts Blastoise's level-52 Hydro Pump
# prompt and its default slot-one replacement instead of silently declining it.
MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL = 10_000
JOLTEON_SPECIES_ID = 0x68
MANSION_TRAINING_POLICY = TrainingPolicy(
    target_level=55,
    preferred_move_slots=(4, 2, 3, 1),
    retreat_hp_ratio=0.45,
    reserve_total_pp=2,
    max_enemy_level_delta=0,
    max_battles=180,
    max_steps=15_000,
    max_healing_trips=24,
)
#: Balance contract for the Mansion block.
#:
#: ``required_size`` tracks the complete declared roster assembled before this
#: long-form balancing block.
MANSION_TEAM_POLICY = BalancedTeamPolicy(
    minimum_level=50,
    maximum_level_spread=5,
    required_size=6,
    retreat_hp_ratio=0.90,
    # The lead-only block reserved 2 PP because it ran barely a hundred battles
    # at an overwhelming level advantage.  Team training runs far longer, so it
    # returns to heal with a real margin instead of fighting to exhaustion and
    # discovering mid-battle that its last slot is Disabled.
    reserve_total_pp=16,
    max_enemy_level_delta=0,
    minimum_direct_level_advantage=15,
    # Clean-power measurements have needed between 5,445 wins (levels 82--87)
    # and more than 5,500 wins (levels 82--91) because escort participation is
    # encounter-dependent. Retain the strict spread and zero-faint contract and
    # provide measured headroom for the slower lineage.
    max_battles=7_000,
    max_steps=500_000,
    # The live acquisition lineage changes Mansion RNG and requires the escort
    # to absorb volatile encounters before escaping. A clean replay reached a
    # six-level spread at 1,000 heals, one trainee level short of readiness.
    # Preserve the 90% retreat threshold and zero-faint contract while giving
    # that measured safe strategy 25% bounded headroom.
    max_healing_trips=1_250,
    max_faints=0,
)
BATTLE_PARTY_MENU_COMMAND = 2
PARTY_SUBMENU_SWITCH = 0
BATTLE_COMMAND_COORDINATES = {
    0: (0, 0),
    1: (0, 1),
    2: (1, 0),
    3: (1, 1),
}
DIGLETT_SPECIES_ID = 0x3B
CUT_MOVE_ID = 0x0F
FLY_MOVE_ID = 0x13
SURF_MOVE_ID = 0x39
STRENGTH_MOVE_ID = 0x46
FIELD_MOVE_IDS = frozenset({CUT_MOVE_ID, DIG, FLY_MOVE_ID, SURF_MOVE_ID, STRENGTH_MOVE_ID})
TRAINING_MOVE_IDS = {
    BLASTOISE_SPECIES_ID: (SURF_MOVE_ID, 0x3A, STRENGTH_MOVE_ID, 0x82),
    # Fly's two-turn state can spend PP before its delayed semantic effect is
    # observable.  Keep it for field travel, but grind with one-turn Cut/Peck.
    DUX_SPECIES_ID: (CUT_MOVE_ID, 0x40),
    DIGLETT_SPECIES_ID: (DIG,),
    DUGTRIO_SPECIES_ID: (DIG,),
    # Snorlax replaces its early Headbutt as the long curriculum accepts
    # Body Slam, Double-Edge, and Hyper Beam level-up prompts.
    SNORLAX_SPECIES_ID: (0x1D, 0x22, 0x26, 0x3F),
    # Prefer Jolteon's natural Electric and coverage progression and stop for
    # healing once those damaging moves are spent; its status moves must not
    # be mistaken for a usable attack reserve.
    JOLTEON_SPECIES_ID: (0x57, 0x54, 0x18, 0x2A, 0x62),
    # Hitmonlee begins with Double Kick and grows into its natural kick suite.
    HITMONLEE_SPECIES_ID: (0x18, 0x1B, 0x1A, 0x88, 0x19),
}
RED_DIRECT_LEVEL_ADVANTAGE = {
    DUX_SPECIES_ID: 15,
    DIGLETT_SPECIES_ID: 8,
    DUGTRIO_SPECIES_ID: 8,
}
TRAINING_ATTACK_PP_RESERVE = {
    BLASTOISE_SPECIES_ID: 16,
    DUX_SPECIES_ID: 6,
    DIGLETT_SPECIES_ID: 2,
    DUGTRIO_SPECIES_ID: 2,
    SNORLAX_SPECIES_ID: 2,
    JOLTEON_SPECIES_ID: 5,
    HITMONLEE_SPECIES_ID: 5,
}
# Muk can outlast a trainee's weak coverage and turn a safe starting-HP check
# into a long attritional knockout. It is fled rather than feeding still more
# experience to the already-high Blastoise escort.
MANSION_ESCORT_ENEMY_SPECIES = frozenset({0x88})
# Koffing and Weezing can end an encounter with Selfdestruct while a trainee is
# switching to the escort. They are never assigned to a trainee directly. A
# terminal Selfdestruct is counted only after the zero-faint check; otherwise
# the healthy escort flees so it does not widen the level spread unnecessarily.
MANSION_VOLATILE_ENEMY_SPECIES = frozenset({0x37, 0x8F})
# A healthy training route can occasionally draw several excluded encounters,
# but it must never spend an unbounded amount of wall time fleeing without
# earning experience.  This is deliberately local to the Red adapter: the
# portable policy continues to reason in battles, steps, and healing trips.
MANSION_MAX_CONSECUTIVE_FLEES = 32
MANSION_TRAINER_EVENTS = (
    EventFlag.BEAT_MANSION_1_TRAINER_0,
    EventFlag.BEAT_MANSION_2_TRAINER_0,
    EventFlag.BEAT_MANSION_3_TRAINER_0,
    EventFlag.BEAT_MANSION_3_TRAINER_1,
    EventFlag.BEAT_MANSION_4_TRAINER_0,
    EventFlag.BEAT_MANSION_4_TRAINER_1,
)
GYM_TRAINER_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_CINNABAR_GYM_TRAINER_0) + offset) for offset in range(7)
)
GYM_GATE_EVENTS = tuple(
    EventFlag(int(EventFlag.CINNABAR_GYM_GATE_0_UNLOCKED) + offset) for offset in range(7)
)
QUIZ_ANSWERS = (True, False, False, False, True, False)
QUIZ_TEXT_PULSES = (9, 10, 9, 11, 11, 9)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "R": "right", "D": "down", "L": "left"}[item] for item in value)


CENTER_TO_MART = ("down",) * 5 + ("right",) * 4 + ("up",)
MART_TO_MANSION = _directions("RDDDRRRUUUUUUULULLLLLLLLLLLU")
CENTER_TO_MANSION = (
    ("down",) * 5 + ("right",) * 7 + ("up",) * 7 + ("left", "up") + ("left",) * 11 + ("up",)
)
MANSION_1F_TO_3F = _directions("U" * 17 + "RRRURRUUUUUULLUUULL")
MANSION_3F_TO_STATUE = _directions("RRRRRDDDDL")
MANSION_3F_TO_B1F = _directions("RRRRDDDDRDRDDDLLLDDDDDDRRRRRRRRDDD")
MANSION_B1F_TO_STATUE = _directions("UUUUUUULLLLLLDDDRDDDDLDDDDR")
MANSION_B1F_TO_NORTH_STATUE = _directions("LUUUULLLLLUUUUUUURRRRRRRRRRRRDDDRRUUUUUUUUUUUULUULLLLL")
MANSION_B1F_TO_SECRET_KEY = _directions("RRRRDDLLLLLLLLLLLLLLLLLLLLDDDDDDDDR")
GYM_ENTRY_ROUTE = _directions("RRRRRRRUUUUUUUUU")
GYM_QUIZ_ROUTES = (
    _directions("UUURRUUUUULLUL"),
    _directions("RURRUUUUUULLLLLLDLL"),
    _directions("RRDDDDDLLDL"),
    _directions("RDRRDDDDLLDL"),
    _directions("DDLLLLULLLUL"),
    _directions("RURRUUUULLUL"),
)
QUIZ_6_TO_BLAINE = _directions("RURRUUUL")
BLAINE_TO_GYM_EXIT = _directions("RRDDDDDDDDDDDDRRRRUURURRUUUUUUUUUUUURRRRRRDDDDDDDDDDDDDLLDD")
MART_TO_GYM = _directions("RDDDRRRUUUUUUUUUU")
GYM_RETURN_TO_BLAINE = _directions("UURRUUUUUUUUUUUUULLLLLLDDDDDDDDDDDDLLDLDDLLLLUUUUUUUUUUUULL")
GYM_EXIT_TO_CENTER = ("down",) * 8 + ("left",) * 7 + ("up",)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class BlaineChapterError(RuntimeError):
    """Raised when the Mansion or Blaine evidence contract fails."""


@dataclass(frozen=True, slots=True)
class BlaineProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[BlaineProgress], None]


@dataclass(frozen=True, slots=True)
class BlaineCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class BlaineTurn:
    enemy_species: int
    enemy_level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class BlaineChapterReport:
    records: tuple[BlaineCheckpoint, ...]
    final_raw: RawGameState
    mansion_switch_trace: tuple[bool, ...]
    mansion_trainer_events_before: tuple[bool, ...]
    mansion_trainer_events_after: tuple[bool, ...]
    mansion_wild_flees: tuple[CeladonWildFleeEvidence, ...]
    training: TrainingReport
    secret_key_quantity: int
    tm14_quantity: int
    quiz_answers: tuple[bool, ...]
    gym_gate_events_after_quizzes: tuple[bool, ...]
    gym_trainer_events_before: tuple[bool, ...]
    gym_trainer_events_after: tuple[bool, ...]
    identity: tuple[int, int, int]
    turns: tuple[BlaineTurn, ...]
    got_tm38: bool
    beat_blaine: bool
    volcano_badge: bool
    volcano_badge_mirror: bool
    tm38_quantity: int
    x_accuracy_retained: bool
    bide_sold: bool
    antidote_sold: bool
    max_repel_bought: int
    initial_money: int
    money_remaining: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool
    capacity_ultra_ball_bought: bool = False
    initial_bag_slot_count: int = 17
    team_readiness: BalancedTeamReport | None = None
    team_training_battles: int = 0
    team_training_healing_trips: int = 0

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == BLAINE_CHECKPOINT_COUNT
            and self.mansion_switch_trace == (False, True, False, True)
            and self.mansion_trainer_events_before == (False,) * 6
            and self.mansion_trainer_events_after == (False,) * 6
            and len(self.mansion_wild_flees) <= BLAINE_MAX_WILD_FLEES
            and all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.mansion_wild_flees
            )
            and self.training.passed
            and self.training.area_id == "pokemon_mansion_1f"
            and self.team_readiness is not None
            and self.team_readiness.passed
            and self.secret_key_quantity == 1
            and self.tm14_quantity == 1
            and self.quiz_answers == QUIZ_ANSWERS
            and self.gym_gate_events_after_quizzes == (False,) + (True,) * 6
            and self.gym_trainer_events_before == (False,) * 7
            and self.gym_trainer_events_after == (True,) * 7
            and self.identity == (BLAINE_OPPONENT, BLAINE_TRAINER_CLASS, BLAINE_TRAINER_SET)
            and _encounter_party(self.turns) == BLAINE_PARTY
            and bool(self.turns)
            and all(turn.move_slot == 4 for turn in self.turns)
            and all(turn.lead_hp > 0 and turn.lead_status == 0 for turn in self.turns)
            and self.got_tm38
            and self.beat_blaine
            and self.volcano_badge
            and self.volcano_badge_mirror
            and self.tm38_quantity == 1
            and self.x_accuracy_retained
            and self.bide_sold
            and self.max_repel_bought in (1, 2)
            and self.initial_bag_slot_count
            in range(
                BLAINE_INPUT_BAG_SLOT_BOUNDS[0],
                BLAINE_INPUT_BAG_SLOT_BOUNDS[1] + 1,
            )
            and self.capacity_ultra_ball_bought == (self.initial_bag_slot_count == 16)
            and self.money_remaining
            == self.initial_money
            + BLAINE_MONEY_DELTA
            - (self.max_repel_bought - 1) * MAX_REPEL_PRICE
            - (0 if self.antidote_sold else BLAINE_ANTIDOTE_SALE_VALUE)
            - (ULTRA_BALL_PRICE if self.capacity_ultra_ball_bought else 0)
            and self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and (self.final_raw.first_party_level or 0) >= MANSION_TRAINING_POLICY.target_level
            and self.final_raw.first_party_moves == (HYDRO_PUMP_MOVE_ID, 0x46, 0x3A, SURF_MOVE_ID)
            and self.final_raw.first_party_pp == (5, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def failed_terminal_checks(self) -> tuple[str, ...]:
        """Name terminal invariants that failed without dumping the full run receipt."""

        checks = {
            "checkpoint_count": len(self.records) == BLAINE_CHECKPOINT_COUNT,
            "mansion_switches": self.mansion_switch_trace == (False, True, False, True),
            "mansion_trainers_before": self.mansion_trainer_events_before == (False,) * 6,
            "mansion_trainers_after": self.mansion_trainer_events_after == (False,) * 6,
            "mansion_flee_count": len(self.mansion_wild_flees) <= BLAINE_MAX_WILD_FLEES,
            "mansion_flee_safety": all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.mansion_wild_flees
            ),
            "lead_training": self.training.passed and self.training.area_id == "pokemon_mansion_1f",
            "team_readiness": self.team_readiness is not None and self.team_readiness.passed,
            "mansion_items": self.secret_key_quantity == 1 and self.tm14_quantity == 1,
            "quiz_answers": self.quiz_answers == QUIZ_ANSWERS,
            "quiz_gates": self.gym_gate_events_after_quizzes == (False,) + (True,) * 6,
            "gym_trainers_before": self.gym_trainer_events_before == (False,) * 7,
            "gym_trainers_after": self.gym_trainer_events_after == (True,) * 7,
            "blaine_identity": self.identity
            == (BLAINE_OPPONENT, BLAINE_TRAINER_CLASS, BLAINE_TRAINER_SET),
            "blaine_party": _encounter_party(self.turns) == BLAINE_PARTY,
            "blaine_turns": bool(self.turns)
            and all(turn.move_slot == 4 for turn in self.turns)
            and all(turn.lead_hp > 0 and turn.lead_status == 0 for turn in self.turns),
            "rewards": self.got_tm38
            and self.beat_blaine
            and self.volcano_badge
            and self.volcano_badge_mirror
            and self.tm38_quantity == 1,
            "inventory": self.x_accuracy_retained
            and self.bide_sold
            and self.max_repel_bought in (1, 2),
            "money": self.money_remaining
            == self.initial_money
            + BLAINE_MONEY_DELTA
            - (self.max_repel_bought - 1) * MAX_REPEL_PRICE
            - (0 if self.antidote_sold else BLAINE_ANTIDOTE_SALE_VALUE)
            - (ULTRA_BALL_PRICE if self.capacity_ultra_ball_bought else 0),
            "location": self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3),
            "party_core": party_core_intact(self.final_raw.party_species_ids),
            "lead_level": (self.final_raw.first_party_level or 0)
            >= MANSION_TRAINING_POLICY.target_level,
            "lead_moves": self.final_raw.first_party_moves
            == (HYDRO_PUMP_MOVE_ID, 0x46, 0x3A, SURF_MOVE_ID),
            "lead_pp": self.final_raw.first_party_pp == (5, 15, 10, 15),
            "party_health": self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status),
            "controller": self.controller_released,
        }
        return tuple(name for name, passed in checks.items() if not passed)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objectives": ["obtain_secret_key", "defeat_blaine"],
            "mansion": {
                "switch_trace": list(self.mansion_switch_trace),
                "optional_trainers_before": list(self.mansion_trainer_events_before),
                "optional_trainers_after": list(self.mansion_trainer_events_after),
                "wild_flees": [
                    {
                        "map": item.map_id,
                        "position": [item.x, item.y],
                        "species": item.species,
                        "level": item.level,
                        "party_preserved": item.party_preserved,
                        "pp_preserved": item.pp_preserved,
                        "hp_safe": item.hp_safe,
                        "inventory_preserved": item.inventory_preserved,
                    }
                    for item in self.mansion_wild_flees
                ],
                "secret_key": self.secret_key_quantity,
                "tm14_blizzard": self.tm14_quantity,
                "team_balance": {
                    "minimum_level": (
                        self.team_readiness.observed_minimum_level if self.team_readiness else None
                    ),
                    "level_spread": (
                        self.team_readiness.observed_level_spread if self.team_readiness else None
                    ),
                    "passed": (self.team_readiness.passed if self.team_readiness else None),
                    "battles": self.team_training_battles,
                    "healing_trips": self.team_training_healing_trips,
                },
                "training": {
                    "area": self.training.area_id,
                    "levels": [self.training.starting_level, self.training.final_level],
                    "target_level": self.training.target_level,
                    "battles_won": self.training.battles_won,
                    "battles_fled": self.training.battles_fled,
                    "steps": self.training.steps_taken,
                    "healing_trips": self.training.healing_trips,
                    "fainted": self.training.fainted,
                },
            },
            "quiz": {
                "answers": ["yes" if answer else "no" for answer in self.quiz_answers],
                "gates_after": list(self.gym_gate_events_after_quizzes),
                "trainers_before": list(self.gym_trainer_events_before),
            },
            "blaine": {
                "identity": list(self.identity),
                "party": [list(member) for member in BLAINE_PARTY],
                "move_slots": [turn.move_slot for turn in self.turns],
                "trainers_after": list(self.gym_trainer_events_after),
            },
            "rewards": {
                "tm38": self.tm38_quantity,
                "tm38_event": self.got_tm38,
                "blaine_event": self.beat_blaine,
                "volcano_badge": self.volcano_badge,
                "volcano_badge_mirror": self.volcano_badge_mirror,
            },
            "inventory": {
                "x_accuracy_retained": self.x_accuracy_retained,
                "bide_sold": self.bide_sold,
                "antidote_sold": self.antidote_sold,
                "max_repel_bought": self.max_repel_bought,
                "money": [self.initial_money, self.money_remaining],
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_max_hp": list(self.party_max_hp),
                "party_status": list(self.party_status),
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


class _CountingExecutor:
    def __init__(self, delegate: ChapterExecutor) -> None:
        self.delegate = delegate
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self.delegate.execute(action)
        self.actions_executed += 1
        return result


def run_blaine_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> BlaineChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[BlaineCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CINNABAR_POKECENTER, (3, 3), "post-Cinnabar boundary")
    initial_money = _money(emulator)
    initial_bag = _bag(emulator)
    if (
        initial_bag.get(ItemId.SECRET_KEY, 0)
        or _event(emulator, EventFlag.BEAT_BLAINE)
        or _event(emulator, EventFlag.GOT_TM38)
        or initial.badge_bits & Badge.VOLCANO
    ):
        raise BlaineChapterError("Mansion/Blaine input boundary is not pristine.")
    if (
        not BLAINE_INPUT_BAG_SLOT_BOUNDS[0] <= len(initial_bag) <= BLAINE_INPUT_BAG_SLOT_BOUNDS[1]
        or initial_bag.get(ItemId.X_ACCURACY, 0) != 1
        or initial_bag.get(ItemId.TM34_BIDE, 0) != 1
        or initial_bag.get(ItemId.ANTIDOTE, 0) not in (0, 1, 2)
    ):
        raise BlaineChapterError(
            "Cinnabar input inventory lacks the qualified capacity items: "
            f"slots={len(initial_bag)}, "
            f"x_accuracy={initial_bag.get(ItemId.X_ACCURACY, 0)}, "
            f"bide={initial_bag.get(ItemId.TM34_BIDE, 0)}, "
            f"antidote={initial_bag.get(ItemId.ANTIDOTE, 0)}, "
            f"items={tuple(int(item) for item in initial_bag)}."
        )
    mansion_before = _events(emulator, MANSION_TRAINER_EVENTS)
    if mansion_before != (False,) * 6:
        raise BlaineChapterError("A Pokémon Mansion trainer was already defeated.")
    switch_trace = [_event(emulator, EventFlag.MANSION_SWITCH_ON)]
    if switch_trace != [False]:
        raise BlaineChapterError("Pokémon Mansion switch did not start off.")
    _checkpoint(records, progress, emulator, initial, "blaine_ready", "Mansion route ready")

    _move(actions, reader, CENTER_TO_MART, "Cinnabar Mart")
    _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "Cinnabar Mart entry")
    _move(actions, reader, ("up", "up", "left"), "Cinnabar clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    sell_antidote_early = _sell_antidote_before_mansion(
        len(initial_bag),
        initial_bag.get(ItemId.ANTIDOTE, 0),
    )
    if sell_antidote_early:
        _sell_current_bag_item(actions, reader, emulator, BLAINE_CAPACITY_SALE_ITEM)
        if _bag(emulator).get(BLAINE_CAPACITY_SALE_ITEM, 0):
            raise BlaineChapterError("Obsolete Antidote sale did not settle.")
    else:
        _open_sell_menu(actions, emulator)
    # The consumed Silph X Special leaves one extra free slot in this lineage.
    # Retain TM21 here so TM14 plus the Secret Key still fill the bag and keep
    # Blaine's delayed-TM38 reward boundary meaningful. Stay in the sell menu
    # so _buy_repel can return directly to the clerk's BUY/SELL menu.
    capacity_ultra_ball_bought = len(initial_bag) == 16
    repel_purchase_quantity = 2 if len(initial_bag) in {16, 17} else 1
    _buy_repel(
        actions,
        reader,
        emulator,
        quantity=repel_purchase_quantity,
        buy_ultra_ball=capacity_ultra_ball_bought,
    )
    _use_bag_item(actions, reader, emulator, DEFAULT_LAVENDER_TIMING, ItemId.MAX_REPEL)
    if (
        _bag(emulator).get(ItemId.MAX_REPEL, 0) != repel_purchase_quantity - 1
        or emulator.read_u8(RamAddress.REPEL_REMAINING_STEPS) != 250
    ):
        raise BlaineChapterError("Max Repel purchase did not leave its capacity filler.")

    _move(actions, reader, MART_TO_MANSION, "Cinnabar Mart to Mansion")
    _require(reader.read(), MapId.POKEMON_MANSION_1F, (5, 27), "Mansion entrance")
    _checkpoint(records, progress, emulator, reader.read(), "mansion_entered", "Entered Mansion")

    wilds = _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_1F_TO_3F + MANSION_3F_TO_STATUE,
        "Mansion 3F statue",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_3F, (10, 6), "Mansion 3F statue")
    _toggle_statue(actions, reader, emulator, expected=True)
    switch_trace.append(True)

    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_3F_TO_B1F + MANSION_B1F_TO_STATUE,
        "Mansion B1F south statue",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_B1F, (18, 26), "B1F south statue")
    _toggle_statue(actions, reader, emulator, expected=False)
    switch_trace.append(False)
    _move(actions, reader, ("right",), "Mansion TM14 approach")
    _pick_up_mansion_item(
        actions,
        reader,
        emulator,
        ItemId.TM14_BLIZZARD,
        "TM14 Blizzard",
    )
    _move(actions, reader, ("left",), "Mansion south statue return")

    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_B1F_TO_NORTH_STATUE,
        "Mansion B1F north statue",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_B1F, (20, 4), "B1F north statue")
    _toggle_statue(actions, reader, emulator, expected=True)
    switch_trace.append(True)

    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_B1F_TO_SECRET_KEY,
        "Mansion Secret Key",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_B1F, (5, 14), "Secret Key approach")
    _pick_up_secret_key(actions, reader, emulator)
    mansion_after = _events(emulator, MANSION_TRAINER_EVENTS)
    if mansion_after != mansion_before:
        raise BlaineChapterError("Mansion route changed an optional trainer event.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "secret_key_obtained",
        "Recovered Secret Key",
    )

    _field_dig(actions, reader, emulator)
    _require(reader.read(), MapId.SAFFRON_CITY, (9, 30), "Mansion Dig return")
    _field_fly_to_cinnabar(actions, reader, emulator)
    _require(reader.read(), MapId.CINNABAR_ISLAND, (11, 12), "Cinnabar Fly return")
    _move(actions, reader, ("up",), "Cinnabar Center entry")
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "Cinnabar Center")
    _move(actions, reader, ("up",) * 4, "Cinnabar nurse")
    _heal(actions, reader, emulator)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "mansion_returned",
        "Returned safely from Mansion",
    )

    training = _run_mansion_training(actions, reader, emulator)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "mansion_training_complete",
        "Trained safely in Pokémon Mansion",
    )

    team_readiness, team_battles, team_healing_trips = _run_mansion_team_balancing(
        actions,
        reader,
        emulator,
        progress_sink=progress,
        completed_checkpoint_count=len(records),
    )

    _move(actions, reader, ("down",) * 5 + GYM_ENTRY_ROUTE, "Cinnabar Gym")
    _require(reader.read(), MapId.CINNABAR_GYM, (16, 17), "Cinnabar Gym entrance")
    gym_before = _events(emulator, GYM_TRAINER_EVENTS)
    if gym_before != (False,) * 7:
        raise BlaineChapterError("A Cinnabar Gym trainer was already defeated.")
    for index, (route, answer, text_pulses) in enumerate(
        zip(GYM_QUIZ_ROUTES, QUIZ_ANSWERS, QUIZ_TEXT_PULSES, strict=True),
        1,
    ):
        _move(actions, reader, route, f"Cinnabar quiz {index}")
        _answer_quiz(actions, reader, emulator, index, answer, text_pulses)
        if _events(emulator, GYM_TRAINER_EVENTS) != gym_before:
            raise BlaineChapterError(f"Quiz {index} changed a regular trainer event.")
    gates_after = _events(emulator, GYM_GATE_EVENTS)
    if gates_after != (False,) + (True,) * 6:
        raise BlaineChapterError(f"Unexpected Cinnabar gate state: {gates_after!r}.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "gym_quizzes_cleared",
        "Cleared six Gym quizzes",
    )

    _move(actions, reader, QUIZ_6_TO_BLAINE, "Blaine approach")
    _require(reader.read(), MapId.CINNABAR_GYM, (3, 4), "Blaine approach")
    _face_and_interact(actions, "up")
    _await_trainer_battle(actions, reader, DEFAULT_SILPH_TIMING)
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    if identity != (BLAINE_OPPONENT, BLAINE_TRAINER_CLASS, BLAINE_TRAINER_SET):
        raise BlaineChapterError(f"Unexpected Blaine identity: {identity!r}.")
    turns: list[BlaineTurn] = []

    def policy(raw: RawGameState) -> int:
        turns.append(
            BlaineTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                4,
            )
        )
        return 4

    run_adaptive_trainer_battle(
        reader,
        actions,
        policy,
        expected_map=MapId.CINNABAR_GYM,
        intent=BattleIntent(
            "defeat_blaine",
            battle_plan_id=RedBattlePlanId.BLAINE_LEADER,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(SURF_MOVE_ID),
        ),
        required_move_id=SURF_MOVE_ID,
        label="Blaine",
    )
    if _encounter_party(tuple(turns)) != BLAINE_PARTY:
        raise BlaineChapterError(f"Blaine party or Surf policy changed: {turns!r}.")
    _checkpoint(records, progress, emulator, reader.read(), "blaine_defeated", "Defeated Blaine")
    if not _event(emulator, EventFlag.BEAT_BLAINE):
        raise BlaineChapterError("Blaine victory event did not settle.")
    if _event(emulator, EventFlag.GOT_TM38):
        raise BlaineChapterError("Full-bag reward boundary unexpectedly accepted TM38.")

    _move(actions, reader, BLAINE_TO_GYM_EXIT, "Blaine to Gym exit")
    _move(actions, reader, ("down", "down"), "Cinnabar Gym exit")
    _require(reader.read(), MapId.CINNABAR_ISLAND, (18, 4), "Gym exterior")
    _move(
        actions,
        reader,
        ("down",) * 8 + ("left",) * 3 + ("up",),
        "Cinnabar Mart return",
    )
    _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "Cinnabar Mart return")
    _move(actions, reader, ("up", "up", "left"), "Cinnabar clerk return")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _sell_current_bag_item(actions, reader, emulator, ItemId.TM34_BIDE)
    if _bag(emulator).get(ItemId.TM34_BIDE, 0):
        raise BlaineChapterError("TM34 Bide sale did not settle.")
    _close(actions, reader)
    _move(actions, reader, MART_TO_GYM, "Mart to Cinnabar Gym")
    _require(reader.read(), MapId.CINNABAR_GYM, (16, 16), "Gym reward return")
    _move(actions, reader, GYM_RETURN_TO_BLAINE, "Blaine reward approach")
    _require(reader.read(), MapId.CINNABAR_GYM, (3, 4), "Blaine reward approach")
    _face_and_interact(actions, "up")
    for _ in range(16):
        if _event(emulator, EventFlag.GOT_TM38):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise BlaineChapterError("Blaine did not award TM38 after the bag slot was freed.")
    _checkpoint(records, progress, emulator, reader.read(), "tm38_received", "Received TM38")

    _move(actions, reader, BLAINE_TO_GYM_EXIT, "Blaine reward to Gym exit")
    _move(actions, reader, ("down", "down"), "Cinnabar Gym final exit")
    _require(reader.read(), MapId.CINNABAR_ISLAND, (18, 4), "Gym final exterior")
    _move(actions, reader, GYM_EXIT_TO_CENTER, "Cinnabar Center return")
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "Cinnabar Center return")
    _move(actions, reader, ("up",) * 4, "Cinnabar final nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    _checkpoint(records, progress, emulator, final, "blaine_terminal", "Blaine terminal ready")

    report = BlaineChapterReport(
        records=tuple(records),
        final_raw=final,
        mansion_switch_trace=tuple(switch_trace),
        mansion_trainer_events_before=mansion_before,
        mansion_trainer_events_after=mansion_after,
        mansion_wild_flees=tuple(wilds),
        training=training,
        secret_key_quantity=_bag(emulator).get(ItemId.SECRET_KEY, 0),
        tm14_quantity=_bag(emulator).get(ItemId.TM14_BLIZZARD, 0),
        quiz_answers=QUIZ_ANSWERS,
        gym_gate_events_after_quizzes=gates_after,
        gym_trainer_events_before=gym_before,
        gym_trainer_events_after=_events(emulator, GYM_TRAINER_EVENTS),
        identity=identity,
        turns=tuple(turns),
        got_tm38=_event(emulator, EventFlag.GOT_TM38),
        beat_blaine=_event(emulator, EventFlag.BEAT_BLAINE),
        volcano_badge=bool(final.badge_bits & Badge.VOLCANO),
        volcano_badge_mirror=bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.VOLCANO),
        tm38_quantity=_bag(emulator).get(ItemId.TM38_FIRE_BLAST, 0),
        x_accuracy_retained=_bag(emulator).get(ItemId.X_ACCURACY, 0) == 1,
        bide_sold=ItemId.TM34_BIDE not in _bag(emulator),
        antidote_sold=sell_antidote_early,
        max_repel_bought=repel_purchase_quantity,
        initial_money=initial_money,
        money_remaining=_money(emulator),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
        capacity_ultra_ball_bought=(
            capacity_ultra_ball_bought and _bag(emulator).get(ItemId.ULTRA_BALL, 0) == 1
        ),
        initial_bag_slot_count=len(initial_bag),
        team_readiness=team_readiness,
        team_training_battles=team_battles,
        team_training_healing_trips=team_healing_trips,
    )
    if not report.passed:
        raise BlaineChapterError(
            "Blaine terminal evidence failed: "
            f"checks={report.failed_terminal_checks()!r}; report={report!r}."
        )
    return report


def _sell_current_bag_item(actions, reader, emulator, item: ItemId) -> None:
    before = _bag(emulator)
    if before.get(item, 0) != 1:
        raise BlaineChapterError(f"Expected one {item.name} to sell.")
    _open_sell_menu(actions, emulator)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute < len(_bag(emulator)) and tuple(_bag(emulator))[absolute] == item:
            break
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    else:
        raise BlaineChapterError(f"Sell list could not select {item.name}.")
    for _ in range(12):
        _pulse(actions, MacroActionKind.CONFIRM)
        if item not in _bag(emulator):
            return
    raise BlaineChapterError(f"Sale of {item.name} did not settle.")


def _open_sell_menu(actions, emulator) -> None:
    _pulse(actions, MacroActionKind.INTERACT)
    _pulse(actions, MacroActionKind.MOVE, "down")
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise BlaineChapterError("Cinnabar shop did not select SELL.")
    _pulse(actions, MacroActionKind.CONFIRM)


def _sell_antidote_before_mansion(
    input_slots: int,
    antidote_quantity: int,
) -> bool:
    """Sell the Antidote only when the 19-slot lineage needs one free slot."""

    if not BLAINE_INPUT_BAG_SLOT_BOUNDS[0] <= input_slots <= BLAINE_INPUT_BAG_SLOT_BOUNDS[1]:
        raise BlaineChapterError(f"Unsupported Blaine input capacity: {input_slots} slots.")
    if antidote_quantity not in (0, 1, 2) or (input_slots == 19 and antidote_quantity != 1):
        raise BlaineChapterError(
            "Unsupported Blaine Antidote capacity: "
            f"slots={input_slots}, quantity={antidote_quantity}."
        )
    return input_slots == 19


def _buy_repel(
    actions,
    reader,
    emulator,
    *,
    quantity: int = 1,
    buy_ultra_ball: bool = False,
) -> None:
    _pulse(actions, MacroActionKind.CANCEL)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    if buy_ultra_ball:
        _buy_mart_item(
            actions,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=0,
            item=ItemId.ULTRA_BALL,
            quantity=1,
            target_bag_quantity=1,
        )
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=3,
        item=ItemId.MAX_REPEL,
        quantity=quantity,
        target_bag_quantity=quantity,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)


def _move_mansion(
    actions,
    reader,
    emulator,
    route: Iterable[str],
    label: str,
) -> tuple[CeladonWildFleeEvidence, ...]:
    run = _RunState([])
    for index, direction in enumerate(tuple(route), 1):
        before = reader.read()
        for _ in range(4):
            _pulse(actions, MacroActionKind.MOVE, direction, 240)
            raw = reader.read()
            if raw.battle_state == 2:
                raise BlaineChapterError(f"{label} entered trainer battle at step {index}.")
            if raw.battle_state == 1:
                _flee(actions, reader, emulator, run, DEFAULT_CELADON_TIMING)
                raw = reader.read()
            if (raw.map_id, raw.player_x, raw.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
            _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        else:
            raise BlaineChapterError(f"{label} blocked at step {index}.")
        if _events(emulator, MANSION_TRAINER_EVENTS) != (False,) * 6:
            raise BlaineChapterError(f"{label} changed an optional trainer event.")
    return tuple(run.wilds)


def _toggle_statue(actions, reader, emulator, *, expected: bool) -> None:
    before = _event(emulator, EventFlag.MANSION_SWITCH_ON)
    if before == expected:
        raise BlaineChapterError("Mansion statue toggle began in its target state.")
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    for _ in range(8):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if (
            _event(emulator, EventFlag.MANSION_SWITCH_ON) is expected
            and reader.read_input_readiness().ready
        ):
            return
    raise BlaineChapterError("Mansion statue did not toggle to the expected state.")


def _pick_up_secret_key(actions, reader, emulator) -> None:
    before = len(_bag(emulator))
    for _ in range(8):
        if reader.read_input_readiness().ready:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise BlaineChapterError("Secret Key approach did not settle field text.")
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(32):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if _bag(emulator).get(ItemId.SECRET_KEY, 0) == 1 and reader.read_input_readiness().ready:
            if len(_bag(emulator)) != before + 1:
                raise BlaineChapterError("Secret Key changed an unexpected bag slot count.")
            return
    raw = reader.read()
    raise BlaineChapterError(
        "Secret Key did not enter the bag: "
        f"bag_slots={len(_bag(emulator))}, input_ready={reader.read_input_readiness().ready}, "
        f"map={raw.map_id!r}, position={(raw.player_x, raw.player_y)!r}."
    )


def _pick_up_mansion_item(actions, reader, emulator, item: ItemId, label: str) -> None:
    before = len(_bag(emulator))
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(24):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if _bag(emulator).get(item, 0) == 1 and reader.read_input_readiness().ready:
            if len(_bag(emulator)) != before + 1:
                raise BlaineChapterError(f"{label} changed an unexpected bag slot count.")
            return
    raw = reader.read()
    raise BlaineChapterError(
        f"{label} did not enter the bag: map={raw.map_id!r}, "
        f"position={(raw.player_x, raw.player_y)!r}, bag={_bag(emulator)!r}."
    )


def _field_dig(
    actions,
    reader,
    emulator,
    *,
    expected_map: MapId | tuple[MapId, ...] = MapId.SAFFRON_CITY,
) -> RawGameState:
    before_bag = _bag(emulator)
    before_hp = _party_hp(emulator)
    before_status = _party_status(emulator)
    before_pp = emulator.read_u8(int(RamAddress.PARTY_MON_3_PP) + 2)
    _pulse(actions, MacroActionKind.OPEN_MENU, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, 2, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    if emulator.read_u8(int(RamAddress.PARTY_MON_3_MOVES) + 2) != DIG:
        raise BlaineChapterError("Diglett no longer exposes Dig in field slot zero.")
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    expected_maps = (expected_map,) if isinstance(expected_map, MapId) else tuple(expected_map)
    for _ in range(DEFAULT_HIDEOUT_TIMING.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if reader.read().map_id in expected_maps:
            break
    else:
        actual = reader.read()
        names = ", ".join(item.name for item in expected_maps)
        raise BlaineChapterError(
            f"Field Dig did not return to one of {names}: "
            f"map={actual.map_id!r}, position="
            f"{(actual.player_x, actual.player_y)!r}, battle={actual.battle_state!r}."
        )
    if (
        _bag(emulator) != before_bag
        or _party_hp(emulator) != before_hp
        or _party_status(emulator) != before_status
        or emulator.read_u8(int(RamAddress.PARTY_MON_3_PP) + 2) != before_pp
    ):
        raise BlaineChapterError("Field Dig changed protected party or inventory state.")
    return reader.read()


def _training_dig_to_cinnabar(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    destination = _field_dig(
        actions,
        reader,
        emulator,
        expected_map=(MapId.CINNABAR_ISLAND, MapId.SAFFRON_CITY),
    )
    if destination.map_id == MapId.SAFFRON_CITY:
        _require(destination, MapId.SAFFRON_CITY, (9, 30), "training Dig fallback")
        _field_fly_to_cinnabar(actions, reader, emulator)
    _require(reader.read(), MapId.CINNABAR_ISLAND, (11, 12), "training Dig return")


def _team_training_move_slot(state: RawGameState) -> int:
    """Pick a training move, skipping any slot the opponent has Disabled.

    The lead-only block was short enough never to meet Disable.  Team training
    runs many more encounters, so the fallback slot can be locked out; treating
    a disabled slot as available made the battle runtime reject the choice.
    """

    disabled = state.player_disabled_move_slot or 0
    moves = state.battler_moves or ()
    pp = state.battler_pp or ()
    preferred_move_ids = TRAINING_MOVE_IDS.get(state.active_party_species_id or 0, ())
    preferred_slots = tuple(
        index + 1
        for move_id in preferred_move_ids
        for index, observed in enumerate(moves)
        if (
            observed == move_id
            and index + 1 != disabled
            and index < len(pp)
            and pp[index] > 0
        )
    )
    if preferred_move_ids and not preferred_slots:
        raise _PauseForTeamTrainingRecovery
    fallback_slots = tuple(
        slot
        for slot in MANSION_TRAINING_POLICY.preferred_move_slots
        if slot != disabled and slot not in preferred_slots
    )
    slots = preferred_slots or fallback_slots
    return choose_training_move_slot(pp, slots)


class _PauseForTeamTrainingRecovery(Exception):
    """Request a safe escape when live PP or Disable removes every training attack."""


def _training_attack_pp(member: PartyMemberObservation) -> int:
    """Remaining PP on moves that can actually damage a training opponent."""

    damaging = set(TRAINING_MOVE_IDS.get(member.species_id, ()))
    if not damaging:
        return member.total_pp
    return sum(move.current_pp for move in member.known_moves if move.move_id in damaging)


def _training_attack_pp_reserve(
    member: PartyMemberObservation,
    policy: BalancedTeamPolicy,
) -> int:
    """Keep a reserve proportional to the fighter's qualified damaging pool."""

    return TRAINING_ATTACK_PP_RESERVE.get(
        member.species_id,
        policy.reserve_total_pp,
    )


def _red_training_matchup_acceptable(
    trainee: PartyMemberObservation,
    enemy_level: int | None,
    policy: BalancedTeamPolicy,
    enemy_species: int | None = None,
) -> bool:
    """Apply Red-specific risk margins after the portable level gate."""

    if enemy_species in MANSION_ESCORT_ENEMY_SPECIES | MANSION_VOLATILE_ENEMY_SPECIES:
        return False
    if not is_matchup_acceptable(trainee, enemy_level, policy):
        return False
    required_advantage = RED_DIRECT_LEVEL_ADVANTAGE.get(
        trainee.species_id,
        policy.minimum_direct_level_advantage,
    )
    return enemy_level is not None and trainee.level - enemy_level >= required_advantage


def _run_mansion_team_balancing(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    progress_sink: ProgressSink | None = None,
    completed_checkpoint_count: int = 0,
) -> tuple[object, int, int]:
    """Raise the party with safe participation followed by direct training.

    The weakest member is moved to the front before an encounter. If the
    matchup is above its safety ceiling, it switches out to Blastoise so the
    incoming escort absorbs the opponent's turn while both receive experience.
    Once the trainee can safely face the observed opponent, it fights directly
    so the escort does not continue widening the level spread.
    """

    policy = MANSION_TEAM_POLICY
    party_reader = PokemonRedPartyReader(emulator)
    if BLASTOISE_SPECIES_ID not in party_reader.read().species_ids():
        raise BlaineChapterError("Team training lacks its qualified Blastoise escort.")
    battles = 0
    steps = 0
    healing_trips = 0
    consecutive_flees = 0
    flee_run = _RunState([])

    def emit_progress() -> None:
        if progress_sink is None or battles == 0 or battles % 250:
            return
        levels = tuple(member.level for member in party_reader.read().members)
        progress_sink(
            BlaineProgress(
                "mansion_team_training_progress",
                f"Balanced team training: {battles} battles, levels {levels}",
                completed_checkpoint_count,
                BLAINE_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )

    def record_flee(label: str) -> None:
        nonlocal consecutive_flees
        consecutive_flees += 1
        if consecutive_flees > MANSION_MAX_CONSECUTIVE_FLEES:
            levels = tuple(member.level for member in party_reader.read().members)
            raise BlaineChapterError(
                "Balanced training exceeded its consecutive-flee bound after "
                f"{label}: flees={consecutive_flees}, battles={battles}, levels={levels}."
            )

    while True:
        party = party_reader.read()
        progress = TeamTrainingProgress(
            battles_completed=battles,
            steps_taken=steps,
            healing_trips=healing_trips,
            faints=party.fainted_count,
        )
        decision = plan_team_training(party, policy, progress)
        if decision.directive in {
            TeamTrainingDirective.STOP,
            TeamTrainingDirective.RECRUIT_MEMBER,
        }:
            readiness = summarize_team_readiness(party, policy)
            if not readiness.passed:
                raise BlaineChapterError(
                    f"Team training stopped before readiness: {decision.reason}; "
                    f"battles={battles}, steps={steps}, heals={healing_trips}, "
                    f"levels={tuple(member.level for member in party.members)!r}."
                )
            break

        raw = reader.read()
        escort = next(
            (member for member in party.members if member.species_id == BLASTOISE_SPECIES_ID),
            None,
        )
        if escort is None:
            raise BlaineChapterError("Team training lost its Blastoise escort.")
        escort_unsafe = (
            escort.is_fainted
            or escort.hp_ratio <= policy.retreat_hp_ratio
            or escort.status is not StatusCondition.HEALTHY
            or _training_attack_pp(escort) <= _training_attack_pp_reserve(escort, policy)
        )
        if raw.battle_state == 1:
            trainee = party.weakest_trainable_member
            if trainee is None or trainee.slot != 1:
                raise BlaineChapterError(
                    "A Mansion encounter began without the selected trainee in front."
                )
            if raw.enemy_species_id in MANSION_VOLATILE_ENEMY_SPECIES:
                if escort_unsafe:
                    raise BlaineChapterError(
                        "A volatile Mansion matchup began without a safe escape escort."
                    )
                battle_continues = _switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index=escort.slot - 1,
                    label="Blastoise volatile escape escort",
                )
                if not battle_continues:
                    _require_zero_faints(party_reader, "terminal volatile escort switch")
                    battles += 1
                    consecutive_flees = 0
                    emit_progress()
                    continue
                _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                _require_zero_faints(party_reader, "volatile-matchup escape")
                record_flee("volatile matchup")
                continue
            if raw.enemy_species_id in MANSION_ESCORT_ENEMY_SPECIES:
                if escort_unsafe:
                    raise BlaineChapterError(
                        "An excluded Mansion matchup began without a safe escape escort."
                    )
                if not _switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index=escort.slot - 1,
                    label="Blastoise escape escort",
                ):
                    raise BlaineChapterError(
                        "Excluded Mansion encounter ended during the escape switch."
                    )
                _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                _require_zero_faints(party_reader, "excluded-matchup escape")
                record_flee("excluded matchup")
                continue
            trainee_fights = _red_training_matchup_acceptable(
                trainee,
                raw.enemy_level,
                policy,
                raw.enemy_species_id,
            ) and _training_attack_pp(trainee) > _training_attack_pp_reserve(trainee, policy)
            fighter = trainee if trainee_fights else escort
            fighter_unsafe = (
                fighter.is_fainted
                or fighter.hp_ratio <= policy.retreat_hp_ratio
                or fighter.status is not StatusCondition.HEALTHY
                or _training_attack_pp(fighter) <= _training_attack_pp_reserve(fighter, policy)
            )
            if fighter_unsafe:
                _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                _require_zero_faints(party_reader, "unsafe-matchup escape")
                record_flee("unsafe matchup")
                continue
            if not trainee_fights:
                battle_continues = _switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index=escort.slot - 1,
                    label="Blastoise escort",
                )
                if not battle_continues:
                    _require_zero_faints(party_reader, "terminal escort switch")
                    battles += 1
                    consecutive_flees = 0
                    emit_progress()
                    continue
            if reader.read().battle_state != 1:
                continue
            try:
                run_adaptive_wild_battle(
                    reader,
                    actions,
                    _team_training_move_slot,
                    expected_map=MapId.POKEMON_MANSION_1F,
                    label="Pokémon Mansion team training encounter",
                )
            except BattleRuntimeError as error:
                if not isinstance(error.__cause__, _PauseForTeamTrainingRecovery):
                    raise
                current = reader.read()
                if current.active_party_index != escort.slot - 1:
                    if escort_unsafe:
                        raise BlaineChapterError(
                            "Training attacks were exhausted without a safe escape escort."
                        ) from error
                    if not _switch_active_battler(
                        actions,
                        reader,
                        emulator,
                        target_index=escort.slot - 1,
                        label="Blastoise PP-exhaustion escape escort",
                    ):
                        _require_zero_faints(party_reader, "terminal PP-exhaustion switch")
                        battles += 1
                        consecutive_flees = 0
                        emit_progress()
                        continue
                _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                _require_zero_faints(party_reader, "PP-exhaustion escape")
                record_flee("live PP exhaustion or Disable")
                continue
            _require_zero_faints(party_reader, "completed training battle")
            battles += 1
            consecutive_flees = 0
            emit_progress()
            continue

        if decision.directive is TeamTrainingDirective.RESTORE_TEAM or escort_unsafe:
            if healing_trips >= policy.max_healing_trips:
                break
            _restore_training_core_order(actions, reader, emulator)
            _training_dig_to_cinnabar(actions, reader, emulator)
            _move(actions, reader, ("up",), "team training Center entry")
            _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "team training Center")
            _move(actions, reader, ("up",) * 4, "team training nurse")
            _heal(actions, reader, emulator)
            healing_trips += 1
            _move(actions, reader, CENTER_TO_MANSION, "team training return")
            _require(
                reader.read(),
                MapId.POKEMON_MANSION_1F,
                (5, 27),
                "team training Mansion entrance",
            )
            continue

        if raw.map_id == MapId.CINNABAR_POKECENTER:
            _move(actions, reader, CENTER_TO_MANSION, "team training first Mansion trip")
            _require(
                reader.read(),
                MapId.POKEMON_MANSION_1F,
                (5, 27),
                "team training Mansion entrance",
            )
            continue
        if raw.map_id != MapId.POKEMON_MANSION_1F:
            break
        trainee = party.weakest_trainable_member
        if trainee is None:
            break
        if trainee.slot != 1:
            _swap_field_party_slots(
                actions,
                reader,
                emulator,
                first_index=0,
                second_index=trainee.slot - 1,
                label=f"place trainee slot {trainee.slot} in front",
            )
            continue
        direction = "down" if (raw.player_y or 0) <= 20 else "up"
        _pulse(actions, MacroActionKind.MOVE, direction, 240)
        steps += 1

    # The chapter continues from the Cinnabar Center, so this phase has to hand
    # the player back there however its loop happened to end.
    if reader.read().map_id == MapId.POKEMON_MANSION_1F:
        _restore_training_core_order(actions, reader, emulator)
        _training_dig_to_cinnabar(actions, reader, emulator)
        _move(actions, reader, ("up",), "team training final Center entry")
        _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "team training final Center")
        _move(actions, reader, ("up",) * 4, "team training final nurse")
        _heal(actions, reader, emulator)
        healing_trips += 1
    _restore_training_core_order(actions, reader, emulator)
    return summarize_team_readiness(party_reader.read(), policy), battles, healing_trips


def _require_zero_faints(party_reader: PokemonRedPartyReader, context: str) -> None:
    party = party_reader.read()
    if party.fainted_count:
        state = tuple(
            (member.species_id, member.level, member.hp, member.max_hp, member.status.value)
            for member in party.members
        )
        raise BlaineChapterError(
            f"Team training recorded a faint after {context}: party={state!r}."
        )


def _restore_training_core_order(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    """Restore the qualified core after temporary field training swaps."""

    party_reader = PokemonRedPartyReader(emulator)
    observed = party_reader.read().species_ids()
    ground_member = DUGTRIO_SPECIES_ID if DUGTRIO_SPECIES_ID in observed else DIGLETT_SPECIES_ID
    desired_core = (BLASTOISE_SPECIES_ID, DUX_SPECIES_ID, ground_member)
    if any(species not in observed for species in desired_core):
        raise BlaineChapterError(f"Cannot restore the qualified training core from {observed!r}.")
    for target_index, species_id in enumerate(desired_core):
        current = party_reader.read().species_ids()
        if current[target_index] == species_id:
            continue
        source_index = current.index(species_id)
        _swap_field_party_slots(
            actions,
            reader,
            emulator,
            first_index=source_index,
            second_index=target_index,
            label=f"restore core species {species_id:#04x}",
        )


def _swap_field_party_slots(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    first_index: int,
    second_index: int,
    label: str,
) -> None:
    """Swap two field-party positions while proving the exact resulting order."""

    party_reader = PokemonRedPartyReader(emulator)
    before = party_reader.read()
    if not 0 <= first_index < before.size or not 0 <= second_index < before.size:
        raise BlaineChapterError(f"{label} requested an invalid party position.")
    if first_index == second_index:
        return
    expected = list(before.species_ids())
    expected[first_index], expected[second_index] = expected[second_index], expected[first_index]
    selected = before.members[first_index]
    field_move_count = sum(move.move_id in FIELD_MOVE_IDS for move in selected.known_moves)

    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, first_index, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(field_move_count + 1):
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != field_move_count + 1:
        raise BlaineChapterError(f"{label} could not select the field SWITCH command.")
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, second_index, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _close(actions, reader)

    observed = party_reader.read().species_ids()
    if observed != tuple(expected):
        raise BlaineChapterError(
            f"{label} produced party order {observed!r}, expected {tuple(expected)!r}."
        )


def _switch_active_battler(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    target_index: int,
    label: str,
) -> bool:
    """Send a different party member into the active wild battle.

    Experience in this generation is shared by every member that was sent out,
    so a trainee only has to appear once per battle—it never has to land a hit.
    The transition fails closed with its exact menu stage so a missed switch
    can never be counted as training evidence.
    """

    raw = reader.read()
    if not 0 <= target_index < len(raw.party_species_ids or ()) or raw.battle_state != 1:
        raise BlaineChapterError(f"Cannot switch to {label} outside a live wild battle.")
    for pulse in range(48):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if raw.battle_state == 1 and menu.phase is BattleMenuPhase.MAIN:
            break
        if raw.battle_state == 0:
            raise BlaineChapterError(f"Battle ended before switching to {label}.")
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            frames=120,
        )
    else:
        raise BlaineChapterError(f"Battle menu did not settle before switching to {label}.")
    if emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == target_index:
        return True

    for pulse in range(16):
        menu = reader.read_battle_menu_state(reader.read())
        if (
            menu.phase is BattleMenuPhase.MAIN
            and menu.selected_main_command == BATTLE_PARTY_MENU_COMMAND
        ):
            break
        if menu.phase is not BattleMenuPhase.MAIN:
            _pulse(
                actions,
                MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
                frames=120,
            )
            continue
        direction = _battle_command_direction(menu.selected_main_command, BATTLE_PARTY_MENU_COMMAND)
        if direction is None:
            raise BlaineChapterError(f"Battle command cursor is invalid while selecting {label}.")
        _pulse(actions, MacroActionKind.MOVE, direction, 120)
    else:
        raise BlaineChapterError(f"Could not open the party menu for {label}.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target_index:
            break
        _pulse(actions, MacroActionKind.MOVE, "down" if cursor < target_index else "up", 120)
    else:
        raise BlaineChapterError(f"Could not select the party slot for {label}.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == PARTY_SUBMENU_SWITCH:
            break
        _pulse(actions, MacroActionKind.MOVE, "up", 120)
    else:
        raise BlaineChapterError(f"Could not select SWITCH for {label}.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)

    for pulse in range(48):
        settled = reader.read()
        menu = reader.read_battle_menu_state(settled)
        if (
            settled.battle_state == 1
            and menu.phase is BattleMenuPhase.MAIN
            and emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == target_index
        ):
            return True
        party_hp = _party_hp(emulator)
        if target_index < len(party_hp) and party_hp[target_index] == 0:
            raise BlaineChapterError(f"{label.capitalize()} fainted during the switch.")
        if settled.battle_state == 0:
            for _ in range(48):
                if reader.read_input_readiness().ready:
                    return False
                _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            raise BlaineChapterError(
                f"Battle ended safely while switching to {label}, but field input did not settle."
            )
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            frames=120,
        )
    raise BlaineChapterError(f"Switch to {label} did not return to the battle menu.")


def _battle_command_direction(current: int | None, target: int) -> str | None:
    """Return one D-pad step toward a command in Red's two-column battle menu."""

    if current not in BATTLE_COMMAND_COORDINATES:
        return None
    if target not in BATTLE_COMMAND_COORDINATES:
        return None
    current_x, current_y = BATTLE_COMMAND_COORDINATES[current]
    target_x, target_y = BATTLE_COMMAND_COORDINATES[target]
    if current_x < target_x:
        return "right"
    if current_x > target_x:
        return "left"
    if current_y < target_y:
        return "down"
    if current_y > target_y:
        return "up"
    return None


def _run_mansion_training(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> TrainingReport:
    policy = MANSION_TRAINING_POLICY
    initial = reader.read()
    starting_level = initial.first_party_level or 0
    battles_won = 0
    battles_fled = 0
    steps = 0
    healing_trips = 0
    flee_run = _RunState([])

    def observation(raw: RawGameState) -> TrainingObservation:
        return TrainingObservation(
            level=raw.first_party_level or 0,
            hp=raw.first_party_hp or 0,
            max_hp=raw.first_party_max_hp or 0,
            pp=raw.first_party_pp or (),
            in_battle=raw.battle_state == 1,
            status=raw.first_party_status or 0,
            enemy_level=raw.enemy_level,
            battles_completed=battles_won,
            steps_taken=steps,
            healing_trips=healing_trips,
        )

    while True:
        raw = reader.read()
        directive = choose_training_directive(observation(raw), policy)
        if directive is TrainingDirective.STOP:
            if (raw.first_party_level or 0) < policy.target_level:
                raise BlaineChapterError(
                    "Mansion training exhausted a safety bound before its target: "
                    f"level={raw.first_party_level}, battles={battles_won}, "
                    f"steps={steps}, healing_trips={healing_trips}."
                )
            break

        if raw.battle_state == 1:
            if directive is TrainingDirective.FLEE:
                _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                battles_fled += 1
                continue
            if directive is not TrainingDirective.FIGHT:
                raise BlaineChapterError(f"Invalid in-battle training directive {directive}.")
            run_adaptive_wild_battle(
                reader,
                actions,
                lambda state: choose_training_move_slot(
                    state.first_party_pp or (), policy.preferred_move_slots
                ),
                expected_map=MapId.POKEMON_MANSION_1F,
                label="Pokémon Mansion training encounter",
                unknown_cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                transient_zero_pp_main_is_dialogue=True,
            )
            battles_won += 1
            continue

        if directive is TrainingDirective.RETURN_TO_HEAL:
            if healing_trips >= policy.max_healing_trips:
                raise BlaineChapterError("Mansion training exhausted its healing-trip bound.")
            _training_dig_to_cinnabar(actions, reader, emulator)
            _move(actions, reader, ("up",), "training Center entry")
            _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "training Center")
            _move(actions, reader, ("up",) * 4, "training nurse")
            _heal(actions, reader, emulator)
            healing_trips += 1
            _move(actions, reader, CENTER_TO_MANSION, "training return to Mansion")
            _require(
                reader.read(),
                MapId.POKEMON_MANSION_1F,
                (5, 27),
                "training Mansion entrance",
            )
            continue

        if directive is not TrainingDirective.SEEK_ENCOUNTER:
            raise BlaineChapterError(f"Invalid field training directive {directive}.")
        if raw.map_id == MapId.CINNABAR_POKECENTER:
            _move(actions, reader, CENTER_TO_MANSION, "training first Mansion trip")
            _require(
                reader.read(),
                MapId.POKEMON_MANSION_1F,
                (5, 27),
                "training Mansion entrance",
            )
            continue
        if raw.map_id != MapId.POKEMON_MANSION_1F:
            raise BlaineChapterError(f"Mansion training left its qualified area: {raw.map_id!r}.")
        direction = "down" if (raw.player_y or 0) <= 20 else "up"
        _pulse(actions, MacroActionKind.MOVE, direction, 240)
        steps += 1

    _training_dig_to_cinnabar(actions, reader, emulator)
    _move(actions, reader, ("up",), "final training Center entry")
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "final training Center")
    _move(actions, reader, ("up",) * 4, "final training nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    return TrainingReport(
        area_id="pokemon_mansion_1f",
        starting_level=starting_level,
        target_level=policy.target_level,
        final_level=final.first_party_level or 0,
        battles_won=battles_won,
        battles_fled=battles_fled,
        steps_taken=steps,
        healing_trips=healing_trips + 1,
        fainted=any(hp == 0 for hp in _party_hp(emulator)),
    )


def _field_fly_to_cinnabar(actions, reader, emulator) -> None:
    before_bag = _bag(emulator)
    before_hp = _party_hp(emulator)
    before_status = _party_status(emulator)
    before_moves = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    before_pp = _four(emulator, RamAddress.PARTY_MON_2_PP)
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(12):
        if reader.read().map_id == MapId.CINNABAR_ISLAND:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise BlaineChapterError("Fly did not return to Cinnabar.")
    if (
        _bag(emulator) != before_bag
        or _party_hp(emulator) != before_hp
        or _party_status(emulator) != before_status
        or _four(emulator, RamAddress.PARTY_MON_2_MOVES) != before_moves
        or _four(emulator, RamAddress.PARTY_MON_2_PP) != before_pp
    ):
        raise BlaineChapterError("Fly changed protected party or inventory state.")


def _answer_quiz(actions, reader, emulator, index: int, answer: bool, text_pulses: int) -> None:
    target_event = GYM_GATE_EVENTS[index]
    if _event(emulator, target_event):
        raise BlaineChapterError(f"Quiz gate {index} was already open.")
    _face_and_interact(actions, "up")
    for _ in range(text_pulses - 1):
        _pulse(actions, MacroActionKind.CONFIRM)
    if not answer:
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM)
    if not _event(emulator, target_event) or not reader.read_input_readiness().ready:
        raise BlaineChapterError(f"Quiz gate {index} did not open on the qualified answer.")


def _heal(actions, reader, emulator) -> None:
    for _ in range(20):
        _pulse(actions, MacroActionKind.CONFIRM)
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read().first_party_pp in {(15, 15, 10, 15), (5, 15, 10, 15)}
        ):
            break
    _close(actions, reader)


def _move(actions, reader, route: Iterable[str], label: str, *, frames: int = 240) -> None:
    route = tuple(route)
    for index, direction in enumerate(route, 1):
        before = reader.read()
        for _ in range(8):
            _pulse(actions, MacroActionKind.MOVE, direction, frames)
            after = reader.read()
            if after.battle_state:
                raise BlaineChapterError(f"{label} entered battle at step {index}.")
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
        else:
            raise BlaineChapterError(f"{label} blocked at step {index}/{len(route)}.")


def _face_and_interact(actions, direction: str) -> None:
    _pulse(actions, MacroActionKind.MOVE, direction, 120)
    _pulse(actions, MacroActionKind.INTERACT)


def _close(actions, reader) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL)
    if not reader.read_input_readiness().ready:
        raise BlaineChapterError("Menus did not restore field input.")


def _select_cursor(actions, emulator, target: int, timing) -> None:
    for _ in range(20):
        top = (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        )
        if target == 1 and top == (5, 12):
            # A long training lineage can finish a party reorder while the
            # selected Pokémon's field-command submenu is still settling.
            # Close back to the field and reopen START before selecting
            # POKéMON; directional input is ignored by that stale submenu.
            for _ in range(4):
                _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
            _pulse(actions, MacroActionKind.OPEN_MENU, frames=timing.wait_frames)
            continue
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if current == target:
            return
        _pulse(actions, MacroActionKind.MOVE, "down" if current < target else "up", 120)
    raise BlaineChapterError(
        f"Menu could not select cursor {target}: "
        f"current={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
        f"max={emulator.read_u8(RamAddress.MAX_MENU_ITEM)}, "
        f"top=({emulator.read_u8(RamAddress.TOP_MENU_ITEM_X)}, "
        f"{emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y)}), "
        f"watched={emulator.read_u8(RamAddress.MENU_WATCHED_KEYS):#04x}."
    )


def _pulse(actions, kind: MacroActionKind, value: str | None = None, frames: int = 180) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _event(emulator, event: EventFlag) -> bool:
    index = int(event)
    value = emulator.read_u8(int(RamAddress.EVENT_FLAGS) + index // 8)
    return bool(value & (1 << (index % 8)))


def _events(emulator, events: Iterable[EventFlag]) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in events)


def _encounter_party(turns: tuple[BlaineTurn, ...]) -> tuple[tuple[int, int], ...]:
    party: list[tuple[int, int]] = []
    for turn in turns:
        member = (turn.enemy_species, turn.enemy_level)
        if not party or member != party[-1]:
            party.append(member)
    return tuple(party)


def _checkpoint(
    records: list[BlaineCheckpoint],
    progress: ProgressSink | None,
    emulator,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(BlaineCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            BlaineProgress(
                checkpoint_id,
                label,
                len(records),
                BLAINE_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(raw: RawGameState, map_id: int, coordinate: tuple[int, int], label: str) -> None:
    if (raw.map_id, raw.player_x, raw.player_y) != (map_id, *coordinate):
        raise BlaineChapterError(
            f"{label} expected {(int(map_id), *coordinate)!r}, got "
            f"{(raw.map_id, raw.player_x, raw.player_y)!r}."
        )
