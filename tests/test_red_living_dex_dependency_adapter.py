from __future__ import annotations

import json

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.living_dex_dependency_curriculum import (
    ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
)
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyCandidateReadiness,
    RedDependencyExecutionFacts,
    RedDependencyOpportunityStatus,
    RedLivingDexDependencyAdapterResult,
    RedLivingDexDependencyOpportunity,
    adapt_red_living_dex_dependencies,
)


def _observation(*species_and_levels: tuple[int, int]) -> CollectionObservation:
    specimens = tuple(
        LivingSpecimen(
            red_species_ref(number),
            level,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=index,
        )
        for index, (number, level) in enumerate(species_and_levels)
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


def _edge(
    result: RedLivingDexDependencyAdapterResult,
    precursor: int,
    evolved: int,
) -> RedLivingDexDependencyOpportunity:
    opportunities = result.opportunities
    return next(
        item
        for item in opportunities
        if item.binding.precursor_species_ref == red_species_ref(precursor)
        and item.binding.evolved_species_ref == red_species_ref(evolved)
    )


def test_canonical_catalog_has_22_supported_and_four_zero_reserve_edges() -> None:
    result = adapt_red_living_dex_dependencies(_observation())

    assert len(result.opportunities) == 26
    assert len(result.rankable) == 22
    assert {
        (
            item.binding.precursor_species_ref,
            item.binding.evolved_species_ref,
        )
        for item in result.opportunities
        if item.status is RedDependencyOpportunityStatus.ZERO_RESERVE_UNSUPPORTED
    } == {
        (red_species_ref(7), red_species_ref(8)),
        (red_species_ref(8), red_species_ref(9)),
        (red_species_ref(133), red_species_ref(135)),
        (red_species_ref(138), red_species_ref(139)),
    }
    assert result.public_dict() == {
        "schema": "pokemon.red.living-dex-dependency-observation-adapter.v1",
        "transformation_edges": 26,
        "rankable_edges": 22,
        "execution_qualified_edges": 0,
        "status_counts": {
            "rankable": 22,
            "zero_precursor_reserve_outside_model_support": 4,
        },
        "policy_feature_schema": ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
        "model_predictions": 0,
        "controller_actions": 0,
        "private_binding_values_public": False,
        "species_identity_fields": 0,
        "source_identity_fields": 0,
        "item_identity_fields": 0,
        "route_identity_fields": 0,
    }


@pytest.mark.parametrize(
    ("dratini_count", "expected_surplus"),
    ((1, 0), (2, 1)),
)
def test_multistage_edge_maps_scarce_and_duplicate_ready_state(
    dratini_count: int,
    expected_surplus: int,
) -> None:
    observation = _observation(
        *((147, 30),) * dratini_count,
        (148, 30),
    )
    facts = RedDependencyExecutionFacts(acquirable_precursor_refs=frozenset({red_species_ref(147)}))

    opportunity = _edge(
        adapt_red_living_dex_dependencies(observation, execution_facts=facts),
        147,
        148,
    )

    assert opportunity.status is RedDependencyOpportunityStatus.RANKABLE
    assert opportunity.state is not None
    assert opportunity.state.precursor_count == dratini_count
    assert opportunity.state.evolved_count == 1
    assert opportunity.state.required_precursor_count == 1
    assert opportunity.state.required_evolved_count == 2
    assert opportunity.state.precursor_surplus == expected_surplus
    assert opportunity.candidate_readiness == (
        RedDependencyCandidateReadiness.AVAILABLE,
        RedDependencyCandidateReadiness.AVAILABLE,
    )
    assert opportunity.execution_qualified


def test_descendant_specimen_counts_as_progress_through_its_parent_edge() -> None:
    observation = _observation((148, 40), (149, 55))

    dratini_to_dragonair = _edge(
        adapt_red_living_dex_dependencies(observation),
        147,
        148,
    )

    assert dratini_to_dragonair.status is RedDependencyOpportunityStatus.COMPLETE
    assert not dratini_to_dragonair.shadow_rankable
    assert dratini_to_dragonair.policy_rows() == ()


def test_branch_reserves_a_precursor_until_the_sibling_transformation_is_fulfilled() -> None:
    missing_jynx = _observation((61, 40), (61, 40))
    retained_jynx = _observation((61, 40), (61, 40), (124, 30))

    before_sibling = _edge(adapt_red_living_dex_dependencies(missing_jynx), 61, 62)
    after_sibling = _edge(adapt_red_living_dex_dependencies(retained_jynx), 61, 62)

    assert before_sibling.state is not None
    assert after_sibling.state is not None
    assert before_sibling.state.required_precursor_count == 2
    assert before_sibling.state.precursor_surplus == 0
    assert after_sibling.state.required_precursor_count == 1
    assert after_sibling.state.precursor_surplus == 1


def test_item_and_trade_readiness_stay_outside_policy_rows() -> None:
    nidorina = red_species_ref(30)
    nidoqueen_method = RED_ACQUISITION_CATALOG.method_for(red_species_ref(31))
    assert nidoqueen_method.required_item_ref is not None
    observation = _observation((30, 30), (30, 30), (61, 40), (61, 40))

    blocked = _edge(
        adapt_red_living_dex_dependencies(
            observation,
            execution_facts=RedDependencyExecutionFacts(
                acquirable_precursor_refs=frozenset({nidorina, red_species_ref(61)}),
            ),
        ),
        30,
        31,
    )
    ready_result = adapt_red_living_dex_dependencies(
        observation,
        execution_facts=RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset({nidorina, red_species_ref(61)}),
            available_item_refs=frozenset({nidoqueen_method.required_item_ref}),
            trade_available=True,
        ),
    )
    ready = _edge(ready_result, 30, 31)
    trade = _edge(ready_result, 61, 124)

    assert blocked.candidate_readiness[1] is (
        RedDependencyCandidateReadiness.ITEM_REQUIREMENT_UNSATISFIED
    )
    assert ready.candidate_readiness == (
        RedDependencyCandidateReadiness.AVAILABLE,
        RedDependencyCandidateReadiness.AVAILABLE,
    )
    assert trade.candidate_readiness == (
        RedDependencyCandidateReadiness.AVAILABLE,
        RedDependencyCandidateReadiness.AVAILABLE,
    )
    encoded = json.dumps((*ready.policy_rows(), *trade.policy_rows()), sort_keys=True)
    assert "pokemon:national" not in encoded
    assert "pokemon:red" not in encoded
    assert "source_id" not in encoded
    assert "item" not in encoded


def test_level_readiness_requires_one_eligible_precursor_without_changing_features() -> None:
    precursor = red_species_ref(147)
    facts = RedDependencyExecutionFacts(acquirable_precursor_refs=frozenset({precursor}))
    underleveled = _edge(
        adapt_red_living_dex_dependencies(
            _observation((147, 29), (148, 30)),
            execution_facts=facts,
        ),
        147,
        148,
    )
    eligible = _edge(
        adapt_red_living_dex_dependencies(
            _observation((147, 30), (148, 30)),
            execution_facts=facts,
        ),
        147,
        148,
    )

    assert underleveled.candidate_readiness[1] is (
        RedDependencyCandidateReadiness.LEVEL_REQUIREMENT_UNSATISFIED
    )
    assert eligible.candidate_readiness[1] is RedDependencyCandidateReadiness.AVAILABLE
    assert underleveled.policy_rows() == eligible.policy_rows()


def test_policy_rows_are_exact_title_neutral_ranker_inputs() -> None:
    result = adapt_red_living_dex_dependencies(_observation((147, 30), (148, 30)))
    opportunity = _edge(result, 147, 148)

    assert opportunity.state is not None
    rows = opportunity.policy_rows()
    assert len(rows) == 2
    assert rows[0]["adds_precursor"] == 1
    assert rows[0]["consumes_precursor"] == 0
    assert rows[1]["adds_precursor"] == 0
    assert rows[1]["consumes_precursor"] == 1
    assert rows[0]["schema"] == ROOTLESS_DEPENDENCY_FEATURE_SCHEMA
    assert tuple(rows[0]) == tuple(rows[1])
    assert all(
        key
        not in {
            "species_ref",
            "precursor_species_ref",
            "evolved_species_ref",
            "source_id",
            "required_item_ref",
            "map_id",
            "route_id",
        }
        for key in rows[0]
    )


def test_projection_order_and_private_binding_identity_are_deterministic() -> None:
    first = adapt_red_living_dex_dependencies(_observation((147, 30), (148, 30)))
    second = adapt_red_living_dex_dependencies(_observation((147, 30), (148, 30)))

    assert tuple(item.binding.binding_sha256 for item in first.opportunities) == tuple(
        item.binding.binding_sha256 for item in second.opportunities
    )
    assert tuple(item.policy_rows() for item in first.opportunities) == tuple(
        item.policy_rows() for item in second.opportunities
    )


def test_completed_and_unsupported_edges_never_expose_policy_candidates() -> None:
    result = adapt_red_living_dex_dependencies(_observation((9, 50)))
    squirtle_to_wartortle = _edge(result, 7, 8)
    wartortle_to_blastoise = _edge(result, 8, 9)

    assert squirtle_to_wartortle.status is RedDependencyOpportunityStatus.COMPLETE
    assert wartortle_to_blastoise.status is RedDependencyOpportunityStatus.COMPLETE
    assert squirtle_to_wartortle.policy_rows() == ()
    assert wartortle_to_blastoise.policy_rows() == ()


def test_execution_facts_are_strictly_typed() -> None:
    with pytest.raises(TypeError, match="acquirable_precursor_refs"):
        RedDependencyExecutionFacts(acquirable_precursor_refs={red_species_ref(1)})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="trade_available"):
        RedDependencyExecutionFacts(trade_available=1)  # type: ignore[arg-type]
