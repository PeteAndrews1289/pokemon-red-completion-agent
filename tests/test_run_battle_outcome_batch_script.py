from __future__ import annotations

import runpy
from types import SimpleNamespace

import numpy as np

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_learning import BattleTurnOutcome
from pokemon_red_completion.claim_first_admission import ClaimFirstRootPair
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/run_battle_outcome_batch.py")
BATCH_HELPERS = runpy.run_path("tests/test_battle_outcome_batch.py")
LEARNING_HELPERS = runpy.run_path("tests/test_battle_outcome_learning.py")


class Writer:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object], bool]] = []

    def append(
        self,
        stream: str,
        record: dict[str, object],
        *,
        durable: bool,
    ) -> None:
        self.events.append((stream, record, durable))


def _claim() -> ClaimFirstRootPair:
    return ClaimFirstRootPair(
        logical_root_sha256="1" * 64,
        physical_root_sha256="2" * 64,
        stage="battle-batch-train",
        execution_identity_sha256="3" * 64,
        plan_sha256="4" * 64,
        slot_sha256="5" * 64,
        runner_sha256="6" * 64,
        source_commit="a" * 40,
    )


def test_batch_collector_durably_claims_each_candidate_before_controller_input(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    candidate = BATCH_HELPERS["_candidate"](
        ScenarioPartition.TRAIN,
        "batch-run",
        basis_offset=0,
        supported_count=2,
    )
    features = LEARNING_HELPERS["_features"]()
    outcomes = (
        BattleTurnOutcome(
            move_executed=True,
            opponent_damage_fraction=0.2,
            player_damage_fraction=0.0,
            opponent_fainted=False,
            player_fainted=False,
            battle_exited=False,
            actions_executed=2,
            frames_executed=48,
        ),
        BattleTurnOutcome(
            move_executed=True,
            opponent_damage_fraction=0.8,
            player_damage_fraction=0.0,
            opponent_fainted=False,
            player_fainted=False,
            battle_exited=False,
            actions_executed=2,
            frames_executed=48,
        ),
        None,
    )
    prepared = SimpleNamespace(
        initial_observation_sha256="7" * 64,
        features=features,
    )
    collection = SimpleNamespace(
        initial_observation_sha256=prepared.initial_observation_sha256,
        example=SimpleNamespace(features=features),
        outcomes=outcomes,
        public_dict=lambda: {"schema": "synthetic-collection"},
    )
    writer = Writer()

    def collect(capture, **kwargs):  # type: ignore[no-untyped-def]
        del capture
        for index in (0, 1):
            kwargs["candidate_claim_sink"](index)
            assert writer.events[-1][0] == "candidate_claims"
            assert writer.events[-1][2]
            kwargs["outcome_sink"](index, outcomes[index])
        return collection

    monkeypatch.setitem(
        SCRIPT["_collect_claimed_capture"].__globals__,
        "collect_red_battle_outcome_example",
        collect,
    )

    result = SCRIPT["_collect_claimed_capture"](
        writer,
        freeze_sha256="8" * 64,
        ordinal=0,
        candidate=candidate,
        capture=object(),
        prepared=prepared,
        root_pair=_claim(),
        session_factory=lambda: None,
    )

    assert result is collection
    assert [item[0] for item in writer.events] == [
        "candidate_claims",
        "candidate_outcomes",
        "candidate_claims",
        "candidate_outcomes",
        "outcomes",
    ]
    assert all(item[2] for item in writer.events)


def test_development_commitment_contains_all_controls_and_no_outcomes() -> None:
    features = LEARNING_HELPERS["_features"]()
    base_model = LEARNING_HELPERS["_model"]()
    payload = base_model.to_dict()
    updated_model = MaskedMLPMoveRanker(
        feature_names=payload["feature_names"],
        feature_schema_id=payload["feature_schema_id"],
        input_weights=np.asarray(payload["input_weights"]),
        hidden_bias=np.asarray(payload["hidden_bias"]),
        output_weights=-np.asarray(payload["output_weights"]),
        output_bias=payload["output_bias"],
        training_seed=payload["training_seed"],
    )
    candidate = BATCH_HELPERS["_candidate"](
        ScenarioPartition.DEVELOPMENT,
        "commitment",
        basis_offset=0,
        supported_count=2,
    )
    prepared = SimpleNamespace(
        initial_observation_sha256="9" * 64,
        features=features,
    )

    commitment = SCRIPT["_prediction_commitment"](
        freeze_sha256="8" * 64,
        candidate=candidate,
        prepared=prepared,
        base_model=base_model,
        updated_model=updated_model,
    )

    assert commitment["development_outcomes_opened"] == 0
    assert set(commitment) >= {
        "base_candidate_index",
        "updated_candidate_index",
        "fixed_heuristic_candidate_index",
    }


def test_batch_artifact_and_root_claims_are_freeze_scoped() -> None:
    candidate = BATCH_HELPERS["_candidate"](
        ScenarioPartition.DEVELOPMENT,
        "root-claim",
        basis_offset=0,
    )
    pair = SCRIPT["_root_pair"](
        candidate.binding,
        freeze_sha256="8" * 64,
        execution_sha256="3" * 64,
        runner_sha256="6" * 64,
        source_commit="a" * 40,
    )

    assert pair.plan_sha256 == "8" * 64
    assert pair.stage == "battle-batch-development"
    assert pair.logical_root_sha256 == candidate.binding.logical_root_sha256
    assert pair.physical_root_sha256 == candidate.binding.physical_root_sha256
