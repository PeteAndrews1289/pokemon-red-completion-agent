#!/usr/bin/env python3
"""Make explicitly teacher-assisted OHKO contrasts from authenticated battle states.

This edits only private *training/development* emulator states. It is not a
player action and its descendants must never count as legitimate play.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.observation import (  # noqa: E402
    PARTY_MOVES_OFFSET,
    PARTY_PP_OFFSET,
    PARTY_STRUCT_STRIDE,
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
)
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario  # noqa: E402
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-state", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("output directory already exists; this experiment is one-use")
    source_paths = tuple(args.source_state)
    if len(source_paths) != len(set(source_paths)):
        parser.error("source state repeated")
    sources = tuple(
        open_battle_scenario_capture(path, Path(f"{path}.json"))
        for path in source_paths
    )
    if len({source.manifest.root_lineage_id for source in sources}) != len(sources):
        parser.error("source roots must be distinct")
    if {source.manifest.partition for source in sources} != {
        ScenarioPartition.TRAIN,
        ScenarioPartition.DEVELOPMENT,
    }:
        parser.error("both train and development partitions are required")
    rom = resolve_rom_path(args.rom)
    commit = __import__("subprocess").check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    derived: list[tuple[str, bytes, bytes, dict[str, object]]] = []
    for ordinal, source in enumerate(sources, 1):
        with PyBoyAdapter(rom) as emulator:
            emulator.load_state_bytes(source.state_bytes)
            reader = PokemonRedStateReader(emulator)
            before = reader.read()
            if reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN:
                raise RuntimeError("source is not at the main battle menu")
            if before.active_party_index is None or before.battler_moves is None:
                raise RuntimeError("source active battler is unavailable")
            if tuple(emulator.read_u8(0xD01C + i) for i in range(4)) != before.battler_moves:
                raise RuntimeError("battle and party move arrays differ")
            if tuple(emulator.read_u8(0xD02D + i) for i in range(4)) != before.battler_pp:
                raise RuntimeError("battle and party PP arrays differ")
            party_base = (
                int(RamAddress.PARTY_MON_1)
                + before.active_party_index * PARTY_STRUCT_STRIDE
            )
            backend = emulator._require_backend()  # teacher-only state intervention
            backend.memory[0xD01C] = 12  # Guillotine, deliberately risky
            backend.memory[0xD02D] = 5
            backend.memory[party_base + PARTY_MOVES_OFFSET] = 12
            backend.memory[party_base + PARTY_PP_OFFSET] = 5
            after = reader.read()
            if (
                after.battler_moves is None
                or after.battler_moves[0] != 12
                or after.battler_pp is None
                or after.battler_pp[0] != 5
                or reader.read_battle_menu_state(after).phase is not BattleMenuPhase.MAIN
            ):
                raise RuntimeError("assisted state did not retain the policy boundary")
            prepared = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(reader), after
            )
            if (
                not prepared.supported_candidate_mask[0]
                or sum(prepared.supported_candidate_mask) < 2
            ):
                raise RuntimeError("assisted state lacks a supported move contrast")
            state = emulator.save_state_bytes()
            capture_id = f"ohko-assisted-{ordinal:02d}-{source.manifest.capture_id[-12:]}"
            manifest = build_battle_scenario_capture_payload(
                capture_id=capture_id,
                root_lineage_id=source.manifest.root_lineage_id,
                partition=source.manifest.partition,
                state_bytes=state,
                initial_observation_sha256=prepared.initial_observation_sha256,
                source_commit=commit,
                expected_map=after.map_id,
                expected_battle_state=after.battle_state,
                source_state_sha256=source.manifest.state_sha256,
            )
            derived.append((capture_id, state, manifest, {
                "capture_id": capture_id,
                "source_capture_id": source.manifest.capture_id,
                "source_manifest_sha256": source.manifest_sha256,
                "root_lineage_id": source.manifest.root_lineage_id,
                "partition": source.manifest.partition.value,
                "original_slot_1_move": before.battler_moves[0],
                "assisted_slot_1_move": 12,
                "assistance": "trainer_only_emulator_memory_edit_before_any_action",
            }))
    args.output_dir.mkdir(parents=True)
    for capture_id, state, manifest, record in derived:
        directory = args.output_dir / str(record["partition"])
        directory.mkdir(exist_ok=True)
        state_path = directory / f"{capture_id}.state"
        manifest_path = directory / f"{capture_id}.state.json"
        for path, payload in ((state_path, state), (manifest_path, manifest)):
            with path.open("xb") as handle:
                handle.write(payload)
            path.chmod(0o600)
        open_battle_scenario_capture(state_path, manifest_path)
        print(json.dumps(record, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
