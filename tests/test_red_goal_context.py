from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.blaine import DIGLETT_SPECIES_ID
from pokemon_red_completion.executor import CountingExecutor, WindowedFrameBudgetController
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
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
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.red_acquisition import RedAreaExecutionPolicy
from pokemon_red_completion.red_goal_context import (
    _targeted_evolution_index,
    _wild_provider,
    build_red_goal_context_runtime,
    red_team_development_quantum_policy,
)
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_CONTEXT_PROFILE_SCHEMA,
    RedGoalMechanic,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalManagerConfig
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID, DUGTRIO_SPECIES_ID


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
    pressed_buttons: frozenset[str] = frozenset()

    def read_u8(self, _address: int) -> int:
        return 0

    def press(self, _button: str) -> None:
        pass

    def release(self, _button: str) -> None:
        pass

    def tick(self, frames: int) -> None:
        self.frame_count += frames


class _ActionDelegate:
    def execute(self, action: MacroAction) -> MacroAction:
        return action


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"


def _capture(
    tmp_path: Path,
    *,
    verified_objective_ids: tuple[str, ...] = ("power_on",),
):  # type: ignore[no-untyped-def]
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
                "checkpoints_completed": len(verified_objective_ids),
                "checkpoints_total": 36,
                "verified_objective_ids": list(verified_objective_ids),
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


def _team_profile(profile_id: str):  # type: ignore[no-untyped-def]
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
                        "kind": "advance_story",
                        "mechanic": "midgame_story",
                        "parameters": {},
                    },
                    {
                        "kind": "develop_team",
                        "mechanic": "balanced_team",
                        "parameters": {},
                    },
                    {
                        "kind": "evolve_species",
                        "mechanic": "diglett_evolution",
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

    binding_set = runtime.enumerator(CountingExecutor(_ActionDelegate())).enumerate(
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

    first_set = first.enumerator(CountingExecutor(_ActionDelegate())).enumerate(
        first.adapter.observe()
    )
    second_set = second.enumerator(CountingExecutor(_ActionDelegate())).enumerate(
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


def test_wild_goal_context_binds_one_capture_quantum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_context.LiveWildCorridorSurveyExecutor",
        lambda *_args, **_kwargs: SimpleNamespace(
            finish_at_starting_endpoint=lambda: None
        ),
    )

    def provider(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_context.RedAreaSurveyGoalProvider",
        provider,
    )
    parameters = {
        "source_id": "wild:Route1:grass",
        "label": "Route 1 capture lane",
        "map_id": int(MapId.ROUTE_1),
        "player_x": 10,
        "player_y": 20,
        "forward_directions": ("up",),
        "starting_endpoint": "south",
        "maximum_legs": 8,
        "maximum_seek_steps": 64,
        "maximum_encounters": 16,
    }

    _wild_provider(
        SimpleNamespace(emulator=object(), reader=object(), adapter=object()),
        SimpleNamespace(
            parameters=parameters,
            mechanic=RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        ),
        CountingExecutor(_ActionDelegate()),
    )

    policy = captured["policy"]
    assert isinstance(policy, RedAreaExecutionPolicy)
    assert policy.capture_quota == 1
    assert policy.capture_in_requirement_order is True
    assert callable(captured["normalize_after_capture"])


def test_wild_goal_context_binds_hard_limited_source_local_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalizations = 0

    def finish_at_starting_endpoint() -> None:
        nonlocal normalizations
        normalizations += 1

    area = SimpleNamespace(
        seek_encounter=lambda: None,
        finish_at_starting_endpoint=finish_at_starting_endpoint,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_context.LiveWildCorridorSurveyExecutor",
        lambda *_args, **_kwargs: area,
    )
    captured: dict[str, object] = {}

    def provider(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_context.RedEncounterSourceDevelopmentGoalProvider",
        provider,
    )

    emulator = WindowedFrameBudgetController(
        _Emulator(),
        maximum_frames_per_window=1_000,
        maximum_total_frames=2_000,
    )
    hard_actions = HardCompositionActionLimiter(
        _ActionDelegate(),
        maximum_actions_per_decision=100,
        maximum_episode_actions=200,
    )
    actions = CountingExecutor(hard_actions)
    party = PartyObservation(
        (
            PartyMemberObservation(
                1,
                BLASTOISE_SPECIES_ID,
                60,
                120,
                120,
                moves=(MoveObservation(57, 15),),
            ),
            PartyMemberObservation(
                2,
                64,
                35,
                80,
                80,
                moves=(MoveObservation(10, 20),),
            ),
        )
    )
    runtime = SimpleNamespace(
        emulator=emulator,
        reader=object(),
        adapter=SimpleNamespace(observe=lambda: SimpleNamespace(party=party)),
        profile=SimpleNamespace(manager_config=RedGoalManagerConfig()),
    )
    observed: dict[str, object] = {}

    def run_local(
        received_actions: CountingExecutor,
        _reader: object,
        received_emulator: WindowedFrameBudgetController,
        **kwargs: object,
    ) -> tuple[None, int, int]:
        observed.update(kwargs)
        received_actions.execute(MacroAction(MacroActionKind.WAIT))
        received_emulator.tick(1)
        return None, 4, 0

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_context.run_red_team_balancing",
        run_local,
    )
    parameters = {
        "source_id": "wild:PokemonMansion1F:grass",
        "label": "Mansion source-local development",
        "map_id": int(MapId.POKEMON_MANSION_1F),
        "player_x": 5,
        "player_y": 21,
        "forward_directions": ("up",),
        "starting_endpoint": "south",
        "maximum_legs": 8,
        "maximum_seek_steps": 64,
        "maximum_encounters": 16,
        "completed_battles": 4,
    }

    _wild_provider(
        runtime,
        SimpleNamespace(
            parameters=parameters,
            mechanic=RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
        ),
        actions,
    )

    assert captured["source_ref"] == "wild:PokemonMansion1F:grass"
    executor = captured["executor"]
    assert callable(executor)
    report = executor()
    assert report.actions_executed == 1
    assert report.frames_executed == 1
    assert report.evidence == {
        "bounded": True,
        "source_local": True,
        "completed_battles": 4,
        "healing_trips": 0,
        "travel_transitions": 0,
    }
    assert observed["policy"].max_healing_trips == 0  # type: ignore[union-attr]
    assert observed["policy"].max_steps == 64  # type: ignore[union-attr]
    assert observed["fixed_dose"].completed_battles == 4  # type: ignore[union-attr]
    assert normalizations == 1


def test_targeted_evolution_requires_one_exact_in_place_species_change() -> None:
    before = (28, DIGLETT_SPECIES_ID, 64)
    after = (28, DUGTRIO_SPECIES_ID, 64)

    assert (
        _targeted_evolution_index(
            before,
            after,
            source_species_id=DIGLETT_SPECIES_ID,
            target_species_id=DUGTRIO_SPECIES_ID,
        )
        == 1
    )
    assert (
        _targeted_evolution_index(
            before,
            (DUGTRIO_SPECIES_ID, 28, 64),
            source_species_id=DIGLETT_SPECIES_ID,
            target_species_id=DUGTRIO_SPECIES_ID,
        )
        is None
    )
    assert (
        _targeted_evolution_index(
            before,
            (28, DUGTRIO_SPECIES_ID, 65),
            source_species_id=DIGLETT_SPECIES_ID,
            target_species_id=DUGTRIO_SPECIES_ID,
        )
        is None
    )
    assert (
        _targeted_evolution_index(
            before,
            before,
            source_species_id=DIGLETT_SPECIES_ID,
            target_species_id=DUGTRIO_SPECIES_ID,
        )
        is None
    )


def test_targeted_evolution_verifies_living_transform_without_catalog_counter_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _Reader()
    reader.raw = replace(
        reader.raw,
        map_id=MapId.CINNABAR_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=2,
        party_species_ids=(0x1C, DIGLETT_SPECIES_ID),
        party_levels=(48, 25),
        party_hp=(150, 50),
        party_max_hp=(150, 50),
        party_status=(0, 0),
        party_moves=((57, 58, 55, 0), (1, 0, 0, 0)),
        party_pp=((15, 10, 5, 0), (10, 0, 0, 0)),
    )
    emulator = _Emulator()
    runtime = build_red_goal_context_runtime(
        profile=_team_profile("evolution-fixture"),
        capture=_capture(
            tmp_path,
            verified_objective_ids=(
                "power_on",
                "begin_adventure",
                "choose_starter",
                "receive_pokedex",
                "reach_pewter",
                "defeat_brock",
                "reach_cerulean",
                "help_bill",
                "reach_vermilion",
                "defeat_misty",
                "obtain_cut",
                "defeat_surge",
                "reach_lavender",
                "reach_celadon",
                "clear_rocket_hideout",
                "obtain_silph_scope",
                "rescue_fuji",
                "reach_fuchsia",
                "obtain_surf",
                "obtain_strength",
                "defeat_koga",
                "reach_cinnabar",
            ),
        ),
        emulator=emulator,
        reader=reader,  # type: ignore[arg-type]
    )
    actions = CountingExecutor(_ActionDelegate())

    def evolve(*_args: object, **_kwargs: object) -> tuple[object, int, int]:
        actions.execute(MacroAction(MacroActionKind.WAIT))
        emulator.tick(1)
        reader.raw = replace(
            reader.raw,
            party_species_ids=(0x1C, DUGTRIO_SPECIES_ID),
            party_levels=(48, 26),
        )
        return object(), 1, 0

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_context.run_red_team_balancing",
        evolve,
    )
    before = runtime.adapter.observe()
    binding_set = runtime.enumerator(actions).enumerate(before)
    binding = next(item for item in binding_set.bindings if item.kind is GoalKind.EVOLVE_SPECIES)

    report = binding.execute()
    verification = binding.verify(report)
    after = runtime.adapter.observe()

    assert before.evidence.evolution == after.evidence.evolution
    assert after.party.species_ids() == (0x1C, DUGTRIO_SPECIES_ID)
    assert report.actions_executed == 1
    assert verification.status.value == "succeeded"
