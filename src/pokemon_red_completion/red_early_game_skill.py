"""Semantic early-game stages backed by Red's verified deterministic chapters.

The portable player exposes resumable chapter boundaries while keeping controller
sequences and coordinates out of policy-visible inputs.  Story effects completed
inside one game chapter remain declared automatic effects, not fictitious model
decisions.  The older one-dispatch composite remains available for historical
replay compatibility.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.cascade import (
    CascadeChapterReport,
    run_cascade_chapter,
)
from pokemon_red_completion.cascade import (
    EmulatorState as ChapterEmulatorState,
)
from pokemon_red_completion.celadon import CeladonChapterReport, run_celadon_chapter
from pokemon_red_completion.cerulean import CeruleanChapterReport, run_cerulean_chapter
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, ExecutedAction
from pokemon_red_completion.lavender import LavenderChapterReport, run_lavender_chapter
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillAvailability,
    ObjectiveSkillExecution,
    ObjectiveSkillRegistry,
)
from pokemon_red_completion.observation import PokemonRedStateReader, semantic_facts
from pokemon_red_completion.opening import (
    DEFAULT_OPENING_TIMING,
    OpeningChapterReport,
    OpeningTiming,
    run_opening_chapter,
)
from pokemon_red_completion.pewter import PewterChapterReport, run_pewter_chapter
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    OaksErrandChapterReport,
    QualifiedPlayTiming,
    is_rival_victory_verified,
    run_oaks_errand_chapter,
)
from pokemon_red_completion.quest import Specialist
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.ss_anne import SSAnneChapterReport, run_ss_anne_chapter
from pokemon_red_completion.surge import SurgeChapterReport, run_surge_chapter
from pokemon_red_completion.vermilion import VermilionChapterReport, run_vermilion_chapter

EARLY_GAME_OBJECTIVE_IDS = (
    "power_on",
    "begin_adventure",
    "choose_starter",
    "receive_pokedex",
    "reach_pewter",
    "defeat_brock",
    "reach_cerulean",
    "help_bill",
    "defeat_misty",
    "reach_vermilion",
    "obtain_cut",
    "defeat_surge",
    "reach_lavender",
    "reach_celadon",
)
EARLY_GAME_VERIFIED_FACTS = frozenset(
    fact
    for objective_id in EARLY_GAME_OBJECTIVE_IDS
    for fact in COMPLETION_QUEST.objective(objective_id).completion_facts
)
EARLY_GAME_AUTOMATIC_OBJECTIVE_IDS = EARLY_GAME_OBJECTIVE_IDS[1:]

EARLY_GAME_STAGE_OBJECTIVE_IDS = (
    "power_on",
    "receive_pokedex",
    "reach_pewter",
    "reach_cerulean",
    "help_bill",
    "reach_vermilion",
    "obtain_cut",
    "defeat_surge",
    "reach_lavender",
    "reach_celadon",
)


class EarlyGameCompositeError(RuntimeError):
    """Raised when the bounded early-game prefix misses its evidence contract."""


class EarlyGameExecutor(Protocol):
    def execute(self, action: MacroAction) -> ExecutedAction: ...


class EarlyGameObserver(Protocol):
    def latch_verified_facts(self, facts: frozenset[str]) -> None: ...


class EarlyGameChapterReport(Protocol):
    @property
    def passed(self) -> bool: ...

    @property
    def actions_executed(self) -> int: ...

    @property
    def frames_executed(self) -> int: ...

    def public_dict(self) -> dict[str, object]: ...


@dataclass(slots=True)
class EarlyGameConductorMemory:
    """Observed mechanics needed by a later stage, never a policy feature."""

    lab_rival_loss_recovery_required: bool | None = None


@dataclass(frozen=True, slots=True)
class EarlyGameSemanticStageSkill:
    """Bind one semantic objective to one already-verified mechanics chapter.

    The model sees the quest objective and semantic state.  It never sees the
    chapter callback, controller sequence, map coordinates, or an expected
    answer label.  Some chapters verify dependent story effects as a single
    game mechanic; those effects remain explicit and outside the model-choice
    count.
    """

    objective_id: str
    specialist: Specialist
    expected_facts: frozenset[str]
    additional_effect_facts: frozenset[str]
    required_facts: frozenset[str]
    required_mode: GameMode
    required_location: str | None
    run_chapter: Callable[[], EarlyGameChapterReport]
    observer: EarlyGameObserver
    max_actions: int
    max_frames: int

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        facts_ready = self.required_facts.issubset(state.facts)
        effects_absent = not self.expected_facts.intersection(state.facts)
        mode_ready = state.mode is self.required_mode
        location_ready = (
            self.required_location is None or state.location == self.required_location
        )
        executable = facts_ready and effects_absent and mode_ready and location_ready
        if executable:
            reason = "Observed the semantic boundary for this bounded chapter."
        elif not facts_ready:
            reason = "Required earlier objective evidence is absent."
        elif not effects_absent:
            reason = "The objective is already complete."
        elif not mode_ready:
            reason = f"Requires {self.required_mode.value} mode."
        else:
            reason = f"Requires the {self.required_location} chapter boundary."
        return ObjectiveSkillAvailability(executable, reason)

    def execute(self) -> ObjectiveSkillExecution:
        report = self.run_chapter()
        if not report.passed:
            raise EarlyGameCompositeError(
                f"{self.objective_id} chapter evidence failed its public contract"
            )
        verified = self.expected_facts.union(self.additional_effect_facts)
        self.observer.latch_verified_facts(frozenset(verified))
        automatic_ids = tuple(
            objective.id
            for objective in COMPLETION_QUEST.topological_order()
            if objective.completion_facts.intersection(self.additional_effect_facts)
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence={
                "automatic_objective_ids": list(automatic_ids),
                "chapter": report.public_dict(),
                "mechanic_execution": "teacher_authored_bounded_chapter",
                "schema": "pokemon-red-early-game-semantic-stage-v1",
                "selected_objective_id": self.objective_id,
                "status": "ok",
            },
        )


@dataclass(frozen=True, slots=True)
class EarlyGameCompositeReport:
    opening: OpeningChapterReport
    oaks_errand: OaksErrandChapterReport
    pewter: PewterChapterReport
    cerulean: CeruleanChapterReport
    cascade: CascadeChapterReport
    vermilion: VermilionChapterReport
    ss_anne: SSAnneChapterReport
    surge: SurgeChapterReport
    lavender: LavenderChapterReport
    celadon: CeladonChapterReport
    verified_facts: frozenset[str]
    actions_executed: int
    frames_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.opening.passed
            and self.oaks_errand.passed
            and self.pewter.passed
            and self.cerulean.passed
            and self.cascade.passed
            and self.vermilion.passed
            and self.ss_anne.passed
            and self.surge.passed
            and self.lavender.passed
            and self.celadon.passed
            and self.verified_facts == EARLY_GAME_VERIFIED_FACTS
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": self.actions_executed,
            "automatic_objective_ids": list(EARLY_GAME_AUTOMATIC_OBJECTIVE_IDS),
            "automatic_objectives": len(EARLY_GAME_AUTOMATIC_OBJECTIVE_IDS),
            "dispatch_objective_id": EARLY_GAME_OBJECTIVE_IDS[0],
            "frames_executed": self.frames_executed,
            "learned_objective_choices": 1,
            "mechanic_execution": "teacher_authored_bounded_composite",
            "schema": "pokemon-red-early-game-composite-v1",
            "status": "ok" if self.passed else "failed",
            "verified_facts": sorted(self.verified_facts),
        }


def run_early_game_composite(
    rom_path: str | Path,
    *,
    emulator: PyBoyAdapter,
    reader: PokemonRedStateReader,
    executor: EarlyGameExecutor,
    opening_timing: OpeningTiming = DEFAULT_OPENING_TIMING,
    play_timing: QualifiedPlayTiming = DEFAULT_QUALIFIED_PLAY_TIMING,
) -> EarlyGameCompositeReport:
    """Run the frozen prefix once and preserve every chapter's native evidence."""

    start_frames = emulator.frame_count
    chapter_emulator = cast(ChapterEmulatorState, emulator)
    opening = run_opening_chapter(
        rom_path,
        opening_timing=opening_timing,
        _emulator=emulator,
        _executor=executor,
    )
    counted = CountingExecutor(executor)
    oaks_errand = run_oaks_errand_chapter(
        emulator,
        reader,
        counted,
        timing=play_timing,
    )
    pewter = run_pewter_chapter(
        chapter_emulator,
        reader,
        counted,
        lab_rival_loss_recovery_required=not is_rival_victory_verified(
            oaks_errand.rival_evidence,
            saw_trainer_battle=oaks_errand.saw_trainer_battle,
        ),
    )
    cerulean = run_cerulean_chapter(chapter_emulator, reader, counted)
    cascade = run_cascade_chapter(chapter_emulator, reader, counted)
    vermilion = run_vermilion_chapter(emulator, reader, counted)
    ss_anne = run_ss_anne_chapter(emulator, reader, counted)
    surge = run_surge_chapter(emulator, reader, counted)
    lavender = run_lavender_chapter(emulator, reader, counted)
    celadon = run_celadon_chapter(emulator, reader, counted)

    observed = opening.facts.union(
        semantic_facts(oaks_errand.pokedex_received),
        semantic_facts(pewter.pewter_reached),
        semantic_facts(pewter.brock_defeated),
        semantic_facts(cerulean.cerulean_reached),
        semantic_facts(cascade.final_raw),
        semantic_facts(vermilion.final_raw),
        semantic_facts(ss_anne.final_raw),
        semantic_facts(surge.final_raw),
        semantic_facts(lavender.final_raw),
        semantic_facts(celadon.final_raw),
    )
    verified_facts = frozenset(observed.intersection(EARLY_GAME_VERIFIED_FACTS))
    report = EarlyGameCompositeReport(
        opening=opening,
        oaks_errand=oaks_errand,
        pewter=pewter,
        cerulean=cerulean,
        cascade=cascade,
        vermilion=vermilion,
        ss_anne=ss_anne,
        surge=surge,
        lavender=lavender,
        celadon=celadon,
        verified_facts=verified_facts,
        actions_executed=opening.actions_executed + counted.actions_executed,
        frames_executed=emulator.frame_count - start_frames,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        missing = sorted(EARLY_GAME_VERIFIED_FACTS.difference(verified_facts))
        raise EarlyGameCompositeError(
            "early-game composite evidence failed" + (": " + ", ".join(missing) if missing else "")
        )
    return report


@dataclass(frozen=True, slots=True)
class EarlyGameThroughCeladonObjectiveSkill:
    """Expose the frozen early prefix as one honest portable-loop dispatch."""

    rom_path: str | Path
    emulator: PyBoyAdapter
    reader: PokemonRedStateReader
    executor: EarlyGameExecutor
    observer: EarlyGameObserver
    opening_timing: OpeningTiming = DEFAULT_OPENING_TIMING
    play_timing: QualifiedPlayTiming = DEFAULT_QUALIFIED_PLAY_TIMING
    objective_id: str = "power_on"
    specialist: Specialist = Specialist.BOOTSTRAP
    expected_facts: frozenset[str] = COMPLETION_QUEST.objective("power_on").completion_facts
    additional_effect_facts: frozenset[str] = EARLY_GAME_VERIFIED_FACTS.difference(
        COMPLETION_QUEST.objective("power_on").completion_facts
    )
    max_actions: int = 150_000
    max_frames: int = 20_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = state.mode is GameMode.BOOTING and not state.facts
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed a fact-free clean-power boot boundary."
                if executable
                else "Requires the untouched clean-power boot boundary."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_early_game_composite(
            self.rom_path,
            emulator=self.emulator,
            reader=self.reader,
            executor=self.executor,
            opening_timing=self.opening_timing,
            play_timing=self.play_timing,
        )
        self.observer.latch_verified_facts(report.verified_facts)
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


def build_red_early_game_semantic_skill_registry(
    rom_path: str | Path,
    *,
    emulator: PyBoyAdapter,
    reader: PokemonRedStateReader,
    executor: EarlyGameExecutor,
    observer: EarlyGameObserver,
    opening_timing: OpeningTiming = DEFAULT_OPENING_TIMING,
    play_timing: QualifiedPlayTiming = DEFAULT_QUALIFIED_PLAY_TIMING,
) -> ObjectiveSkillRegistry:
    """Build resumable clean-boot-to-Celadon stages from verified chapters."""

    memory = EarlyGameConductorMemory()

    def objective_facts(objective_id: str) -> frozenset[str]:
        return COMPLETION_QUEST.objective(objective_id).completion_facts

    def prerequisites(*objective_ids: str) -> frozenset[str]:
        return frozenset(
            fact
            for objective_id in objective_ids
            for fact in objective_facts(objective_id)
        )

    def run_opening() -> OpeningChapterReport:
        return run_opening_chapter(
            rom_path,
            opening_timing=opening_timing,
            _emulator=emulator,
            _executor=executor,
        )

    def run_errand() -> OaksErrandChapterReport:
        counted = CountingExecutor(executor)
        report = run_oaks_errand_chapter(
            emulator,
            reader,
            counted,
            timing=play_timing,
        )
        memory.lab_rival_loss_recovery_required = not is_rival_victory_verified(
            report.rival_evidence,
            saw_trainer_battle=report.saw_trainer_battle,
        )
        return report

    def run_first_badge() -> PewterChapterReport:
        loss_recovery = memory.lab_rival_loss_recovery_required
        if loss_recovery is None:
            level = reader.read().first_party_level
            if level not in {5, 6}:
                raise EarlyGameCompositeError(
                    "Pewter stage cannot recover the lab-rival outcome from live state."
                )
            loss_recovery = level == 5
        return run_pewter_chapter(
            cast(ChapterEmulatorState, emulator),
            reader,
            executor,
            lab_rival_loss_recovery_required=loss_recovery,
        )

    def stage(
        objective_id: str,
        *,
        automatic_ids: tuple[str, ...] = (),
        required_ids: tuple[str, ...] = (),
        mode: GameMode = GameMode.OVERWORLD,
        location: str | None = None,
        run: Callable[[], EarlyGameChapterReport],
        max_actions: int,
        max_frames: int,
    ) -> EarlyGameSemanticStageSkill:
        objective = COMPLETION_QUEST.objective(objective_id)
        return EarlyGameSemanticStageSkill(
            objective_id=objective_id,
            specialist=objective.specialist,
            expected_facts=objective.completion_facts,
            additional_effect_facts=prerequisites(*automatic_ids),
            required_facts=prerequisites(*required_ids),
            required_mode=mode,
            required_location=location,
            run_chapter=run,
            observer=observer,
            max_actions=max_actions,
            max_frames=max_frames,
        )

    return ObjectiveSkillRegistry(
        (
            stage(
                "power_on",
                automatic_ids=("begin_adventure", "choose_starter"),
                mode=GameMode.BOOTING,
                run=run_opening,
                max_actions=5_000,
                max_frames=2_000_000,
            ),
            stage(
                "receive_pokedex",
                required_ids=("power_on", "begin_adventure", "choose_starter"),
                location="oaks_lab",
                run=run_errand,
                max_actions=10_000,
                max_frames=3_000_000,
            ),
            stage(
                "reach_pewter",
                automatic_ids=("defeat_brock",),
                required_ids=("receive_pokedex",),
                location="oaks_lab",
                run=run_first_badge,
                max_actions=25_000,
                max_frames=5_000_000,
            ),
            stage(
                "reach_cerulean",
                required_ids=("defeat_brock",),
                location="pewter_gym",
                run=lambda: run_cerulean_chapter(
                    cast(ChapterEmulatorState, emulator), reader, executor
                ),
                max_actions=25_000,
                max_frames=5_000_000,
            ),
            stage(
                "help_bill",
                automatic_ids=("defeat_misty",),
                required_ids=("reach_cerulean",),
                location="cerulean_city",
                run=lambda: run_cascade_chapter(
                    cast(ChapterEmulatorState, emulator), reader, executor
                ),
                max_actions=30_000,
                max_frames=6_000_000,
            ),
            stage(
                "reach_vermilion",
                required_ids=("help_bill", "defeat_misty"),
                location="cerulean_gym",
                run=lambda: run_vermilion_chapter(emulator, reader, executor),
                max_actions=20_000,
                max_frames=4_000_000,
            ),
            stage(
                "obtain_cut",
                required_ids=("reach_vermilion",),
                location="vermilion_city",
                run=lambda: run_ss_anne_chapter(emulator, reader, executor),
                max_actions=20_000,
                max_frames=4_000_000,
            ),
            stage(
                "defeat_surge",
                required_ids=("obtain_cut", "defeat_misty"),
                run=lambda: run_surge_chapter(emulator, reader, executor),
                max_actions=30_000,
                max_frames=5_000_000,
            ),
            stage(
                "reach_lavender",
                required_ids=("defeat_surge",),
                location="vermilion_gym",
                run=lambda: run_lavender_chapter(emulator, reader, executor),
                max_actions=30_000,
                max_frames=6_000_000,
            ),
            stage(
                "reach_celadon",
                required_ids=("reach_lavender",),
                location="lavender_pokecenter",
                run=lambda: run_celadon_chapter(emulator, reader, executor),
                max_actions=10_000,
                max_frames=3_000_000,
            ),
        )
    )
