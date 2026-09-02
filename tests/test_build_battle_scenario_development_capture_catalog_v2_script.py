from __future__ import annotations

import hashlib
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_development_capture_catalog import (
    BattleScenarioDevelopmentCaptureCatalogV2,
    parse_battle_scenario_development_capture_catalog,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (
    RetainedBattleScenarioMaterializationCapture,
    build_battle_scenario_materialization_completion_plan,
)
from pokemon_red_completion.battle_scenario_materialization_run import (
    BattleScenarioMaterializationRunIdentity,
    fail_battle_scenario_materialization_assignment,
    initialize_battle_scenario_materialization_run,
    start_battle_scenario_materialization_assignment,
    succeed_battle_scenario_materialization_assignment,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(
        PROJECT_ROOT
        / "scripts"
        / "build_battle_scenario_development_capture_catalog_v2.py"
    )
)
PLAN = runpy.run_path(
    str(PROJECT_ROOT / "tests" / "test_battle_scenario_materialization_plan_v2.py")
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _directory_sha(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def _identity(plan, *, role: str):  # type: ignore[no-untyped-def]
    return BattleScenarioMaterializationRunIdentity(
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        source_commit=plan.source_commit,
        source_bundle_sha256=plan.source_bundle_sha256,
        materializer_sha256=_sha(f"{role}-materializer"),
        runtime_identity_sha256=_sha("runtime"),
        rom_sha256=plan.rom_sha256,
        capture_directory_sha256=plan.capture_directory_sha256,
        context_catalog_sha256=_sha("catalog"),
        registry_sha256=_sha("registry"),
        registry_source_commit="a" * 40,
        exact_ci_run=100 if role == "predecessor" else 101,
        exact_ci_attempt=1,
    )


def _campaign(tmp_path: Path):  # type: ignore[no-untyped-def]
    predecessor_directory = tmp_path / "predecessor"
    completion_directory = tmp_path / "completion"
    output_directory = tmp_path / "catalog"
    for directory in (predecessor_directory, completion_directory, output_directory):
        directory.mkdir(mode=0o700)
    candidates = tuple(
        PLAN["_candidate"](index, partition=ScenarioPartition.DEVELOPMENT)
        for index in range(20)
    )
    predecessor_plan = replace(
        PLAN["_build"](candidates),
        capture_directory_sha256=_directory_sha(predecessor_directory),
    )
    predecessor_journal = initialize_battle_scenario_materialization_run(
        predecessor_plan,
        _identity(predecessor_plan, role="predecessor"),
    )
    retained = []
    for assignment in predecessor_plan.assignments:
        predecessor_journal = start_battle_scenario_materialization_assignment(
            predecessor_journal,
            assignment.ordinal,
        )
        if assignment.ordinal == 6:
            predecessor_journal = fail_battle_scenario_materialization_assignment(
                predecessor_journal,
                assignment.ordinal,
                reason_code="source_relocation_failed",
            )
            continue
        state_sha256 = _sha(f"predecessor-state-{assignment.ordinal}")
        manifest_sha256 = _sha(f"predecessor-manifest-{assignment.ordinal}")
        predecessor_journal = succeed_battle_scenario_materialization_assignment(
            predecessor_journal,
            assignment.ordinal,
            state_sha256=state_sha256,
            manifest_sha256=manifest_sha256,
        )
        retained.append(
            RetainedBattleScenarioMaterializationCapture(
                ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=canonical_sha256(assignment.private_dict()),
                source_commit=predecessor_plan.source_commit,
                source_state_sha256=assignment.candidate.source.source_state_sha256,
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=assignment.selected_venue.venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=state_sha256,
                manifest_sha256=manifest_sha256,
            )
        )
    completion_plan = build_battle_scenario_materialization_completion_plan(
        plan_id="red-battle-v2-development-completion",
        source_commit="c" * 40,
        source_bundle_sha256=_sha("completion-bundle"),
        rom_sha256=predecessor_plan.rom_sha256,
        capture_directory_sha256=_directory_sha(completion_directory),
        earliest_excluded_plan_sha256=predecessor_plan.excluded_plan_sha256,
        earliest_excluded_run_journal_sha256=(
            predecessor_plan.excluded_run_journal_sha256
        ),
        predecessor_plan_sha256=predecessor_plan.plan_sha256,
        predecessor_run_journal_sha256=predecessor_journal.journal_sha256,
        predecessor_capture_directory_sha256=(
            predecessor_plan.capture_directory_sha256
        ),
        predecessor_failure_count=1,
        retained_successes=tuple(retained),
        candidates=tuple(
            PLAN["_candidate"](index, partition=ScenarioPartition.DEVELOPMENT)
            for index in range(20, 24)
        ),
    )
    completion_journal = initialize_battle_scenario_materialization_run(
        completion_plan,
        _identity(completion_plan, role="completion"),
    )
    assignment = completion_plan.assignments[0]
    completion_journal = start_battle_scenario_materialization_assignment(
        completion_journal,
        assignment.ordinal,
    )
    completion_journal = succeed_battle_scenario_materialization_assignment(
        completion_journal,
        assignment.ordinal,
        state_sha256=_sha("completion-state-0"),
        manifest_sha256=_sha("completion-manifest-0"),
    )
    for directory, plan, journal in (
        (predecessor_directory, predecessor_plan, predecessor_journal),
        (completion_directory, completion_plan, completion_journal),
    ):
        (directory / "plan.json").write_bytes(plan.canonical_bytes())
        (directory / "journal.json").write_bytes(journal.canonical_bytes())
    args = SimpleNamespace(
        catalog_id="red-battle-v2-development-catalog-v2",
        expected_source_commit="f" * 40,
        expected_source_bundle_sha256=_sha("builder-bundle"),
        predecessor_plan=predecessor_directory / "plan.json",
        expected_predecessor_plan_sha256=predecessor_plan.plan_sha256,
        predecessor_journal=predecessor_directory / "journal.json",
        expected_predecessor_journal_sha256=predecessor_journal.journal_sha256,
        predecessor_capture_directory=predecessor_directory,
        completion_plan=completion_directory / "plan.json",
        expected_completion_plan_sha256=completion_plan.plan_sha256,
        completion_journal=completion_directory / "journal.json",
        expected_completion_journal_sha256=completion_journal.journal_sha256,
        completion_capture_directory=completion_directory,
        out_catalog=output_directory / "catalog.json",
        rom=tmp_path / "red.gb",
    )
    return args, predecessor_plan, completion_plan


def test_builder_preserves_development_seven_plus_one_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, predecessor_plan, completion_plan = _campaign(tmp_path)
    run = SCRIPT["_run"]
    globals_ = run.__globals__
    monkeypatch.setitem(
        globals_,
        "detect_source_identity",
        lambda *args, **kwargs: SimpleNamespace(git_commit="f" * 40),
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda source: None)
    monkeypatch.setitem(globals_, "require_published_source", lambda *args: None)
    monkeypatch.setitem(
        globals_,
        "working_source_bundle_sha256",
        lambda project: _sha("builder-bundle"),
    )
    monkeypatch.setitem(globals_, "resolve_rom_path", lambda path: path)
    monkeypatch.setitem(
        globals_,
        "verify_rom",
        lambda path: SimpleNamespace(sha256=predecessor_plan.rom_sha256),
    )
    def authenticate(assignment, **kwargs):  # type: ignore[no-untyped-def]
        role = (
            "completion"
            if kwargs["source_commit"] == completion_plan.source_commit
            else "predecessor"
        )
        return (
            _sha(f"{role}-state-{assignment.ordinal}"),
            _sha(f"{role}-manifest-{assignment.ordinal}"),
        )

    monkeypatch.setitem(
        SCRIPT["_catalog_entries"].__globals__,
        "_authenticate_assignment_outputs",
        authenticate,
    )

    receipt = run(args)
    catalog = parse_battle_scenario_development_capture_catalog(
        args.out_catalog.read_bytes()
    )

    assert receipt["capture_count"] == 8
    assert receipt["producer_count"] == 2
    assert isinstance(catalog, BattleScenarioDevelopmentCaptureCatalogV2)
    assert [item.producer_id for item in catalog.captures].count("predecessor") == 7
    assert [item.producer_id for item in catalog.captures].count("completion") == 1
    assert receipt["controller_actions"] == receipt["outcomes_opened"] == 0


def test_builder_rejects_changed_completion_lineage(tmp_path: Path) -> None:
    _args, predecessor_plan, completion_plan = _campaign(tmp_path)
    forged = replace(completion_plan, predecessor_plan_sha256=_sha("changed-plan"))

    with pytest.raises(
        SCRIPT["BattleScenarioDevelopmentCaptureCatalogV2BuildError"],
        match="lineage differs",
    ):
        SCRIPT["_require_completion_lineage"](
            predecessor_plan,
            initialize_battle_scenario_materialization_run(
                predecessor_plan,
                _identity(predecessor_plan, role="predecessor"),
            ),
            forged,
        )
