#!/usr/bin/env python3
"""Materialize one construction-only resource without opening a policy context.

Supported lessons collect Gold Teeth without HM03 or acquire and teach HM02/Fly.
Each preserves the source's verified completion objectives, writes a new
authenticated private capture, and never creates an episode or label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressError,
    load_captured_progress,
    write_captured_progress,
)
from pokemon_red_completion.celadon import _bag  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.fly_resource import (  # noqa: E402
    FlyResourceError,
    FlyResourceReport,
    run_fly_resource_chapter,
)
from pokemon_red_completion.observation import (  # noqa: E402
    ItemId,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_player_observer import (  # noqa: E402
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.rom import (  # noqa: E402
    RomValidationError,
    resolve_rom_path,
    verify_rom,
)
from pokemon_red_completion.route import COMPLETION_QUEST  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.safari import (  # noqa: E402
    GoldTeethChapterReport,
    SafariChapterError,
    run_gold_teeth_chapter,
)
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    StrategicNavigationProtocolError,
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRuntimeError,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)

SUPPORTED_RESOURCE_IDS = ("fly", "gold_teeth")


class _SemanticTrackingExecutor:
    def __init__(
        self,
        delegate: FrameSafeExecutor,
        observer: CapturedPokemonRedObserver,
    ) -> None:
        self._delegate = delegate
        self._observer = observer

    def execute(self, action: MacroAction) -> object:
        result = self._delegate.execute(action)
        self._observer.observe()
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-scenario-id", required=True)
    parser.add_argument("--acquire-resource-id", choices=SUPPORTED_RESOURCE_IDS, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None, help="defaults to <state>.json")
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _require_private_new_output(destination: Path, rom_path: Path) -> Path:
    resolved = destination.resolve()
    envelope = Path(f"{resolved}.json")
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise StrategicScenarioRuntimeError("resource capture must remain outside the repository")
    if resolved.parent == rom_path.resolve().parent:
        raise StrategicScenarioRuntimeError("resource capture must not be written beside the ROM")
    if not resolved.parent.is_dir():
        raise StrategicScenarioRuntimeError("resource capture parent directory does not exist")
    if resolved.exists() or envelope.exists():
        raise StrategicScenarioRuntimeError("resource capture output already exists")
    return resolved


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise StrategicScenarioRuntimeError("--speed requires --watch")

    source_identity = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source_identity)
    require_published_source(PROJECT_ROOT, source_identity)
    execution = load_committed_strategic_navigation_registry(PROJECT_ROOT).execution
    if (
        source_identity.git_commit != execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT) != execution.source_bundle_sha256
    ):
        raise StrategicScenarioRuntimeError(
            "the executable source differs from the committed strategic execution"
        )

    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    target = registry.scenario(args.target_scenario_id)
    if target.partition == "test":
        raise StrategicScenarioRuntimeError("resource construction cannot open a test scenario")

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    out_state = _require_private_new_output(args.out_state, rom_path)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = load_captured_progress(envelope_path, state_path=state_path)
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    with PyBoyAdapter(rom_path, watch=args.watch, speed=args.speed) as emulator:
        emulator.load_state(state_path)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        stable_boundary = (
            raw.game_started
            and raw.battle_state == 0
            and reader.read_input_readiness().ready
        )
        if args.acquire_resource_id == "gold_teeth":
            stable_boundary = stable_boundary and (
                raw.map_id == MapId.FUCHSIA_POKECENTER
                and (raw.player_x, raw.player_y) == (3, 3)
            )
        else:
            stable_boundary = stable_boundary and (
                (
                    raw.map_id == MapId.CELADON_CITY
                    and (raw.player_x, raw.player_y) == (49, 11)
                )
                or (
                    raw.map_id == MapId.CELADON_POKECENTER
                    and (raw.player_x, raw.player_y) == (3, 3)
                )
            )
        if not stable_boundary:
            raise StrategicScenarioRuntimeError(
                "resource source is not the required stable lesson boundary"
            )
        observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, capture)
        before = observer.observe()
        completed_before = COMPLETION_QUEST.completed_ids(before)
        target_completed = frozenset(target.completed_objective_ids)
        if not completed_before < target_completed:
            raise StrategicScenarioRuntimeError(
                "resource source must be a strict subset of the target frontier"
            )
        if args.acquire_resource_id == "gold_teeth" and (
            "item:gold_teeth" in before.facts or "move:surf_available" in before.facts
        ):
            raise StrategicScenarioRuntimeError(
                "Gold Teeth resource source is not pristine or already contains Surf"
            )
        if args.acquire_resource_id == "fly" and ItemId.HM02_FLY in _bag(emulator):
            raise StrategicScenarioRuntimeError("Fly resource source already contains HM02")

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        tracked = _SemanticTrackingExecutor(controller, observer)
        report: GoldTeethChapterReport | FlyResourceReport
        if args.acquire_resource_id == "gold_teeth":
            report = run_gold_teeth_chapter(emulator, reader, tracked)
            encounters_fled = report.encounters_fled
        else:
            report = run_fly_resource_chapter(emulator, reader, tracked)
            encounters_fled = report.wild_battles
        after = observer.observe()
        objectives_changed = COMPLETION_QUEST.completed_ids(after) != completed_before
        gold_teeth_failed = args.acquire_resource_id == "gold_teeth" and (
            "item:gold_teeth" not in after.facts
            or "move:surf_available" in after.facts
            or ItemId.HM03_SURF in _bag(emulator)
        )
        fly_failed = args.acquire_resource_id == "fly" and (
            ItemId.HM02_FLY not in _bag(emulator) or not report.passed
        )
        if objectives_changed or gold_teeth_failed or fly_failed:
            raise StrategicScenarioRuntimeError(
                "resource lesson changed objectives or failed its acquisition contract"
            )
        final = reader.read()
        expected_map = (
            MapId.FUCHSIA_POKECENTER
            if args.acquire_resource_id == "gold_teeth"
            else MapId.CELADON_POKECENTER
        )
        if (
            final.map_id != expected_map
            or (final.player_x, final.player_y) != (3, 3)
            or final.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "resource lesson did not end at the stable Fuchsia boundary"
            )

        emulator.save_state(out_state)
        output_envelope = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=(
                f"{target.scenario_id}-toward-{args.acquire_resource_id}-resource-materialized"
            ),
            checkpoint_label=(
                f"Materialized {args.acquire_resource_id} toward {target.scenario_id} "
                "without an objective label"
            ),
            checkpoints_completed=capture.checkpoints_completed,
            checkpoints_total=capture.checkpoints_total,
            verified_objective_ids=tuple(sorted(completed_before)),
        )

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise StrategicScenarioRuntimeError(
            "source capture changed during resource materialization"
        )
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise StrategicScenarioRuntimeError(
            "resource materialization created a ROM-adjacent artifact"
        )
    return {
        "schema": "strategic-navigation-resource-skill-materialization-v1",
        "status": "complete",
        "resource_id": args.acquire_resource_id,
        "target_scenario_id": target.scenario_id,
        "target_scenario_exact": False,
        "counted": False,
        "episode_created": False,
        "source_registry_assignment_opened": False,
        "verified_objectives_added": [],
        "surf_objective_added": False,
        "skill": {
            "actions_executed": report.actions_executed,
            "frames_executed": report.frames_executed,
            "encounters_fled": encounters_fled,
        },
        "capture": {
            "checkpoint_id": output_envelope.checkpoint_id,
            "state_sha256": output_envelope.state_sha256,
            "verified_objective_count": len(output_envelope.verified_objective_ids),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        payload = _run(args)
    except (
        CapturedProgressError,
        CollectionProtocolError,
        EmulatorError,
        EvaluationIdentityError,
        FlyResourceError,
        OSError,
        ResumedStateError,
        RomValidationError,
        SafariChapterError,
        StrategicNavigationProtocolError,
        StrategicScenarioProtocolError,
        StrategicScenarioRuntimeError,
        ValueError,
    ):
        parser.error(
            "Strategic resource materialization failed closed; private paths were withheld."
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
