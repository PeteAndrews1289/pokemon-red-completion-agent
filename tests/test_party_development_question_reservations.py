from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

import pokemon_red_completion.party_development_question_reservations as reservation_module
from pokemon_red_completion.party_development_exclusion_audit import (
    PartyDevelopmentExclusionAuditError,
    audit_party_development_exclusions,
)
from pokemon_red_completion.party_development_inventory import (
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
    PartyDevelopmentInventoryMember,
)
from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentTeacherPrior,
)
from pokemon_red_completion.party_development_question_reservations import (
    PP_CONTEXT_MATERIALIZATION_PROTOCOL,
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
    PartyDevelopmentQuestionReservationError,
    PartyDevelopmentQuestionReservationPlan,
    pp_materialization_source_ready,
    refresh_party_development_question_reservations,
    reserve_party_development_questions,
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
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_party_development_pp_materialization import (
    RED_PP_MATERIALIZATION_EXECUTION_CONTRACT,
    RedPartyDevelopmentPpMaterializationError,
    RedPartyDevelopmentPpMaterializationPlan,
    RedPpMaterializationBounds,
    RedPpMaterializationSource,
    RedPpStartAdapter,
    freeze_red_party_development_pp_materialization_plan,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import GrindingArea
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _member(
    *, level: int, hp_bin: str, route: EvolutionRouteKind
) -> PartyDevelopmentInventoryMember:
    return PartyDevelopmentInventoryMember(
        level=level,
        hp_bin=hp_bin,
        pp_bin="high",
        status_present=False,
        trainable=True,
        evolution_routes=(route,),
        level_evolution_distance_bin=(
            "near" if route is EvolutionRouteKind.LEVEL else "none"
        ),
        registration_target_needed=route is EvolutionRouteKind.LEVEL,
        living_target_needed=route is EvolutionRouteKind.LEVEL,
        role_complete=route is EvolutionRouteKind.NONE,
    )


def _entry(
    *, checkpoint: str, partition: ScenarioPartition, index: int
) -> PartyDevelopmentInventoryEntry:
    members = (
        _member(
            level=20 + index,
            hp_bin="low" if index == 0 else "high",
            route=EvolutionRouteKind.LEVEL,
        ),
        _member(
            level=35 + index,
            hp_bin="middle" if index % 3 == 0 else "high",
            route=EvolutionRouteKind.NONE,
        ),
        _member(
            level=45 + index,
            hp_bin="high",
            route=EvolutionRouteKind.NONE,
        ),
    )
    return PartyDevelopmentInventoryEntry(
        checkpoint_id=checkpoint,
        partition=partition,
        state_sha256=_digest(f"{checkpoint}:state"),
        envelope_sha256=_digest(f"{checkpoint}:envelope"),
        controls_ready=True,
        battle_active=False,
        members=tuple(sorted(members, key=lambda item: item.semantic_tuple())),
        registration_owned_count=20 + index,
        registration_target_count=124,
        living_unique_count=18 + index,
        living_target_count=120,
        specimen_count=24 + index,
        role_coverage_count=1,
        role_target_count=6,
        storage_headroom=200 - index,
        goal_hints=tuple(PartyDevelopmentGoal),
    )


def _inventory() -> PartyDevelopmentCheckpointInventory:
    entries = [
        _entry(
            checkpoint=f"question-development-{index:02d}",
            partition=ScenarioPartition.DEVELOPMENT,
            index=index,
        )
        for index in range(8)
    ]
    entries.extend(
        _entry(
            checkpoint=f"question-train-{index:02d}",
            partition=ScenarioPartition.TRAIN,
            index=index,
        )
        for index in range(10)
    )
    entries.append(
        _entry(
            checkpoint="venue-support-root",
            partition=ScenarioPartition.TRAIN,
            index=10,
        )
    )
    return PartyDevelopmentCheckpointInventory(
        tuple(sorted(entries, key=lambda item: item.checkpoint_id))
    )


def _teacher_prior() -> PartyDevelopmentTeacherPrior:
    return PartyDevelopmentTeacherPrior(
        model_file_sha256="1" * 64,
        model_canonical_sha256="2" * 64,
        offline_evidence_sha256="3" * 64,
        training_root_lineage_ids=("teacher-train",),
        training_state_sha256=("4" * 64,),
        evaluation_root_lineage_ids=("teacher-development",),
        evaluation_state_sha256=("5" * 64,),
    )


def _venue_registry() -> PartyDevelopmentVenuePriorRegistry:
    venue = GrindingArea("private-route", 9, 15, measured_samples=30)
    evidence = VenuePriorEvidence(
        evidence_id="venue-prior-a",
        venue=venue,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract_sha256="c" * 64,
        operational_contract_sha256="d" * 64,
        source_compatibility_sha256="e" * 64,
        support_root_lineage_ids=("venue-support-root",),
        support_state_sha256=(
            _digest("venue-support-root:state"),
        ),
        outcome_receipt_sha256=("f" * 64,),
        reliability=VenuePriorUnitRatio(1, 1),
        expected_yield=VenuePriorUnitRatio(4, 5),
        matchup_safety=VenuePriorUnitRatio(9, 10),
        travel_cost=VenuePriorUnitRatio(1, 10),
        recovery_cost=VenuePriorUnitRatio(1, 5),
    )
    return PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="6" * 40,
        source_bundle_sha256="7" * 64,
        entries=(evidence,),
    )


def _two_venue_registry() -> PartyDevelopmentVenuePriorRegistry:
    previous = _venue_registry()
    second = VenuePriorEvidence(
        evidence_id="venue-prior-b",
        venue=GrindingArea("private-cave", 15, 21, measured_samples=30),
        source_commit="8" * 40,
        source_bundle_sha256="9" * 64,
        measurement_contract_sha256=(
            previous.entries[0].measurement_contract_sha256
        ),
        operational_contract_sha256="a" * 64,
        source_compatibility_sha256="b" * 64,
        support_root_lineage_ids=("venue-support-root-b",),
        support_state_sha256=("c" * 64,),
        outcome_receipt_sha256=("d" * 64,),
        reliability=VenuePriorUnitRatio(1, 1),
        expected_yield=VenuePriorUnitRatio(1, 1),
        matchup_safety=VenuePriorUnitRatio(1, 1),
        travel_cost=VenuePriorUnitRatio(1, 10),
        recovery_cost=VenuePriorUnitRatio(1, 10),
    )
    return PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="e" * 40,
        source_bundle_sha256="f" * 64,
        entries=(*previous.entries, second),
    )


def _plan() -> PartyDevelopmentQuestionReservationPlan:
    return reserve_party_development_questions(
        _inventory(),
        teacher_prior=_teacher_prior(),
        venue_prior_registry=_venue_registry(),
    )


def test_reservation_plan_freezes_exact_diverse_8_plus_6_sources() -> None:
    plan = _plan()
    summary = plan.public_summary()

    assert summary["partition_counts"] == {"development": 6, "train": 8}
    assert summary["choice_kind_partition_counts"] == {
        "development:trainee": 3,
        "development:venue": 3,
        "train:trainee": 4,
        "train:venue": 4,
    }
    assert summary["source_health_bins"] == {
        "development": ["high", "low", "middle"],
        "train": ["high", "low", "middle"],
    }
    assert summary["source_pp_bins"] == {
        "development": ["high"],
        "train": ["high"],
    }
    assert summary["prospective_pp_bins_after_materialization"] == {
        "development": ["high", "middle"],
        "train": ["high", "middle"],
    }
    assert summary["qualified_venue_priors"] == 1
    assert plan.catalog_freeze_ready is False
    assert plan.unresolved_blockers == (
        "concrete_red_candidate_bindings_not_frozen",
        "prospective_8_plus_6_catalog_not_frozen",
        "reserved_pp_contexts_not_materialized",
        "second_compatible_venue_prior_missing",
    )
    assert sum(
        item.preparation
        is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
        for item in plan.reservations
    ) == 2
    assert {item.kind for item in plan.reservations} == set(TrainingChoiceKind)
    assert "venue-support-root" not in {
        item.source_checkpoint_id for item in plan.reservations
    }
    assert len({item.source_state_sha256 for item in plan.reservations}) == 14


def test_private_plan_round_trip_keeps_every_counter_closed() -> None:
    plan = _plan()
    restored = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        plan.private_dict()
    )

    assert restored == plan
    assert restored.plan_sha256 == plan.plan_sha256
    assert restored.private_dict()["candidate_menus_frozen"] == 0
    assert restored.private_dict()["outcomes_opened"] == 0
    assert restored.private_dict()["controller_actions"] == 0


def test_public_summary_hides_reserved_roots_and_candidate_values() -> None:
    plan = _plan()
    encoded = json.dumps(plan.public_summary(), sort_keys=True)

    assert "question-train" not in encoded
    assert "question-development" not in encoded
    assert "venue-support-root" not in encoded
    assert '"source_checkpoint_id":' not in encoded
    assert '"features":' not in encoded
    assert "/Users/" not in encoded


def test_private_plan_rejects_counter_protocol_and_digest_drift() -> None:
    plan = _plan()

    counter_drift = plan.private_dict()
    counter_drift["controller_actions"] = 1
    with pytest.raises(
        PartyDevelopmentQuestionReservationError, match="provenance"
    ):
        PartyDevelopmentQuestionReservationPlan.from_private_dict(counter_drift)

    protocol_drift = plan.private_dict()
    protocol = dict(PP_CONTEXT_MATERIALIZATION_PROTOCOL)
    protocol["deterministic_stop"] = "after_any_battle"
    protocol_drift["pp_materialization_protocol"] = protocol
    with pytest.raises(
        PartyDevelopmentQuestionReservationError, match="provenance"
    ):
        PartyDevelopmentQuestionReservationPlan.from_private_dict(protocol_drift)

    digest_drift = plan.private_dict()
    digest_drift["inventory_sha256"] = "9" * 64
    with pytest.raises(PartyDevelopmentQuestionReservationError, match="digest differs"):
        PartyDevelopmentQuestionReservationPlan.from_private_dict(digest_drift)


def test_plan_rejects_loss_of_pp_preparation_or_choice_kind() -> None:
    plan = _plan()
    prepared_index = next(
        index
        for index, item in enumerate(plan.reservations)
        if item.partition is ScenarioPartition.TRAIN
        and item.preparation
        is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    )
    without_preparation = list(plan.reservations)
    without_preparation[prepared_index] = replace(
        without_preparation[prepared_index],
        preparation=PartyDevelopmentContextPreparation.NONE,
        target_pp_bin=None,
    )
    with pytest.raises(PartyDevelopmentQuestionReservationError, match="PP diversity"):
        replace(plan, reservations=tuple(without_preparation))

    one_kind = tuple(
        replace(item, kind=TrainingChoiceKind.TRAINEE)
        if item.partition is ScenarioPartition.DEVELOPMENT
        else item
        for item in plan.reservations
    )
    with pytest.raises(PartyDevelopmentQuestionReservationError, match="choice kind"):
        replace(plan, reservations=one_kind)


def test_materialization_protocol_forbids_labels_predictions_and_memory_edits() -> None:
    forbidden = set(PP_CONTEXT_MATERIALIZATION_PROTOCOL["forbidden_operations"])

    assert {
        "candidate_outcome_measurement",
        "direct_memory_edit",
        "model_fit",
        "model_prediction",
        "sealed_context_access",
        "teacher_query",
    } <= forbidden
    assert PP_CONTEXT_MATERIALIZATION_PROTOCOL["deterministic_stop"] == (
        "first_post_battle_middle_pp_bin"
    )
    assert PP_CONTEXT_MATERIALIZATION_PROTOCOL["replacement_policy"] == (
        "never_replace_an_exposed_or_failed_identity"
    )


def test_pp_materialization_sources_start_healthy_high_hp_and_high_pp() -> None:
    inventory = _inventory()
    entries = {item.checkpoint_id: item for item in inventory.entries}
    plan = _plan()

    prepared = tuple(
        entries[item.source_checkpoint_id]
        for item in plan.reservations
        if item.preparation
        is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    )

    assert len(prepared) == 2
    assert all(pp_materialization_source_ready(item) for item in prepared)
    unsafe = replace(
        prepared[0],
        members=tuple(
            sorted(
                (
                    replace(prepared[0].members[0], status_present=True),
                    *prepared[0].members[1:],
                ),
                key=lambda item: item.semantic_tuple(),
            )
        ),
    )
    assert pp_materialization_source_ready(unsafe) is False
    assert reservation_module._pp_materialization_source_health_only_unsafe(
        unsafe
    )
    pp_unsafe = replace(
        prepared[0],
        members=tuple(
            sorted(
                (
                    replace(prepared[0].members[0], pp_bin="middle"),
                    *prepared[0].members[1:],
                ),
                key=lambda item: item.semantic_tuple(),
            )
        ),
    )
    assert not reservation_module._pp_materialization_source_health_only_unsafe(
        pp_unsafe
    )


def test_refresh_retires_only_the_unsafe_unexecuted_pp_source() -> None:
    original_inventory = _inventory()
    previous_plan = _plan()
    prepared = next(
        item
        for item in previous_plan.reservations
        if item.partition is ScenarioPartition.DEVELOPMENT
        and item.preparation
        is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    )
    entries = []
    for entry in original_inventory.entries:
        if entry.checkpoint_id != prepared.source_checkpoint_id:
            entries.append(entry)
            continue
        entries.append(
            replace(
                entry,
                members=tuple(
                    sorted(
                        (
                            replace(entry.members[0], status_present=True),
                            *entry.members[1:],
                        ),
                        key=lambda item: item.semantic_tuple(),
                    )
                ),
            )
        )
    inventory = PartyDevelopmentCheckpointInventory(tuple(entries))
    unsafe_entry = next(
        item
        for item in inventory.entries
        if item.checkpoint_id == prepared.source_checkpoint_id
    )
    previous_plan = replace(
        previous_plan,
        inventory_sha256=inventory.inventory_sha256,
        reservations=tuple(
            replace(
                item,
                source_semantic_signature_sha256=(
                    unsafe_entry.semantic_signature_sha256
                ),
            )
            if item.scenario_id == prepared.scenario_id
            else item
            for item in previous_plan.reservations
        ),
    )

    refresh = refresh_party_development_question_reservations(
        inventory,
        teacher_prior=_teacher_prior(),
        previous_plan=previous_plan,
        previous_venue_prior_registry=_venue_registry(),
        venue_prior_registry=_two_venue_registry(),
    )

    assert refresh.retained_reservation_count == 13
    assert refresh.replaced_pp_preparation_count == 1
    assert refresh.plan.venue_prior_count == 2
    assert "second_compatible_venue_prior_missing" not in (
        refresh.plan.unresolved_blockers
    )
    before = {
        item.scenario_id: item for item in previous_plan.reservations
    }
    after = {item.scenario_id: item for item in refresh.plan.reservations}
    changed = tuple(
        scenario_id
        for scenario_id in sorted(before)
        if before[scenario_id].source_checkpoint_id
        != after[scenario_id].source_checkpoint_id
    )
    assert changed == (prepared.scenario_id,)
    assert pp_materialization_source_ready(
        next(
            item
            for item in inventory.entries
            if item.checkpoint_id == after[prepared.scenario_id].source_checkpoint_id
        )
    )
    encoded = json.dumps(refresh.public_summary(), sort_keys=True)
    assert prepared.source_checkpoint_id not in encoded
    assert "question-development" not in encoded
    assert "/Users/" not in encoded


def test_refresh_rejects_a_non_append_only_venue_registry() -> None:
    with pytest.raises(
        PartyDevelopmentQuestionReservationError,
        match="append-only venue prior",
    ):
        refresh_party_development_question_reservations(
            _inventory(),
            teacher_prior=_teacher_prior(),
            previous_plan=_plan(),
            previous_venue_prior_registry=_venue_registry(),
            venue_prior_registry=PartyDevelopmentVenuePriorRegistry.freeze(
                source_commit="e" * 40,
                source_bundle_sha256="f" * 64,
                entries=(_two_venue_registry().entries[1],),
            ),
        )


def _pp_materialization_source(
    reservation: PartyDevelopmentQuestionReservation,
    *,
    start_adapter: RedPpStartAdapter,
    output_capture_id: str,
) -> RedPpMaterializationSource:
    possible_species = (5, 48, 108)
    return RedPpMaterializationSource(
        scenario_id=reservation.scenario_id,
        partition=reservation.partition,
        source_checkpoint_id=reservation.source_checkpoint_id,
        source_state_sha256=reservation.source_state_sha256,
        source_envelope_sha256=reservation.source_envelope_sha256,
        source_semantic_signature_sha256=(
            reservation.source_semantic_signature_sha256
        ),
        source_root_lineage_id=f"root-{reservation.scenario_id}",
        source_boundary_sha256=_digest(
            f"boundary:{reservation.scenario_id}"
        ),
        protected_state_sha256=_digest(
            f"protected:{reservation.scenario_id}"
        ),
        start_adapter=start_adapter,
        target_party_slot=1,
        target_species_id=28,
        target_level=50,
        target_hp=100,
        target_max_hp=100,
        target_move_ids=(44, 39, 58, 57),
        target_initial_packed_pp=(25, 30, 10, 15),
        safe_move_slots=(1, 3, 4),
        current_total_pp=80,
        maximum_total_pp=80,
        middle_pp_ceiling=53,
        minimum_pp_consumption=27,
        safe_current_pp=50,
        target_has_evolution_route=False,
        venue_map_id=22,
        venue_binding_sha256="a" * 64,
        venue_maximum_wild_level=17,
        possible_wild_species_ids=possible_species,
        possible_wild_species_sha256=canonical_sha256(
            list(possible_species)
        ),
        all_possible_wild_species_seen=True,
        output_capture_id=output_capture_id,
    )


def _pp_materialization_plan() -> RedPartyDevelopmentPpMaterializationPlan:
    reservation_plan = reserve_party_development_questions(
        _inventory(),
        teacher_prior=_teacher_prior(),
        venue_prior_registry=_two_venue_registry(),
    )
    pp_reservations = tuple(
        item
        for item in reservation_plan.reservations
        if item.preparation
        is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    )
    adapters = {
        ScenarioPartition.TRAIN: (
            RedPpStartAdapter.CINNABAR_MART_CLERK_TO_ROUTE_11
        ),
        ScenarioPartition.DEVELOPMENT: (
            RedPpStartAdapter.CINNABAR_CENTER_PC_TO_ROUTE_11
        ),
    }
    sources = tuple(
        _pp_materialization_source(
            item,
            start_adapter=adapters[item.partition],
            output_capture_id=f"pp-output-{item.partition.value}",
        )
        for item in pp_reservations
    )
    return freeze_red_party_development_pp_materialization_plan(
        reservation_plan,
        sources=sources,
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        rom_sha256="3" * 64,
        inventory_file_sha256="4" * 64,
        reservation_plan_file_sha256="5" * 64,
        venue_prior_registry_file_sha256="6" * 64,
        context_catalog_sha256="7" * 64,
        context_catalog_file_sha256="8" * 64,
    )


def test_pp_materialization_plan_is_two_partition_path_free_and_round_trips() -> None:
    plan = _pp_materialization_plan()
    summary = plan.public_summary()

    assert summary["preparations_planned"] == 2
    assert summary["partition_counts"] == {"development": 1, "train": 1}
    assert summary["source_pp_bin"] == "high"
    assert summary["target_pp_bin"] == "middle"
    assert summary["safe_move_capacity_sufficient"] == 2
    assert summary["wild_species_seen_coverage_complete"] == 2
    assert summary["execution_authorized"] is False
    assert summary["controller_actions"] == 0
    encoded = json.dumps(summary, sort_keys=True)
    assert "pp-output" not in encoded
    assert "cinnabar" not in encoded.lower()
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert (
        RedPartyDevelopmentPpMaterializationPlan.from_private_dict(
            plan.private_dict()
        )
        == plan
    )


def test_pp_materialization_plan_rejects_bad_depletion_arithmetic() -> None:
    plan = _pp_materialization_plan()
    source = plan.entries[0]

    with pytest.raises(
        RedPartyDevelopmentPpMaterializationError,
        match="depletion arithmetic",
    ):
        replace(source, middle_pp_ceiling=54)


def test_pp_materialization_source_rederives_its_safe_slots_and_capacity() -> None:
    source = _pp_materialization_plan().entries[0]

    with pytest.raises(
        RedPartyDevelopmentPpMaterializationError,
        match="safe move slots",
    ):
        replace(source, safe_move_slots=(1, 4))
    with pytest.raises(
        RedPartyDevelopmentPpMaterializationError,
        match="depletion arithmetic",
    ):
        replace(source, safe_current_pp=49)


def test_pp_materialization_plan_rejects_mutable_bounds_or_adapter_collapse() -> None:
    plan = _pp_materialization_plan()

    with pytest.raises(
        RedPartyDevelopmentPpMaterializationError,
        match="plan contract",
    ):
        replace(
            plan,
            bounds=RedPpMaterializationBounds(maximum_completed_battles=28),
        )
    collapsed = tuple(
        replace(
            item,
            start_adapter=(
                RedPpStartAdapter.CINNABAR_CENTER_PC_TO_ROUTE_11
            ),
        )
        for item in plan.entries
    )
    with pytest.raises(
        RedPartyDevelopmentPpMaterializationError,
        match="frozen execution bounds",
    ):
        replace(plan, entries=collapsed)


def test_pp_materialization_contract_forbids_learning_healing_and_retry() -> None:
    forbidden_operations = RED_PP_MATERIALIZATION_EXECUTION_CONTRACT[
        "forbidden_operations"
    ]
    assert isinstance(forbidden_operations, list)
    forbidden = set(forbidden_operations)

    assert {
        "healing",
        "learner_candidate_construction",
        "learner_outcome_measurement",
        "model_prediction",
        "teacher_query",
    } <= forbidden
    assert (
        RED_PP_MATERIALIZATION_EXECUTION_CONTRACT[
            "retry_after_any_controller_input"
        ]
        is False
    )


def test_exclusion_audit_separates_canonical_roots_legacy_aliases_and_states() -> None:
    inventory = _inventory()
    plan = _plan()
    roots = {
        item.checkpoint_id: f"canonical-root-{index:02d}"
        for index, item in enumerate(inventory.entries)
    }

    audit = audit_party_development_exclusions(
        inventory,
        plan,
        root_lineage_by_checkpoint_id=roots,
    )
    counts = {
        partition.value: partition_counts
        for partition, partition_counts in audit.partition_counts
    }

    assert counts["development"].public_dict() == {
        "inventory_count": 8,
        "canonical_root_match_count": 0,
        "legacy_checkpoint_alias_match_count": 0,
        "state_digest_match_count": 0,
        "canonical_root_or_state_match_count": 0,
    }
    assert counts["train"].public_dict() == {
        "inventory_count": 11,
        "canonical_root_match_count": 0,
        "legacy_checkpoint_alias_match_count": 1,
        "state_digest_match_count": 1,
        "canonical_root_or_state_match_count": 1,
    }
    assert audit.reserved_root_overlap_count == 0
    assert audit.reserved_state_overlap_count == 0
    assert audit.public_dict()["checkpoint_id_is_root_lineage_id"] is False
    assert "venue-support-root" not in json.dumps(audit.public_dict())


def test_exclusion_audit_rejects_reserved_prior_overlap() -> None:
    inventory = _inventory()
    plan = _plan()
    reserved_checkpoint = plan.reservations[0].source_checkpoint_id
    roots = {
        item.checkpoint_id: (
            "venue-support-root"
            if item.checkpoint_id == reserved_checkpoint
            else f"canonical-root-{index:02d}"
        )
        for index, item in enumerate(inventory.entries)
    }

    with pytest.raises(
        PartyDevelopmentExclusionAuditError,
        match="overlap prior evidence",
    ):
        audit_party_development_exclusions(
            inventory,
            plan,
            root_lineage_by_checkpoint_id=roots,
        )


def test_exclusion_audit_requires_an_exact_unique_root_mapping() -> None:
    inventory = _inventory()
    plan = _plan()
    incomplete_roots = {
        item.checkpoint_id: f"canonical-root-{index:02d}"
        for index, item in enumerate(inventory.entries[:-1])
    }

    with pytest.raises(
        PartyDevelopmentExclusionAuditError,
        match="one explicit unique root",
    ):
        audit_party_development_exclusions(
            inventory,
            plan,
            root_lineage_by_checkpoint_id=incomplete_roots,
        )
