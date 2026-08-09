"""Observation-driven clean-power player using the portable objective loop."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_neural_model import BattleMoveRanker
from pokemon_red_completion.battle_runtime import bind_battle_policy_override
from pokemon_red_completion.battle_schedule import (
    BattleStartScheduleController,
    bind_battle_start_schedule,
)
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetMLP
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import BattleStartOffset
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.hideout import EmulatorState as ObjectiveSkillEmulatorState
from pokemon_red_completion.learned_battle_policy import ModelAssistedBattlePolicy
from pokemon_red_completion.learned_planner_policy import ModelObjectivePolicy
from pokemon_red_completion.objective_skills import ObjectiveSkillRegistry
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.planner_model import ObjectiveRanker
from pokemon_red_completion.player_loop import PlayerRunReport, PortablePlayerLoop
from pokemon_red_completion.red_early_game_skill import EarlyGameThroughCeladonObjectiveSkill
from pokemon_red_completion.red_objective_skills import (
    build_red_midgame_objective_skill_registry,
)
from pokemon_red_completion.red_player_observer import LivePokemonRedObserver
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.specialists import SpecialistRegistry
from pokemon_red_completion.training_candidate_model import (
    TrainingCandidateMLP,
    TrainingCandidateShadowAudit,
)
from pokemon_red_completion.training_candidate_rank import TrainingCandidateDecision
from pokemon_red_completion.training_control import (
    TrainingControlAction,
    TrainingControlDecision,
    TrainingControlPhase,
)
from pokemon_red_completion.training_control_model import (
    TrainingControlMLP,
    TrainingControlShadowAudit,
)

PORTABLE_CLEAN_START_MAX_STEPS = 24


class CleanStartPlayerError(RuntimeError):
    """Raised when the portable clean-start process fails its authority contract."""

    def __init__(
        self,
        message: str,
        *,
        evidence: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.evidence = dict(evidence) if evidence is not None else None


@dataclass(frozen=True, slots=True)
class CleanStartPortableReport:
    run: PlayerRunReport
    loop: Mapping[str, object]
    observer: Mapping[str, object]
    objective_policy: Mapping[str, object]
    battle_policy: Mapping[str, object] | None
    training_control: Mapping[str, object] | None
    training_candidate: Mapping[str, object] | None
    initial_wait_frames: int
    battle_schedule: Mapping[str, object] | None
    automatic_objective_ids: tuple[str, ...]
    selected_objective_ids: tuple[str, ...]
    strict_teacher_free_battle_required: bool
    training_control_authority_required: bool
    training_candidate_authority_required: bool
    controller_released: bool
    frames_executed: int

    @property
    def passed(self) -> bool:
        objective = self.objective_policy
        selected_decisions = _counter(objective, "selected_decisions")
        if not (
            self.run.passed
            and objective.get("route_dispatch_mode") == "model_selected_specialists"
            and objective.get("expected_answer_labels_supplied") == 0
            and objective.get("fixed_dispatch_decisions") == 0
            and selected_decisions == _counter(self.loop, "decisions")
            and selected_decisions > 0
            and self.controller_released
        ):
            return False
        if self.strict_teacher_free_battle_required and not self._strict_battle_passed:
            return False
        if self.training_control_authority_required and not self._training_control_passed:
            return False
        return not (
            self.training_candidate_authority_required and not self._training_candidate_passed
        )

    @property
    def _strict_battle_passed(self) -> bool:
        policy = self.battle_policy
        if policy is None:
            return False
        execution = policy.get("control_model_execution")
        return (
            policy.get("teacher_queries_allowed") is False
            and policy.get("teacher_queries") == 0
            and policy.get("teacher_fallbacks") == 0
            and _counter(policy, "decisions") > 0
            and (
                not isinstance(execution, Mapping)
                or (
                    execution.get("safety_fallbacks") == 0
                    and execution.get("low_confidence_fallbacks") == 0
                )
            )
        )

    @property
    def _training_control_passed(self) -> bool:
        report = self.training_control
        return bool(
            report is not None
            and _counter(report, "controlled_decisions") > 0
            and report.get("teacher_fallback_on_model_disagreement") is False
        )

    @property
    def _training_candidate_passed(self) -> bool:
        report = self.training_candidate
        return bool(
            report is not None
            and _counter(report, "controlled_decisions") > 0
            and report.get("teacher_fallback_on_model_disagreement") is False
        )

    def public_dict(self) -> dict[str, object]:
        objective = self.objective_policy
        assistance = {
            "expected_route_labels": _counter(objective, "expected_answer_labels_supplied"),
            "fixed_objective_dispatches": _counter(objective, "fixed_dispatch_decisions"),
            "human_input": False,
            "save_state_loaded": False,
            "teacher_fallbacks": (
                _counter(self.battle_policy, "teacher_fallbacks")
                if self.battle_policy is not None
                else 0
            ),
            "teacher_queries": (
                _counter(self.battle_policy, "teacher_queries")
                if self.battle_policy is not None
                else 0
            ),
        }
        return {
            "assistance": assistance,
            "automatic_objective_ids": list(self.automatic_objective_ids),
            "battle_policy": self.battle_policy,
            "battle_schedule": self.battle_schedule,
            "claim": (
                "A learned objective ranker selected every executable composite from clean power; "
                "registered fixed skills executed mechanics; fresh observations verified effects."
            ),
            "controller_released": self.controller_released,
            "frames_executed": self.frames_executed,
            "initial_wait_frames": self.initial_wait_frames,
            "limitations": [
                "teacher_authored_bounded_mechanic_skills",
                "early_game_is_one_fourteen_objective_composite",
                "singleton_dispatches_do_not_measure_ranking_quality",
                "not_cross_title_transfer",
            ],
            "loop": dict(self.loop),
            "objective_policy": dict(self.objective_policy),
            "observer": dict(self.observer),
            "run": self.run.public_dict(),
            "schema": "pokemon-red-portable-clean-start-run-v1",
            "selected_objective_ids": list(self.selected_objective_ids),
            "status": "ok" if self.passed else "failed",
            "strict_teacher_free_battle_required": self.strict_teacher_free_battle_required,
            "training_candidate": self.training_candidate,
            "training_candidate_authority_required": self.training_candidate_authority_required,
            "training_control": self.training_control,
            "training_control_authority_required": self.training_control_authority_required,
        }


def run_portable_clean_start(
    rom_path: str | Path,
    *,
    objective_model: ObjectiveRanker,
    objective_confidence_threshold: float = 0.0,
    battle_model: BattleMoveRanker | None = None,
    battle_control_model: BattleControlMLP | None = None,
    execute_battle_control_model: bool = False,
    battle_switch_target_model: BattleSwitchTargetMLP | None = None,
    execute_battle_switch_target_model: bool = False,
    battle_confidence_threshold: float = 0.0,
    battle_control_confidence_threshold: float = 0.0,
    require_teacher_free_battle: bool = False,
    training_control_model: TrainingControlMLP | None = None,
    execute_training_control_model: bool = False,
    training_candidate_model: TrainingCandidateMLP | None = None,
    execute_training_candidate_model: bool = False,
    initial_wait_frames: int = 0,
    battle_start_offsets: tuple[BattleStartOffset, ...] | None = None,
    watch: bool = False,
    speed: int | None = None,
    _emulator: PyBoyAdapter | None = None,
) -> CleanStartPortableReport:
    """Run observe → select → dispatch → verify from untouched boot to graph completion."""

    if type(initial_wait_frames) is not int or not 0 <= initial_wait_frames <= 255:  # noqa: E721
        raise ValueError("initial_wait_frames must be an integer from zero through 255")
    if execute_battle_control_model and battle_control_model is None:
        raise ValueError("battle-control execution requires a battle-control model")
    if execute_battle_switch_target_model and battle_switch_target_model is None:
        raise ValueError("switch-target execution requires a switch-target model")
    if battle_switch_target_model is not None and battle_model is None:
        raise ValueError("switch-target inference requires a battle move model")
    if battle_control_model is not None and battle_model is None:
        raise ValueError("battle-control inference requires a battle move model")
    if require_teacher_free_battle and battle_model is None:
        raise ValueError("teacher-free battle evaluation requires a battle model")
    if execute_training_control_model and training_control_model is None:
        raise ValueError("training-control execution requires a training-control model")
    if execute_training_candidate_model and training_candidate_model is None:
        raise ValueError("training-candidate execution requires a candidate model")

    schedule = (
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
        if schedule is not None:
            stack.enter_context(bind_battle_start_schedule(schedule))
        emulator = stack.enter_context(emulator_context)
        reader = PokemonRedStateReader(emulator)
        encoder = PokemonRedObservationEncoder.from_state_reader(reader)
        battle_policy = None
        if battle_model is not None:
            battle_policy = ModelAssistedBattlePolicy(
                model=battle_model,
                encoder=encoder,
                confidence_threshold=battle_confidence_threshold,
                control_model=battle_control_model,
                execute_control_model=execute_battle_control_model,
                control_confidence_threshold=battle_control_confidence_threshold,
                switch_target_model=battle_switch_target_model,
                execute_switch_target_model=execute_battle_switch_target_model,
                require_teacher_agreement=not require_teacher_free_battle,
                allow_teacher_queries=not require_teacher_free_battle,
            )
            stack.enter_context(bind_battle_policy_override(battle_policy))

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
        training_audit = (
            TrainingControlShadowAudit(training_control_model)
            if training_control_model is not None
            else None
        )
        candidate_audit = (
            TrainingCandidateShadowAudit(training_candidate_model)
            if training_candidate_model is not None
            else None
        )
        training_controlled = 0
        candidate_controlled = 0

        def training_authority(decision: TrainingControlDecision) -> TrainingControlAction:
            nonlocal training_controlled
            assert training_audit is not None
            assert training_control_model is not None
            training_audit.observe(decision)
            training_controlled += 1
            return training_control_model.predict(decision.observation)

        def candidate_authority(decision: TrainingCandidateDecision) -> int:
            nonlocal candidate_controlled
            assert candidate_audit is not None
            assert training_candidate_model is not None
            candidate_audit.observe(decision)
            candidate_controlled += 1
            return training_candidate_model.predict(decision.observation)

        midgame = build_red_midgame_objective_skill_registry(
            cast(ObjectiveSkillEmulatorState, emulator),
            reader,
            executor,
            training_decision_sink=(
                training_audit.observe
                if training_audit is not None and not execute_training_control_model
                else None
            ),
            training_decision_authority=(
                training_authority if execute_training_control_model else None
            ),
            training_candidate_decision_sink=(
                candidate_audit.observe
                if candidate_audit is not None and not execute_training_candidate_model
                else None
            ),
            training_candidate_decision_authority=(
                candidate_authority if execute_training_candidate_model else None
            ),
        )
        early = EarlyGameThroughCeladonObjectiveSkill(
            rom_path,
            emulator,
            reader,
            executor,
            observer,
        )
        loop = PortablePlayerLoop(
            graph=COMPLETION_QUEST,
            observer=observer,
            objective_policy=objective_policy,
            specialists=SpecialistRegistry(()),
            executor=executor,
            objective_skills=ObjectiveSkillRegistry((early, *midgame.skills())),
        )
        try:
            run = loop.run(max_steps=PORTABLE_CLEAN_START_MAX_STEPS)
            if schedule is not None:
                schedule.require_complete()
        except Exception as error:
            raise CleanStartPlayerError(
                "portable clean-start execution failed closed",
                evidence=_partial_failure_evidence(
                    error=error,
                    emulator=emulator,
                    loop=loop,
                    observer=observer,
                    objective_policy=objective_policy,
                    battle_policy=battle_policy,
                    training_audit=training_audit,
                    training_controlled=training_controlled,
                    candidate_audit=candidate_audit,
                    candidate_controlled=candidate_controlled,
                    execute_training_control_model=execute_training_control_model,
                    execute_training_candidate_model=execute_training_candidate_model,
                    schedule=schedule,
                ),
            ) from error
        selected_ids = tuple(
            step.objective_id for step in run.steps if step.objective_id is not None
        )
        completed_ids = COMPLETION_QUEST.completed_ids(run.terminal_state)
        automatic_ids = tuple(
            objective.id
            for objective in COMPLETION_QUEST.topological_order()
            if objective.id in completed_ids and objective.id not in selected_ids
        )
        training_report = _authority_report(
            training_audit.public_dict() if training_audit is not None else None,
            authority=execute_training_control_model,
            controlled_decisions=training_controlled,
            phases=(TrainingControlPhase.BATTLE.value, TrainingControlPhase.OVERWORLD.value),
        )
        candidate_report = _authority_report(
            candidate_audit.public_dict() if candidate_audit is not None else None,
            authority=execute_training_candidate_model,
            controlled_decisions=candidate_controlled,
            phases=("trainee", "venue"),
        )
        report = CleanStartPortableReport(
            run=run,
            loop=loop.public_dict(),
            observer=observer.public_dict(),
            objective_policy=objective_policy.public_dict(),
            battle_policy=battle_policy.public_dict() if battle_policy is not None else None,
            training_control=training_report,
            training_candidate=candidate_report,
            initial_wait_frames=initial_wait_frames,
            battle_schedule=(
                {
                    "complete": True,
                    "expected_battles": schedule.expected_count,
                    "finished_battles": schedule.finished_count,
                    "schedule_sha256": schedule.schedule_sha256,
                }
                if schedule is not None
                else None
            ),
            automatic_objective_ids=automatic_ids,
            selected_objective_ids=selected_ids,
            strict_teacher_free_battle_required=require_teacher_free_battle,
            training_control_authority_required=execute_training_control_model,
            training_candidate_authority_required=execute_training_candidate_model,
            controller_released=not emulator.pressed_buttons,
            frames_executed=emulator.frame_count,
        )
        if not report.passed:
            raise CleanStartPlayerError(
                "portable clean-start evidence failed its contract",
                evidence={
                    "report": report.public_dict(),
                    "schema": "pokemon-red-portable-clean-start-failure-evidence-v1",
                    "stage": "final_evidence_contract",
                },
            )
        return report


def _partial_failure_evidence(
    *,
    error: Exception,
    emulator: PyBoyAdapter,
    loop: PortablePlayerLoop,
    observer: LivePokemonRedObserver,
    objective_policy: ModelObjectivePolicy,
    battle_policy: ModelAssistedBattlePolicy | None,
    training_audit: TrainingControlShadowAudit | None,
    training_controlled: int,
    candidate_audit: TrainingCandidateShadowAudit | None,
    candidate_controlled: int,
    execute_training_control_model: bool,
    execute_training_candidate_model: bool,
    schedule: BattleStartScheduleController | None,
) -> dict[str, object]:
    return {
        "battle_policy": battle_policy.public_dict() if battle_policy is not None else None,
        "battle_schedule": (
            {
                "complete": schedule.finished_count == schedule.expected_count,
                "expected_battles": schedule.expected_count,
                "finished_battles": schedule.finished_count,
                "schedule_sha256": schedule.schedule_sha256,
            }
            if schedule is not None
            else None
        ),
        "cause": {"exception_type": type(error).__name__, "message": str(error)},
        "exception_chain": _exception_chain(error),
        "controller_released": not emulator.pressed_buttons,
        "frames_executed": emulator.frame_count,
        "loop": dict(loop.public_dict()),
        "objective_policy": objective_policy.public_dict(),
        "observer": observer.public_dict(),
        "schema": "pokemon-red-portable-clean-start-failure-evidence-v1",
        "stage": "objective_loop_execution",
        "training_candidate": _authority_report(
            candidate_audit.public_dict() if candidate_audit is not None else None,
            authority=execute_training_candidate_model,
            controlled_decisions=candidate_controlled,
            phases=("trainee", "venue"),
        ),
        "training_control": _authority_report(
            training_audit.public_dict() if training_audit is not None else None,
            authority=execute_training_control_model,
            controlled_decisions=training_controlled,
            phases=(TrainingControlPhase.BATTLE.value, TrainingControlPhase.OVERWORLD.value),
        ),
    }


def _exception_chain(error: BaseException, *, maximum_depth: int = 8) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(chain) < maximum_depth and id(current) not in seen:
        seen.add(id(current))
        chain.append(
            {
                "exception_type": type(current).__name__,
                "message": str(current),
            }
        )
        current = current.__cause__ or current.__context__
    return chain


def _authority_report(
    summary: Mapping[str, object] | None,
    *,
    authority: bool,
    controlled_decisions: int,
    phases: tuple[str, ...],
) -> dict[str, object] | None:
    if summary is None:
        return None
    report = dict(summary)
    report.update(
        {
            "authority_scopes": list(phases) if authority else [],
            "controlled_decisions": controlled_decisions,
            "model_had_execution_authority": authority and controlled_decisions > 0,
            "teacher_fallback_on_model_disagreement": False if authority else None,
        }
    )
    return report


def _counter(value: Mapping[str, object], key: str) -> int:
    observed = value.get(key, 0)
    return observed if type(observed) is int and observed >= 0 else 0  # noqa: E721
