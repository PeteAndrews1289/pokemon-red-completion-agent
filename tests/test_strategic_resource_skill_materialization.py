from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from materialize_strategic_resource_skill import (  # noqa: E402
    PROJECT_ROOT,
    _require_private_new_output,
    main,
)

from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRuntimeError,
)


def test_resource_materializer_help_is_explicitly_non_collection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "construction-only resource" in output
    assert "--acquire-resource-id" in output
    assert "gold_teeth" in output
    assert "fly" in output
    assert "--execute" not in output


def test_resource_materializer_accepts_only_new_private_output(tmp_path: Path) -> None:
    rom_dir = tmp_path / "roms"
    capture_dir = tmp_path / "captures"
    rom_dir.mkdir()
    capture_dir.mkdir()
    rom = rom_dir / "game.gb"
    rom.touch()

    accepted = capture_dir / "next.state"
    assert _require_private_new_output(accepted, rom) == accepted.resolve()

    with pytest.raises(StrategicScenarioRuntimeError, match="beside the ROM"):
        _require_private_new_output(rom_dir / "next.state", rom)
    accepted.touch()
    with pytest.raises(StrategicScenarioRuntimeError, match="already exists"):
        _require_private_new_output(accepted, rom)
    with pytest.raises(StrategicScenarioRuntimeError, match="outside the repository"):
        _require_private_new_output(PROJECT_ROOT / "private.state", rom)
