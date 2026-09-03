from __future__ import annotations

import hashlib
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.multi_goal_curriculum_inventory import (
    MultiGoalCurriculumInventoryError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/audit_multi_goal_curriculum_inventory.py")
)


def test_bound_reader_rejects_changed_input(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_bytes(b"{}\n")

    with pytest.raises(MultiGoalCurriculumInventoryError, match="digest differs"):
        SCRIPT["_read_bound"](path, "0" * 64, subject="context plan")


def test_run_passes_no_lineage_as_unresolved_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    plan = tmp_path / "plan.json"
    plan_payload = b'{"source_commit":"' + b"a" * 40 + b'"}\n'
    plan.write_bytes(plan_payload)
    profile_lineage = tmp_path / "profile-lineage.json"
    profile_payload = b"{}\n"
    profile_lineage.write_bytes(profile_payload)
    captured: dict[str, object] = {}

    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "load_committed_goal_manager_registry_at_revision",
        lambda root, commit: captured.update(root=root, commit=commit) or object(),
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: tmp_path,
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda _registry, *, exclusive: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "audit_multi_goal_curriculum_inventory",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(
            public_dict=lambda: {"status": "lineage_evidence_required"}
        ),
    )
    args = SimpleNamespace(
        plan=plan,
        expected_plan_sha256=hashlib.sha256(plan_payload).hexdigest(),
        profile_lineage=profile_lineage,
        expected_profile_lineage_sha256=hashlib.sha256(profile_payload).hexdigest(),
        lineage_manifest=None,
        expected_lineage_manifest_sha256=None,
    )

    result = SCRIPT["_run"](args)

    assert result == {"status": "lineage_evidence_required"}
    assert captured["commit"] == "a" * 40
    assert captured["lineage_manifest_payload"] is None
    assert list(tmp_path.iterdir()) == [plan, profile_lineage]
