from __future__ import annotations

import ast
import hashlib
import json
import runpy
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.party_development_inventory import (
    PartyDevelopmentInventoryEntry,
    PartyDevelopmentInventoryMember,
)
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
)
from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_red_party_development_frozen_catalog.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_private_loader_requires_external_exact_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "private.json"
    payload = b'{"schema":"private-test-v1"}\n'
    path.write_bytes(payload)

    document, observed = SCRIPT["_load_private_json"](
        path,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        subject="test input",
    )

    assert document == {"schema": "private-test-v1"}
    assert observed == payload
    with pytest.raises(RuntimeError, match="digest or size differs"):
        SCRIPT["_load_private_json"](
            path,
            expected_sha256="0" * 64,
            subject="test input",
        )
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_load_private_json"](
            PROJECT_ROOT / "private.json",
            expected_sha256="0" * 64,
            subject="test input",
        )


def test_catalog_scan_rejects_generic_paths_and_target_fields() -> None:
    scan = SCRIPT["_require_no_path_or_target"]

    scan({"safe": ["relative-id", "a" * 64]})
    with pytest.raises(RuntimeError, match="private path"):
        scan({"unsafe": "/private/example.state"})
    with pytest.raises(RuntimeError, match="target field"):
        scan({"selected_candidate_index": 0})


def test_inventory_extension_requires_exact_old_rows_plus_two_new_ids() -> None:
    old_a = SimpleNamespace(checkpoint_id="old-a", marker=1)
    old_b = SimpleNamespace(checkpoint_id="old-b", marker=2)
    new_a = SimpleNamespace(checkpoint_id="new-a", marker=3)
    new_b = SimpleNamespace(checkpoint_id="new-b", marker=4)
    previous = SimpleNamespace(entries=(old_a, old_b))
    current = SimpleNamespace(entries=(old_a, old_b, new_a, new_b))
    require_extension = SCRIPT["_require_inventory_extension"]

    require_extension(previous, current, output_capture_ids={"new-a", "new-b"})
    drifted_old_a = SimpleNamespace(checkpoint_id="old-a", marker=99)
    with pytest.raises(RuntimeError, match="exact historical inventory"):
        require_extension(
            previous,
            SimpleNamespace(entries=(drifted_old_a, old_b, new_a, new_b)),
            output_capture_ids={"new-a", "new-b"},
        )
    with pytest.raises(RuntimeError, match="exact historical inventory"):
        require_extension(
            previous,
            SimpleNamespace(entries=(old_a, old_b, new_a)),
            output_capture_ids={"new-a", "new-b"},
        )


def test_question_paths_rejects_a_symlinked_catalog_directory(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    target = tmp_path / "capture-target"
    target.mkdir()
    catalog.mkdir()
    (catalog / "profiles").mkdir()
    (catalog / "captures").symlink_to(target, target_is_directory=True)

    with pytest.raises(RuntimeError, match="directory is invalid"):
        SCRIPT["_question_paths"](
            catalog,
            capture_id="capture",
            profile_id="profile",
        )


def test_exact_ci_authentication_requires_the_named_green_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = 12345
    commit = "a" * 40
    response = {
        "attempt": 1,
        "conclusion": "success",
        "databaseId": run,
        "event": "pull_request",
        "headSha": commit,
        "status": "completed",
        "url": (
            f"https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/runs/{run}"
        ),
        "workflowName": "CI",
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(response),
        ),
    )

    assert (
        SCRIPT["_require_exact_green_ci_run"](
            run,
            1,
            source_commit=commit,
        )
        == response
    )

    response["headSha"] = "b" * 40
    with pytest.raises(RuntimeError, match="not the exact successful"):
        SCRIPT["_require_exact_green_ci_run"](
            run,
            1,
            source_commit=commit,
        )
    response["headSha"] = commit
    response["attempt"] = True
    with pytest.raises(RuntimeError, match="not the exact successful"):
        SCRIPT["_require_exact_green_ci_run"](
            run,
            1,
            source_commit=commit,
        )
    with pytest.raises(RuntimeError, match="CI binding is invalid"):
        SCRIPT["_require_exact_green_ci_run"](
            True,
            1,
            source_commit=commit,
        )


def test_reservation_source_join_rejects_each_recorded_semantic_drift() -> None:
    members = tuple(
        sorted(
            (
                PartyDevelopmentInventoryMember(
                    level=20,
                    hp_bin="low",
                    pp_bin="middle",
                    status_present=False,
                    trainable=True,
                    evolution_routes=(EvolutionRouteKind.LEVEL,),
                    level_evolution_distance_bin="near",
                    registration_target_needed=True,
                    living_target_needed=True,
                    role_complete=False,
                ),
                PartyDevelopmentInventoryMember(
                    level=40,
                    hp_bin="high",
                    pp_bin="high",
                    status_present=False,
                    trainable=True,
                    evolution_routes=(EvolutionRouteKind.NONE,),
                    level_evolution_distance_bin="none",
                    registration_target_needed=False,
                    living_target_needed=False,
                    role_complete=True,
                ),
            ),
            key=lambda item: item.semantic_tuple(),
        )
    )
    entry = PartyDevelopmentInventoryEntry(
        checkpoint_id="audit-source",
        partition=ScenarioPartition.TRAIN,
        state_sha256="a" * 64,
        envelope_sha256="b" * 64,
        controls_ready=True,
        battle_active=False,
        members=members,
        registration_owned_count=20,
        registration_target_count=124,
        living_unique_count=18,
        living_target_count=120,
        specimen_count=22,
        role_coverage_count=1,
        role_target_count=6,
        storage_headroom=200,
        goal_hints=tuple(PartyDevelopmentGoal),
    )
    reservation = PartyDevelopmentQuestionReservation(
        scenario_id="audit-question",
        source_checkpoint_id=entry.checkpoint_id,
        source_state_sha256=entry.state_sha256,
        source_envelope_sha256=entry.envelope_sha256,
        source_semantic_signature_sha256=entry.semantic_signature_sha256,
        partition=entry.partition,
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.COLLECTION,
        preparation=PartyDevelopmentContextPreparation.NONE,
        target_pp_bin=None,
        source_member_count=2,
        source_trainable_count=2,
        source_hp_bins=("low", "high"),
        source_pp_bins=("middle", "high"),
        source_evolution_route_kinds=(
            EvolutionRouteKind.NONE,
            EvolutionRouteKind.LEVEL,
        ),
    )
    matches = SCRIPT["_entry_matches_reservation_source"]

    assert matches(entry, reservation)
    assert not matches(replace(entry, controls_ready=False), reservation)
    assert not matches(replace(entry, battle_active=True), reservation)
    mutations = (
        replace(reservation, source_state_sha256="c" * 64),
        replace(reservation, source_envelope_sha256="c" * 64),
        replace(reservation, source_semantic_signature_sha256="c" * 64),
        replace(reservation, source_member_count=3),
        replace(reservation, source_hp_bins=("high",)),
        replace(reservation, source_pp_bins=("high",)),
        replace(
            reservation,
            source_evolution_route_kinds=(EvolutionRouteKind.LEVEL,),
        ),
    )
    assert all(not matches(entry, mutation) for mutation in mutations)


def test_catalog_auditor_has_no_actor_answer_learning_or_write_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any(
        token in module
        for module in imported_modules
        for token in ("executor", "outcome_learning", "teacher")
    )
    assert called_names.isdisjoint(
        {"CountingExecutor", "FrameSafeExecutor", "run_red_team_balancing"}
    )
    assert called_attributes.isdisjoint(
        {
            "execute",
            "hold",
            "press",
            "release",
            "send_input",
            "tick",
            "write_bytes",
            "write_text",
        }
    )
    for required_seam in (
        "committed_source_bundle_sha256",
        "authenticated_root_lineage_id",
        "RedPartyDevelopmentQuestionPreflight",
        "expected_question != question",
        "prepared_partition_counts",
        "materialization_manifest_paths",
        "_entry_matches_reservation_source",
        "protected_expected",
        "audit_committed_bundle",
        "audit_script_sha256",
    ):
        assert required_seam in source
    assert '"answers_selected": 0' in source
    assert '"outcomes_opened": 0' in source
    assert '"controller_actions": 0' in source
    assert '"teacher_queries": 0' in source
