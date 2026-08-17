from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
    summarize_collection,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.goal_manager_state import CompletionProgress, GoalStateEvidence
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
    PartyDevelopmentUnavailableReason,
)
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
)
from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorUnitRatio,
)
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    RedCollectionProgress,
    RedPokedexProgress,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_party import party_observation_from_raw
from pokemon_red_completion.red_party_development_adapter import (
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
    RedPartyDevelopmentAdapterError,
    RedPartyDevelopmentExecutionCapabilityError,
    RedPartyDevelopmentQuestionPreflight,
    _execution_capability_matrix,
    build_red_party_development_snapshot,
    preflight_red_party_development_question,
    red_party_completion_snapshot,
    red_vermilion_training_transition_available,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind
from pokemon_red_completion.training_venue import TrainingVenue

_CANONICAL_ROOT = "canonical-reserved-root"


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=15,
        player_x=10,
        player_y=12,
        party_count=3,
        battle_state=0,
        bag_item_ids=(),
        bag_items=(),
        party_species_ids=(0x3B, 0x1C, 0x40),
        party_levels=(22, 28, 24),
        party_hp=(50, 80, 70),
        party_max_hp=(60, 100, 80),
        party_status=(0, 0, 0),
        party_moves=((10, 91, 0, 0), (55, 57, 58, 0), (15, 19, 31, 0)),
        party_pp=((20, 10, 0, 0), (15, 10, 5, 0), (30, 20, 15, 0)),
    )


def _observation() -> RedGoalObservation:
    raw = _raw()
    party = party_observation_from_raw(raw)
    owned_numbers = tuple(
        sorted(red_internal_species_number(member.species_id) for member in party.members)
    )
    owned_refs = frozenset(red_species_ref(number) for number in owned_numbers)
    collection_observation = CollectionObservation(
        owned_species=owned_refs,
        specimens=tuple(
            LivingSpecimen(
                species_ref=red_species_ref(red_internal_species_number(member.species_id)),
                level=member.level,
                location=CollectionLocation.PARTY,
                slot_index=index,
            )
            for index, member in enumerate(party.members)
        ),
        party_size=party.size,
        party_limit=6,
        box_counts=(0,) * 12,
        current_box_index=0,
        box_capacity=20,
    )
    report = summarize_collection(
        RED_SOLO_COLLECTION_CONTRACT,
        collection_observation,
    )
    targets = tuple(
        int(species_ref.rsplit(":", 1)[1])
        for species_ref in RED_SOLO_COLLECTION_CONTRACT.target_species
    )
    missing = tuple(number for number in targets if number not in set(owned_numbers))
    pokedex = RedPokedexProgress(
        owned_target_numbers=owned_numbers,
        seen_target_numbers=owned_numbers,
        missing_target_numbers=missing,
        excluded_owned_numbers=(),
    )
    collection = RedCollectionProgress(
        pokedex=pokedex,
        collection=report,
        box_counts=(0,) * 12,
        current_box_index=0,
        storage_initialized=True,
    )
    evidence = GoalStateEvidence(
        story=CompletionProgress(1, 8),
        registered_collection=CompletionProgress(
            report.pokedex_owned_count,
            report.target_count,
        ),
        living_collection=CompletionProgress(
            report.living_count,
            report.living_target_count,
        ),
        level_collection=CompletionProgress(
            report.level_cap_count,
            report.living_target_count,
        ),
        team_readiness=0.25,
        evolution=CompletionProgress(0, 1),
        safety=1.0,
        resources=1.0,
        storage=1.0,
        control=1.0,
        world_knowledge=CompletionProgress(len(owned_numbers), report.target_count),
    )
    return RedGoalObservation(
        raw=raw,
        game_state=GameState(GameMode.OVERWORLD, location="private-boundary"),
        party=party,
        collection=collection,
        collection_observation=collection_observation,
        evidence=evidence,
        input_ready=True,
        capture_item_count=0,
        recovery_item_count=0,
        free_storage_slots=240,
        immediate_capture_slots=23,
    )


def _areas() -> tuple[GrindingArea, ...]:
    return (
        GrindingArea("private-route-a", 10, 15, measured_samples=50),
        GrindingArea("private-cave-b", 15, 20, measured_samples=40),
    )


def _evidence(venue: GrindingArea) -> VenuePriorEvidence:
    return VenuePriorEvidence(
        evidence_id="independent-route-prior",
        venue=venue,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract_sha256="0" * 64,
        operational_contract_sha256="6" * 64,
        source_compatibility_sha256="5" * 64,
        support_root_lineage_ids=("prior-root",),
        support_state_sha256=("c" * 64,),
        outcome_receipt_sha256=("f" * 64,),
        reliability=VenuePriorUnitRatio(9, 10),
        expected_yield=VenuePriorUnitRatio(3, 4),
        matchup_safety=VenuePriorUnitRatio(19, 20),
        travel_cost=VenuePriorUnitRatio(1, 4),
        recovery_cost=VenuePriorUnitRatio(1, 5),
    )


def _registry(*venues: GrindingArea) -> PartyDevelopmentVenuePriorRegistry:
    return PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        entries=tuple(_evidence(venue) for venue in venues),
    )


def _reservation(
    *,
    kind: TrainingChoiceKind = TrainingChoiceKind.TRAINEE,
    preparation: PartyDevelopmentContextPreparation = (PartyDevelopmentContextPreparation.NONE),
) -> PartyDevelopmentQuestionReservation:
    return PartyDevelopmentQuestionReservation(
        scenario_id="party-train-001",
        source_checkpoint_id="reserved-root",
        source_state_sha256="9" * 64,
        source_envelope_sha256="8" * 64,
        source_semantic_signature_sha256="7" * 64,
        partition=(
            ScenarioPartition.TRAIN
            if kind is TrainingChoiceKind.TRAINEE
            else ScenarioPartition.DEVELOPMENT
        ),
        kind=kind,
        goal=PartyDevelopmentGoal.EVOLUTION,
        preparation=preparation,
        target_pp_bin=(
            "middle"
            if preparation is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
            else None
        ),
        source_member_count=3,
        source_trainable_count=3,
        source_hp_bins=("high",),
        source_pp_bins=("high",),
        source_evolution_route_kinds=(EvolutionRouteKind.LEVEL,),
    )


def _evolutions() -> dict[int, tuple[Evolution, ...]]:
    return {
        50: (Evolution(50, 51, EvolutionMethod.LEVEL, 26),),
    }


def test_red_curriculum_policy_matches_the_reserved_balance_semantics() -> None:
    assert RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY.minimum_level == 60
    assert RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY.maximum_level_spread == 5
    assert RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY.required_size == 6
    assert RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY.max_faints == 0


def test_red_completion_snapshot_recomputes_collection_roles_evolution_and_deficit() -> None:
    snapshot = red_party_completion_snapshot(
        _observation(),
        evolutions=_evolutions(),
        policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
    )

    assert snapshot.registered_target_count == 3
    assert snapshot.living_target_count == 3
    assert snapshot.role_coverage_count == 2
    assert snapshot.role_target_total == 6
    assert snapshot.evolution_steps_remaining == 1
    assert snapshot.level_floor_deficit == 16


def test_red_completion_snapshot_requires_a_stable_boundary() -> None:
    observation = _observation()

    with pytest.raises(RedPartyDevelopmentAdapterError, match="stable ready"):
        red_party_completion_snapshot(
            replace(observation, raw=replace(observation.raw, battle_state=1)),
            evolutions=_evolutions(),
            policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
        )


def _snapshot(
    observation: RedGoalObservation | None = None,
):
    areas = _areas()
    return build_red_party_development_snapshot(
        _reservation(),
        source_root_lineage_id=_CANONICAL_ROOT,
        observation=observation or _observation(),
        evolutions=_evolutions(),
        policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
        areas=areas,
        venue_prior_registry=_registry(areas[0]),
        venue_operational_contract_sha256=("6" * 64, "6" * 64),
        source_commit="3" * 40,
        source_bundle_sha256="4" * 64,
    )


def test_red_snapshot_derives_completion_evolution_and_retention_semantics() -> None:
    snapshot = _snapshot()
    diglett = snapshot.member_profiles[0]

    assert diglett.evolution.required
    assert diglett.evolution.stages_remaining == 1
    assert diglett.evolution.route_kind is EvolutionRouteKind.LEVEL
    assert diglett.evolution.levels_to_next == 4
    assert diglett.evolution.feasible_now
    assert diglett.registration_needed
    assert diglett.living_target_needed
    assert diglett.living_retention_risk
    assert diglett.role_needed
    assert not diglett.role_complete
    assert snapshot.registration_owned_count == 3
    assert snapshot.living_unique_count == 3


def test_red_execution_capabilities_mask_dynamic_transition_and_move_failures() -> None:
    areas = _areas()
    base_observation = _observation()
    raw = replace(
        base_observation.raw,
        party_pp=((5, 5, 0, 0), (5, 5, 5, 0), (5, 5, 5, 0)),
    )
    observation = replace(
        base_observation,
        raw=raw,
        party=party_observation_from_raw(raw),
    )

    def no_op(*_args: object) -> None:
        return None

    venues = (
        TrainingVenue(
            band=areas[0],
            map_id=101,
            walk_to_grass=lambda *_args: 1,
            heal_and_return=no_op,
            is_in_center=lambda _raw: False,
            move_slot=lambda _raw: 1,
        ),
        TrainingVenue(
            band=areas[1],
            map_id=102,
            walk_to_grass=lambda *_args: 1,
            heal_and_return=no_op,
            is_in_center=lambda _raw: False,
            move_slot=lambda _raw: 1,
        ),
    )
    transition_guards = (
        lambda _raw, anchor: anchor == 5,
        lambda _raw, _anchor: False,
    )
    snapshot = build_red_party_development_snapshot(
        _reservation(),
        source_root_lineage_id=_CANONICAL_ROOT,
        observation=observation,
        evolutions=_evolutions(),
        policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
        areas=areas,
        venue_prior_registry=_registry(areas[0]),
        venue_operational_contract_sha256=("6" * 64, "6" * 64),
        source_commit="3" * 40,
        source_bundle_sha256="4" * 64,
        training_venues=venues,
        transition_guards=transition_guards,
        last_blackout_map=5,
    )

    menu = snapshot.trainee_menu(areas[0])

    assert menu is not None
    assert menu.candidate_available == (True, True, False)
    assert menu.candidate_unavailable_reasons == (
        None,
        None,
        PartyDevelopmentUnavailableReason.BATTLE_POLICY_INCOMPATIBLE,
    )
    assert all(
        profile.execution_capabilities_by_venue[1].unavailable_reason
        is PartyDevelopmentUnavailableReason.TRANSITION_UNAVAILABLE
        for profile in snapshot.member_profiles
    )

    unavailable_pp = replace(observation, raw=replace(raw, party_pp=None))
    with pytest.raises(RedPartyDevelopmentExecutionCapabilityError) as caught:
        _execution_capability_matrix(
            unavailable_pp,
            policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
            areas=areas,
            training_venues=venues,
            transition_guards=transition_guards,
            last_blackout_map=5,
        )
    assert caught.value.code == "packed_party_pp_unavailable"


def test_red_transition_guard_matches_existing_navigator_boundaries() -> None:
    route = RawGameState(True, MapId.ROUTE_11, 8, 4, 6, 0)
    known_center = RawGameState(True, MapId.CINNABAR_POKECENTER, 13, 4, 6, 0)
    wrong_center_boundary = replace(known_center, player_x=4, player_y=3)
    field_dig_source = RawGameState(True, MapId.POKEMON_MANSION_1F, 5, 27, 6, 0)

    assert red_vermilion_training_transition_available(
        route,
        int(MapId.CELADON_CITY),
    )
    assert red_vermilion_training_transition_available(
        known_center,
        int(MapId.CINNABAR_ISLAND),
    )
    assert not red_vermilion_training_transition_available(
        wrong_center_boundary,
        int(MapId.CINNABAR_ISLAND),
    )
    assert red_vermilion_training_transition_available(
        field_dig_source,
        int(MapId.SAFFRON_CITY),
    )
    assert not red_vermilion_training_transition_available(
        field_dig_source,
        int(MapId.CELADON_CITY),
    )
    cave_source = replace(field_dig_source, map_id=MapId.DIGLETTS_CAVE)
    assert not red_vermilion_training_transition_available(cave_source, 0)
    assert red_vermilion_training_transition_available(
        cave_source,
        int(MapId.VERMILION_CITY),
    )
    assert not red_vermilion_training_transition_available(
        replace(route, battle_state=1),
        int(MapId.VERMILION_CITY),
    )


def test_red_preflight_freezes_identity_free_actionless_trainee_menu() -> None:
    observation = _observation()
    areas = _areas()
    preflight = preflight_red_party_development_question(
        _reservation(),
        source_root_lineage_id=_CANONICAL_ROOT,
        observation=observation,
        evolutions=_evolutions(),
        policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
        areas=areas,
        venue_prior_registry=_registry(areas[0]),
        venue_operational_contract_sha256=("6" * 64, "6" * 64),
        source_commit="3" * 40,
        source_bundle_sha256="4" * 64,
        shared_venue=areas[0],
    )

    public = preflight.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["candidate_count"] == 3
    assert public["available_candidate_count"] == 3
    assert public["ready_to_freeze"] is True
    assert public["actions_executed"] == 0
    assert public["teacher_queries"] == 0
    assert public["model_predictions"] == 0
    assert public["outcomes_opened"] == 0
    assert preflight.binding.root_lineage_id == _CANONICAL_ROOT
    assert preflight.binding.root_lineage_id != preflight.reservation.source_checkpoint_id
    assert "private-route-a" not in encoded
    assert "private-cave-b" not in encoded
    assert "species_id" not in encoded
    assert "reserved-root" not in encoded


def test_red_preflight_rejects_same_shape_binding_from_another_menu() -> None:
    areas = _areas()
    snapshot = _snapshot()
    menu = snapshot.trainee_menu(areas[0])
    assert menu is not None
    expected = snapshot.freeze_binding(menu, scenario_id="party-train-001")
    changed_candidates = replace(
        menu.candidate_set,
        candidates=(
            replace(
                menu.candidate_set.candidates[0],
                features=menu.candidate_set.candidates[0].features[:2]
                + (menu.candidate_set.candidates[0].features[2] + 0.01,)
                + menu.candidate_set.candidates[0].features[3:],
            ),
            *menu.candidate_set.candidates[1:],
        ),
    )
    swapped = PartyDevelopmentProspectiveBinding.build(
        scenario_id=expected.scenario_id,
        root_lineage_id=expected.root_lineage_id,
        initial_state_sha256=expected.initial_state_sha256,
        partition=expected.partition,
        source_commit=expected.source_commit,
        source_bundle_sha256=expected.source_bundle_sha256,
        semantic_snapshot_sha256=expected.semantic_snapshot_sha256,
        candidate_set=changed_candidates,
        venue_priors=menu.venue_priors,
        venue_prior_registry_sha256=expected.venue_prior_registry_sha256,
        outcome_objective_sha256=expected.outcome_objective_sha256,
        shared_venue_prior=menu.shared_venue_prior,
        candidate_available=menu.candidate_available,
        candidate_unavailable_reasons=menu.candidate_unavailable_reasons,
    )

    with pytest.raises(
        RedPartyDevelopmentAdapterError,
        match="differs from its reserved question",
    ):
        RedPartyDevelopmentQuestionPreflight(
            reservation=_reservation(),
            source_root_lineage_id=_CANONICAL_ROOT,
            snapshot=snapshot,
            menu=menu,
            binding=swapped,
        )


def test_red_preflight_rejects_checkpoint_alias_as_canonical_root() -> None:
    snapshot = _snapshot()
    menu = snapshot.trainee_menu(snapshot.areas[0])
    assert menu is not None
    binding = snapshot.freeze_binding(menu, scenario_id="party-train-001")

    with pytest.raises(
        RedPartyDevelopmentAdapterError,
        match="differs from its reserved question",
    ):
        RedPartyDevelopmentQuestionPreflight(
            reservation=_reservation(),
            source_root_lineage_id=_reservation().source_checkpoint_id,
            snapshot=snapshot,
            menu=menu,
            binding=binding,
        )


def test_semantic_state_mutation_changes_snapshot_and_menu_digests() -> None:
    original = _snapshot()
    observation = _observation()
    mutated_raw = replace(
        observation.raw,
        party_levels=(23, 28, 24),
    )
    mutated_party = party_observation_from_raw(mutated_raw)
    specimens = tuple(
        replace(specimen, level=23)
        if specimen.location is CollectionLocation.PARTY and specimen.slot_index == 0
        else specimen
        for specimen in observation.collection_observation.specimens
    )
    mutated_collection_observation = replace(
        observation.collection_observation,
        specimens=specimens,
    )
    mutated_report = summarize_collection(
        RED_SOLO_COLLECTION_CONTRACT,
        mutated_collection_observation,
    )
    mutated = replace(
        observation,
        raw=mutated_raw,
        party=mutated_party,
        collection_observation=mutated_collection_observation,
        collection=replace(observation.collection, collection=mutated_report),
    )
    changed = _snapshot(mutated)

    original_menu = original.trainee_menu(original.areas[0])
    changed_menu = changed.trainee_menu(changed.areas[0])
    assert original_menu is not None
    assert changed_menu is not None
    assert original.semantic_snapshot_sha256 != changed.semantic_snapshot_sha256
    assert (
        original.freeze_binding(original_menu, scenario_id="party-train-001").candidate_menu_sha256
        != changed.freeze_binding(changed_menu, scenario_id="party-train-001").candidate_menu_sha256
    )


def test_red_snapshot_rejects_raw_and_semantic_party_drift() -> None:
    observation = _observation()
    changed_first = replace(observation.party.members[0], hp=49)
    drifted = replace(
        observation,
        party=PartyObservation((changed_first, *observation.party.members[1:])),
    )

    with pytest.raises(RedPartyDevelopmentAdapterError, match="party observations differ"):
        _snapshot(drifted)


def test_pp_preparation_requires_a_new_authenticated_reservation() -> None:
    areas = _areas()
    with pytest.raises(
        RedPartyDevelopmentAdapterError,
        match="newly authenticated post-materialization reservation",
    ):
        build_red_party_development_snapshot(
            _reservation(preparation=PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION),
            source_root_lineage_id=_CANONICAL_ROOT,
            observation=_observation(),
            evolutions=_evolutions(),
            policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
            areas=areas,
            venue_prior_registry=_registry(areas[0]),
            venue_operational_contract_sha256=("6" * 64, "6" * 64),
            source_commit="3" * 40,
            source_bundle_sha256="4" * 64,
        )


def test_venue_preflight_cannot_freeze_with_only_one_independent_prior() -> None:
    areas = _areas()
    with pytest.raises(
        RedPartyDevelopmentAdapterError,
        match="does not produce a multi-candidate question",
    ):
        preflight_red_party_development_question(
            _reservation(kind=TrainingChoiceKind.VENUE),
            source_root_lineage_id=_CANONICAL_ROOT,
            observation=_observation(),
            evolutions=_evolutions(),
            policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
            areas=areas,
            venue_prior_registry=_registry(areas[0]),
            venue_operational_contract_sha256=("6" * 64, "6" * 64),
            source_commit="3" * 40,
            source_bundle_sha256="4" * 64,
            fixed_trainee=_observation().party.members[0],
        )
