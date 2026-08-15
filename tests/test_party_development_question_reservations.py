from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

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
    PartyDevelopmentQuestionReservationError,
    PartyDevelopmentQuestionReservationPlan,
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
