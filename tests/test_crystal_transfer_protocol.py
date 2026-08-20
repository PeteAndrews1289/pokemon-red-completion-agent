from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_crystal_completion.transfer_protocol import (
    CrystalTransferProtocolError,
    canonical_crystal_transfer_plan_bytes,
    crystal_transfer_candidate_order,
    parse_crystal_transfer_plan,
)
from pokemon_red_completion.goal_manager import GoalKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "crystal-goal-manager-transfer-v2.json"
PLAN_SHA256 = "e07ef52b1146f4c0ee05d003eea2f10f949e41a84398bb071def37f43ebd720b"


def _canonical(document: object) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _set_path(document: dict[str, object], path: tuple[object, ...], value: object) -> None:
    target: object = document
    for component in path[:-1]:
        if isinstance(component, int):
            assert isinstance(target, list)
            target = target[component]
        else:
            assert isinstance(target, dict)
            target = target[component]
    final = path[-1]
    if isinstance(final, int):
        assert isinstance(target, list)
        target[final] = value
    else:
        assert isinstance(target, dict)
        target[final] = value


def test_committed_transfer_plan_is_canonical_and_source_bound() -> None:
    payload = PLAN_PATH.read_bytes()
    plan = parse_crystal_transfer_plan(payload)
    document = json.loads(payload)

    assert payload == canonical_crystal_transfer_plan_bytes()
    assert plan.plan_sha256 == PLAN_SHA256
    assert len(plan.slots) == 72
    assert not plan.ready_for_private_context_access
    assert document["source_candidate"] == {
        "candidate_id": "red-goal-manager-74922cc-r3",
        "context_catalog_sha256": (
            "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
        ),
        "feature_schema_id": "pokemon.core.goal-manager.shared-candidate.v1",
        "fit_summary_file_sha256": (
            "cba3c9c19841c83110ff32b2be044b3ee7dbea350765df09f6ebc95081b117dc"
        ),
        "model_canonical_sha256": (
            "af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d"
        ),
        "model_file_sha256": (
            "16901b701476230d2be6c0327cc3e572f6dc5ce034f99067562916cecd3e77f4"
        ),
        "model_id": "pokemon.core.goal-manager.linear.v1",
        "promotion_plan_sha256": (
            "b648d1825fb7701f38aa00f5625fe88a86040dc7b4b061b4256f6ae665b90c46"
        ),
        "training_source_commit": "74922cc9faa793bae4f9daf03627e8621297b038",
    }
    target = document["target_source"]
    assert isinstance(target, dict)
    assert target["game_id"] == "pokemon.mainline:crystal:gbc:international:rev1"
    assert target["rom"] == {
        "header_title": "PM_CRYSTAL",
        "revision": 1,
        "sha1": "f2f52230b536214ef7c9924f483392993e226cfb",
        "sha256": None,
        "sha256_required_before_private_context_access": True,
        "size_bytes": 2_097_152,
    }


def test_all_partitions_are_disjoint_balanced_and_nested_budgets_are_balanced() -> None:
    plan = parse_crystal_transfer_plan(PLAN_PATH.read_bytes())
    slots = plan.slots

    assert len({slot.slot_id for slot in slots}) == len(slots)
    expected = {"zero_shot_probe": 2, "adaptation": 3, "sealed_test": 3}
    for partition, per_kind in expected.items():
        rows = tuple(slot for slot in slots if slot.partition == partition)
        assert Counter(slot.goal_kind for slot in rows) == Counter(
            {kind: per_kind for kind in GoalKind}
        )
        assert len({slot.focus_candidate_index for slot in rows}) >= 8
        assert all(
            slot.candidate_goal_kinds == crystal_transfer_candidate_order(slot.slot_id)
            for slot in rows
        )
    adaptation = tuple(slot for slot in slots if slot.partition == "adaptation")
    for budget, per_kind in ((9, 1), (18, 2), (27, 3)):
        assert Counter(slot.goal_kind for slot in adaptation[:budget]) == Counter(
            {kind: per_kind for kind in GoalKind}
        )
    assert slots[0].slot_id == "crystal-goal-transfer-v2-zero_shot_probe-001"
    assert slots[-1].slot_id == "crystal-goal-transfer-v2-sealed_test-027"


def test_primary_endpoint_has_enough_discordance_to_be_testable() -> None:
    plan = parse_crystal_transfer_plan(PLAN_PATH.read_bytes())

    assert plan.primary_budget == 9
    assert plan.minimum_primary_wins == 6
    assert plan.maximum_primary_losses == 0
    # With six discordant pairs all favoring transfer, the preregistered
    # two-sided exact probability is 2 * (1/2)^6.
    assert 2 * (0.5**plan.minimum_primary_wins) == pytest.approx(0.03125)


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("adaptation", "budgets"), [18, 27]),
        (("adaptation", "configuration", "epochs_per_budget"), 801),
        (("adaptation", "configuration", "normalization"), "per_candidate"),
        (
            (
                "adaptation",
                "same_examples_order_optimizer_and_normalizer_for_both_initializations",
            ),
            False,
        ),
        (("catalog_gates", "all_policy_contexts_unique"), False),
        (("catalog_gates", "minimum_candidates_per_context"), 1),
        (("catalog_gates", "partition_policy_context_overlap"), 1),
        (("catalog_gates", "selected_candidate_positions_must_vary"), False),
        (("claims", "primary_endpoint", "budget"), 27),
        (("claims", "primary_endpoint", "minimum_discordant_wins"), 5),
        (("claims", "primary_endpoint", "maximum_discordant_losses"), 1),
        (("partitions", 0, "teacher_labels_used_for_fitting"), True),
        (("partitions", 1, "contexts"), 18),
        (("partitions", 2, "teacher_access"), "before_predictions"),
        (("sealed_red_destination_test", "opened"), 1),
        (("sealed_red_destination_test", "reused_for_transfer"), True),
        (("source_candidate", "model_file_sha256"), "0" * 64),
        (("target_source", "rom", "sha1"), "0" * 40),
        (("target_source", "source", "commit"), "0" * 40),
    ),
)
def test_parser_rejects_every_high_risk_protocol_mutation(
    path: tuple[object, ...], replacement: object
) -> None:
    document = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    _set_path(document, path, replacement)

    with pytest.raises(CrystalTransferProtocolError, match="preregistration"):
        parse_crystal_transfer_plan(_canonical(document))


def test_parser_rejects_optional_stopping_or_noncanonical_serialization() -> None:
    document = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    mutated = deepcopy(document)
    assert isinstance(mutated["prediction_order"], list)
    mutated["prediction_order"].pop()
    with pytest.raises(CrystalTransferProtocolError, match="preregistration"):
        parse_crystal_transfer_plan(_canonical(mutated))

    with pytest.raises(CrystalTransferProtocolError, match="canonical"):
        parse_crystal_transfer_plan(json.dumps(document, indent=2).encode("ascii"))
    with pytest.raises(CrystalTransferProtocolError, match="duplicate"):
        parse_crystal_transfer_plan(b'{"schema":"x","schema":"y"}\n')
    with pytest.raises(CrystalTransferProtocolError, match="non-finite"):
        parse_crystal_transfer_plan(b'{"value":NaN}\n')


def test_plan_contains_no_private_path_capture_or_teacher_label() -> None:
    encoded = PLAN_PATH.read_text(encoding="ascii")
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "selected_candidate_index",
        "teacher_choice_target",
    ):
        assert forbidden not in encoded
    document = json.loads(encoded)
    assert document["sealed_red_destination_test"] == {
        "captures": 12,
        "evaluated": 0,
        "opened": 0,
        "reused_for_transfer": False,
    }


def test_generator_check_accepts_the_exact_committed_plan() -> None:
    subprocess.run(
        [sys.executable, "scripts/regenerate_crystal_transfer_plan.py", "--check"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
