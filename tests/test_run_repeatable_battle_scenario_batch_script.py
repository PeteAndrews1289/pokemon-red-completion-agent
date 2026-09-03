from __future__ import annotations

import hashlib
import json
import runpy
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

SCRIPT = runpy.run_path("scripts/run_repeatable_battle_scenario_batch.py")
GLOBALS = SCRIPT["_run"].__globals__


def _source(
    source_id: str,
    partition: ScenarioPartition,
    state_bytes: bytes,
    menu_character: str,
) -> RepeatableBattleSourceObservation:
    return RepeatableBattleSourceObservation(
        source_id=source_id,
        source_lineage_id=f"lineage-{source_id}",
        partition=partition,
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        source_commit="a" * 40,
        expected_map=22,
        source_kind=RepeatableBattleSourceKind.FIELD,
        active_party_index=None,
        reachable_venue_ids=("route_11",),
        party_options=(
            RepeatableBattlePartyOption(0, menu_character * 64, 3, 1.0),
        ),
    )


def _payload(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("ascii")


def _inputs(tmp_path: Path, *, limit: int = 0) -> tuple[SimpleNamespace, dict[str, object]]:
    source_rows = (
        ("train-a", ScenarioPartition.TRAIN, b"train-a", "1"),
        ("train-b", ScenarioPartition.TRAIN, b"train-b", "2"),
        ("dev-a", ScenarioPartition.DEVELOPMENT, b"dev-a", "3"),
    )
    sources = tuple(_source(*row) for row in source_rows)
    plan = build_repeatable_battle_scenario_plan(
        sources,
        seed=1289,
        training_scenarios=2,
        development_scenarios=1,
        wait_frame_offsets=(0,),
    )
    plan_payload = _payload(plan.private_dict())
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(plan_payload)
    catalog_sources = []
    by_id: dict[str, object] = {}
    for source, (_, _, state_bytes, _) in zip(sources, source_rows, strict=True):
        state_path = tmp_path / f"{source.source_id}.state"
        state_path.write_bytes(state_bytes)
        catalog_sources.append(
            {
                "source_id": source.source_id,
                "source_lineage_id": source.source_lineage_id,
                "partition": source.partition.value,
                "state_path": str(state_path),
                "source_commit": source.source_commit,
            }
        )
        by_id[source.source_id] = source
    zero_coverage = {
        "scenarios": 0,
        "source_lineages": 0,
        "source_states": 0,
        "party_menus": 0,
        "semantic_setups": 0,
        "venues": 0,
        "battle_kinds": 0,
    }
    catalog = {
        "schema": "pokemon-private-repeatable-battle-source-catalog-v1",
        "seed": 1289,
        "training_scenarios": 2,
        "development_scenarios": 1,
        "wait_frame_offsets": [0],
        "minimum_coverage": {
            "train": zero_coverage,
            "development": zero_coverage,
        },
        "sources": catalog_sources,
    }
    catalog_payload = _payload(catalog)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(catalog_payload)
    rom_path = tmp_path / "red.gb"
    rom_path.write_bytes(b"rom")
    output_dir = tmp_path / "captures"
    output_dir.mkdir()
    args = SimpleNamespace(
        private_plan=plan_path,
        expected_plan_sha256=plan.sha256,
        source_catalog=catalog_path,
        expected_source_catalog_sha256=hashlib.sha256(catalog_payload).hexdigest(),
        output_dir=output_dir,
        journal=tmp_path / "journal.json",
        progress=tmp_path / "progress.json",
        partition="train",
        rom=rom_path,
        limit=limit,
        maximum_encounter_steps=32,
        watch=False,
        speed=None,
    )
    return args, by_id


def _install_preflight_fakes(
    monkeypatch: pytest.MonkeyPatch,
    sources: dict[str, object],
) -> None:
    monkeypatch.setitem(
        GLOBALS,
        "detect_source_identity",
        lambda *args, **kwargs: SimpleNamespace(git_commit="b" * 40),
    )
    monkeypatch.setitem(GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(GLOBALS, "require_published_source", lambda *args: None)
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda value: value)
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="c" * 64),
    )
    monkeypatch.setitem(
        GLOBALS,
        "inspect_repeatable_red_battle_source",
        lambda state_bytes, **kwargs: sources[kwargs["source_id"]],
    )


def test_batch_retains_success_and_failure_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, sources = _inputs(tmp_path)
    assert hashlib.sha256(args.private_plan.read_bytes()).hexdigest() != (
        args.expected_plan_sha256
    )
    _install_preflight_fakes(monkeypatch, sources)
    calls: list[str] = []

    def materialize(source, assignment, state_bytes, **kwargs):  # type: ignore[no-untyped-def]
        del source, state_bytes, kwargs
        calls.append(assignment.scenario_id)
        if len(calls) == 2:
            raise RuntimeError("bounded natural route failed")
        return SimpleNamespace(
            state_bytes=f"state-{assignment.scenario_id}".encode("ascii"),
            manifest_payload=f"manifest-{assignment.scenario_id}".encode("ascii"),
        )

    monkeypatch.setitem(GLOBALS, "materialize_repeatable_red_battle_scenario", materialize)

    summary = SCRIPT["_run"](args)

    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["pending"] == 0
    assert summary["model_fits"] == 0
    assert summary["outcomes"] == 0
    assert len(calls) == 2
    journal = json.loads(args.journal.read_text("ascii"))
    assert [row["status"] for row in journal["assignments"]] == ["succeeded", "failed"]
    assert journal["assignments"][1]["reason"] == "bounded natural route failed"
    assert "reason" not in json.loads(args.progress.read_text("ascii"))

    monkeypatch.setitem(
        GLOBALS,
        "materialize_repeatable_red_battle_scenario",
        lambda *args, **kwargs: pytest.fail("terminal assignment executed again"),
    )
    assert SCRIPT["_run"](args) == summary


def test_interrupted_started_assignment_is_never_retried_but_pending_work_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, sources = _inputs(tmp_path, limit=1)
    _install_preflight_fakes(monkeypatch, sources)
    monkeypatch.setitem(
        GLOBALS,
        "materialize_repeatable_red_battle_scenario",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        SCRIPT["_run"](args)
    interrupted = json.loads(args.journal.read_text("ascii"))
    assert [row["status"] for row in interrupted["assignments"]] == ["started", "pending"]

    resumed: list[str] = []

    def finish(source, assignment, state_bytes, **kwargs):  # type: ignore[no-untyped-def]
        del source, state_bytes, kwargs
        resumed.append(assignment.scenario_id)
        return SimpleNamespace(state_bytes=b"state", manifest_payload=b"manifest")

    monkeypatch.setitem(GLOBALS, "materialize_repeatable_red_battle_scenario", finish)
    summary = SCRIPT["_run"](args)

    assert len(resumed) == 1
    assert summary["started"] == 1
    assert summary["succeeded"] == 1
    assert summary["completed"] == 2


def test_batch_rejects_catalog_binding_drift_before_source_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _ = _inputs(tmp_path)
    catalog = json.loads(args.source_catalog.read_text("ascii"))
    catalog["sources"][0]["source_lineage_id"] = "different-lineage"
    changed = _payload(catalog)
    args.source_catalog.write_bytes(changed)
    args.expected_source_catalog_sha256 = hashlib.sha256(changed).hexdigest()
    touched = False

    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal touched
        touched = True
        raise AssertionError("source must remain closed")

    monkeypatch.setitem(GLOBALS, "detect_source_identity", forbidden)

    with pytest.raises(SCRIPT["RepeatableBattleScenarioBatchError"], match="catalog differs"):
        SCRIPT["_run"](args)
    assert not touched


def test_batch_rejects_impossible_retained_status_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, sources = _inputs(tmp_path, limit=0)
    _install_preflight_fakes(monkeypatch, sources)
    monkeypatch.setitem(
        GLOBALS,
        "materialize_repeatable_red_battle_scenario",
        lambda source, assignment, state_bytes, **kwargs: SimpleNamespace(
            state_bytes=f"state-{assignment.scenario_id}".encode("ascii"),
            manifest_payload=f"manifest-{assignment.scenario_id}".encode("ascii"),
        ),
    )
    SCRIPT["_run"](args)
    journal = json.loads(args.journal.read_text("ascii"))
    journal["assignments"][0]["state_sha256"] = None
    args.journal.write_text(json.dumps(journal), encoding="ascii")

    with pytest.raises(
        SCRIPT["RepeatableBattleScenarioBatchError"],
        match="successful materialization journal result is invalid",
    ):
        SCRIPT["_run"](args)
