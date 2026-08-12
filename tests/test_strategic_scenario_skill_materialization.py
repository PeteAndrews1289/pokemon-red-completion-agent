from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from materialize_strategic_scenario_skill import (  # noqa: E402
    PROJECT_ROOT,
    _can_fly_from_cinnabar_to_origin,
    _can_fly_to_cinnabar_skill_boundary,
    _intermediate_checkpoint_id,
    _materialized_checkpoint_id,
    _require_private_new_output,
    _route_materialized_checkpoint_id,
    _SemanticTrackingExecutor,
    main,
)

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.observation import MapId, RawGameState  # noqa: E402
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
    assert "--intermediate-toward-target" in output
    assert "--complete-via-origin-route" in output
    assert "--relocate-to-skill-boundary" in output
    assert "--relocate-to-origin" in output
    assert "--maximum-flees" in output
    assert "--maximum-interruptions" in output
    assert "--maximum-trainer-battles" in output
    assert "--source-scenario-id" not in output


def test_skill_materialized_checkpoint_id_is_portable() -> None:
    checkpoint_id = _materialized_checkpoint_id(
        "red-strategic-scenario-v2-043-validation"
    )

    assert checkpoint_id == (
        "red-strategic-scenario-v2-043-validation-skill-materialized"
    )
    assert ":" not in checkpoint_id

    intermediate = _intermediate_checkpoint_id(
        "red-strategic-scenario-v2-015-validation",
        "reach_saffron",
    )
    assert intermediate == (
        "red-strategic-scenario-v2-015-validation-toward-reach_saffron-"
        "skill-materialized"
    )
    assert _route_materialized_checkpoint_id(
        "red-strategic-scenario-v2-045-train"
    ) == "red-strategic-scenario-v2-045-train-route-materialized"


def test_cinnabar_fly_relocation_accepts_qualified_mainland_origins() -> None:
    raw = RawGameState(True, MapId.CINNABAR_POKECENTER, 3, 3, 4, 0)

    assert _can_fly_from_cinnabar_to_origin(
        raw,
        frozenset({MapId.CELADON_CITY, MapId.CELADON_POKECENTER}),
    )
    assert not _can_fly_from_cinnabar_to_origin(
        raw,
        frozenset({MapId.SAFFRON_CITY, MapId.SAFFRON_POKECENTER}),
    )
    assert _can_fly_to_cinnabar_skill_boundary(
        replace(raw, map_id=MapId.FUCHSIA_CITY, player_x=19, player_y=28),
        (MapId.CINNABAR_POKECENTER, (3, 3)),
    )
    assert not _can_fly_from_cinnabar_to_origin(
        replace(raw, map_id=MapId.CINNABAR_ISLAND),
        frozenset({MapId.CELADON_CITY, MapId.CELADON_POKECENTER}),
    )


def test_construction_executor_latches_semantics_after_every_action() -> None:
    calls: list[str] = []

    class Delegate:
        def execute(self, action: MacroAction) -> object:
            calls.append(f"execute:{action.value}")
            return action

    class Observer:
        def observe(self) -> object:
            calls.append("observe")
            return object()

    action = MacroAction(MacroActionKind.MOVE, "left")
    executor = _SemanticTrackingExecutor(  # type: ignore[arg-type]
        Delegate(),
        Observer(),
    )

    assert executor.execute(action) is action
    assert calls == ["execute:left", "observe"]


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
