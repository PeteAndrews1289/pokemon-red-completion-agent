"""Qualified Pokémon Mansion, Secret Key, Cinnabar Gym, and Blaine chapter.

The map routes, quiz answers, event IDs, trainer identity, party, and reward
order are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
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
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.gen1_field_moves import GEN1_FIELD_MOVE_IDS
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING, DIG
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
    _use_bag_item,
)
from pokemon_red_completion.observation import (
    Badge,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.party import PartyMemberObservation
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    PP_OFFSET,
    RED_BALANCED_ROSTER,
    PokemonRedPartyReader,
    member_field_address,
)
from pokemon_red_completion.red_team_training import (
    MEASURED_TRAINING_VENUES,
    TRAINING_ATTACK_PP_RESERVE,
    TRAINING_MOVE_IDS,
    _PauseForTeamTrainingRecovery,
    run_red_team_balancing,
)
from pokemon_red_completion.silph import DEFAULT_SILPH_TIMING, _await_trainer_battle
from pokemon_red_completion.surge import (
    VERMILION_CENTER_TO_ROUTE_11,
    VERMILION_NURSE_TO_EXIT,
    VERMILION_ROUTE_11_TO_CENTER_EXTERIOR,
)
from pokemon_red_completion.team_training import (
    COMPLETION_LEVEL_PARITY,
    BalancedTeamPolicy,
    DevelopedTeamPolicy,
    DevelopedTeamReport,
    TeamRosterPlan,
    TeamTrainingDirective,
    plan_team_development,
    summarize_team_development,
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
from pokemon_red_completion.training_candidate_rank import TrainingCandidateDecision
from pokemon_red_completion.training_control import (
    TrainingControlAction,
    TrainingControlDecision,
)
from pokemon_red_completion.training_venue import TrainingVenue

BLAINE_CHECKPOINT_COUNT = 9
MANSION_SECRET_KEY_CHECKPOINT_COUNT = 4
BLAINE_AFTER_MANSION_CHECKPOINT_COUNT = 5
BLAINE_CAPACITY_SALE_ITEM = ItemId.ANTIDOTE
BLAINE_INPUT_BAG_SLOT_BOUNDS = (15, 20)
BLAINE_GYM_TRAINER_INCOME = 6_930
BLAINE_MONEY_DELTA = 5_003 + BLAINE_GYM_TRAINER_INCOME
BLAINE_ANTIDOTE_SALE_VALUE = 50
BLAINE_POTION_SALE_VALUE = 150
BLAINE_TM21_SALE_VALUE = 2_500
BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST = 1_300
MAX_REPEL_PRICE = 700
ULTRA_BALL_PRICE = 1_200
GREAT_BALL_PRICE = 600
BLAINE_MAX_WILD_FLEES = 3
MANSION_TRAINING_FLEE_TIMING = CeladonTiming(flee_pulses=96)
BLAINE_OPPONENT = 0xEF
BLAINE_TRAINER_CLASS = 0xEF
BLAINE_TRAINER_SET = 1
BLAINE_PARTY = ((0x21, 42), (0xA3, 40), (0xA4, 42), (0x14, 47))
BLAINE_GYM_BURGLAR_OPPONENT = 0xD3
BLAINE_GYM_BURGLAR_CLASS = 0xD3
BLAINE_GYM_BURGLAR_SET_4_PARTY = ((0x21, 36), (0x52, 36), (0x53, 36))
BLAINE_GYM_BURGLAR_SET_5_PARTY = ((0xA3, 41),)
HYDRO_PUMP_MOVE_ID = 0x38
HYDRO_PUMP_LEARN_LEVEL = 52
# No trainer switch prompt can occur in this wild-only block.  Keeping CANCEL
# outside the bounded runtime therefore accepts Blastoise's level-52 Hydro Pump
# prompt and its default slot-one replacement instead of silently declining it.
MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL = 10_000
JOLTEON_SPECIES_ID = 0x68
MANSION_TRAINING_POLICY = TrainingPolicy(
    target_level=60,
    preferred_move_slots=(4, 2, 3, 1),
    retreat_hp_ratio=0.45,
    reserve_total_pp=2,
    max_enemy_level_delta=0,
    max_battles=800,
    max_steps=80_000,
    max_healing_trips=100,
)
#: The strongest Pokémon the Indigo League fields.
INDIGO_MAX_OPPOSITION_LEVEL = 65

MANSION_DEVELOPMENT_POLICY = DevelopedTeamPolicy(
    roster=RED_BALANCED_ROSTER,
    workhorse_species_id=BLASTOISE_SPECIES_ID,
    workhorse_target_level=60,
    level_parity=COMPLETION_LEVEL_PARITY,
    parity_opposition_level=INDIGO_MAX_OPPOSITION_LEVEL,
)
PRE_SAFFRON_BALANCED_ROSTER = TeamRosterPlan(
    tuple(
        slot
        for slot in RED_BALANCED_ROSTER.slots
        if slot.species_id
        in {BLASTOISE_SPECIES_ID, DUGTRIO_SPECIES_ID, 0x40, 0x84}
    )
)
PRE_SAFFRON_DEVELOPMENT_POLICY = replace(
    MANSION_DEVELOPMENT_POLICY,
    roster=PRE_SAFFRON_BALANCED_ROSTER,
)
#: How far below the League a natural playthrough arrives.  A player who used a
#: team throughout the game reaches Indigo in the mid-fifties; that is the band
#: where switching and type choices still decide battles.  Above it the team
#: wins on stats alone and the demonstrations stop containing decisions.
# Removed local level parity contract, using COMPLETION_LEVEL_PARITY instead

#: Balance contract for the Mansion block.
#:
#: ``required_size`` tracks the complete declared roster assembled before this
#: long-form balancing block.
#:
#: ``minimum_level`` is derived from the League rather than written as a
#: constant, so it states *why* the number is what it is and moves with the
#: opposition instead of being tuned by hand.
#:
#: ``maximum_level_spread`` is deliberately non-binding.  Measured inside the
#: party it anchored to the strongest member -- an escort at 84 -- and dragged
#: every trainee up to 79 against opposition of 65.  A measured run paid 4,570
#: battles and 1,063 healing trips for that overshoot, arriving nineteen levels
#: past parity.  Readiness is a question about the opposition, not about the
#: escort, so the spread is now reported rather than chased.
MANSION_TEAM_POLICY = BalancedTeamPolicy(
    minimum_level=COMPLETION_LEVEL_PARITY.required_level(INDIGO_MAX_OPPOSITION_LEVEL),
    maximum_level_spread=40,
    required_size=6,
    retreat_hp_ratio=0.90,
    # The lead-only block reserved 2 PP because it ran barely a hundred battles
    # at an overwhelming level advantage.  Team training runs far longer, so it
    # returns to heal with a real margin instead of fighting to exhaustion and
    # discovering mid-battle that its last slot is Disabled.
    reserve_total_pp=16,
    # Training margin, expressed relatively so it transfers to any title.
    #
    # This block previously demanded a fifteen-level advantage, inherited from
    # the lead-only route where one overleveled carry outclassed everything and
    # the requirement never bound.  It binds on a real team, and it binds
    # hardest on the weakest members: measured against the harvested bands, a
    # level-20 trainee could engage nothing above level 5, so venue selection
    # sent it to Viridian Forest to fight level-3 Caterpie.  That is safe and it
    # is not training.  Experience scales with the defeated Pokemon's level, so
    # a rule permitting only opponents far below guarantees the slowest possible
    # progress.
    #
    # The +2 experiment is now rejected by live evidence. A level-23 Diglett
    # was knocked out from full HP by a level-19 Diglett before acting, so even
    # a four-level lead cannot support the zero-faint contract. Five levels is
    # the first boundary the measurement has not contradicted. Route 11 is an
    # implemented venue below the Cave so this margin does not send the early
    # trainees back to level-three encounters.
    max_enemy_level_delta=0,
    minimum_direct_level_advantage=5,
    safe_lead_level=42,
    # A measured clean-power run reached parity (level 60+) near battle 1,500
    # and then spent roughly 3,000 more closing an internal spread against the
    # escort. With the spread no longer driving training, the budget retains
    # generous headroom over the parity requirement rather than the overshoot.
    max_battles=7_000,
    max_steps=500_000,
    # Recovery demand varies with encounter damage, not only with the number of
    # wins. One complete development lineage required 1,808 battles and 1,175
    # Center trips; a later unopened lineage safely reached 1,500 wins but used
    # the old 1,250-trip cap with two trainees only one level short. Preserve
    # the measured 90% retreat threshold and zero-faint contract. A rounded
    # 2,000-trip ceiling permits one recovery per battle across the largest
    # completed block while remaining a finite, independently enforced bound.
    max_healing_trips=2_000,
    max_faints=0,
)
PRE_SAFFRON_TEAM_POLICY = replace(
    MANSION_TEAM_POLICY,
    required_size=len(PRE_SAFFRON_BALANCED_ROSTER.slots),
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
# Muk can outlast a trainee's weak coverage and turn a safe starting-HP check
# into a long attritional knockout. A held-out feature-v2 collection also
# observed a level-29 Dugtrio knock out a full-health level-34 trainee before
# the per-turn retreat callback could protect it. Both are fled rather than
# gambling the zero-faint contract or feeding the already-high Blastoise.
MANSION_ESCORT_ENEMY_SPECIES = frozenset({0x88, DUGTRIO_SPECIES_ID})
# Koffing and Weezing can end an encounter with Selfdestruct while a trainee is
# switching to the escort. They are never assigned to a trainee directly. A
# terminal Selfdestruct is counted only after the zero-faint check; otherwise
# the healthy escort flees so it does not widen the level spread unnecessarily.
MANSION_VOLATILE_ENEMY_SPECIES = frozenset({0x37, 0x8F})
# A healthy training route can draw long streaks of excluded encounters. This
# value is the horizon at which the portable consecutive-flee feature saturates;
# the global step budget, not the saturated feature, bounds a non-progressing run.
MANSION_MAX_CONSECUTIVE_FLEES = 32
MANSION_LEAD_TRAINING_INTENT = BattleIntent(
    "train_party",
    battle_plan_id="red.mansion.lead-leveling",
    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
)
MANSION_BALANCED_TEAM_TRAINING_INTENT = BattleIntent(
    "build_balanced_team",
    battle_plan_id="red.mansion.balanced-team-training",
    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
)
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
QUIZ_CORRECT_ANSWERS = (True, False, False, False, True, False)
# Intentionally miss the first and third quizzes.  Their adjacent Burglars
# provide a deterministic late-game income and experience buffer instead of
# relying on low capture costs or selling useful supplies.
QUIZ_TRAINER_BATTLE_INDEXES = (1, 3)
QUIZ_ANSWERS = tuple(
    not answer if index in QUIZ_TRAINER_BATTLE_INDEXES else answer
    for index, answer in enumerate(QUIZ_CORRECT_ANSWERS, 1)
)
QUIZ_TEXT_PULSES = (9, 10, 9, 11, 11, 9)
CINNABAR_GYM_TRAINER_PLANS = {
    1: (
        "Cinnabar Gym Burglar set 4",
        (BLAINE_GYM_BURGLAR_OPPONENT, BLAINE_GYM_BURGLAR_CLASS, 4),
        BLAINE_GYM_BURGLAR_SET_4_PARTY,
        3_240,
        RedBattlePlanId.BLAINE_GYM_BURGLAR_SET_4,
    ),
    3: (
        "Cinnabar Gym Burglar set 5",
        (BLAINE_GYM_BURGLAR_OPPONENT, BLAINE_GYM_BURGLAR_CLASS, 5),
        BLAINE_GYM_BURGLAR_SET_5_PARTY,
        3_690,
        RedBattlePlanId.BLAINE_GYM_BURGLAR_SET_5,
    ),
}


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
    # Quiz-one's Burglar remains at (16, 8) after stepping toward the player.
    # Walk around him through the open row below before resuming the original
    # approach at (16, 7).
    _directions("DRRUULRRUUUUUULLLLLLDLL"),
    _directions("RRDDDDDLLDL"),
    # Quiz-three's Burglar likewise occupies the old first step at (10, 8).
    _directions("DRRRDDDDLLDL"),
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
class CinnabarGymTrainerReceipt:
    quiz_index: int
    identity: tuple[int, int, int]
    expected_party: tuple[tuple[int, int], ...]
    turns: tuple[BlaineTurn, ...]
    money_before: int
    money_after: int
    expected_reward: int

    @property
    def passed(self) -> bool:
        plan = CINNABAR_GYM_TRAINER_PLANS.get(self.quiz_index)
        return (
            plan is not None
            and self.identity == plan[1]
            and self.expected_party == plan[2]
            and self.expected_reward == plan[3]
            and _encounter_party(self.turns) == self.expected_party
            and bool(self.turns)
            and all(turn.move_slot == 4 for turn in self.turns)
            and all(turn.lead_hp > 0 and turn.lead_status == 0 for turn in self.turns)
            and self.money_after - self.money_before == self.expected_reward
        )


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
    gym_trainer_events_after_quizzes: tuple[bool, ...]
    quiz_trainer_battles: tuple[CinnabarGymTrainerReceipt, ...]
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
    antidote_sold_quantity: int
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
    capacity_great_ball_bought: bool = False
    initial_bag_slot_count: int = 17
    potion_sold_quantity: int = 0
    team_readiness: DevelopedTeamReport | None = None
    team_training_battles: int = 0
    team_training_healing_trips: int = 0
    tm21_sold_early: bool = False

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
            and self.gym_trainer_events_after_quizzes
            == (False, True, False, True, False, False, False)
            and tuple(item.quiz_index for item in self.quiz_trainer_battles)
            == QUIZ_TRAINER_BATTLE_INDEXES
            and all(item.passed for item in self.quiz_trainer_battles)
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
            and self.capacity_ultra_ball_bought
            == (
                self.initial_bag_slot_count
                - int(self.potion_sold_quantity > 0)
                + int(self.capacity_great_ball_bought)
                == 16
            )
            and (not self.capacity_great_ball_bought or self.initial_bag_slot_count >= 15)
            and self.money_remaining
            == self.initial_money
            + BLAINE_MONEY_DELTA
            - (self.max_repel_bought - 1) * MAX_REPEL_PRICE
            + (self.antidote_sold_quantity - 1) * BLAINE_ANTIDOTE_SALE_VALUE
            + self.potion_sold_quantity * BLAINE_POTION_SALE_VALUE
            + int(self.tm21_sold_early) * BLAINE_TM21_SALE_VALUE
            - (ULTRA_BALL_PRICE if self.capacity_ultra_ball_bought else 0)
            - (BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST if self.capacity_great_ball_bought else 0)
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
            "gym_trainers_after_quizzes": self.gym_trainer_events_after_quizzes
            == (False, True, False, True, False, False, False),
            "quiz_trainer_battles": tuple(item.quiz_index for item in self.quiz_trainer_battles)
            == QUIZ_TRAINER_BATTLE_INDEXES
            and all(item.passed for item in self.quiz_trainer_battles),
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
            + (self.antidote_sold_quantity - 1) * BLAINE_ANTIDOTE_SALE_VALUE
            + self.potion_sold_quantity * BLAINE_POTION_SALE_VALUE
            + int(self.tm21_sold_early) * BLAINE_TM21_SALE_VALUE
            - (ULTRA_BALL_PRICE if self.capacity_ultra_ball_bought else 0)
            - (BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST if self.capacity_great_ball_bought else 0),
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
                "team_development": {
                    "observed_levels": (
                        list(self.team_readiness.observed_levels) if self.team_readiness else []
                    ),
                    "minimum_level": (
                        self.team_readiness.minimum_level if self.team_readiness else None
                    ),
                    "maximum_level": (
                        self.team_readiness.maximum_level if self.team_readiness else None
                    ),
                    "level_spread": (
                        self.team_readiness.level_spread if self.team_readiness else None
                    ),
                    "final_forms_complete": (
                        self.team_readiness.has_final_form_roster if self.team_readiness else None
                    ),
                    "workhorse_species": (
                        self.team_readiness.workhorse_species_id if self.team_readiness else None
                    ),
                    "workhorse_level": (
                        self.team_readiness.observed_workhorse_level
                        if self.team_readiness
                        else None
                    ),
                    "workhorse_target_level": (
                        self.team_readiness.workhorse_target_level if self.team_readiness else None
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
                "correct_answers": ["yes" if answer else "no" for answer in QUIZ_CORRECT_ANSWERS],
                "gates_after": list(self.gym_gate_events_after_quizzes),
                "trainers_before": list(self.gym_trainer_events_before),
                "trainers_after": list(self.gym_trainer_events_after_quizzes),
                "trainer_battles": [
                    {
                        "quiz_index": item.quiz_index,
                        "identity": list(item.identity),
                        "party": [list(member) for member in item.expected_party],
                        "reward": item.money_after - item.money_before,
                        "move_slots": [turn.move_slot for turn in item.turns],
                    }
                    for item in self.quiz_trainer_battles
                ],
                "income_buffer": BLAINE_GYM_TRAINER_INCOME,
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
                "antidote_sold_quantity": self.antidote_sold_quantity,
                "potion_sold_quantity": self.potion_sold_quantity,
                "tm21_sold_early": self.tm21_sold_early,
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


@dataclass(frozen=True, slots=True)
class MansionSecretKeyReport:
    """Evidence for the Mansion-only objective boundary before team training and Blaine."""

    records: tuple[BlaineCheckpoint, ...]
    final_raw: RawGameState
    switch_trace: tuple[bool, ...]
    trainer_events_before: tuple[bool, ...]
    trainer_events_after: tuple[bool, ...]
    wild_flees: tuple[CeladonWildFleeEvidence, ...]
    secret_key_quantity: int
    tm14_quantity: int
    x_accuracy_retained: bool
    blaine_defeated: bool
    volcano_badge: bool
    initial_bag_slots: int
    final_bag_slots: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == MANSION_SECRET_KEY_CHECKPOINT_COUNT
            and self.switch_trace == (False, True, False, True)
            and self.trainer_events_before == (False,) * 6
            and self.trainer_events_after == (False,) * 6
            and len(self.wild_flees) <= BLAINE_MAX_WILD_FLEES
            and all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.wild_flees
            )
            and self.secret_key_quantity == 1
            and self.tm14_quantity == 1
            and self.x_accuracy_retained
            and not self.blaine_defeated
            and not self.volcano_badge
            and BLAINE_INPUT_BAG_SLOT_BOUNDS[0]
            <= self.initial_bag_slots
            <= BLAINE_INPUT_BAG_SLOT_BOUNDS[1]
            and self.final_bag_slots <= 20
            and self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "obtain_secret_key",
            "switch_trace": list(self.switch_trace),
            "optional_trainers_before": list(self.trainer_events_before),
            "optional_trainers_after": list(self.trainer_events_after),
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
                for item in self.wild_flees
            ],
            "inventory": {
                "secret_key": self.secret_key_quantity,
                "tm14_blizzard": self.tm14_quantity,
                "x_accuracy_retained": self.x_accuracy_retained,
                "bag_slots": [self.initial_bag_slots, self.final_bag_slots],
            },
            "blaine_untouched": not self.blaine_defeated and not self.volcano_badge,
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


@dataclass(frozen=True, slots=True)
class BlaineAfterMansionReport:
    """Evidence for training and Blaine from the authenticated Secret Key boundary."""

    records: tuple[BlaineCheckpoint, ...]
    final_raw: RawGameState
    training: TrainingReport
    team_readiness: DevelopedTeamReport
    team_training_battles: int
    team_training_healing_trips: int
    quiz_answers: tuple[bool, ...]
    gym_gate_events_after_quizzes: tuple[bool, ...]
    gym_trainer_events_before: tuple[bool, ...]
    gym_trainer_events_after_quizzes: tuple[bool, ...]
    quiz_trainer_battles: tuple[CinnabarGymTrainerReceipt, ...]
    gym_trainer_events_after: tuple[bool, ...]
    identity: tuple[int, int, int]
    turns: tuple[BlaineTurn, ...]
    got_tm38: bool
    beat_blaine: bool
    volcano_badge: bool
    volcano_badge_mirror: bool
    tm38_quantity: int
    secret_key_quantity: int
    tm14_quantity: int
    x_accuracy_retained: bool
    capacity_item_sold: ItemId
    initial_money: int
    money_remaining: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == BLAINE_AFTER_MANSION_CHECKPOINT_COUNT
            and self.training.passed
            and self.team_readiness.passed
            and self.quiz_answers == QUIZ_ANSWERS
            and self.gym_gate_events_after_quizzes == (False,) + (True,) * 6
            and self.gym_trainer_events_before == (False,) * 7
            and self.gym_trainer_events_after_quizzes
            == (False, True, False, True, False, False, False)
            and tuple(item.quiz_index for item in self.quiz_trainer_battles)
            == QUIZ_TRAINER_BATTLE_INDEXES
            and all(item.passed for item in self.quiz_trainer_battles)
            and self.gym_trainer_events_after == (True,) * 7
            and self.identity == (BLAINE_OPPONENT, BLAINE_TRAINER_CLASS, BLAINE_TRAINER_SET)
            and _encounter_party(self.turns) == BLAINE_PARTY
            and bool(self.turns)
            and all(turn.move_slot == 4 for turn in self.turns)
            and self.got_tm38
            and self.beat_blaine
            and self.volcano_badge
            and self.volcano_badge_mirror
            and self.tm38_quantity == 1
            and self.secret_key_quantity == 1
            and self.tm14_quantity == 1
            and self.x_accuracy_retained
            and self.capacity_item_sold not in (self.final_raw.bag_item_ids or ())
            and self.money_remaining > self.initial_money
            and self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_blaine",
            "team_development": {
                "levels": list(self.team_readiness.observed_levels),
                "final_forms_complete": self.team_readiness.has_final_form_roster,
                "battles": self.team_training_battles,
                "healing_trips": self.team_training_healing_trips,
            },
            "training": {
                "area": self.training.area_id,
                "levels": [self.training.starting_level, self.training.final_level],
                "battles_won": self.training.battles_won,
                "healing_trips": self.training.healing_trips,
            },
            "quiz": {
                "answers": ["yes" if answer else "no" for answer in self.quiz_answers],
                "trainer_battles": [item.quiz_index for item in self.quiz_trainer_battles],
            },
            "blaine": {
                "identity": list(self.identity),
                "party": [list(member) for member in BLAINE_PARTY],
                "move_slots": [turn.move_slot for turn in self.turns],
            },
            "rewards": {
                "tm38": self.tm38_quantity,
                "volcano_badge": self.volcano_badge,
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


def run_mansion_secret_key_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> MansionSecretKeyReport:
    """Recover the Secret Key and stop before training or entering Cinnabar Gym."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[BlaineCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CINNABAR_POKECENTER, (3, 3), "post-Cinnabar boundary")
    initial_bag = _bag(emulator)
    bide_present = initial_bag.get(ItemId.TM34_BIDE, 0) == 1
    capacity_input_slots, potion_sold_quantity = _blaine_capacity_input_slots(
        len(initial_bag),
        initial_bag.get(ItemId.POTION, 0),
        bide_present=bide_present,
        force_potion_sale=(
            len(initial_bag) == 18
            and not bide_present
            and initial_bag.get(ItemId.ANTIDOTE, 0) == 0
            and initial_bag.get(ItemId.TM21_MEGA_DRAIN, 0) == 0
        ),
    )
    (
        capacity_great_ball_required,
        capacity_ultra_ball_bought,
        repel_purchase_quantity,
        effective_input_slots,
    ) = _blaine_capacity_plan(capacity_input_slots, bide_present=bide_present)
    if (
        initial_bag.get(ItemId.SECRET_KEY, 0)
        or _event(emulator, EventFlag.BEAT_BLAINE)
        or _event(emulator, EventFlag.GOT_TM38)
        or initial.badge_bits & Badge.VOLCANO
    ):
        raise BlaineChapterError("Mansion input boundary is not pristine.")
    if (
        not BLAINE_INPUT_BAG_SLOT_BOUNDS[0] <= len(initial_bag) <= BLAINE_INPUT_BAG_SLOT_BOUNDS[1]
        or initial_bag.get(ItemId.X_ACCURACY, 0) != 1
        or initial_bag.get(ItemId.TM34_BIDE, 0) not in {0, 1}
        or (capacity_great_ball_required and initial_bag.get(ItemId.POKE_BALL, 0) != 1)
        or not 16 <= effective_input_slots <= 20
        or not 0 <= initial_bag.get(ItemId.ANTIDOTE, 0) <= 99
        or (
            effective_input_slots in {19, 20}
            and initial_bag.get(ItemId.ANTIDOTE, 0) == 0
            and initial_bag.get(ItemId.TM21_MEGA_DRAIN, 0) != 1
        )
        or (len(initial_bag) == 20 and potion_sold_quantity == 0)
    ):
        raise BlaineChapterError("Cinnabar input inventory lacks Mansion capacity items.")
    mansion_before = _events(emulator, MANSION_TRAINER_EVENTS)
    if mansion_before != (False,) * 6:
        raise BlaineChapterError("A Pokémon Mansion trainer was already defeated.")
    switch_trace = [_event(emulator, EventFlag.MANSION_SWITCH_ON)]
    if switch_trace != [False]:
        raise BlaineChapterError("Pokémon Mansion switch did not start off.")
    _checkpoint(records, progress, emulator, initial, "mansion_ready", "Mansion route ready")

    _move(actions, reader, CENTER_TO_MART, "Cinnabar Mart")
    _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "Cinnabar Mart entry")
    _move(actions, reader, ("up", "up", "left"), "Cinnabar clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    if potion_sold_quantity:
        _sell_bag_item_stack(actions, reader, emulator, ItemId.POTION, potion_sold_quantity)
        _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    sell_antidote_early = _sell_antidote_before_mansion(
        effective_input_slots,
        initial_bag.get(ItemId.ANTIDOTE, 0),
    )
    sell_tm21_early = effective_input_slots in {19, 20} and initial_bag.get(ItemId.ANTIDOTE, 0) == 0
    if sell_antidote_early:
        _sell_bag_item_stack(
            actions,
            reader,
            emulator,
            BLAINE_CAPACITY_SALE_ITEM,
            initial_bag.get(BLAINE_CAPACITY_SALE_ITEM, 0),
        )
    elif sell_tm21_early:
        _sell_bag_item_stack(actions, reader, emulator, ItemId.TM21_MEGA_DRAIN, 1)
    else:
        _open_sell_menu(actions, emulator)
    _buy_repel(
        actions,
        reader,
        emulator,
        quantity=repel_purchase_quantity,
        buy_ultra_ball=capacity_ultra_ball_bought,
        buy_great_ball=capacity_great_ball_required,
    )
    _use_bag_item(actions, reader, emulator, DEFAULT_LAVENDER_TIMING, ItemId.MAX_REPEL)

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
    _toggle_statue(actions, reader, emulator, expected=True)
    switch_trace.append(True)
    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_3F_TO_B1F + MANSION_B1F_TO_STATUE,
        "Mansion B1F south statue",
    )
    _toggle_statue(actions, reader, emulator, expected=False)
    switch_trace.append(False)
    _move(actions, reader, ("right",), "Mansion TM14 approach")
    _pick_up_mansion_item(actions, reader, emulator, ItemId.TM14_BLIZZARD, "TM14 Blizzard")
    _move(actions, reader, ("left",), "Mansion south statue return")
    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_B1F_TO_NORTH_STATUE,
        "Mansion B1F north statue",
    )
    _toggle_statue(actions, reader, emulator, expected=True)
    switch_trace.append(True)
    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_B1F_TO_SECRET_KEY,
        "Mansion Secret Key",
    )
    _pick_up_secret_key(actions, reader, emulator)
    mansion_after = _events(emulator, MANSION_TRAINER_EVENTS)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "secret_key_obtained",
        "Recovered Secret Key",
    )

    _return_from_mansion_to_cinnabar(actions, reader, emulator)
    _move(actions, reader, ("up",), "Cinnabar Center entry")
    _move(actions, reader, ("up",) * 4, "Cinnabar nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    _checkpoint(
        records,
        progress,
        emulator,
        final,
        "mansion_returned",
        "Returned safely from Mansion",
    )

    report = MansionSecretKeyReport(
        records=tuple(records),
        final_raw=final,
        switch_trace=tuple(switch_trace),
        trainer_events_before=mansion_before,
        trainer_events_after=mansion_after,
        wild_flees=tuple(wilds),
        secret_key_quantity=_bag(emulator).get(ItemId.SECRET_KEY, 0),
        tm14_quantity=_bag(emulator).get(ItemId.TM14_BLIZZARD, 0),
        x_accuracy_retained=_bag(emulator).get(ItemId.X_ACCURACY, 0) == 1,
        blaine_defeated=_event(emulator, EventFlag.BEAT_BLAINE),
        volcano_badge=bool(final.badge_bits & Badge.VOLCANO),
        initial_bag_slots=len(initial_bag),
        final_bag_slots=len(_bag(emulator)),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise BlaineChapterError(f"Mansion evidence contract failed: {report.public_dict()!r}.")
    return report


def run_blaine_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
    training_candidate_decision_sink: Callable[[TrainingCandidateDecision], None] | None = None,
    training_candidate_decision_authority: Callable[[TrainingCandidateDecision], int] | None = None,
) -> BlaineChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[BlaineCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CINNABAR_POKECENTER, (3, 3), "post-Cinnabar boundary")
    initial_money = _money(emulator)
    initial_bag = _bag(emulator)
    bide_present = initial_bag.get(ItemId.TM34_BIDE, 0) == 1
    capacity_input_slots, potion_sold_quantity = _blaine_capacity_input_slots(
        len(initial_bag),
        initial_bag.get(ItemId.POTION, 0),
        bide_present=bide_present,
        force_potion_sale=(
            len(initial_bag) == 18
            and not bide_present
            and initial_bag.get(ItemId.ANTIDOTE, 0) == 0
            and initial_bag.get(ItemId.TM21_MEGA_DRAIN, 0) == 0
        ),
    )
    (
        capacity_great_ball_required,
        capacity_ultra_ball_bought,
        repel_purchase_quantity,
        effective_input_slots,
    ) = _blaine_capacity_plan(capacity_input_slots, bide_present=bide_present)
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
        or initial_bag.get(ItemId.TM34_BIDE, 0) not in {0, 1}
        or (capacity_great_ball_required and initial_bag.get(ItemId.POKE_BALL, 0) != 1)
        or not 16 <= effective_input_slots <= 20
        or not 0 <= initial_bag.get(ItemId.ANTIDOTE, 0) <= 99
        or (
            effective_input_slots in {19, 20}
            and initial_bag.get(ItemId.ANTIDOTE, 0) == 0
            and initial_bag.get(ItemId.TM21_MEGA_DRAIN, 0) != 1
        )
        or (len(initial_bag) == 20 and potion_sold_quantity == 0)
    ):
        raise BlaineChapterError(
            "Cinnabar input inventory lacks the qualified capacity items: "
            f"slots={len(initial_bag)}, "
            f"x_accuracy={initial_bag.get(ItemId.X_ACCURACY, 0)}, "
            f"bide={initial_bag.get(ItemId.TM34_BIDE, 0)}, "
            f"capacity_ball={initial_bag.get(ItemId.POKE_BALL, 0)}, "
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
    if potion_sold_quantity:
        _sell_bag_item_stack(
            actions,
            reader,
            emulator,
            ItemId.POTION,
            potion_sold_quantity,
        )
        if _bag(emulator).get(ItemId.POTION, 0):
            raise BlaineChapterError("Obsolete Potion sale did not settle.")
        _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    sell_antidote_early = _sell_antidote_before_mansion(
        effective_input_slots,
        initial_bag.get(ItemId.ANTIDOTE, 0),
    )
    sell_tm21_early = effective_input_slots in {19, 20} and initial_bag.get(ItemId.ANTIDOTE, 0) == 0
    if sell_antidote_early:
        _sell_bag_item_stack(
            actions,
            reader,
            emulator,
            BLAINE_CAPACITY_SALE_ITEM,
            initial_bag.get(BLAINE_CAPACITY_SALE_ITEM, 0),
        )
        if _bag(emulator).get(BLAINE_CAPACITY_SALE_ITEM, 0):
            raise BlaineChapterError("Obsolete Antidote sale did not settle.")
    elif sell_tm21_early:
        _sell_bag_item_stack(
            actions,
            reader,
            emulator,
            ItemId.TM21_MEGA_DRAIN,
            1,
        )
        if _bag(emulator).get(ItemId.TM21_MEGA_DRAIN, 0):
            raise BlaineChapterError("Obsolete TM21 sale did not settle.")
    else:
        _open_sell_menu(actions, emulator)
    # Retain TM21 when possible so TM14 plus the Secret Key still fill the bag.
    # A capacity-bound lineage with no Antidote sells that later-unused TM
    # instead; the two Mansion pickups still restore the delayed-TM38 boundary.
    # Stay in SELL so _buy_repel can return directly to BUY/SELL.
    _buy_repel(
        actions,
        reader,
        emulator,
        quantity=repel_purchase_quantity,
        buy_ultra_ball=capacity_ultra_ball_bought,
        buy_great_ball=capacity_great_ball_required,
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

    _return_from_mansion_to_cinnabar(actions, reader, emulator)
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

    development_policy = (
        PRE_SAFFRON_DEVELOPMENT_POLICY
        if initial.party_count == len(PRE_SAFFRON_BALANCED_ROSTER.slots)
        else MANSION_DEVELOPMENT_POLICY
    )
    team_policy = (
        PRE_SAFFRON_TEAM_POLICY
        if development_policy is PRE_SAFFRON_DEVELOPMENT_POLICY
        else MANSION_TEAM_POLICY
    )
    development = plan_team_development(
        PokemonRedPartyReader(emulator).read(), development_policy
    )
    team_battles = 0
    team_healing_trips = 0
    if development.directive is TeamTrainingDirective.EVOLVE_MEMBER:
        _, evolution_battles, evolution_heals = run_red_team_balancing(
            actions,
            reader,
            emulator,
            policy=team_policy,
            venues=(
                ROUTE_11_TRAINING_VENUE,
                DIGLETTS_CAVE_TRAINING_VENUE,
                MANSION_TRAINING_VENUE,
            ),
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=_flee,
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            candidate_decision_sink=training_candidate_decision_sink,
            candidate_decision_authority=training_candidate_decision_authority,
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            report_label="Mansion team training",
            checkpoint_count=BLAINE_CHECKPOINT_COUNT,
        )
        team_battles += evolution_battles
        team_healing_trips += evolution_heals

    # The evolution pass breaks as soon as the final species appears, without
    # checking readiness.  Until now it was the only call, so the balancing pass
    # below -- the one that enforces MANSION_TEAM_POLICY's level floor and
    # spread -- was never reached, and the party finished the game at
    # [68, 20, 26, 30, 25, 30].  Run it.
    _, balance_battles, balance_heals = run_red_team_balancing(
        actions,
        reader,
        emulator,
        policy=team_policy,
        venues=(
            ROUTE_11_TRAINING_VENUE,
            DIGLETTS_CAVE_TRAINING_VENUE,
            MANSION_TRAINING_VENUE,
        ),
        intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
        flee_timing=MANSION_TRAINING_FLEE_TIMING,
        hideout_timing=DEFAULT_HIDEOUT_TIMING,
        flee_func=_flee,
        volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
        escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
        max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
        cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
        candidate_decision_sink=training_candidate_decision_sink,
        candidate_decision_authority=training_candidate_decision_authority,
        progress_sink=(
            (
                lambda message: progress(
                    BlaineProgress(
                        "mansion_team_training_progress",
                        message,
                        len(records),
                        BLAINE_CHECKPOINT_COUNT,
                        emulator.frame_count,
                    )
                )
            )
            if progress is not None
            else None
        ),
        completed_checkpoint_count=len(records),
        report_label="Mansion team training",
        checkpoint_count=BLAINE_CHECKPOINT_COUNT,
    )
    team_battles += balance_battles
    team_healing_trips += balance_heals

    training = _run_mansion_training(actions, reader, emulator)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "mansion_training_complete",
        "Trained safely in Pokémon Mansion",
    )

    team_readiness = _qualify_mansion_team_development(
        reader,
        emulator,
        policy=development_policy,
    )
    if not team_readiness.passed:
        raise BlaineChapterError("Team development failed the parity contract.")

    _move(actions, reader, ("down",) * 5 + GYM_ENTRY_ROUTE, "Cinnabar Gym")
    _require(reader.read(), MapId.CINNABAR_GYM, (16, 17), "Cinnabar Gym entrance")
    gym_before = _events(emulator, GYM_TRAINER_EVENTS)
    if gym_before != (False,) * 7:
        raise BlaineChapterError("A Cinnabar Gym trainer was already defeated.")
    quiz_trainer_battles: list[CinnabarGymTrainerReceipt] = []
    for index, (route, answer, text_pulses) in enumerate(
        zip(GYM_QUIZ_ROUTES, QUIZ_ANSWERS, QUIZ_TEXT_PULSES, strict=True),
        1,
    ):
        _move(actions, reader, route, f"Cinnabar quiz {index}")
        receipt = _answer_quiz(actions, reader, emulator, index, answer, text_pulses)
        if receipt is not None:
            quiz_trainer_battles.append(receipt)
        expected_trainers = tuple(
            trainer_index in {item.quiz_index for item in quiz_trainer_battles}
            for trainer_index in range(7)
        )
        observed_trainers = _events(emulator, GYM_TRAINER_EVENTS)
        if observed_trainers != expected_trainers:
            raise BlaineChapterError(
                f"Quiz {index} trainer state changed: expected {expected_trainers!r}, "
                f"got {observed_trainers!r}."
            )
    gates_after = _events(emulator, GYM_GATE_EVENTS)
    gym_after_quizzes = _events(emulator, GYM_TRAINER_EVENTS)
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

    def record_turn(raw: RawGameState, slot: int) -> None:
        turns.append(
            BlaineTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                slot,
            )
        )

    run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _raw: 4,
        expected_map=MapId.CINNABAR_GYM,
        intent=BattleIntent(
            "defeat_blaine",
            battle_plan_id=RedBattlePlanId.BLAINE_LEADER,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(SURF_MOVE_ID),
        ),
        required_move_id=SURF_MOVE_ID,
        label="Blaine",
        move_decision_sink=record_turn,
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
    capacity_sale_item = ItemId.GREAT_BALL if capacity_great_ball_required else ItemId.TM34_BIDE
    _sell_current_bag_item(actions, reader, emulator, capacity_sale_item)
    if _bag(emulator).get(capacity_sale_item, 0):
        raise BlaineChapterError(f"{capacity_sale_item.name} capacity sale did not settle.")
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
        gym_trainer_events_after_quizzes=gym_after_quizzes,
        quiz_trainer_battles=tuple(quiz_trainer_battles),
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
        antidote_sold_quantity=(initial_bag.get(ItemId.ANTIDOTE, 0) if sell_antidote_early else 0),
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
        capacity_great_ball_bought=capacity_great_ball_required,
        initial_bag_slot_count=len(initial_bag),
        potion_sold_quantity=potion_sold_quantity,
        tm21_sold_early=sell_tm21_early,
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


def run_blaine_after_mansion_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
    training_decision_sink: Callable[[TrainingControlDecision], None] | None = None,
    training_decision_authority: Callable[
        [TrainingControlDecision], TrainingControlAction
    ]
    | None = None,
    training_candidate_decision_sink: Callable[[TrainingCandidateDecision], None]
    | None = None,
    training_candidate_decision_authority: Callable[[TrainingCandidateDecision], int]
    | None = None,
) -> BlaineAfterMansionReport:
    """Train the party and defeat Blaine after the Secret Key skill releases control."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[BlaineCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CINNABAR_POKECENTER, (3, 3), "post-Mansion boundary")
    initial_bag = _bag(emulator)
    initial_money = _money(emulator)
    if (
        initial_bag.get(ItemId.SECRET_KEY, 0) != 1
        or initial_bag.get(ItemId.TM14_BLIZZARD, 0) != 1
        or initial_bag.get(ItemId.X_ACCURACY, 0) != 1
        or _event(emulator, EventFlag.BEAT_BLAINE)
        or _event(emulator, EventFlag.GOT_TM38)
        or initial.badge_bits & Badge.VOLCANO
    ):
        raise BlaineChapterError("Post-Mansion Blaine boundary is not pristine.")
    capacity_items = tuple(
        item
        for item in (ItemId.GREAT_BALL, ItemId.TM34_BIDE)
        if initial_bag.get(item, 0) == 1
    )
    if len(capacity_items) != 1:
        raise BlaineChapterError("Post-Mansion boundary lacks one declared TM38 capacity item.")
    capacity_great_ball_required = capacity_items[0] is ItemId.GREAT_BALL
    if _events(emulator, MANSION_TRAINER_EVENTS) != (False,) * 6:
        raise BlaineChapterError("The Secret Key lesson changed an optional Mansion trainer.")
    if _events(emulator, GYM_TRAINER_EVENTS) != (False,) * 7:
        raise BlaineChapterError("A Cinnabar Gym trainer was already defeated.")

    development_policy = (
        PRE_SAFFRON_DEVELOPMENT_POLICY
        if initial.party_count == len(PRE_SAFFRON_BALANCED_ROSTER.slots)
        else MANSION_DEVELOPMENT_POLICY
    )
    team_policy = (
        PRE_SAFFRON_TEAM_POLICY
        if development_policy is PRE_SAFFRON_DEVELOPMENT_POLICY
        else MANSION_TEAM_POLICY
    )
    development = plan_team_development(
        PokemonRedPartyReader(emulator).read(), development_policy
    )
    team_battles = 0
    team_healing_trips = 0
    if development.directive is TeamTrainingDirective.EVOLVE_MEMBER:
        _, evolution_battles, evolution_heals = run_red_team_balancing(
            actions,
            reader,
            emulator,
            policy=team_policy,
            venues=(
                ROUTE_11_TRAINING_VENUE,
                DIGLETTS_CAVE_TRAINING_VENUE,
                MANSION_TRAINING_VENUE,
            ),
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=_flee,
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            decision_sink=training_decision_sink,
            decision_authority=training_decision_authority,
            candidate_decision_sink=training_candidate_decision_sink,
            candidate_decision_authority=training_candidate_decision_authority,
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            report_label="Mansion team training",
            checkpoint_count=BLAINE_AFTER_MANSION_CHECKPOINT_COUNT,
        )
        team_battles += evolution_battles
        team_healing_trips += evolution_heals

    # The evolution pass breaks as soon as the final species appears, without
    # checking readiness.  Until now it was the only call, so the balancing pass
    # below -- the one that enforces MANSION_TEAM_POLICY's level floor and
    # spread -- was never reached, and the party finished the game at
    # [68, 20, 26, 30, 25, 30].  Run it.
    _, balance_battles, balance_heals = run_red_team_balancing(
        actions,
        reader,
        emulator,
        policy=team_policy,
        venues=(
            ROUTE_11_TRAINING_VENUE,
            DIGLETTS_CAVE_TRAINING_VENUE,
            MANSION_TRAINING_VENUE,
        ),
        intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
        flee_timing=MANSION_TRAINING_FLEE_TIMING,
        hideout_timing=DEFAULT_HIDEOUT_TIMING,
        flee_func=_flee,
        volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
        escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
        max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
        cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
        decision_sink=training_decision_sink,
        decision_authority=training_decision_authority,
        candidate_decision_sink=training_candidate_decision_sink,
        candidate_decision_authority=training_candidate_decision_authority,
        progress_sink=(
            (
                lambda message: progress(
                    BlaineProgress(
                        "mansion_team_training_progress",
                        message,
                        len(records),
                        BLAINE_AFTER_MANSION_CHECKPOINT_COUNT,
                        emulator.frame_count,
                    )
                )
            )
            if progress is not None
            else None
        ),
        completed_checkpoint_count=len(records),
        report_label="Mansion team training",
        checkpoint_count=BLAINE_AFTER_MANSION_CHECKPOINT_COUNT,
    )
    team_battles += balance_battles
    team_healing_trips += balance_heals

    training = _run_mansion_training(actions, reader, emulator)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "mansion_training_complete",
        "Trained safely in Pokémon Mansion",
    )

    team_readiness = _qualify_mansion_team_development(
        reader,
        emulator,
        policy=development_policy,
    )
    if not team_readiness.passed:
        raise BlaineChapterError("Team development failed the parity contract.")

    _move(actions, reader, ("down",) * 5 + GYM_ENTRY_ROUTE, "Cinnabar Gym")
    _require(reader.read(), MapId.CINNABAR_GYM, (16, 17), "Cinnabar Gym entrance")
    gym_before = _events(emulator, GYM_TRAINER_EVENTS)
    if gym_before != (False,) * 7:
        raise BlaineChapterError("A Cinnabar Gym trainer was already defeated.")
    quiz_trainer_battles: list[CinnabarGymTrainerReceipt] = []
    for index, (route, answer, text_pulses) in enumerate(
        zip(GYM_QUIZ_ROUTES, QUIZ_ANSWERS, QUIZ_TEXT_PULSES, strict=True),
        1,
    ):
        _move(actions, reader, route, f"Cinnabar quiz {index}")
        receipt = _answer_quiz(actions, reader, emulator, index, answer, text_pulses)
        if receipt is not None:
            quiz_trainer_battles.append(receipt)
        expected_trainers = tuple(
            trainer_index in {item.quiz_index for item in quiz_trainer_battles}
            for trainer_index in range(7)
        )
        observed_trainers = _events(emulator, GYM_TRAINER_EVENTS)
        if observed_trainers != expected_trainers:
            raise BlaineChapterError(
                f"Quiz {index} trainer state changed: expected {expected_trainers!r}, "
                f"got {observed_trainers!r}."
            )
    gates_after = _events(emulator, GYM_GATE_EVENTS)
    gym_after_quizzes = _events(emulator, GYM_TRAINER_EVENTS)
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

    def record_turn(raw: RawGameState, slot: int) -> None:
        turns.append(
            BlaineTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                slot,
            )
        )

    run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _raw: 4,
        expected_map=MapId.CINNABAR_GYM,
        intent=BattleIntent(
            "defeat_blaine",
            battle_plan_id=RedBattlePlanId.BLAINE_LEADER,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(SURF_MOVE_ID),
        ),
        required_move_id=SURF_MOVE_ID,
        label="Blaine",
        move_decision_sink=record_turn,
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
    capacity_sale_item = ItemId.GREAT_BALL if capacity_great_ball_required else ItemId.TM34_BIDE
    _sell_current_bag_item(actions, reader, emulator, capacity_sale_item)
    if _bag(emulator).get(capacity_sale_item, 0):
        raise BlaineChapterError(f"{capacity_sale_item.name} capacity sale did not settle.")
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

    report = BlaineAfterMansionReport(
        records=tuple(records),
        final_raw=final,
        training=training,
        team_readiness=team_readiness,
        team_training_battles=team_battles,
        team_training_healing_trips=team_healing_trips,
        quiz_answers=QUIZ_ANSWERS,
        gym_gate_events_after_quizzes=gates_after,
        gym_trainer_events_before=gym_before,
        gym_trainer_events_after_quizzes=gym_after_quizzes,
        quiz_trainer_battles=tuple(quiz_trainer_battles),
        gym_trainer_events_after=_events(emulator, GYM_TRAINER_EVENTS),
        identity=identity,
        turns=tuple(turns),
        got_tm38=_event(emulator, EventFlag.GOT_TM38),
        beat_blaine=_event(emulator, EventFlag.BEAT_BLAINE),
        volcano_badge=bool(final.badge_bits & Badge.VOLCANO),
        volcano_badge_mirror=bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.VOLCANO),
        tm38_quantity=_bag(emulator).get(ItemId.TM38_FIRE_BLAST, 0),
        secret_key_quantity=_bag(emulator).get(ItemId.SECRET_KEY, 0),
        tm14_quantity=_bag(emulator).get(ItemId.TM14_BLIZZARD, 0),
        x_accuracy_retained=_bag(emulator).get(ItemId.X_ACCURACY, 0) == 1,
        capacity_item_sold=capacity_items[0],
        initial_money=initial_money,
        money_remaining=_money(emulator),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise BlaineChapterError(f"Post-Mansion Blaine evidence failed: {report.public_dict()!r}.")
    return report



def _sell_current_bag_item(actions, reader, emulator, item: ItemId) -> None:
    before = _bag(emulator)
    if before.get(item, 0) != 1:
        raise BlaineChapterError(f"Expected one {item.name} to sell.")
    _sell_bag_item_stack(actions, reader, emulator, item, 1)


def _sell_bag_item_stack(actions, reader, emulator, item: ItemId, quantity: int) -> None:
    """Sell an exact complete stack while preserving the live shop boundary."""

    before = _bag(emulator).get(item, 0)
    if type(quantity) is not int or quantity <= 0 or before != quantity:
        raise BlaineChapterError(
            f"Expected exactly {quantity} {item.name} to sell; observed {before}."
        )
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
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(quantity + 2):
        if (
            emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM) == item
            and emulator.read_u8(RamAddress.SHOP_QUANTITY) == quantity
        ):
            break
        _pulse(actions, MacroActionKind.MOVE, "up", 120)
    else:
        raise BlaineChapterError(f"Cinnabar sale quantity selector missed {quantity} {item.name}.")
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
    """Prefer the Antidote when a capacity-bound plan has that obsolete cure."""

    if not BLAINE_INPUT_BAG_SLOT_BOUNDS[0] <= input_slots <= BLAINE_INPUT_BAG_SLOT_BOUNDS[1]:
        raise BlaineChapterError(f"Unsupported Blaine input capacity: {input_slots} slots.")
    if type(antidote_quantity) is not int or not 0 <= antidote_quantity <= 99:
        raise BlaineChapterError(
            "Unsupported Blaine Antidote capacity: "
            f"slots={input_slots}, quantity={antidote_quantity}."
        )
    return input_slots in {19, 20} and antidote_quantity > 0


def _blaine_capacity_input_slots(
    input_slots: int,
    potion_quantity: int,
    *,
    bide_present: bool,
    force_potion_sale: bool = False,
) -> tuple[int, int]:
    """Remove obsolete Potions when Mansion pickups otherwise exceed capacity."""

    if not BLAINE_INPUT_BAG_SLOT_BOUNDS[0] <= input_slots <= BLAINE_INPUT_BAG_SLOT_BOUNDS[1]:
        raise BlaineChapterError(f"Unsupported Blaine input capacity: {input_slots} slots.")
    if type(potion_quantity) is not int or potion_quantity < 0:
        raise BlaineChapterError("Unsupported Blaine Potion quantity.")
    if type(bide_present) is not bool:
        raise TypeError("bide_present must be a bool")
    if type(force_potion_sale) is not bool:
        raise TypeError("force_potion_sale must be a bool")
    potion_sale_required = (
        input_slots == 20
        or (input_slots == 19 and not bide_present)
        or force_potion_sale
    )
    if potion_sale_required:
        if potion_quantity == 0:
            raise BlaineChapterError("Capacity-bound Blaine input lacks obsolete Potions to sell.")
        if force_potion_sale and (input_slots != 18 or bide_present):
            raise BlaineChapterError("Forced early Potion sale has an unsupported input lineage.")
        return input_slots - 1, potion_quantity
    return input_slots, 0


def _blaine_capacity_plan(
    input_slots: int,
    *,
    bide_present: bool,
) -> tuple[bool, bool, int, int]:
    """Replace an early-sold Bide slot while preserving the delayed TM38 lesson."""

    if type(input_slots) is not int or not BLAINE_INPUT_BAG_SLOT_BOUNDS[0] <= input_slots <= 19:
        raise BlaineChapterError(f"Unsupported Blaine input capacity: {input_slots} slots.")
    if type(bide_present) is not bool:
        raise TypeError("bide_present must be a bool")
    buy_great_ball = not bide_present
    effective_slots = input_slots + int(buy_great_ball)
    if not 16 <= effective_slots <= 20:
        raise BlaineChapterError(
            f"Blaine replacement capacity is unsupported: {effective_slots} effective slots."
        )
    return (
        buy_great_ball,
        effective_slots == 16,
        2 if effective_slots in {16, 17} else 1,
        effective_slots,
    )


def _buy_repel(
    actions,
    reader,
    emulator,
    *,
    quantity: int = 1,
    buy_ultra_ball: bool = False,
    buy_great_ball: bool = False,
) -> None:
    def reopen_buy_list() -> None:
        _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
        _pulse(actions, MacroActionKind.INTERACT)
        _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
        _pulse(actions, MacroActionKind.CONFIRM)

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
        reopen_buy_list()
    if buy_great_ball:
        _buy_mart_item(
            actions,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=1,
            item=ItemId.GREAT_BALL,
            quantity=1,
            target_bag_quantity=1,
        )
        reopen_buy_list()
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
    # Which slot digs, and which submenu row Dig is on, are read from the party.
    # They used to be the constants two and zero, which held only while the
    # party never moved. The first working party swap moved Diglett and this
    # raised "Diglett no longer exposes Dig in field slot zero" on a live run.
    dig_index, dig_row = _field_move_menu_indices(emulator, DIG, "Dig")
    before_pp = emulator.read_u8(member_field_address(dig_index, PP_OFFSET + dig_row))
    _pulse(actions, MacroActionKind.OPEN_MENU, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, dig_index, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, dig_row, DEFAULT_HIDEOUT_TIMING)
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
        or emulator.read_u8(member_field_address(dig_index, PP_OFFSET + dig_row)) != before_pp
    ):
        raise BlaineChapterError("Field Dig changed protected party or inventory state.")
    return reader.read()


MANSION_DIG_RETURN_MAPS = (
    MapId.CINNABAR_ISLAND,
    MapId.CELADON_CITY,
    MapId.SAFFRON_CITY,
    MapId.VERMILION_CITY,
)


def _return_from_mansion_to_cinnabar(actions, reader, emulator) -> None:
    """Return from the Mansion for every authenticated healing anchor.

    Dig returns to the save's current blackout/healing anchor, not to a place
    implied by the objective frontier.  Older captures happened to return to
    Saffron.  Construction lineages can legitimately retain Celadon, Cinnabar,
    or Vermilion instead, so observe the landing and fly only when necessary.
    """

    destination = _field_dig(
        actions,
        reader,
        emulator,
        expected_map=MANSION_DIG_RETURN_MAPS,
    )
    if destination.map_id != MapId.CINNABAR_ISLAND:
        _fly_to_town(
            actions,
            reader,
            emulator,
            MapId.CINNABAR_ISLAND,
            "Mansion Dig return to Cinnabar",
        )
    _require(reader.read(), MapId.CINNABAR_ISLAND, (11, 12), "Cinnabar return")


def _field_fly_to_vermilion_from_saffron(actions, reader, emulator) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(12):
        if reader.read().map_id == MapId.VERMILION_CITY:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise BlaineChapterError("Fly did not return to Vermilion from Saffron.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=12)

#: How many town-map cursor positions to try before giving up.
#:
#: The town map is not a list menu -- it writes to none of the standard menu
#: RAM, so there is no cursor to read and step toward. That was measured, not
#: assumed: five candidate addresses were sampled after every move and all five
#: were frozen at values left behind by the previous submenu. See
#: ``docs/evidence/town-map-cursor-not-observable-2026-08-07.json``.
#:
#: What can be observed is where we land. A wrong fly puts us in another
#: flyable town and costs only in-game time, so trying and checking is cheap,
#: repeatable, and answers with the game's own state instead of our beliefs
#: about the map's layout.
FLY_ATTEMPT_LIMIT = 10


def _field_move_menu_indices(emulator: EmulatorState, move_id: int, name: str) -> tuple[int, int]:
    """Which party slot knows ``move_id``, and which submenu row it occupies.

    Both are read from the party rather than fixed, because training reorders
    it. A hard-coded slot was how field Dig broke the moment the party swap
    started working: it addressed Diglett as the third member with Dig in move
    slot two, and the first successful swap moved both.

    The submenu lists a Pokemon's usable field moves first, in move order, then
    STATS, SWITCH and CANCEL -- measured one row at a time in
    ``docs/evidence/party-submenu-layout-2026-08-07.json``. A field move
    therefore sits at its own index among that member's field moves.
    """

    party = PokemonRedPartyReader(emulator).read()
    for index, member in enumerate(party.members):
        move_ids = [move.move_id for move in member.known_moves]
        if move_id not in move_ids:
            continue
        field_moves = [candidate for candidate in move_ids if candidate in GEN1_FIELD_MOVE_IDS]
        return index, field_moves.index(move_id)
    raise BlaineChapterError(f"No party member knows {name}.")


def _fly_menu_indices(emulator: EmulatorState) -> tuple[int, int]:
    """Which party slot knows Fly, and which submenu row Fly occupies.

    Both are read from the party rather than fixed, because training reorders
    it: a trainee is swapped into slot one whenever the venue changes, so the
    Fly holder does not stay put. A hard-coded slot index would fly with
    whichever Pokemon happened to be second.

    The submenu lists a Pokemon's usable field moves first, in move order, then
    SWITCH, STATS and CANCEL. That layout is measured -- it is what the party
    switch investigation established, and the town-map run corroborated it: the
    submenu reported five entries for a Pokemon knowing Cut and Fly.
    """

    return _field_move_menu_indices(emulator, FLY_MOVE_ID, "Fly, so no town can be reached by air")


def _open_fly_map(actions, reader, emulator) -> None:
    """Open the town map with Fly selected, from the field."""

    party_index, fly_row = _fly_menu_indices(emulator)
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, party_index, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, fly_row, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.WAIT, frames=90)


def _fly_to_town(actions, reader, emulator, destination: MapId, label: str) -> None:
    """Fly to ``destination``, judged by where we land rather than by a cursor.

    Each attempt moves the cursor a different number of steps and confirms; the
    map we end up standing on says whether it worked. Wrong landings are not
    wasted -- every one is recorded, and on exhaustion the table of
    origin, direction, steps and landing is reported, which is the measurement
    somebody needs to make this deterministic later.
    """

    landings: list[tuple[str, str, int, str]] = []
    # No zero-step attempt: the cursor opens on the town we are standing in, so
    # confirming immediately flies us nowhere and costs an attempt.
    attempts = [("up", steps) for steps in range(1, FLY_ATTEMPT_LIMIT // 2 + 1)]
    attempts += [("down", steps) for steps in range(1, FLY_ATTEMPT_LIMIT // 2 + 1)]

    for direction, steps in attempts:
        origin = reader.read().map_id
        if origin == destination:
            return
        _open_fly_map(actions, reader, emulator)
        for _ in range(steps):
            _pulse(actions, MacroActionKind.MOVE, direction, 120)

        # Confirm, then *wait* rather than press again. An earlier version kept
        # confirming until the map changed, which is fine while it works and
        # ruinous when it does not: an attempt that flies nowhere leaves eight
        # unanswered A presses in the field, and the next attempt then found a
        # prompt open with only A and B watched, so the d-pad did nothing and
        # the cursor would not move at all.
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        landed = origin
        for index in range(6):
            _pulse(actions, MacroActionKind.WAIT, frames=90)
            landed = reader.read().map_id
            if landed != origin:
                break
            if index == 0:
                # One further press, in case a prompt is waiting on it.
                _pulse(actions, MacroActionKind.CONFIRM, frames=240)

        landings.append((_map_name(origin), direction, steps, _map_name(landed)))
        if landed == destination:
            return
        if landed == origin:
            # Nothing happened. Put the field back in a known state before the
            # next attempt rather than opening a menu on top of whatever is up.
            _close(actions, reader)

    raise BlaineChapterError(
        f"{label}: could not reach {_map_name(int(destination))} by air in "
        f"{len(attempts)} attempts. (origin, direction, steps, landing) = {landings!r}."
    )


def _map_name(map_id: int | None) -> str:
    if map_id is None:
        return "unknown"
    try:
        return MapId(map_id).name.lower()
    except ValueError:
        return f"map_{map_id:#04x}"


def _field_fly_to_vermilion_from_saffron(actions, reader, emulator) -> None:
    _fly_to_town(actions, reader, emulator, MapId.VERMILION_CITY, "Saffron to Vermilion")


def _field_fly_to_vermilion_from_cinnabar(actions, reader, emulator) -> None:
    _fly_to_town(actions, reader, emulator, MapId.VERMILION_CITY, "Cinnabar to Vermilion")


def _field_fly_to_cinnabar_from_vermilion(actions, reader, emulator) -> None:
    _fly_to_town(actions, reader, emulator, MapId.CINNABAR_ISLAND, "Vermilion to Cinnabar")



def _team_training_move_slot(state: RawGameState) -> int:
    """Pick a safe training move, or request an in-battle escape.

    The lead-only block was short enough never to meet Disable.  Team training
    runs many more encounters, so the fallback slot can be locked out; treating
    a disabled slot as available made the battle runtime reject the choice.
    The overworld retreat gate is not enough by itself: a durable opponent can
    push a trainee below the same safety floor after the battle has begun.  The
    move policy is re-evaluated before every turn, so it also enforces that
    portable health rule and hands control back to the bounded escort-and-flee
    path before selecting another attack.
    """

    _team_training_move_guard(state)
    preferred_slots = _team_training_preferred_slots(state)
    disabled = state.player_disabled_move_slot or 0
    pp = state.battler_pp or ()
    fallback_slots = tuple(
        slot
        for slot in MANSION_TRAINING_POLICY.preferred_move_slots
        if slot != disabled and slot not in preferred_slots
    )
    slots = preferred_slots or fallback_slots
    return choose_training_move_slot(pp, slots)


def _team_training_move_guard(state: RawGameState) -> None:
    """Preserve per-turn retreat and preferred-attack constraints for any policy."""

    hp = state.battler_hp
    max_hp = state.battler_max_hp
    if hp is None or max_hp is None or max_hp <= 0:
        raise _PauseForTeamTrainingRecovery
    if hp / max_hp <= MANSION_TEAM_POLICY.retreat_hp_ratio:
        raise _PauseForTeamTrainingRecovery
    preferred_move_ids = TRAINING_MOVE_IDS.get(state.active_party_species_id or 0, ())
    if preferred_move_ids and not _team_training_preferred_slots(state):
        raise _PauseForTeamTrainingRecovery


def _team_training_preferred_slots(state: RawGameState) -> tuple[int, ...]:
    disabled = state.player_disabled_move_slot or 0
    moves = state.battler_moves or ()
    pp = state.battler_pp or ()
    preferred_move_ids = TRAINING_MOVE_IDS.get(state.active_party_species_id or 0, ())
    return tuple(
        index + 1
        for move_id in preferred_move_ids
        for index, observed in enumerate(moves)
        if (observed == move_id and index + 1 != disabled and index < len(pp) and pp[index] > 0)
    )


def _mansion_training_move_slot(state: RawGameState) -> int:
    """Rank live lead-training attacks while respecting temporary Disable."""

    disabled = state.player_disabled_move_slot or 0 if (state.player_disable_turns or 0) > 0 else 0
    slots = tuple(slot for slot in MANSION_TRAINING_POLICY.preferred_move_slots if slot != disabled)
    try:
        return choose_training_move_slot(state.battler_pp or (), slots)
    except ValueError as error:
        raise _PauseForTeamTrainingRecovery from error


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


def _qualify_mansion_team_development(
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    policy: DevelopedTeamPolicy = MANSION_DEVELOPMENT_POLICY,
) -> DevelopedTeamReport:
    """Require final available forms and the level-60 completion workhorse."""

    party = PokemonRedPartyReader(emulator).read()
    decision = plan_team_development(party, policy)
    report = summarize_team_development(party, policy)
    if decision.directive is not TeamTrainingDirective.STOP or not report.passed:
        raise BlaineChapterError(
            "Mansion team development stopped before readiness: "
            f"{decision.reason}; species={party.species_ids()!r}, "
            f"levels={party.levels!r}."
        )
    if not reader.read_input_readiness().ready:
        raise BlaineChapterError("Mansion team development boundary is not input-ready.")
    return report


def _mansion_heal_and_return(actions, reader, emulator) -> None:
    """Restore the party and return to the Mansion, from wherever this starts.

    The balancing block runs straight after the lead-only block, which ends by
    healing — so this can be entered already standing at the Cinnabar nurse.
    Field Dig cannot be used indoors, so digging unconditionally failed there
    with the player at (3, 3) inside the Center.  Each leg is now guarded by
    where the player actually is rather than by where the Mansion path assumed.
    """

    raw = reader.read()
    if raw.map_id != MapId.CINNABAR_POKECENTER:
        _training_dig_to_cinnabar(actions, reader, emulator)
        _move(actions, reader, ("up",), "team training Center entry")
        _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "team training Center")
        raw = reader.read()
    if (raw.player_x, raw.player_y) != (3, 3):
        _move(actions, reader, ("up",) * 4, "team training nurse")
    _heal(actions, reader, emulator)
    _move(actions, reader, CENTER_TO_MANSION, "team training return")
    _require(reader.read(), MapId.POKEMON_MANSION_1F, (5, 27), "team training Mansion entrance")


def _mansion_walk_to_grass(actions, reader, emulator) -> int:
    raw = reader.read()
    direction = "down" if (raw.player_y or 0) <= 20 else "up"
    _pulse(actions, MacroActionKind.MOVE, direction, 240)
    return 1


def _training_dig_to_cinnabar(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    destination = _field_dig(
        actions,
        reader,
        emulator,
        expected_map=(MapId.CINNABAR_ISLAND, MapId.SAFFRON_CITY, MapId.VERMILION_CITY),
    )
    if destination.map_id == MapId.SAFFRON_CITY:
        _field_fly_to_cinnabar(actions, reader, emulator)
    elif destination.map_id == MapId.VERMILION_CITY:
        _field_fly_to_cinnabar_from_vermilion(actions, reader, emulator)
    _require(reader.read(), MapId.CINNABAR_ISLAND, (11, 12), "training Dig return")


def _training_dig_to_vermilion(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    raw = reader.read()
    if raw.map_id == MapId.CINNABAR_POKECENTER:
        _move(actions, reader, ("down",) * 5, "exit Cinnabar Center")
        raw = reader.read()
    elif raw.map_id == MapId.SAFFRON_POKECENTER:
        _move(actions, reader, ("down",) * 5, "exit Saffron Center")
        raw = reader.read()

    if raw.map_id not in (MapId.CINNABAR_ISLAND, MapId.SAFFRON_CITY, MapId.VERMILION_CITY):
        raw = _field_dig(
            actions,
            reader,
            emulator,
            expected_map=(MapId.CINNABAR_ISLAND, MapId.SAFFRON_CITY, MapId.VERMILION_CITY),
        )
        
    if raw.map_id == MapId.SAFFRON_CITY:
        _field_fly_to_vermilion_from_saffron(actions, reader, emulator)
    elif raw.map_id == MapId.CINNABAR_ISLAND:
        _field_fly_to_vermilion_from_cinnabar(actions, reader, emulator)
        
    _require(reader.read(), MapId.VERMILION_CITY, (11, 4), "training Dig return vermilion")


#: Which way the cave pacing is currently headed, reversed on every wall.
_CAVE_PACING = {"direction": "left"}


def _digletts_cave_walk_to_grass(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> int:
    """Pace the tunnel, turning round at each wall.

    The whole cave is an encounter zone, so any real step will do -- but only a
    real step counts. Walking one fixed direction chosen by x walks into a wall
    and stays there, and a blocked press is not a step, so the encounter check
    never runs. Measured from a captured state: 250 walks produced one
    encounter and no level gain, because after about eight tiles west the
    remaining two hundred presses were all against rock.

    Bouncing is what surge's own Diglett search does for the same cave. The
    direction is kept between calls and reversed whenever the player did not
    actually move.
    """

    before = reader.read()
    if before.player_x is None:
        return 0
    direction = _CAVE_PACING["direction"]
    _pulse(actions, MacroActionKind.MOVE, direction, 120)
    after = reader.read()
    if after.battle_state:
        return 1
    if (after.player_x, after.player_y) == (before.player_x, before.player_y):
        _CAVE_PACING["direction"] = "right" if direction == "left" else "left"
        return 0
    return 1

def _route_11_heal_and_return(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    raw = reader.read()
    if raw.map_id != MapId.VERMILION_POKECENTER:
        if raw.map_id == MapId.ROUTE_11:
            flee_run = _RunState([])
            for _ in range(64):
                raw = reader.read()
                if raw.map_id == MapId.VERMILION_CITY:
                    break
                if raw.battle_state:
                    _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                    continue
                _pulse(actions, MacroActionKind.MOVE, "left", 120)
            else:
                raise BlaineChapterError("Route 11 training could not return to Vermilion.")
            raw = reader.read()
            if raw.player_x is None or raw.player_y != 14 or raw.player_x < 23:
                raise BlaineChapterError(
                    "Route 11 training reached an invalid Vermilion boundary: "
                    f"{(raw.player_x, raw.player_y)!r}."
                )
            _move(
                actions,
                reader,
                ("left",) * (raw.player_x - 23),
                "team training Vermilion east-boundary normalization",
            )
            _move(
                actions,
                reader,
                VERMILION_ROUTE_11_TO_CENTER_EXTERIOR,
                "team training Vermilion Center return",
            )
            _require(reader.read(), MapId.VERMILION_CITY, (11, 4), "training Center exterior")
        else:
            _training_dig_to_vermilion(actions, reader, emulator)
        _move(actions, reader, ("up",), "team training Vermilion Center entry")
        _require(reader.read(), MapId.VERMILION_POKECENTER, (3, 7), "team training Center")
        raw = reader.read()
    if (raw.player_x, raw.player_y) != (3, 3):
        _move(actions, reader, ("up",) * 4, "team training Vermilion nurse")
    _heal(actions, reader, emulator)
    _move(actions, reader, VERMILION_NURSE_TO_EXIT, "team training Vermilion Center exit")
    after_exit = reader.read()
    _move(actions, reader, VERMILION_CENTER_TO_ROUTE_11, "team training Route 11 return")

    # Walk east until Route 11 loads. The failure carries where we were at each
    # stage, because "Failed to enter Route 11" on its own cannot distinguish
    # leaving the Center at the wrong tile from walking the right path from the
    # wrong start -- and those want different fixes.
    # Twenty-four steps, matching surge._move_until_map, which is proven on this
    # exact stretch. A copy here used twelve, and a measured run showed why that
    # is not a detail: the return path lands at x=23, twelve steps east reached
    # x=35, and Vermilion had not ended. The walk was working and simply gave up
    # partway.
    #
    # The battle guard is the proven version's too. The east end of this walk
    # crosses into Route 11's grass, and an encounter mid-walk would leave the
    # step count meaning nothing.
    trail: list[tuple[str, int | None]] = []
    for _ in range(24):
        raw = reader.read()
        trail.append((_map_name(raw.map_id), raw.player_x))
        if raw.map_id == MapId.ROUTE_11:
            break
        _pulse(actions, MacroActionKind.MOVE, "right", 120)
        if reader.read().battle_state:
            raise BlaineChapterError(
                "Walking east to Route 11 was interrupted by a battle at "
                f"{_map_name(reader.read().map_id)}."
            )
    else:
        raw = reader.read()
        raise BlaineChapterError(
            f"Failed to enter Route 11. Left the Center at "
            f"{_map_name(after_exit.map_id)} {(after_exit.player_x, after_exit.player_y)!r}; "
            f"after the return path at {_map_name(raw.map_id)} "
            f"{(raw.player_x, raw.player_y)!r}; "
            f"(map, x) while walking east: {trail!r}."
        )
    _pulse(actions, MacroActionKind.CONFIRM, frames=12) # wait out transition


def _digletts_cave_heal_and_return(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _route_11_heal_and_return(actions, reader, emulator)
    
    _move(actions, reader, ("right",) * 4, "Post-Spearow Diglett Cave approach")
    raw = reader.read()
    if raw.player_x is None or raw.player_x < 4:
        raise BlaineChapterError("Route 11 Diglett Cave approach failed")
        
    def _directions(s: str) -> tuple[str, ...]:
        return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in s)
        
    _move(
        actions,
        reader,
        _directions("L" * (raw.player_x - 4) + "U"),
        "Diglett Cave Route 11 gate",
    )
    _pulse(actions, MacroActionKind.CONFIRM, frames=60) # Wait transition
    
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_11 or raw.player_x is None or raw.player_y is None:
        raise BlaineChapterError("Route 11 Diglett Cave gate did not load.")
    to_cave = "U" * max(raw.player_y - 4, 0)
    to_cave += ("R" if raw.player_x < 4 else "L") * abs(raw.player_x - 4)
    _move(actions, reader, _directions(to_cave), "Diglett Cave entry")
    _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    
    entry = reader.read()
    if entry.map_id != MapId.DIGLETTS_CAVE or entry.player_x is None or entry.player_y is None:
        raise BlaineChapterError("Diglett Cave interior did not load")


def _route_11_walk_to_grass(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> int:
    """Reach Route 11's measured grass, then alternate across two real tiles."""

    del emulator
    before = reader.read()
    if before.map_id != MapId.ROUTE_11 or before.player_x is None:
        return 0
    direction = "right" if before.player_x <= 12 else "left"
    _pulse(actions, MacroActionKind.MOVE, direction, 120)
    after = reader.read()
    if after.battle_state:
        return 1
    return int((after.player_x, after.player_y) != (before.player_x, before.player_y))


def _route_11_training_venue() -> TrainingVenue:
    """Route 11's measured band, used before a trainee is Cave-safe."""

    band = next(area for area in MEASURED_TRAINING_VENUES if area.area_id == "route_11")
    return TrainingVenue(
        band=band,
        map_id=int(MapId.ROUTE_11),
        walk_to_grass=_route_11_walk_to_grass,
        heal_and_return=_route_11_heal_and_return,
        is_in_center=lambda raw: raw.map_id == MapId.VERMILION_POKECENTER,
        move_slot=_team_training_move_slot,
        move_guard=_team_training_move_guard,
        battle_timing=BattleRuntimeTiming(max_sleep_reapplications=4),
    )


ROUTE_11_TRAINING_VENUE = _route_11_training_venue()

def _digletts_cave_training_venue() -> TrainingVenue:
    """Diglett's Cave, bound to the band it was measured to field.

    The band is taken from ``MEASURED_TRAINING_VENUES`` rather than restated
    here. A hand-copied copy held the right numbers but sat outside
    ``test_measured_venues_match_the_evidence``, so a re-harvest would have
    updated the guarded list and left this one silently behind -- which is
    exactly how a Mansion band of "30-32" outlived the 155 samples saying 28-39.
    """

    band = next(
        area for area in MEASURED_TRAINING_VENUES if area.area_id == "digletts_cave"
    )
    return TrainingVenue(
        band=band,
        map_id=int(MapId.DIGLETTS_CAVE),
        walk_to_grass=_digletts_cave_walk_to_grass,
        heal_and_return=_digletts_cave_heal_and_return,
        is_in_center=lambda r: r.map_id == MapId.VERMILION_POKECENTER,
        move_slot=_team_training_move_slot,
        move_guard=_team_training_move_guard,
    )

DIGLETTS_CAVE_TRAINING_VENUE = _digletts_cave_training_venue()

def _mansion_training_venue() -> TrainingVenue:
    """The Mansion, bound to the band it was actually measured to field.

    Route 11 and Diglett's Cave now cover the lower measured bands; the Mansion
    remains the late-game venue once a trainee can safely engage it.
    """

    band = next(
        area for area in MEASURED_TRAINING_VENUES if area.area_id == "pokemon_mansion_1f"
    )
    return TrainingVenue(
        band=band,
        map_id=int(MapId.POKEMON_MANSION_1F),
        walk_to_grass=_mansion_walk_to_grass,
        heal_and_return=_mansion_heal_and_return,
        is_in_center=lambda raw: raw.map_id == MapId.CINNABAR_POKECENTER,
        move_slot=_team_training_move_slot,
        move_guard=_team_training_move_guard,
    )


MANSION_TRAINING_VENUE = _mansion_training_venue()


def _mansion_training_fainted_pivot_target(
    raw: RawGameState,
    party_hp: tuple[int, ...],
) -> int | None:
    """Choose the healthiest reserve after the lead faints in a wild lesson."""

    if raw.battle_state != 1 or (raw.battler_hp or 0) > 0:
        return None
    living_reserves = tuple(
        (hp, index) for index, hp in enumerate(party_hp[1:], start=1) if hp > 0
    )
    return max(living_reserves, default=(0, -1))[1] if living_reserves else None


def _settle_mansion_training_forced_switch(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    target: int,
) -> None:
    """Give the six-member forced-party transition three observed settle windows."""

    last_error: ProtectedRecoveryError | None = None
    for _ in range(3):
        try:
            switch_active_battler(
                actions,
                reader,
                emulator,
                target,
                expected_battle_state=1,
                label="Mansion training fainted-member escape",
            )
        except ProtectedRecoveryError as error:
            last_error = error
            continue
        return
    raise BlaineChapterError(
        "Mansion training could not settle its forced switch after three windows."
    ) from last_error


def _run_mansion_training(
    actions: CountingExecutor,
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
            try:
                run_adaptive_wild_battle(
                    reader,
                    actions,
                    _mansion_training_move_slot,
                    expected_map=MapId.POKEMON_MANSION_1F,
                    intent=MANSION_LEAD_TRAINING_INTENT,
                    label="Pokémon Mansion training encounter",
                    unknown_cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                    transient_zero_pp_main_is_dialogue=True,
                )
            except BattleRuntimeError as error:
                if "active battler fainted" in str(error):
                    target = _mansion_training_fainted_pivot_target(
                        reader.read(),
                        _party_hp(emulator),
                    )
                    if target is None:
                        raise BlaineChapterError(
                            "Mansion training fainted without a living escape reserve."
                        ) from error
                    _settle_mansion_training_forced_switch(
                        actions,
                        reader,
                        emulator,
                        target,
                    )
                    _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                    battles_fled += 1
                    continue
                if not isinstance(error.__cause__, _PauseForTeamTrainingRecovery):
                    raise
                _flee(actions, reader, emulator, flee_run, MANSION_TRAINING_FLEE_TIMING)
                battles_fled += 1
                continue
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


def _answer_quiz(
    actions,
    reader,
    emulator,
    index: int,
    answer: bool,
    text_pulses: int,
) -> CinnabarGymTrainerReceipt | None:
    target_event = GYM_GATE_EVENTS[index]
    if _event(emulator, target_event):
        raise BlaineChapterError(f"Quiz gate {index} was already open.")
    _face_and_interact(actions, "up")
    for _ in range(text_pulses - 1):
        _pulse(actions, MacroActionKind.CONFIRM)
    if not answer:
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM)
    plan = CINNABAR_GYM_TRAINER_PLANS.get(index)
    if plan is None:
        if answer != QUIZ_CORRECT_ANSWERS[index - 1]:
            raise BlaineChapterError(f"Quiz {index} has an unplanned incorrect answer.")
        _pulse(actions, MacroActionKind.CONFIRM)
        _pulse(actions, MacroActionKind.CONFIRM)
        if not _event(emulator, target_event) or not reader.read_input_readiness().ready:
            raise BlaineChapterError(f"Quiz gate {index} did not open on the qualified answer.")
        return None

    if answer == QUIZ_CORRECT_ANSWERS[index - 1]:
        raise BlaineChapterError(f"Quiz {index} did not select its planned trainer battle.")
    label, expected_identity, expected_party, expected_reward, battle_plan_id = plan
    money_before = _money(emulator)
    _await_trainer_battle(actions, reader, DEFAULT_SILPH_TIMING)
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    if identity != expected_identity:
        raise BlaineChapterError(
            f"Unexpected {label} identity: expected {expected_identity!r}, got {identity!r}."
        )
    turns: list[BlaineTurn] = []

    def record_turn(raw: RawGameState, slot: int) -> None:
        turns.append(
            BlaineTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                slot,
            )
        )

    run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _raw: 4,
        expected_map=MapId.CINNABAR_GYM,
        intent=BattleIntent(
            "build_income_and_experience_buffer",
            battle_plan_id=battle_plan_id,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(SURF_MOVE_ID),
        ),
        required_move_id=SURF_MOVE_ID,
        label=label,
        move_decision_sink=record_turn,
    )
    for _ in range(DEFAULT_SILPH_TIMING.max_script_pulses):
        if _event(emulator, target_event) and reader.read_input_readiness().ready:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_SILPH_TIMING.dialogue_frames)
    else:
        raise BlaineChapterError(f"Quiz gate {index} did not open after {label}.")
    receipt = CinnabarGymTrainerReceipt(
        quiz_index=index,
        identity=identity,
        expected_party=expected_party,
        turns=tuple(turns),
        money_before=money_before,
        money_after=_money(emulator),
        expected_reward=expected_reward,
    )
    if not receipt.passed:
        raise BlaineChapterError(f"{label} evidence failed: {receipt!r}.")
    return receipt


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
