from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_funding_fly as funding_fly
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_field_moves import FLY_MOVE_ID
from pokemon_red_completion.gen1_trainer_parties import (
    TrainerPartyMember,
    TrainerPartyQuote,
)
from pokemon_red_completion.gen1_trainer_sight import (
    TrainerFacing,
    TrainerHeader,
)
from pokemon_red_completion.gen1_traversal import MapObjectEvent
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import (
    Badge,
    InputReadiness,
    OverworldMovementMode,
    RawGameState,
)
from pokemon_red_completion.red_funding_fly import (
    FundingFlyCandidate,
    funding_fly_candidates,
)
from pokemon_red_completion.red_trainer_funding import TrainerFundingCandidate


def synthetic_cartridge() -> bytes:
    """cartridge ROM fixture with valid Fly landing pointer table at 0x6448."""
    rom = bytearray(0x8000)
    for index, map_id in enumerate((*range(11), 15, 21)):
        pointer = 0x7000 + index * 8
        rom[0x6448 + index * 4 : 0x644C + index * 4] = bytes(
            (map_id, 0, pointer & 255, pointer >> 8)
        )
        y, x = 6 + index, 9 + index
        if map_id == 5:
            y, x = 11, 14
        rom[pointer : pointer + 6] = bytes((0x40, 0xC7, y, x, y & 1, x & 1))
    return bytes(rom)


def make_grid(
    height: int, width: int, blocked: frozenset[tuple[int, int]] = frozenset(),
) -> LocalGraph:
    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for y in range(height):
        for x in range(width):
            if (y, x) in blocked:
                continue
            cell_edges = []
            for dy, dx, action in ((-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and (ny, nx) not in blocked:
                    cell_edges.append(
                        LocalEdge(
                            (ny, nx),
                            action=action,
                            action_kind=MacroActionKind.MOVE,
                            kind="walk",
                            required_mode="land",
                            result_mode="land",
                        )
                    )
            edges[(y, x)] = tuple(cell_edges)
    return LocalGraph(edges)


@pytest.fixture
def funding_env(monkeypatch):
    rom = synthetic_cartridge()

    # Quote fixture
    monkeypatch.setattr(
        "pokemon_red_completion.red_regional_trainer_funding.trainer_party_quote",
        lambda *args: TrainerPartyQuote(
            201, 9, (TrainerPartyMember(108, 23, 21),), 15, 315
        ),
    )

    town_grid = make_grid(16, 16)
    route_grid = make_grid(16, 16)

    # Synthetic town5 connects to synthetic route23; not a real-map topology claim.
    macro = MacroGraph(
        {
            5: (
                MacroEdge(
                    23,
                    kind="connection",
                    coordinate_transitions=(MacroTransition((15, 14), (0, 14), "down"),),
                ),
            ),
            23: (),
            22: (),
        }
    )

    world = SimpleNamespace(
        rom=rom,
        macro_graph=macro,
        local_graphs={5: town_grid, 23: route_grid, 22: make_grid(8, 8)},
        object_blockers={5: frozenset(), 23: frozenset(), 22: frozenset()},
    )

    raw = RawGameState(
        game_started=True,
        map_id=22,
        player_y=4,
        player_x=4,
        battle_state=0,
        badge_bits=int(Badge.THUNDER),
        party_count=1,
        party_species_ids=(16,),
        party_hp=(100,),
        party_moves=((FLY_MOVE_ID, 33),),
        event_flags=bytes(320),
    )

    state = SimpleNamespace(raw=raw)
    reader = SimpleNamespace(
        read=lambda: state.raw,
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_menu_state=lambda: None,
        read_overworld_movement_mode=lambda: OverworldMovementMode.WALKING,
        read_input_readiness=lambda: InputReadiness(0, 0, 0, 0, 0, 0, 0),
        read_fly_destinations=lambda: (5,),
        read_retained_outside_map=lambda: 22,
        read_visible_object_coordinates=lambda: frozenset(),
        trainer_engagement_active=lambda: False,
    )

    spec = SimpleNamespace(
        kind=GoalKind.RESUPPLY,
        parameters={"funding_fly_transport": True},
    )
    profile = SimpleNamespace(providers=(spec,))
    runtime = SimpleNamespace(reader=reader, profile=profile)
    router = SimpleNamespace(
        runtime=runtime,
        world=world,
        regional_trainer_funding=True,
    )

    # Mock static trainer discovery to return an undefeated trainer on route 23
    trainer_header = TrainerHeader(23, 1, 3, 17, 0)
    trainer_event = MapObjectEvent(23, 1, 4, 14, 0xFF, 0xD0, 0x42, 1, 201, 9)

    monkeypatch.setattr(
        funding_fly,
        "trainer_headers",
        lambda _rom, maps, **kwargs: (trainer_header,) if 23 in maps else (),
    )
    monkeypatch.setattr(
        funding_fly,
        "map_object_events",
        lambda _rom, maps: (trainer_event,) if 23 in maps else (),
    )

    return router, state, reader, world


def test_opt_in_regional_trainer_funding_and_funding_fly_transport(funding_env):
    router, state, reader, world = funding_env

    # 1. Base case produces candidate
    candidates = funding_fly_candidates(router)
    assert len(candidates) == 1
    assert candidates[0].town == 5
    assert candidates[0].landing == (11, 14)
    assert isinstance(candidates[0], FundingFlyCandidate)
    assert isinstance(candidates[0].target, TrainerFundingCandidate)

    # 2. regional_trainer_funding is False -> empty
    router.regional_trainer_funding = False
    assert funding_fly_candidates(router) == ()
    router.regional_trainer_funding = True

    # 3. funding_fly_transport is False -> empty
    resupply = router.runtime.profile.providers[0]
    resupply.parameters["funding_fly_transport"] = False
    assert funding_fly_candidates(router) == ()

    # 4. Old fly_transport must NOT enable funding fly
    resupply.parameters["funding_fly_transport"] = False
    resupply.parameters["fly_transport"] = True
    assert funding_fly_candidates(router) == ()

    # 5. Non-resupply spec declaring funding_fly_transport must NOT enable it
    resupply.parameters["funding_fly_transport"] = False
    non_resupply = SimpleNamespace(
        kind=GoalKind.ACQUIRE_SPECIES,
        parameters={"funding_fly_transport": True},
    )
    router.runtime.profile.providers = (non_resupply,)
    assert funding_fly_candidates(router) == ()


def test_badge_carrier_and_unlocks(funding_env):
    router, state, reader, world = funding_env

    # 1. Thunder badge absent -> empty
    state.raw = replace(state.raw, badge_bits=0)
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, badge_bits=int(Badge.THUNDER))

    # 2. Fly carrier fainted -> empty
    state.raw = replace(state.raw, party_hp=(0,))
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, party_hp=(100,))

    # 3. No party member knows Fly -> empty
    state.raw = replace(state.raw, party_moves=((33, 10),))
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, party_moves=((FLY_MOVE_ID, 33),))

    # 4. Town not in unlocked fly destinations -> empty
    reader.read_fly_destinations = lambda: (0, 1)  # town 5 not unlocked
    assert funding_fly_candidates(router) == ()
    reader.read_fly_destinations = lambda: (5,)

    # 5. Out of range or invalid town indices skipped
    reader.read_fly_destinations = lambda: (99, -1, True, 5)
    candidates = funding_fly_candidates(router)
    assert len(candidates) == 1
    assert candidates[0].town == 5


def test_pending_battle_menu_and_readiness_guards(funding_env):
    router, state, reader, world = funding_env

    # 1. In battle
    state.raw = replace(state.raw, battle_state=1)
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, battle_state=0)

    # 2. Dialogue visible
    reader.read_bottom_dialogue_box_visible = lambda: True
    assert funding_fly_candidates(router) == ()
    reader.read_bottom_dialogue_box_visible = lambda: False

    # 3. Pending trainer battle
    reader.read_pending_trainer_battle_identity = lambda: (201, 1)
    assert funding_fly_candidates(router) == ()
    reader.read_pending_trainer_battle_identity = lambda: None

    # 4. Active fly menu
    reader.read_fly_menu_state = lambda: SimpleNamespace()
    assert funding_fly_candidates(router) == ()
    reader.read_fly_menu_state = lambda: None

    # 5. Input not ready
    reader.read_input_readiness = lambda: SimpleNamespace(ready=False)
    assert funding_fly_candidates(router) == ()
    reader.read_input_readiness = lambda: InputReadiness(0, 0, 0, 0, 0, 0, 0)

    # 6. Movement mode not walking (e.g. biking)
    reader.read_overworld_movement_mode = lambda: OverworldMovementMode.BIKING
    assert funding_fly_candidates(router) == ()
    reader.read_overworld_movement_mode = lambda: OverworldMovementMode.WALKING


def test_excluded_and_blocked_landings_and_same_town(funding_env):
    router, state, reader, world = funding_env

    # 1. Player is already in destination town (same-map exclusion)
    state.raw = replace(state.raw, map_id=5)
    reader.read_retained_outside_map = lambda: 5
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, map_id=22)
    reader.read_retained_outside_map = lambda: 22

    # 2. Player is in non-outdoor map (indoor map >= 0x25 or 0x0B)
    state.raw = replace(state.raw, map_id=0x25)
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, map_id=0x0B)
    assert funding_fly_candidates(router) == ()
    state.raw = replace(state.raw, map_id=22)

    # 3. Landing tile blocked by static object blocker
    world.object_blockers[5] = frozenset({(11, 14)})
    assert funding_fly_candidates(router) == ()
    world.object_blockers[5] = frozenset()

    # 4. Landing tile not in local graph
    world.local_graphs[5] = make_grid(16, 16, blocked=frozenset({(11, 14)}))
    assert funding_fly_candidates(router) == ()
    world.local_graphs[5] = make_grid(16, 16)


def test_remote_hazards_and_origin_isolation(funding_env, monkeypatch):
    router, state, reader, world = funding_env

    # Origin map has occupied coordinates and active hazards
    reader.read_visible_object_coordinates = lambda: frozenset({(4, 5), (4, 3)})

    # Origin occupancy should NOT leak into town 5 projection
    candidates = funding_fly_candidates(router)
    assert len(candidates) == 1
    assert candidates[0].town == 5

    # Remote trainer facing down at (4, 14) with engage distance 3 covers (5, 14), (6, 14), (7, 14).
    # If the trainer covers the arrival connection tile at (0, 14) on route 23:
    trainer_header = TrainerHeader(23, 1, 3, 17, 0)
    # At (2, 14) facing DOWN with engage 3: lane covers (3, 14), (4, 14), (5, 14).
    # If target is at (1, 14) facing UP with engage 2: lane covers (0, 14), blocking the entrance!
    blocking_event = MapObjectEvent(23, 1, 1, 14, 0xFF, 0xD1, 0x42, 1, 201, 9)
    monkeypatch.setattr(funding_fly, "trainer_headers",
                        lambda _rom, maps, **kwargs: (trainer_header,) if 23 in maps else ())
    monkeypatch.setattr(funding_fly, "map_object_events",
                        lambda _rom, maps: (blocking_event,) if 23 in maps else ())

    # Entrance to route 23 at (0, 14) is in the trainer's sight lane, so regional route cannot reach
    blocked_candidates = funding_fly_candidates(router)
    assert blocked_candidates == ()


def test_complete_static_map_inventory_and_event_flags(funding_env):
    router, state, reader, world = funding_env

    # Set event flag 17 (bit 1 of byte 2, since 17 = 2*8 + 1)
    flags = bytearray(320)
    flags[2] |= 1 << 1
    state.raw = replace(state.raw, event_flags=bytes(flags))

    # Static trainer is marked defeated by event flag -> no candidate
    assert funding_fly_candidates(router) == ()

    # Clear event flag -> candidate is available
    state.raw = replace(state.raw, event_flags=bytes(320))
    candidates = funding_fly_candidates(router)
    assert len(candidates) == 1
    assert candidates[0].target.trainer.defeated is False

    # Corrupted ROM in red_fly_landings raises CartridgeReadError (never silently swallowed)
    corrupted_rom = bytearray(synthetic_cartridge())
    corrupted_rom[0x6448] = 0x99  # corrupt map id
    world.rom = bytes(corrupted_rom)
    with pytest.raises(CartridgeReadError):
        funding_fly_candidates(router)


def test_real_regional_planner_with_unequal_route_geometry(funding_env, monkeypatch):
    router, state, reader, world = funding_env

    # Build unequal route geometry in Route 23:
    # Landing in Town 5 is at (11, 14). Transition to Route 23 is at (15, 14) -> (0, 14).
    # In Route 23, create an obstacle wall forcing a detour around column 12 vs column 14.
    wall = frozenset({(y, 14) for y in range(1, 5)})
    world.local_graphs[23] = make_grid(16, 16, blocked=wall)

    # Trainer is at (6, 14), facing DOWN with engage 1 (lane covers (7, 14)).
    # Route goes through (0,14), left to column13, then down past the wall to interact.
    trainer_header = TrainerHeader(23, 1, 1, 17, 0)
    trainer_event = MapObjectEvent(23, 1, 6, 14, 0xFF, 0xD0, 0x42, 1, 201, 9)
    monkeypatch.setattr(funding_fly, "trainer_headers",
                        lambda _rom, maps, **kwargs: (trainer_header,) if 23 in maps else ())
    monkeypatch.setattr(funding_fly, "map_object_events",
                        lambda _rom, maps: (trainer_event,) if 23 in maps else ())

    candidates = funding_fly_candidates(router)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.town == 5
    assert cand.landing == (11, 14)

    plan = cand.target.approach
    assert plan.terminal_map == 23
    assert plan.macro_path.maps == (5, 23)
    # The detour avoids the wall and arrives at interaction boundary (5, 14)
    assert plan.terminal_at == (5, 14)
    assert cand.target.interaction_facing is TrainerFacing.DOWN
    # Plan steps contain connection step and walk steps
    assert any(step.kind == "connection" for step in plan.steps)
    assert len(plan.steps) > 8


def test_nontrainer_object_blocks_remote_entry_not_only_landing(funding_env):
    router, _, _, world = funding_env
    assert len(funding_fly_candidates(router)) == 1
    # A non-trainer occupies the only onward entrance, in a different map from Fly.
    world.object_blockers[23] = frozenset({(0, 14)})
    assert funding_fly_candidates(router) == ()


def test_missing_static_inventory_is_not_an_empty_map(funding_env):
    router, _, _, world = funding_env
    del world.object_blockers[5]
    with pytest.raises(CartridgeReadError, match="inventory"):
        funding_fly_candidates(router)


def test_changed_unlocks_during_planning_do_not_yield_stale_candidate(funding_env):
    router, _, reader, _ = funding_env
    unlocks = iter(((5,), ()))
    reader.read_fly_destinations = lambda: next(unlocks)
    with pytest.raises(CartridgeReadError, match="unlocks changed"):
        funding_fly_candidates(router)
