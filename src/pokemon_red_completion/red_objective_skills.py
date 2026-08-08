"""Pokémon Red adapters for bounded objective skills."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.domain import GameState
from pokemon_red_completion.executor import ChapterExecutor
from pokemon_red_completion.fuchsia import FuchsiaTiming, run_fuchsia_chapter
from pokemon_red_completion.hideout import EmulatorState, HideoutTiming, run_hideout_chapter
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillAvailability,
    ObjectiveSkillExecution,
)
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

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "celadon_pokecenter"
            and "story:rocket_hideout_cleared" not in state.facts
            and "item:silph_scope" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the pristine Celadon Center entrance boundary."
                if executable
                else "Requires the pre-Hideout Celadon Center boundary."
            ),
        )

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

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "celadon_pokecenter"
            and "item:silph_scope" in state.facts
            and "item:poke_flute" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the Celadon Center boundary with the Silph Scope."
                if executable
                else "Requires Celadon Center with the Silph Scope before Mr. Fuji is rescued."
            ),
        )

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


@dataclass(frozen=True, slots=True)
class ReachFuchsiaObjectiveSkill:
    """Execute the qualified Poké Flute and Route 12–15 chapter."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: FuchsiaTiming = FuchsiaTiming()
    objective_id: str = "reach_fuchsia"
    specialist: Specialist = Specialist.NAVIGATION
    expected_facts: frozenset[str] = frozenset({"location:fuchsia_city"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 5_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "lavender_pokecenter"
            and "item:poke_flute" in state.facts
            and "location:fuchsia_city" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the Lavender Center boundary with the Poké Flute."
                if executable
                else "Requires Lavender Center with the Poké Flute before Fuchsia is reached."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_fuchsia_chapter(
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
