from __future__ import annotations

import json
import math

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DEPENDENCY_RANKER_FEATURE_NAMES,
    DependencyRankerModel,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    adapt_red_living_dex_dependencies,
)
from pokemon_red_completion.red_living_dex_dependency_shadow import (
    RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS,
    PreparedRedDependencyShadow,
    RedDependencyShadowCandidateKind,
    RedDependencyShadowStop,
    RedLivingDexDependencyShadowError,
    prepare_red_dependency_shadow,
    score_red_dependency_shadow,
)

DESIGN_SHA256 = "1" * 64
CONTEXT_SHA256 = "2" * 64
TRAIN_SHA256 = "3" * 64


def _observation(*species_and_levels: tuple[int, int]) -> CollectionObservation:
    specimens = tuple(
        LivingSpecimen(
            red_species_ref(species),
            level,
            CollectionLocation.BOX,
            slot_index=index,
        )
        for index, (species, level) in enumerate(species_and_levels)
    )
    return CollectionObservation(
        owned_species=frozenset(item.species_ref for item in specimens),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(len(specimens),),
        current_box_index=0,
        box_capacity=20,
    )


def _model(weights: tuple[float, ...]) -> DependencyRankerModel:
    return DependencyRankerModel(DEPENDENCY_RANKER_FEATURE_NAMES, weights, TRAIN_SHA256)


def _prepared(model: DependencyRankerModel) -> PreparedRedDependencyShadow:
    dratini = red_species_ref(147)
    result = adapt_red_living_dex_dependencies(
        _observation((147, 30), (148, 30)),
        execution_facts=RedDependencyExecutionFacts(acquirable_precursor_refs=frozenset({dratini})),
    )
    prepared = prepare_red_dependency_shadow(
        result,
        design_sha256=DESIGN_SHA256,
        model_sha256=model.model_sha256,
        context_identity_sha256=CONTEXT_SHA256,
    )
    assert isinstance(prepared, PreparedRedDependencyShadow)
    return prepared


def test_preparation_freezes_first_catalog_order_eligible_menu_before_scoring() -> None:
    model = _model((1.0, -1.0, 0.0, 0.0))
    dratini = red_species_ref(147)
    nidorina = red_species_ref(30)
    result = adapt_red_living_dex_dependencies(
        _observation((30, 30), (30, 30), (147, 30), (148, 30)),
        execution_facts=RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset({nidorina, dratini})
        ),
    )

    prepared = prepare_red_dependency_shadow(
        result,
        design_sha256=DESIGN_SHA256,
        model_sha256=model.model_sha256,
        context_identity_sha256=CONTEXT_SHA256,
    )

    assert isinstance(prepared, PreparedRedDependencyShadow)
    eligible = tuple(item for item in result.opportunities if item.execution_qualified)
    assert prepared.opportunity is eligible[0]
    assert prepared.selected_opportunity_ordinal == result.opportunities.index(eligible[0])
    assert prepared.candidate_rows == prepared.opportunity.policy_rows()
    assert prepared.private_dict()["model_predictions"] == 0


def test_shadow_scores_full_menu_as_one_prediction_and_computes_probability() -> None:
    model = _model((1.0, -1.0, 0.0, 0.0))
    decision = score_red_dependency_shadow(_prepared(model), model)

    assert decision.selected_candidate_kind is (RedDependencyShadowCandidateKind.ACQUIRE_PRECURSOR)
    assert decision.acquire_score == 1.0
    assert decision.transform_score == -1.0
    assert decision.score_margin == 2.0
    assert decision.selected_candidate_probability == pytest.approx(1.0 / (1.0 + math.exp(-2)))
    assert decision.public_dict() == {
        "status": "shadow_preference_recorded_zero_action",
        "candidate_count": 2,
        "selected_candidate_kind": "acquire_precursor",
        "selected_candidate_probability": decision.selected_candidate_probability,
        "score_margin": 2.0,
        "model_predictions": 1,
        "controller_actions": 0,
        "emulator_frames_advanced": 0,
        "teacher_queries": 0,
        "identity_fields_public": 0,
    }


def test_tie_breaks_to_lower_acquire_index() -> None:
    model = _model((0.0, 0.0, 0.0, 0.0))

    decision = score_red_dependency_shadow(_prepared(model), model)

    assert decision.selected_candidate_kind is (RedDependencyShadowCandidateKind.ACQUIRE_PRECURSOR)
    assert decision.selected_candidate_probability == 0.5
    assert decision.score_margin == 0.0


def test_transform_preference_reports_selected_probability_not_acquire_probability() -> None:
    model = _model((-1.0, 1.0, 0.0, 0.0))

    decision = score_red_dependency_shadow(_prepared(model), model)

    assert decision.selected_candidate_kind is (
        RedDependencyShadowCandidateKind.TRANSFORM_PRECURSOR
    )
    assert decision.selected_candidate_probability == pytest.approx(1.0 / (1.0 + math.exp(-2)))


def test_no_eligible_opportunity_stops_without_model_score_or_identity_disclosure() -> None:
    model = _model((1.0, -1.0, 0.0, 0.0))
    result = adapt_red_living_dex_dependencies(_observation((147, 30), (148, 30)))

    stopped = prepare_red_dependency_shadow(
        result,
        design_sha256=DESIGN_SHA256,
        model_sha256=model.model_sha256,
        context_identity_sha256=CONTEXT_SHA256,
    )

    assert isinstance(stopped, RedDependencyShadowStop)
    public = stopped.public_dict()
    assert public["status"] == RED_LIVING_DEX_DEPENDENCY_SHADOW_NO_ELIGIBLE_STATUS
    assert public["model_predictions"] == 0
    assert public["controller_actions"] == 0
    assert public["emulator_frames_advanced"] == 0
    assert public["identity_fields_public"] == 0
    encoded = json.dumps(public, sort_keys=True)
    assert "pokemon:red" not in encoded
    assert CONTEXT_SHA256 not in encoded


def test_exact_skill_pair_filter_can_close_mechanically_ready_opportunity() -> None:
    model = _model((1.0, -1.0, 0.0, 0.0))
    dratini = red_species_ref(147)
    result = adapt_red_living_dex_dependencies(
        _observation((147, 30), (148, 30)),
        execution_facts=RedDependencyExecutionFacts(acquirable_precursor_refs=frozenset({dratini})),
    )

    stopped = prepare_red_dependency_shadow(
        result,
        design_sha256=DESIGN_SHA256,
        model_sha256=model.model_sha256,
        context_identity_sha256=CONTEXT_SHA256,
        execution_capable_binding_sha256s=frozenset(),
    )

    assert isinstance(stopped, RedDependencyShadowStop)
    assert stopped.public_dict()["model_predictions"] == 0


def test_public_projection_is_exact_and_private_terminal_binds_frozen_inputs() -> None:
    model = _model((1.0, -1.0, 0.0, 0.0))
    prepared = _prepared(model)
    decision = score_red_dependency_shadow(prepared, model)

    assert set(decision.public_dict()) == {
        "status",
        "candidate_count",
        "selected_candidate_kind",
        "selected_candidate_probability",
        "score_margin",
        "model_predictions",
        "controller_actions",
        "emulator_frames_advanced",
        "teacher_queries",
        "identity_fields_public",
    }
    terminal = decision.private_terminal_dict()
    assert terminal["context_identity_sha256"] == CONTEXT_SHA256
    assert terminal["model_sha256"] == model.model_sha256
    assert terminal["candidate_rows"] == [dict(row) for row in prepared.candidate_rows]
    assert terminal["semantic_identity_sha256"] == prepared.semantic_identity_sha256


def test_scoring_rejects_a_different_model_before_score() -> None:
    expected = _model((1.0, -1.0, 0.0, 0.0))
    replacement = _model((-1.0, 1.0, 0.0, 0.0))

    with pytest.raises(RedLivingDexDependencyShadowError, match="model identity"):
        score_red_dependency_shadow(_prepared(expected), replacement)


def test_preparation_rejects_non_digest_context_identity() -> None:
    model = _model((1.0, -1.0, 0.0, 0.0))
    result = adapt_red_living_dex_dependencies(_observation())

    with pytest.raises(RedLivingDexDependencyShadowError, match="context identity"):
        prepare_red_dependency_shadow(
            result,
            design_sha256=DESIGN_SHA256,
            model_sha256=model.model_sha256,
            context_identity_sha256="private-path",
        )
