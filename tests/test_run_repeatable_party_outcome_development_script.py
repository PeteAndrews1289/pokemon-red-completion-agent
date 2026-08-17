from __future__ import annotations

import hashlib
import json
import runpy
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.party_development_adapter import (
    PartyDevelopmentCapabilityState,
    PartyDevelopmentExecutionCapability,
)
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_development.py")
)


def _canonical_line(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _write_artifact(
    root: Path,
    *,
    assignments: list[dict[str, object]] | None = None,
    unique_root_count: int | None = None,
    kind: str = "repeatable_party_outcome_development",
) -> tuple[Path, dict[str, object], bytes]:
    artifact = root / "repeatable-party-development-test"
    artifact.mkdir()
    if assignments is None:
        assignments = [
            {
                "schema": "pokemon.core.repeatable-party-development-assignment.v1",
                "scenario_id": f"repeatable-party-{partition}-{index:03d}",
                "option_sha256": f"{index + 10:064x}",
                "root_lineage_id": f"fresh-root-{partition}-{index:03d}",
                "initial_state_sha256": f"{index + 1:064x}",
                "partition": partition,
                "kind": "trainee",
                "goal": "collection",
                "candidate_count": 3,
                "candidate_order_sha256": f"{index + 20:064x}",
                "timing_offset_frames": index,
                "candidate_feature_values_public": False,
                "private_path_fields": 0,
            }
            for index, partition in enumerate(("train", "development"))
        ]
    partition_counts = {
        partition: sum(item["partition"] == partition for item in assignments)
        for partition in ("train", "development")
    }
    plan: dict[str, object] = {
        "schema": "pokemon.core.repeatable-party-development-scenario-plan.v1",
        "seed": 17,
        "assignments": assignments,
        "partition_counts": partition_counts,
        "unique_root_count": (
            len({str(item["root_lineage_id"]) for item in assignments})
            if unique_root_count is None
            else unique_root_count
        ),
        "unique_initial_state_count": len(
            {str(item["initial_state_sha256"]) for item in assignments}
        ),
        "teacher_choice_targets": 0,
        "sealed_test_cases_opened": 0,
        "private_path_fields": 0,
    }
    record: dict[str, object] = {
        "record_type": "repeatable_party_development_plan",
        "plan": plan,
        "plan_sha256": canonical_sha256(plan),
    }
    plan_payload = _canonical_line(record)
    (artifact / "plan.jsonl").write_bytes(plan_payload)
    manifest: dict[str, object] = {
        "artifact_id": artifact.name,
        "files": [
            {
                "bytes": len(plan_payload),
                "filename": "plan.jsonl",
                "records": 1,
                "sha256": hashlib.sha256(plan_payload).hexdigest(),
            }
        ],
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": kind,
        "schema_version": 1,
        "status": "complete",
        "totals": {
            "bytes": len(plan_payload),
            "files": 1,
            "records": 1,
        },
    }
    (artifact / "manifest.json").write_bytes(_canonical_line(manifest))
    return artifact, plan, plan_payload


def test_prior_development_artifact_excludes_only_verified_plan_identities(
    tmp_path: Path,
) -> None:
    artifact, plan, _payload = _write_artifact(tmp_path)

    exclusion = SCRIPT["_development_artifact_exclusion"](artifact)

    assignments = plan["assignments"]
    assert isinstance(assignments, list)
    assert exclusion.root_lineage_ids == frozenset(item["root_lineage_id"] for item in assignments)
    assert exclusion.initial_state_sha256 == frozenset(
        item["initial_state_sha256"] for item in assignments
    )
    assert exclusion.plan_sha256 == canonical_sha256(plan)
    assert (
        exclusion.manifest_sha256
        == hashlib.sha256((artifact / "manifest.json").read_bytes()).hexdigest()
    )


def test_prior_development_artifact_rejects_plan_tampering(tmp_path: Path) -> None:
    artifact, _plan, payload = _write_artifact(tmp_path)
    (artifact / "plan.jsonl").write_bytes(payload + b" \n")

    with pytest.raises(RuntimeError, match="differs from its manifest"):
        SCRIPT["_development_artifact_exclusion"](artifact)


def test_prior_development_artifact_rejects_self_consistent_false_summary(
    tmp_path: Path,
) -> None:
    artifact, _plan, _payload = _write_artifact(tmp_path, unique_root_count=99)

    with pytest.raises(RuntimeError, match="summary is inconsistent"):
        SCRIPT["_development_artifact_exclusion"](artifact)


def test_prior_development_artifact_rejects_wrong_kind(tmp_path: Path) -> None:
    artifact, _plan, _payload = _write_artifact(tmp_path, kind="other_evidence")

    with pytest.raises(RuntimeError, match="manifest identity is invalid"):
        SCRIPT["_development_artifact_exclusion"](artifact)


def test_prior_development_artifact_must_remain_outside_repository() -> None:
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_development_artifact_exclusion"](PROJECT_ROOT / "private-development-artifact")


def test_pool_summary_surfaces_capability_rejected_roots_without_identities() -> None:
    summary = SCRIPT["_pool_summary"](
        (),
        capability_rejected_root_counts={"packed_party_pp_unavailable": 3},
    )

    assert summary["capability_rejected_root_counts"] == {"packed_party_pp_unavailable": 3}
    assert "root_lineage_id" not in json.dumps(summary, sort_keys=True)


def test_root_rejection_reports_an_all_blocked_axis_without_private_identity() -> None:
    blocked_transition = PartyDevelopmentExecutionCapability(
        PartyDevelopmentCapabilityState.BLOCKED,
        PartyDevelopmentCapabilityState.READY,
        PartyDevelopmentCapabilityState.READY,
    )
    snapshot = SimpleNamespace(
        member_profiles=(
            SimpleNamespace(
                execution_capabilities_by_venue=(
                    blocked_transition,
                    blocked_transition,
                )
            ),
        )
    )

    code = SCRIPT["_capability_root_rejection_code"](snapshot)

    assert code == "all_transition_capabilities_blocked"
    assert "root" not in code


def test_repeatable_dose_binds_switch_assisted_battle_credit() -> None:
    dose = SCRIPT["PartyDevelopmentOutcomeDose"](
        completed_battles=2,
        maximum_encounter_steps=1_200,
        maximum_controller_actions=50_000,
        maximum_frames=750_000,
        maximum_healing_trips=3,
        maximum_rotations=8,
        maximum_faints=0,
    )

    protocol = SCRIPT["_battle_credit_protocol"](dose.completed_battles)
    policy = SCRIPT["_switch_assisted_outcome_policy"](dose)

    assert protocol == {
        "protocol_id": "switch-assisted-fixed-dose-v1",
        "selected_member_participates": True,
        "qualified_escort_completes_battle": True,
        "candidate_eligibility_scope": "curriculum_venue_band_relevant",
        "candidate_eligibility_is_direct_combat_claim": False,
        "venue_prior_feature_mode": "masked_uncalibrated",
        "completed_battles": 2,
        "teacher_choices": 0,
        "private_identity_fields": 0,
    }
    assert policy.safe_lead_level is None
    assert policy.minimum_direct_level_advantage == 100
    assert policy.max_battles == 2
    assert policy.max_healing_trips == 2

    calibrated = "a" * 64
    first = SCRIPT["_switch_assisted_venue_contract_sha256"](
        calibrated,
        completed_battles=2,
    )
    second = SCRIPT["_switch_assisted_venue_contract_sha256"](
        calibrated,
        completed_battles=2,
    )
    assert first == second
    assert first != calibrated


def test_hybrid_dose_uses_direct_combat_before_switch_assistance() -> None:
    dose = SCRIPT["PartyDevelopmentOutcomeDose"](
        completed_battles=1,
        maximum_encounter_steps=1_200,
        maximum_controller_actions=50_000,
        maximum_frames=750_000,
        maximum_healing_trips=3,
        maximum_rotations=8,
        maximum_faints=0,
    )
    protocol_id = SCRIPT["_HYBRID_BATTLE_CREDIT_PROTOCOL_ID"]

    protocol = SCRIPT["_battle_credit_protocol"](
        dose.completed_battles,
        protocol_id=protocol_id,
    )
    policy = SCRIPT["_outcome_policy"](dose, protocol_id=protocol_id)

    assert protocol["protocol_id"] == protocol_id
    assert protocol["selected_member_completes_when_direct_safe"] is True
    assert protocol["qualified_escort_completes_when_direct_unsafe"] is True
    assert protocol["control_settle_prelude"] == "at_most_one_no_input_frame"
    assert policy.safe_lead_level is not None
    assert policy.minimum_direct_level_advantage < 100
    assert policy.max_battles == 1
    assert policy.max_healing_trips == 2
    assert SCRIPT["_outcome_venue_contract_sha256"](
        "a" * 64,
        completed_battles=1,
        protocol_id=protocol_id,
    ) != SCRIPT["_switch_assisted_venue_contract_sha256"](
        "a" * 64,
        completed_battles=1,
    )


def test_control_settle_prelude_is_one_frame_and_changes_no_semantics() -> None:
    raw = SimpleNamespace(
        battle_state=0,
        map_id=7,
        player_x=19,
        player_y=28,
        bag_items=((1, 2),),
        player_money=3,
    )
    party = object()
    collection = object()

    class Emulator:
        frames = 0
        pressed_buttons = frozenset()

        def tick(self, frames: int) -> None:
            assert frames == 1
            self.frames += frames

    emulator = Emulator()

    class Adapter:
        def observe(self) -> SimpleNamespace:
            return SimpleNamespace(
                input_ready=emulator.frames == 1,
                raw=raw,
                party=party,
                collection_observation=collection,
            )

    runtime = SimpleNamespace(
        adapter=Adapter(),
        observer=SimpleNamespace(observe=lambda: ("same-story",)),
    )

    settled = SCRIPT["_settle_control_context"](
        runtime,
        emulator=emulator,
        reader=object(),
    )

    assert settled == 1
    assert emulator.frames == 1


def test_control_settle_prelude_rejects_protected_state_drift() -> None:
    before_raw = SimpleNamespace(
        battle_state=0,
        map_id=7,
        player_x=19,
        player_y=28,
        bag_items=((1, 2),),
        player_money=3,
    )
    after_raw = SimpleNamespace(
        battle_state=0,
        map_id=7,
        player_x=19,
        player_y=28,
        bag_items=(),
        player_money=3,
    )

    class Emulator:
        frames = 0
        pressed_buttons = frozenset()

        def tick(self, frames: int) -> None:
            self.frames += frames

    emulator = Emulator()
    party = object()
    collection = object()

    class Adapter:
        def observe(self) -> SimpleNamespace:
            return SimpleNamespace(
                input_ready=emulator.frames == 1,
                raw=after_raw if emulator.frames else before_raw,
                party=party,
                collection_observation=collection,
            )

    runtime = SimpleNamespace(
        adapter=Adapter(),
        observer=SimpleNamespace(observe=lambda: ("same-story",)),
    )

    with pytest.raises(RuntimeError, match="changed protected state"):
        SCRIPT["_settle_control_context"](
            runtime,
            emulator=emulator,
            reader=object(),
        )


def test_frozen_plan_is_external_exclusive_and_binds_the_controller_free_gate(
    tmp_path: Path,
) -> None:
    receipt: dict[str, object] = {
        "active_lane": "repeatable-party-outcome-learning-v1",
        "battle_credit_protocol": {"protocol_id": "hybrid"},
        "candidate_trial_count": 98,
        "development_repeatable": True,
        "excluded_development_artifact_count": 3,
        "excluded_development_artifact_root_count": 36,
        "excluded_development_plan_sha256": ["1" * 64],
        "excluded_prior_root_count": 5,
        "excluded_total_unique_root_count": 41,
        "input_file_sha256": {"inventory": "2" * 64},
        "plan": {"schema": "private-plan"},
        "plan_sha256": "3" * 64,
        "question_count": 36,
        "rom": {"sha256": "4" * 64},
        "scenario_pool": {"independent_root_counts": {"train": 24}},
        "selection_summary": {"kind_counts": {"train:trainee": 12}},
        "scenario_selection_protocol": "balanced-kind-goal-coverage-v2",
        "source_bundle_sha256": "5" * 64,
        "source_commit": "6" * 40,
    }
    document = SCRIPT["_frozen_plan_document"](receipt)
    destination = tmp_path / "frozen-plan.json"

    file_sha256 = SCRIPT["_write_frozen_plan"](destination, document)

    assert json.loads(destination.read_text("ascii")) == document
    assert file_sha256 == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert document["controller_actions"] == 0
    assert document["teacher_queries"] == 0
    assert document["model_predictions"] == 0
    assert document["sealed_red_cases_opened"] == 0
    assert document["crystal_cases_opened"] == 0
    with pytest.raises(RuntimeError, match="new external file"):
        SCRIPT["_write_frozen_plan"](destination, document)
