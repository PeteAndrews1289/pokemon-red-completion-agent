from __future__ import annotations

import json
import runpy
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_outcome_clustered_curriculum import (
    BATTLE_OUTCOME_CONTRAST_CURRICULUM_SCHEMA,
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


def _contrast_curriculum():  # type: ignore[no-untyped-def]
    original = _curriculum()
    fresh = list(original.fresh_train)
    for index, basis_offset in ((0, 2), (2, 6)):
        prior = fresh[index]
        fresh[index] = _candidate(
            ScenarioPartition.TRAIN,
            f"contrast-train-{index}",
            basis_offset=basis_offset,
            supported_count=2,
            expected_map=prior.binding.expected_map,
            margin_stratum=prior.prior_margin_stratum,
            prior_model_sha256=original.original_prior_sha256,
            player_hp_ratio=prior.player_hp_ratio,
        )
    development = list(original.development)
    for index, basis_offset in ((1, 2), (3, 6)):
        prior = development[index]
        development[index] = _candidate(
            ScenarioPartition.DEVELOPMENT,
            f"contrast-development-{index}",
            basis_offset=basis_offset,
            supported_count=2,
            expected_map=prior.binding.expected_map,
            margin_stratum=prior.prior_margin_stratum,
            prior_model_sha256=original.original_prior_sha256,
            player_hp_ratio=prior.player_hp_ratio,
        )
    return build_battle_outcome_clustered_curriculum(
        curriculum_id="red-battle-contrast-integration-v2",
        retained_prefix=original.retained_prefix,
        prefix=original.prefix,
        fresh_train=fresh,
        development=development,
        claim_registry_sha256="1" * 64,
        train_catalog_sha256="2" * 64,
        development_catalog_sha256="3" * 64,
        policy_version="v2",
    )


def test_clustered_curriculum_is_canonical_and_action_free() -> None:
    curriculum = _curriculum()

    reopened = parse_battle_outcome_clustered_curriculum(
        curriculum.canonical_bytes()
    )

    assert reopened == curriculum
    assert battle_outcome_clustered_policy_sha256() == (
        "6b336685b35c08de090a31723863cf68a70a0c2aafde0ff45a6c4a9bd3c7c67b"
    )
    assert curriculum.curriculum_sha256 == (
        "e669b3cf71a7230e82938a2f4ab14e262a717483414eee79c7358a9659720246"
    )
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


def test_contrast_policy_accepts_mixed_two_and_three_action_contexts() -> None:
    curriculum = _contrast_curriculum()
    summary = curriculum.public_dict()["information_summary"]

    assert curriculum.schema == BATTLE_OUTCOME_CONTRAST_CURRICULUM_SCHEMA
    assert curriculum.policy_version == "v2"
    assert curriculum.policy_sha256 == battle_outcome_clustered_policy_sha256(
        version="v2"
    )
    assert summary["train_contrast_rows"] == 10  # type: ignore[index]
    assert summary["development_contrast_rows"] == 14  # type: ignore[index]
    assert summary["fresh_train_three_action_contexts"] == 3  # type: ignore[index]
    assert summary["development_three_action_contexts"] == 6  # type: ignore[index]
    assert summary["train_hidden_contrast_rank"] == 10  # type: ignore[index]
    assert summary["development_hidden_contrast_rank"] == 14  # type: ignore[index]
    assert (
        parse_battle_outcome_clustered_curriculum(curriculum.canonical_bytes())
        == curriculum
    )


def test_contrast_policy_does_not_rewrite_failed_v1_threshold() -> None:
    curriculum = _contrast_curriculum()

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="fresh train three-action coverage",
    ):
        replace(
            curriculum,
            policy_sha256=battle_outcome_clustered_policy_sha256(version="v1"),
        )


def test_contrast_policy_counts_multiway_fresh_contexts_not_prefix() -> None:
    curriculum = _contrast_curriculum()
    multiway_index = next(
        index
        for index, item in enumerate(curriculum.fresh_train)
        if item.binding.supported_candidate_count == 3
    )
    prior = curriculum.fresh_train[multiway_index]
    two_action = _candidate(
        ScenarioPartition.TRAIN,
        "contrast-third-two-action",
        basis_offset=4,
        supported_count=2,
        expected_map=prior.binding.expected_map,
        margin_stratum=prior.prior_margin_stratum,
        prior_model_sha256=curriculum.original_prior_sha256,
        player_hp_ratio=prior.player_hp_ratio,
    )

    with pytest.raises(
        BattleOutcomeClusteredCurriculumError,
        match="contrast fresh train three-action coverage",
    ):
        changed = list(curriculum.fresh_train)
        changed[multiway_index] = two_action
        replace(curriculum, fresh_train=tuple(changed))


def test_clustered_policy_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="version is unsupported"):
        battle_outcome_clustered_policy_sha256(version="v3")


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
