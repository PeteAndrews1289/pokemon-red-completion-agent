"""Independent admission for one frozen multi-goal calibration episode.

The execution runner chooses no arm: it performs the arm already frozen in the
campaign.  This module is the separate trust boundary used by later fitting.  It
reopens the immutable episode, authenticates its provenance and assignment law,
reconciles controller accounting, and derives the signed outcome target from the
recorded verifier result.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_ACTIONS_PER_DECISION,
    FRESH_COMPOSITION_FRAMES_PER_DECISION,
    GoalManagerCompositionError,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
)
from pokemon_red_completion.goal_manager_trajectory import (
    CollectedGoalManagerDataset,
    GoalEpisodeReader,
    GoalManagerTrajectoryError,
    load_goal_manager_episode,
)
from pokemon_red_completion.multi_goal_calibration_outcome import (
    FORCED_CALIBRATION_POLICY_ID,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    RED_SOLO_COLLECTION_CONTRACT,
)

CALIBRATION_OUTCOME_SCHEMA = "pokemon.red.multi-goal-calibration-outcome.v1"
CALIBRATION_ACTOR = "forced_calibration_arm"
CALIBRATION_OBJECTIVE = "selected-semantic-option-multioutcome-calibration-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class MultiGoalCalibrationAdmissionError(RuntimeError):
    """Raised when a complete private episode differs from its frozen arm."""


@dataclass(frozen=True, slots=True)
class AdmittedMultiGoalCalibrationOutcome:
    """One path-free, independently reconstructed calibration target."""

    dataset: CollectedGoalManagerDataset
    selected_goal_kind: GoalKind
    status: GoalDecisionOutcome
    reward: float
    actions_executed: int
    frames_executed: int
    semantic_state_changed: bool
    collection_before: LivingCollectionCheckpoint
    collection_after: LivingCollectionCheckpoint

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "manifest_sha256": self.dataset.manifest_sha256,
            "private_path_fields": 0,
            "reward": self.reward,
            "schema": "pokemon.red.multi-goal-calibration-admission.v1",
            "selected_candidate_index": (
                self.dataset.examples[0].selected_candidate_index
            ),
            "selected_goal_kind": self.selected_goal_kind.value,
            "status": self.status.value,
            "teacher_queries": 0,
        }


def admit_multi_goal_calibration_episode(
    reader: GoalEpisodeReader,
    *,
    expected_episode_id: str,
    expected_campaign_id: str,
    expected_trial_claim_sha256: str,
    expected_execution_identity_sha256: str,
    expected_root_lineage_id: str,
    expected_context_catalog_sha256: str,
    expected_context_id: str,
    expected_binding_manifest_sha256: str,
    expected_state_sha256: str,
    expected_envelope_sha256: str,
    expected_question_sha256: str,
    expected_policy_context_sha256: str,
    expected_available_menu_sha256: str,
    expected_selected_available_ordinal: int,
    expected_selected_goal_kind: GoalKind,
    expected_source_commit: str,
    expected_trial_ordinal: int,
) -> AdmittedMultiGoalCalibrationOutcome:
    """Admit exactly one complete arm and derive its outcome-learning target."""

    try:
        dataset = load_goal_manager_episode(reader)
    except GoalManagerTrajectoryError as error:
        raise MultiGoalCalibrationAdmissionError(str(error)) from error
    if (
        dataset.episode_id != expected_episode_id
        or dataset.partition != "train"
        or dataset.environment_id != RED_COLLECTION_GAME_ID
        or dataset.actor != CALIBRATION_ACTOR
        or dataset.policy_id != FORCED_CALIBRATION_POLICY_ID
        or dataset.collection_id != expected_campaign_id
        or dataset.assignment_id != expected_trial_claim_sha256
        or dataset.root_lineage_id != expected_root_lineage_id
        or dataset.context_catalog_sha256 != expected_context_catalog_sha256
        or dataset.context_id != expected_context_id
        or dataset.binding_manifest_sha256 != expected_binding_manifest_sha256
        or dataset.capture_state_sha256 != expected_state_sha256
        or dataset.capture_envelope_sha256 != expected_envelope_sha256
        or dataset.source_commit != expected_source_commit
        or len(dataset.examples) != 1
    ):
        raise MultiGoalCalibrationAdmissionError("calibration provenance differs")

    example = dataset.examples[0]
    question = example.question
    if (
        type(expected_selected_available_ordinal) is not int  # noqa: E721
        or not 0 <= expected_selected_available_ordinal < len(question.available_indices)
    ):
        raise MultiGoalCalibrationAdmissionError("calibration arm differs")
    expected_selected_candidate_index = question.available_indices[
        expected_selected_available_ordinal
    ]
    probabilities = tuple(
        1.0 if index == expected_selected_candidate_index else 0.0
        for index in range(len(question.opportunities))
    )
    if (
        example.decision_id != f"{expected_episode_id}:goal-manager:0"
        or example.decision_index != 0
        or question.ordered_policy_input_sha256 != expected_question_sha256
        or question.policy_context_sha256 != expected_policy_context_sha256
        or question.available_menu_sha256 != expected_available_menu_sha256
        or example.selected_candidate_index != expected_selected_candidate_index
        or example.selected_kind is not expected_selected_goal_kind
        or example.behavior_policy_id != FORCED_CALIBRATION_POLICY_ID
        or example.behavior_probability != 1.0
        or example.behavior_candidate_probabilities != probabilities
        or example.behavior_base_probability != 0.0
        or example.behavior_exploration_mix != 0.0
        or example.behavior_temperature != 1.0
        or example.outcome_status is GoalDecisionOutcome.INTERRUPTED
    ):
        raise MultiGoalCalibrationAdmissionError("calibration arm differs")

    header = _mapping(reader.read_header(), "calibration header")
    metadata = _mapping(header.get("metadata"), "calibration metadata")
    goal = _mapping(metadata.get("goal_manager"), "calibration goal metadata")
    contract = _mapping(metadata.get("calibration"), "calibration contract")
    if (
        goal.get("execution_identity_sha256")
        != expected_execution_identity_sha256
        or contract
        != {
            "assignment_probability": 1.0,
            "maximum_decisions": 1,
            "outcome_objective": CALIBRATION_OBJECTIVE,
            "teacher_queries": 0,
            "trial_ordinal": expected_trial_ordinal,
        }
    ):
        raise MultiGoalCalibrationAdmissionError("calibration contract differs")

    terminals = [
        _mapping(row, "calibration terminal")
        for row in reader.iter_stream("events")
        if row.get("kind") == "terminal"
    ]
    if len(terminals) != 1:
        raise MultiGoalCalibrationAdmissionError(
            "calibration needs exactly one terminal"
        )
    terminal = terminals[0]
    terminal_step = terminal.get("step_index")
    if (
        terminal.get("event_id") != f"{expected_episode_id}:terminal"
        or terminal.get("episode_id") != expected_episode_id
        or type(terminal_step) is not int  # noqa: E721
        or terminal_step < 0
    ):
        raise MultiGoalCalibrationAdmissionError("calibration terminal differs")
    payload = _mapping(terminal.get("payload"), "calibration terminal payload")
    if set(payload) != {"status", "calibration"} or payload.get("status") != "complete":
        raise MultiGoalCalibrationAdmissionError("calibration terminal is incomplete")
    outcome = _mapping(payload.get("calibration"), "calibration outcome")
    expected_outcome_keys = {
        "actions_executed",
        "available_menu_sha256",
        "collection_after",
        "collection_before",
        "frames_executed",
        "policy_context_sha256",
        "schema",
        "selected_candidate_index",
        "selected_goal_kind",
        "semantic_state_changed",
        "status",
        "teacher_queries",
    }
    if (
        set(outcome) != expected_outcome_keys
        or outcome.get("schema") != CALIBRATION_OUTCOME_SCHEMA
        or outcome.get("selected_candidate_index")
        != expected_selected_candidate_index
        or outcome.get("selected_goal_kind") != expected_selected_goal_kind.value
        or outcome.get("status") != example.outcome_status.value
        or outcome.get("policy_context_sha256")
        != expected_policy_context_sha256
        or outcome.get("available_menu_sha256")
        != expected_available_menu_sha256
        or outcome.get("teacher_queries") != 0
        or type(outcome.get("semantic_state_changed")) is not bool  # noqa: E721
    ):
        raise MultiGoalCalibrationAdmissionError("calibration outcome differs")

    actions = _integer(outcome.get("actions_executed"), "calibration actions")
    frames = _integer(outcome.get("frames_executed"), "calibration frames")
    changed = bool(outcome["semantic_state_changed"])
    if (
        actions > FRESH_COMPOSITION_ACTIONS_PER_DECISION
        or frames > FRESH_COMPOSITION_FRAMES_PER_DECISION
        or (example.outcome_status is GoalDecisionOutcome.SUCCEEDED and not changed)
    ):
        raise MultiGoalCalibrationAdmissionError("calibration budget differs")

    before = _collection_checkpoint(outcome.get("collection_before"))
    after = _collection_checkpoint(outcome.get("collection_after"))
    try:
        require_living_collection_transition(
            before,
            after,
            selected_kind=expected_selected_goal_kind,
            require_selected_goal_progress=(
                example.outcome_status is GoalDecisionOutcome.SUCCEEDED
            ),
        )
    except GoalManagerCompositionError as error:
        raise MultiGoalCalibrationAdmissionError(
            "calibration collection transition differs"
        ) from error

    try:
        executions = [
            _mapping(row, "calibration execution")
            for row in reader.iter_stream("executions")
        ]
    except PrivateArtifactError as error:
        # Episode writers materialize streams lazily. A legitimately settled
        # zero-action failure therefore has no executions file at all, while
        # every nonzero outcome must still carry the independently counted
        # controller records below.
        if actions != 0 or frames != 0:
            raise MultiGoalCalibrationAdmissionError(
                "calibration execution accounting differs"
            ) from error
        executions = []
    execution_frames = [_integer(row.get("frames"), "execution frames") for row in executions]
    if (
        len(executions) != actions
        or sum(execution_frames) != frames
        or terminal_step != actions
        or any(
            row.get("episode_id") != expected_episode_id
            or row.get("status") != "success"
            or row.get("step_index") != index
            # Goal-manager choices are standalone semantic decisions. They divide
            # the stream but deliberately do not open a RecordingExecutor decision
            # scope around thousands of specialist controller actions.
            or row.get("decision_id") is not None
            for index, row in enumerate(executions)
        )
    ):
        raise MultiGoalCalibrationAdmissionError(
            "calibration execution accounting differs"
        )

    return AdmittedMultiGoalCalibrationOutcome(
        dataset=dataset,
        selected_goal_kind=expected_selected_goal_kind,
        status=example.outcome_status,
        reward=(
            1.0
            if example.outcome_status is GoalDecisionOutcome.SUCCEEDED
            else -1.0
        ),
        actions_executed=actions,
        frames_executed=frames,
        semantic_state_changed=changed,
        collection_before=before,
        collection_after=after,
    )


def _collection_checkpoint(value: object) -> LivingCollectionCheckpoint:
    raw = _mapping(value, "calibration collection")
    expected_keys = {
        "completion_contract_sha256",
        "living_species",
        "registered_species",
        "required_specimens_remaining",
        "required_specimens_sha256",
        "retained_captures",
        "specimen_counts",
        "specimen_ledger_sha256",
        "storage_headroom",
        "total_living_specimens",
        "undeclared_specimen_losses",
    }
    counts = raw.get("specimen_counts")
    if set(raw) != expected_keys or not isinstance(counts, list):
        raise MultiGoalCalibrationAdmissionError("calibration collection differs")
    parsed_counts: list[tuple[str, int]] = []
    for item in counts:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or type(item[1]) is not int  # noqa: E721
        ):
            raise MultiGoalCalibrationAdmissionError(
                "calibration specimen inventory differs"
            )
        parsed_counts.append((item[0], item[1]))
    digests: dict[str, str] = {}
    for key in (
        "completion_contract_sha256",
        "specimen_ledger_sha256",
        "required_specimens_sha256",
    ):
        candidate = raw.get(key)
        if not isinstance(candidate, str) or _SHA256.fullmatch(candidate) is None:
            raise MultiGoalCalibrationAdmissionError(
                "calibration collection digest differs"
            )
        digests[key] = candidate
    try:
        checkpoint = LivingCollectionCheckpoint(
            registered_species=_integer(raw.get("registered_species"), "registered species"),
            living_species=_integer(raw.get("living_species"), "living species"),
            required_specimens_remaining=_integer(
                raw.get("required_specimens_remaining"), "required specimens"
            ),
            retained_captures=_integer(raw.get("retained_captures"), "retained captures"),
            storage_headroom=_integer(raw.get("storage_headroom"), "storage headroom"),
            undeclared_specimen_losses=_integer(
                raw.get("undeclared_specimen_losses"), "specimen losses"
            ),
            completion_contract_sha256=digests["completion_contract_sha256"],
            specimen_ledger_sha256=digests["specimen_ledger_sha256"],
            required_specimens_sha256=digests["required_specimens_sha256"],
            specimen_counts=tuple(parsed_counts),
        )
    except GoalManagerCompositionError as error:
        raise MultiGoalCalibrationAdmissionError(
            "calibration collection differs"
        ) from error

    specimens = dict(checkpoint.specimen_counts)
    required = RED_ACQUISITION_CATALOG.required_root_acquisitions()
    remaining = {
        species: required_count - specimens.get(species, 0)
        for species, required_count in required.items()
        if required_count > specimens.get(species, 0)
    }
    retained = sum(
        min(required_count, specimens.get(species, 0))
        for species, required_count in required.items()
    )
    expected_contract = canonical_sha256(
        {
            "game_id": RED_COLLECTION_GAME_ID,
            "living_target": sorted(
                RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
            ),
            "registered_target": sorted(RED_SOLO_COLLECTION_CONTRACT.target_species),
            "required_root_acquisitions": dict(sorted(required.items())),
            "schema": "pokemon.core.living-collection-contract.v1",
        }
    )
    expected_ledger = canonical_sha256(
        {
            "schema": "pokemon.core.living-specimen-ledger.v1",
            "specimens": dict(sorted(specimens.items())),
        }
    )
    expected_required = canonical_sha256(
        {
            "remaining": dict(sorted(remaining.items())),
            "schema": "pokemon.core.remaining-required-specimens.v1",
        }
    )
    expected_living = sum(
        species in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
        for species in specimens
    )
    if (
        _integer(raw.get("total_living_specimens"), "living specimens")
        != sum(specimens.values())
        or checkpoint.living_species != expected_living
        or checkpoint.specimen_ledger_sha256 != expected_ledger
        or checkpoint.required_specimens_sha256 != expected_required
        or checkpoint.required_specimens_remaining != sum(remaining.values())
        or checkpoint.retained_captures != retained
        or checkpoint.completion_contract_sha256 != expected_contract
    ):
        raise MultiGoalCalibrationAdmissionError("calibration collection differs")
    return checkpoint


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MultiGoalCalibrationAdmissionError(f"{subject} differs")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise MultiGoalCalibrationAdmissionError(f"{subject} differs")
    return value


__all__ = [
    "AdmittedMultiGoalCalibrationOutcome",
    "MultiGoalCalibrationAdmissionError",
    "admit_multi_goal_calibration_episode",
]
