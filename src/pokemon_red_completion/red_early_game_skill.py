"""One explicit fixed-mechanics boundary from clean power through Celadon.

The legacy teacher already verifies this prefix, but its chapters are not yet
independently reorderable.  The portable player therefore treats the prefix as
one composite objective skill.  Every automatically completed quest objective
is public evidence and remains outside the learned objective-choice
denominator; the model receives one dispatch at ``power_on`` rather than
fourteen fictitious decisions.
"""

from __future__ import annotations

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
from pokemon_red_completion.red_player_observer import LivePokemonRedObserver
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


class EarlyGameCompositeError(RuntimeError):
    """Raised when the bounded early-game prefix misses its evidence contract."""


class EarlyGameExecutor(Protocol):
    def execute(self, action: MacroAction) -> ExecutedAction: ...


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
    observer: LivePokemonRedObserver
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
