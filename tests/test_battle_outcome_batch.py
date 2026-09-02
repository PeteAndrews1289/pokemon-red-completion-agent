from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_batch import (
    BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
    DEVELOPMENT_CONTEXTS,
    FRESH_TRAIN_CONTEXTS,
    BattleOutcomeBatchError,
    BattleOutcomeBatchFreeze,
    BattleOutcomeBatchRoster,
    BattleOutcomePressureCandidate,
    BattleOutcomePressureInventory,
    RetainedBattleOutcomePrefix,
    battle_outcome_fixed_heuristic_choice,
    battle_outcome_model_sha256,
    battle_outcome_pressure_policy_sha256,
    battle_outcome_source_cluster_sha256,
    build_battle_outcome_batch_freeze,
    build_battle_outcome_pressure_candidate,
    build_battle_outcome_pressure_inventory,
    build_retained_battle_outcome_prefix,
    parse_battle_outcome_batch_freeze,
    parse_battle_outcome_batch_roster,
    parse_battle_outcome_pressure_inventory,
    parse_retained_battle_outcome_prefix,
    reconstruct_retained_battle_outcome_example,
    revalidate_battle_outcome_pressure_candidate,
    select_battle_outcome_batch_roster,
    select_battle_outcome_batch_roster_from_inventory,
)
from pokemon_red_completion.battle_outcome_experiment import (
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentPlan,
    battle_outcome_hidden_menu_sha256,
    battle_outcome_menu_sha256,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAvailabilitySnapshot,
    ClaimFirstPairAvailability,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

_HIDDEN_WIDTH = 16


def _digest(marker: str, label: str) -> str:
    return hashlib.sha256(f"{marker}:{label}".encode()).hexdigest()


def _candidate(
    partition: ScenarioPartition,
    marker: str,
    *,
    basis_offset: int,
    claim_available: bool = True,
    expected_map: int = int(MapId.POKEMON_MANSION_1F),
    margin_stratum: int = 0,
    supported_count: int = 3,
    embeddings: tuple[tuple[float, ...], ...] | None = None,
    prior_model_sha256: str = "1" * 64,
    player_hp_ratio: float = 1.0,
    player_status_id: str = "none",
    player_type_ids: tuple[str, ...] = ("normal",),
) -> BattleOutcomePressureCandidate:
    if embeddings is None:
        rows = [[0.0] * _HIDDEN_WIDTH for _ in range(supported_count)]
        for row_index in range(1, supported_count):
            rows[row_index][(basis_offset + row_index - 1) % _HIDDEN_WIDTH] = 1.0
        embeddings = tuple(tuple(row) for row in rows)
    assignment = _digest(marker, "assignment")
    source_state = _digest(marker, "source-state")
    envelope = _digest(marker, "source-envelope")
    hidden_sha256 = canonical_sha256(
        {
            "embeddings": embeddings,
            "schema": "pokemon.red.battle-outcome-hidden-menu.v1",
        }
    )
    binding = BattleOutcomeCaptureBinding(
        partition=partition,
        capture_id=f"battle-{partition.value}-{marker}",
        manifest_sha256=_digest(marker, "manifest"),
        state_sha256=_digest(marker, "capture-state"),
        initial_observation_sha256=_digest(marker, "observation"),
        source_commit="a" * 40,
        source_state_sha256=source_state,
        source_slot_id=f"red-goal-v1-{partition.value}-{marker}",
        source_assignment_id=assignment,
        source_context_id=_digest(marker, "context"),
        source_envelope_sha256=envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=source_state,
            envelope_sha256=envelope,
        ),
        menu_sha256=_digest(marker, "menu"),
        supported_candidate_count=supported_count,
        distinct_candidate_vector_count=supported_count,
        hidden_embedding_sha256=hidden_sha256,
        distinct_hidden_embedding_count=supported_count,
        expected_map=expected_map,
        expected_battle_state=1,
    )
    second_score = {0: 0.99, 1: 0.90, 2: 0.70, 3: 0.20}[margin_stratum]
    return BattleOutcomePressureCandidate(
        binding=binding,
        prior_model_sha256=prior_model_sha256,
        source_cluster_sha256=battle_outcome_source_cluster_sha256(binding),
        player_level=42,
        opponent_level=40,
        player_hp_ratio=player_hp_ratio,
        opponent_hp_ratio=1.0,
        player_status_id=player_status_id,
        player_type_ids=player_type_ids,
        supported_candidate_indices=tuple(range(supported_count)),
        prior_scores=(1.0, second_score, *([0.0] * (supported_count - 2))),
        hidden_embeddings=embeddings,
        claim_available=claim_available,
    )


def _roster_inputs() -> tuple[
    BattleOutcomePressureCandidate,
    tuple[BattleOutcomePressureCandidate, ...],
]:
    prefix = _candidate(
        ScenarioPartition.TRAIN,
        "prefix",
        basis_offset=0,
        claim_available=False,
        margin_stratum=0,
    )
    train = tuple(
        _candidate(
            ScenarioPartition.TRAIN,
            f"train-{index:02d}",
            basis_offset=index * 2,
            expected_map=(
                int(MapId.VICTORY_ROAD_1F) if index % 2 else int(MapId.POKEMON_MANSION_1F)
            ),
            margin_stratum=2 if index % 2 else 0,
            player_hp_ratio=0.5 if index % 2 else 1.0,
        )
        for index in range(1, FRESH_TRAIN_CONTEXTS + 1)
    )
    development = tuple(
        _candidate(
            ScenarioPartition.DEVELOPMENT,
            f"development-{index:02d}",
            basis_offset=index * 2,
            expected_map=(
                int(MapId.VICTORY_ROAD_1F) if index % 2 else int(MapId.POKEMON_MANSION_1F)
            ),
            margin_stratum=2 if index % 2 else 0,
            player_hp_ratio=0.5 if index % 2 else 1.0,
        )
        for index in range(DEVELOPMENT_CONTEXTS)
    )
    return prefix, (*train, *development)


def _roster(
    *,
    prefix: BattleOutcomePressureCandidate | None = None,
    screened: tuple[BattleOutcomePressureCandidate, ...] | None = None,
    forbidden_consumed: tuple[BattleOutcomeCaptureBinding, ...] | None = None,
) -> BattleOutcomeBatchRoster:
    default_prefix, default_screened = _roster_inputs()
    selected_prefix = prefix or default_prefix
    consumed = forbidden_consumed or (
        _candidate(
            ScenarioPartition.DEVELOPMENT,
            "consumed-development",
            basis_offset=0,
            claim_available=False,
        ).binding,
    )
    retained = RetainedBattleOutcomePrefix(
        plan=BattleOutcomeExperimentPlan(
            experiment_id="red-battle-update-retained-v1",
            source_commit="a" * 40,
            source_bundle_sha256="2" * 64,
            runner_sha256="3" * 64,
            materializer_sha256="4" * 64,
            registry_source_commit="b" * 40,
            registry_source_bundle_sha256="6" * 64,
            registry_sha256="7" * 64,
            context_catalog_sha256="8" * 64,
            rom_sha256="9" * 64,
            runtime_identity_sha256="a" * 64,
            numpy_runtime_sha256="b" * 64,
            base_model_sha256="1" * 64,
            controller_timing_sha256="c" * 64,
            captures=(selected_prefix.binding, consumed[0]),
        ),
        artifact_manifest_sha256="3" * 64,
        train_record_sha256="4" * 64,
        train_supported_candidate_indices=(0, 1, 2),
    )
    return select_battle_outcome_batch_roster(
        roster_id="red-battle-outcome-batch-v2-001",
        retained_prefix=retained,
        claim_registry_sha256="5" * 64,
        prefix=selected_prefix,
        screened=screened or default_screened,
    )


def _inventory() -> BattleOutcomePressureInventory:
    prefix, screened = _roster_inputs()
    retained = _roster(prefix=prefix, screened=screened).retained_prefix
    observations = tuple(
        sorted(
            (
                ClaimFirstPairAvailability(
                    logical_root_sha256=binding.logical_root_sha256,
                    physical_root_sha256=binding.physical_root_sha256,
                    available=available,
                )
                for binding, available in (
                    (retained.train, False),
                    (retained.forbidden_development, False),
                    *((item.binding, True) for item in screened),
                )
            ),
            key=lambda item: (
                item.logical_root_sha256,
                item.physical_root_sha256,
            ),
        )
    )
    snapshot = ClaimFirstAvailabilitySnapshot(
        registry_state_sha256=_digest("inventory", "registry"),
        observations=observations,
    )
    return build_battle_outcome_pressure_inventory(
        retained_prefix=retained,
        claim_snapshot=snapshot,
        prefix=prefix,
        screened=screened,
    )


def _canonical(document: object) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _turn_outcome(
    *,
    opponent_damage: float,
    player_damage: float = 0.0,
    opponent_fainted: bool = False,
    player_fainted: bool = False,
) -> dict[str, object]:
    utility = (
        2.0 * float(opponent_fainted)
        - 2.0 * float(player_fainted)
        + opponent_damage
        - player_damage
    )
    return {
        "schema": "pokemon.core.battle.selected-turn-outcome.v2",
        "move_executed": True,
        "opponent_damage_fraction": opponent_damage,
        "player_damage_fraction": player_damage,
        "opponent_fainted": opponent_fainted,
        "player_fainted": player_fainted,
        "battle_exited": opponent_fainted or player_fainted,
        "actions_executed": 3,
        "frames_executed": 40,
        "pre_attack_frames": 10,
        "utility": utility,
    }


def _retained_train_record(plan: BattleOutcomeExperimentPlan) -> dict[str, object]:
    outcomes = [
        _turn_outcome(opponent_damage=0.4),
        _turn_outcome(opponent_damage=1.0, opponent_fainted=True),
        _turn_outcome(opponent_damage=0.2, player_damage=0.1),
    ]
    return {
        "record_type": "battle_outcome_collection",
        "split": "train",
        "collection": {
            "schema": "pokemon.red.battle.outcome-collection.v1",
            "capture_id": plan.train.capture_id,
            "manifest_sha256": plan.train.manifest_sha256,
            "root_lineage_id": plan.train.root_lineage_id,
            "partition": "train",
            "initial_state_sha256": plan.train.state_sha256,
            "initial_observation_sha256": (plan.train.initial_observation_sha256),
            "candidate_count": 3,
            "measured_candidate_count": 3,
            "outcomes": outcomes,
            "best_candidate_indices": [1],
            "learner_update_eligible": True,
            "counterfactual_pre_attack_frames": 10,
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
            "full_game_replays": 0,
            "private_path_fields": 0,
        },
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
    }


def test_batch_roster_round_trips_complete_outcome_blind_denominator() -> None:
    roster = _roster()

    restored = parse_battle_outcome_batch_roster(roster.canonical_bytes())

    assert restored == roster
    assert len(restored.fresh_train) == FRESH_TRAIN_CONTEXTS
    assert len(restored.development) == DEVELOPMENT_CONTEXTS
    assert restored.train_hidden_contrast_rank == _HIDDEN_WIDTH
    assert restored.development_hidden_contrast_rank == _HIDDEN_WIDTH
    assert restored.public_dict()["fixed_heuristic_id"] == (BATTLE_OUTCOME_FIXED_HEURISTIC_ID)
    assert restored.public_dict()["protections"] == {
        "authority_promoted": False,
        "crystal_contexts_opened": 0,
        "development_reused": False,
        "development_outcomes_opened": 0,
        "full_game_replays": 0,
        "inferential_claim": False,
        "model_fits": 0,
        "outcomes_opened": 0,
        "preferred_action_fields": 0,
        "replacement_slots": 0,
        "retained_prefix_reexecuted": False,
        "red_sealed_test_cases_opened": 0,
        "teacher_choice_fields": 0,
    }


def test_retained_prefix_joins_the_exact_v1_plan_and_train_record() -> None:
    plan = _roster().retained_prefix.plan
    record = _retained_train_record(plan)

    retained = build_retained_battle_outcome_prefix(
        plan,
        artifact_manifest_sha256="d" * 64,
        train_collection_record=record,
    )

    assert retained.plan == plan
    assert retained.train == plan.train
    assert retained.forbidden_development == plan.development
    assert retained.original_prior_sha256 == plan.base_model_sha256
    assert retained.train_supported_candidate_indices == (0, 1, 2)
    assert retained.train_record_sha256 == canonical_sha256(record)
    assert parse_retained_battle_outcome_prefix(retained.canonical_bytes()) == retained


def test_retained_prefix_parser_rejects_noncanonical_or_duplicate_fields() -> None:
    retained = _roster().retained_prefix
    indented = json.dumps(retained.public_dict(), indent=2).encode("ascii")
    with pytest.raises(BattleOutcomeBatchError, match="not canonical"):
        parse_retained_battle_outcome_prefix(indented)

    duplicate = retained.canonical_bytes().replace(
        b'{"artifact_manifest_sha256":',
        b'{"artifact_manifest_sha256":"d' + b"d" * 63 + b'","artifact_manifest_sha256":',
        1,
    )
    with pytest.raises(BattleOutcomeBatchError, match="not canonical"):
        parse_retained_battle_outcome_prefix(duplicate)


def test_retained_prefix_rejects_a_plan_record_mismatch() -> None:
    plan = _roster().retained_prefix.plan
    record = _retained_train_record(plan)
    collection = record["collection"]
    assert isinstance(collection, dict)
    collection["capture_id"] = "battle-train-forged"

    with pytest.raises(BattleOutcomeBatchError, match="collection differs"):
        build_retained_battle_outcome_prefix(
            plan,
            artifact_manifest_sha256="d" * 64,
            train_collection_record=record,
        )


def test_batch_selection_is_stable_under_inventory_reordering() -> None:
    prefix, screened = _roster_inputs()

    forward = _roster(prefix=prefix, screened=screened)
    reverse = _roster(prefix=prefix, screened=tuple(reversed(screened)))

    assert forward.canonical_bytes() == reverse.canonical_bytes()
    assert forward.roster_sha256 == reverse.roster_sha256


def test_atomic_pressure_inventory_round_trips_and_is_the_only_roster_input() -> None:
    inventory = _inventory()

    reopened = parse_battle_outcome_pressure_inventory(inventory.canonical_bytes())
    roster = select_battle_outcome_batch_roster_from_inventory(
        roster_id="red-battle-outcome-batch-v2-inventory",
        inventory=reopened,
    )

    assert reopened == inventory
    assert roster.claim_registry_sha256 == (inventory.claim_snapshot.registry_state_sha256)
    assert roster.screened_inventory_sha256 == (inventory.screened_inventory_sha256)
    assert roster.public_dict()["protections"]["outcomes_opened"] == 0


def test_atomic_batch_freeze_round_trips_inventory_and_selected_roster() -> None:
    freeze = build_battle_outcome_batch_freeze(
        roster_id="red-battle-outcome-batch-v2-freeze",
        consumer_source_commit="f" * 40,
        consumer_source_bundle_sha256="e" * 64,
        capture_catalog_sha256s=("d" * 64,),
        inventory=_inventory(),
    )

    reopened = parse_battle_outcome_batch_freeze(freeze.canonical_bytes())

    assert isinstance(reopened, BattleOutcomeBatchFreeze)
    assert reopened == freeze
    assert reopened.consumer_source_commit == "f" * 40
    assert reopened.consumer_source_bundle_sha256 == "e" * 64
    assert reopened.capture_catalog_sha256s == ("d" * 64,)
    assert reopened.public_dict()["protections"] == {
        "authority_promoted": False,
        "controller_actions": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "model_choice_predictions": 0,
        "model_fits": 0,
        "outcomes_opened": 0,
        "root_claims_created": 0,
        "sealed_red_cases_opened": 0,
        "teacher_choice_targets": 0,
        "teacher_queries": 0,
    }


def test_batch_freeze_rejects_a_roster_not_derived_from_its_inventory() -> None:
    inventory = _inventory()
    freeze = build_battle_outcome_batch_freeze(
        roster_id="red-battle-outcome-batch-v2-freeze",
        consumer_source_commit="f" * 40,
        consumer_source_bundle_sha256="e" * 64,
        capture_catalog_sha256s=("d" * 64,),
        inventory=inventory,
    )
    document = freeze.public_dict()
    roster = document["roster"]
    assert isinstance(roster, dict)
    roster["roster_id"] = "red-battle-outcome-batch-v2-forged"

    with pytest.raises(BattleOutcomeBatchError, match="canonical JSON"):
        parse_battle_outcome_batch_freeze(_canonical(document))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("consumer_source_commit", "0" * 39, "consumer source commit"),
        ("consumer_source_bundle_sha256", "0" * 63, "source bundle digest"),
        ("capture_catalog_sha256s", [], "capture catalogs differ"),
        (
            "capture_catalog_sha256s",
            ["d" * 64, "d" * 64],
            "capture catalogs differ",
        ),
    ),
)
def test_batch_freeze_rejects_consumer_or_catalog_provenance_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    freeze = build_battle_outcome_batch_freeze(
        roster_id="red-battle-outcome-batch-v2-freeze",
        consumer_source_commit="f" * 40,
        consumer_source_bundle_sha256="e" * 64,
        capture_catalog_sha256s=("d" * 64,),
        inventory=_inventory(),
    )
    document = freeze.public_dict()
    document[field] = value

    with pytest.raises(BattleOutcomeBatchError, match=message):
        parse_battle_outcome_batch_freeze(_canonical(document))


def test_pressure_inventory_rejects_availability_or_denominator_drift() -> None:
    inventory = _inventory()
    document = inventory.public_dict()
    snapshot = document["claim_snapshot"]
    assert isinstance(snapshot, dict)
    observations = snapshot["observations"]
    assert isinstance(observations, list)
    assert isinstance(observations[-1], dict)
    observations[-1]["available"] = not observations[-1]["available"]

    with pytest.raises(BattleOutcomeBatchError, match="claim availability"):
        parse_battle_outcome_pressure_inventory(_canonical(document))


def test_different_assignments_from_one_upstream_state_cannot_cross_partitions() -> None:
    prefix, screened = _roster_inputs()
    train = tuple(item for item in screened if item.partition is ScenarioPartition.TRAIN)
    development = tuple(
        item for item in screened if item.partition is ScenarioPartition.DEVELOPMENT
    )
    sibling_template = _candidate(
        ScenarioPartition.DEVELOPMENT,
        "a-rng-sibling-with-new-assignment",
        basis_offset=14,
        expected_map=int(MapId.VICTORY_ROAD_1F),
        margin_stratum=2,
        player_hp_ratio=0.5,
    )
    sibling_binding = replace(
        sibling_template.binding,
        source_state_sha256=train[0].binding.source_state_sha256,
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=train[0].binding.source_state_sha256,
            envelope_sha256=sibling_template.binding.source_envelope_sha256,
        ),
    )
    sibling = replace(
        sibling_template,
        binding=sibling_binding,
        source_cluster_sha256=battle_outcome_source_cluster_sha256(sibling_binding),
    )

    roster = _roster(
        prefix=prefix,
        screened=(*train, sibling, *development),
    )

    assert sibling.binding.root_lineage_id != train[0].binding.root_lineage_id
    assert sibling.binding.source_assignment_id != (train[0].binding.source_assignment_id)
    assert sibling.binding.state_sha256 != train[0].binding.state_sha256
    assert sibling.binding.menu_sha256 != train[0].binding.menu_sha256
    assert sibling.capture_id not in {item.capture_id for item in roster.development}


def test_pressure_policy_digest_binds_party_priority_and_repair_order() -> None:
    assert battle_outcome_pressure_policy_sha256() == (
        "d6562531ebb75318c327261a0358ad237e7a201db1b9e7fd8c9fcdaf3282131d"
    )


def test_batch_selector_repairs_a_feasible_two_venue_subset() -> None:
    prefix, screened = _roster_inputs()
    train = tuple(item for item in screened if item.partition is ScenarioPartition.TRAIN)
    original_development = tuple(
        item for item in screened if item.partition is ScenarioPartition.DEVELOPMENT
    )
    mansion_development = tuple(
        replace(
            item,
            binding=replace(
                item.binding,
                expected_map=int(MapId.POKEMON_MANSION_1F),
            ),
        )
        for item in original_development
    )
    replacements = tuple(
        _candidate(
            ScenarioPartition.DEVELOPMENT,
            f"z-venue-repair-{index}",
            basis_offset=index * 2,
            expected_map=int(MapId.VICTORY_ROAD_1F),
            margin_stratum=2 if index % 2 else 0,
            player_hp_ratio=0.5 if index % 2 else 1.0,
            embeddings=mansion_development[index].hidden_embeddings,
        )
        for index in range(2)
    )

    roster = _roster(
        prefix=prefix,
        screened=(*train, *mansion_development, *replacements),
    )

    selected = {item.capture_id for item in roster.development}
    assert {item.capture_id for item in replacements} <= selected
    assert roster.development_hidden_contrast_rank == _HIDDEN_WIDTH


def test_batch_selector_recovers_when_a_greedy_root_blocks_two_needed_rows() -> None:
    prefix, screened = _roster_inputs()
    train = tuple(item for item in screened if item.partition is ScenarioPartition.TRAIN)
    development = tuple(
        item for item in screened if item.partition is ScenarioPartition.DEVELOPMENT
    )
    trap_template = _candidate(
        ScenarioPartition.TRAIN,
        "a-independent-trap",
        basis_offset=2,
        expected_map=int(MapId.VICTORY_ROAD_1F),
        embeddings=train[0].hidden_embeddings,
    )
    first = train[0].binding
    second = train[1].binding
    trap_binding = replace(
        trap_template.binding,
        source_state_sha256=first.source_state_sha256,
        source_envelope_sha256=first.source_envelope_sha256,
        root_consumption_sha256=first.root_consumption_sha256,
        state_sha256=second.state_sha256,
    )
    trap = replace(trap_template, binding=trap_binding)

    roster = _roster(
        prefix=prefix,
        screened=(trap, *train, *development),
    )

    assert trap.capture_id not in {item.capture_id for item in roster.fresh_train}
    assert {item.capture_id for item in train} == {item.capture_id for item in roster.fresh_train}


def test_batch_never_reuses_the_consumed_v1_development_root() -> None:
    prefix, screened = _roster_inputs()
    old_development = next(
        item for item in screened if item.partition is ScenarioPartition.DEVELOPMENT
    )
    backup = _candidate(
        ScenarioPartition.DEVELOPMENT,
        "development-backup",
        basis_offset=0,
        expected_map=int(MapId.POKEMON_MANSION_1F),
        margin_stratum=0,
        player_hp_ratio=1.0,
        embeddings=old_development.hidden_embeddings,
    )

    roster = _roster(
        prefix=prefix,
        screened=(*screened, backup),
        forbidden_consumed=(old_development.binding,),
    )

    assert old_development.capture_id not in {item.capture_id for item in roster.development}
    assert dict(roster.exclusion_counts)["previously_consumed"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("development_outcomes_opened", 1),
        ("outcomes_opened", 1),
        ("model_fits", 1),
        ("retained_prefix_reexecuted", True),
        ("replacement_slots", 1),
    ),
)
def test_batch_parser_rejects_mutated_protections(
    field: str,
    value: object,
) -> None:
    document = _roster().public_dict()
    protections = document["protections"]
    assert isinstance(protections, dict)
    protections[field] = value

    with pytest.raises(BattleOutcomeBatchError, match="canonical"):
        parse_battle_outcome_batch_roster(_canonical(document))


def test_batch_parser_rejects_outcome_or_teacher_fields() -> None:
    document = _roster().public_dict()
    development = document["development"]
    assert isinstance(development, list)
    assert isinstance(development[0], dict)
    development[0]["outcome"] = "opened"

    with pytest.raises(BattleOutcomeBatchError, match="fields differ"):
        parse_battle_outcome_batch_roster(_canonical(document))


def test_batch_parser_rejects_a_mutated_nested_capture() -> None:
    document = _roster().public_dict()
    prefix = document["prefix"]
    assert isinstance(prefix, dict)
    binding = prefix["binding"]
    assert isinstance(binding, dict)
    binding["root_lineage_id"] = "red-goal-root-forged"

    with pytest.raises(BattleOutcomeBatchError, match="capture binding"):
        parse_battle_outcome_batch_roster(_canonical(document))


def test_batch_parser_rejects_a_nonreconciling_screened_denominator() -> None:
    document = _roster().public_dict()
    document["screened_candidate_count"] = 16

    with pytest.raises(BattleOutcomeBatchError, match="does not reconcile"):
        parse_battle_outcome_batch_roster(_canonical(document))


def test_batch_parser_rejects_a_retained_prior_plan_mismatch() -> None:
    document = _roster().public_dict()
    retained = document["retained_prefix"]
    assert isinstance(retained, dict)
    retained["original_prior_sha256"] = "f" * 64

    with pytest.raises(BattleOutcomeBatchError, match="protections differ"):
        parse_battle_outcome_batch_roster(_canonical(document))


def test_batch_parser_normalizes_huge_numeric_input() -> None:
    document = _roster().public_dict()
    development = document["development"]
    assert isinstance(development, list)
    first = development[0]
    assert isinstance(first, dict)
    scores = first["prior_scores"]
    assert isinstance(scores, list)
    scores[0] = 10**400

    with pytest.raises(BattleOutcomeBatchError, match="finite numeric"):
        parse_battle_outcome_batch_roster(_canonical(document))


def test_batch_rejects_inadequate_venue_diversity() -> None:
    prefix, screened = _roster_inputs()
    single_venue_prefix = replace(
        prefix,
        binding=replace(prefix.binding, expected_map=int(MapId.POKEMON_MANSION_1F)),
    )
    single_venue = tuple(
        replace(
            item,
            binding=replace(
                item.binding,
                expected_map=int(MapId.POKEMON_MANSION_1F),
            ),
        )
        for item in screened
    )

    with pytest.raises(BattleOutcomeBatchError, match="venue diversity"):
        _roster(prefix=single_venue_prefix, screened=single_venue)


def test_multiple_floors_of_one_area_are_one_venue() -> None:
    first = _candidate(
        ScenarioPartition.TRAIN,
        "mansion-first",
        basis_offset=0,
        expected_map=int(MapId.POKEMON_MANSION_1F),
    )
    second = _candidate(
        ScenarioPartition.TRAIN,
        "mansion-second",
        basis_offset=2,
        expected_map=int(MapId.POKEMON_MANSION_2F),
    )

    assert first.venue_id == second.venue_id == "pokemon_mansion"


def test_batch_rejects_inadequate_prior_margin_diversity() -> None:
    prefix, screened = _roster_inputs()
    flat_prefix = replace(prefix, prior_scores=(1.0, 0.99, 0.0))
    flat = tuple(replace(item, prior_scores=(1.0, 0.99, 0.0)) for item in screened)

    with pytest.raises(BattleOutcomeBatchError, match="prior-margin diversity"):
        _roster(prefix=flat_prefix, screened=flat)


def test_batch_rejects_inadequate_hidden_contrast_rank() -> None:
    prefix, screened = _roster_inputs()
    collapsed_embeddings = tuple(
        tuple(1.0 if column == row else 0.0 for column in range(_HIDDEN_WIDTH)) for row in range(3)
    )

    def collapse(item: BattleOutcomePressureCandidate) -> BattleOutcomePressureCandidate:
        hidden_sha256 = canonical_sha256(
            {
                "embeddings": collapsed_embeddings,
                "schema": "pokemon.red.battle-outcome-hidden-menu.v1",
            }
        )
        return replace(
            item,
            binding=replace(item.binding, hidden_embedding_sha256=hidden_sha256),
            hidden_embeddings=collapsed_embeddings,
        )

    with pytest.raises(BattleOutcomeBatchError, match="hidden contrast rank"):
        _roster(
            prefix=collapse(prefix),
            screened=tuple(collapse(item) for item in screened),
        )


def test_batch_rejects_a_seven_to_one_party_condition_imbalance() -> None:
    roster = _roster()

    with pytest.raises(BattleOutcomeBatchError, match="party-condition balance"):
        replace(
            roster,
            prefix=replace(roster.prefix, player_hp_ratio=1.0),
            fresh_train=tuple(
                replace(item, player_hp_ratio=0.5 if index == 0 else 1.0)
                for index, item in enumerate(roster.fresh_train)
            ),
            development=tuple(
                replace(item, player_hp_ratio=0.5 if index == 0 else 1.0)
                for index, item in enumerate(roster.development)
            ),
        )


def test_pressure_candidate_rejects_embeddings_outside_tanh_range() -> None:
    rows = [[0.0] * _HIDDEN_WIDTH for _ in range(3)]
    rows[1][0] = 1.1
    rows[2][1] = 1.0

    with pytest.raises(BattleOutcomeBatchError, match="hidden embedding width"):
        _candidate(
            ScenarioPartition.TRAIN,
            "bad-hidden-range",
            basis_offset=0,
            embeddings=tuple(tuple(row) for row in rows),
        )


def test_batch_excludes_unavailable_and_excessive_level_gap_before_freeze() -> None:
    prefix, screened = _roster_inputs()
    unavailable = _candidate(
        ScenarioPartition.TRAIN,
        "unavailable",
        basis_offset=0,
        claim_available=False,
    )
    excessive_gap = replace(
        _candidate(
            ScenarioPartition.TRAIN,
            "level-gap",
            basis_offset=0,
        ),
        player_level=60,
        opponent_level=40,
    )

    roster = _roster(screened=(*screened, unavailable, excessive_gap))

    assert dict(roster.exclusion_counts)["claim_unavailable"] == 1
    assert dict(roster.exclusion_counts)["level_gap_exceeded"] == 1


def test_batch_allows_the_authenticated_legacy_prefix_at_its_exact_level_gap() -> None:
    prefix, screened = _roster_inputs()
    retained_prefix = replace(prefix, player_level=44, opponent_level=30)

    roster = _roster(prefix=retained_prefix, screened=screened)

    assert roster.prefix.level_gap == 14
    assert all(item.level_gap <= 12 for item in roster.fresh_train)


def test_batch_rejects_a_legacy_prefix_beyond_its_narrow_tolerance() -> None:
    prefix, screened = _roster_inputs()
    excessive_prefix = replace(prefix, player_level=45, opponent_level=30)

    with pytest.raises(BattleOutcomeBatchError, match="level gap exceeds policy"):
        _roster(prefix=excessive_prefix, screened=screened)


def test_fixed_heuristic_is_legal_pp_aware_and_avoids_self_destruct() -> None:
    vectors = [[0.0] * len(FEATURE_NAMES) for _ in range(4)]
    effective = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    self_destruct = FEATURE_NAMES.index("move.effect.self_destruct")
    vectors[0][effective] = 0.60
    vectors[1][effective] = 1.00
    vectors[1][self_destruct] = 1.00
    vectors[2][effective] = 1.00
    vectors[3][effective] = 1.00
    features = BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=tuple(tuple(row) for row in vectors),
        legal_mask=(True, True, False, False),
        current_pp=(10.0, 10.0, 10.0, 0.0),
        slot_indices=(0, 1, 2, 3),
        schema_id=FEATURE_SCHEMA_ID,
    )

    assert battle_outcome_fixed_heuristic_choice(features) == 0


def test_pressure_builder_binds_exact_prior_features_and_levels() -> None:
    vectors = [[0.0] * len(FEATURE_NAMES) for _ in range(3)]
    player_level = FEATURE_NAMES.index("state.player_level_fraction")
    opponent_level = FEATURE_NAMES.index("state.opponent_level_fraction")
    player_hp = FEATURE_NAMES.index("state.player_hp_ratio")
    opponent_hp = FEATURE_NAMES.index("state.opponent_hp_ratio")
    status_none = FEATURE_NAMES.index("state.player_status.none")
    player_type_normal = FEATURE_NAMES.index("state.player_type.normal")
    power = FEATURE_NAMES.index("move.power_fraction")
    for index, vector in enumerate(vectors):
        vector[player_level] = 0.42
        vector[opponent_level] = 0.40
        vector[player_hp] = 1.0
        vector[opponent_hp] = 1.0
        vector[status_none] = 1.0
        vector[player_type_normal] = 1.0
        vector[power] = 0.2 * (index + 1)
    features = BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=tuple(tuple(row) for row in vectors),
        legal_mask=(True, True, True),
        current_pp=(10.0, 10.0, 10.0),
        slot_indices=(0, 1, 2),
        schema_id=FEATURE_SCHEMA_ID,
    )
    weights = np.zeros((_HIDDEN_WIDTH, len(FEATURE_NAMES)), dtype=np.float64)
    weights[0, power] = 1.0
    weights[1, power] = -1.0
    model = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.linspace(-0.4, 0.4, _HIDDEN_WIDTH),
        output_weights=np.linspace(-0.5, 0.5, _HIDDEN_WIDTH),
        output_bias=0.0,
    )
    template = _candidate(
        ScenarioPartition.TRAIN,
        "builder",
        basis_offset=0,
    )
    binding = replace(
        template.binding,
        menu_sha256=battle_outcome_menu_sha256(features),
        hidden_embedding_sha256=battle_outcome_hidden_menu_sha256(model, features),
    )

    candidate = build_battle_outcome_pressure_candidate(
        binding,
        features,
        model,
        expected_prior_sha256=battle_outcome_model_sha256(model),
        claim_available=True,
    )

    assert candidate.player_level == 42
    assert candidate.opponent_level == 40
    assert candidate.player_type_ids == ("normal",)
    assert candidate.supported_candidate_indices == (0, 1, 2)
    assert candidate.binding.hidden_embedding_sha256 == (
        canonical_sha256(
            {
                "embeddings": candidate.hidden_embeddings,
                "schema": "pokemon.red.battle-outcome-hidden-menu.v1",
            }
        )
    )

    rejected_output_head = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.linspace(-0.4, 0.4, _HIDDEN_WIDTH),
        output_weights=np.linspace(0.5, -0.5, _HIDDEN_WIDTH),
        output_bias=0.25,
    )
    assert battle_outcome_hidden_menu_sha256(
        rejected_output_head,
        features,
    ) == battle_outcome_hidden_menu_sha256(model, features)

    with pytest.raises(BattleOutcomeBatchError, match="original prior"):
        build_battle_outcome_pressure_candidate(
            binding,
            features,
            rejected_output_head,
            expected_prior_sha256=battle_outcome_model_sha256(model),
            claim_available=True,
        )

    revalidate_battle_outcome_pressure_candidate(
        candidate,
        features,
        model,
        claim_available=True,
    )

    with pytest.raises(BattleOutcomeBatchError, match="rederived source facts"):
        revalidate_battle_outcome_pressure_candidate(
            replace(candidate, player_hp_ratio=0.5),
            features,
            model,
            claim_available=True,
        )
    with pytest.raises(BattleOutcomeBatchError, match="rederived source facts"):
        revalidate_battle_outcome_pressure_candidate(
            replace(candidate, prior_scores=(1.0, 0.0, -1.0)),
            features,
            model,
            claim_available=True,
        )


def test_retained_train_example_is_reconstructed_without_replay() -> None:
    vectors = [[0.0] * len(FEATURE_NAMES) for _ in range(3)]
    power = FEATURE_NAMES.index("move.power_fraction")
    for index, vector in enumerate(vectors):
        vector[power] = 0.2 * (index + 1)
    features = BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=tuple(tuple(row) for row in vectors),
        legal_mask=(True, True, True),
        current_pp=(10.0, 10.0, 10.0),
        slot_indices=(0, 1, 2),
        schema_id=FEATURE_SCHEMA_ID,
    )
    weights = np.zeros((_HIDDEN_WIDTH, len(FEATURE_NAMES)), dtype=np.float64)
    weights[0, power] = 1.0
    model = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(_HIDDEN_WIDTH),
        output_weights=np.linspace(-0.5, 0.5, _HIDDEN_WIDTH),
        output_bias=0.0,
    )
    train = replace(
        _candidate(ScenarioPartition.TRAIN, "retained", basis_offset=0).binding,
        menu_sha256=battle_outcome_menu_sha256(features),
        hidden_embedding_sha256=battle_outcome_hidden_menu_sha256(model, features),
    )
    development = _candidate(
        ScenarioPartition.DEVELOPMENT,
        "retained-forbidden",
        basis_offset=0,
    ).binding
    plan = BattleOutcomeExperimentPlan(
        experiment_id="red-battle-retained-reconstruction",
        source_commit="a" * 40,
        source_bundle_sha256="2" * 64,
        runner_sha256="3" * 64,
        materializer_sha256="4" * 64,
        registry_source_commit="b" * 40,
        registry_source_bundle_sha256="6" * 64,
        registry_sha256="7" * 64,
        context_catalog_sha256="8" * 64,
        rom_sha256="9" * 64,
        runtime_identity_sha256="a" * 64,
        numpy_runtime_sha256="b" * 64,
        base_model_sha256=battle_outcome_model_sha256(model),
        controller_timing_sha256="c" * 64,
        captures=(train, development),
    )
    record = _retained_train_record(plan)
    retained = build_retained_battle_outcome_prefix(
        plan,
        artifact_manifest_sha256="d" * 64,
        train_collection_record=record,
    )

    example = reconstruct_retained_battle_outcome_example(
        retained,
        record,
        features=features,
        model=model,
    )

    assert example.root_lineage_id == train.root_lineage_id
    assert example.best_candidate_indices == (1,)
    assert example.learner_update_eligible
    with pytest.raises(BattleOutcomeBatchError, match="record digest differs"):
        reconstruct_retained_battle_outcome_example(
            retained,
            {**record, "unmeasured_action_targets": 1},
            features=features,
            model=model,
        )
