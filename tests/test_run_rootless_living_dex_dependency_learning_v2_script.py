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
    str(PROJECT_ROOT / "scripts/run_rootless_living_dex_dependency_learning_v2.py"),
    run_name="run_rootless_living_dex_dependency_learning_v2_test",
)

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    EvaluationExecutionBindingV2,
    RootlessDependencyEvaluationDesignV2,
    build_dependency_comparison_claim_v2,
    build_dependency_fit_claim_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    claim_v2_fit_before_computation,
    materialize_claimed_v2_fit_bundle,
    publish_v2_fit_bundle,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    commitment_roster_from_metadata_v2,
    generate_v2_development_openings,
    provision_v2_development_commitments,
)
from pokemon_red_completion.private_artifacts import (
    SealedRecordManifestMetadata,
    initialize_private_root,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _design() -> RootlessDependencyEvaluationDesignV2:
    openings = generate_v2_development_openings()
    metadata = tuple(
        SealedRecordManifestMetadata(
            record_id=row.scenario_id,
            kind="rootless-living-dex-dependency-development-opening-v2",
            declared_record_sha256=hashlib.sha256(row.canonical_private_bytes()).hexdigest(),
            manifest_sha256=_sha(f"manifest:{row.scenario_id}"),
            declared_total_bytes=len(row.canonical_private_bytes()),
        )
        for row in openings
    )
    return RootlessDependencyEvaluationDesignV2(commitment_roster_from_metadata_v2(metadata))


def _public() -> dict[str, str]:
    return {
        "source_commit": "a" * 40,
        "source_bundle_sha256": _sha("source"),
        "runner_sha256": _sha("runner"),
        "runtime_sha256": _sha("runtime"),
        "core_sha256": _sha("core"),
    }


def _actual_store(tmp_path: Path):
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == private.resolve() else 1

    return initialize_private_root(
        private,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda path: False,
    )


def _args(mode: str) -> list[str]:
    return [
        "--mode",
        mode,
        "--execution-manifest",
        str(PROJECT_ROOT / ".public-execution-manifests" / "v2-learning.json"),
        "--expected-execution-manifest-sha256",
        _sha("manifest"),
        "--design",
        str(PROJECT_ROOT / "docs" / "evidence" / "v2-design.json"),
        "--expected-design-document-sha256",
        _sha("design-document"),
        "--private-root",
        "/private/root",
    ]


class _MetadataStore:
    def __init__(self, design: RootlessDependencyEvaluationDesignV2) -> None:
        self._rows = {
            row.record_id: SealedRecordManifestMetadata(
                record_id=row.record_id,
                kind="rootless-living-dex-dependency-development-opening-v2",
                declared_record_sha256=row.declared_record_sha256,
                manifest_sha256=row.manifest_sha256,
                declared_total_bytes=row.declared_total_bytes,
            )
            for row in design.development_roster.rows
        }
        self.payload_open_calls = 0
        self.published: list[tuple[str, str, object]] = []

    def inspect_sealed_record_metadata(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> SealedRecordManifestMetadata | None:
        row = self._rows.get(record_id)
        assert row is None or row.kind == expected_kind
        return row

    def find_sealed_record(self, *args: object, **kwargs: object) -> object:
        self.payload_open_calls += 1
        raise AssertionError("fit stage opened a development payload")

    def publish_sealed_record(
        self,
        record_id: str,
        *,
        kind: str,
        record: object,
    ) -> object:
        self.published.append((record_id, kind, record))
        return object()


def _patch_fit_environment(
    monkeypatch: pytest.MonkeyPatch,
    design: RootlessDependencyEvaluationDesignV2,
    store: object,
    events: list[str],
) -> None:
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_read_public_document",
        lambda *args, **kwargs: design.public_dict(),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_current_public_bindings",
        lambda **kwargs: _public(),
    )

    def gate(*args: object, **kwargs: object) -> str:
        events.append("manifest")
        return _sha("manifest")

    monkeypatch.setitem(SCRIPT["main"].__globals__, "_authenticate_gate", gate)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "open_private_root",
        lambda *args, **kwargs: store,
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


def test_fit_preflight_authenticates_manifest_and_metadata_without_fit_or_payload_open(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    design = _design()
    store = _MetadataStore(design)
    events: list[str] = []
    _patch_fit_environment(monkeypatch, design, store, events)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "materialize_claimed_v2_fit_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preflight fit")),
    )

    assert SCRIPT["main"](_args("fit-preflight")) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready_identity_unclaimed"
    assert result["development_payloads_opened"] == 0
    assert result["fit_claim_consumed"] is False
    assert events == ["manifest"]
    assert store.payload_open_calls == 0


def test_fit_claim_writer_returns_before_optimizer_or_publication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    design = _design()
    store = _MetadataStore(design)
    events: list[str] = []
    _patch_fit_environment(monkeypatch, design, store, events)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "write_root_claim",
        lambda *args, **kwargs: events.append("claim"),
    )

    bundle = SimpleNamespace(public_dict=lambda: {"schema": "synthetic-fit-bundle"})

    def materialize(*args: object, **kwargs: object) -> object:
        assert events[-1] == "claim"
        events.append("fit")
        return bundle

    def publish(publisher: object, value: object) -> object:
        assert events[-1] == "fit"
        assert value is bundle
        events.append("publish")
        return SimpleNamespace(
            bundle=bundle,
            fit_record_manifest_sha256=_sha("fit-record-manifest"),
            fit_manifest_manifest_sha256=_sha("fit-manifest-manifest"),
            fit_terminal_manifest_sha256=_sha("fit-terminal-manifest"),
        )

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "materialize_claimed_v2_fit_bundle",
        materialize,
    )
    monkeypatch.setitem(SCRIPT["main"].__globals__, "publish_v2_fit_bundle", publish)

    assert SCRIPT["main"](_args("fit")) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed_compliance_replacement_fit"
    assert result["fit_claim_consumed"] is True
    assert events == ["manifest", "claim", "fit", "publish"]
    assert store.payload_open_calls == 0


def test_postclaim_fit_failure_uses_distinct_retained_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    design = _design()
    store = _MetadataStore(design)
    events: list[str] = []
    _patch_fit_environment(monkeypatch, design, store, events)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "write_root_claim",
        lambda *args, **kwargs: events.append("claim"),
    )

    def fail_after_claim(*args: object, **kwargs: object) -> object:
        assert events[-1] == "claim"
        raise RuntimeError("private-looking detail must not escape")

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "materialize_claimed_v2_fit_bundle",
        fail_after_claim,
    )

    assert SCRIPT["main"](_args("fit")) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["claim_consumed"] is True
    assert result["claim_state"] == "consumed"
    assert result["effects"] == "not_attested"
    assert len(store.published) == 1
    record_id, kind, document = store.published[0]
    assert "fit-failure" in record_id
    assert kind == "rootless-dependency-fit-failure-v2"
    assert isinstance(document, dict)
    assert document["status"] == "failed"


def test_uncertain_claim_write_reconciles_visible_marker_as_consumed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    design = _design()
    store = _MetadataStore(design)
    events: list[str] = []
    _patch_fit_environment(monkeypatch, design, store, events)
    published_claim: dict[str, str] = {}

    def uncertain_write(*args: object, **kwargs: str) -> None:
        published_claim.update(kwargs)
        raise RuntimeError("directory sync result uncertain")

    def reconcile(registry: object, identity: str) -> dict[str, str]:
        assert identity == published_claim["root_consumption_sha256"]
        return {
            "schema": "pokemon.red.fresh-composition-root-claim.v1",
            **published_claim,
        }

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "write_root_claim",
        uncertain_write,
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "read_root_claim",
        reconcile,
    )

    assert SCRIPT["main"](_args("fit")) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["claim_consumed"] is True
    assert result["claim_state"] == "consumed"
    assert result["effects"] == "not_attested"
    assert len(store.published) == 1


def test_unreadable_claim_after_write_failure_is_reported_as_uncertain(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    design = _design()
    store = _MetadataStore(design)
    events: list[str] = []
    _patch_fit_environment(monkeypatch, design, store, events)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "write_root_claim",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("sync uncertain")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "read_root_claim",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("ledger unreadable")),
    )

    assert SCRIPT["main"](_args("fit")) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["claim_consumed"] is False
    assert result["claim_state"] == "uncertain"
    assert result["effects"] == "not_attested"
    assert store.published == []


def test_comparison_preflight_authenticates_fit_claim_and_opens_no_dev_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _actual_store(tmp_path)
    provisioned = provision_v2_development_commitments(store)
    design = RootlessDependencyEvaluationDesignV2(provisioned.roster)
    fit_binding = EvaluationExecutionBindingV2(
        operation="fit",
        source_commit="b" * 40,
        source_bundle_sha256=_sha("fit-source"),
        runner_sha256=_sha("fit-runner"),
        runtime_sha256=_sha("fit-runtime"),
    )
    fit_claim = build_dependency_fit_claim_v2(design, execution_binding=fit_binding)
    claimed = claim_v2_fit_before_computation(fit_claim, claim_writer=lambda value: None)
    bundle = materialize_claimed_v2_fit_bundle(
        design,
        claimed_fit=claimed,
        fit_execution_manifest_sha256=_sha("fit-manifest"),
        executable_bundle_sha256=_sha("fit-bundle"),
    )
    publish_v2_fit_bundle(store, bundle)
    comparison_binding = EvaluationExecutionBindingV2(
        operation="comparison",
        source_commit=_public()["source_commit"],
        source_bundle_sha256=_public()["source_bundle_sha256"],
        runner_sha256=_public()["runner_sha256"],
        runtime_sha256=_public()["runtime_sha256"],
    )
    comparison_claim = build_dependency_comparison_claim_v2(
        design,
        fit_claim=fit_claim,
        fit_bundle_pins=bundle.pins,
        execution_binding=comparison_binding,
    )
    args = SimpleNamespace(
        fit_source_commit=fit_binding.source_commit,
        fit_source_bundle_sha256=fit_binding.source_bundle_sha256,
        fit_runner_sha256=fit_binding.runner_sha256,
        fit_runtime_sha256=fit_binding.runtime_sha256,
        fit_claim_sha256=fit_claim.semantic_claim_sha256,
        fit_execution_identity_sha256=fit_claim.execution_identity_sha256,
        train_dataset_sha256=bundle.pins.fit_identity.train_dataset_sha256,
        fit_record_sha256=bundle.pins.fit_identity.fit_record_sha256,
        fit_sha256=bundle.pins.fit_identity.fit_sha256,
        model_sha256=bundle.pins.fit_identity.model_sha256,
        fit_execution_manifest_sha256=(bundle.pins.fit_identity.fit_execution_manifest_sha256),
        executable_bundle_sha256=bundle.pins.fit_identity.executable_bundle_sha256,
        fit_manifest_record_sha256=bundle.pins.fit_manifest_record_sha256,
        fit_terminal_record_sha256=bundle.pins.fit_terminal_record_sha256,
        comparison_claim_sha256=comparison_claim.semantic_claim_sha256,
        comparison_execution_identity_sha256=comparison_claim.execution_identity_sha256,
        expected_design_document_sha256=_sha("design-document"),
        execution_manifest=Path("unused"),
        expected_execution_manifest_sha256=_sha("comparison-manifest"),
        private_root=Path("/private/root"),
    )
    opened_ids: list[str] = []

    class ObservedStore:
        def inspect_sealed_record_metadata(self, *values: object, **kwargs: object):
            return store.inspect_sealed_record_metadata(*values, **kwargs)  # type: ignore[arg-type]

        def find_sealed_record(self, record_id: str, **kwargs: object):
            opened_ids.append(record_id)
            return store.find_sealed_record(record_id, **kwargs)  # type: ignore[arg-type]

    expected_claim = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": fit_claim.semantic_claim_sha256,
        "execution_identity_sha256": fit_claim.execution_identity_sha256,
        "source_commit": fit_binding.source_commit,
        "runner_sha256": fit_binding.runner_sha256,
    }
    monkeypatch.setitem(
        SCRIPT["_comparison_preflight"].__globals__,
        "_authenticate_gate",
        lambda *values, **kwargs: _sha("comparison-manifest"),
    )
    monkeypatch.setitem(
        SCRIPT["_comparison_preflight"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/registry"),
    )
    monkeypatch.setitem(
        SCRIPT["_comparison_preflight"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *values, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_comparison_preflight"].__globals__,
        "read_root_claim",
        lambda *values, **kwargs: expected_claim,
    )
    monkeypatch.setitem(
        SCRIPT["_comparison_preflight"].__globals__,
        "root_claim_is_available",
        lambda *values, **kwargs: True,
    )
    monkeypatch.setitem(
        SCRIPT["_comparison_preflight"].__globals__,
        "open_private_root",
        lambda *values, **kwargs: ObservedStore(),
    )

    result = SCRIPT["_comparison_preflight"](args, design, _public())

    assert result["development_payloads_opened"] == 0
    assert len(opened_ids) == 3
    assert not any(row.record_id in opened_ids for row in design.development_roster.rows)


def test_argument_failure_is_sanitized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "secret" / "private"
    assert SCRIPT["main"](["--private-root", str(private)]) == 1
    captured = capsys.readouterr()
    assert str(tmp_path) not in captured.out
    assert captured.err == ""
    assert json.loads(captured.out)["private_path_fields"] == 0
