from __future__ import annotations

import argparse
import ast
import hashlib
import json
import runpy
import stat
from pathlib import Path

import pytest

from pokemon_red_completion.collection_protocol import (
    committed_source_bundle_sha256,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import SourceIdentity, detect_source_identity

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "compose_red_party_development_venue_prior.py"
)
SCRIPT = runpy.run_path(str(SCRIPT_PATH))
GLOBALS = SCRIPT["_run"].__globals__
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-plan-v2-2026-08-14.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-result-v2-2026-08-14.json"
)


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        plan=PLAN_PATH,
        result=RESULT_PATH,
        out_registry=tmp_path / "private-registry.json",
        out_summary=tmp_path / "public-summary.json",
    )


def test_script_writes_one_exclusive_private_registry_and_path_free_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = detect_source_identity(PROJECT_ROOT)
    assert identity.git_commit is not None
    current_commit = identity.git_commit
    current_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=current_commit,
    )
    monkeypatch.setitem(
        GLOBALS,
        "detect_source_identity",
        lambda _root: SourceIdentity(current_commit, False),
    )
    monkeypatch.setitem(
        GLOBALS,
        "require_published_source",
        lambda _root, _identity: None,
    )
    monkeypatch.setitem(
        GLOBALS,
        "working_source_bundle_sha256",
        lambda _root: current_bundle,
    )
    args = _args(tmp_path)

    returned = SCRIPT["_run"](args)
    private_payload = args.out_registry.read_bytes()
    public_payload = args.out_summary.read_bytes()
    registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        json.loads(private_payload.decode("ascii"))
    )
    public = json.loads(public_payload.decode("ascii"))

    assert registry.source_commit == current_commit
    assert registry.source_bundle_sha256 == current_bundle
    assert len(registry.entries) == 1
    assert public["private_registry_file_sha256"] == hashlib.sha256(
        private_payload
    ).hexdigest()
    assert returned["public_summary_file_sha256"] == hashlib.sha256(
        public_payload
    ).hexdigest()
    assert stat.S_IMODE(args.out_registry.stat().st_mode) == 0o600
    assert stat.S_IMODE(args.out_summary.stat().st_mode) == 0o600
    assert "/Users/" not in public_payload.decode("ascii")
    assert "/Volumes/" not in public_payload.decode("ascii")
    with pytest.raises(FileExistsError):
        SCRIPT["_run"](args)


def test_script_refuses_to_put_the_private_registry_in_the_repository(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path)
    args.out_registry = PROJECT_ROOT / "private-venue-registry-must-not-exist.json"

    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_run"](args)

    assert not args.out_registry.exists()


def test_script_has_no_game_execution_or_teacher_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
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
        for token in ("emulator", "rom", "controller", "teacher")
    )
    assert called_names.isdisjoint(
        {"PyBoyAdapter", "resolve_rom_path", "verify_rom", "run_red_team_balancing"}
    )
    assert called_attributes.isdisjoint(
        {"tick", "press", "hold", "release", "send_input", "execute", "load_state"}
    )
