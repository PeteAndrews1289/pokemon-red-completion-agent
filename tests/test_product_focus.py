from __future__ import annotations

import json
import runpy
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from product_focus import (  # noqa: E402
    DEFAULT_FOCUS_CONFIG,
    DEFAULT_FOCUS_DOCUMENT,
    ProductFocusError,
    canonical_focus_json,
    focus_progress_fraction,
    focus_scorecard,
    load_product_focus,
    render_product_focus_markdown,
    validate_product_focus_document,
)

CHECKER = runpy.run_path(str(SCRIPTS / "check_product_focus.py"))
CHECK_DOCS = runpy.run_path(str(SCRIPTS / "check_docs.py"))
DASHBOARD = runpy.run_path(str(SCRIPTS / "run_product_focus_dashboard.py"))


def _document() -> dict[str, object]:
    return json.loads(DEFAULT_FOCUS_CONFIG.read_text(encoding="ascii"))


def _active(document: dict[str, object]) -> dict[str, object]:
    lanes = document["lanes"]
    assert isinstance(lanes, list)
    active = [lane for lane in lanes if isinstance(lane, dict) and lane.get("status") == "active"]
    assert len(active) == 1
    return active[0]


def test_tracked_focus_is_canonical_and_reports_no_false_learning_progress() -> None:
    state = load_product_focus()

    assert DEFAULT_FOCUS_CONFIG.read_bytes() == canonical_focus_json(state.document)
    assert DEFAULT_FOCUS_DOCUMENT.read_text(encoding="utf-8") == (
        render_product_focus_markdown(state)
    )
    assert state.active_lane["id"] == "repeatable-party-outcome-learning-v1"
    assert len(state.retired_lanes) == 1
    assert focus_progress_fraction(state) == 0.0
    assert focus_scorecard(state) == (
        ("Outcome Question · train", 0, 8),
        ("Outcome Question · development", 0, 4),
        ("Model Fit · train", 0, 1),
        ("Unseen Comparison · development", 0, 1),
    )
    encoded = json.dumps(state.document, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_checker_binds_discovery_docs_and_pull_request_mission_check() -> None:
    rows = CHECKER["check_product_focus"]()

    assert rows[-1] == "Unseen Comparison · development: 0/1"


def test_existing_ci_documentation_gate_invokes_the_focus_checker() -> None:
    main = CHECK_DOCS["main"]
    calls = 0

    def checked() -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        return ()

    original = main.__globals__["check_product_focus"]
    main.__globals__["check_product_focus"] = checked
    try:
        assert main() == 0
    finally:
        main.__globals__["check_product_focus"] = original

    assert calls == 1


def test_focus_requires_exactly_one_active_lane() -> None:
    document = _document()
    lanes = document["lanes"]
    assert isinstance(lanes, list)
    retired = lanes[1]
    assert isinstance(retired, dict)
    retired["status"] = "active"

    with pytest.raises(ProductFocusError, match="fields|exactly one"):
        validate_product_focus_document(document)


def test_learning_lane_requires_outcomes_fit_and_unseen_evaluation() -> None:
    document = _document()
    lane = _active(document)
    outputs = lane["measurable_outputs"]
    assert isinstance(outputs, list)
    lane["measurable_outputs"] = [
        item for item in outputs if isinstance(item, dict) and item.get("kind") != "model_fit"
    ]

    with pytest.raises(ProductFocusError, match="outcomes, a model fit and unseen"):
        validate_product_focus_document(document)


def test_maintenance_must_name_the_learning_experiment_it_unblocks() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "maintenance"
    lane["measurable_outputs"] = []

    with pytest.raises(ProductFocusError, match="must name the learning lane"):
        validate_product_focus_document(document)


def test_development_cannot_silently_open_a_protected_action() -> None:
    document = _document()
    lane = _active(document)
    prohibited = lane["prohibited_actions"]
    assert isinstance(prohibited, list)
    prohibited.remove("full_game_replay")

    with pytest.raises(ProductFocusError, match="protected-action prohibition"):
        validate_product_focus_document(document)


@pytest.mark.parametrize(
    ("section", "key", "value", "match"),
    (
        ("alarms", "maximum_sessions_without_measured_learning_output", 2, "one session"),
        ("alarms", "maximum_full_replays_during_active_lane", 1, "full replay"),
        ("session_budget_percent", "maintenance_and_docs", 30, "sum to 100"),
    ),
)
def test_focus_rejects_weakened_alarms_or_learning_budget(
    section: str,
    key: str,
    value: object,
    match: str,
) -> None:
    document = _document()
    target = document[section]
    assert isinstance(target, dict)
    target[key] = value

    with pytest.raises(ProductFocusError, match=match):
        validate_product_focus_document(document)


def test_nonzero_progress_requires_a_tracked_path_free_evidence_file() -> None:
    document = _document()
    lane = _active(document)
    progress = lane["progress"]
    assert isinstance(progress, dict)
    outcomes = progress["outcome_questions"]
    assert isinstance(outcomes, dict)
    outcomes["train"] = 1
    progress["evidence"] = []

    with pytest.raises(ProductFocusError, match="requires tracked evidence"):
        validate_product_focus_document(document)


def test_latest_reorientation_must_bind_current_progress_evidence() -> None:
    document = _document()
    lane = _active(document)
    progress = lane["progress"]
    assert isinstance(progress, dict)
    outcomes = progress["outcome_questions"]
    assert isinstance(outcomes, dict)
    outcomes["train"] = 1
    progress["evidence"] = [
        {
            "kind": "outcome_question",
            "path": "docs/evidence/example.json",
            "sha256": "e" * 64,
        }
    ]
    reorientation = lane["latest_reorientation"]
    assert isinstance(reorientation, dict)
    evidence = reorientation["evidence"]
    assert isinstance(evidence, dict)
    evidence["sha256"] = "f" * 64

    with pytest.raises(ProductFocusError, match="bind one current progress evidence"):
        validate_product_focus_document(document)


def test_loader_rejects_duplicate_keys_and_noncanonical_bytes(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"schema":"a","schema":"b"}\n')
    with pytest.raises(ProductFocusError, match="invalid JSON"):
        load_product_focus(duplicate, project_root=tmp_path)

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(_document()), encoding="ascii")
    with pytest.raises(ProductFocusError, match="not canonical"):
        load_product_focus(noncanonical, project_root=tmp_path)


def test_contract_is_title_neutral_enough_for_a_later_game_lane() -> None:
    document = deepcopy(_document())
    lane = _active(document)
    lane["id"] = "repeatable-party-transfer-learning-v1"
    lane["name"] = "Repeatable party transfer learning"
    lane["capability"] = "Choose portable party actions in an unseen title."
    lane["cheapest_falsifier"] = "Compare transferred and zero-initialized policies."
    lane["transfer_test"] = "Evaluate the same semantic contract in a later title."
    lane["next_decision"] = "Decide whether the shared representation transfers."

    state = validate_product_focus_document(document)

    assert state.active_lane["id"] == "repeatable-party-transfer-learning-v1"


def test_focus_dashboard_is_view_only_and_does_not_overclaim_training() -> None:
    state = load_product_focus()
    snapshot = DASHBOARD["product_focus_dashboard_snapshot"](state)
    public = snapshot.public_dict()

    assert public["run_status"] == "waiting"
    assert public["stage_progress"] == 0.0
    assert public["actions"] == 0
    assert public["experiment"]["zero_shot"] == {"completed": 0, "total": 12}  # type: ignore[index]
    assert public["experiment"]["adaptation"] == {"completed": 0, "total": 1}  # type: ignore[index]
    assert public["experiment"]["sealed_test"] == {"completed": 0, "total": 1}  # type: ignore[index]
    encoded = json.dumps(public, sort_keys=True)
    assert "No active-lane model fit yet" in encoded
    assert "not yet published at an exact green head" in encoded
    assert "full replay 0" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_focus_dashboard_uses_a_separate_local_port() -> None:
    args = DASHBOARD["_parser"]().parse_args(["--no-browser", "--duration-seconds", "1"])

    assert args.port == 8768
    assert args.no_browser is True
    assert args.duration_seconds == 1
