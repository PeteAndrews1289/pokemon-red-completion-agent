"""Bounded semantic conductor from clean power to Red's first badge."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.learned_planner_policy import ModelObjectivePolicy
from pokemon_red_completion.objective_skills import ObjectiveSkillRegistry
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.planner_model import ObjectiveRanker
from pokemon_red_completion.player_loop import (
    PlayerStepKind,
    PlayerStepResult,
    PortablePlayerLoop,
)
from pokemon_red_completion.red_early_game_skill import (
    build_red_early_game_semantic_skill_registry,
)
from pokemon_red_completion.red_player_observer import LivePokemonRedObserver
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.specialists import SpecialistRegistry

FIRST_BADGE_SELECTED_STAGE_IDS = (
    "power_on",
    "receive_pokedex",
    "reach_pewter",
)
FIRST_BADGE_AUTOMATIC_OBJECTIVE_IDS = (
    "begin_adventure",
    "choose_starter",
    "defeat_brock",
)
FIRST_BADGE_VERIFIED_OBJECTIVE_IDS = (
    "power_on",
    "begin_adventure",
    "choose_starter",
    "receive_pokedex",
    "reach_pewter",
    "defeat_brock",
)
FIRST_BADGE_FACT = "badge:boulder"
FIRST_BADGE_MAX_STEPS = len(FIRST_BADGE_SELECTED_STAGE_IDS)
RANKER_TRAINING_STATUSES = frozenset(
    {"authenticated_learned", "integration_only_unlearned"}
)


class FreshStartConductorError(RuntimeError):
    """The bounded conductor failed before a stable first-badge handoff."""

    def __init__(self, message: str, *, evidence: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.evidence = dict(evidence) if evidence is not None else None


@dataclass(frozen=True, slots=True)
class FreshFirstBadgeReport:
    steps: tuple[PlayerStepResult, ...]
    terminal_state: GameState
    loop: dict[str, object]
    observer: dict[str, object]
    objective_policy: dict[str, object]
    selected_objective_ids: tuple[str, ...]
    automatic_objective_ids: tuple[str, ...]
    ranker_training_status: str
    initial_wait_frames: int
    actions_executed: int
    frames_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        completed = COMPLETION_QUEST.completed_ids(self.terminal_state)
        policy = self.objective_policy
        return (
            FIRST_BADGE_FACT in self.terminal_state.facts
            and self.ranker_training_status in RANKER_TRAINING_STATUSES
            and set(FIRST_BADGE_VERIFIED_OBJECTIVE_IDS).issubset(completed)
            and self.selected_objective_ids == FIRST_BADGE_SELECTED_STAGE_IDS
            and self.automatic_objective_ids == FIRST_BADGE_AUTOMATIC_OBJECTIVE_IDS
            and policy.get("route_dispatch_mode") == "model_selected_specialists"
            and policy.get("expected_answer_labels_supplied") == 0
            and policy.get("fixed_dispatch_decisions") == 0
            and policy.get("selected_decisions") == FIRST_BADGE_MAX_STEPS
            and policy.get("singleton_decisions") == FIRST_BADGE_MAX_STEPS
            and policy.get("branching_decisions") == 0
            and self.actions_executed > 0
            and self.frames_executed > 0
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        policy = dict(self.objective_policy)
        if self.ranker_training_status == "integration_only_unlearned":
            integration_decisions = policy.pop("learned_choice_decisions", 0)
            policy["integration_only_decisions"] = integration_decisions
        return {
            "actions_executed": self.actions_executed,
            "assistance": {
                "deterministic_mechanics": True,
                "expected_route_labels": 0,
                "fixed_objective_dispatches": 0,
                "human_input": False,
                "ranker_training_status": self.ranker_training_status,
                "save_state_loaded": False,
                "teacher_objective_choices": 0,
            },
            "automatic_objective_ids": list(self.automatic_objective_ids),
            "checkpoint": {
                "id": "red-first-badge-v1",
                "label": "Stable post-Brock control boundary",
                "verified_objective_ids": list(FIRST_BADGE_VERIFIED_OBJECTIVE_IDS),
            },
            "claim": (
                (
                    "An authenticated learned objective ranker"
                    if self.ranker_training_status == "authenticated_learned"
                    else "An explicitly unlearned integration ranker"
                )
                + " selected three semantic singleton stages; "
                "bounded deterministic skills executed opening, errand, travel, training, "
                "and battle mechanics to a verified first-badge boundary."
            ),
            "controller_released": self.controller_released,
            "frames_executed": self.frames_executed,
            "initial_wait_frames": self.initial_wait_frames,
            "limitations": [
                "all_three_objective_selections_were_singletons",
                "deterministic_opening_navigation_training_and_battle_mechanics",
                "not_objective_ranking_competence",
                "ranker_training_status_is_declared_by_the_calling_runtime",
                "not_fresh_game_autonomy",
                "not_cross_title_transfer",
            ],
            "loop": self.loop,
            "objective_policy": policy,
            "observer": self.observer,
            "schema": "pokemon-red-fresh-first-badge-conductor-v1",
            "selected_objective_ids": list(self.selected_objective_ids),
            "status": "ok" if self.passed else "failed",
            "steps": [step.public_dict() for step in self.steps],
            "terminal": {
                "facts": sorted(self.terminal_state.facts),
                "location": self.terminal_state.location,
                "mode": self.terminal_state.mode.value,
            },
        }


def run_fresh_first_badge_conductor(
    rom_path: str | Path,
    *,
    objective_model: ObjectiveRanker,
    ranker_training_status: str,
    objective_confidence_threshold: float = 0.0,
    initial_wait_frames: int = 0,
    watch: bool = False,
    speed: int | None = None,
    _emulator: PyBoyAdapter | None = None,
) -> FreshFirstBadgeReport:
    """Run three semantic selections and stop immediately after verified Brock."""

    if ranker_training_status not in RANKER_TRAINING_STATUSES:
        raise ValueError("ranker_training_status is unsupported")
    if type(initial_wait_frames) is not int or not 0 <= initial_wait_frames <= 255:  # noqa: E721
        raise ValueError("initial_wait_frames must be an integer from zero through 255")
    emulator_context = (
        PyBoyAdapter(rom_path, watch=watch, speed=speed)
        if _emulator is None
        else nullcontext(_emulator)
    )
    with emulator_context as emulator:
        start_frames = emulator.frame_count
        reader = PokemonRedStateReader(emulator)
        encoder = PokemonRedObservationEncoder.from_state_reader(reader)
        executor = FrameSafeExecutor(
            emulator,
            timing=DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        if initial_wait_frames:
            executor.execute(MacroAction(MacroActionKind.WAIT, repeat=initial_wait_frames))
        observer = LivePokemonRedObserver(reader, COMPLETION_QUEST)
        objective_policy = ModelObjectivePolicy(
            model=objective_model,
            graph=COMPLETION_QUEST,
            snapshot_provider=encoder,
            confidence_threshold=objective_confidence_threshold,
        )
        early = build_red_early_game_semantic_skill_registry(
            rom_path,
            emulator=emulator,
            reader=reader,
            executor=executor,
            observer=observer,
        )
        loop = PortablePlayerLoop(
            graph=COMPLETION_QUEST,
            observer=observer,
            objective_policy=objective_policy,
            specialists=SpecialistRegistry(()),
            executor=executor,
            objective_skills=ObjectiveSkillRegistry(early.skills()),
        )
        steps: list[PlayerStepResult] = []
        try:
            for _ in range(FIRST_BADGE_MAX_STEPS):
                step = loop.step()
                if step.kind is PlayerStepKind.COMPLETE:
                    raise FreshStartConductorError(
                        "full quest graph completed before the first-badge boundary"
                    )
                steps.append(step)
                if FIRST_BADGE_FACT in observer.observe().facts:
                    break
            terminal = observer.observe()
        except Exception as error:
            if isinstance(error, FreshStartConductorError):
                raise
            raise FreshStartConductorError(
                "fresh-start conductor failed closed",
                evidence={
                    "cause": {
                        "exception_type": type(error).__name__,
                        "message": str(error),
                    },
                    "controller_released": not emulator.pressed_buttons,
                    "frames_executed": emulator.frame_count - start_frames,
                    "loop": dict(loop.public_dict()),
                    "objective_policy": objective_policy.public_dict(),
                    "observer": observer.public_dict(),
                    "schema": "pokemon-red-fresh-first-badge-failure-v1",
                    "stage": "semantic_conductor",
                },
            ) from error

        selected = tuple(step.objective_id for step in steps if step.objective_id is not None)
        completed = COMPLETION_QUEST.completed_ids(terminal)
        automatic = tuple(
            objective.id
            for objective in COMPLETION_QUEST.topological_order()
            if objective.id in completed and objective.id not in selected
        )
        report = FreshFirstBadgeReport(
            steps=tuple(steps),
            terminal_state=terminal,
            loop=dict(loop.public_dict()),
            observer=observer.public_dict(),
            objective_policy=objective_policy.public_dict(),
            selected_objective_ids=selected,
            automatic_objective_ids=automatic,
            ranker_training_status=ranker_training_status,
            initial_wait_frames=initial_wait_frames,
            actions_executed=loop.actions_executed,
            frames_executed=emulator.frame_count - start_frames,
            controller_released=not emulator.pressed_buttons,
        )
        if not report.passed:
            raise FreshStartConductorError(
                "fresh-start conductor missed its first-badge evidence contract",
                evidence=report.public_dict(),
            )
        return report
