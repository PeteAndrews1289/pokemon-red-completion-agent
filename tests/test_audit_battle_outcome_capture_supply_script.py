from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleOutcomeCaptureAuthenticationError,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/audit_battle_outcome_capture_supply.py")
GLOBALS = SCRIPT["_run"].__globals__


def test_cli_has_no_state_rom_model_or_gameplay_input() -> None:
    destinations = {
        action.dest for action in SCRIPT["_parser"]()._actions  # noqa: SLF001
    }

    assert "development_manifest" in destinations
    assert not destinations.intersection(
        {"development_state", "rom", "base_model", "controller", "teacher"}
    )


def test_metadata_only_audit_reports_incompatible_supply_without_opening_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_payload = b"context"
    train_payload = b"train"
    context_sha256 = hashlib.sha256(context_payload).hexdigest()
    train_sha256 = hashlib.sha256(train_payload).hexdigest()
    registry_sha256 = "9" * 64
    registry_commit = "a" * 40
    producer_commit = "b" * 40
    payloads = {
        Path("context.json"): context_payload,
        Path("train.json"): train_payload,
        **{Path(f"development-{index}.json"): f"manifest-{index}".encode() for index in range(8)},
    }
    freezer = GLOBALS["freezer"]
    monkeypatch.setattr(
        freezer,
        "_read_bounded_private_file",
        lambda path, **_kwargs: payloads[path],
    )
    monkeypatch.setattr(
        freezer,
        "_development_catalogs",
        lambda _value: {
            producer_commit: (
                "8" * 64,
                {
                    f"capture-{index}": (f"{index + 1:x}" * 64, f"root-{index}")
                    for index in range(8)
                },
            )
        },
    )
    monkeypatch.setitem(
        GLOBALS,
        "load_committed_goal_manager_registry_at_revision",
        lambda _root, _commit: SimpleNamespace(registry_sha256=registry_sha256),
    )
    monkeypatch.setitem(
        GLOBALS,
        "parse_goal_manager_context_catalog",
        lambda _payload, _registry: object(),
    )
    monkeypatch.setitem(
        GLOBALS,
        "parse_battle_scenario_capture_catalog",
        lambda _payload: SimpleNamespace(
            producers=(
                SimpleNamespace(
                    context_catalog_sha256=context_sha256,
                    registry_sha256=registry_sha256,
                    registry_source_commit=registry_commit,
                ),
                SimpleNamespace(
                    context_catalog_sha256=context_sha256,
                    registry_sha256=registry_sha256,
                    registry_source_commit=registry_commit,
                ),
            ),
            captures=tuple(range(7)),
        ),
    )

    manifests = {
        f"manifest-{index}".encode(): SimpleNamespace(
            capture_id=f"capture-{index}",
            source_state_sha256=f"{index + 1:x}" * 64,
            root_lineage_id=f"root-{index}",
            partition=ScenarioPartition.DEVELOPMENT,
            source_commit=producer_commit,
        )
        for index in range(8)
    }
    monkeypatch.setitem(
        GLOBALS,
        "parse_battle_scenario_capture_manifest",
        manifests.__getitem__,
    )

    def reject_current_catalog(*_args: object, **_kwargs: object) -> None:
        raise BattleOutcomeCaptureAuthenticationError("different experiment")

    monkeypatch.setitem(
        GLOBALS,
        "authenticate_battle_scenario_source_binding",
        reject_current_catalog,
    )
    args = SimpleNamespace(
        registry_source_commit=registry_commit,
        expected_registry_sha256=registry_sha256,
        context_catalog=Path("context.json"),
        expected_context_catalog_sha256=context_sha256,
        train_capture_catalog=Path("train.json"),
        expected_train_capture_catalog_sha256=train_sha256,
        development_producer_catalog=[[producer_commit, "catalog", "7" * 64]],
        development_manifest=[
            [producer_commit, f"development-{index}.json"] for index in range(8)
        ],
        required_development_contexts=8,
    )

    receipt = SCRIPT["_run"](args)

    assert receipt["status"] == "insufficient_compatible_supply"
    assert receipt["train_captures"] == 7
    assert receipt["development_manifests"] == 8
    assert receipt["producer_membership_matches"] == 8
    assert receipt["partition_matches"] == 8
    assert receipt["source_commit_matches"] == 8
    assert receipt["source_catalog_matches"] == 0
    assert receipt["lineage_matches"] == 0
    assert receipt["compatible_development_captures"] == 0
    assert receipt["development_deficit"] == 8
    assert receipt["state_files_opened"] == 0
    assert receipt["controller_actions"] == 0
    assert receipt["emulator_frames"] == 0
