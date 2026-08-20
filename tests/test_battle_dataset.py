from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from pokemon_red_completion.battle_dataset import (
    BattleDatasetError,
    BattleDecisionProvenance,
    audit_preassigned_partitions,
    grouped_diagnostic_folds,
    load_battle_episode,
)
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.trajectory import canonical_sha256

PROVENANCE = BattleDecisionProvenance(
    actor="deterministic_teacher",
    policy_id="pokemon-red-qualified-teacher-v1",
    skill_id="pokemon.core:battle:move_selection",
)


class _Reader:
    manifest_sha256 = "f" * 64

    def __init__(
        self,
        *,
        decisions: list[dict[str, object]],
        snapshots: list[dict[str, object]],
        partition: str = "unassigned",
        root_lineage_id: str = "episode-001",
    ) -> None:
        self._header = {
            "record_type": "episode",
            "trajectory_schema": "pokemon.trajectory.v1",
            "episode_id": "episode-001",
            "game_id": "pokemon.mainline:red:gb:us:rev0",
            "metadata": {
                "policy": {
                    "actor": PROVENANCE.actor,
                    "policy_id": PROVENANCE.policy_id,
                },
                "split": {
                    "partition": partition,
                    "regime": "within_game",
                    "root_lineage_id": root_lineage_id,
                },
            },
        }
        self._streams = {
            "decisions": decisions,
            "snapshots": snapshots,
        }

    def read_header(self) -> dict[str, object]:
        return self._header

    def iter_stream(self, stream: str):
        return iter(self._streams[stream])


def _snapshot(*, group: int, water_pp: int = 25) -> dict[str, object]:
    return {
        "schema_version": 1,
        "game_id": "pokemon.mainline:red:gb:us:rev0",
        "mode": "battle",
        "location": f"pokemon.red.gb.us.rev0:area:test_{group}",
        "facts": ["pokemon.core:battle:active"],
        "features": {
            "adapter_id": "pokemon.red.gb.us.rev0.v1",
            "ontology_id": "pokemon.core.v1",
            "control": {"input_ready": True},
            "world": {
                "area_kind": "interior",
                "area_ref": f"pokemon.red.gb.us.rev0:area:test_{group}",
                "position": {"x": group, "y": 4},
            },
            "progress": {"badge_count": 0},
            "party": {
                "count": 1,
                "species_refs": ["pokemon.red.gb.us.rev0:species:177"],
                "lead": {
                    "species_ref": "pokemon.red.gb.us.rev0:species:177",
                    "level": 12,
                    "hp": 30,
                    "max_hp": 30,
                    "hp_ratio": 1.0,
                    "status": None,
                    "moves": [
                        {
                            "move_ref": "pokemon.red.gb.us.rev0:move:033",
                            "pp": 35,
                            "slot_index": 0,
                        },
                        {
                            "move_ref": "pokemon.red.gb.us.rev0:move:055",
                            "pp": water_pp,
                            "slot_index": 1,
                        },
                        {
                            "move_ref": "pokemon.red.gb.us.rev0:move:039",
                            "pp": 30,
                            "slot_index": 2,
                        },
                        {
                            "move_ref": "pokemon.red.gb.us.rev0:move:028",
                            "pp": 15,
                            "slot_index": 3,
                        },
                    ],
                },
            },
            "battle": {
                "active": True,
                "kind": "trainer",
                "opponent_species_ref": "pokemon.red.gb.us.rev0:species:034",
                "opponent_level": 12,
                "opponent_hp": 35,
                "opponent_max_hp": 35,
                "opponent_hp_ratio": 1.0,
                "player_attack_stage": 0,
                "player_accuracy_stage": 0,
                "opponent_defense_stage": 0,
            },
            "menu": {"kind": "battle_main", "selected_command_index": 0},
        },
    }


def _records(
    *,
    count: int = 10,
    partition: str = "unassigned",
    explicit_groups: bool = False,
) -> _Reader:
    decisions: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    for index in range(count):
        snapshot = _snapshot(group=index)
        digest = canonical_sha256(snapshot)
        snapshots.append(
            {
                "record_type": "snapshot",
                "snapshot_sha256": digest,
                "snapshot": snapshot,
            }
        )
        metadata: dict[str, object] = {
            "skill_id": "pokemon.core:battle:move_selection",
        }
        if explicit_groups:
            metadata["battle_instance_id"] = f"battle-{index}"
            metadata["battle_plan_id"] = f"battle-{index:03d}-test"
            metadata["battle_goal"] = "win"
            metadata["battle_policy_context"] = {
                "goal": "win",
                "move_policy": "any_usable",
                "required_move_ref": None,
            }
            metadata["teacher_recovery_marker"] = "none"
        decisions.append(
            {
                "record_type": "decision",
                "schema_version": 1,
                "decision_id": f"episode-001:decision:{index}",
                "episode_id": "episode-001",
                "step_index": index,
                "snapshot_sha256": digest,
                "decision_type": "battle_move_selection",
                "context": {
                    "schema_version": 1,
                    "actor": PROVENANCE.actor,
                    "policy_id": PROVENANCE.policy_id,
                    "objective_id": "defeat_test_trainer" if explicit_groups else None,
                    "metadata": metadata,
                },
                "action": {"kind": "select_move", "slot_index": 1},
            }
        )
    return _Reader(
        decisions=decisions,
        snapshots=snapshots,
        partition=partition,
    )


def _load(reader: _Reader):
    return load_battle_episode(
        cast(object, reader),
        BattleFeatureProjector(PokemonRedBattleCatalog()),
        required_provenance=PROVENANCE,
    )


def test_loader_joins_exact_snapshots_and_keeps_route_fields_out_of_features() -> None:
    dataset = _load(_records())

    assert len(dataset.examples) == 10
    assert len(dataset.group_ids) == 10
    assert dataset.public_summary()["slot_counts"] == [0, 10, 0, 0]
    assert dataset.diagnostic_reasons == (
        "inferred_battle_groups",
        "policy_goal_not_fully_observed",
        "unassigned_root_lineage",
    )
    assert dataset.episode_qualified is False
    assert dataset.promotion_eligible is False
    assert all(
        forbidden not in name
        for name in dataset.feature_names
        for forbidden in (
            "area",
            "assignment",
            "badge",
            "battle_plan",
            "decision",
            "harness",
            "location",
            "partition",
            "position",
            "run_id",
            "schedule",
            "slot",
        )
    )


def test_explicit_groups_goals_and_preassigned_partition_remove_diagnostic_reasons() -> None:
    dataset = _load(_records(partition="train", explicit_groups=True))

    assert dataset.episode_qualified is True
    assert dataset.promotion_eligible is False
    assert dataset.diagnostic_reasons == ()
    assert {example.group_source for example in dataset.examples} == {"explicit_battle_instance"}
    assert all(example.policy_goal_observed for example in dataset.examples)


@pytest.mark.parametrize(
    ("location", "field", "value"),
    [
        ("context", "objective_id", None),
        ("metadata", "battle_plan_id", None),
        ("metadata", "battle_goal", None),
        ("metadata", "battle_policy_context", None),
        ("metadata", "teacher_recovery_marker", None),
    ],
)
def test_null_or_incomplete_policy_context_never_qualifies(
    location: str,
    field: str,
    value: object,
) -> None:
    reader = _records(count=1, partition="train", explicit_groups=True)
    context = reader._streams["decisions"][0]["context"]
    assert isinstance(context, dict)
    target = context if location == "context" else context["metadata"]
    assert isinstance(target, dict)
    target[field] = value

    dataset = _load(reader)

    assert dataset.promotion_eligible is False
    assert "policy_goal_not_fully_observed" in dataset.diagnostic_reasons
    assert dataset.examples[0].policy_goal_observed is False


def test_exact_required_context_must_name_the_selected_semantic_move() -> None:
    reader = _records(count=1, partition="train", explicit_groups=True)
    context = reader._streams["decisions"][0]["context"]
    assert isinstance(context, dict)
    metadata = context["metadata"]
    assert isinstance(metadata, dict)
    metadata["battle_policy_context"] = {
        "goal": "win",
        "move_policy": "exact_required",
        "required_move_ref": "pokemon.red.gb.us.rev0:move:055",
    }

    qualified = _load(reader)
    assert qualified.episode_qualified is True
    assert qualified.promotion_eligible is False
    assert qualified.examples[0].policy_goal_observed is True

    policy_context = metadata["battle_policy_context"]
    assert isinstance(policy_context, dict)
    policy_context["required_move_ref"] = "pokemon.red.gb.us.rev0:move:033"
    mismatched = _load(reader)
    assert mismatched.episode_qualified is False
    assert mismatched.promotion_eligible is False
    assert "policy_goal_not_fully_observed" in mismatched.diagnostic_reasons


def test_grouped_folds_are_deterministic_complete_and_group_disjoint() -> None:
    dataset = _load(_records())

    first = grouped_diagnostic_folds(dataset, fold_count=5)
    second = grouped_diagnostic_folds(dataset, fold_count=5)

    assert first == second
    assert sorted(index for fold in first for index in fold.test_indices) == list(range(10))
    for fold in first:
        assert set(fold.train_indices).isdisjoint(fold.test_indices)
        train_groups = {dataset.examples[index].group_id for index in fold.train_indices}
        test_groups = {dataset.examples[index].group_id for index in fold.test_indices}
        assert train_groups.isdisjoint(test_groups)


def test_loader_rejects_snapshot_tampering_and_unusable_teacher_choice() -> None:
    tampered = _records()
    tampered._streams["snapshots"][0]["snapshot"] = _snapshot(group=99)
    with pytest.raises(BattleDatasetError, match="digest"):
        _load(tampered)

    unusable = _records(count=1)
    snapshot = _snapshot(group=0, water_pp=0)
    digest = canonical_sha256(snapshot)
    unusable._streams["snapshots"][0] = {
        "record_type": "snapshot",
        "snapshot_sha256": digest,
        "snapshot": snapshot,
    }
    unusable._streams["decisions"][0]["snapshot_sha256"] = digest
    with pytest.raises(BattleDatasetError, match="illegal"):
        _load(unusable)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor", "learned_policy"),
        ("policy_id", "different-teacher"),
    ],
)
def test_loader_rejects_mixed_decision_provenance(field: str, value: str) -> None:
    reader = _records(count=1)
    context = reader._streams["decisions"][0]["context"]
    assert isinstance(context, dict)
    context[field] = value

    with pytest.raises(BattleDatasetError, match="provenance"):
        _load(reader)

    metadata = context["metadata"]
    assert isinstance(metadata, dict)
    context[field] = getattr(PROVENANCE, field)
    metadata["skill_id"] = "pokemon.core:navigation"
    with pytest.raises(BattleDatasetError, match="provenance"):
        _load(reader)


@pytest.mark.parametrize("field", ["actor", "policy_id"])
def test_loader_rejects_mismatched_episode_provenance(field: str) -> None:
    reader = _records(count=1)
    metadata = reader._header["metadata"]
    assert isinstance(metadata, dict)
    policy = metadata["policy"]
    assert isinstance(policy, dict)
    policy[field] = "different-teacher"

    with pytest.raises(BattleDatasetError, match="provenance"):
        _load(reader)


@pytest.mark.parametrize("location", ["decision", "context"])
def test_loader_rejects_boolean_schema_versions(location: str) -> None:
    reader = _records(count=1)
    decision = reader._streams["decisions"][0]
    if location == "decision":
        decision["schema_version"] = True
    else:
        context = decision["context"]
        assert isinstance(context, dict)
        context["schema_version"] = True

    with pytest.raises(BattleDatasetError, match="unsupported schema"):
        _load(reader)


def test_partition_audit_rejects_missing_splits_and_cross_partition_leakage() -> None:
    train = _load(_records(partition="train", explicit_groups=True))
    validation = replace(
        train,
        episode_id="episode-002",
        root_lineage_id="episode-002",
        partition="validation",
    )
    test = replace(
        train,
        episode_id="episode-003",
        root_lineage_id="episode-003",
        partition="test",
    )

    overlapping = audit_preassigned_partitions((train, validation, test))
    assert overlapping.promotion_eligible is False
    assert overlapping.snapshot_overlap_count == 10
    assert "snapshot_partition_overlap" not in overlapping.reasons
    assert "duplicate_episode_manifest" in overlapping.reasons

    missing = audit_preassigned_partitions((train,))
    assert {"missing_validation_partition", "missing_test_partition"}.issubset(missing.reasons)


def test_partition_audit_never_claims_promotion_without_registry_authentication() -> None:
    train = _load(_records(partition="train", explicit_groups=True))
    validation = replace(
        _load(_records(partition="validation", explicit_groups=True)),
        episode_id="episode-002",
        manifest_sha256="b" * 64,
        root_lineage_id="episode-002",
    )
    test = replace(
        _load(_records(partition="test", explicit_groups=True)),
        episode_id="episode-003",
        manifest_sha256="c" * 64,
        root_lineage_id="episode-003",
    )
    validation = replace(
        validation,
        examples=tuple(
            replace(example, snapshot_sha256=f"{index + 100:064x}")
            for index, example in enumerate(validation.examples)
        ),
    )
    test = replace(
        test,
        examples=tuple(
            replace(example, snapshot_sha256=f"{index + 200:064x}")
            for index, example in enumerate(test.examples)
        ),
    )

    audit = audit_preassigned_partitions((train, validation, test))

    assert audit.snapshot_overlap_count == 0
    assert audit.promotion_eligible is False
    assert audit.reasons == ("promotion_protocol_not_authenticated",)
