from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from test_red_living_dex_claim_first_invocation import _fixture

from pokemon_red_completion.red_living_dex_causal_campaign import (
    load_red_living_dex_causal_campaign,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_causal_campaign.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "freeze_red_living_dex_causal_campaign_script_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments(
    tmp_path: Path,
    *,
    producer,  # type: ignore[no-untyped-def]
    root,  # type: ignore[no-untyped-def]
    retired: str,
) -> list[str]:
    private_root = tmp_path / "private"
    state_path = private_root / "causal-selected.state"
    envelope_path = private_root / "causal-selected.state.json"
    state_path.write_bytes(root.state_bytes)
    envelope_path.write_bytes(root.envelope_bytes)
    state_path.chmod(0o600)
    envelope_path.chmod(0o600)
    return [
        "--private-root",
        str(private_root),
        "--expected-source-commit",
        "c" * 40,
        "--expected-source-bundle-sha256",
        "d" * 64,
        "--exact-ci-run",
        "123",
        "--exact-ci-attempt",
        "1",
        "--expected-producer-plan-sha256",
        producer.producer_plan_sha256,
        "--expected-producer-private-plan-sha256",
        producer.producer_private_plan_sha256,
        "--expected-producer-manifest-sha256",
        producer.producer_manifest_sha256,
        "--ordinal",
        str(producer.ordinal),
        "--selected-state",
        str(state_path),
        "--selected-envelope",
        str(envelope_path),
        "--expected-selected-physical-root-sha256",
        root.physical_root_sha256,
        "--retired-physical-root-sha256",
        retired,
        "--claim-registry",
        str(tmp_path / "claims"),
    ]


def test_parser_is_freeze_only_and_has_no_runtime_or_gameplay_capability() -> None:
    module = _load_script()
    actions = {action.dest for action in module._parser()._actions}
    assert "rom" not in actions
    assert "rom_path" not in actions
    assert "execute" not in actions
    assert "mode" not in actions
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "run_red_living_dex_causal_campaign" not in source
    assert "materialize_living_dex_causal_example" not in source
    assert "RedLivingDexProductionSetupResolver" not in source
    assert "PyBoy" not in source


def test_main_freezes_one_path_free_train_campaign_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, store, _record, producer, root = _fixture(tmp_path, ordinal=3)
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    monkeypatch.setattr(module, "_require_current_source", lambda _args: None)
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: store)

    result = module.main(
        _arguments(
            tmp_path,
            producer=producer,
            root=root,
            retired="e" * 64,
        )
    )
    assert result == 0
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "one_action_free_train_campaign_frozen"
    assert public["selected_slots"] == 1
    assert public["retired_root_exclusions"] == 1
    assert public["controller_actions"] == 0
    assert public["emulator_frames"] == 0
    assert public["root_claims"] == 0
    assert public["causal_examples"] == 0
    assert public["private_identity_fields"] == 0
    assert public["private_path_fields"] == 0
    assert str(tmp_path) not in json.dumps(public)
    assert load_red_living_dex_causal_campaign(store).partition == "train"
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_main_fails_closed_if_the_selected_root_is_retired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, store, _record, producer, root = _fixture(tmp_path, ordinal=2)
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    monkeypatch.setattr(module, "_require_current_source", lambda _args: None)
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: store)

    result = module.main(
        _arguments(
            tmp_path,
            producer=producer,
            root=root,
            retired=root.physical_root_sha256,
        )
    )
    assert result == 1
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "failed_closed"
    assert public["campaign_commitment_published"] is False
    assert public["retry_allowed"] is False
    assert public["stage"] == "campaign_freeze"
    assert public["root_claims"] == 0
    assert public["controller_actions"] == 0
    assert public["causal_examples"] == 0
    assert public["private_identity_fields"] == 0
    assert public["private_path_fields"] == 0
    assert str(tmp_path) not in json.dumps(public)


def test_post_freeze_source_failure_reports_the_durable_commitment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    _plan, store, _record, producer, root = _fixture(tmp_path, ordinal=4)
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    checks = 0

    def check_source(_args: object) -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise module.CausalCampaignFreezeError(
                "current_source_authentication"
            )

    monkeypatch.setattr(module, "_require_current_source", check_source)
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: store)

    result = module.main(
        _arguments(
            tmp_path,
            producer=producer,
            root=root,
            retired="e" * 64,
        )
    )
    assert result == 1
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "frozen_postcheck_failed"
    assert public["stage"] == "post_freeze_source_authentication"
    assert public["campaign_commitment_published"] is True
    assert public["retry_allowed"] is False
    assert public["root_claims"] == 0
    assert public["controller_actions"] == 0
    assert load_red_living_dex_causal_campaign(store).partition == "train"
