from __future__ import annotations

import hashlib
import json
import runpy
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattlePartyOption,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
    build_repeatable_battle_scenario_plan,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/materialize_repeatable_battle_scenario.py")
GLOBALS = SCRIPT["_run"].__globals__
MaterializationError = SCRIPT["RepeatableBattleScenarioMaterializationError"]


def _source(partition: ScenarioPartition, state_bytes: bytes) -> RepeatableBattleSourceObservation:
    stem = partition.value
    return RepeatableBattleSourceObservation(
        source_id=f"source-{stem}",
        source_lineage_id=f"lineage-{stem}",
        partition=partition,
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        source_commit="a" * 40,
        expected_map=22,
        source_kind=RepeatableBattleSourceKind.FIELD,
        active_party_index=None,
        reachable_venue_ids=("route_11",),
        party_options=(
            RepeatableBattlePartyOption(
                0,
                ("b" if partition is ScenarioPartition.TRAIN else "c") * 64,
                3,
                1.0,
            ),
        ),
    )


def _payload(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("ascii")


def _inputs(tmp_path: Path) -> tuple[SimpleNamespace, RepeatableBattleSourceObservation]:
    train_bytes = b"train-source-state"
    train = _source(ScenarioPartition.TRAIN, train_bytes)
    development = _source(ScenarioPartition.DEVELOPMENT, b"development-source-state")
    plan = build_repeatable_battle_scenario_plan(
        (train, development),
        seed=1289,
        training_scenarios=1,
        development_scenarios=1,
        wait_frame_offsets=(0,),
    )
    plan_payload = _payload(plan.private_dict())
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(plan_payload)
    state_path = tmp_path / "source.state"
    state_path.write_bytes(train_bytes)
    rom_path = tmp_path / "red.gb"
    rom_path.write_bytes(b"rom")
    args = SimpleNamespace(
        private_plan=plan_path,
        expected_plan_sha256=plan.sha256,
        scenario_id=plan.partition_assignments(ScenarioPartition.TRAIN)[0].scenario_id,
        source_state=state_path,
        out_state=tmp_path / "capture.state",
        out_manifest=tmp_path / "capture.state.json",
        rom=rom_path,
        maximum_encounter_steps=32,
        watch=False,
        speed=None,
    )
    return args, train


def test_script_binds_plan_source_and_private_outputs_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, source = _inputs(tmp_path)
    assert hashlib.sha256(args.private_plan.read_bytes()).hexdigest() != (
        args.expected_plan_sha256
    )
    monkeypatch.setitem(
        GLOBALS,
        "detect_source_identity",
        lambda *args, **kwargs: SimpleNamespace(git_commit="d" * 40),
    )
    monkeypatch.setitem(GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(GLOBALS, "require_published_source", lambda *args: None)
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda value: value)
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="e" * 64),
    )
    monkeypatch.setitem(
        GLOBALS,
        "inspect_repeatable_red_battle_source",
        lambda *args, **kwargs: source,
    )
    calls: list[str] = []

    def materialize(observed, assignment, state_bytes, **kwargs):  # type: ignore[no-untyped-def]
        assert observed == source
        assert hashlib.sha256(state_bytes).hexdigest() == assignment.source_state_sha256
        assert kwargs["materializer_source_commit"] == "d" * 40
        calls.append(assignment.scenario_id)
        return SimpleNamespace(
            state_bytes=b"materialized-state",
            manifest_payload=b"canonical-manifest\n",
            public_dict=lambda: {
                "schema": "pokemon.red.battle.repeatable-materialization.v1",
                "scenario_id": assignment.scenario_id,
            },
        )

    monkeypatch.setitem(GLOBALS, "materialize_repeatable_red_battle_scenario", materialize)

    summary = SCRIPT["_run"](args)

    assert calls == [args.scenario_id]
    assert args.out_state.read_bytes() == b"materialized-state"
    assert args.out_manifest.read_bytes() == b"canonical-manifest\n"
    assert stat.S_IMODE(args.out_state.stat().st_mode) == 0o600
    assert stat.S_IMODE(args.out_manifest.stat().st_mode) == 0o600
    assert summary["private_path_fields"] == 0


def test_script_rejects_plan_digest_before_source_or_controller_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _ = _inputs(tmp_path)
    args.expected_plan_sha256 = "0" * 64
    touched = False

    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal touched
        touched = True
        raise AssertionError("source access must not occur")

    monkeypatch.setitem(GLOBALS, "detect_source_identity", forbidden)

    with pytest.raises(MaterializationError, match="plan digest differs"):
        SCRIPT["_run"](args)
    assert not touched


def test_script_rejects_existing_output_before_reading_private_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _ = _inputs(tmp_path)
    args.out_state.write_bytes(b"existing")
    touched = False

    def forbidden(path, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal touched
        touched = True
        raise AssertionError("plan must not be read")

    monkeypatch.setitem(GLOBALS, "_read_bounded", forbidden)

    with pytest.raises(MaterializationError, match="already exists"):
        SCRIPT["_run"](args)
    assert not touched
