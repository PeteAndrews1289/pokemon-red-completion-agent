"""Action-free qualification of one supplied Red capture, never a root search.

This is an engineering diagnostic, not training, evaluation, a claim, or a fit.
Input, tick and release primitives are refused by the existing read-only port.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor, ReadOnlyController
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_context_catalog import open_goal_manager_context_capture
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID, red_species_ref
from pokemon_red_completion.red_full_pokedex_goal_proposal import (
    RedFullPokedexGoalProposalError,
    build_red_full_pokedex_player_observer,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    build_native_boxed_evolution_profile_payload,
    load_red_goal_context_profile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def inspect_departure(
    *, rom_path: Path, state_path: Path, envelope_path: Path, profile_path: Path,
    expected_state_sha256: str, expected_profile_sha256: str,
    evolution: tuple[int, int, int] | None = None,
) -> dict[str, object]:
    """Inspect exactly one pinned input. A failure cannot select a replacement."""
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    profile = load_red_goal_context_profile(profile_path)
    if (capture.state_sha256 != expected_state_sha256
            or profile.profile_sha256 != expected_profile_sha256):
        raise ValueError("departure input pins differ")
    if evolution is not None:
        source, target, level = evolution
        profile = parse_red_goal_context_profile(build_native_boxed_evolution_profile_payload(
            profile, source_species=source, target_species=target, evolution_level=level,
        ))
    rom = rom_path.read_bytes()
    world = StrategicScenarioRouteWorld.from_rom(rom)
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        before, frame = emulator.save_state_bytes(), emulator.frame_count
        controller = ReadOnlyController(emulator)
        runtime = build_red_goal_context_runtime(
            profile=profile, capture=capture, emulator=controller,
            reader=PokemonRedStateReader(controller),
        )
        observed = runtime.adapter.observe()
        collection = observed.collection_observation
        # Ephemeral accounting only. This does not create a training root, durable
        # registration session, upstream-lineage claim, or private artifact.
        row = observation_from_collection(
            collection, seen_species=collection.owned_species,
            national_ids={red_species_ref(n): n for n in range(1, 152)},
            run_id="action-free-inspection", game_id=RED_COLLECTION_GAME_ID,
            adapter_id="red-full-local-inspection-v1",
            cartridge_sha256=hashlib.sha256(rom).hexdigest(),
            snapshot_sha256=capture.state_sha256, sequence=0,
        )
        protected: dict[str, int] = {}
        for member in collection.specimens:
            if member.location.value == "party":
                protected[member.species_ref] = protected.get(member.species_ref, 0) + 1
        policy = RedRegistrationPolicy(
            RegistrationSnapshot((row,)), row.run_id, capture.state_sha256, collection,
            protected, completion_scope="local_red",
        )
        actions = CountingExecutor(FrameSafeExecutor(controller))
        observer = build_red_full_pokedex_player_observer(
            replace(runtime, registration_policy=policy), actions, world,
        )
        try:
            result = observer()
            kinds = {b.kind for b in result.binding_set.bindings}
            passed = {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES} <= kinds
            reason, family_diagnostics = None, []
        except RedFullPokedexGoalProposalError as error:
            passed, reason = False, str(error)
            family_diagnostics = error.public_family_diagnostics()
        finally:
            if (before != emulator.save_state_bytes() or frame != emulator.frame_count
                    or emulator.pressed_buttons or actions.actions_executed):
                raise ValueError("departure inspection changed the game")
        return {
            "schema": "pokemon.red.full-local-departure-inspection.v2",
            "passed": passed, "failure": reason,
            "family_diagnostics": family_diagnostics,
            "acquisition_family_count": 2 if passed else None,
            "local_registration_count": len(collection.owned_species),
            "local_target_count": 151,
            "controller_actions": 0, "emulator_frames": 0,
            "state_bytes_unchanged": True,
            "model_queries": 0, "outcomes": 0, "fits": 0, "claims": 0,
            "classification": "action_free_engineering_diagnostic",
            "upstream_independence_verified": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "state", "envelope", "profile"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--expected-state-sha256", required=True)
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--evolution", nargs=3, type=int, metavar=("SOURCE", "TARGET", "LEVEL"))
    args = parser.parse_args()
    result = inspect_departure(
        rom_path=args.rom, state_path=args.state, envelope_path=args.envelope,
        profile_path=args.profile, expected_state_sha256=args.expected_state_sha256,
        expected_profile_sha256=args.expected_profile_sha256,
        evolution=tuple(args.evolution) if args.evolution else None,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
