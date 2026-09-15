from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_battle_cartridge_campaign import _document

SCRIPT = runpy.run_path("scripts/run_red_battle_cartridge_campaign.py")
GLOBALS = SCRIPT["_run"].__globals__
CampaignError = SCRIPT["RedBattleCartridgeCampaignError"]


def _inputs(tmp_path: Path) -> tuple[SimpleNamespace, bytes]:
    state = b"exact source state"
    rom = b"exact rom"
    document = _document()
    document["source"]["state_sha256"] = hashlib.sha256(state).hexdigest()
    document["rom_sha256"] = hashlib.sha256(rom).hexdigest()
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    plan = tmp_path / "campaign.json"
    source = tmp_path / "source.state"
    rom_path = tmp_path / "red.gb"
    private_root = tmp_path / "private"
    plan.write_bytes(payload)
    source.write_bytes(state)
    rom_path.write_bytes(rom)
    private_root.mkdir()
    return (
        SimpleNamespace(
            private_plan=plan,
            expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
            source_state=source,
            private_root=private_root,
            rom=rom_path,
            qualification_ci_run_id=document["qualification_ci_run_id"],
            allow_same_device_private_root=True,
        ),
        payload,
    )


def test_script_authenticates_all_frozen_inputs_before_durable_campaign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, payload = _inputs(tmp_path)
    document = json.loads(payload)
    calls = []
    identity = SimpleNamespace(git_commit=document["source_commit"])
    store = object()
    monkeypatch.setitem(GLOBALS, "detect_source_identity", lambda *a, **kw: identity)
    monkeypatch.setitem(GLOBALS, "require_clean_source", lambda value: calls.append("clean"))
    monkeypatch.setitem(
        GLOBALS, "require_published_source", lambda *args: calls.append("published")
    )
    monkeypatch.setitem(
        GLOBALS,
        "committed_source_bundle_sha256",
        lambda root: document["source_bundle_sha256"],
    )
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda path: path)
    monkeypatch.setitem(
        GLOBALS, "verify_rom", lambda path: SimpleNamespace(sha256=document["rom_sha256"])
    )
    monkeypatch.setitem(GLOBALS, "open_private_root", lambda *a, **kw: store)

    def execute(received_store, plan, run_case):
        assert received_store is store
        assert plan.sha256 == args.expected_plan_sha256
        assert callable(run_case)
        calls.append("execute")
        return {"status": "passed_with_declared_coverage_gaps"}

    monkeypatch.setitem(GLOBALS, "execute_durable_red_battle_cartridge_campaign", execute)

    assert SCRIPT["_run"](args) == {"status": "passed_with_declared_coverage_gaps"}
    assert calls == ["clean", "published", "execute"]


def test_script_forwards_frozen_contingency_policy(tmp_path, monkeypatch):
    from pokemon_red_completion.red_battle_contingency import CONTINGENCY_POLICY
    args, payload = _inputs(tmp_path)
    document = json.loads(payload)
    document["policy"] = CONTINGENCY_POLICY
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    args.private_plan.write_bytes(payload)
    args.expected_plan_sha256 = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(GLOBALS, "detect_source_identity",
                        lambda *a, **kw: SimpleNamespace(git_commit=document["source_commit"]))
    monkeypatch.setitem(GLOBALS, "require_clean_source", lambda *a: None)
    monkeypatch.setitem(GLOBALS, "require_published_source", lambda *a: None)
    monkeypatch.setitem(GLOBALS, "committed_source_bundle_sha256",
                        lambda *a: document["source_bundle_sha256"])
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda path: path)
    monkeypatch.setitem(GLOBALS, "verify_rom",
                        lambda *a: SimpleNamespace(sha256=document["rom_sha256"]))
    monkeypatch.setitem(GLOBALS, "open_private_root", lambda *a, **kw: object())
    calls = []
    monkeypatch.setitem(GLOBALS, "qualify_repeatable_red_wild_battle",
                        lambda *a, **kw: calls.append(kw))
    def execute(store, plan, run_case):
        run_case(plan.cases[0], object(), object())
        return {"status": "synthetic"}
    monkeypatch.setitem(GLOBALS, "execute_durable_red_battle_cartridge_campaign", execute)
    assert SCRIPT["_run"](args) == {"status": "synthetic"}
    assert calls[0]["policy"] == CONTINGENCY_POLICY


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("expected_plan_sha256", "0" * 64, "plan digest"),
        ("qualification_ci_run_id", 999, "CI run"),
    ],
)
def test_script_rejects_plan_or_ci_mismatch_before_source_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    match: str,
) -> None:
    args, _ = _inputs(tmp_path)
    setattr(args, field, value)
    touched = []
    monkeypatch.setitem(GLOBALS, "detect_source_identity", lambda *a, **kw: touched.append(True))
    with pytest.raises(CampaignError, match=match):
        SCRIPT["_run"](args)
    assert touched == []


def test_script_rejects_source_bundle_before_rom_or_private_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, payload = _inputs(tmp_path)
    document = json.loads(payload)
    identity = SimpleNamespace(git_commit=document["source_commit"])
    monkeypatch.setitem(GLOBALS, "detect_source_identity", lambda *a, **kw: identity)
    monkeypatch.setitem(GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(GLOBALS, "require_published_source", lambda *args: None)
    monkeypatch.setitem(GLOBALS, "committed_source_bundle_sha256", lambda root: "0" * 64)
    touched = []
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda path: touched.append(True))
    with pytest.raises(CampaignError, match="source bundle"):
        SCRIPT["_run"](args)
    assert touched == []
