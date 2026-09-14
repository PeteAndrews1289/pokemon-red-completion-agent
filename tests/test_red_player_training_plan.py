import hashlib
import json
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_player_training_plan as plans


def _base_plan():
    return plans.RedPlayerTrainingPlan(
        {
            "schema": plans.TRAINING_PLAN_SCHEMA,
            "episode_id": "direct-catalog-episode",
            "partition": "train",
            "seed": 17,
            "decision_limit": 2,
            "behavior_policy_id": "living-dex-player-supported-menu-v2",
            "economic_contract": "known-spend-and-excess-reserve-v1",
            "context_catalog_sha256": "1" * 64,
            "context_id": "2" * 64,
            "catalog_source_commit": "3" * 40,
            "binding_manifest_sha256": "4" * 64,
            "root_lineage_id": "direct-catalog-root",
            "state_sha256": "5" * 64,
            "envelope_sha256": "6" * 64,
            "profile_sha256": "7" * 64,
            "model_sha256": "8" * 64,
            "source_commit": "9" * 40,
            "source_bundle_sha256": "a" * 64,
            "independent_evaluation": False,
            "historical_trial_retry": False,
            "episode_retry_after_input": False,
        }
    )


def test_direct_completion_binds_execution_profile_without_inventing_parent():
    direct = plans.declare_direct_completion_dose(
        _base_plan(),
        execution_profile_sha256="b" * 64,
        root_pair_claim_sha256="c" * 64,
    )
    assert direct.document["schema"] == plans.DIRECT_COMPLETION_TRAINING_PLAN_SCHEMA
    assert direct.document["origin_profile_sha256"] == "7" * 64
    assert direct.document["profile_sha256"] == "b" * 64
    assert direct.document["root_pair_claim_sha256"] == "c" * 64
    assert direct.maximum_actions == 30_000
    assert direct.maximum_frames == 3_000_000
    assert not any(key.startswith("continuation_") for key in direct.document)
    assert "restore_profile_sha256" not in direct.document


def test_direct_completion_rejects_relabeling_a_continuation():
    direct = plans.declare_direct_completion_dose(
        _base_plan(),
        execution_profile_sha256="b" * 64,
        root_pair_claim_sha256="c" * 64,
    )
    with pytest.raises(ValueError, match="original catalog plan"):
        plans.declare_direct_completion_dose(
            direct,
            execution_profile_sha256="c" * 64,
            root_pair_claim_sha256="d" * 64,
        )
    with pytest.raises(ValueError, match="fields differ"):
        plans.RedPlayerTrainingPlan(
            {
                **direct.document,
                "continuation_episode_id": "invented-parent",
                "continuation_checkpoint_sha256": "d" * 64,
            }
        )


@pytest.mark.parametrize(
    "partition,other_partition,state_changed",
    [
        ("train", "train", False),
        ("development", "train", False),
        ("train", "test", False),
        ("train", "train", True),
    ],
)
@pytest.mark.parametrize("feature_version", [1, 2, 3, 4, 5])
def test_declaration_uses_original_assignment_not_filename(
    tmp_path, monkeypatch, partition, other_partition, state_changed, feature_version
):
    # Stub the separately tested catalog authentication only. The declaration's
    # partition and physical-state checks run unchanged below.
    payload = json.dumps({"source_commit": "a" * 40}).encode()
    path = tmp_path / "catalog.json"
    path.write_bytes(payload)
    registry = SimpleNamespace(
        assignment=lambda slot: SimpleNamespace(
            partition=partition if slot == "first" else other_partition
        )
    )
    revisions = []

    def committed(_root, revision):
        revisions.append(revision)
        return registry

    monkeypatch.setattr(plans, "load_committed_goal_manager_registry_at_revision", committed)
    entry = SimpleNamespace(
        capture_id="not-a-partition-label",
        slot_id="first",
        state_sha256="1" * 64,
        envelope_sha256="2" * 64,
        context_id="3" * 64,
        binding_manifest_sha256="4" * 64,
        root_lineage_id="original-root",
    )
    other = SimpleNamespace(capture_id="another", slot_id="other", state_sha256="1" * 64)
    monkeypatch.setattr(
        plans,
        "parse_goal_manager_context_catalog",
        lambda actual, supplied: (
            SimpleNamespace(entries=(entry, other), catalog_sha256="5" * 64)
            if actual == payload and supplied is registry
            else pytest.fail("wrong registry")
        ),
    )
    capture = SimpleNamespace(
        capture_id=entry.capture_id,
        state_sha256=("9" if state_changed else "1") * 64,
        envelope_sha256="2" * 64,
    )
    kwargs = dict(
        repository_root=tmp_path,
        catalog_path=path,
        expected_catalog_sha256=hashlib.sha256(payload).hexdigest(),
        capture=capture,
        profile_sha256="6" * 64,
        model_sha256="7" * 64,
        source_commit="b" * 40,
        source_bundle_sha256="8" * 64,
        episode_id="new-native-episode",
        seed=17,
        decision_limit=4,
        feature_version=feature_version,
    )
    if partition == other_partition == "train" and not state_changed and feature_version <= 4:
        plan = plans.declare_red_player_training(**kwargs)
        assert plan.document["root_lineage_id"] == "original-root"
        assert plan.document["partition"] == "train"
        assert plan.document["behavior_policy_id"] == (
            "living-dex-player-optional-recovery-v4" if feature_version >= 3
            else "living-dex-player-supported-menu-v2"
        )
    elif partition == other_partition == "train" and not state_changed:
        with pytest.raises(ValueError, match="exploration feature version"):
            plans.declare_red_player_training(**kwargs)
    else:
        with pytest.raises(ValueError, match="exclusively train"):
            plans.declare_red_player_training(**kwargs)
    assert revisions == ["a" * 40]
