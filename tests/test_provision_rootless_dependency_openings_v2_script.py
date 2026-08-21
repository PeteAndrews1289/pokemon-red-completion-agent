# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

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
    str(PROJECT_ROOT / "scripts/provision_rootless_dependency_openings_v2.py"),
    run_name="provision_rootless_dependency_openings_v2_test",
)

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    RootlessDependencyEvaluationDesignV2,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND,
    commitment_roster_from_metadata_v2,
    generate_v2_development_openings,
)
from pokemon_red_completion.private_artifacts import (
    PRIVATE_ROOT_SENTINEL,
    SealedRecordManifestMetadata,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _public() -> dict[str, str]:
    return {
        "source_commit": "a" * 40,
        "source_bundle_sha256": _sha("source"),
        "runner_sha256": _sha("runner"),
        "runtime_sha256": _sha("runtime"),
        "core_sha256": _sha("core"),
    }


def _roster():
    openings = generate_v2_development_openings()
    rows = tuple(
        SealedRecordManifestMetadata(
            record_id=row.scenario_id,
            kind="rootless-living-dex-dependency-development-opening-v2",
            declared_record_sha256=hashlib.sha256(row.canonical_private_bytes()).hexdigest(),
            manifest_sha256=_sha(f"manifest:{row.scenario_id}"),
            declared_total_bytes=len(row.canonical_private_bytes()),
        )
        for row in openings
    )
    return openings, commitment_roster_from_metadata_v2(rows)


def _args(mode: str) -> list[str]:
    result = [
        "--mode",
        mode,
        "--execution-manifest",
        str(PROJECT_ROOT / ".public-execution-manifests" / "v2.json"),
        "--expected-execution-manifest-sha256",
        _sha("manifest"),
        "--design-qualification-sha256",
        _sha("qualification"),
    ]
    result.extend(("--private-root", "/private/root"))
    return result


def _patch_public_gate(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_current_public_bindings",
        lambda **kwargs: _public(),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "read_public_manifest",
        lambda *args, **kwargs: b"manifest\n",
    )

    def authenticate(*args: object, **kwargs: object) -> dict[str, object]:
        events.append("manifest")
        return {}

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "authenticate_rootless_execution_manifest",
        authenticate,
    )


def test_preflight_authenticates_manifest_then_binds_store_before_registry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    _patch_public_gate(monkeypatch, events)

    store = SimpleNamespace(inspect_sealed_record_metadata=lambda *args, **kwargs: None)

    def open_bound(path: Path) -> tuple[object, str]:
        assert events == ["manifest"]
        events.append("store")
        return store, _sha("private-root")

    def registry() -> Path:
        assert events == ["manifest", "store"]
        events.append("registry")
        return Path("/fixed/registry")

    monkeypatch.setitem(SCRIPT["main"].__globals__, "_open_bound_private_root", open_bound)
    monkeypatch.setitem(SCRIPT["main"].__globals__, "open_fixed_account_claim_registry", registry)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "root_claim_is_available",
        lambda *args, **kwargs: True,
    )
    assert SCRIPT["main"](_args("preflight")) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready_identity_unclaimed"
    assert result["development_openings_provisioned"] == 0
    assert events == ["manifest", "store", "registry"]


def test_provision_binds_store_then_claims_before_opening_publication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    _patch_public_gate(monkeypatch, events)
    openings, roster = _roster()
    store = SimpleNamespace(inspect_sealed_record_metadata=lambda *args, **kwargs: None)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_open_bound_private_root",
        lambda path: (events.append("store") or store, _sha("private-root")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/registry"),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "root_claim_is_available",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "write_root_claim",
        lambda *args, **kwargs: events.append("claim"),
    )

    def provision(opened_store: object) -> object:
        assert events[-1] == "claim"
        assert opened_store is store
        events.append("provision")
        return SimpleNamespace(openings=openings, roster=roster)

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "provision_v2_development_commitments",
        provision,
    )

    assert SCRIPT["main"](_args("provision")) == 0

    result = json.loads(capsys.readouterr().out)
    design = RootlessDependencyEvaluationDesignV2.from_dict(result["design"])
    assert result["status"] == "four_openings_provisioned_once"
    assert result["development_payloads_disclosed_publicly"] == 0
    assert design.development_roster == roster
    assert all(row.nonce not in json.dumps(result) for row in openings)
    assert events == ["manifest", "store", "claim", "provision"]


def test_consumed_provision_claim_cannot_resume_against_another_store(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    _patch_public_gate(monkeypatch, events)
    store = SimpleNamespace(inspect_sealed_record_metadata=lambda *args, **kwargs: None)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_open_bound_private_root",
        lambda path: (store, _sha("second-private-root")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/registry"),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "root_claim_is_available",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "read_root_claim",
        lambda *args, **kwargs: {
            "schema": "pokemon.red.fresh-composition-root-claim.v1",
            "root_consumption_sha256": args[1],
            "execution_identity_sha256": _sha("first-private-root-execution"),
            "source_commit": _public()["source_commit"],
            "runner_sha256": _public()["runner_sha256"],
        },
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "provision_v2_development_commitments",
        lambda store: (_ for _ in ()).throw(AssertionError("alternate store was provisioned")),
    )

    assert SCRIPT["main"](_args("provision")) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["failure_stage"] == "provision_claim"


def test_private_store_binding_changes_with_the_exact_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = (tmp_path / "first", tmp_path / "second")
    for root in roots:
        root.mkdir()
        (root / PRIVATE_ROOT_SENTINEL).write_bytes(b"private-root-sentinel\n")
    monkeypatch.setitem(
        SCRIPT["_open_bound_private_root"].__globals__,
        "open_private_root",
        lambda *args, **kwargs: object(),
    )

    _, first_identity = SCRIPT["_open_bound_private_root"](roots[0])
    _, second_identity = SCRIPT["_open_bound_private_root"](roots[1])

    assert first_identity != second_identity


def test_preflight_rejects_an_unclaimed_but_preexisting_local_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    _patch_public_gate(monkeypatch, events)
    store = SimpleNamespace(
        inspect_sealed_record_metadata=lambda *args, **kwargs: SimpleNamespace(
            kind=ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND
        )
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_open_bound_private_root",
        lambda path: (store, _sha("private-root")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/registry"),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "root_claim_is_available",
        lambda *args, **kwargs: True,
    )

    assert SCRIPT["main"](_args("preflight")) == 1
    assert json.loads(capsys.readouterr().out)["failure_stage"] == "provision_claim"


def test_argument_failure_is_path_free(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = tmp_path / "very-private" / "root"
    assert SCRIPT["main"](["--private-root", str(secret)]) == 1
    captured = capsys.readouterr()
    assert str(tmp_path) not in captured.out
    assert captured.err == ""
    assert json.loads(captured.out)["private_path_fields"] == 0
