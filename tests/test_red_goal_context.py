from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    open_goal_manager_context_capture,
)
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_goal_context import (
    build_red_goal_context_runtime,
    red_team_development_quantum_policy,
)
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_CONTEXT_PROFILE_SCHEMA,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalManagerConfig


class _Reader:
    def __init__(self) -> None:
        self.raw = RawGameState(
            game_started=True,
            map_id=MapId.VIRIDIAN_MART,
            player_x=2,
            player_y=4,
            party_count=1,
            battle_state=0,
            bag_item_ids=(int(ItemId.HYPER_POTION), int(ItemId.POKE_BALL)),
            bag_items=(
                (int(ItemId.HYPER_POTION), 1),
                (int(ItemId.POKE_BALL), 1),
            ),
            party_species_ids=(0x1C,),
            party_levels=(20,),
            party_hp=(50,),
            party_max_hp=(100,),
            party_status=(0,),
            party_moves=((57, 58, 55, 0),),
            party_pp=((15, 10, 5, 0),),
            player_money=5_000,
        )
        self.boxes = RedBoxCollectionState(
            tuple(RedCurrentBoxState(index, (), ()) for index in range(12)),
            0,
            False,
        )

    def read(self) -> RawGameState:
        return self.raw

    def read_pokedex_state(self) -> RedPokedexState:
        return RedPokedexState(frozenset({9}), frozenset({9}))

    def read_all_box_states(self) -> RedBoxCollectionState:
        return self.boxes

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0)


class _Emulator:
    frame_count = 0
    pressed_buttons = frozenset()

    def read_u8(self, _address: int) -> int:
        return 0

    def press(self, _button: str) -> None:
        pass

    def release(self, _button: str) -> None:
        pass

    def tick(self, frames: int) -> None:
        self.frame_count += frames


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )


def _capture(tmp_path: Path):  # type: ignore[no-untyped-def]
    state = b"authenticated context state"
    state_path = tmp_path / "context.state"
    envelope_path = tmp_path / "context.state.json"
    state_path.write_bytes(state)
    envelope_path.write_bytes(
        _canonical(
            {
                "schema": "pokemon-private-captured-progress-v1",
                "state_sha256": hashlib.sha256(state).hexdigest(),
                "checkpoint_id": "goal-context-fixture",
                "checkpoint_label": "Goal context fixture",
                "checkpoints_completed": 1,
                "checkpoints_total": 36,
                "verified_objective_ids": ["power_on"],
            }
        )
    )
    return open_goal_manager_context_capture(state_path, envelope_path)


def _profile(profile_id: str):  # type: ignore[no-untyped-def]
    return parse_red_goal_context_profile(
        _canonical(
            {
                "schema": RED_GOAL_CONTEXT_PROFILE_SCHEMA,
                "profile_id": profile_id,
                "manager_config": {
                    "required_party_size": 6,
                    "required_team_level": 60,
                    "desired_capture_items": 10,
                    "desired_recovery_items": 8,
                    "desired_storage_headroom": 8,
                },
                "providers": [
                    {
                        "kind": "restore_team",
                        "mechanic": "field_restore",
                        "parameters": {},
                    },
                    {
                        "kind": "resupply",
                        "mechanic": "mart_resupply",
                        "parameters": {
                            "map_id": int(MapId.VIRIDIAN_MART),
                            "player_x": 2,
                            "player_y": 4,
                            "interaction_direction": "up",
                            "purchases": [
                                {
                                    "absolute_index": 0,
                                    "item_id": int(ItemId.POKE_BALL),
                                    "quantity": 3,
                                    "unit_price": 200,
                                },
                                {
                                    "absolute_index": 1,
                                    "item_id": int(ItemId.POTION),
                                    "quantity": 2,
                                    "unit_price": 300,
                                },
                            ],
                        },
                    },
                    {
                        "kind": "recover_control",
                        "mechanic": "control_recovery",
                        "parameters": {},
                    },
                ],
            }
        )
    )


def test_context_factory_binds_exact_profile_only_beside_policy_menu(
    tmp_path: Path,
) -> None:
    reader = _Reader()
    profile = _profile("fixture-a")
    runtime = build_red_goal_context_runtime(
        profile=profile,
        capture=_capture(tmp_path),
        emulator=_Emulator(),
        reader=reader,  # type: ignore[arg-type]
    )

    binding_set = runtime.enumerator(CountingExecutor(_Emulator())).enumerate(
        runtime.adapter.observe()
    )

    available = tuple(
        item.kind
        for item in binding_set.opportunities
        if item.availability is GoalAvailability.AVAILABLE
    )
    assert available == (GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY)
    assert all(profile.profile_sha256 in item.binding_ref for item in binding_set.bindings)
    assert all(
        item.binding_ref not in json.dumps(item.opportunity.policy_dict(), sort_keys=True)
        for item in binding_set.bindings
    )


def test_profile_identity_changes_private_manifest_without_changing_kind_menu(
    tmp_path: Path,
) -> None:
    reader = _Reader()
    capture = _capture(tmp_path)
    first = build_red_goal_context_runtime(
        profile=_profile("fixture-a"),
        capture=capture,
        emulator=_Emulator(),
        reader=reader,  # type: ignore[arg-type]
    )
    second = build_red_goal_context_runtime(
        profile=_profile("fixture-b"),
        capture=capture,
        emulator=_Emulator(),
        reader=reader,  # type: ignore[arg-type]
    )

    first_set = first.enumerator(CountingExecutor(_Emulator())).enumerate(
        first.adapter.observe()
    )
    second_set = second.enumerator(CountingExecutor(_Emulator())).enumerate(
        second.adapter.observe()
    )

    assert tuple(item.policy_dict() for item in first_set.opportunities) == tuple(
        item.policy_dict() for item in second_set.opportunities
    )
    assert tuple(item.binding_ref for item in first_set.bindings) != tuple(
        item.binding_ref for item in second_set.bindings
    )


def test_team_development_is_one_level_quantum_not_a_full_duplicate_grind() -> None:
    party = PartyObservation(
        tuple(
            PartyMemberObservation(
                slot=index + 1,
                species_id=species,
                level=level,
                hp=100,
                max_hp=100,
            )
            for index, (species, level) in enumerate(
                zip((28, 64, 118, 132, 104, 43), (60, 55, 57, 58, 59, 60), strict=True)
            )
        )
    )

    development = red_team_development_quantum_policy(
        party,
        RedGoalManagerConfig(),
        kind=GoalKind.DEVELOP_TEAM,
    )
    evolution = red_team_development_quantum_policy(
        party,
        RedGoalManagerConfig(),
        kind=GoalKind.EVOLVE_SPECIES,
    )

    assert development.minimum_level == 56
    assert development.required_size == 6
    assert evolution.minimum_level == 2
    assert evolution.required_size == party.size
