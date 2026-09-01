from __future__ import annotations

import hashlib
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "build_battle_scenario_capture_catalog.py"))
V2 = runpy.run_path(str(PROJECT_ROOT / "tests" / "test_battle_scenario_materialization_plan_v2.py"))


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _directory_sha(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def _identity(plan, *, source: str):  # type: ignore[no-untyped-def]
    return BattleScenarioMaterializationRunIdentity(
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        source_commit=plan.source_commit,
        source_bundle_sha256=plan.source_bundle_sha256,
        materializer_sha256=_sha(f"materializer-{source}"),
        runtime_identity_sha256=_sha(f"runtime-{source}"),
        rom_sha256=plan.rom_sha256,
        capture_directory_sha256=plan.capture_directory_sha256,
        context_catalog_sha256=_sha("catalog"),
        registry_sha256=_sha("registry"),
        registry_source_commit="a" * 40,
        exact_ci_run=100 if source == "predecessor" else 101,
        exact_ci_attempt=1,
    )


def _terminal_predecessor(directory: Path):  # type: ignore[no-untyped-def]
    plan = replace(V2["_build"](), capture_directory_sha256=_directory_sha(directory))
    journal = initialize_battle_scenario_materialization_run(
        plan,
        _identity(plan, source="predecessor"),
    )
    successes = {0, 2, 4, 5, 6}
    retained = []
    for assignment in plan.assignments:
        journal = start_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
        )
        if assignment.ordinal not in successes:
            journal = fail_battle_scenario_materialization_assignment(
                journal,
                assignment.ordinal,
                reason_code="terminal_failure",
            )
            continue
        state_sha = _sha(f"predecessor-state-{assignment.ordinal}")
        manifest_sha = _sha(f"predecessor-manifest-{assignment.ordinal}")
        journal = succeed_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
            state_sha256=state_sha,
            manifest_sha256=manifest_sha,
        )
        retained.append(
            RetainedBattleScenarioMaterializationCapture(
                ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=canonical_sha256(assignment.private_dict()),
                source_commit=plan.source_commit,
                source_state_sha256=(assignment.candidate.source.source_state_sha256),
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=assignment.selected_venue.venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=state_sha,
                manifest_sha256=manifest_sha,
            )
        )
    return plan, journal, tuple(retained)


def _terminal_completion(
    directory: Path,
    predecessor_plan,  # type: ignore[no-untyped-def]
    predecessor_journal,  # type: ignore[no-untyped-def]
    retained,  # type: ignore[no-untyped-def]
):
    plan = build_battle_scenario_materialization_completion_plan(
        plan_id="red-battle-v2-additive-completion",
        source_commit="c" * 40,
        source_bundle_sha256=_sha("completion-bundle"),
        rom_sha256=predecessor_plan.rom_sha256,
        capture_directory_sha256=_directory_sha(directory),
        earliest_excluded_plan_sha256=predecessor_plan.excluded_plan_sha256,
        earliest_excluded_run_journal_sha256=(predecessor_plan.excluded_run_journal_sha256),
        predecessor_plan_sha256=predecessor_plan.plan_sha256,
        predecessor_run_journal_sha256=predecessor_journal.journal_sha256,
        predecessor_capture_directory_sha256=(predecessor_plan.capture_directory_sha256),
        predecessor_failure_count=2,
        retained_successes=retained,
        candidates=tuple(V2["_candidate"](index) for index in range(20, 23)),
    )
    journal = initialize_battle_scenario_materialization_run(
        plan,
        _identity(plan, source="completion"),
    )
    for assignment in plan.assignments:
        journal = start_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
        )
        journal = succeed_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
            state_sha256=_sha(f"completion-state-{assignment.ordinal}"),
            manifest_sha256=_sha(f"completion-manifest-{assignment.ordinal}"),
        )
    return plan, journal


def _campaign(tmp_path: Path):  # type: ignore[no-untyped-def]
    predecessor_directory = tmp_path / "predecessor"
    completion_directory = tmp_path / "completion"
    predecessor_directory.mkdir()
    completion_directory.mkdir()
    predecessor_plan, predecessor_journal, retained = _terminal_predecessor(predecessor_directory)
    completion_plan, completion_journal = _terminal_completion(
        completion_directory,
        predecessor_plan,
        predecessor_journal,
        retained,
    )
    return (
        predecessor_directory,
        completion_directory,
        predecessor_plan,
        predecessor_journal,
        completion_plan,
        completion_journal,
    )


def _patch_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    def authenticate(assignment, **kwargs):  # type: ignore[no-untyped-def]
        producer = "completion" if kwargs["source_commit"] == "c" * 40 else "predecessor"
        return (
            _sha(f"{producer}-state-{assignment.ordinal}"),
            _sha(f"{producer}-manifest-{assignment.ordinal}"),
        )

    monkeypatch.setitem(
        SCRIPT["_catalog_entries"].__globals__,
        "_authenticate_assignment_outputs",
        authenticate,
    )


def test_mixed_catalog_reopens_only_seven_successes_and_keeps_producers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        predecessor_directory,
        completion_directory,
        predecessor_plan,
        predecessor_journal,
        completion_plan,
        completion_journal,
    ) = _campaign(tmp_path)
    _patch_authentication(monkeypatch)

    SCRIPT["_require_terminal_producer"](
        predecessor_plan,
        predecessor_journal,
        expected_successes=5,
        expected_failures=2,
        capture_directory=predecessor_directory,
    )
    SCRIPT["_require_terminal_producer"](
        completion_plan,
        completion_journal,
        expected_successes=2,
        expected_failures=0,
        capture_directory=completion_directory,
    )
    SCRIPT["_require_completion_lineage"](
        predecessor_plan,
        predecessor_journal,
        completion_plan,
    )
    old_entries, retained = SCRIPT["_catalog_entries"](
        producer_id="predecessor",
        plan=predecessor_plan,
        journal=predecessor_journal,
        capture_directory=predecessor_directory,
        rom_path=tmp_path / "red.gb",
    )
    new_entries, _ = SCRIPT["_catalog_entries"](
        producer_id="completion",
        plan=completion_plan,
        journal=completion_journal,
        capture_directory=completion_directory,
        rom_path=tmp_path / "red.gb",
    )

    assert len(old_entries) == 5
    assert len(new_entries) == 2
    assert retained == completion_plan.retained_successes
    assert {item.producer_ordinal for item in old_entries} == {0, 2, 4, 5, 6}
    assert {item.producer_id for item in (*old_entries, *new_entries)} == {
        "predecessor",
        "completion",
    }


def test_mixed_catalog_rejects_nonterminal_or_changed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        predecessor_directory,
        _completion_directory,
        predecessor_plan,
        predecessor_journal,
        _completion_plan,
        _completion_journal,
    ) = _campaign(tmp_path)
    monkeypatch.setitem(
        SCRIPT["_catalog_entries"].__globals__,
        "_authenticate_assignment_outputs",
        lambda *args, **kwargs: (_sha("changed"), _sha("changed-manifest")),
    )

    with pytest.raises(
        SCRIPT["BattleScenarioCaptureCatalogBuildError"],
        match="differs from its terminal journal",
    ):
        SCRIPT["_catalog_entries"](
            producer_id="predecessor",
            plan=predecessor_plan,
            journal=predecessor_journal,
            capture_directory=predecessor_directory,
            rom_path=tmp_path / "red.gb",
        )


def test_mixed_catalog_rejects_completion_reusing_a_predecessor_root(
    tmp_path: Path,
) -> None:
    (
        _predecessor_directory,
        _completion_directory,
        predecessor_plan,
        predecessor_journal,
        _completion_plan,
        _completion_journal,
    ) = _campaign(tmp_path)
    failed_predecessor_candidate = predecessor_plan.assignments[1].candidate
    forged = build_battle_scenario_materialization_completion_plan(
        plan_id="red-battle-v2-reused-failure",
        source_commit="c" * 40,
        source_bundle_sha256=_sha("completion-bundle"),
        rom_sha256=predecessor_plan.rom_sha256,
        capture_directory_sha256=_sha("completion-directory"),
        earliest_excluded_plan_sha256=predecessor_plan.excluded_plan_sha256,
        earliest_excluded_run_journal_sha256=(predecessor_plan.excluded_run_journal_sha256),
        predecessor_plan_sha256=predecessor_plan.plan_sha256,
        predecessor_run_journal_sha256=predecessor_journal.journal_sha256,
        predecessor_capture_directory_sha256=(predecessor_plan.capture_directory_sha256),
        predecessor_failure_count=2,
        retained_successes=tuple(
            RetainedBattleScenarioMaterializationCapture(
                ordinal=assignment.ordinal,
                capture_id=assignment.capture_id,
                assignment_sha256=canonical_sha256(assignment.private_dict()),
                source_commit=predecessor_plan.source_commit,
                source_state_sha256=(assignment.candidate.source.source_state_sha256),
                root_lineage_id=assignment.candidate.source.root_lineage_id,
                venue_id=assignment.selected_venue.venue_id,
                party_slot=assignment.party_slot,
                state_filename=assignment.state_filename,
                manifest_filename=assignment.manifest_filename,
                state_sha256=_sha(f"predecessor-state-{assignment.ordinal}"),
                manifest_sha256=_sha(f"predecessor-manifest-{assignment.ordinal}"),
            )
            for assignment in (
                predecessor_plan.assignments[0],
                predecessor_plan.assignments[2],
                predecessor_plan.assignments[4],
                predecessor_plan.assignments[5],
                predecessor_plan.assignments[6],
            )
        ),
        candidates=(
            failed_predecessor_candidate,
            V2["_candidate"](20),
        ),
    )

    with pytest.raises(
        SCRIPT["BattleScenarioCaptureCatalogBuildError"],
        match="lineage differs",
    ):
        SCRIPT["_require_completion_lineage"](
            predecessor_plan,
            predecessor_journal,
            forged,
        )


def test_catalog_cli_has_no_action_or_outcome_arguments() -> None:
    options = SCRIPT["_parser"]()._option_string_actions

    assert "--predecessor-plan" in options
    assert "--completion-plan" in options
    assert "--out-catalog" in options
    assert "--watch" not in options
    assert "--speed" not in options
    assert "--candidate" not in options
    assert "--outcome" not in options
    assert "--model" not in options


def test_catalog_reader_rejects_a_symlinked_private_input(tmp_path: Path) -> None:
    parent = tmp_path / "private"
    parent.mkdir()
    target = parent / "target.json"
    target.write_bytes(b"{}\n")
    target.chmod(0o600)
    link = parent / "link.json"
    link.symlink_to(target)

    with pytest.raises(
        SCRIPT["BattleScenarioCaptureCatalogBuildError"],
        match="unavailable",
    ):
        SCRIPT["_read_input"](
            link,
            parent=parent,
            maximum_bytes=100,
            subject="private input",
            expected_sha256=hashlib.sha256(b"{}\n").hexdigest(),
        )
