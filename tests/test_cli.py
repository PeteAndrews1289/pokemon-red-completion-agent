from __future__ import annotations

import json

from pokemon_red_completion.cli import main


def test_route_command_prints_validated_hall_of_fame_route(capsys) -> None:
    assert main(["route"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["id"] == "power_on"
    assert payload[-1]["id"] == "enter_hall_of_fame"
    assert payload[-1]["prerequisites"] == ["defeat_champion"]
    assert len(payload) >= 30
