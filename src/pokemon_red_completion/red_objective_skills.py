"""Pokémon Red adapters for bounded objective skills."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pokemon_red_completion.agatha import run_agatha_chapter
from pokemon_red_completion.blaine import (
    run_blaine_after_mansion_chapter,
    run_mansion_secret_key_chapter,
)
from pokemon_red_completion.bruno import run_bruno_chapter
from pokemon_red_completion.champion import run_champion_chapter
from pokemon_red_completion.cinnabar import run_cinnabar_chapter
from pokemon_red_completion.dojo import run_dojo_chapter
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.erika import (
    EarlyErikaChapterReport,
    ErikaChapterReport,
    ErikaTiming,
    run_early_erika_chapter,
    run_erika_chapter,
)
from pokemon_red_completion.executor import ChapterExecutor
from pokemon_red_completion.fuchsia import FuchsiaTiming, run_fuchsia_chapter
from pokemon_red_completion.giovanni import run_giovanni_chapter
from pokemon_red_completion.hideout import (
    EmulatorState,
    HideoutTiming,
    run_hideout_chapter,
)
from pokemon_red_completion.koga import KogaTiming, run_koga_chapter
from pokemon_red_completion.lance import run_lance_chapter
from pokemon_red_completion.lorelei import run_lorelei_chapter
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillAvailability,
    ObjectiveSkillExecution,
    ObjectiveSkillRegistry,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.quest import Specialist
from pokemon_red_completion.sabrina import run_sabrina_chapter
from pokemon_red_completion.safari import SafariTiming, run_safari_chapter
from pokemon_red_completion.saffron import SaffronTiming, run_saffron_objective_chapter
from pokemon_red_completion.silph import SilphTiming, run_silph_chapter
from pokemon_red_completion.strength import StrengthTiming, run_strength_chapter
from pokemon_red_completion.tower import TowerTiming, run_tower_chapter
from pokemon_red_completion.training_candidate_rank import TrainingCandidateDecision
from pokemon_red_completion.training_control import (
    TrainingControlAction,
    TrainingControlDecision,
)
from pokemon_red_completion.victory_road import run_victory_road_chapter


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


@dataclass(frozen=True, slots=True)
class ObtainSurfObjectiveSkill:
    """Execute the qualified Safari Zone traversal and Surf lesson."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: SafariTiming = SafariTiming()
    objective_id: str = "obtain_surf"
    specialist: Specialist = Specialist.NAVIGATION
    expected_facts: frozenset[str] = frozenset({"move:surf_available"})
    additional_effect_facts: frozenset[str] = frozenset({"item:gold_teeth"})
    max_actions: int = 5_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "fuchsia_pokecenter"
            and "location:fuchsia_city" in state.facts
            and "move:surf_available" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the pre-Safari Fuchsia Center boundary."
                if executable
                else "Requires Fuchsia Center before Surf is obtained."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_safari_chapter(
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
class DefeatKogaObjectiveSkill:
    """Execute either qualified Fuchsia Gym battle curriculum."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: KogaTiming = KogaTiming()
    objective_id: str = "defeat_koga"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"badge:soul"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 5_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "fuchsia_pokecenter"
            and (
                "move:surf_available" in state.facts
                or "move:strength_available" in state.facts
                or "move:koga_attack_slot_3" in state.facts
            )
            and "badge:soul" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed a qualified Koga attack layout at Fuchsia Center."
                if executable
                else "Requires Fuchsia Center with a qualified Koga attack layout."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_koga_chapter(
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
class ObtainStrengthObjectiveSkill:
    """Execute the qualified Warden and Strength lesson from Fuchsia."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: StrengthTiming = StrengthTiming()
    objective_id: str = "obtain_strength"
    specialist: Specialist = Specialist.INTERACTION
    expected_facts: frozenset[str] = frozenset({"move:strength_available"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 5_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "fuchsia_pokecenter"
            and "item:gold_teeth" in state.facts
            and "move:strength_available" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed Fuchsia Center with the Gold Teeth."
                if executable
                else "Requires Fuchsia Center with Gold Teeth before Strength is obtained."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_strength_chapter(
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
class DefeatErikaObjectiveSkill:
    """Execute either qualified legal-order Celadon Gym curriculum."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: ErikaTiming = ErikaTiming()
    objective_id: str = "defeat_erika"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"badge:rainbow"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 5_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        post_strength = (
            state.mode.value == "overworld"
            and state.location == "fuchsia_pokecenter"
            and "move:strength_available" in state.facts
            and "badge:rainbow" not in state.facts
        )
        pre_koga = (
            state.mode.value == "overworld"
            and state.location == "celadon_pokecenter"
            and "story:rocket_hideout_cleared" in state.facts
            and "item:silph_scope" in state.facts
            and "badge:rainbow" not in state.facts
        )
        executable = post_strength or pre_koga
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed a qualified pre-Koga Celadon or post-Strength Fuchsia boundary."
                if executable
                else "Requires a qualified Celadon or Fuchsia Erika boundary."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        raw = self.reader.read()
        report: EarlyErikaChapterReport | ErikaChapterReport
        if raw.map_id == MapId.CELADON_POKECENTER:
            report = run_early_erika_chapter(
                self.emulator,
                self.reader,
                self.executor,
                timing=self.timing,
            )
        else:
            report = run_erika_chapter(
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
class ReachSaffronObjectiveSkill:
    """Execute the qualified vending and guard-access chapter."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: SaffronTiming = SaffronTiming()
    objective_id: str = "reach_saffron"
    specialist: Specialist = Specialist.NAVIGATION
    expected_facts: frozenset[str] = frozenset({"location:saffron_city"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 5_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "celadon_pokecenter"
            and "location:saffron_city" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the pre-access Celadon Center boundary."
                if executable
                else "Requires Celadon Center before Saffron access."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_saffron_objective_chapter(
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
class LiberateSilphObjectiveSkill:
    """Execute the qualified Silph Co. chapter from Saffron Center."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: SilphTiming = SilphTiming()
    objective_id: str = "liberate_silph"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"story:silph_co_liberated"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 15_000
    max_frames: int = 8_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "saffron_pokecenter"
            and "location:saffron_city" in state.facts
            and "story:silph_co_liberated" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the pristine post-access Saffron Center boundary."
                if executable
                else "Requires Saffron Center before Silph Co. is liberated."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_silph_chapter(
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
class DefeatSabrinaObjectiveSkill:
    """Recruit the sixth team member, then execute the qualified Sabrina chapter."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    timing: SilphTiming = SilphTiming()
    objective_id: str = "defeat_sabrina"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"badge:marsh"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 15_000
    max_frames: int = 8_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "saffron_pokecenter"
            and "story:silph_co_liberated" in state.facts
            and "badge:marsh" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the post-Silph Saffron Center boundary."
                if executable
                else "Requires Saffron Center after Silph Co. is liberated."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        dojo = run_dojo_chapter(
            self.emulator,
            self.reader,
            self.executor,
            timing=self.timing,
        )
        sabrina = run_sabrina_chapter(
            self.emulator,
            self.reader,
            self.executor,
            timing=self.timing,
        )
        return ObjectiveSkillExecution(
            actions_executed=dojo.actions_executed + sabrina.actions_executed,
            frames_executed=dojo.frames_executed + sabrina.frames_executed,
            evidence={
                "status": "ok" if dojo.passed and sabrina.passed else "failed",
                "curriculum": "recruit_hitmonlee_then_defeat_sabrina",
                "dojo": dojo.public_dict(),
                "sabrina": sabrina.public_dict(),
            },
        )


@dataclass(frozen=True, slots=True)
class ReachCinnabarObjectiveSkill:
    """Execute the qualified Fly acquisition and Route 21 chapter."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "reach_cinnabar"
    specialist: Specialist = Specialist.NAVIGATION
    expected_facts: frozenset[str] = frozenset({"location:cinnabar_island"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 5_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        post_sabrina = (
            state.mode.value == "overworld"
            and state.location == "saffron_pokecenter"
            and "badge:marsh" in state.facts
            and "move:surf_available" in state.facts
        )
        pre_sabrina = (
            state.mode.value == "overworld"
            and state.location == "celadon_pokecenter"
            and "badge:soul" in state.facts
            and "move:strength_available" in state.facts
            and "move:surf_available" in state.facts
        )
        executable = (
            (post_sabrina or pre_sabrina)
            and "location:cinnabar_island" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed a qualified post-Sabrina or pre-Sabrina Cinnabar boundary."
                if executable
                else "Requires Surf from a qualified Saffron or Celadon team boundary."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_cinnabar_chapter(
            self.emulator,
            self.reader,
            self.executor,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class ObtainSecretKeyObjectiveSkill:
    """Execute only the Mansion objective, leaving Blaine untouched."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "obtain_secret_key"
    specialist: Specialist = Specialist.NAVIGATION
    expected_facts: frozenset[str] = frozenset({"item:secret_key"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 5_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "cinnabar_pokecenter"
            and "location:cinnabar_island" in state.facts
            and "item:secret_key" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the pristine Cinnabar Center boundary."
                if executable
                else "Requires Cinnabar Center before the Mansion Secret Key route."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_mansion_secret_key_chapter(
            self.emulator,
            self.reader,
            self.executor,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatBlaineObjectiveSkill:
    """Execute party development and Cinnabar Gym after the Mansion lesson."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    training_decision_sink: Callable[[TrainingControlDecision], None] | None = None
    training_decision_authority: (
        Callable[[TrainingControlDecision], TrainingControlAction] | None
    ) = None
    training_candidate_decision_sink: Callable[[TrainingCandidateDecision], None] | None = None
    training_candidate_decision_authority: Callable[[TrainingCandidateDecision], int] | None = None
    objective_id: str = "defeat_blaine"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"badge:volcano"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 750_000
    max_frames: int = 100_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "cinnabar_pokecenter"
            and "item:secret_key" in state.facts
            and "badge:volcano" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the healed post-Mansion Cinnabar Center boundary."
                if executable
                else "Requires Cinnabar Center with the Secret Key before Blaine."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_blaine_after_mansion_chapter(
            self.emulator,
            self.reader,
            self.executor,
            training_decision_sink=self.training_decision_sink,
            training_decision_authority=self.training_decision_authority,
            training_candidate_decision_sink=self.training_candidate_decision_sink,
            training_candidate_decision_authority=self.training_candidate_decision_authority,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatGiovanniObjectiveSkill:
    """Execute the qualified Viridian Gym chapter after Blaine releases control."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "defeat_giovanni"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"badge:earth"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 5_000
    max_frames: int = 2_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "cinnabar_pokecenter"
            and "badge:volcano" in state.facts
            and "badge:earth" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the healed post-Blaine Cinnabar Center boundary."
                if executable
                else "Requires Cinnabar Center after Blaine and before Giovanni."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_giovanni_chapter(
            self.emulator,
            self.reader,
            self.executor,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class CrossVictoryRoadObjectiveSkill:
    """Execute the qualified Route 22, badge-gate, and Victory Road chapter."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "cross_victory_road"
    specialist: Specialist = Specialist.NAVIGATION
    expected_facts: frozenset[str] = frozenset({"story:victory_road_cleared"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "viridian_pokecenter"
            and "badge:earth" in state.facts
            and "move:strength_available" in state.facts
            and "story:victory_road_cleared" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the healed eight-badge Viridian Center boundary with Strength."
                if executable
                else "Requires eight badges, Strength, and the Viridian Center boundary."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_victory_road_chapter(
            self.emulator,
            self.reader,
            self.executor,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatLoreleiObjectiveSkill:
    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "defeat_lorelei"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"league:lorelei_defeated"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "indigo_plateau_lobby"
            and "story:victory_road_cleared" in state.facts
            and "league:lorelei_defeated" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            "Observed the qualified Indigo terminal." if executable else "Requires Indigo.",
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_lorelei_chapter(self.emulator, self.reader, self.executor)
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatBrunoObjectiveSkill:
    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "defeat_bruno"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"league:bruno_defeated"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "brunos_room"
            and "league:lorelei_defeated" in state.facts
            and "league:bruno_defeated" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the qualified Bruno room boundary."
                if executable
                else "Requires Bruno's room."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_bruno_chapter(self.emulator, self.reader, self.executor)
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatAgathaObjectiveSkill:
    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "defeat_agatha"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"league:agatha_defeated"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "agathas_room"
            and "league:bruno_defeated" in state.facts
            and "league:agatha_defeated" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the qualified Agatha room boundary."
                if executable
                else "Requires Agatha's room."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_agatha_chapter(self.emulator, self.reader, self.executor)
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatLanceObjectiveSkill:
    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "defeat_lance"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"league:lance_defeated"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 10_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "lances_room"
            and "league:agatha_defeated" in state.facts
            and "league:lance_defeated" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            (
                "Observed the qualified Lance room boundary."
                if executable
                else "Requires Lance's room."
            ),
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_lance_chapter(self.emulator, self.reader, self.executor)
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


@dataclass(frozen=True, slots=True)
class DefeatChampionObjectiveSkill:
    """Defeat the Champion and declare Red's coupled Hall-of-Fame transition."""

    emulator: EmulatorState
    reader: PokemonRedStateReader
    executor: ChapterExecutor
    objective_id: str = "defeat_champion"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"league:champion_defeated"})
    additional_effect_facts: frozenset[str] = frozenset({"game:hall_of_fame"})
    max_actions: int = 10_000
    max_frames: int = 3_000_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        executable = (
            state.mode.value == "overworld"
            and state.location == "champions_room"
            and "league:lance_defeated" in state.facts
            and "league:champion_defeated" not in state.facts
        )
        return ObjectiveSkillAvailability(
            executable,
            "Observed the qualified Champion room boundary."
            if executable
            else "Requires the Champion room after Lance.",
        )

    def execute(self) -> ObjectiveSkillExecution:
        report = run_champion_chapter(
            self.emulator,
            self.reader,
            self.executor,
            stop_after_victory=True,
        )
        return ObjectiveSkillExecution(
            actions_executed=report.actions_executed,
            frames_executed=report.frames_executed,
            evidence=report.public_dict(),
        )


def build_red_midgame_objective_skill_registry(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    training_decision_sink: Callable[[TrainingControlDecision], None] | None = None,
    training_decision_authority: (
        Callable[[TrainingControlDecision], TrainingControlAction] | None
    ) = None,
    training_candidate_decision_sink: (Callable[[TrainingCandidateDecision], None] | None) = None,
    training_candidate_decision_authority: (
        Callable[[TrainingCandidateDecision], int] | None
    ) = None,
) -> ObjectiveSkillRegistry:
    """Build the one canonical Celadon-to-Hall-of-Fame skill allow-list."""

    return ObjectiveSkillRegistry(
        (
            RocketHideoutObjectiveSkill(emulator, reader, executor),
            PokemonTowerObjectiveSkill(emulator, reader, executor),
            ReachFuchsiaObjectiveSkill(emulator, reader, executor),
            ObtainSurfObjectiveSkill(emulator, reader, executor),
            DefeatKogaObjectiveSkill(emulator, reader, executor),
            ObtainStrengthObjectiveSkill(emulator, reader, executor),
            DefeatErikaObjectiveSkill(emulator, reader, executor),
            ReachSaffronObjectiveSkill(emulator, reader, executor),
            LiberateSilphObjectiveSkill(emulator, reader, executor),
            DefeatSabrinaObjectiveSkill(emulator, reader, executor),
            ReachCinnabarObjectiveSkill(emulator, reader, executor),
            ObtainSecretKeyObjectiveSkill(emulator, reader, executor),
            DefeatBlaineObjectiveSkill(
                emulator,
                reader,
                executor,
                training_decision_sink=training_decision_sink,
                training_decision_authority=training_decision_authority,
                training_candidate_decision_sink=training_candidate_decision_sink,
                training_candidate_decision_authority=training_candidate_decision_authority,
            ),
            DefeatGiovanniObjectiveSkill(emulator, reader, executor),
            CrossVictoryRoadObjectiveSkill(emulator, reader, executor),
            DefeatLoreleiObjectiveSkill(emulator, reader, executor),
            DefeatBrunoObjectiveSkill(emulator, reader, executor),
            DefeatAgathaObjectiveSkill(emulator, reader, executor),
            DefeatLanceObjectiveSkill(emulator, reader, executor),
            DefeatChampionObjectiveSkill(emulator, reader, executor),
        )
    )
