from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_setup_bindings.py"


def _script() -> dict[str, Any]:
    loaded = runpy.run_path(
        str(SCRIPT_PATH),
        run_name="freeze_red_setup_bindings_test",
    )
    return loaded["main"].__globals__


def test_script_wires_one_private_catalog_to_the_action_free_materializer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script()
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(b"{}\n")
    catalog.chmod(0o600)
    private_root = tmp_path / "private-root"
    private_root.mkdir()
    observed: dict[str, object] = {}

    class _Source:
        def __init__(self, reader: object, expected: str, meter: object) -> None:
            observed["payload"] = reader()  # type: ignore[operator]
            observed["expected"] = expected
            observed["meter"] = meter

    class _Result:
        def public_dict(self) -> dict[str, object]:
            return {
                "slot_count": 15,
                "provider_contracts_bound": 45,
                "private_identity_fields": 0,
                "private_path_fields": 0,
            }

    store = object()
    monkeypatch.setitem(
        script,
        "open_private_root",
        lambda root, *, repository_root: (
            observed.update(root=root, repository_root=repository_root) or store
        ),
    )
    monkeypatch.setitem(script, "RedLivingDexSetupCatalogSource", _Source)

    def materialize(actual_store: object, *, source: object, effects_meter: object):
        observed["actual_store"] = actual_store
        observed["source"] = source
        observed["effects_meter"] = effects_meter
        return _Result()

    monkeypatch.setitem(script, "materialize_red_living_dex_setup_bindings", materialize)

    code = script["main"](
        [
            "--source-catalog",
            str(catalog),
            "--expected-source-catalog-sha256",
            "a" * 64,
            "--private-root",
            str(private_root),
        ]
    )

    assert code == 0
    assert observed["payload"] == b"{}\n"
    assert observed["expected"] == "a" * 64
    assert observed["actual_store"] is store
    assert observed["meter"] is observed["effects_meter"]
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "complete"
    assert result["slot_count"] == 15
    assert result["provider_contracts_bound"] == 45
    assert str(tmp_path) not in json.dumps(result, sort_keys=True)


def test_script_failure_is_path_free_and_keeps_setup_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script()
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(b"{}\n")
    catalog.chmod(0o600)
    private_root = tmp_path / "private-root"
    private_root.mkdir()
    private_detail = str(tmp_path / "private" / "route-record.json")

    monkeypatch.setitem(script, "open_private_root", lambda *args, **kwargs: object())
    monkeypatch.setitem(
        script,
        "RedLivingDexSetupCatalogSource",
        lambda *args, **kwargs: object(),
    )

    def fail(*args: object, **kwargs: object) -> object:
        raise script["RedLivingDexSetupMaterializationError"](private_detail)

    monkeypatch.setitem(script, "materialize_red_living_dex_setup_bindings", fail)

    code = script["main"](
        [
            "--source-catalog",
            str(catalog),
            "--expected-source-catalog-sha256",
            "a" * 64,
            "--private-root",
            str(private_root),
        ]
    )

    assert code == 1
    result = json.loads(capsys.readouterr().out)
    encoded = json.dumps(result, sort_keys=True)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "source_materialization"
    assert result["actionful_setup_execution_authorized"] is False
    assert result["retry_allowed_only_if_effects_zero"] is True
    assert private_detail not in encoded
    assert str(tmp_path) not in encoded


def test_script_rejects_a_world_readable_catalog_before_private_store_access(
    tmp_path: Path,
) -> None:
    script = _script()
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(b"{}\n")
    catalog.chmod(0o644)
    reader = script["_private_catalog_reader"](catalog)

    with pytest.raises(
        script["RedLivingDexSetupSourceError"],
        match="file authentication failed",
    ):
        reader()


def test_script_rejects_a_catalog_not_owned_by_the_current_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _script()
    catalog = tmp_path / "catalog.json"
    catalog.write_bytes(b"{}\n")
    catalog.chmod(0o600)
    monkeypatch.setattr(
        script["os"],
        "geteuid",
        lambda: script["os"].stat(catalog).st_uid + 1,
    )
    reader = script["_private_catalog_reader"](catalog)

    with pytest.raises(
        script["RedLivingDexSetupSourceError"],
        match="file authentication failed",
    ):
        reader()


def test_script_has_no_rom_emulator_controller_or_training_entrypoint() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "POKEMON_RED_ROM",
        "PyBoyAdapter",
        "CountingExecutor",
        "execute_setup(",
        "model.fit(",
        "CompletionFirstGoalTeacher",
    ):
        assert forbidden not in source
    assert "materialize_red_living_dex_setup_bindings(" in source
