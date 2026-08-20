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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_rootless_living_dex_dependency_campaign.py"),
    run_name="run_rootless_dependency_campaign_script_test",
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

    def add(self, record: _Record) -> None:
        self.records[(record.summary.record_id, record.summary.kind)] = record

    def find_sealed_record(self, record_id: str, *, expected_kind: str):
        return self.records.get((record_id, expected_kind))

    def publish_sealed_record(self, record_id: str, *, kind: str, record: dict[str, object]):
        existing = self.records.get((record_id, kind))
        if existing is not None:
            if existing.document != record:
                raise RuntimeError("collision")
            return existing
        created = _Record(record_id, kind, record)
        self.add(created)
        return created


def _roster_and_store() -> tuple[dict[str, object], _Store, tuple[_Record, ...]]:
    store = _Store()
    rows = []
    openings = []
    for index in range(4):
        record_id = f"rootless-development-{index:016x}"
        opening = _Record(record_id, SCRIPT["OPENING_KIND"], {"opaque": index})
        store.add(opening)
        openings.append(opening)
        rows.append(
            {
                "scenario_id": record_id,
                "opening_sha256": opening.summary.record_sha256,
                "record_manifest_sha256": opening.summary.manifest_sha256,
            }
        )
    roster = {
        "schema": SCRIPT["PUBLIC_ROSTER_SCHEMA"],
        "row_count": 4,
        "rows": rows,
        "provision_record_sha256": "a" * 64,
        "private_path_fields": 0,
    }
    return roster, store, tuple(openings)


def _gate() -> object:
    return SCRIPT["_Gate"](
        "b" * 64,
        {
            "source_commit": "c" * 40,
            "source_bundle_sha256": "d" * 64,
            "runner_sha256": "e" * 64,
        },
        {
            "development_roster_sha256": "f" * 64,
            "execute_execution_manifest_sha256": "b" * 64,
        },
    )


def test_freeze_preflight_execute_and_admit_have_exact_counter_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster, store, opening_records = _roster_and_store()
    gate = _gate()
    roster_sha = "f" * 64
    campaign = SCRIPT["_reconstruct_campaign"](store, roster, roster_sha, gate)
    frozen = SCRIPT["_freeze"](store, campaign, gate)
    assert frozen["synthetic_rootless_train_outcomes_added"] == 0
    assert all(record.reads == 0 for record in opening_records)

    claims: dict[str, dict[str, str]] = {}
    globals_dict = SCRIPT["_preflight"].__globals__
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

    ready = SCRIPT["_preflight"](store, campaign, gate)
    assert ready["status"] == "training_ready"
    assert ready["available_train_identities"] == 8
    assert ready["development_opening_payloads_disclosed_to_stage"] == 0

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
    executed = SCRIPT["_execute"](store, campaign, gate)
    assert executed["settled_outcomes"] == 8
    assert executed["synthetic_rootless_train_outcomes_added"] == 0

    admitted = SCRIPT["_admit"](store, campaign, gate)
    assert admitted["synthetic_rootless_train_outcomes_added"] == 8
    assert admitted["synthetic_rootless_atomic_goal_episodes_added"] == 8
    assert admitted["causal_train_examples_added"] == 0
    assert admitted["model_fits_added"] == 0
    assert all(record.reads == 0 for record in opening_records)


def test_nonfreeze_operation_reconstructs_the_exact_frozen_plan() -> None:
    roster, store, _ = _roster_and_store()
    freeze_gate = _gate()
    frozen = SCRIPT["_reconstruct_campaign"](store, roster, "f" * 64, freeze_gate)
    preflight_gate = SCRIPT["_Gate"](
        "1" * 64,
        freeze_gate.public_bindings,
        {
            "development_roster_sha256": "f" * 64,
            "freeze_execution_manifest_sha256": freeze_gate.execution_manifest_sha256,
        },
    )

    reconstructed = SCRIPT["_reconstruct_campaign"](
        store,
        roster,
        "f" * 64,
        preflight_gate,
    )

    assert reconstructed.plan == frozen.plan
    assert reconstructed.plan["freeze_execution_manifest_sha256"] == "b" * 64


def test_admission_authenticates_the_distinct_execute_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster, store, _ = _roster_and_store()
    freeze_gate = _gate()
    campaign = SCRIPT["_reconstruct_campaign"](store, roster, "f" * 64, freeze_gate)
    SCRIPT["_freeze"](store, campaign, freeze_gate)
    execute_gate = SCRIPT["_Gate"](
        "2" * 64,
        freeze_gate.public_bindings,
        {
            "development_roster_sha256": "f" * 64,
            "freeze_execution_manifest_sha256": "b" * 64,
        },
    )
    admit_gate = SCRIPT["_Gate"](
        "3" * 64,
        freeze_gate.public_bindings,
        {
            "development_roster_sha256": "f" * 64,
            "freeze_execution_manifest_sha256": "b" * 64,
            "execute_execution_manifest_sha256": "2" * 64,
        },
    )
    claims: dict[str, dict[str, str]] = {}
    globals_dict = SCRIPT["_execute"].__globals__
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

    SCRIPT["_execute"](store, campaign, execute_gate)
    admitted = SCRIPT["_admit"](store, campaign, admit_gate)

    assert admitted["synthetic_rootless_train_outcomes_added"] == 8


def test_consumed_scenario_without_artifact_is_censored_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster, store, _ = _roster_and_store()
    gate = _gate()
    campaign = SCRIPT["_reconstruct_campaign"](store, roster, "f" * 64, gate)
    SCRIPT["_freeze"](store, campaign, gate)
    claims: dict[str, dict[str, str]] = {}
    globals_dict = SCRIPT["_execute"].__globals__
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
    execution_identity = SCRIPT["_execution_identity"](
        campaign,
        gate,
        execution_manifest_sha256=gate.execution_manifest_sha256,
    )
    first_scenario_identity = SCRIPT["_campaign_claim_identities"](campaign)[2]
    claims[first_scenario_identity] = {"execution_identity_sha256": execution_identity}

    executed = SCRIPT["_execute"](store, campaign, gate)

    assert executed["status"] == "train_campaign_closed_with_censored_outcomes"
    assert executed["settled_outcomes"] == 7
    assert executed["interrupted_outcomes"] == 1
    with pytest.raises(SCRIPT["RootlessCampaignError"]):
        SCRIPT["_admit"](store, campaign, gate)


def test_main_authenticates_public_manifest_before_private_store(
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
        "freeze",
        "--execution-manifest",
        str(tmp_path / "manifest.json"),
        "--expected-execution-manifest-sha256",
        "a" * 64,
        "--dependency",
        "core=src/pokemon_red_completion/living_dex_dependency_curriculum.py",
        "--semantic-binding",
        f"development_roster_sha256={'b' * 64}",
        "--private-input-role",
        "private_root",
        "--public-roster",
        str(tmp_path / "roster.json"),
        "--private-root",
        str(tmp_path / "private"),
    ]

    assert SCRIPT["main"](args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["failure_stage"] == "public_manifest_authentication"
    assert result["private_path_fields"] == 0
    assert opened == []
