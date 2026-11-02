"""Materialize one TRAIN or explicitly assisted held-out battle in a private copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

from pokemon_red_completion.battle_practice_factory import (
    AssistedDevelopmentPracticeSpec,
    BattlePracticeSpec,
)
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
    parse_battle_scenario_capture_manifest,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_practice_factory import (
    WritableRedMemory,
    materialize_red_assisted_development_practice,
    materialize_red_train_practice,
)
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.teacher-battle-practice-plan.v1"
TRAINER_SCHEMA = "pokemon.red.teacher-battle-practice-plan.v2"
DEVELOPMENT_SCHEMA = "pokemon.red.assisted-development-battle-practice-plan.v1"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def _bound_file(value: object, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"{label} identity differs")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{label} hash differs")
    return payload


def _authenticate(
    plan: object, plan_bytes: bytes
) -> tuple[dict[str, object], BattlePracticeSpec, bytes, bytes]:
    if not isinstance(plan, dict) or plan.get("schema") not in {
        SCHEMA, TRAINER_SCHEMA, DEVELOPMENT_SCHEMA
    }:
        raise ValueError("teacher battle practice plan differs")
    if plan.get("observation_schema") not in {None, OBSERVATION_SCHEMA_V2} or (
        plan.get("observation_schema") is not None
        and plan.get("schema") not in {TRAINER_SCHEMA, DEVELOPMENT_SCHEMA}
    ):
        raise ValueError("teacher battle observation version differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit teacher factory before cartridge materialization")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("teacher factory source commit differs")
    rom = _bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("teacher factory Red ROM differs")
    source = _bound_file(plan.get("source_state"), "source state")
    spec = (
        AssistedDevelopmentPracticeSpec.from_dict(plan.get("practice"))
        if plan["schema"] == DEVELOPMENT_SCHEMA
        else BattlePracticeSpec.from_dict(plan.get("practice"))
    )
    if plan["schema"] == DEVELOPMENT_SCHEMA and (
        plan.get("observation_schema") != OBSERVATION_SCHEMA_V2
        or plan.get("fit_allowed") is not False
        or plan.get("natural_battle_qualification") is not False
    ):
        raise ValueError("assisted DEVELOPMENT needs rich observations and explicit exclusions")
    if plan["schema"] == SCHEMA:
        query = json.loads(_bound_file(plan.get("source_query"), "source query"))
        episode = json.loads(_bound_file(plan.get("source_episode"), "source episode"))
        if (
            spec.battle_kind != "wild"
            or not isinstance(query, dict)
            or query.get("state_sha256") != hashlib.sha256(source).hexdigest()
            or query.get("observation_sha256") != plan.get("source_observation_sha256")
            or episode.get("schema") != "pokemon.red.model-battle-train-episode-outcome.v1"
            or episode.get("root_lineage_id") != spec.root_lineage_id
            or episode.get("completed_decisions", 0) < 1
            or spec.source_state_sha256 != hashlib.sha256(source).hexdigest()
            or plan.get("source_encounter_index") != 0
        ):
            raise ValueError("teacher factory source is not the retained train decision")
    else:
        manifest = parse_battle_scenario_capture_manifest(
            _bound_file(plan.get("source_capture_manifest"), "source capture manifest")
        )
        if (
            spec.battle_kind != "trainer"
            or manifest.partition is not spec.partition
            or manifest.expected_battle_state != 2
            or manifest.root_lineage_id != spec.root_lineage_id
            or manifest.state_sha256 != hashlib.sha256(source).hexdigest()
            or spec.source_state_sha256 != manifest.state_sha256
        ):
            raise ValueError("teacher factory source is not an authenticated train trainer capture")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists() or not plan_bytes:
        raise ValueError("teacher factory output must be new")
    return plan, spec, source, rom


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan_bytes = plan_path.read_bytes()
    plan, spec, source, rom = _authenticate(json.loads(plan_bytes), plan_bytes)
    rom_binding = plan["rom"]
    assert isinstance(rom_binding, dict)
    rom_path = rom_binding["path"]
    assert isinstance(rom_path, str)
    with PyBoyAdapter(Path(rom_path), watch=False, speed=None) as emulator:
        emulator.load_state_bytes(source)
        before_frame = emulator.frame_count
        reader = PokemonRedStateReader(emulator)
        if plan["schema"] in {TRAINER_SCHEMA, DEVELOPMENT_SCHEMA}:
            source_manifest = parse_battle_scenario_capture_manifest(
                _bound_file(plan.get("source_capture_manifest"), "source capture manifest")
            )
            source_cartridge = RedPracticeCartridge(rom)
            source_prepared = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(
                    reader,
                    include_battle_stats=(
                        source_manifest.observation_schema == OBSERVATION_SCHEMA_V2
                    ),
                    public_species_base_stats=(
                        source_cartridge.public_base_stats
                        if source_manifest.observation_schema == OBSERVATION_SCHEMA_V2
                        else None
                    ),
                ),
                reader.read(),
                allow_no_attack=(
                    source_manifest.observation_schema == OBSERVATION_SCHEMA_V2
                ),
            )
            if source_prepared.initial_observation_sha256 != (
                source_manifest.initial_observation_sha256
            ):
                raise ValueError("source trainer semantic observation differs from capture")
        backend = emulator._require_backend()  # isolated teacher-only write surface
        cartridge = RedPracticeCartridge(rom)
        if isinstance(spec, AssistedDevelopmentPracticeSpec):
            receipt = materialize_red_assisted_development_practice(
                reader, cast(WritableRedMemory, backend.memory), spec, cartridge=cartridge
            )
        else:
            receipt = materialize_red_train_practice(
                reader, cast(WritableRedMemory, backend.memory), spec, cartridge=cartridge
            )
        if emulator.frame_count != before_frame:
            raise ValueError("teacher materialization advanced emulator frames")
        rich_observation_sha256 = None
        if plan.get("observation_schema") == OBSERVATION_SCHEMA_V2:
            rich_observation_sha256 = prepare_red_battle_scenario(
                PokemonRedObservationEncoder.from_state_reader(
                    reader,
                    include_battle_stats=True,
                    public_species_base_stats=cartridge.public_base_stats,
                ),
                reader.read(),
                allow_no_attack=True,
            ).initial_observation_sha256
        if check_only:
            return {
                "status": "action_free_materialization_preflight_passed",
                "configuration_sha256": spec.configuration_sha256,
                "legal_move_count": receipt.legal_move_count,
                "controller_actions": 0,
                "emulator_frames": 0,
                "persistent_artifacts": 0,
            }
        observation_sha256 = rich_observation_sha256 or receipt.observation_sha256
        generated = emulator.save_state_bytes()
        if generated == source:
            raise ValueError("teacher materialization did not change the copied state")
        generated_map = reader.read().map_id
        if type(generated_map) is not int:  # noqa: E721
            raise ValueError("assisted battle map is unavailable")
        capture_id = f"assisted-{spec.partition.value}-{spec.configuration_sha256[:16]}"
        source_commit = plan["source_commit"]
        assert isinstance(source_commit, str)
        manifest = build_battle_scenario_capture_payload(
            capture_id=capture_id,
            root_lineage_id=spec.root_lineage_id,
            partition=spec.partition,
            state_bytes=generated,
            initial_observation_sha256=observation_sha256,
            source_commit=source_commit,
            expected_map=generated_map,
            expected_battle_state=1 if spec.battle_kind == "wild" else 2,
            source_state_sha256=spec.source_state_sha256,
            observation_schema=plan.get("observation_schema"),
        )
    output_path = plan["output"]
    assert isinstance(output_path, str)
    output = Path(output_path)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(
        output / "execution-started.json",
        {
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "configuration_sha256": spec.configuration_sha256,
            "source_state_sha256": spec.source_state_sha256,
            "root_lineage_id": spec.root_lineage_id,
            "teacher_only": True,
        },
    )
    _write(output / "assisted.state", generated)
    _write(output / "assisted.state.json", manifest)
    capture = open_battle_scenario_capture(
        output / "assisted.state", output / "assisted.state.json"
    )
    outcome: dict[str, object] = {
        **receipt.public_dict(),
        "capture_id": capture.manifest.capture_id,
        "capture_manifest_sha256": capture.manifest_sha256,
        "observation_schema": capture.manifest.observation_schema,
        "assisted_state_sha256": hashlib.sha256(generated).hexdigest(),
        "controller_actions": 0,
        "emulator_frames": 0,
        "model_queries": 0,
        "candidate_outcomes": 0,
        "model_updates": 0,
        "authority_promotions": 0,
    }
    _record(output / "outcome.json", outcome)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
