"""Real Red counterfactual adapter for one authenticated battle snapshot."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, cast

from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_runtime import execute_bounded_battle_move_turn
from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    ReadOnlyMemory,
)
from pokemon_red_completion.red_battle_scenario import (
    PreparedRedBattleScenario,
    prepare_red_battle_scenario,
    project_red_battle_turn_outcome,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder


class RedBattleScenarioSession(Protocol):
    """One isolated no-save emulator used for exactly one counterfactual."""

    def load_state_bytes(self, payload: bytes) -> None: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...

    def read_u8(self, address: int) -> int: ...


SessionFactory = Callable[[], AbstractContextManager[RedBattleScenarioSession]]
OutcomeSink = Callable[[int, BattleTurnOutcome], None]
CandidateClaimSink = Callable[[int], None]
COUNTERFACTUAL_PRE_ATTACK_FRAMES = 2_048


class RedBattleOutcomeRuntimeError(RuntimeError):
    """Raised when counterfactual replays cease to share one exact boundary."""


@dataclass(frozen=True, slots=True)
class RedBattleOutcomeCollection:
    example: BattleOutcomeExample
    capture_id: str
    manifest_sha256: str
    initial_observation_sha256: str
    outcomes: tuple[BattleTurnOutcome | None, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.battle.outcome-collection.v1",
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "root_lineage_id": self.example.root_lineage_id,
            "partition": self.example.partition.value,
            "initial_state_sha256": self.example.initial_state_sha256,
            "initial_observation_sha256": self.initial_observation_sha256,
            "candidate_count": len(self.example.features.candidate_vectors),
            "measured_candidate_count": sum(outcome is not None for outcome in self.outcomes),
            "outcomes": [
                None if outcome is None else outcome.public_dict()
                for outcome in self.outcomes
            ],
            "best_candidate_indices": list(self.example.best_candidate_indices),
            "learner_update_eligible": self.example.learner_update_eligible,
            "counterfactual_pre_attack_frames": _shared_pre_attack_frames(
                self.outcomes
            ),
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
            "full_game_replays": 0,
            "private_path_fields": 0,
        }


def collect_red_battle_outcome_example(
    capture: BattleScenarioCapture,
    *,
    session_factory: SessionFactory,
    controller_timing: ControllerTiming | None = None,
    candidate_claim_sink: CandidateClaimSink | None = None,
    outcome_sink: OutcomeSink | None = None,
) -> RedBattleOutcomeCollection:
    """Replay every supported move from identical authenticated state bytes."""

    if not isinstance(capture, BattleScenarioCapture):
        raise TypeError("capture must come from the verified battle opener")
    if not callable(session_factory):
        raise TypeError("session_factory must be callable")
    if candidate_claim_sink is not None and not callable(candidate_claim_sink):
        raise TypeError("candidate_claim_sink must be callable or None")
    if outcome_sink is not None and not callable(outcome_sink):
        raise TypeError("outcome_sink must be callable or None")
    timing = controller_timing or DEFAULT_NEW_GAME_TIMING.controller_timing()
    prepared = _prepare_exact_boundary(capture, session_factory=session_factory)
    outcomes: list[BattleTurnOutcome | None] = []
    for candidate_index, supported in enumerate(prepared.supported_candidate_mask):
        if not supported:
            outcomes.append(None)
            continue
        if candidate_claim_sink is not None:
            candidate_claim_sink(candidate_index)
        with session_factory() as session:
            session.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(cast(ReadOnlyMemory, session))
            replay_prepared = _prepare_loaded_boundary(capture, reader)
            if replay_prepared != prepared:
                raise RedBattleOutcomeRuntimeError(
                    "counterfactual replay differs from its authenticated policy boundary"
                )
            executor = FrameSafeExecutor(session, timing)
            execution = execute_bounded_battle_move_turn(
                reader,
                executor,
                expected_map=capture.manifest.expected_map,
                selected_slot=prepared.features.slot_indices[candidate_index] + 1,
                expected_battle_state=capture.manifest.expected_battle_state,
                minimum_pre_attack_frames=COUNTERFACTUAL_PRE_ATTACK_FRAMES,
                label="authenticated Red battle counterfactual",
            )
            outcome = project_red_battle_turn_outcome(execution)
            outcomes.append(outcome)
            if outcome_sink is not None:
                outcome_sink(candidate_index, outcome)

    measured = tuple(outcomes)
    _shared_pre_attack_frames(measured)
    example = BattleOutcomeExample(
        root_lineage_id=capture.manifest.root_lineage_id,
        initial_state_sha256=capture.manifest.state_sha256,
        partition=capture.manifest.partition,
        features=prepared.features,
        outcomes=measured,
    )
    return RedBattleOutcomeCollection(
        example=example,
        capture_id=capture.manifest.capture_id,
        manifest_sha256=capture.manifest_sha256,
        initial_observation_sha256=prepared.initial_observation_sha256,
        outcomes=measured,
    )


def prepare_red_battle_outcome_capture(
    capture: BattleScenarioCapture,
    *,
    session_factory: SessionFactory,
) -> PreparedRedBattleScenario:
    """Authenticate one capture's policy-visible boundary without taking an action.

    A prospective evaluator uses this narrow read-only projection to commit the
    frozen prior and candidate choices before it executes any development
    branch.  The later collector repeats the same authentication and fails if
    the observation changed.
    """

    if not isinstance(capture, BattleScenarioCapture):
        raise TypeError("capture must come from the verified battle opener")
    if not callable(session_factory):
        raise TypeError("session_factory must be callable")
    return _prepare_exact_boundary(capture, session_factory=session_factory)


def _prepare_exact_boundary(
    capture: BattleScenarioCapture,
    *,
    session_factory: SessionFactory,
) -> PreparedRedBattleScenario:
    with session_factory() as session:
        session.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(cast(ReadOnlyMemory, session))
        return _prepare_loaded_boundary(capture, reader)


def _prepare_loaded_boundary(
    capture: BattleScenarioCapture,
    reader: PokemonRedStateReader,
) -> PreparedRedBattleScenario:
    raw = reader.read()
    if (
        raw.map_id != capture.manifest.expected_map
        or raw.battle_state != capture.manifest.expected_battle_state
    ):
        raise RedBattleOutcomeRuntimeError(
            "loaded state differs from its map or battle binding"
        )
    menu = reader.read_battle_menu_state(raw)
    if menu.phase is not BattleMenuPhase.MAIN:
        raise RedBattleOutcomeRuntimeError("loaded state is not at the MAIN policy boundary")
    prepared = prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(reader),
        raw,
    )
    if (
        prepared.initial_observation_sha256
        != capture.manifest.initial_observation_sha256
    ):
        raise RedBattleOutcomeRuntimeError(
            "loaded semantic observation differs from its capture binding"
        )
    return prepared


def _shared_pre_attack_frames(
    outcomes: tuple[BattleTurnOutcome | None, ...],
) -> int:
    measured = {
        outcome.pre_attack_frames for outcome in outcomes if outcome is not None
    }
    if len(measured) != 1 or 0 in measured:
        raise RedBattleOutcomeRuntimeError(
            "counterfactual candidates do not share one positive pre-attack frame count"
        )
    return next(iter(measured))
