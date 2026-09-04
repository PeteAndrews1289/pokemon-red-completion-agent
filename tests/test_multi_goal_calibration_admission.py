from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_trajectory import CollectedGoalManagerDataset
from pokemon_red_completion.multi_goal_calibration_admission import (
    MultiGoalCalibrationAdmissionError,
    admit_multi_goal_calibration_episode,
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

EPISODE = "red-multigoal-cal-test-00"
CAMPAIGN = "1" * 64
CLAIM = "2" * 64
ROOT = "red-goal-root-" + "3" * 64
CATALOG = "4" * 64
CONTEXT = "5" * 64
BINDING = "6" * 64
STATE = "7" * 64
ENVELOPE = "8" * 64
SOURCE = "9" * 40
EXECUTION = "a" * 64


class _Reader:
    manifest_sha256 = "b" * 64

    def __init__(self, header: dict[str, object], streams: dict[str, list[dict[str, object]]]):
        self.header = header
        self.streams = streams

    def read_header(self) -> Mapping[str, object]:
        return deepcopy(self.header)

    def iter_stream(self, stream: str) -> Iterator[Mapping[str, object]]:
        if stream not in self.streams:
            raise PrivateArtifactError("episode stream is absent")
        yield from deepcopy(self.streams.get(stream, []))


def _question() -> GoalManagerQuestion:
    return GoalManagerQuestion(
        situation=GoalSituation(*([0.5] * 9)),
        opportunities=(
            GoalOpportunity(
                binding_ref="private:acquire",
                kind=GoalKind.ACQUIRE_SPECIES,
                availability=GoalAvailability.UNAVAILABLE,
                estimated_effort=None,
                estimated_risk=None,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            ),
            GoalOpportunity(
                binding_ref="private:story",
                kind=GoalKind.ADVANCE_STORY,
                availability=GoalAvailability.AVAILABLE,
                estimated_effort=0.2,
                estimated_risk=0.1,
            ),
            GoalOpportunity(
                binding_ref="private:team",
                kind=GoalKind.DEVELOP_TEAM,
                availability=GoalAvailability.AVAILABLE,
                estimated_effort=0.3,
                estimated_risk=0.1,
            ),
        ),
    )


def _dataset() -> CollectedGoalManagerDataset:
    question = _question()
    example = GoalManagerExample(
        decision_id=f"{EPISODE}:goal-manager:0",
        episode_id=EPISODE,
        decision_index=0,
        root_lineage_id=ROOT,
        partition="train",
        environment_id=RED_COLLECTION_GAME_ID,
        actor="forced_calibration_arm",
        policy_id=FORCED_CALIBRATION_POLICY_ID,
        question=question,
        selected_candidate_index=1,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
        behavior_policy_id=FORCED_CALIBRATION_POLICY_ID,
        behavior_probability=1.0,
        behavior_candidate_probabilities=(0.0, 1.0, 0.0),
        behavior_base_probability=0.0,
        behavior_exploration_mix=0.0,
        behavior_temperature=1.0,
    )
    return CollectedGoalManagerDataset(
        episode_id=EPISODE,
        manifest_sha256="b" * 64,
        root_lineage_id=ROOT,
        partition="train",
        environment_id=RED_COLLECTION_GAME_ID,
        actor="forced_calibration_arm",
        policy_id=FORCED_CALIBRATION_POLICY_ID,
        collection_id=CAMPAIGN,
        assignment_id=CLAIM,
        source_commit=SOURCE,
        context_catalog_sha256=CATALOG,
        context_id=CONTEXT,
        binding_manifest_sha256=BINDING,
        capture_state_sha256=STATE,
        capture_envelope_sha256=ENVELOPE,
        examples=(example,),
    )


def _collection() -> LivingCollectionCheckpoint:
    species = min(RED_ACQUISITION_CATALOG.required_root_acquisitions())
    specimens = {species: 1}
    required = RED_ACQUISITION_CATALOG.required_root_acquisitions()
    remaining = {
        item: count - specimens.get(item, 0)
        for item, count in required.items()
        if count > specimens.get(item, 0)
    }
    return LivingCollectionCheckpoint(
        registered_species=1,
        living_species=int(
            species in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
        ),
        required_specimens_remaining=sum(remaining.values()),
        retained_captures=min(required[species], 1),
        storage_headroom=20,
        undeclared_specimen_losses=0,
        completion_contract_sha256=canonical_sha256(
            {
                "game_id": RED_COLLECTION_GAME_ID,
                "living_target": sorted(
                    RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
                ),
                "registered_target": sorted(RED_SOLO_COLLECTION_CONTRACT.target_species),
                "required_root_acquisitions": dict(sorted(required.items())),
                "schema": "pokemon.core.living-collection-contract.v1",
            }
        ),
        specimen_ledger_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.living-specimen-ledger.v1",
                "specimens": specimens,
            }
        ),
        required_specimens_sha256=canonical_sha256(
            {
                "remaining": dict(sorted(remaining.items())),
                "schema": "pokemon.core.remaining-required-specimens.v1",
            }
        ),
        specimen_counts=((species, 1),),
    )


def _evidence(checkpoint: LivingCollectionCheckpoint) -> dict[str, object]:
    result = checkpoint.public_dict()
    result["specimen_counts"] = [list(item) for item in checkpoint.specimen_counts]
    return result


def _reader() -> _Reader:
    question = _question()
    collection = _evidence(_collection())
    return _Reader(
        {
            "metadata": {
                "goal_manager": {"execution_identity_sha256": EXECUTION},
                "calibration": {
                    "assignment_probability": 1.0,
                    "maximum_decisions": 1,
                    "outcome_objective": (
                        "selected-semantic-option-multioutcome-calibration-v1"
                    ),
                    "teacher_queries": 0,
                    "trial_ordinal": 0,
                },
            }
        },
        {
            "events": [
                {
                    "event_id": f"{EPISODE}:terminal",
                    "episode_id": EPISODE,
                    "step_index": 1,
                    "kind": "terminal",
                    "payload": {
                        "status": "complete",
                        "calibration": {
                            "actions_executed": 1,
                            "available_menu_sha256": question.available_menu_sha256,
                            "collection_after": collection,
                            "collection_before": collection,
                            "frames_executed": 10,
                            "policy_context_sha256": question.policy_context_sha256,
                            "schema": "pokemon.red.multi-goal-calibration-outcome.v1",
                            "selected_candidate_index": 1,
                            "selected_goal_kind": "advance_story",
                            "semantic_state_changed": True,
                            "status": "succeeded",
                            "teacher_queries": 0,
                        },
                    },
                }
            ],
            "executions": [
                {
                    "episode_id": EPISODE,
                    "step_index": 0,
                    "decision_id": None,
                    "frames": 10,
                    "status": "success",
                }
            ],
        },
    )


def _admit(
    monkeypatch: pytest.MonkeyPatch,
    reader: _Reader,
    *,
    dataset: CollectedGoalManagerDataset | None = None,
):
    dataset = _dataset() if dataset is None else dataset
    monkeypatch.setattr(
        "pokemon_red_completion.multi_goal_calibration_admission.load_goal_manager_episode",
        lambda _reader: dataset,
    )
    question = dataset.examples[0].question
    return admit_multi_goal_calibration_episode(
        reader,
        expected_episode_id=EPISODE,
        expected_campaign_id=CAMPAIGN,
        expected_trial_claim_sha256=CLAIM,
        expected_execution_identity_sha256=EXECUTION,
        expected_root_lineage_id=ROOT,
        expected_context_catalog_sha256=CATALOG,
        expected_context_id=CONTEXT,
        expected_binding_manifest_sha256=BINDING,
        expected_state_sha256=STATE,
        expected_envelope_sha256=ENVELOPE,
        expected_question_sha256=question.ordered_policy_input_sha256,
        expected_policy_context_sha256=question.policy_context_sha256,
        expected_available_menu_sha256=question.available_menu_sha256,
        expected_selected_available_ordinal=0,
        expected_selected_goal_kind=GoalKind.ADVANCE_STORY,
        expected_source_commit=SOURCE,
        expected_trial_ordinal=0,
    )


def test_admission_derives_one_target_from_independent_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _admit(monkeypatch, _reader())

    assert result.reward == 1.0
    assert result.actions_executed == 1
    assert result.frames_executed == 10
    assert result.public_dict()["private_path_fields"] == 0


def test_admission_rejects_terminal_selected_arm_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    reader.streams["events"][0]["payload"]["calibration"][  # type: ignore[index]
        "selected_goal_kind"
    ] = "develop_team"

    with pytest.raises(MultiGoalCalibrationAdmissionError, match="outcome differs"):
        _admit(monkeypatch, reader)


def test_admission_rejects_execution_counter_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    reader.streams["executions"][0]["frames"] = 9

    with pytest.raises(MultiGoalCalibrationAdmissionError, match="accounting"):
        _admit(monkeypatch, reader)


def test_admission_accepts_absent_execution_stream_for_exact_zero_action_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    del reader.streams["executions"]
    terminal = reader.streams["events"][0]
    terminal["step_index"] = 0
    calibration = terminal["payload"]["calibration"]  # type: ignore[index]
    calibration["actions_executed"] = 0  # type: ignore[index]
    calibration["frames_executed"] = 0  # type: ignore[index]
    calibration["semantic_state_changed"] = False  # type: ignore[index]
    calibration["status"] = "failed"  # type: ignore[index]
    dataset = _dataset()
    object.__setattr__(
        dataset.examples[0],
        "outcome_status",
        GoalDecisionOutcome.FAILED,
    )
    result = _admit(monkeypatch, reader, dataset=dataset)

    assert result.status is GoalDecisionOutcome.FAILED
    assert result.reward == -1.0
    assert result.actions_executed == 0
    assert result.frames_executed == 0


def test_admission_rejects_absent_execution_stream_for_nonzero_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    del reader.streams["executions"]

    with pytest.raises(MultiGoalCalibrationAdmissionError, match="accounting"):
        _admit(monkeypatch, reader)


def test_admission_rejects_a_forged_controller_decision_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    reader.streams["executions"][0]["decision_id"] = f"{EPISODE}:goal-manager:0"

    with pytest.raises(MultiGoalCalibrationAdmissionError, match="accounting"):
        _admit(monkeypatch, reader)


def test_admission_rejects_forged_collection_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    calibration = reader.streams["events"][0]["payload"]["calibration"]  # type: ignore[index]
    calibration["collection_after"]["specimen_ledger_sha256"] = "f" * 64  # type: ignore[index]

    with pytest.raises(MultiGoalCalibrationAdmissionError, match="collection differs"):
        _admit(monkeypatch, reader)


def test_admission_rejects_a_non_one_hot_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _dataset()
    example = dataset.examples[0]
    object.__setattr__(
        example,
        "behavior_candidate_probabilities",
        (0.0, 0.5, 0.5),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.multi_goal_calibration_admission.load_goal_manager_episode",
        lambda _reader: dataset,
    )
    question = example.question

    with pytest.raises(MultiGoalCalibrationAdmissionError, match="arm differs"):
        admit_multi_goal_calibration_episode(
            _reader(),
            expected_episode_id=EPISODE,
            expected_campaign_id=CAMPAIGN,
            expected_trial_claim_sha256=CLAIM,
            expected_execution_identity_sha256=EXECUTION,
            expected_root_lineage_id=ROOT,
            expected_context_catalog_sha256=CATALOG,
            expected_context_id=CONTEXT,
            expected_binding_manifest_sha256=BINDING,
            expected_state_sha256=STATE,
            expected_envelope_sha256=ENVELOPE,
            expected_question_sha256=question.ordered_policy_input_sha256,
            expected_policy_context_sha256=question.policy_context_sha256,
            expected_available_menu_sha256=question.available_menu_sha256,
            expected_selected_available_ordinal=0,
            expected_selected_goal_kind=GoalKind.ADVANCE_STORY,
            expected_source_commit=SOURCE,
            expected_trial_ordinal=0,
        )
