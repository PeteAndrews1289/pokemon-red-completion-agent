from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
    DependencyMultiplicity,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    ProspectiveRedCapabilityBinding,
    ProspectiveRedDualCapabilityScenario,
    RedDependencyCapabilityRole,
    RedDependencySpeciesBinding,
    RedDualCapabilityCurriculumError,
    red_dual_capability_curriculum_design,
    red_dual_capability_scenario_specs,
    verify_red_dual_capability_outcome,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = PROJECT_ROOT / "configs/red-dual-capability-dependency-curriculum-v1.json"
PRECURSOR = "pokemon:national:050"
EVOLVED = "pokemon:national:051"
UNRELATED = "pokemon:national:001"


def _ledger(**counts: int) -> DependencySpecimenLedger:
    mapping = {
        PRECURSOR: counts.get("precursor", 0),
        EVOLVED: counts.get("evolved", 0),
        UNRELATED: counts.get("unrelated", 0),
    }
    return DependencySpecimenLedger(
        tuple(sorted((species, count) for species, count in mapping.items() if count))
    )


def _binding() -> RedDependencySpeciesBinding:
    return RedDependencySpeciesBinding(PRECURSOR, EVOLVED)


def _capabilities(
    *,
    reset: str = "a" * 64,
) -> tuple[ProspectiveRedCapabilityBinding, ...]:
    return (
        ProspectiveRedCapabilityBinding(
            GoalKind.ACQUIRE_SPECIES,
            RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE,
            reset,
            "b" * 64,
            True,
        ),
        ProspectiveRedCapabilityBinding(
            GoalKind.EVOLVE_SPECIES,
            RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
            reset,
            "c" * 64,
            True,
        ),
    )


def test_design_is_canonical_title_neutral_and_has_no_teacher_action() -> None:
    design = red_dual_capability_curriculum_design()
    document = design.public_dict()
    scenarios = red_dual_capability_scenario_specs()

    assert document == {
        "schema": "pokemon.red.dual-capability-living-dex-curriculum-design.v1",
        "feature_schema": ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
        "candidate_count": 2,
        "candidate_order": ["acquire_species", "evolve_species"],
        "capabilities": [
            {
                "goal_kind": "acquire_species",
                "execution_role": "measured_venue_capture",
            },
            {
                "goal_kind": "evolve_species",
                "execution_role": "bounded_training_evolution",
            },
        ],
        "reset_contract": "restore_identical_authenticated_state_before_each_selected_action",
        "outcome_source": "independent_post_transition_living_collection_observation",
        "teacher_choice_fields": 0,
        "title_identity_fields_at_policy_boundary": 0,
        "route_identity_fields_at_policy_boundary": 0,
        "executable_binding_qualified": False,
    }
    assert [item.multiplicity for item in scenarios] == [
        DependencyMultiplicity.SCARCE,
        DependencyMultiplicity.DUPLICATE_READY,
    ]
    assert all(item.public_dict()["assigned_action"] is None for item in scenarios)
    encoded_rows = json.dumps([item.policy_rows() for item in scenarios], sort_keys=True)
    assert PRECURSOR not in encoded_rows
    assert EVOLVED not in encoded_rows
    assert "binding_sha256" not in encoded_rows
    assert "route" not in encoded_rows


def test_design_file_is_canonical_and_exposes_the_real_acquisition_gap() -> None:
    raw = DESIGN_PATH.read_bytes()
    document = json.loads(raw.decode("ascii"))

    assert raw == (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    capabilities = document["capability_contract"]["capabilities"]
    assert capabilities[0]["implementation_status"] == (
        "semantic_venue_entry_capture_adapter_required"
    )
    assert capabilities[1]["implementation_status"] == (
        "existing_provider_candidate_requires_scenario_binding"
    )
    assert document["capability_contract"]["existing_local_corridor_capture_is_sufficient"] is False
    assert document["stage_contract"]["prediction_or_execution_authorized"] is False
    assert set(document["counter_contract"].values()) == {0}
    encoded = raw.decode("ascii").lower()
    for forbidden in (
        "diglett",
        "dugtrio",
        "vermilion",
        '"map_id"',
        "forward_directions",
        "trainingvenue.heal_and_return",
        "/users/",
        "/volumes/",
    ):
        assert forbidden not in encoded


def test_future_binding_requires_two_distinct_offers_from_one_reset_state() -> None:
    scenario = red_dual_capability_scenario_specs()[0]
    capabilities = _capabilities()
    bound = ProspectiveRedDualCapabilityScenario(scenario, "d" * 64, capabilities)

    assert bound.policy_rows() == scenario.policy_rows()
    assert bound.public_dict()["same_reset_state"] is True
    assert bound.public_dict()["independently_available_capabilities"] == 2
    assert "d" * 64 not in json.dumps(bound.public_dict(), sort_keys=True)

    invalid_capability_sets = (
        capabilities[:1],
        tuple(reversed(capabilities)),
        (capabilities[0], replace(capabilities[1], reset_state_sha256="e" * 64)),
        (capabilities[0], replace(capabilities[1], mechanically_available=False)),
        (
            capabilities[0],
            replace(capabilities[1], skill_binding_sha256=capabilities[0].skill_binding_sha256),
        ),
    )
    for invalid in invalid_capability_sets:
        with pytest.raises(
            RedDualCapabilityCurriculumError,
            match="both independent capabilities",
        ):
            ProspectiveRedDualCapabilityScenario(scenario, "d" * 64, invalid)


def test_capability_roles_cannot_be_swapped_or_fabricated() -> None:
    with pytest.raises(
        RedDualCapabilityCurriculumError,
        match="kind and execution role differ",
    ):
        ProspectiveRedCapabilityBinding(
            GoalKind.ACQUIRE_SPECIES,
            RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
            "a" * 64,
            "b" * 64,
            True,
        )


def test_scarce_state_rewards_only_exact_retained_acquisition() -> None:
    scenario = red_dual_capability_scenario_specs()[0]
    before = _ledger(precursor=1, unrelated=1)
    acquired = verify_red_dual_capability_outcome(
        scenario,
        _binding(),
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        before_ledger=before,
        after_ledger=_ledger(precursor=2, unrelated=1),
    )
    evolved_last = verify_red_dual_capability_outcome(
        scenario,
        _binding(),
        selected_kind=GoalKind.EVOLVE_SPECIES,
        before_ledger=before,
        after_ledger=_ledger(evolved=1, unrelated=1),
    )

    assert acquired.reward == 1
    assert acquired.exact_selected_transition is True
    assert acquired.required_living_preserved is True
    assert acquired.dependency_distance_after == acquired.dependency_distance_before - 1
    assert evolved_last.reward == -1
    assert evolved_last.exact_selected_transition is True
    assert evolved_last.required_living_preserved is False


def test_duplicate_ready_state_rewards_only_exact_safe_evolution() -> None:
    scenario = red_dual_capability_scenario_specs()[1]
    before = _ledger(precursor=2, unrelated=1)
    evolved = verify_red_dual_capability_outcome(
        scenario,
        _binding(),
        selected_kind=GoalKind.EVOLVE_SPECIES,
        before_ledger=before,
        after_ledger=_ledger(precursor=1, evolved=1, unrelated=1),
    )
    acquired_again = verify_red_dual_capability_outcome(
        scenario,
        _binding(),
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        before_ledger=before,
        after_ledger=_ledger(precursor=3, unrelated=1),
    )

    assert evolved.reward == 1
    assert evolved.exact_selected_transition is True
    assert evolved.required_living_preserved is True
    assert acquired_again.reward == -1
    assert acquired_again.exact_selected_transition is True
    assert acquired_again.dependency_distance_after == acquired_again.dependency_distance_before


@pytest.mark.parametrize(
    ("selected_kind", "after"),
    (
        (GoalKind.ACQUIRE_SPECIES, _ledger(precursor=1, unrelated=2)),
        (GoalKind.EVOLVE_SPECIES, _ledger(precursor=1, unrelated=2)),
        (GoalKind.EVOLVE_SPECIES, _ledger(precursor=1, evolved=1)),
    ),
)
def test_irrelevant_capture_wrong_evolution_and_unrelated_loss_are_negative(
    selected_kind: GoalKind,
    after: DependencySpecimenLedger,
) -> None:
    scenario = red_dual_capability_scenario_specs()[1]
    outcome = verify_red_dual_capability_outcome(
        scenario,
        _binding(),
        selected_kind=selected_kind,
        before_ledger=_ledger(precursor=2, unrelated=1),
        after_ledger=after,
    )

    assert outcome.reward == -1
    assert not (outcome.exact_selected_transition and outcome.unrelated_species_preserved)


def test_interruption_remains_censored_and_public_result_contains_no_species() -> None:
    scenario = red_dual_capability_scenario_specs()[0]
    outcome = verify_red_dual_capability_outcome(
        scenario,
        _binding(),
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        before_ledger=_ledger(precursor=1, unrelated=1),
        after_ledger=None,
    )

    assert outcome.status == "interrupted"
    assert outcome.reward is None
    assert outcome.after_ledger is None
    public = json.dumps(outcome.public_dict(), sort_keys=True)
    assert PRECURSOR not in public
    assert EVOLVED not in public
    assert outcome.private_dict()["binding_sha256"] == _binding().binding_sha256


def test_observed_start_must_match_the_frozen_scenario_multiset() -> None:
    with pytest.raises(
        RedDualCapabilityCurriculumError,
        match="observed ledger differs from scenario start",
    ):
        verify_red_dual_capability_outcome(
            red_dual_capability_scenario_specs()[0],
            _binding(),
            selected_kind=GoalKind.ACQUIRE_SPECIES,
            before_ledger=_ledger(precursor=2),
            after_ledger=_ledger(precursor=3),
        )
