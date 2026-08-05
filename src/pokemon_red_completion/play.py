"""One clean, bounded run from power-on through the Hall of Fame.

The route and semantic gates in this module are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``. It composes every qualified
chapter from clean power-on through verified game completion in one emulator
session. It is a deterministic teacher baseline, not a learned-policy claim.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.agatha import (
    AGATHA_CHECKPOINT_COUNT,
    AgathaChapterError,
    AgathaChapterReport,
    AgathaProgress,
    run_agatha_chapter,
)
from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_neural_model import BattleMoveRanker
from pokemon_red_completion.battle_runtime import (
    bind_battle_decision_observer,
    bind_battle_policy_override,
    bind_battle_schedule_observer,
)
from pokemon_red_completion.battle_schedule import (
    BattleStartScheduleController,
    bind_battle_start_schedule,
)
from pokemon_red_completion.blaine import (
    BLAINE_CHECKPOINT_COUNT,
    BlaineChapterError,
    BlaineChapterReport,
    BlaineProgress,
    run_blaine_chapter,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING, NewGameTiming
from pokemon_red_completion.bruno import (
    BRUNO_CHECKPOINT_COUNT,
    BrunoChapterError,
    BrunoChapterReport,
    BrunoProgress,
    run_bruno_chapter,
)
from pokemon_red_completion.cascade import (
    CASCADE_CHECKPOINT_COUNT,
    CascadeChapterError,
    CascadeChapterReport,
    CascadeProgress,
    run_cascade_chapter,
)
from pokemon_red_completion.celadon import (
    CELADON_CHECKPOINT_COUNT,
    CeladonChapterError,
    CeladonChapterReport,
    CeladonProgress,
    run_celadon_chapter,
)
from pokemon_red_completion.cerulean import (
    CERULEAN_CHECKPOINT_COUNT,
    CeruleanChapterError,
    CeruleanChapterReport,
    CeruleanProgress,
    run_cerulean_chapter,
)
from pokemon_red_completion.champion import (
    CHAMPION_CHECKPOINT_COUNT,
    ChampionChapterError,
    ChampionChapterReport,
    ChampionProgress,
    run_champion_chapter,
)
from pokemon_red_completion.cinnabar import (
    CINNABAR_CHECKPOINT_COUNT,
    CinnabarChapterError,
    CinnabarChapterReport,
    CinnabarProgress,
    run_cinnabar_chapter,
)
from pokemon_red_completion.collection_protocol import BattleStartOffset
from pokemon_red_completion.dojo import (
    DOJO_CHECKPOINT_COUNT,
    DojoChapterError,
    DojoChapterReport,
    DojoProgress,
    run_dojo_chapter,
)
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.erika import (
    ERIKA_CHECKPOINT_COUNT,
    ErikaChapterError,
    ErikaChapterReport,
    ErikaProgress,
    run_erika_chapter,
)
from pokemon_red_completion.executor import ExecutedAction, FrameSafeExecutor
from pokemon_red_completion.fuchsia import (
    FUCHSIA_CHECKPOINT_COUNT,
    FuchsiaChapterError,
    FuchsiaChapterReport,
    FuchsiaProgress,
    run_fuchsia_chapter,
)
from pokemon_red_completion.giovanni import (
    GIOVANNI_CHECKPOINT_COUNT,
    GiovanniChapterError,
    GiovanniChapterReport,
    GiovanniProgress,
    run_giovanni_chapter,
)
from pokemon_red_completion.hideout import (
    HIDEOUT_CHECKPOINT_COUNT,
    HideoutChapterError,
    HideoutChapterReport,
    HideoutProgress,
    run_hideout_chapter,
)
from pokemon_red_completion.koga import (
    KOGA_CHECKPOINT_COUNT,
    KogaChapterError,
    KogaChapterReport,
    KogaProgress,
    run_koga_chapter,
)
from pokemon_red_completion.lance import (
    LANCE_CHECKPOINT_COUNT,
    LanceChapterError,
    LanceChapterReport,
    LanceProgress,
    run_lance_chapter,
)
from pokemon_red_completion.lavender import (
    LAVENDER_CHECKPOINT_COUNT,
    LavenderChapterError,
    LavenderChapterReport,
    LavenderProgress,
    run_lavender_chapter,
)
from pokemon_red_completion.learned_battle_policy import ModelAssistedBattlePolicy
from pokemon_red_completion.lorelei import (
    LORELEI_CHECKPOINT_COUNT,
    LoreleiChapterError,
    LoreleiChapterReport,
    LoreleiProgress,
    run_lorelei_chapter,
)
from pokemon_red_completion.observation import (
    MapId,
    OaksErrandPhase,
    OaksErrandState,
    PokemonRedStateReader,
    RawGameState,
    RedPokedexState,
    game_mode,
    location_label,
    semantic_facts,
)
from pokemon_red_completion.opening import (
    DEFAULT_OPENING_TIMING,
    OPENING_CHECKPOINT_COUNT,
    OpeningChapterReport,
    OpeningProgress,
    OpeningTiming,
    run_opening_chapter,
)
from pokemon_red_completion.pewter import (
    PEWTER_CHECKPOINT_COUNT,
    PewterChapterError,
    PewterChapterReport,
    PewterProgress,
    run_pewter_chapter,
)
from pokemon_red_completion.red_collection import (
    RedCollectionProgress,
    summarize_red_collection,
    summarize_red_pokedex,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_trajectory import (
    PokemonRedBattleDecisionObserver,
    PokemonRedBattleScheduleObserver,
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import RomFingerprint
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.sabrina import (
    SABRINA_CHECKPOINT_COUNT,
    SabrinaChapterError,
    SabrinaChapterReport,
    SabrinaProgress,
    run_sabrina_chapter,
)
from pokemon_red_completion.safari import (
    SAFARI_CHECKPOINT_COUNT,
    SafariChapterError,
    SafariChapterReport,
    SafariProgress,
    run_safari_chapter,
)
from pokemon_red_completion.saffron import (
    SAFFRON_CHECKPOINT_COUNT,
    SaffronChapterError,
    SaffronChapterReport,
    SaffronProgress,
    run_saffron_chapter,
)
from pokemon_red_completion.silph import (
    SILPH_CHECKPOINT_COUNT,
    SilphChapterError,
    SilphChapterReport,
    SilphProgress,
    run_silph_chapter,
)
from pokemon_red_completion.ss_anne import (
    SS_ANNE_CHECKPOINT_COUNT,
    SSAnneChapterError,
    SSAnneChapterReport,
    SSAnneProgress,
    run_ss_anne_chapter,
)
from pokemon_red_completion.strength import (
    STRENGTH_CHECKPOINT_COUNT,
    StrengthChapterError,
    StrengthChapterReport,
    StrengthProgress,
    run_strength_chapter,
)
from pokemon_red_completion.surge import (
    SURGE_CHECKPOINT_COUNT,
    SurgeChapterError,
    SurgeChapterReport,
    SurgeProgress,
    run_surge_chapter,
)
from pokemon_red_completion.tower import (
    TOWER_CHECKPOINT_COUNT,
    TowerChapterError,
    TowerChapterReport,
    TowerProgress,
    run_tower_chapter,
)
from pokemon_red_completion.trajectory import (
    RecordingExecutor,
    SparseEvent,
    TrajectorySink,
)
from pokemon_red_completion.vermilion import (
    VERMILION_CHECKPOINT_COUNT,
    VermilionChapterError,
    VermilionChapterReport,
    VermilionProgress,
    run_vermilion_chapter,
)
from pokemon_red_completion.victory_road import (
    VICTORY_ROAD_CHECKPOINT_COUNT,
    VictoryRoadChapterError,
    VictoryRoadChapterReport,
    VictoryRoadProgress,
    run_victory_road_chapter,
)

POKEDEX_CHECKPOINT_COUNT = 11
QUALIFIED_PLAY_CHECKPOINT_COUNT = (
    POKEDEX_CHECKPOINT_COUNT
    + PEWTER_CHECKPOINT_COUNT
    + CERULEAN_CHECKPOINT_COUNT
    + CASCADE_CHECKPOINT_COUNT
    + VERMILION_CHECKPOINT_COUNT
    + SS_ANNE_CHECKPOINT_COUNT
    + SURGE_CHECKPOINT_COUNT
    + LAVENDER_CHECKPOINT_COUNT
    + CELADON_CHECKPOINT_COUNT
    + HIDEOUT_CHECKPOINT_COUNT
    + TOWER_CHECKPOINT_COUNT
    + FUCHSIA_CHECKPOINT_COUNT
    + SAFARI_CHECKPOINT_COUNT
    + KOGA_CHECKPOINT_COUNT
    + STRENGTH_CHECKPOINT_COUNT
    + ERIKA_CHECKPOINT_COUNT
    + SAFFRON_CHECKPOINT_COUNT
    + SILPH_CHECKPOINT_COUNT
    + DOJO_CHECKPOINT_COUNT
    + SABRINA_CHECKPOINT_COUNT
    + CINNABAR_CHECKPOINT_COUNT
    + BLAINE_CHECKPOINT_COUNT
    + GIOVANNI_CHECKPOINT_COUNT
    + VICTORY_ROAD_CHECKPOINT_COUNT
    + LORELEI_CHECKPOINT_COUNT
    + BRUNO_CHECKPOINT_COUNT
    + AGATHA_CHECKPOINT_COUNT
    + LANCE_CHECKPOINT_COUNT
    + CHAMPION_CHECKPOINT_COUNT
)
QUALIFIED_THROUGH_OBJECTIVE = "enter_hall_of_fame"

LAB_RIVAL_TRIGGER_DIRECTIONS = ("down", "left", "left", "left", "down")
LAB_EXIT_DIRECTIONS = ("down",) * 6
PALLET_TO_ROUTE_1_DIRECTIONS = (
    *(("left",) * 3),
    *(("up",) * 10),
    "right",
    *(("up",) * 3),
)
ROUTE_1_TO_VIRIDIAN_DIRECTIONS = (
    *(("up",) * 7),
    *(("left",) * 2),
    *(("up",) * 4),
    *(("right",) * 4),
    *(("up",) * 4),
    *(("left",) * 3),
    *(("up",) * 6),
    *(("right",) * 5),
    *(("up",) * 12),
    *(("left",) * 3),
    *(("up",) * 3),
)
VIRIDIAN_TO_MART_DIRECTIONS = (
    *(("up",) * 5),
    "left",
    *(("up",) * 2),
    "left",
    *(("up",) * 8),
    *(("right",) * 10),
    "up",
)
MART_EXIT_DIRECTIONS = ("right", "down", "down", "down")
VIRIDIAN_TO_ROUTE_1_DIRECTIONS = (
    *(("left",) * 10),
    *(("down",) * 8),
    "right",
    *(("down",) * 2),
    "right",
    *(("down",) * 6),
)
ROUTE_1_TO_PALLET_DIRECTIONS = (
    *(("down",) * 2),
    *(("right",) * 3),
    *(("down",) * 12),
    *(("left",) * 5),
    *(("down",) * 6),
    *(("right",) * 3),
    *(("down",) * 4),
    *(("left",) * 4),
    *(("down",) * 4),
    *(("right",) * 2),
    *(("down",) * 8),
)
PALLET_TO_LAB_DIRECTIONS = (
    *(("down",) * 2),
    "left",
    *(("down",) * 10),
    *(("right",) * 3),
    "up",
)
LAB_TO_OAK_DIRECTIONS = ("left", *(("up",) * 6), "right", "up", "up")


class QualifiedPlayError(RuntimeError):
    """Raised when the clean run misses a bounded route or semantic gate."""


@dataclass(frozen=True, slots=True)
class QualifiedPlayTiming:
    transition_wait_frames: int = 120
    rival_trigger_wait_frames: int = 360
    battle_wait_frames: int = 180
    dialogue_wait_frames: int = 240
    route_1_north_seed_wait_frames: int = 192
    mart_prompt_wait_frames: int = 240
    route_1_south_seed_wait_frames: int = 48
    max_rival_pulses: int = 56
    max_parcel_pulses: int = 5
    max_pokedex_pulses: int = 42

    def __post_init__(self) -> None:
        for name, value in (
            ("transition_wait_frames", self.transition_wait_frames),
            ("rival_trigger_wait_frames", self.rival_trigger_wait_frames),
            ("battle_wait_frames", self.battle_wait_frames),
            ("dialogue_wait_frames", self.dialogue_wait_frames),
            ("route_1_north_seed_wait_frames", self.route_1_north_seed_wait_frames),
            ("mart_prompt_wait_frames", self.mart_prompt_wait_frames),
            ("route_1_south_seed_wait_frames", self.route_1_south_seed_wait_frames),
            ("max_rival_pulses", self.max_rival_pulses),
            ("max_parcel_pulses", self.max_parcel_pulses),
            ("max_pokedex_pulses", self.max_pokedex_pulses),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_QUALIFIED_PLAY_TIMING = QualifiedPlayTiming()


@dataclass(frozen=True, slots=True)
class QualifiedPlayProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[QualifiedPlayProgress], None]


@dataclass(frozen=True, slots=True)
class QualifiedPlayReport:
    rom: RomFingerprint
    pyboy_version: str
    emulator_window: str
    emulator_speed: int
    opening: OpeningChapterReport
    rival_defeated: RawGameState
    viridian_reached: RawGameState
    parcel_received: RawGameState
    pallet_returned: RawGameState
    pokedex_received: RawGameState
    pewter: PewterChapterReport
    cerulean: CeruleanChapterReport
    cascade: CascadeChapterReport
    vermilion: VermilionChapterReport
    ss_anne: SSAnneChapterReport
    surge: SurgeChapterReport
    lavender: LavenderChapterReport
    celadon: CeladonChapterReport
    hideout: HideoutChapterReport
    tower: TowerChapterReport
    fuchsia: FuchsiaChapterReport
    safari: SafariChapterReport
    koga: KogaChapterReport
    strength: StrengthChapterReport
    erika: ErikaChapterReport
    saffron: SaffronChapterReport
    silph: SilphChapterReport
    dojo: DojoChapterReport
    sabrina: SabrinaChapterReport
    cinnabar: CinnabarChapterReport
    blaine: BlaineChapterReport
    giovanni: GiovanniChapterReport
    victory_road: VictoryRoadChapterReport
    lorelei: LoreleiChapterReport
    bruno: BrunoChapterReport
    agatha: AgathaChapterReport
    lance: LanceChapterReport
    champion: ChampionChapterReport
    rival_evidence: OaksErrandState
    parcel_evidence: OaksErrandState
    pokedex_evidence: OaksErrandState
    saw_trainer_battle: bool
    facts: frozenset[str]
    verified_objectives: tuple[str, ...]
    next_objective: str | None
    frames_executed: int
    actions_executed: int
    controller_released: bool
    pokedex_state: RedPokedexState | None = None
    collection_progress: RedCollectionProgress | None = None
    battle_policy_report: dict[str, object] | None = None

    @property
    def passed(self) -> bool:
        return (
            self.opening.passed
            and is_rival_victory_verified(
                self.rival_evidence,
                saw_trainer_battle=self.saw_trainer_battle,
            )
            and is_parcel_verified(self.parcel_evidence)
            and is_pokedex_verified(self.pokedex_evidence)
            and self.pewter.passed
            and self.cerulean.passed
            and self.cascade.passed
            and self.vermilion.passed
            and self.ss_anne.passed
            and self.surge.passed
            and self.lavender.passed
            and self.celadon.passed
            and self.hideout.passed
            and self.tower.passed
            and self.fuchsia.passed
            and self.safari.passed
            and self.koga.passed
            and self.strength.passed
            and self.erika.passed
            and self.saffron.passed
            and self.silph.passed
            and self.dojo.passed
            and self.sabrina.passed
            and self.cinnabar.passed
            and self.blaine.passed
            and self.giovanni.passed
            and self.victory_road.passed
            and self.lorelei.passed
            and self.bruno.passed
            and self.agatha.passed
            and self.lance.passed
            and self.champion.passed
            and QUALIFIED_THROUGH_OBJECTIVE in self.verified_objectives
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        checkpoints = (
            (
                "bedroom_ready",
                "Bedroom input ready",
                self.opening.bedroom,
            ),
            (
                "downstairs",
                "Reached Red's house first floor",
                self.opening.downstairs,
            ),
            ("outside", "Exited into Pallet Town", self.opening.outside),
            ("oak_triggered", "Triggered Professor Oak", self.opening.oak_triggered),
            (
                "selection_ready",
                "Reached the starter selection gate",
                self.opening.selection_ready,
            ),
            (
                "starter_obtained",
                "Selected and verified Squirtle",
                self.opening.starter,
            ),
            ("rival_defeated", "Defeated the lab rival", self.rival_defeated),
            ("viridian_reached", "Reached Viridian City", self.viridian_reached),
            ("parcel_received", "Received Oak's Parcel", self.parcel_received),
            ("pallet_returned", "Returned safely to Pallet Town", self.pallet_returned),
            (
                "pokedex_received",
                "Delivered the parcel and received the Pokédex",
                self.pokedex_received,
            ),
            *self.pewter.checkpoints(),
            *self.cerulean.checkpoints(),
            *self.cascade.checkpoints(),
            *self.vermilion.checkpoints(),
            *self.ss_anne.checkpoints(),
            *self.surge.checkpoints(),
            *self.lavender.checkpoints(),
            *self.celadon.checkpoints(),
            *self.hideout.checkpoints(),
            *self.tower.checkpoints(),
            *self.fuchsia.checkpoints(),
            *self.safari.checkpoints(),
            *self.koga.checkpoints(),
            *self.strength.checkpoints(),
            *self.erika.checkpoints(),
            *self.saffron.checkpoints(),
            *self.silph.checkpoints(),
            *self.dojo.checkpoints(),
            *self.sabrina.checkpoints(),
            *self.cinnabar.checkpoints(),
            *self.blaine.checkpoints(),
            *self.giovanni.checkpoints(),
            *self.victory_road.checkpoints(),
            *self.lorelei.checkpoints(),
            *self.bruno.checkpoints(),
            *self.agatha.checkpoints(),
            *self.lance.checkpoints(),
            *self.champion.checkpoints(),
        )
        pewter = self.pewter.public_dict()
        pokedex = {
            "received_verified": is_pokedex_verified(self.pokedex_evidence),
            "controls_ready": self.pokedex_evidence.controls_ready,
        }
        if self.collection_progress is not None:
            pokedex["collection_progress"] = self.collection_progress.public_dict()
        elif self.pokedex_state is not None:
            pokedex["collection_progress"] = summarize_red_pokedex(self.pokedex_state).public_dict()
        return {
            "schema": "qualified-play-v26",
            "status": "ok" if self.passed else "failed",
            "qualified_through": QUALIFIED_THROUGH_OBJECTIVE,
            "game_complete": True,
            "safe_stop_reason": "completion_verified",
            "rom": self.rom.public_dict(),
            "emulator": {
                "name": "PyBoy",
                "version": self.pyboy_version,
                "window": self.emulator_window,
                "speed": self.emulator_speed,
                "human_input": False,
                "save_on_exit": False,
            },
            "clean_power_on": self.opening.clean_power_on,
            "checkpoints": [
                {
                    "id": checkpoint_id,
                    "label": label,
                    "status": "verified",
                    "state": _public_state(state),
                }
                for checkpoint_id, label, state in checkpoints
            ],
            "rival": {
                "trainer_battle_observed": self.saw_trainer_battle,
                "victory_verified": is_rival_victory_verified(
                    self.rival_evidence,
                    saw_trainer_battle=self.saw_trainer_battle,
                ),
                "species": "squirtle",
                "species_id": self.rival_evidence.first_party_species,
                "level": self.rival_evidence.first_party_level,
                "hp": self.rival_evidence.first_party_hp,
                "max_hp": self.rival_evidence.first_party_max_hp,
            },
            "parcel": {
                "received_verified": is_parcel_verified(self.parcel_evidence),
                "delivered_verified": self.pokedex_evidence.oak_got_parcel,
                "present_after_delivery": self.pokedex_evidence.parcel_in_bag,
            },
            "pokedex": pokedex,
            "northbound": pewter["route"],
            "brock": pewter["brock"],
            "cerulean_chapter": self.cerulean.public_dict(),
            "cascade_chapter": self.cascade.public_dict(),
            "vermilion_chapter": self.vermilion.public_dict(),
            "ss_anne_chapter": self.ss_anne.public_dict(),
            "surge_chapter": self.surge.public_dict(),
            "lavender_chapter": self.lavender.public_dict(),
            "celadon_chapter": self.celadon.public_dict(),
            "hideout_chapter": self.hideout.public_dict(),
            "tower_chapter": self.tower.public_dict(),
            "fuchsia_chapter": self.fuchsia.public_dict(),
            "safari_chapter": self.safari.public_dict(),
            "koga_chapter": self.koga.public_dict(),
            "strength_chapter": self.strength.public_dict(),
            "erika_chapter": self.erika.public_dict(),
            "saffron_chapter": self.saffron.public_dict(),
            "silph_chapter": self.silph.public_dict(),
            "dojo_chapter": self.dojo.public_dict(),
            "sabrina_chapter": self.sabrina.public_dict(),
            "cinnabar_chapter": self.cinnabar.public_dict(),
            "blaine_chapter": self.blaine.public_dict(),
            "giovanni_chapter": self.giovanni.public_dict(),
            "victory_road_chapter": self.victory_road.public_dict(),
            "lorelei_chapter": self.lorelei.public_dict(),
            "bruno_chapter": self.bruno.public_dict(),
            "agatha_chapter": self.agatha.public_dict(),
            "lance_chapter": self.lance.public_dict(),
            "champion_chapter": self.champion.public_dict(),
            "facts": sorted(self.facts),
            "objective_progress": {
                "verified": len(self.verified_objectives),
                "total": len(COMPLETION_QUEST),
                "verified_ids": list(self.verified_objectives),
                "next": self.next_objective,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
            "battle_policy": self.battle_policy_report,
        }


class QualifiedExecutor(Protocol):
    def execute(self, action: MacroAction) -> ExecutedAction: ...


class _CountingExecutor:
    def __init__(self, executor: QualifiedExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> ExecutedAction:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


def is_rival_victory_verified(
    state: OaksErrandState,
    *,
    saw_trainer_battle: bool,
) -> bool:
    """Require both a trainer-battle latch and the immutable post-win snapshot."""
    return saw_trainer_battle and state.rival_victory_snapshot


def is_parcel_verified(state: OaksErrandState) -> bool:
    return state.parcel_snapshot


def is_pokedex_verified(state: OaksErrandState) -> bool:
    return state.pokedex_snapshot


def run_qualified_play(
    rom_path: str | Path,
    *,
    watch: bool = False,
    speed: int | None = None,
    new_game_timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
    opening_timing: OpeningTiming = DEFAULT_OPENING_TIMING,
    play_timing: QualifiedPlayTiming = DEFAULT_QUALIFIED_PLAY_TIMING,
    progress: ProgressSink | None = None,
    trajectory_sink: TrajectorySink | None = None,
    trajectory_episode_id: str | None = None,
    battle_start_offsets: tuple[BattleStartOffset, ...] | None = None,
    battle_model: BattleMoveRanker | None = None,
    battle_control_model: BattleControlMLP | None = None,
    execute_battle_control_model: bool = False,
    battle_control_confidence_threshold: float = 0.0,
    battle_model_confidence_threshold: float = 0.0,
    require_battle_model_teacher_agreement: bool = True,
    battle_correction_sink: Callable[[Mapping[str, object]], None] | None = None,
    battle_control_sink: Callable[[Mapping[str, object]], None] | None = None,
    _emulator: PyBoyAdapter | None = None,
) -> QualifiedPlayReport:
    """Run every currently qualified objective in one clean, no-save session."""
    if (trajectory_sink is None) != (trajectory_episode_id is None):
        raise ValueError("trajectory_sink and trajectory_episode_id must be provided together")
    if (
        battle_start_offsets is not None
        and trajectory_sink is None
        and battle_control_sink is None
    ):
        raise ValueError(
            "battle_start_offsets require private trajectory or battle-control recording"
        )
    if not 0.0 <= battle_model_confidence_threshold <= 1.0:
        raise ValueError("battle_model_confidence_threshold must be between zero and one")
    if not isinstance(require_battle_model_teacher_agreement, bool):
        raise TypeError("require_battle_model_teacher_agreement must be a bool")
    if battle_correction_sink is not None and battle_model is None:
        raise ValueError("battle_correction_sink requires a battle model")
    if battle_control_sink is not None and battle_model is None:
        raise ValueError("battle_control_sink requires a battle model")
    if battle_control_model is not None and battle_model is None:
        raise ValueError("battle_control_model requires a battle move model")
    if execute_battle_control_model and battle_control_model is None:
        raise ValueError("battle control execution requires a control model")
    if not 0.0 <= battle_control_confidence_threshold <= 1.0:
        raise ValueError(
            "battle_control_confidence_threshold must be between zero and one"
        )
    battle_start_schedule = (
        BattleStartScheduleController(battle_start_offsets)
        if battle_start_offsets is not None
        else None
    )
    emulator_context = (
        PyBoyAdapter(rom_path, watch=watch, speed=speed)
        if _emulator is None
        else nullcontext(_emulator)
    )
    with ExitStack() as stack:
        if battle_start_schedule is not None:
            stack.enter_context(bind_battle_start_schedule(battle_start_schedule))
        emulator = stack.enter_context(emulator_context)
        reader = PokemonRedStateReader(emulator)
        model_policy = None
        if battle_model is not None:
            model_policy = ModelAssistedBattlePolicy(
                model=battle_model,
                encoder=PokemonRedObservationEncoder.from_state_reader(reader),
                confidence_threshold=battle_model_confidence_threshold,
                control_model=battle_control_model,
                execute_control_model=execute_battle_control_model,
                control_confidence_threshold=battle_control_confidence_threshold,
                require_teacher_agreement=require_battle_model_teacher_agreement,
                correction_sink=battle_correction_sink,
                control_sink=battle_control_sink,
                observe_teacher_when_not_required=(
                    (battle_correction_sink is not None or battle_control_sink is not None)
                    and not require_battle_model_teacher_agreement
                ),
            )
            stack.enter_context(bind_battle_policy_override(model_policy))
        base_executor: QualifiedExecutor = FrameSafeExecutor(
            emulator,
            new_game_timing.controller_timing(),
        )
        recording_executor: RecordingExecutor[MacroAction, ExecutedAction] | None = None
        recording_failures = [0]
        effective_progress = progress
        if trajectory_sink is not None and trajectory_episode_id is not None:
            snapshot_encoder = PokemonRedObservationEncoder.from_state_reader(reader)
            recording_executor = RecordingExecutor(
                delegate=base_executor,
                snapshot_provider=snapshot_encoder,
                sink=trajectory_sink,
                episode_id=trajectory_episode_id,
            )
            base_executor = recording_executor
            stack.enter_context(
                bind_battle_decision_observer(
                    PokemonRedBattleDecisionObserver(
                        encoder=snapshot_encoder,
                        recorder=recording_executor,
                    )
                )
            )
            if battle_start_schedule is not None:
                stack.enter_context(
                    bind_battle_schedule_observer(
                        PokemonRedBattleScheduleObserver(
                            encoder=snapshot_encoder,
                            recorder=recording_executor,
                            sink=trajectory_sink,
                            schedule_sha256=battle_start_schedule.schedule_sha256,
                        )
                    )
                )
            effective_progress = _trajectory_progress_bridge(
                progress,
                trajectory_sink,
                trajectory_episode_id,
                recording_executor,
                recording_failures,
            )
        progress = effective_progress

        opening = run_opening_chapter(
            rom_path,
            new_game_timing=new_game_timing,
            opening_timing=opening_timing,
            progress=_opening_progress_bridge(effective_progress),
            _emulator=emulator,
            _executor=base_executor,
        )
        executor = _CountingExecutor(base_executor)

        _move(executor, reader, LAB_RIVAL_TRIGGER_DIRECTIONS, "lab rival trigger")
        _expect_position(reader.read(), MapId.OAKS_LAB, 4, 6, "lab rival trigger")
        _wait(executor, play_timing.rival_trigger_wait_frames)
        rival_raw, rival_evidence, saw_trainer_battle = _defeat_lab_rival(
            executor,
            reader,
            play_timing,
        )
        _emit(progress, emulator, "rival_defeated", "Defeated the lab rival", 7)

        _move(executor, reader, LAB_EXIT_DIRECTIONS, "Oak's Lab exit")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.PALLET_TOWN, 12, 12, "Oak's Lab exit")

        _move(
            executor,
            reader,
            PALLET_TO_ROUTE_1_DIRECTIONS,
            "Pallet Town north route",
        )
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.ROUTE_1, 10, 35, "Route 1 south entrance")

        _wait(executor, play_timing.route_1_north_seed_wait_frames)
        _move(
            executor,
            reader,
            ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
            "Route 1 northbound",
        )
        _wait(executor, play_timing.transition_wait_frames)
        viridian = reader.read()
        _expect_position(viridian, MapId.VIRIDIAN_CITY, 21, 35, "Viridian City entrance")
        _emit(progress, emulator, "viridian_reached", "Reached Viridian City", 8)

        _move(executor, reader, VIRIDIAN_TO_MART_DIRECTIONS, "Viridian Mart route")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.VIRIDIAN_MART, 3, 7, "Viridian Mart entrance")
        _wait(executor, play_timing.mart_prompt_wait_frames)
        parcel_raw, parcel_evidence = _receive_parcel(
            executor,
            reader,
            play_timing,
        )
        _emit(progress, emulator, "parcel_received", "Received Oak's Parcel", 9)

        _move(executor, reader, MART_EXIT_DIRECTIONS, "Viridian Mart exit")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.VIRIDIAN_CITY, 29, 20, "Viridian Mart exterior")

        _move(
            executor,
            reader,
            VIRIDIAN_TO_ROUTE_1_DIRECTIONS,
            "Viridian City south route",
        )
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.ROUTE_1, 11, 0, "Route 1 north entrance")

        _wait(executor, play_timing.route_1_south_seed_wait_frames)
        _move(
            executor,
            reader,
            ROUTE_1_TO_PALLET_DIRECTIONS,
            "Route 1 southbound",
        )
        _wait(executor, play_timing.transition_wait_frames)
        pallet_returned = reader.read()
        _expect_position(pallet_returned, MapId.PALLET_TOWN, 10, 0, "Pallet Town return")
        _emit(
            progress,
            emulator,
            "pallet_returned",
            "Returned safely to Pallet Town",
            10,
        )

        _move(executor, reader, PALLET_TO_LAB_DIRECTIONS, "Professor Oak return")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.OAKS_LAB, 5, 11, "Oak's Lab return")
        _move(executor, reader, LAB_TO_OAK_DIRECTIONS, "Professor Oak approach")
        _expect_position(reader.read(), MapId.OAKS_LAB, 5, 3, "Professor Oak")

        executor.execute(MacroAction(MacroActionKind.INTERACT))
        _wait(executor, play_timing.dialogue_wait_frames)
        pokedex_raw, pokedex_evidence = _receive_pokedex(
            executor,
            reader,
            play_timing,
        )
        _emit(
            progress,
            emulator,
            "pokedex_received",
            "Delivered the parcel and received the Pokédex",
            11,
        )

        try:
            pewter = run_pewter_chapter(
                emulator,
                reader,
                executor,
                progress=_pewter_progress_bridge(progress),
            )
        except PewterChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            cerulean = run_cerulean_chapter(
                emulator,
                reader,
                executor,
                progress=_cerulean_progress_bridge(progress),
            )
        except CeruleanChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            cascade = run_cascade_chapter(
                emulator,
                reader,
                executor,
                progress=_cascade_progress_bridge(progress),
            )
        except CascadeChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            vermilion = run_vermilion_chapter(
                emulator,
                reader,
                executor,
                progress=_vermilion_progress_bridge(progress),
            )
        except VermilionChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            ss_anne = run_ss_anne_chapter(
                emulator,
                reader,
                executor,
                progress=_ss_anne_progress_bridge(progress),
            )
        except SSAnneChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            surge = run_surge_chapter(
                emulator,
                reader,
                executor,
                progress=_surge_progress_bridge(progress),
            )
        except SurgeChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            lavender = run_lavender_chapter(
                emulator,
                reader,
                executor,
                progress=_lavender_progress_bridge(progress),
            )
        except LavenderChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            celadon = run_celadon_chapter(
                emulator,
                reader,
                executor,
                progress=_celadon_progress_bridge(progress),
            )
        except CeladonChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            hideout = run_hideout_chapter(
                emulator,
                reader,
                executor,
                progress=_hideout_progress_bridge(progress),
            )
        except HideoutChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            tower = run_tower_chapter(
                emulator,
                reader,
                executor,
                progress=_tower_progress_bridge(progress),
            )
        except TowerChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            fuchsia = run_fuchsia_chapter(
                emulator,
                reader,
                executor,
                progress=_fuchsia_progress_bridge(progress),
            )
        except FuchsiaChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            safari = run_safari_chapter(
                emulator,
                reader,
                executor,
                progress=_safari_progress_bridge(progress),
            )
        except SafariChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            koga = run_koga_chapter(
                emulator,
                reader,
                executor,
                progress=_koga_progress_bridge(progress),
            )
        except KogaChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            strength = run_strength_chapter(
                emulator,
                reader,
                executor,
                progress=_strength_progress_bridge(progress),
            )
        except StrengthChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            erika = run_erika_chapter(
                emulator,
                reader,
                executor,
                progress=_erika_progress_bridge(progress),
            )
        except ErikaChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            saffron = run_saffron_chapter(
                emulator,
                reader,
                executor,
                progress=_saffron_progress_bridge(progress),
            )
        except SaffronChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            silph = run_silph_chapter(
                emulator,
                reader,
                executor,
                progress=_silph_progress_bridge(progress),
            )
        except SilphChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            dojo = run_dojo_chapter(
                emulator,
                reader,
                executor,
                progress=_dojo_progress_bridge(progress),
            )
        except DojoChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            sabrina = run_sabrina_chapter(
                emulator,
                reader,
                executor,
                progress=_sabrina_progress_bridge(progress),
            )
        except SabrinaChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            cinnabar = run_cinnabar_chapter(
                emulator,
                reader,
                executor,
                progress=_cinnabar_progress_bridge(progress),
            )
        except CinnabarChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            blaine = run_blaine_chapter(
                emulator,
                reader,
                executor,
                progress=_blaine_progress_bridge(progress),
            )
        except BlaineChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            giovanni = run_giovanni_chapter(
                emulator,
                reader,
                executor,
                progress=_giovanni_progress_bridge(progress),
            )
        except GiovanniChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            victory_road = run_victory_road_chapter(
                emulator,
                reader,
                executor,
                progress=_victory_road_progress_bridge(progress),
            )
        except VictoryRoadChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            lorelei = run_lorelei_chapter(
                emulator,
                reader,
                executor,
                progress=_lorelei_progress_bridge(progress),
            )
        except LoreleiChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            bruno = run_bruno_chapter(
                emulator,
                reader,
                executor,
                progress=_bruno_progress_bridge(progress),
            )
        except BrunoChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            agatha = run_agatha_chapter(
                emulator,
                reader,
                executor,
                progress=_agatha_progress_bridge(progress),
            )
        except AgathaChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            lance = run_lance_chapter(
                emulator,
                reader,
                executor,
                progress=_lance_progress_bridge(progress),
            )
        except LanceChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            champion = run_champion_chapter(
                emulator,
                reader,
                executor,
                progress=_champion_progress_bridge(progress),
            )
        except ChampionChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        facts = (
            opening.facts
            | semantic_facts(pokedex_raw)
            | semantic_facts(pewter.pewter_reached)
            | semantic_facts(pewter.brock_defeated)
            | semantic_facts(cerulean.cerulean_reached)
            | semantic_facts(vermilion.final_raw)
            | semantic_facts(ss_anne.final_raw)
            | semantic_facts(surge.final_raw)
            | semantic_facts(lavender.final_raw)
            | semantic_facts(celadon.final_raw)
            | semantic_facts(hideout.final_raw)
            | semantic_facts(tower.final_raw)
            | semantic_facts(fuchsia.final_raw)
            | semantic_facts(safari.final_raw)
            | semantic_facts(koga.final_raw)
            | semantic_facts(strength.final_raw)
            | semantic_facts(erika.final_raw)
            | semantic_facts(saffron.final_raw)
            | semantic_facts(silph.final_raw)
            | semantic_facts(dojo.final_raw)
            | semantic_facts(sabrina.final_raw)
            | semantic_facts(cinnabar.final_raw)
            | semantic_facts(blaine.final_raw)
            | semantic_facts(giovanni.final_raw)
            | semantic_facts(victory_road.final_raw)
            | semantic_facts(lorelei.final_raw)
            | semantic_facts(bruno.final_raw)
            | semantic_facts(agatha.final_raw)
            | semantic_facts(lance.final_raw)
            | semantic_facts(champion.final_raw)
        )
        state = GameState(
            mode=game_mode(champion.final_raw),
            facts=facts,
            location=location_label(champion.final_raw.map_id),
        )
        verified_objectives = tuple(
            objective.id
            for objective in COMPLETION_QUEST.topological_order()
            if objective.completion_facts.issubset(facts)
        )
        available = COMPLETION_QUEST.available_objectives(state)
        next_objective = available[0].id if available else None
        final_pokedex = reader.read_pokedex_state()
        final_boxes = reader.read_all_box_states()
        final_party = PokemonRedPartyReader(emulator).read()
        report = QualifiedPlayReport(
            rom=emulator.fingerprint,
            pyboy_version=emulator.pyboy_version,
            emulator_window=emulator.window_name,
            emulator_speed=emulator.speed,
            opening=opening,
            rival_defeated=rival_raw,
            viridian_reached=viridian,
            parcel_received=parcel_raw,
            pallet_returned=pallet_returned,
            pokedex_received=pokedex_raw,
            pewter=pewter,
            cerulean=cerulean,
            cascade=cascade,
            vermilion=vermilion,
            ss_anne=ss_anne,
            surge=surge,
            lavender=lavender,
            celadon=celadon,
            hideout=hideout,
            tower=tower,
            fuchsia=fuchsia,
            safari=safari,
            koga=koga,
            strength=strength,
            erika=erika,
            saffron=saffron,
            silph=silph,
            dojo=dojo,
            sabrina=sabrina,
            cinnabar=cinnabar,
            blaine=blaine,
            giovanni=giovanni,
            victory_road=victory_road,
            lorelei=lorelei,
            bruno=bruno,
            agatha=agatha,
            lance=lance,
            champion=champion,
            rival_evidence=rival_evidence,
            parcel_evidence=parcel_evidence,
            pokedex_evidence=pokedex_evidence,
            saw_trainer_battle=saw_trainer_battle,
            facts=facts,
            verified_objectives=verified_objectives,
            next_objective=next_objective,
            frames_executed=emulator.frame_count,
            actions_executed=opening.actions_executed + executor.actions_executed,
            controller_released=not emulator.pressed_buttons,
            pokedex_state=final_pokedex,
            collection_progress=summarize_red_collection(
                final_pokedex,
                final_party,
                final_boxes,
            ),
            battle_policy_report=(model_policy.public_dict() if model_policy is not None else None),
        )
        if not report.passed:
            raise QualifiedPlayError("Qualified play evidence failed its public contract.")
        if battle_start_schedule is not None:
            battle_start_schedule.require_complete()
        if (
            trajectory_sink is not None
            and trajectory_episode_id is not None
            and recording_executor is not None
        ):
            try:
                trajectory_sink.record_event(
                    SparseEvent(
                        event_id=f"{trajectory_episode_id}:terminal",
                        episode_id=trajectory_episode_id,
                        step_index=recording_executor.next_step_index,
                        kind="terminal",
                        payload={
                            "status": "complete",
                            "game_complete": True,
                            "qualified_through": QUALIFIED_THROUGH_OBJECTIVE,
                            "objectives_verified": len(verified_objectives),
                            "objectives_total": len(COMPLETION_QUEST),
                            "frames": report.frames_executed,
                            "actions": report.actions_executed,
                            "controller_released": report.controller_released,
                            "battle_start_schedule": (
                                {
                                    "complete": True,
                                    "expected_battles": battle_start_schedule.expected_count,
                                    "finished_battles": battle_start_schedule.finished_count,
                                    "schedule_sha256": (battle_start_schedule.schedule_sha256),
                                }
                                if battle_start_schedule is not None
                                else None
                            ),
                        },
                    )
                )
            except Exception:
                recording_failures[0] += 1
            failures = recording_failures[0] + recording_executor.recording_failures
            if failures:
                reasons = dict(recording_executor.recording_failure_reasons)
                if recording_failures[0]:
                    reasons["sparse_event"] = recording_failures[0]
                raise QualifiedPlayError(
                    f"Trajectory recording lost {failures} record(s); "
                    f"categories={reasons!r}; the private episode was not promoted."
                )
            try:
                trajectory_sink.finalize()
            except Exception as error:
                raise QualifiedPlayError(
                    "Trajectory finalization failed; the private episode was not promoted."
                ) from error
        return report


def _defeat_lab_rival(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: QualifiedPlayTiming,
) -> tuple[RawGameState, OaksErrandState, bool]:
    saw_trainer_battle = False
    for pulse in range(timing.max_rival_pulses + 1):
        raw = reader.read()
        state = reader.read_oaks_errand_state(raw)
        if state.phase is OaksErrandPhase.RIVAL_BATTLE:
            saw_trainer_battle = True
        if is_rival_victory_verified(
            state,
            saw_trainer_battle=saw_trainer_battle,
        ):
            return raw, state, saw_trainer_battle
        if pulse == timing.max_rival_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        wait_frames = timing.battle_wait_frames if raw.battle_state else timing.dialogue_wait_frames
        _wait(executor, wait_frames)
    raise QualifiedPlayError("The lab rival failed the bounded verified-victory gate.")


def _receive_parcel(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: QualifiedPlayTiming,
) -> tuple[RawGameState, OaksErrandState]:
    for pulse in range(timing.max_parcel_pulses + 1):
        raw = reader.read()
        state = reader.read_oaks_errand_state(raw)
        if is_parcel_verified(state):
            return raw, state
        if pulse == timing.max_parcel_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise QualifiedPlayError("Oak's Parcel failed its bounded semantic gate.")


def _receive_pokedex(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: QualifiedPlayTiming,
) -> tuple[RawGameState, OaksErrandState]:
    for pulse in range(timing.max_pokedex_pulses + 1):
        raw = reader.read()
        state = reader.read_oaks_errand_state(raw)
        if is_pokedex_verified(state):
            return raw, state
        if pulse == timing.max_pokedex_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise QualifiedPlayError("The Pokédex failed its bounded semantic gate.")


def _move(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
) -> RawGameState:
    state = reader.read()
    for step, direction in enumerate(directions, start=1):
        if state.battle_state:
            raise QualifiedPlayError(f"Unexpected battle interrupted {label} before step {step}.")
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        if state.battle_state:
            raise QualifiedPlayError(f"Unexpected battle interrupted {label} at step {step}.")
    return state


def _expect_position(
    state: RawGameState,
    map_id: MapId,
    x: int,
    y: int,
    label: str,
) -> None:
    if (
        state.map_id != map_id
        or state.player_x != x
        or state.player_y != y
        or state.battle_state != 0
    ):
        raise QualifiedPlayError(f"The clean run missed the stable {label} gate.")


def _wait(executor: _CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _opening_progress_bridge(sink: ProgressSink | None) -> Callable[[OpeningProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: OpeningProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _pewter_progress_bridge(sink: ProgressSink | None) -> Callable[[PewterProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: PewterProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=POKEDEX_CHECKPOINT_COUNT + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _cerulean_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[CeruleanProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: CeruleanProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(POKEDEX_CHECKPOINT_COUNT + PEWTER_CHECKPOINT_COUNT + progress.completed),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _cascade_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[CascadeProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: CascadeProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _vermilion_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[VermilionProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: VermilionProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _ss_anne_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[SSAnneProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: SSAnneProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _surge_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[SurgeProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: SurgeProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _lavender_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[LavenderProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: LavenderProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _celadon_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[CeladonProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: CeladonProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _hideout_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[HideoutProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: HideoutProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _tower_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[TowerProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: TowerProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _fuchsia_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[FuchsiaProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: FuchsiaProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _safari_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[SafariProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: SafariProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + FUCHSIA_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _koga_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[KogaProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: KogaProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + FUCHSIA_CHECKPOINT_COUNT
                    + SAFARI_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _strength_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[StrengthProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: StrengthProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + FUCHSIA_CHECKPOINT_COUNT
                    + SAFARI_CHECKPOINT_COUNT
                    + KOGA_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _erika_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[ErikaProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: ErikaProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + FUCHSIA_CHECKPOINT_COUNT
                    + SAFARI_CHECKPOINT_COUNT
                    + KOGA_CHECKPOINT_COUNT
                    + STRENGTH_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _saffron_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[SaffronProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: SaffronProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + FUCHSIA_CHECKPOINT_COUNT
                    + SAFARI_CHECKPOINT_COUNT
                    + KOGA_CHECKPOINT_COUNT
                    + STRENGTH_CHECKPOINT_COUNT
                    + ERIKA_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _silph_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[SilphProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: SilphProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + CASCADE_CHECKPOINT_COUNT
                    + VERMILION_CHECKPOINT_COUNT
                    + SS_ANNE_CHECKPOINT_COUNT
                    + SURGE_CHECKPOINT_COUNT
                    + LAVENDER_CHECKPOINT_COUNT
                    + CELADON_CHECKPOINT_COUNT
                    + HIDEOUT_CHECKPOINT_COUNT
                    + TOWER_CHECKPOINT_COUNT
                    + FUCHSIA_CHECKPOINT_COUNT
                    + SAFARI_CHECKPOINT_COUNT
                    + KOGA_CHECKPOINT_COUNT
                    + STRENGTH_CHECKPOINT_COUNT
                    + ERIKA_CHECKPOINT_COUNT
                    + SAFFRON_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _sabrina_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[SabrinaProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: SabrinaProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                - VICTORY_ROAD_CHECKPOINT_COUNT
                - GIOVANNI_CHECKPOINT_COUNT
                - BLAINE_CHECKPOINT_COUNT
                - CINNABAR_CHECKPOINT_COUNT
                - SABRINA_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _dojo_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[DojoProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: DojoProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                - VICTORY_ROAD_CHECKPOINT_COUNT
                - GIOVANNI_CHECKPOINT_COUNT
                - BLAINE_CHECKPOINT_COUNT
                - CINNABAR_CHECKPOINT_COUNT
                - SABRINA_CHECKPOINT_COUNT
                - DOJO_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _cinnabar_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[CinnabarProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: CinnabarProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                - VICTORY_ROAD_CHECKPOINT_COUNT
                - GIOVANNI_CHECKPOINT_COUNT
                - BLAINE_CHECKPOINT_COUNT
                - CINNABAR_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _blaine_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[BlaineProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: BlaineProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                - VICTORY_ROAD_CHECKPOINT_COUNT
                - GIOVANNI_CHECKPOINT_COUNT
                - BLAINE_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _giovanni_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[GiovanniProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: GiovanniProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                - VICTORY_ROAD_CHECKPOINT_COUNT
                - GIOVANNI_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _victory_road_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[VictoryRoadProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: VictoryRoadProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                - VICTORY_ROAD_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _lorelei_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[LoreleiProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: LoreleiProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                - LORELEI_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _bruno_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[BrunoProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: BrunoProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                - BRUNO_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _agatha_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[AgathaProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: AgathaProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                - AGATHA_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _lance_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[LanceProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: LanceProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                - LANCE_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _champion_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[ChampionProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: ChampionProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=QUALIFIED_PLAY_CHECKPOINT_COUNT
                - CHAMPION_CHECKPOINT_COUNT
                + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _trajectory_progress_bridge(
    downstream: ProgressSink | None,
    sink: TrajectorySink,
    episode_id: str,
    recorder: RecordingExecutor[MacroAction, ExecutedAction],
    recording_failures: list[int],
) -> ProgressSink:
    def emit(progress: QualifiedPlayProgress) -> None:
        if downstream is not None:
            downstream(progress)
        try:
            sink.record_event(
                SparseEvent(
                    event_id=(
                        f"{episode_id}:checkpoint:{recorder.next_step_index}:"
                        f"{progress.completed}:{progress.checkpoint_id}"
                    ),
                    episode_id=episode_id,
                    step_index=recorder.next_step_index,
                    kind="checkpoint",
                    payload={
                        "checkpoint_id": progress.checkpoint_id,
                        "label": progress.label,
                        "completed": progress.completed,
                        "total": progress.total,
                        "frames": progress.frames_executed,
                    },
                )
            )
        except Exception:
            recording_failures[0] += 1

    return emit


def _emit(
    sink: ProgressSink | None,
    emulator: PyBoyAdapter,
    checkpoint_id: str,
    label: str,
    completed: int,
) -> None:
    if sink is not None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )


def _public_state(state: RawGameState) -> dict[str, object]:
    return {
        "mode": game_mode(state).value,
        "map_id": state.map_id,
        "location": location_label(state.map_id),
        "player_x": state.player_x,
        "player_y": state.player_y,
        "party_count": state.party_count,
        "battle_state": state.battle_state,
    }


assert (
    OPENING_CHECKPOINT_COUNT
    < POKEDEX_CHECKPOINT_COUNT
    < POKEDEX_CHECKPOINT_COUNT + PEWTER_CHECKPOINT_COUNT
    < POKEDEX_CHECKPOINT_COUNT + PEWTER_CHECKPOINT_COUNT + CERULEAN_CHECKPOINT_COUNT
    < QUALIFIED_PLAY_CHECKPOINT_COUNT
)
