from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

import pytest

from pokemon_red_completion.goal_manager import GoalKind, GoalOpportunity
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_acquisition import RedAcquisitionKind
from pokemon_red_completion.red_full_pokedex import build_red_full_pokedex_inventory
from pokemon_red_completion.red_full_pokedex_goal_proposal import (
    RedFullPokedexGoalProposalError,
    propose_red_full_pokedex_goals,
)
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_MANAGER_CONFIG,
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
)


def _sha(document: object) -> str:
    return hashlib.sha256(
        (
            json.dumps(
                document,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    ).hexdigest()


def _spec(
    kind: GoalKind,
    mechanic: RedGoalMechanic,
    parameters: Mapping[str, object],
) -> RedGoalProviderSpec:
    digest = _sha(
        {
            "kind": kind.value,
            "mechanic": mechanic.value,
            "parameters": dict(parameters),
        }
    )
    return RedGoalProviderSpec(kind, mechanic, parameters, digest)


def _profile(
    *,
    wild_source: str = "wild:ViridianForest:grass",
    evolution_source: str = "pokemon:national:007",
    evolution_target: str = "pokemon:national:008",
) -> RedGoalContextProfile:
    providers = (
        _spec(GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        _spec(
            GoalKind.ACQUIRE_SPECIES,
            RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
            {"source_id": wild_source},
        ),
        _spec(
            GoalKind.EVOLVE_SPECIES,
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
            {
                "source_species_ref": evolution_source,
                "target_species_ref": evolution_target,
                "evolution_level": 16,
            },
        ),
    )
    return RedGoalContextProfile(
        "full-pokedex-proposal-test",
        "a" * 64,
        RED_GOAL_MANAGER_CONFIG,
        providers,
    )


def _binding(profile: RedGoalContextProfile, spec: RedGoalProviderSpec) -> ExecutableGoalBinding:
    return ExecutableGoalBinding(
        binding_ref=(
            f"pokemon.red:semantic:{spec.kind.value}:"
            f"profile-{profile.profile_sha256}:config-{spec.configuration_sha256}"
        ),
        kind=spec.kind,
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=lambda: GoalExecutionReport(0, 0, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )


def _bindings(profile: RedGoalContextProfile) -> GoalBindingSet:
    bindings = tuple(_binding(profile, spec) for spec in profile.providers)
    opportunities: tuple[GoalOpportunity, ...] = tuple(
        binding.opportunity for binding in bindings
    )
    return GoalBindingSet(opportunities, bindings)


def _mixed_inventory(
    local: frozenset[int] = frozenset(),
    *,
    shared: frozenset[int] = frozenset(),
    physical: frozenset[int] = frozenset({7}),
):
    return build_red_full_pokedex_inventory(
        local,
        shared_registered_numbers=shared,
        physical_specimen_numbers=physical,
    )


def test_proposal_joins_missing_local_flags_to_two_executable_families() -> None:
    profile = _profile()
    proposal = propose_red_full_pokedex_goals(
        _mixed_inventory(), profile, _bindings(profile)
    )

    assert proposal.acquisition_family_count == 2
    assert tuple(candidate.acquisition_kind for candidate in proposal.candidates) == (
        RedAcquisitionKind.WILD,
        RedAcquisitionKind.EVOLUTION,
    )
    assert tuple(candidate.option_kind for candidate in proposal.candidates) == (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
    )
    assert proposal.candidates[0].target_numbers == (10, 11, 14, 25)
    assert proposal.candidates[1].target_numbers == (8,)


def test_public_proposal_is_action_free_and_contains_no_routing_identity() -> None:
    profile = _profile()
    proposal = propose_red_full_pokedex_goals(
        _mixed_inventory(), profile, _bindings(profile)
    )

    public = proposal.public_dict()
    assert public == {
        "schema": "pokemon.red.full-pokedex-goal-proposal.v1",
        "candidate_count": 2,
        "acquisition_family_count": 2,
        "portable_option_kinds": ["acquire", "evolve"],
        "all_executors_profile_bound": True,
        "completion_authority": "local_red_registration_flags",
        "identity_fields_public": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
    }
    encoded = json.dumps(public, sort_keys=True)
    for private_value in (
        profile.profile_sha256,
        "wild:ViridianForest:grass",
        "pokemon:national:008",
        "pokemon.red:semantic",
    ):
        assert private_value not in encoded


def test_shared_registration_does_not_remove_a_locally_missing_candidate() -> None:
    profile = _profile()
    proposal = propose_red_full_pokedex_goals(
        _mixed_inventory(shared=frozenset({8, 10})),
        profile,
        _bindings(profile),
    )

    assert proposal.candidates[0].target_numbers == (10, 11, 14, 25)
    assert proposal.candidates[1].target_numbers == (8,)


def test_gate_rejects_a_single_family_after_wild_targets_are_locally_complete() -> None:
    profile = _profile()

    with pytest.raises(RedFullPokedexGoalProposalError, match="at least two"):
        propose_red_full_pokedex_goals(
            _mixed_inventory(frozenset({10, 11, 14, 25})),
            profile,
            _bindings(profile),
        )


def test_gate_rejects_evolution_without_a_physical_precursor() -> None:
    profile = _profile()

    with pytest.raises(RedFullPokedexGoalProposalError, match="at least two"):
        propose_red_full_pokedex_goals(
            _mixed_inventory(physical=frozenset()), profile, _bindings(profile)
        )


def test_gate_rejects_binding_from_a_different_profile() -> None:
    profile = _profile()
    wrong_profile = RedGoalContextProfile(
        profile.profile_id,
        "b" * 64,
        profile.manager_config,
        profile.providers,
    )

    with pytest.raises(RedFullPokedexGoalProposalError, match="not authenticated"):
        propose_red_full_pokedex_goals(
            _mixed_inventory(), profile, _bindings(wrong_profile)
        )


def test_gate_rejects_a_wild_profile_bound_to_a_gift_source() -> None:
    profile = _profile(wild_source="gift:OakLab:Squirtle")

    with pytest.raises(RedFullPokedexGoalProposalError, match="different acquisition family"):
        propose_red_full_pokedex_goals(
            _mixed_inventory(), profile, _bindings(profile)
        )


def test_gate_rejects_evolution_identity_that_differs_from_the_catalog() -> None:
    profile = _profile(evolution_source="pokemon:national:004")

    with pytest.raises(RedFullPokedexGoalProposalError, match="pinned Red acquisition graph"):
        propose_red_full_pokedex_goals(
            _mixed_inventory(physical=frozenset({4})), profile, _bindings(profile)
        )
