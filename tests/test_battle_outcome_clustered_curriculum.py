from __future__ import annotations

import json
import runpy
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_outcome_clustered_curriculum import (
    DEVELOPMENT_CONTEXTS,
    FRESH_TRAIN_CONTEXTS,
    BattleOutcomeClusteredCurriculumError,
    battle_outcome_clustered_policy_sha256,
    build_battle_outcome_clustered_curriculum,
    parse_battle_outcome_clustered_curriculum,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

_HELPERS = runpy.run_path("tests/test_battle_outcome_batch.py")
_candidate = _HELPERS["_candidate"]
_roster = _HELPERS["_roster"]
_roster_inputs = _HELPERS["_roster_inputs"]


def _curriculum():  # type: ignore[no-untyped-def]
    prefix, screened = _roster_inputs()
    retained = _roster(prefix=prefix, screened=screened).retained_prefix
    train = tuple(
        item for item in screened if item.partition is ScenarioPartition.TRAIN
    )[:FRESH_TRAIN_CONTEXTS]
    development = tuple(
        item
        for item in screened
        if item.partition is ScenarioPartition.DEVELOPMENT
    )[:DEVELOPMENT_CONTEXTS]
    return build_battle_outcome_clustered_curriculum(
        curriculum_id="red-battle-clustered-integration-v1",
        retained_prefix=retained,
        prefix=prefix,
        fresh_train=train,
        development=development,
        claim_registry_sha256="1" * 64,
        train_catalog_sha256="2" * 64,
        development_catalog_sha256="3" * 64,
    )


def test_clustered_curriculum_is_canonical_and_action_free() -> None:
    curriculum = _curriculum()

    reopened = parse_battle_outcome_clustered_curriculum(
        curriculum.canonical_bytes()
    )

    assert reopened == curriculum
    assert reopened.curriculum_sha256 == curriculum.curriculum_sha256
    assert len(reopened.train) == 6
    assert len(reopened.fresh_train) == 5
    assert len(reopened.development) == 8
    assert reopened.public_dict()["protections"] == {
        "authority_promoted": False,
        "controller_actions": 0,
        "crystal_contexts_opened": 0,
        "development_outcomes_opened": 0,
        "full_game_replays": 0,
        "inferential_claim": False,
        "model_fits": 0,
        "predictions_computed": 0,
        "retained_prefix_reexecuted": False,
        "root_claims_created": 0,
        "sealed_red_cases_opened": 0,
        "teacher_choice_targets": 0,
        "teacher_queries": 0,
        "train_outcomes_opened": 0,
    }


def test_clustered_policy_equal_weights_upstream_contexts() -> None:
    curriculum = _curriculum()
    summary = curriculum.public_dict()["information_summary"]

    assert battle_outcome_clustered_policy_sha256() == curriculum.policy_sha256
    assert summary["train_example_weight"] == pytest.approx(1.0 / 6.0)  # type: ignore[index]
    assert summary["fresh_train_measured_action_arms"] == 15  # type: ignore[index]
    assert summary["train_hidden_contrast_rank"] == 12  # type: ignore[index]
    assert summary["train_required_hidden_contrast_rank"] == 12  # type: ignore[index]


def test_clustered_curriculum_rejects_denominator_change() -> None:
    curriculum = _curriculum()

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="fresh train denominator",
    ):
        replace(curriculum, fresh_train=curriculum.fresh_train[:-1])


def test_clustered_curriculum_requires_three_actions_in_every_fresh_context() -> None:
    curriculum = _curriculum()
    two_action = _candidate(
        ScenarioPartition.TRAIN,
        "two-action",
        basis_offset=2,
        supported_count=2,
        prior_model_sha256=curriculum.original_prior_sha256,
    )

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="fresh train three-action coverage",
    ):
        replace(
            curriculum,
            fresh_train=(two_action, *curriculum.fresh_train[1:]),
        )


def test_clustered_curriculum_rejects_cross_partition_observation_reuse() -> None:
    curriculum = _curriculum()
    reused = replace(
        curriculum.development[0],
        binding=replace(
            curriculum.development[0].binding,
            initial_observation_sha256=(
                curriculum.fresh_train[0].binding.initial_observation_sha256
            ),
        ),
    )

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="initial_observation_sha256",
    ):
        replace(
            curriculum,
            development=(reused, *curriculum.development[1:]),
        )


def test_clustered_curriculum_rejects_rank_collapse() -> None:
    curriculum = _curriculum()
    collapsed = tuple(
        replace(
            item,
            hidden_embeddings=curriculum.fresh_train[0].hidden_embeddings,
            binding=replace(
                item.binding,
                hidden_embedding_sha256=curriculum.fresh_train[
                    0
                ].binding.hidden_embedding_sha256,
            ),
        )
        for item in curriculum.fresh_train
    )

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="hidden contrast rank",
    ):
        replace(curriculum, fresh_train=collapsed)


def test_clustered_curriculum_parser_rejects_derived_summary_mutation() -> None:
    curriculum = _curriculum()
    document = json.loads(curriculum.canonical_bytes())
    document["information_summary"]["fresh_train_measured_action_arms"] += 1
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="not canonical",
    ):
        parse_battle_outcome_clustered_curriculum(payload)
