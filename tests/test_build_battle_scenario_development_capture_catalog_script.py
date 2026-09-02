from __future__ import annotations

import hashlib
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_development_capture_catalog import (
    parse_battle_scenario_development_capture_catalog,
)
from pokemon_red_completion.battle_scenario_materialization_run import (
    initialize_battle_scenario_materialization_run,
    start_battle_scenario_materialization_assignment,
    succeed_battle_scenario_materialization_assignment,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/build_battle_scenario_development_capture_catalog.py")
PLAN_HELPERS = runpy.run_path("tests/test_battle_scenario_materialization_plan_v2.py")
RUN_HELPERS = runpy.run_path("tests/test_battle_scenario_materialization_run.py")


def _sha(marker: str) -> str:
    return PLAN_HELPERS["_sha"](marker)


def _terminal_inputs(capture_directory: Path):  # type: ignore[no-untyped-def]
    candidates = tuple(
        PLAN_HELPERS["_candidate"](
            index,
            partition=ScenarioPartition.DEVELOPMENT,
        )
        for index in range(20)
    )
    plan = PLAN_HELPERS["_build"](candidates)
    plan = replace(
        plan,
        capture_directory_sha256=hashlib.sha256(
            str(capture_directory.resolve()).encode("utf-8")
        ).hexdigest(),
    )
    identity = replace(
        RUN_HELPERS["_identity"](plan),
        source_commit=plan.source_commit,
    )
    journal = initialize_battle_scenario_materialization_run(plan, identity)
    outputs: dict[int, tuple[str, str]] = {}
    for assignment in plan.assignments:
        state_sha256 = _sha(f"state-{assignment.ordinal}")
        manifest_sha256 = _sha(f"manifest-{assignment.ordinal}")
        outputs[assignment.ordinal] = state_sha256, manifest_sha256
        journal = start_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
        )
        journal = succeed_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
            state_sha256=state_sha256,
            manifest_sha256=manifest_sha256,
        )
    return plan, journal, outputs


def _args(tmp_path: Path, plan, journal):  # type: ignore[no-untyped-def]
    capture_directory = tmp_path / "captures"
    plan_path = capture_directory / "development-plan.json"
    journal_path = capture_directory / f"battle-materialization-{plan.plan_sha256}.journal.json"
    out_directory = tmp_path / "catalogs"
    out_directory.mkdir(mode=0o700)
    plan_path.write_bytes(plan.canonical_bytes())
    journal_path.write_bytes(journal.canonical_bytes())
    plan_path.chmod(0o600)
    journal_path.chmod(0o600)
    return SimpleNamespace(
        catalog_id="red-battle-v2-development-catalog",
        expected_source_commit="f" * 40,
        expected_source_bundle_sha256=_sha("builder-bundle"),
        plan=plan_path,
        expected_plan_sha256=plan.plan_sha256,
        journal=journal_path,
        expected_journal_sha256=journal.journal_sha256,
        capture_directory=capture_directory,
        out_catalog=out_directory / "development-catalog.json",
        rom=tmp_path / "red.gb",
    )


def _patch_action_free_builder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    capture_directory: Path,
    plan,
    outputs: dict[int, tuple[str, str]],
) -> None:  # type: ignore[no-untyped-def]
    run = SCRIPT["_run"]
    globals_ = run.__globals__
    monkeypatch.setitem(
        globals_,
        "detect_source_identity",
        lambda *args, **kwargs: SimpleNamespace(git_commit="f" * 40),
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda source: None)
    monkeypatch.setitem(
        globals_,
        "require_published_source",
        lambda project, source: None,
    )
    monkeypatch.setitem(
        globals_,
        "working_source_bundle_sha256",
        lambda project: _sha("builder-bundle"),
    )
    monkeypatch.setitem(globals_, "resolve_rom_path", lambda path: path)
    monkeypatch.setitem(
        globals_,
        "verify_rom",
        lambda path: SimpleNamespace(sha256=plan.rom_sha256),
    )
    monkeypatch.setitem(
        globals_,
        "_private_capture_directory",
        lambda path, **kwargs: capture_directory.resolve(),
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_assignment_outputs",
        lambda assignment, **kwargs: outputs[assignment.ordinal],
    )


def test_builder_authenticates_terminal_development_run_without_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_directory = tmp_path / "captures"
    capture_directory.mkdir(mode=0o700)
    plan, journal, outputs = _terminal_inputs(capture_directory)
    args = _args(tmp_path, plan, journal)
    _patch_action_free_builder(
        monkeypatch,
        capture_directory=capture_directory,
        plan=plan,
        outputs=outputs,
    )

    receipt = SCRIPT["_run"](args)
    catalog = parse_battle_scenario_development_capture_catalog(args.out_catalog.read_bytes())

    assert receipt["capture_count"] == 8
    assert receipt["venue_counts"] == {"digletts_cave": 4, "route_11": 4}
    assert receipt["controller_actions"] == 0
    assert receipt["outcomes_opened"] == 0
    assert receipt["model_fits"] == 0
    assert catalog.producer.run_journal_sha256 == journal.journal_sha256
    assert catalog.producer.plan_sha256 == plan.plan_sha256


def test_builder_rejects_an_alternate_journal_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_directory = tmp_path / "captures"
    capture_directory.mkdir(mode=0o700)
    plan, journal, outputs = _terminal_inputs(capture_directory)
    args = _args(tmp_path, plan, journal)
    alternate = capture_directory / "alternate-journal.json"
    alternate.write_bytes(journal.canonical_bytes())
    alternate.chmod(0o600)
    args.journal = alternate
    _patch_action_free_builder(
        monkeypatch,
        capture_directory=capture_directory,
        plan=plan,
        outputs=outputs,
    )

    with pytest.raises(
        SCRIPT["BattleScenarioDevelopmentCaptureCatalogBuildError"],
        match="not bound to its plan",
    ):
        SCRIPT["_run"](args)


def test_builder_rejects_a_nonterminal_development_denominator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_directory = tmp_path / "captures"
    capture_directory.mkdir(mode=0o700)
    plan, journal, outputs = _terminal_inputs(capture_directory)
    pending = initialize_battle_scenario_materialization_run(plan, journal.identity)
    args = _args(tmp_path, plan, pending)
    _patch_action_free_builder(
        monkeypatch,
        capture_directory=capture_directory,
        plan=plan,
        outputs=outputs,
    )

    with pytest.raises(
        SCRIPT["BattleScenarioDevelopmentCaptureCatalogBuildError"],
        match="terminal denominator differs",
    ):
        SCRIPT["_run"](args)
