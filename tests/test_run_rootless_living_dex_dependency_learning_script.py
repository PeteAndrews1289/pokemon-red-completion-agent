# ruff: noqa: E402 -- script is loaded as a standalone execution boundary.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DEVELOPMENT_OPENING_SCHEMA,
    DependencyMultiplicity,
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    build_rootless_living_dex_dependency_design,
    materialize_train_dependency_outcome,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_rootless_living_dex_dependency_campaign as campaign_runner

SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_rootless_living_dex_dependency_learning.py"),
    run_name="run_rootless_dependency_learning_script_test",
)


def _line(document: dict[str, object]) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        + b"\n"
    )


class _Record:
    def __init__(self, record_id: str, kind: str, document: dict[str, object]) -> None:
        payload = _line(document)
        self.document = document
        self.reads = 0
        self.summary = SimpleNamespace(
            record_id=record_id,
            kind=kind,
            record_sha256=hashlib.sha256(payload).hexdigest(),
            manifest_sha256=hashlib.sha256(b"manifest:" + payload).hexdigest(),
        )

    def read(self) -> dict[str, object]:
        self.reads += 1
        return json.loads(json.dumps(self.document))


class _Store:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], _Record] = {}

    def find_sealed_record(self, record_id: str, *, expected_kind: str):
        return self.records.get((record_id, expected_kind))

    def publish_sealed_record(self, record_id: str, *, kind: str, record: dict[str, object]):
        existing = self.find_sealed_record(record_id, expected_kind=kind)
        if existing is not None:
            if existing.document != record:
                raise RuntimeError("collision")
            return existing
        created = _Record(record_id, kind, record)
        self.records[(record_id, kind)] = created
        return created


def _opening_documents() -> tuple[dict[str, object], ...]:
    result = []
    for family_index, (precursor, evolved) in enumerate(((3, 1), (1, 3))):
        for row_index, multiplicity in enumerate(DependencyMultiplicity):
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            result.append(
                {
                    "schema": DEVELOPMENT_OPENING_SCHEMA,
                    "scenario_id": f"rootless-development-{family_index:08x}{row_index:08x}",
                    "family_id": f"development-family-{family_index:016x}",
                    "nonce": hashlib.sha256(
                        f"private-{family_index}-{row_index}".encode()
                    ).hexdigest(),
                    "partition": "development",
                    "multiplicity": multiplicity.value,
                    "structure": {
                        "required_precursor_count": precursor,
                        "required_evolved_count": evolved,
                    },
                    "before": {
                        "precursor_count": precursor if scarce else precursor + evolved,
                        "evolved_count": 0,
                    },
                    "assigned_action": (
                        GoalKind.ACQUIRE_SPECIES.value
                        if scarce == (family_index % 2 == 0)
                        else GoalKind.EVOLVE_SPECIES.value
                    ),
                }
            )
    return tuple(result)


def _inventory_and_store():
    store = _Store()
    commitments = []
    opening_ids = []
    for document in _opening_documents():
        record_id = document["scenario_id"]
        assert isinstance(record_id, str)
        record = store.publish_sealed_record(
            record_id,
            kind=campaign_runner.OPENING_KIND,
            record=document,
        )
        commitments.append(DevelopmentCommitmentRow(record_id, record.summary.record_sha256))
        opening_ids.append(record_id)
    design = build_rootless_living_dex_dependency_design(
        DevelopmentCommitmentRoster(tuple(commitments))
    )
    campaign_sha = "a" * 64
    outcome_hashes = []
    for scenario in design.train_scenarios:
        outcome = materialize_train_dependency_outcome(scenario)
        record = store.publish_sealed_record(
            campaign_runner._outcome_record_id(scenario.scenario_id),
            kind=campaign_runner.OUTCOME_KIND,
            record=outcome.public_dict(),
        )
        outcome_hashes.append(record.summary.record_sha256)
    admission = {
        "schema": campaign_runner.TRAIN_ADMISSION_SCHEMA,
        "status": "admitted",
        "campaign_sha256": campaign_sha,
        "design_sha256": design.design_sha256,
        "train_dataset_sha256": "b" * 64,
        "outcome_record_sha256": outcome_hashes,
        "settled_outcomes": 8,
        "positive_outcomes": 4,
        "negative_outcomes": 4,
        "development_opening_payloads_disclosed_to_stage": 0,
    }
    inventory = SCRIPT["_Inventory"](
        design,
        campaign_sha,
        "c" * 64,
        admission,
        tuple(opening_ids),
    )
    return inventory, store


def _gate():
    return SCRIPT["_Gate"](
        "d" * 64,
        {
            "source_commit": "e" * 40,
            "source_bundle_sha256": "f" * 64,
            "runner_sha256": "1" * 64,
        },
        {"fit_execution_manifest_sha256": "d" * 64},
    )


def test_fit_then_sealed_comparison_are_separate_claimed_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory, store = _inventory_and_store()
    gate = _gate()
    claims: dict[str, dict[str, str]] = {}
    globals_dict = SCRIPT["_fit"].__globals__
    monkeypatch.setitem(globals_dict, "open_fixed_account_claim_registry", lambda: Path("registry"))
    monkeypatch.setitem(
        globals_dict,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        globals_dict,
        "root_claim_is_available",
        lambda registry, identity: identity not in claims,
    )

    def write_claim(registry: Path, **values: str) -> None:
        claims[values["root_consumption_sha256"]] = {
            "execution_identity_sha256": values["execution_identity_sha256"]
        }

    monkeypatch.setitem(globals_dict, "write_root_claim", write_claim)
    monkeypatch.setitem(
        globals_dict,
        "read_root_claim",
        lambda registry, identity: claims[identity],
    )

    fit_result = SCRIPT["_fit"](store, inventory, gate)
    assert fit_result["model_fits_added"] == 1
    assert fit_result["development_opening_payloads_disclosed_to_stage"] == 0

    args = SimpleNamespace(
        expected_fit_manifest_record_sha256=fit_result["fit_manifest_record_sha256"],
        expected_fit_terminal_record_sha256=fit_result["fit_terminal_record_sha256"],
    )
    compare_gate = SCRIPT["_Gate"](
        "2" * 64,
        gate.public_bindings,
        {"fit_execution_manifest_sha256": gate.execution_manifest_sha256},
    )
    preflight = SCRIPT["_preflight_compare"](args, store, inventory, compare_gate)
    assert preflight["development_opening_payloads_disclosed_to_stage"] == 0
    comparison = SCRIPT["_compare"](args, store, inventory, compare_gate)
    assert comparison["development_opening_payloads_disclosed_to_stage"] == 4
    assert comparison["unseen_comparisons_added"] == 1
    assert comparison["descriptive_gate_passed"] is True
    assert comparison["authority_promotions_added"] == 0
    assert comparison["transfer_results_added"] == 0


def test_postclaim_fit_failure_retains_a_path_free_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory, store = _inventory_and_store()
    gate = _gate()
    claims: dict[str, dict[str, str]] = {}
    globals_dict = SCRIPT["_fit"].__globals__
    monkeypatch.setitem(globals_dict, "open_fixed_account_claim_registry", lambda: Path("registry"))
    monkeypatch.setitem(
        globals_dict,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(globals_dict, "root_claim_is_available", lambda *args: True)

    def write_claim(registry: Path, **values: str) -> None:
        claims[values["root_consumption_sha256"]] = {
            "execution_identity_sha256": values["execution_identity_sha256"]
        }

    monkeypatch.setitem(globals_dict, "write_root_claim", write_claim)
    monkeypatch.setitem(
        globals_dict,
        "_materialize_fit_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private detail")),
    )

    with pytest.raises(SCRIPT["RootlessLearningError"], match="dependency_ranker_fit"):
        SCRIPT["_fit"](store, inventory, gate)

    terminal = store.find_sealed_record(
        SCRIPT["_fit_terminal_record_id"](inventory),
        expected_kind=SCRIPT["FIT_TERMINAL_KIND"],
    )
    assert terminal is not None
    assert terminal.read()["failure_stage"] == "dependency_ranker_fit"
    assert claims


@pytest.mark.parametrize("operation", ["fit", "compare"])
def test_failure_terminal_helper_covers_both_one_shot_stages(operation: str) -> None:
    inventory, store = _inventory_and_store()

    SCRIPT["_retain_learning_failure_terminal"](
        store,
        inventory,
        operation=operation,
        failure_stage="synthetic_failure",
    )

    if operation == "fit":
        record_id = SCRIPT["_fit_terminal_record_id"](inventory)
        kind = SCRIPT["FIT_TERMINAL_KIND"]
    else:
        record_id = SCRIPT["_comparison_terminal_record_id"](inventory)
        kind = SCRIPT["COMPARISON_TERMINAL_KIND"]
    terminal = store.find_sealed_record(record_id, expected_kind=kind)
    assert terminal is not None
    assert terminal.read() == {
        "schema": "pokemon.private.rootless-dependency-learning-failure-terminal.v1",
        "status": "failed",
        "operation": operation,
        "failure_stage": "synthetic_failure",
        "campaign_sha256": inventory.campaign_sha256,
        "design_sha256": inventory.design.design_sha256,
        "private_path_fields": 0,
    }


def test_main_public_gate_precedes_private_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    opened = []
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_public_gate",
        lambda args: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "open_private_root",
        lambda *args, **kwargs: opened.append(True),
    )
    args = [
        "--mode",
        "preflight-fit",
        "--execution-manifest",
        str(tmp_path / "manifest.json"),
        "--expected-execution-manifest-sha256",
        "a" * 64,
        "--dependency",
        "core=src/pokemon_red_completion/living_dex_dependency_curriculum.py",
        "--semantic-binding",
        f"campaign_plan_record_sha256={'b' * 64}",
        "--private-input-role",
        "private_root",
        "--public-roster",
        str(tmp_path / "roster.json"),
        "--private-root",
        str(tmp_path / "private"),
        "--expected-campaign-sha256",
        "c" * 64,
    ]

    assert SCRIPT["main"](args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["failure_stage"] == "public_manifest_authentication"
    assert result["private_path_fields"] == 0
    assert opened == []
