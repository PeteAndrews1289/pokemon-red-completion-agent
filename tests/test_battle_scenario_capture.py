from __future__ import annotations

import json

import pytest

from pokemon_red_completion.battle_scenario_capture import (
    BattleScenarioCaptureError,
    BattleScenarioCaptureManifest,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
    parse_battle_scenario_capture_manifest,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _payload(state: bytes, *, partition: ScenarioPartition = ScenarioPartition.TRAIN) -> bytes:
    return build_battle_scenario_capture_payload(
        capture_id="battle-capture-001",
        root_lineage_id="red-lineage-a",
        partition=partition,
        state_bytes=state,
        initial_observation_sha256="b" * 64,
        source_commit="c" * 40,
        expected_map=165,
        expected_battle_state=1,
    )


def test_verified_opener_returns_bytes_and_no_private_path_fields(tmp_path) -> None:
    state = b"private emulator state"
    state_path = tmp_path / "private.state"
    manifest_path = tmp_path / "private.state.json"
    state_path.write_bytes(state)
    manifest_path.write_bytes(_payload(state))

    capture = open_battle_scenario_capture(state_path, manifest_path)

    assert capture.state_bytes == state
    assert capture.manifest.partition is ScenarioPartition.TRAIN
    assert not hasattr(capture, "state_path")
    assert not hasattr(capture, "manifest_path")
    encoded = json.dumps(capture.manifest.public_dict(), sort_keys=True)
    assert str(tmp_path) not in encoded
    assert "/" not in encoded


def test_v2_manifest_binds_the_private_source_state_without_retaining_its_path(
    tmp_path,
) -> None:
    state = b"derived battle state"
    source_state_sha256 = "d" * 64
    state_path = tmp_path / "derived.state"
    manifest_path = tmp_path / "derived.state.json"
    state_path.write_bytes(state)
    manifest_path.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="battle-capture-v2",
            root_lineage_id="red-lineage-v2",
            partition=ScenarioPartition.DEVELOPMENT,
            state_bytes=state,
            initial_observation_sha256="b" * 64,
            source_commit="c" * 40,
            expected_map=165,
            expected_battle_state=1,
            source_state_sha256=source_state_sha256,
        )
    )

    capture = open_battle_scenario_capture(state_path, manifest_path)

    assert capture.manifest.source_state_sha256 == source_state_sha256
    assert capture.manifest.public_dict()["schema"].endswith("capture-v2")
    assert str(tmp_path) not in json.dumps(capture.manifest.public_dict())


def test_manifest_parser_authenticates_metadata_without_opening_state() -> None:
    payload = build_battle_scenario_capture_payload(
        capture_id="battle-capture-v2",
        root_lineage_id="red-lineage-v2",
        partition=ScenarioPartition.DEVELOPMENT,
        state_bytes=b"state remains unopened",
        initial_observation_sha256="b" * 64,
        source_commit="c" * 40,
        expected_map=165,
        expected_battle_state=1,
        source_state_sha256="d" * 64,
    )

    manifest = parse_battle_scenario_capture_manifest(payload)

    assert manifest.capture_id == "battle-capture-v2"
    assert manifest.partition is ScenarioPartition.DEVELOPMENT
    with pytest.raises(TypeError, match="must be bytes"):
        parse_battle_scenario_capture_manifest("not bytes")  # type: ignore[arg-type]


def test_opener_rejects_state_drift_noncanonical_manifest_and_symlinks(tmp_path) -> None:
    state_path = tmp_path / "private.state"
    manifest_path = tmp_path / "private.state.json"
    state_path.write_bytes(b"changed")
    manifest_path.write_bytes(_payload(b"original"))
    with pytest.raises(BattleScenarioCaptureError, match="state bytes differ"):
        open_battle_scenario_capture(state_path, manifest_path)

    state_path.write_bytes(b"original")
    parsed = json.loads(_payload(b"original"))
    manifest_path.write_text(json.dumps(parsed, indent=2), encoding="ascii")
    with pytest.raises(BattleScenarioCaptureError, match="not canonical"):
        open_battle_scenario_capture(state_path, manifest_path)

    manifest_path.write_bytes(_payload(b"original"))
    state_link = tmp_path / "linked.state"
    state_link.symlink_to(state_path)
    with pytest.raises(BattleScenarioCaptureError, match="unavailable"):
        open_battle_scenario_capture(state_link, manifest_path)

    state_link.unlink()
    hardlink = tmp_path / "hardlinked.state"
    hardlink.hardlink_to(state_path)
    with pytest.raises(BattleScenarioCaptureError, match="unavailable"):
        open_battle_scenario_capture(state_path, manifest_path)
    hardlink.unlink()

    state_path.chmod(0o666)
    with pytest.raises(BattleScenarioCaptureError, match="unavailable"):
        open_battle_scenario_capture(state_path, manifest_path)


def test_development_opener_refuses_test_partition() -> None:
    with pytest.raises(BattleScenarioCaptureError, match="sealed test captures"):
        _payload(b"private", partition=ScenarioPartition.TEST)


def test_capture_object_cannot_be_constructed_without_verified_opener() -> None:
    manifest = BattleScenarioCaptureManifest(
        capture_id="battle-capture-001",
        root_lineage_id="red-lineage-a",
        partition=ScenarioPartition.TRAIN,
        state_sha256="a" * 64,
        initial_observation_sha256="b" * 64,
        source_commit="c" * 40,
        expected_map=165,
        expected_battle_state=1,
    )
    from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture

    with pytest.raises(BattleScenarioCaptureError, match="verified opener"):
        BattleScenarioCapture(
            manifest=manifest,
            manifest_sha256="d" * 64,
            state_bytes=b"private",
            _validation_token=object(),
        )
