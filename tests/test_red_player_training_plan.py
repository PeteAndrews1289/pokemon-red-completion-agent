import hashlib
import json
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_player_training_plan as plans


@pytest.mark.parametrize(
    "partition,other_partition,state_changed",
    [
        ("train", "train", False),
        ("development", "train", False),
        ("train", "test", False),
        ("train", "train", True),
    ],
)
def test_declaration_uses_original_assignment_not_filename(
    tmp_path, monkeypatch, partition, other_partition, state_changed
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
    )
    if partition == other_partition == "train" and not state_changed:
        plan = plans.declare_red_player_training(**kwargs)
        assert plan.document["root_lineage_id"] == "original-root"
        assert plan.document["partition"] == "train"
    else:
        with pytest.raises(ValueError, match="exclusively train"):
            plans.declare_red_player_training(**kwargs)
    assert revisions == ["a" * 40]
