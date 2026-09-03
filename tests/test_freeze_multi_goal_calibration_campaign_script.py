from __future__ import annotations

import hashlib
import json
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.multi_goal_calibration_plan import (
    build_multi_goal_calibration_schedule,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "freeze_multi_goal_calibration_campaign.py")
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _root(
    slot: str,
    focus: GoalKind,
    menu: tuple[GoalKind, ...],
) -> SimpleNamespace:
    return SimpleNamespace(
        entry=SimpleNamespace(slot_id=slot),
        assignment=SimpleNamespace(partition="train", focus_kind=focus),
        capture=SimpleNamespace(
            state_sha256=_sha(f"{slot}:state"),
            envelope_sha256=_sha(f"{slot}:envelope"),
        ),
        profile_file_sha256=_sha(f"{slot}:profile"),
        available_goal_kinds=tuple(kind.value for kind in menu),
    )


def _roots() -> tuple[SimpleNamespace, ...]:
    return (
        _root(
            "develop-open",
            GoalKind.DEVELOP_TEAM,
            (GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY),
        ),
        _root(
            "evolve-open",
            GoalKind.EVOLVE_SPECIES,
            (GoalKind.EVOLVE_SPECIES, GoalKind.EXPLORE),
        ),
        _root(
            "storage-open-a",
            GoalKind.MANAGE_STORAGE,
            (GoalKind.MANAGE_STORAGE, GoalKind.ACQUIRE_SPECIES),
        ),
        _root(
            "storage-open-b",
            GoalKind.MANAGE_STORAGE,
            (GoalKind.RECOVER_CONTROL, GoalKind.MANAGE_STORAGE, GoalKind.DEVELOP_TEAM),
        ),
    )


def _readiness(roots: tuple[SimpleNamespace, ...]) -> SimpleNamespace:
    base = SimpleNamespace(
        candidate=SimpleNamespace(
            registry=SimpleNamespace(
                assignment=lambda slot: next(
                    root.assignment for root in roots if root.entry.slot_id == slot
                )
            )
        ),
        context_plan_sha256=_sha("context-plan"),
        entries=tuple(root.entry for root in roots),
        numpy_runtime_sha256=_sha("numpy"),
        rom_path=Path("rom.gb"),
        runtime=SimpleNamespace(sha256=_sha("runtime")),
        skill_manifest_sha256=_sha("skills"),
        source=SimpleNamespace(git_commit="a" * 40),
        source_bundle_sha256=_sha("source-bundle"),
    )
    return SimpleNamespace(
        development=base,
        runner_sha256=_sha("runner"),
        development_runner_sha256=_sha("development-runner"),
    )


def test_candidate_projection_preserves_menu_positions_and_root_identity() -> None:
    root = _roots()[0]

    candidate = SCRIPT["_candidate_from_root"](root, claim_available=True)

    assert candidate.slot_id == "develop-open"
    assert candidate.focus_kind is GoalKind.DEVELOP_TEAM
    assert candidate.available_goal_kinds == (
        GoalKind.DEVELOP_TEAM,
        GoalKind.ADVANCE_STORY,
    )
    assert candidate.physical_root_sha256 == SCRIPT["root_consumption_sha256"](
        state_sha256=root.capture.state_sha256,
        envelope_sha256=root.capture.envelope_sha256,
    )


def test_compose_plan_binds_schedule_roots_and_trial_claims(monkeypatch) -> None:
    roots = _roots()
    candidates = tuple(
        SCRIPT["_candidate_from_root"](root, claim_available=True) for root in roots
    )
    schedule = build_multi_goal_calibration_schedule(candidates)
    readiness = _readiness(roots)
    development = SCRIPT["_compose_plan"].__globals__["development"]
    monkeypatch.setattr(
        development,
        "_private_root_record",
        lambda root: {"slot_id": root.entry.slot_id},
    )
    monkeypatch.setattr(
        development,
        "_candidate_identity",
        lambda _base: {"model_canonical_sha256": _sha("model")},
    )

    first = SCRIPT["_compose_plan"](
        readiness,
        schedule,
        selected_roots=roots,
        private_root_identity=_sha("private-root"),
        inventory_result_sha256=_sha("inventory"),
    )
    second = SCRIPT["_compose_plan"](
        readiness,
        schedule,
        selected_roots=roots,
        private_root_identity=_sha("private-root"),
        inventory_result_sha256=_sha("inventory"),
    )

    assert first == second
    assert first["schema"] == "pokemon.red.multi-goal-calibration-campaign.v1"
    assert first["schedule_sha256"] == schedule.schedule_sha256
    assert len(first["roots"]) == 4
    assert len(first["trials"]) == 8
    assert len({trial["trial_claim_sha256"] for trial in first["trials"]}) == 8
    assert all(trial["maximum_decisions"] == 1 for trial in first["trials"])


def test_freeze_is_action_free_and_writes_one_bound_plan(tmp_path: Path, monkeypatch) -> None:
    roots = _roots()
    readiness = _readiness(roots)
    destination = tmp_path / "campaign.json"
    args = SimpleNamespace(
        campaign_plan=destination,
        private_root=tmp_path,
        expected_inventory_result_sha256=_sha("inventory"),
    )
    development = SCRIPT["_freeze"].__globals__["development"]
    root_by_slot = {root.entry.slot_id: root for root in roots}
    writes: list[bytes] = []
    monkeypatch.setattr(development, "_new_external_file", lambda path, **_kw: path)
    monkeypatch.setattr(development, "_file_sha256", lambda _path: _sha("inventory"))
    monkeypatch.setattr(
        development,
        "_open_bound_private_root",
        lambda *_args, **_kwargs: (object(), _sha("private-root")),
    )
    monkeypatch.setattr(development, "rom_adjacent_artifacts", lambda _path: ())
    monkeypatch.setattr(development, "_historical_root_is_open", lambda *_args: True)
    monkeypatch.setattr(
        development,
        "_inspect_root",
        lambda _base, entry, **_kwargs: root_by_slot[entry.slot_id],
    )
    monkeypatch.setattr(
        development,
        "_private_root_record",
        lambda root: {"slot_id": root.entry.slot_id},
    )
    monkeypatch.setattr(
        development,
        "_candidate_identity",
        lambda _base: {"model_canonical_sha256": _sha("model")},
    )
    monkeypatch.setattr(development, "_write_exclusive", lambda _path, data: writes.append(data))
    monkeypatch.setitem(
        SCRIPT["_freeze"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: tmp_path,
    )
    monkeypatch.setitem(
        SCRIPT["_freeze"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda _registry, *, exclusive: nullcontext(),
    )

    result = SCRIPT["_freeze"](args, readiness)

    assert result["status"] == "compact_train_calibration_campaign_frozen"
    assert result["root_count"] == 4
    assert result["trial_count"] == 8
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0
    assert len(writes) == 1
    plan = json.loads(writes[0])
    assert len(plan["roots"]) == 4
    assert len(plan["trials"]) == 8


def test_compose_plan_rejects_a_root_order_mismatch(monkeypatch) -> None:
    roots = _roots()
    schedule = build_multi_goal_calibration_schedule(
        tuple(SCRIPT["_candidate_from_root"](root, claim_available=True) for root in roots)
    )
    development = SCRIPT["_compose_plan"].__globals__["development"]
    monkeypatch.setattr(development, "_private_root_record", lambda _root: {})
    monkeypatch.setattr(development, "_candidate_identity", lambda _base: {})

    with pytest.raises(SCRIPT["FreezeMultiGoalCalibrationError"], match="schedule_root_join"):
        SCRIPT["_compose_plan"](
            _readiness(roots),
            schedule,
            selected_roots=tuple(reversed(roots)),
            private_root_identity=_sha("private-root"),
            inventory_result_sha256=_sha("inventory"),
        )
