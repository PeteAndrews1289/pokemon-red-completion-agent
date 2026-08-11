from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_strength import (
    STRENGTH_PUSH_COST,
    Gen1StrengthExecutor,
    StrengthBoulder,
    StrengthGoal,
    StrengthPlanningError,
    StrengthState,
    plan_strength,
)
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import (
    STRENGTH_MOVE_ID,
    TilePairRestriction,
    TraversalRules,
)
from pokemon_red_completion.observation import (
    Badge,
    CurrentStrengthBoulder,
    InputReadiness,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.route_executor import RouteActionPort


def terrain(
    picture: tuple[str, ...],
    *,
    tiles: dict[tuple[int, int], int] | None = None,
) -> Terrain:
    width = len(picture[0])
    assert all(len(row) == width for row in picture)
    tile_overrides = tiles or {}
    return Terrain(
        map_id=7,
        tileset=1,
        walkable=tuple(tuple(cell != "#" for cell in row) for row in picture),
        grass=tuple(tuple(False for _ in row) for row in picture),
        water=tuple(tuple(False for _ in row) for row in picture),
        tiles=tuple(
            tuple(tile_overrides.get((y, x), 1) for x in range(width))
            for y in range(len(picture))
        ),
    )


def rules(*, land: tuple[TilePairRestriction, ...] = ()) -> TraversalRules:
    return TraversalRules((), land, (), (), ())


def raw(at: tuple[int, int] = (1, 1)) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=7,
        player_y=at[0],
        player_x=at[1],
        party_count=1,
        battle_state=0,
        badge_bits=int(Badge.RAINBOW),
        party_hp=(10,),
        party_moves=((STRENGTH_MOVE_ID,),),
    )


def test_planner_routes_around_a_boulder_then_prices_each_push_as_two_inputs() -> None:
    world = terrain(("#####", "#...#", "#...#", "#...#", "#####"))
    initial = StrengthState((1, 1), (StrengthBoulder(4, (1, 2)),))

    plan = plan_strength(world, rules(), initial, StrengthGoal((1, 1)), raw())

    assert [step.kind for step in plan.steps] == ["walk", "walk", "walk", "walk", "push"]
    assert [step.direction.value for step in plan.steps] == [
        "down",
        "right",
        "right",
        "up",
        "left",
    ]
    assert plan.cost == 4 + STRENGTH_PUSH_COST
    assert plan.states[-1].player_at == (1, 3)
    assert plan.states[-1].boulders == (StrengthBoulder(4, (1, 1)),)


def test_planner_tracks_multiple_boulders_in_state_instead_of_deleting_offscreen_one() -> None:
    world = terrain(("#######", "#.....#", "#.....#", "#######"))
    initial = StrengthState(
        (2, 1),
        (StrengthBoulder(2, (1, 3)), StrengthBoulder(9, (2, 3))),
    )

    plan = plan_strength(
        world,
        rules(),
        initial,
        StrengthGoal((2, 5), boulder_index=9),
        raw((2, 1)),
    )

    pushes = [step for step in plan.steps if step.kind == "push"]
    assert [step.boulder_index for step in pushes] == [9, 9]
    assert plan.states[-1].boulders == (
        StrengthBoulder(2, (1, 3)),
        StrengthBoulder(9, (2, 5)),
    )


def test_planner_rejects_stairs_elevation_pairs_and_occupied_push_destinations() -> None:
    stair_world = terrain((".....",), tiles={(0, 3): 0x15})
    initial = StrengthState((0, 1), (StrengthBoulder(1, (0, 2)),))
    with pytest.raises(StrengthPlanningError, match="no legal"):
        plan_strength(stair_world, rules(), initial, StrengthGoal((0, 3)), raw((0, 1)))

    elevation_world = terrain((".....",), tiles={(0, 2): 0x20, (0, 3): 0x05})
    with pytest.raises(StrengthPlanningError, match="no legal"):
        plan_strength(
            elevation_world,
            rules(land=(TilePairRestriction(1, 0x20, 0x05),)),
            initial,
            StrengthGoal((0, 3)),
            raw((0, 1)),
        )

    occupied = StrengthState(
        (0, 0),
        (StrengthBoulder(1, (0, 1)), StrengthBoulder(2, (0, 2))),
    )
    with pytest.raises(StrengthPlanningError, match="no legal"):
        plan_strength(terrain(("....",)), rules(), occupied, StrengthGoal((0, 2), 1), raw((0, 0)))


def test_planner_fails_closed_on_capability_boundary_mismatch_and_state_bound() -> None:
    world = terrain((".....", "....."))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))

    with pytest.raises(StrengthPlanningError, match="Rainbow Badge"):
        plan_strength(
            world,
            rules(),
            initial,
            StrengthGoal((0, 3)),
            replace(raw((0, 0)), badge_bits=0),
        )
    with pytest.raises(StrengthPlanningError, match="does not match"):
        plan_strength(world, rules(), initial, StrengthGoal((0, 3)), raw((1, 0)))
    with pytest.raises(StrengthPlanningError, match="exceeded"):
        plan_strength(
            world,
            rules(),
            initial,
            StrengthGoal((0, 4)),
            raw((0, 0)),
            max_states=1,
        )


@dataclass
class StrengthWorld:
    raw: RawGameState = field(default_factory=lambda: raw((0, 0)))
    boulders: dict[int, tuple[int, int]] = field(default_factory=lambda: {1: (0, 2)})
    status_flags_1: int = 1
    pushed: bool = False
    suppress_pushed_flag: bool = False
    move_player_on_push: bool = False
    actions: list[MacroAction] = field(default_factory=list)

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0)

    def read_current_strength_boulders(self) -> tuple[CurrentStrengthBoulder, ...]:
        return tuple(
            CurrentStrengthBoulder(index, at, 0, 0x10, 0x10)
            for index, at in sorted(self.boulders.items())
        )

    def read_u8(self, address: int) -> int:
        if address == RamAddress.STATUS_FLAGS_1:
            return self.status_flags_1
        if address == RamAddress.MISC_FLAGS:
            return (1 << 7) if self.pushed and not self.suppress_pushed_flag else 0
        return 0

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return action
        assert action.kind is MacroActionKind.MOVE
        assert isinstance(action.value, str)
        dy, dx = {
            "up": (-1, 0),
            "right": (0, 1),
            "down": (1, 0),
            "left": (0, -1),
        }[action.value]
        player = int(self.raw.player_y or 0), int(self.raw.player_x or 0)
        adjacent = player[0] + dy, player[1] + dx
        pushed = next(
            (index for index, at in self.boulders.items() if at == adjacent),
            None,
        )
        if pushed is None:
            self.raw = replace(self.raw, player_y=adjacent[0], player_x=adjacent[1])
            return action
        beyond = adjacent[0] + dy, adjacent[1] + dx
        self.boulders[pushed] = beyond
        if self.move_player_on_push:
            self.raw = replace(self.raw, player_y=adjacent[0], player_x=adjacent[1])
        self.pushed = True
        return action


def test_executor_requires_the_held_pulse_engine_flag_and_exact_result() -> None:
    world_map = terrain((".....", "....."))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    plan = plan_strength(
        world_map,
        rules(),
        initial,
        StrengthGoal((0, 3)),
        raw((0, 0)),
    )
    world = StrengthWorld()
    executor = Gen1StrengthExecutor(
        cast(RouteActionPort, world),
        cast(PokemonRedStateReader, world),
        cast(ReadOnlyMemory, world),
    )

    report = executor.execute(plan)

    assert report.passed
    assert report.controller_inputs == 2  # one approach walk and one held push pulse
    assert len(report.pushes) == 1
    assert report.pushes[0].player_stationary
    assert report.pushes[0].pushed_flag_observed
    assert report.pushes[0].engine_attempt_cost == 2
    assert (report.pushes[0].boulder_before, report.pushes[0].boulder_after) == (
        (0, 2),
        (0, 3),
    )


def test_executor_fails_closed_if_a_push_moves_the_player_or_lacks_engine_flag() -> None:
    world_map = terrain((".....",))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 1)),))
    plan = plan_strength(
        world_map,
        rules(),
        initial,
        StrengthGoal((0, 2)),
        raw((0, 0)),
    )

    moved = StrengthWorld(boulders={1: (0, 1)}, move_player_on_push=True)
    with pytest.raises(StrengthPlanningError, match="exact state transition"):
        Gen1StrengthExecutor(
            cast(RouteActionPort, moved),
            cast(PokemonRedStateReader, moved),
            cast(ReadOnlyMemory, moved),
        ).execute(plan)

    no_flag = StrengthWorld(boulders={1: (0, 1)}, suppress_pushed_flag=True)
    with pytest.raises(StrengthPlanningError, match="lacked the engine pushed-boulder flag"):
        Gen1StrengthExecutor(
            cast(RouteActionPort, no_flag),
            cast(PokemonRedStateReader, no_flag),
            cast(ReadOnlyMemory, no_flag),
        ).execute(plan)
