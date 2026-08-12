from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from materialize_strategic_scenario_skill import (  # noqa: E402
    PROJECT_ROOT,
    _materialized_checkpoint_id,
    _require_private_new_output,
    main,
)

from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRuntimeError,
)


def test_skill_materializer_help_names_its_non_collection_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "This is" in output
    assert "not a data-collection command" in output
    assert "--target-scenario-id" in output
    assert "--complete-objective-id" in output
    assert "--source-scenario-id" not in output


def test_skill_materialized_checkpoint_id_is_portable() -> None:
    checkpoint_id = _materialized_checkpoint_id(
        "red-strategic-scenario-v2-043-validation"
    )

    assert checkpoint_id == (
        "red-strategic-scenario-v2-043-validation-skill-materialized"
    )
    assert ":" not in checkpoint_id


def test_skill_materializer_accepts_only_new_private_non_rom_adjacent_output(
    tmp_path: Path,
) -> None:
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
