from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    StrategicNavigationProtocolError,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH,
    STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH,
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
    parse_strategic_navigation_scenario_registry,
    reachable_objective_sets,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH
DIGEST_PATH = PROJECT_ROOT / STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH
EXECUTION_REGISTRY_PATH = PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _document() -> dict[str, object]:
    value = json.loads(REGISTRY_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def _scenarios(document: dict[str, object]) -> list[dict[str, object]]:
    rows = document["scenarios"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _resign(row: dict[str, object]) -> None:
    row.pop("scenario_sha256", None)
    row["scenario_sha256"] = canonical_sha256(row)


def test_reachable_inventory_has_real_branch_density() -> None:
    reachable = reachable_objective_sets(COMPLETION_QUEST)
    branching = [
        completed
        for completed in reachable
        if len(
            tuple(
                objective
                for objective in COMPLETION_QUEST
                if objective.id not in completed
                and objective.prerequisites.issubset(completed)
            )
        )
        >= 2
    ]

    assert len(reachable) == 158
    assert len(branching) == 121


def test_registry_preregisters_powered_splits_without_claiming_live_rows() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_strategic_navigation_scenario_registry(payload)

    assert registry.registry_sha256 == hashlib.sha256(payload).hexdigest()
    assert registry.partition_counts == {"test": 12, "train": 24, "validation": 12}
    assert registry.candidate_count_counts == {2: 23, 3: 20, 4: 3, 5: 2}
    assert registry.multiway_scenarios == 25
    assert registry.validation_challenge_hypotheses == 6
    assert registry.teacher_objective_counts == {
        "clear_rocket_hideout": 3,
        "defeat_erika": 6,
        "defeat_koga": 5,
        "defeat_misty": 2,
        "defeat_sabrina": 3,
        "help_bill": 1,
        "liberate_silph": 3,
        "obtain_strength": 7,
        "obtain_surf": 7,
        "reach_fuchsia": 5,
        "reach_saffron": 3,
        "rescue_fuji": 3,
    }
    assert registry.public_summary()["live_policy_contexts_authenticated"] == 0
    assert registry.public_summary()["collection_open"] is False
    assert len(registry.learning_scenarios()) == 36
    test = next(item for item in registry.scenarios if item.partition == "test")
    with pytest.raises(StrategicScenarioProtocolError, match="must remain unopened"):
        registry.scenario(test.scenario_id)


def test_silph_candidates_require_the_cartridge_proven_fuji_gate() -> None:
    registry = parse_strategic_navigation_scenario_registry(REGISTRY_PATH.read_bytes())

    assert "rescue_fuji" in COMPLETION_QUEST.objective(
        "liberate_silph"
    ).prerequisites
    assert all(
        "rescue_fuji" in scenario.completed_objective_ids
        for scenario in registry.scenarios
        if "liberate_silph" in scenario.candidate_objective_ids
    )
    assert {
        scenario.scenario_id
        for scenario in registry.scenarios
        if scenario.cost_baseline_challenge_hypothesis
    } == {
        "red-strategic-scenario-v2-003-validation",
        "red-strategic-scenario-v2-007-validation",
        "red-strategic-scenario-v2-011-validation",
        "red-strategic-scenario-v2-015-validation",
        "red-strategic-scenario-v2-019-validation",
        "red-strategic-scenario-v2-023-validation",
    }


def test_rehearsal_assignment_binds_scenario_capture_and_committed_source() -> None:
    registry = parse_strategic_navigation_scenario_registry(REGISTRY_PATH.read_bytes())
    scenario = registry.learning_scenarios()[0]
    capture = CapturedProgressEnvelope(
        state_sha256="1" * 64,
        checkpoint_id="scenario-capture-001",
        checkpoint_label="private scenario boundary",
        checkpoints_completed=3,
        checkpoints_total=40,
        verified_objective_ids=scenario.completed_objective_ids,
    )
    execution_registry = parse_strategic_navigation_registry(
        EXECUTION_REGISTRY_PATH.read_bytes()
    )
    execution = replace(execution_registry.execution, source_commit="2" * 40)

    assignment = registry.rehearsal_assignment(
        scenario.scenario_id,
        capture=capture,
        execution=execution,
    )

    assert assignment.partition == "unassigned"
    assert assignment.scenario_partition == scenario.partition
    assert assignment.scenario_sha256 == scenario.scenario_sha256
    assert assignment.capture_state_sha256 == capture.state_sha256
    assert len(assignment.episode_id) <= 80
    assert assignment == registry.rehearsal_assignment(
        scenario.scenario_id,
        capture=capture,
        execution=execution,
    )
    metadata = assignment.episode_metadata()
    collection = metadata["collection"]
    assert isinstance(collection, dict)
    assert collection["attempt"] == {
        "attempts_per_slot": 1,
        "counted": False,
        "purpose": "scenario_harness_rehearsal",
    }
    assert metadata["split"] == {
        "partition": "unassigned",
        "regime": "within_game_authenticated_scenario_rehearsal",
        "root_lineage_id": assignment.root_lineage_id,
    }
    assert "/" not in json.dumps(metadata, sort_keys=True)

    with pytest.raises(StrategicNavigationProtocolError, match="digest differs"):
        replace(assignment, capture_state_sha256="3" * 64)
    with pytest.raises(StrategicNavigationProtocolError, match="commit differs"):
        replace(assignment, source_commit=None)  # type: ignore[arg-type]


def test_rehearsal_assignment_rejects_frontier_drift_and_sealed_test() -> None:
    registry = parse_strategic_navigation_scenario_registry(REGISTRY_PATH.read_bytes())
    scenario = registry.learning_scenarios()[0]
    execution_registry = parse_strategic_navigation_registry(
        EXECUTION_REGISTRY_PATH.read_bytes()
    )
    execution = replace(execution_registry.execution, source_commit="4" * 40)
    drifted_capture = CapturedProgressEnvelope(
        state_sha256="5" * 64,
        checkpoint_id="scenario-capture-drifted",
        checkpoint_label="private scenario boundary",
        checkpoints_completed=4,
        checkpoints_total=40,
        verified_objective_ids=(*scenario.completed_objective_ids, "help_bill"),
    )
    with pytest.raises(StrategicScenarioProtocolError, match="frontier differs"):
        registry.rehearsal_assignment(
            scenario.scenario_id,
            capture=drifted_capture,
            execution=execution,
        )

    test = next(item for item in registry.scenarios if item.partition == "test")
    test_capture = replace(
        drifted_capture,
        verified_objective_ids=test.completed_objective_ids,
    )
    with pytest.raises(StrategicScenarioProtocolError, match="must remain unopened"):
        registry.rehearsal_assignment(
            test.scenario_id,
            capture=test_capture,
            execution=execution,
        )


def test_rehearsal_assignment_requires_committed_execution() -> None:
    registry = parse_strategic_navigation_scenario_registry(REGISTRY_PATH.read_bytes())
    scenario = registry.learning_scenarios()[0]
    execution = parse_strategic_navigation_registry(
        EXECUTION_REGISTRY_PATH.read_bytes()
    ).execution
    capture = CapturedProgressEnvelope(
        state_sha256="6" * 64,
        checkpoint_id="scenario-capture-uncommitted",
        checkpoint_label="private scenario boundary",
        checkpoints_completed=0,
        checkpoints_total=40,
        verified_objective_ids=scenario.completed_objective_ids,
    )

    with pytest.raises(StrategicScenarioProtocolError, match="committed source"):
        registry.rehearsal_assignment(
            scenario.scenario_id,
            capture=capture,
            execution=execution,
        )


def test_registry_and_digest_have_stable_public_identities() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    digest = json.loads(DIGEST_PATH.read_text(encoding="ascii"))

    assert len(REGISTRY_PATH.read_bytes()) == 40_744
    assert (
        registry.registry_sha256
        == "d06ecc9c1bc9d4103b966c83df0ee6e49c2329ed7785c63751ada1e74c11cd71"
    )
    assert (
        registry.objective_graph_sha256
        == "4ba32cc5fa84b6b096f1bda8581b9e557e70c8732a40849d128be2b29eb5a528"
    )
    assert (
        registry.teacher_order_sha256
        == "b4b0292a38a062a33fd7449aecf8eca01433a19297558476ee2b8aa9fbeb8cf8"
    )
    assert digest == {
        "bytes": 40_744,
        "schema": "pokemon-strategic-navigation-scenario-registry-digest-v2",
        "sha256": registry.registry_sha256,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("unknown_top_level", "registry fields differ"),
        ("wrong_teacher", "teacher choice differs"),
        ("missing_candidate", "candidates differ"),
        ("wrong_family", "context-family digest differs"),
        ("wrong_order", "scenario order differs"),
    ),
)
def test_parser_kills_semantic_registry_mutations(
    mutation: str,
    message: str,
) -> None:
    document = _document()
    rows = _scenarios(document)
    row = (
        next(
            item
            for item in rows
            if len(item["candidate_objective_ids"]) >= 3
        )
        if mutation == "missing_candidate"
        else rows[0]
    )
    if mutation == "unknown_top_level":
        document["ignored"] = True
    elif mutation == "wrong_teacher":
        candidates = row["candidate_objective_ids"]
        assert isinstance(candidates, list)
        row["teacher_objective_id"] = candidates[-1]
        _resign(row)
    elif mutation == "missing_candidate":
        candidates = row["candidate_objective_ids"]
        assert isinstance(candidates, list)
        candidates.pop()
        _resign(row)
    elif mutation == "wrong_family":
        row["context_family_sha256"] = "0" * 64
        _resign(row)
    else:
        row["scenario_id"] = "red-strategic-scenario-v2-999-train"
        _resign(row)

    with pytest.raises(StrategicScenarioProtocolError, match=message):
        parse_strategic_navigation_scenario_registry(_canonical(document))


def test_parser_rejects_omitted_automatic_completion() -> None:
    document = _document()
    row = next(
        item
        for item in _scenarios(document)
        if item["teacher_objective_id"] == "rescue_fuji"
    )
    completed = row["completed_objective_ids"]
    assert isinstance(completed, list)
    completed.remove("obtain_silph_scope")
    _resign(row)

    with pytest.raises(StrategicScenarioProtocolError, match="automatic objective"):
        parse_strategic_navigation_scenario_registry(_canonical(document))


def test_parser_requires_six_preregistered_validation_challenges() -> None:
    document = _document()
    row = next(
        item
        for item in _scenarios(document)
        if item["partition"] == "validation"
        and item["cost_baseline_challenge_hypothesis"] is True
    )
    row["cost_baseline_challenge_hypothesis"] = False
    _resign(row)

    with pytest.raises(StrategicScenarioProtocolError, match="baseline-challenge"):
        parse_strategic_navigation_scenario_registry(_canonical(document))


def test_parser_rejects_a_context_family_copied_across_partitions() -> None:
    document = _document()
    rows = _scenarios(document)
    training = next(item for item in rows if item["partition"] == "train")
    test_index = next(index for index, item in enumerate(rows) if item["partition"] == "test")
    test = rows[test_index]
    copied = deepcopy(training)
    copied["partition"] = "test"
    copied["scenario_id"] = test["scenario_id"]
    _resign(copied)
    rows[test_index] = copied

    with pytest.raises(StrategicScenarioProtocolError, match="crosses data partitions"):
        parse_strategic_navigation_scenario_registry(_canonical(document))


def test_loader_rejects_a_tampered_digest_sidecar(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    registry = repository / STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH
    digest = repository / STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY_PATH.read_bytes())
    digest.write_text(
        json.dumps(
            {
                "bytes": len(REGISTRY_PATH.read_bytes()),
                "schema": "pokemon-strategic-navigation-scenario-registry-digest-v2",
                "sha256": "0" * 64,
            }
        ),
        encoding="ascii",
    )

    with pytest.raises(StrategicScenarioProtocolError, match="sidecar differs"):
        load_strategic_navigation_scenario_registry(repository)
