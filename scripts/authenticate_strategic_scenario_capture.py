#!/usr/bin/env python3
"""Authenticate one existing state as an exact non-test scenario capture.

This is not a data-collection command. It executes no game action and opens no
scenario episode. Fresh live observation must already equal the target frontier
and origin before a new private state/envelope pair is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressError,
    load_captured_progress,
    write_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
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
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    StrategicNavigationProtocolError,
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (  # noqa: E402
    require_scenario_origin,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRuntimeError,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-scenario-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        default=None,
        help="defaults to <state>.json",
    )
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _require_private_new_output(destination: Path, rom_path: Path) -> Path:
    resolved = destination.resolve()
    envelope = Path(f"{resolved}.json")
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise StrategicScenarioRuntimeError(
            "authenticated capture must remain outside the repository"
        )
    if resolved.parent == rom_path.resolve().parent:
        raise StrategicScenarioRuntimeError(
            "authenticated capture must not be written beside the ROM"
        )
    if not resolved.parent.is_dir():
        raise StrategicScenarioRuntimeError(
            "authenticated capture parent directory does not exist"
        )
    if resolved.exists() or envelope.exists():
        raise StrategicScenarioRuntimeError(
            "authenticated capture output already exists"
        )
    return resolved


def _checkpoint_id(target_scenario_id: str) -> str:
    return f"{target_scenario_id}-authenticated"


def _run(args: argparse.Namespace) -> dict[str, object]:
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

    scenario = load_strategic_navigation_scenario_registry(PROJECT_ROOT).scenario(
        args.target_scenario_id
    )
    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    out_state = _require_private_new_output(args.out_state, rom_path)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = load_captured_progress(envelope_path, state_path=state_path)
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state(state_path)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if (
            not raw.game_started
            or raw.map_id is None
            or raw.player_y is None
            or raw.player_x is None
            or raw.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "source capture is not a stable ready overworld boundary"
            )
        require_scenario_origin(scenario, raw.map_id)
        observed = CapturedPokemonRedObserver(
            reader,
            COMPLETION_QUEST,
            capture,
        ).observe()
        completed = COMPLETION_QUEST.completed_ids(observed)
        if completed != frozenset(scenario.completed_objective_ids):
            raise StrategicScenarioRuntimeError(
                "live frontier differs from the target scenario"
            )

        emulator.save_state(out_state)
        output_envelope = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=_checkpoint_id(scenario.scenario_id),
            checkpoint_label=f"Authenticated {scenario.scenario_id}",
            checkpoints_completed=capture.checkpoints_completed,
            checkpoints_total=capture.checkpoints_total,
            verified_objective_ids=scenario.completed_objective_ids,
        )

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise StrategicScenarioRuntimeError("source capture changed during authentication")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise StrategicScenarioRuntimeError(
            "capture authentication created a ROM-adjacent artifact"
        )
    return {
        "schema": "strategic-navigation-scenario-capture-authentication-v1",
        "status": "complete",
        "counted": False,
        "episode_created": False,
        "target_scenario_id": scenario.scenario_id,
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
        ResumedStateError,
        RomValidationError,
        StrategicNavigationProtocolError,
        StrategicScenarioProtocolError,
        StrategicScenarioRuntimeError,
        OSError,
    ):
        parser.error(
            "Strategic scenario capture authentication failed closed; private paths "
            "were withheld."
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
