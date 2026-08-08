"""Pokémon Red adapters for bounded objective skills."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.executor import ChapterExecutor
from pokemon_red_completion.hideout import EmulatorState, HideoutTiming, run_hideout_chapter
from pokemon_red_completion.objective_skills import ObjectiveSkillExecution
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.quest import Specialist
from pokemon_red_completion.tower import TowerTiming, run_tower_chapter


@dataclass(frozen=True, slots=True)
class RocketHideoutObjectiveSkill:
    """Execute the qualified Hideout chapter after the model chooses that branch."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: HideoutTiming = HideoutTiming()
    objective_id: str = "clear_rocket_hideout"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"story:rocket_hideout_cleared"})
    additional_effect_facts: frozenset[str] = frozenset({"item:silph_scope"})
    max_actions: int = 2_000
    max_frames: int = 2_000_000

    def execute(self) -> ObjectiveSkillExecution:
        report = run_hideout_chapter(
            self.emulator,
            self.reader,
            self.executor,
            timing=self.timing,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class PokemonTowerObjectiveSkill:
    """Execute the qualified Pokémon Tower chapter after model dispatch."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: TowerTiming = TowerTiming()
    objective_id: str = "rescue_fuji"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"item:poke_flute"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 3_000
    max_frames: int = 3_000_000

    def execute(self) -> ObjectiveSkillExecution:
        report = run_tower_chapter(
            self.emulator,
            self.reader,
            self.executor,
            timing=self.timing,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )
