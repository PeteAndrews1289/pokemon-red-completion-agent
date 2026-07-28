from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion import cli


def test_route_command_prints_validated_hall_of_fame_route(capsys) -> None:
    assert cli.main(["route"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["id"] == "power_on"
    assert payload[-1]["id"] == "enter_hall_of_fame"
    assert payload[-1]["prerequisites"] == ["defeat_champion"]
    assert len(payload) >= 30


def test_bootstrap_command_prints_only_public_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeReport:
        def public_dict(self) -> dict[str, object]:
            return {"status": "ok", "clean_power_on": True}

    private_path = Path("/private/Pokemon Red.gb")
    monkeypatch.setattr(cli, "resolve_rom_path", lambda argument: private_path)
    monkeypatch.setattr(cli, "run_bootstrap_smoke", lambda path: FakeReport())

    assert cli.main(["bootstrap", "--rom", str(private_path)]) == 0

    output = capsys.readouterr().out
    assert json.loads(output) == {"clean_power_on": True, "status": "ok"}
    assert str(private_path) not in output
