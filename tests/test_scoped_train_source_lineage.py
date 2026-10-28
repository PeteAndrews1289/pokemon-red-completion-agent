"""ROM-free canonical TRAIN source binding; real native capture codec."""
import ast
import inspect
import json
from dataclasses import fields, replace
from hashlib import sha256
from types import MappingProxyType

import pytest
from test_red_scoped_training_battlers import A, B, prototype
from pokemon_red_completion.battle_scenario_capture import (
    BattleScenarioCaptureManifest, build_battle_scenario_capture_payload,
    parse_battle_scenario_capture_manifest, open_battle_scenario_capture,
)
from pokemon_red_completion.red_scoped_training_battlers import (
    ScopedTrainingBattlers, scoped_train_root_lineage_id,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

ORIGIN = "d" * 64
SOURCE = dict(partition="train", state_sha256="b" * 64,
              source_commit="a" * 40, origin_sha256=ORIGIN)


def bind(p, tmp_path, source=SOURCE, **kwargs):
    return ScopedTrainingBattlers.for_native_source(
        p, source=source, contracts=(A, B), output=tmp_path / "pool",
        experiment_sha256="c" * 64, **kwargs,
    )


@pytest.mark.parametrize("bad", [None, True, 7, b"d" * 64, "", "d" * 63,
    "d" * 65, "D" * 64, "g" * 64, "d" * 63 + "\n"])
def test_origin_is_strict_lowercase_sha256(bad):
    with pytest.raises(ValueError, match="lowercase SHA256"):
        scoped_train_root_lineage_id(bad)


def test_canonical_helper_matches_existing_private_format():
    assert scoped_train_root_lineage_id(ORIGIN) == "red-goal-root-" + ORIGIN


def test_factory_changes_only_cloned_root_and_preserves_prototype(tmp_path):
    p = prototype(tmp_path)
    before = {f.name: getattr(p, f.name) for f in fields(p)}
    pool = bind(p, tmp_path, MappingProxyType(SOURCE))
    declaration = json.loads((pool.output / "declaration.json").read_bytes())
    assert declaration["root_lineage_id"] == scoped_train_root_lineage_id(ORIGIN)
    assert declaration["source_state_sha256"] == SOURCE["state_sha256"]
    assert declaration["source_commit"] == SOURCE["source_commit"]
    assert declaration["source_partition"] == "train"
    assert declaration["fit_allowed"] is declaration["authority_promotion"] is False
    assert {f.name: getattr(p, f.name) for f in fields(p)} == before
    for actor in (pool.story(A), pool.story(B), pool.wild):
        for f in fields(p):
            if f.name not in {"root_lineage_id", "output", "train_story_contract"}:
                assert getattr(actor, f.name) is getattr(p, f.name)
        assert actor.root_lineage_id == declaration["root_lineage_id"]
    assert p.root_lineage_id == "train-root" and p.calls == 0
    assert p.session.frame_count == 0 and not p.output.exists()


def test_real_capture_manifest_uses_same_source_identity_chain(tmp_path):
    p = prototype(tmp_path)
    pool = bind(p, tmp_path)
    a = pool.story(A)
    state_bytes = b"synthetic battle capture bytes, no ROM or emulator"
    payload = build_battle_scenario_capture_payload(
        capture_id="player-trainer-0001", root_lineage_id=a.root_lineage_id,
        partition=a.source_partition, state_bytes=state_bytes,
        initial_observation_sha256="e" * 64, source_commit=a.source_commit,
        expected_map=A.map_id, expected_battle_state=2,
        source_state_sha256=a.source_state_sha256,
    )
    manifest = parse_battle_scenario_capture_manifest(payload)
    assert type(manifest) is BattleScenarioCaptureManifest
    assert manifest.root_lineage_id == scoped_train_root_lineage_id(SOURCE["origin_sha256"])
    assert manifest.source_state_sha256 == SOURCE["state_sha256"]
    assert manifest.source_commit == SOURCE["source_commit"]
    assert manifest.partition is ScenarioPartition.TRAIN
    state_path, manifest_path = tmp_path / "battle.state", tmp_path / "battle.state.json"
    state_path.write_bytes(state_bytes); manifest_path.write_bytes(payload)
    state_path.chmod(0o600); manifest_path.chmod(0o600)
    authenticated = open_battle_scenario_capture(state_path, manifest_path)
    assert authenticated.manifest == manifest
    assert authenticated.state_bytes == state_bytes
    assert manifest.state_sha256 == sha256(state_bytes).hexdigest()


class NoNativeReads:
    @property
    def frame_count(self):
        raise AssertionError("native session must not be read for invalid source")


@pytest.mark.parametrize("field,bad", [
    ("partition", "development"), ("partition", "test"), ("partition", True),
    ("state_sha256", "e" * 64), ("state_sha256", "B" * 64),
    ("state_sha256", None), ("source_commit", "c" * 40),
    ("source_commit", "A" * 40), ("source_commit", "a" * 39),
    ("origin_sha256", "D" * 64), ("origin_sha256", None),
])
def test_invalid_source_rejected_before_native_reads_or_output(tmp_path, field, bad):
    p = replace(prototype(tmp_path), session=NoNativeReads())
    with pytest.raises(ValueError):
        bind(p, tmp_path, {**SOURCE, field: bad})
    assert not (tmp_path / "pool").exists()
    assert p.root_lineage_id == "train-root"


@pytest.mark.parametrize("field", tuple(SOURCE))
def test_missing_source_field_rejected_before_io(tmp_path, field):
    p = replace(prototype(tmp_path), session=NoNativeReads())
    source = dict(SOURCE); del source[field]
    with pytest.raises(ValueError):
        bind(p, tmp_path, source)
    assert not (tmp_path / "pool").exists()


def test_non_mapping_source_rejected_before_io(tmp_path):
    p = replace(prototype(tmp_path), session=NoNativeReads())
    with pytest.raises(ValueError, match="mapping"):
        bind(p, tmp_path, list(SOURCE.items()))
    assert not (tmp_path / "pool").exists()


def test_conflicting_canonical_origin_rejected_before_io(tmp_path):
    p = replace(prototype(tmp_path), session=NoNativeReads(),
                root_lineage_id=scoped_train_root_lineage_id("e" * 64))
    with pytest.raises(ValueError, match="canonical origin"):
        bind(p, tmp_path)
    assert not (tmp_path / "pool").exists()


def test_prototype_development_cannot_be_promoted(tmp_path):
    p = replace(prototype(tmp_path), session=NoNativeReads(),
                source_partition=ScenarioPartition.DEVELOPMENT)
    with pytest.raises(ValueError):
        bind(p, tmp_path)
    assert not (tmp_path / "pool").exists()


def test_existing_canonical_root_is_preserved(tmp_path):
    p = replace(prototype(tmp_path), root_lineage_id=scoped_train_root_lineage_id(ORIGIN))
    assert bind(p, tmp_path).wild.root_lineage_id == p.root_lineage_id


def test_legacy_constructor_keeps_explicit_alias_unchanged(tmp_path):
    p = prototype(tmp_path)
    pool = ScopedTrainingBattlers(p, contracts=(A,), output=tmp_path / "legacy",
                                  experiment_sha256="c" * 64)
    assert pool.wild.root_lineage_id == "train-root"
    assert json.loads((pool.output / "declaration.json").read_bytes())["root_lineage_id"] == "train-root"


def test_existing_fresh_actor_guard_still_rejects_used_prototype(tmp_path):
    p = replace(prototype(tmp_path), calls=1, session=NoNativeReads())
    with pytest.raises(ValueError, match="actor declaration"):
        bind(p, tmp_path)
    assert not (tmp_path / "pool").exists()
