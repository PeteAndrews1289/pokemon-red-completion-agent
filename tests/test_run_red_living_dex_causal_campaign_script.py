from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_red_living_dex_causal_invocation import _frozen_fixture
from test_red_living_dex_claim_first_invocation import _consumer

from pokemon_red_completion.collection_protocol import (
    committed_source_bundle_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_red_living_dex_causal_campaign.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_red_living_dex_causal_campaign_script_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments(tmp_path: Path, root: object) -> list[str]:
    private_root = tmp_path / "private"
    state_path = private_root / "selected.state"
    envelope_path = private_root / "selected.state.json"
    state_path.write_bytes(root.state_bytes)  # type: ignore[attr-defined]
    envelope_path.write_bytes(root.envelope_bytes)  # type: ignore[attr-defined]
    state_path.chmod(0o600)
    envelope_path.chmod(0o600)
    consumer = _consumer()
    return [
        "--private-root",
        str(private_root),
        "--expected-source-commit",
        consumer.source_commit,
        "--expected-source-bundle-sha256",
        consumer.source_bundle_sha256,
        "--exact-ci-run",
        str(consumer.exact_ci_run),
        "--exact-ci-attempt",
        str(consumer.exact_ci_attempt),
        "--selected-state",
        str(state_path),
        "--selected-envelope",
        str(envelope_path),
        "--rom",
        str(tmp_path / "private-red.gb"),
    ]


def _bootstrap_identity() -> tuple[str, str, int, int]:
    consumer = _consumer()
    return (
        consumer.source_commit,
        consumer.source_bundle_sha256,
        consumer.exact_ci_run,
        consumer.exact_ci_attempt,
    )


class _Receipt:
    def __init__(self, *, retry_allowed: bool, recorded: bool) -> None:
        self.causal = SimpleNamespace(retry_allowed=retry_allowed)
        self._recorded = recorded

    def public_dict(self) -> dict[str, object]:
        return {
            "causal_train_example_recorded": self._recorded,
            "model_fits": 0,
            "model_predictions": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "retry_allowed": self.causal.retry_allowed,
            "teacher_queries": 0,
        }


def test_cli_is_one_direct_consumer_with_bootstrap_before_project_imports() -> None:
    module = _load_script()
    actions = {action.dest for action in module._parser()._actions}
    assert actions == {
        "help",
        "private_root",
        "expected_source_commit",
        "expected_source_bundle_sha256",
        "exact_ci_run",
        "exact_ci_attempt",
        "selected_state",
        "selected_envelope",
        "rom",
    }
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    bootstrap = source.index("_BOOTSTRAP_IDENTITY = _authenticate_current_source")
    sentinel = source.index("        _install_numpy_sentinel()")
    project_import = source.index(
        "from pokemon_red_completion.private_artifacts import ("
    )
    runtime_stage = source.index(
        "        _RUNTIME_STAGE = prepare_authenticated_runtime_stage(VENV_SITE_PACKAGES)"
    )
    third_party_search = source.index(
        "        _enable_authenticated_third_party_search(_RUNTIME_STAGE.closure)"
    )
    assert bootstrap < sentinel < project_import < runtime_stage < third_party_search
    assert "freeze_red_living_dex_causal_campaign(" not in source
    assert "preflight_red_living_dex_claim_first_invocation(" not in source
    assert "claim_registry" not in actions
    assert "ordinal" not in actions
    assert "expected_selected_physical_root_sha256" not in actions
    assert "resolver" not in actions


def test_bootstrap_source_bundle_matches_the_canonical_committed_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()

    def portable_git(
        arguments: tuple[str, ...],
        *,
        maximum_bytes: int = 128 * 1024 * 1024,
    ) -> bytes:
        completed = subprocess.run(
            ("git", "--no-replace-objects", *arguments),
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
        )
        assert len(completed.stdout) <= maximum_bytes
        return completed.stdout

    monkeypatch.setattr(module, "_git", portable_git)
    commit = portable_git(("rev-parse", "--verify", "HEAD^{commit}"), maximum_bytes=128)
    commit = commit.decode("ascii").strip()

    assert module._committed_red_source_bundle_sha256(commit) == (
        committed_source_bundle_sha256(PROJECT_ROOT, revision=commit)
    )


def test_bootstrap_rejects_source_bundle_substitution_before_source_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    consumer = _consumer()
    source_state_calls: list[dict[str, object]] = []
    monkeypatch.setattr(module, "_require_interpreter", lambda: None)
    monkeypatch.setattr(module, "_require_environment", lambda: None)
    monkeypatch.setattr(
        module,
        "_committed_red_source_bundle_sha256",
        lambda _commit: "f" * 64,
    )
    monkeypatch.setattr(
        module,
        "_require_source_state",
        lambda **kwargs: source_state_calls.append(kwargs),
    )

    with pytest.raises(module._BootstrapError):
        module._authenticate_current_source(
            [
                "--expected-source-commit",
                consumer.source_commit,
                "--expected-source-bundle-sha256",
                consumer.source_bundle_sha256,
                "--exact-ci-run",
                str(consumer.exact_ci_run),
                "--exact-ci-attempt",
                str(consumer.exact_ci_attempt),
            ]
        )

    assert source_state_calls == []


def test_environment_accepts_only_the_authenticated_pysdl2_self_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    dll_path = (tmp_path / "stage/venv/lib/python3.14/site-packages/sdl2dll/dll").resolve()
    dll_path.mkdir(parents=True, mode=0o700)

    monkeypatch.setattr(module.os, "environ", {"OPENSSL_CONF": module.os.devnull})
    module._require_environment(authenticated_pysdl2_dll_path=dll_path)

    module.os.environ["PYSDL2_DLL_PATH"] = str(dll_path)
    module._require_environment(authenticated_pysdl2_dll_path=dll_path)

    with pytest.raises(module._BootstrapError):
        module._require_environment()

    for substituted_path in (dll_path.parent, Path(f"{dll_path}-poison")):
        module.os.environ["PYSDL2_DLL_PATH"] = str(substituted_path)
        with pytest.raises(module._BootstrapError):
            module._require_environment(authenticated_pysdl2_dll_path=dll_path)


def test_environment_rejects_an_alias_for_the_authenticated_pysdl2_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    dll_path = (tmp_path / "stage/venv/lib/python3.14/site-packages/sdl2dll/dll").resolve()
    dll_path.mkdir(parents=True, mode=0o700)
    alias = tmp_path / "sdl-alias"
    alias.symlink_to(dll_path, target_is_directory=True)
    monkeypatch.setattr(
        module.os,
        "environ",
        {
            "OPENSSL_CONF": module.os.devnull,
            "PYSDL2_DLL_PATH": str(alias),
        },
    )

    with pytest.raises(module._BootstrapError):
        module._require_environment(authenticated_pysdl2_dll_path=dll_path)


def test_runtime_postcheck_accepts_only_the_staged_pysdl2_self_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    site_packages = (tmp_path / "stage/venv/lib/python3.14/site-packages").resolve()
    dll_path = site_packages / "sdl2dll/dll"
    dll_path.mkdir(parents=True, mode=0o700)
    closure = module.ExecutionRuntimeClosure((), site_packages)
    finder = module.AuthenticatedRuntimeFinder(closure)
    calls: list[str] = []
    monkeypatch.setattr(module, "__name__", "__main__")
    monkeypatch.setattr(module, "_RUNTIME_STAGE", SimpleNamespace(closure=closure))
    monkeypatch.setattr(module, "_RUNTIME_FINDER", finder)
    monkeypatch.setattr(
        module,
        "require_authenticated_runtime_finder",
        lambda value: calls.append("finder") if value is closure else pytest.fail(),
    )
    monkeypatch.setattr(
        module,
        "require_loaded_runtime_origins",
        lambda value: calls.append("origins") if value is closure else pytest.fail(),
    )
    monkeypatch.setattr(
        module.os,
        "environ",
        {
            "OPENSSL_CONF": module.os.devnull,
            "PYSDL2_DLL_PATH": str(dll_path),
        },
    )

    module._require_runtime_postcheck()

    assert calls == ["finder", "origins"]


def test_bootstrap_rejects_project_bytecode_cache_from_filesystem_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    root = (tmp_path / "project").resolve()
    source_root = root / "src"
    package = source_root / "pokemon_red_completion"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\n", encoding="ascii")
    (package / "__init__.py").write_text("", encoding="ascii")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-314.pyc").write_bytes(b"poison")
    monkeypatch.setattr(module, "PROJECT_ROOT", root)
    monkeypatch.setattr(module, "SRC_ROOT", source_root)

    with pytest.raises(module._BootstrapError):
        module._filesystem_project_sources(
            {
                "pyproject.toml",
                "src/pokemon_red_completion/__init__.py",
            }
        )


@pytest.mark.skipif(
    not Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
        "Python.framework/Versions/3.14/bin/python3.14"
    ).exists(),
    reason="the production bootstrap is pinned to its macOS host",
)
def test_real_isolated_bootstrap_rejects_runpy_preload_before_private_access() -> None:
    python = Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
        "Python.framework/Versions/3.14/bin/python3.14"
    )
    program = (
        "import runpy,sys,types;"
        "sys.modules['pokemon_red_completion.preloaded']="
        "types.ModuleType('pokemon_red_completion.preloaded');"
        f"sys.argv=[{str(SCRIPT_PATH)!r}];"
        f"runpy.run_path({str(SCRIPT_PATH)!r},run_name='__main__')"
    )
    completed = subprocess.run(
        (str(python), "-I", "-S", "-B", "-c", program),
        cwd=PROJECT_ROOT,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "stage": "bootstrap_source_authentication",
        "status": "failed_closed",
    }
    assert "private" not in completed.stderr.casefold()


def test_bootstrap_has_no_status_filter_authority_and_requires_main_ci() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"status",\n                "--porcelain"' not in source
    assert 'document.get("head_branch") != "main"' in source


def test_main_rejects_nonbootstrap_import_before_private_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, _store, _producer, root, _outer, _registry, _campaign = _frozen_fixture(tmp_path)
    monkeypatch.setattr(module, "_BOOTSTRAP_IDENTITY", None)
    monkeypatch.setattr(
        module,
        "open_private_root",
        lambda *_args, **_kwargs: pytest.fail("private store opened before bootstrap"),
    )

    assert module.main(_arguments(tmp_path, root)) == 1
    public = json.loads(capsys.readouterr().out)
    assert public["stage"] == "bootstrap_source_authentication"
    assert public["controller_actions"] == 0
    assert public["automatic_retry_allowed"] is False


def test_main_calls_direct_consumer_once_and_emits_metered_path_free_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, store, _producer, root, _outer, _registry, _campaign = _frozen_fixture(tmp_path)
    calls: list[dict[str, object]] = []
    postchecks: list[dict[str, object]] = []
    monkeypatch.setattr(module, "_BOOTSTRAP_IDENTITY", _bootstrap_identity())
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: store)
    monkeypatch.setattr(
        module,
        "_require_source_state",
        lambda **kwargs: postchecks.append(kwargs),
    )

    def execute(*_args: object, **kwargs: object) -> _Receipt:
        calls.append(kwargs)
        meter = kwargs["meter"]
        meter.record_root_claim()
        meter.record_controller_actions(3)
        meter.record_emulator_frames(180)
        meter.record_provider_execution()
        return _Receipt(retry_allowed=False, recorded=True)

    monkeypatch.setattr(module, "execute_red_living_dex_causal_campaign", execute)

    assert module.main(_arguments(tmp_path, root)) == 0
    public = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert "claim_registry" not in calls[0]
    assert "resolver" not in calls[0]
    assert public["status"] == "one_causal_campaign_settled"
    assert public["retry_allowed"] is False
    assert public["automatic_retry_allowed"] is False
    assert public["controller_actions"] == 3
    assert public["emulator_frames"] == 180
    assert public["provider_executions"] == 1
    assert public["root_claims_metered_setup_only"] == 1
    assert public["causal_behavior_commitments"] == 1
    assert public["setup_behavior_draws_metered"] == 0
    assert public["model_fits"] == 0
    assert public["model_predictions"] == 0
    assert len(postchecks) == 1
    assert str(tmp_path) not in json.dumps(public)


def test_selected_loader_revalidates_private_namespace_on_every_reopen(
    tmp_path: Path,
) -> None:
    module = _load_script()
    _plan, store, _producer, root, _outer, _registry, campaign = _frozen_fixture(tmp_path)
    private_root = tmp_path / "selected-private"
    private_root.mkdir(mode=0o700)
    state_path = private_root / "selected.state"
    envelope_path = private_root / "selected.state.json"
    state_path.write_bytes(root.state_bytes)
    envelope_path.write_bytes(root.envelope_bytes)
    state_path.chmod(0o600)
    envelope_path.chmod(0o600)
    loader = module._selected_loader(
        store,
        logical_root_sha256=campaign.logical_root_sha256,
        physical_root_sha256=campaign.physical_root_sha256,
        private_root=private_root,
        state_path=state_path,
        envelope_path=envelope_path,
    )

    assert loader(campaign.ordinal).root == root

    outside = tmp_path / "outside.state"
    outside.write_bytes(root.state_bytes)
    outside.chmod(0o600)
    state_path.unlink()
    state_path.symlink_to(outside)

    with pytest.raises(
        module.RedLivingDexCausalInvocationError,
        match="selected_root_authentication",
    ):
        loader(campaign.ordinal)


def test_selected_loader_rejects_a_nested_initialized_private_root(
    tmp_path: Path,
) -> None:
    module = _load_script()
    _plan, store, _producer, root, _outer, _registry, campaign = (
        _frozen_fixture(tmp_path)
    )
    private_root = tmp_path / "selected-private"
    nested = private_root / "nested-store"
    nested.mkdir(parents=True, mode=0o700)
    (nested / module.PRIVATE_ROOT_SENTINEL).write_bytes(b"nested-store\n")
    state_path = nested / "selected.state"
    envelope_path = nested / "selected.state.json"
    state_path.write_bytes(root.state_bytes)
    envelope_path.write_bytes(root.envelope_bytes)
    state_path.chmod(0o600)
    envelope_path.chmod(0o600)
    loader = module._selected_loader(
        store,
        logical_root_sha256=campaign.logical_root_sha256,
        physical_root_sha256=campaign.physical_root_sha256,
        private_root=private_root,
        state_path=state_path,
        envelope_path=envelope_path,
    )

    with pytest.raises(
        module.RedLivingDexCausalInvocationError,
        match="selected_root_authentication",
    ):
        loader(campaign.ordinal)


def test_preinput_retryable_receipt_never_loops_and_is_not_reported_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, store, _producer, root, _outer, _registry, _campaign = _frozen_fixture(tmp_path)
    calls = 0
    monkeypatch.setattr(module, "_BOOTSTRAP_IDENTITY", _bootstrap_identity())
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: store)
    monkeypatch.setattr(module, "_require_source_state", lambda **_kwargs: None)

    def execute(*_args: object, **_kwargs: object) -> _Receipt:
        nonlocal calls
        calls += 1
        return _Receipt(retry_allowed=True, recorded=False)

    monkeypatch.setattr(module, "execute_red_living_dex_causal_campaign", execute)

    assert module.main(_arguments(tmp_path, root)) == 1
    public = json.loads(capsys.readouterr().out)
    assert calls == 1
    assert public["status"] == "preinput_recovery_required_no_automatic_retry"
    assert public["retry_allowed"] is False
    assert public["automatic_retry_allowed"] is False


def test_postexecution_source_or_authority_failure_is_consumed_and_never_zeroed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, store, _producer, root, _outer, _registry, _campaign = _frozen_fixture(tmp_path)
    monkeypatch.setattr(module, "_BOOTSTRAP_IDENTITY", _bootstrap_identity())
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: store)
    monkeypatch.setattr(
        module,
        "_require_source_state",
        lambda **_kwargs: (_ for _ in ()).throw(module._BootstrapError()),
    )

    def execute(*_args: object, **kwargs: object) -> _Receipt:
        meter = kwargs["meter"]
        meter.record_controller_actions(2)
        meter.record_emulator_frames(90)
        return _Receipt(retry_allowed=False, recorded=False)

    monkeypatch.setattr(module, "execute_red_living_dex_causal_campaign", execute)

    assert module.main(_arguments(tmp_path, root)) == 1
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "consumed_postcheck_failed_no_retry"
    assert public["automatic_retry_allowed"] is False
    assert public["durable_result_unknown"] is False
    assert public["controller_actions"] == 2
    assert public["emulator_frames"] == 90
    assert public["causal_train_example_recorded"] is None
