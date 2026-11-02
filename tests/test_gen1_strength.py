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
from pokemon_red_completion.route_executor import (
    ResourceRenewalReceipt,
    RouteActionPort,
    RouteResourceManager,
    TraversalObserver,
    TraversalResource,
    TraversalSnapshot,
)


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
            tuple(tile_overrides.get((y, x), 1) for x in range(width)) for y in range(len(picture))
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


def test_arrival_warp_can_be_departed_but_not_reentered():
    world = terrain((".....", ".....", "....."))
    initial = StrengthState((1, 1), (StrengthBoulder(1, (1, 2)),))
    plan = plan_strength(
        world,
        rules(),
        initial,
        StrengthGoal((1, 3)),
        raw((1, 1)),
        forbidden_player_coordinates={(1, 1)},
    )
    assert plan.steps[0].kind == "push"  # stationary push on arrival is legal
    assert plan.states[-1].boulders[0].at == (1, 3)
    detour = plan_strength(
        world,
        rules(),
        initial,
        StrengthGoal((1, 0)),
        raw((1, 1)),
        forbidden_player_coordinates={(1, 1)},
    )
    assert all(s.result.player_at != (1, 1) for s in detour.steps if s.kind == "walk")
    assert detour.states[-1].boulders[0].at == (1, 0)


def test_other_warp_is_not_a_valid_puzzle_transit():
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    with pytest.raises(StrengthPlanningError, match="no legal Strength plan"):
        plan_strength(
            terrain((".....",)),
            rules(),
            initial,
            StrengthGoal((0, 4)),
            raw((0, 0)),
            forbidden_player_coordinates={(0, 1)},
        )


def test_directional_warp_allows_transit_but_not_outward_action():
    world = terrain((".....",))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    plan = plan_strength(
        world,
        rules(),
        initial,
        StrengthGoal((0, 4)),
        raw((0, 0)),
        forbidden_player_edges={((0, 1), "down")},
    )
    assert plan.states[-1].boulders[0].at == (0, 4)
    with pytest.raises(StrengthPlanningError, match="no legal Strength plan"):
        plan_strength(
            world,
            rules(),
            initial,
            StrengthGoal((0, 4)),
            raw((0, 0)),
            forbidden_player_edges={((0, 1), "right")},
        )


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


def test_planner_models_a_scripted_hole_as_one_terminal_boulder_removal() -> None:
    world = terrain((".....",))
    initial = StrengthState((0, 0), (StrengthBoulder(6, (0, 1)),))

    plan = plan_strength(
        world,
        rules(),
        initial,
        StrengthGoal((0, 2), boulder_index=6, remove_boulder=True),
        raw((0, 0)),
    )

    assert [step.kind for step in plan.steps] == ["drop"]
    assert plan.steps[0].boulder_index == 6
    assert plan.states[-1] == StrengthState((0, 0), ())


def test_disappearing_goal_requires_a_named_present_boulder() -> None:
    with pytest.raises(ValueError, match="must name"):
        StrengthGoal((0, 2), remove_boulder=True)

    with pytest.raises(StrengthPlanningError, match="is not present"):
        plan_strength(
            terrain((".....",)),
            rules(),
            StrengthState((0, 0), (StrengthBoulder(6, (0, 1)),)),
            StrengthGoal((0, 2), boulder_index=7, remove_boulder=True),
            raw((0, 0)),
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
    expose_boulder_dust: bool = False
    boulder_dust: bool = False
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
            value = (1 << 1) if self.boulder_dust else 0
            if self.pushed and not self.suppress_pushed_flag:
                value |= 1 << 7
            return value
        return 0

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(
            map_id=int(self.raw.map_id or 0),
            at=(int(self.raw.player_y or 0), int(self.raw.player_x or 0)),
            ready=True,
            resources=(
                TraversalResource(
                    "encounter_suppression",
                    self.raw.repel_remaining_steps,
                    sum(quantity for _item, quantity in (self.raw.bag_items or ())),
                ),
            ),
        )

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            self.boulder_dust = False
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
        self.boulder_dust = self.expose_boulder_dust
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
    assert not report.pushes[0].boulder_removed
    assert report.pushes[0].pushed_flag_observed
    assert report.pushes[0].engine_attempt_cost == 2
    assert (report.pushes[0].boulder_before, report.pushes[0].boulder_after) == (
        (0, 2),
        (0, 3),
    )


@dataclass
class StrengthResourceManager:
    world: StrengthWorld

    def renew_if_needed(
        self,
        current: TraversalSnapshot,
    ) -> ResourceRenewalReceipt | None:
        (resource,) = current.resources
        if resource.remaining:
            return None
        self.world.raw = replace(
            self.world.raw,
            bag_items=(),
            repel_remaining_steps=250,
        )
        return ResourceRenewalReceipt(
            kind=resource.kind,
            map_id=current.map_id,
            at=current.at,
            before_remaining=0,
            after_remaining=250,
            units_consumed=1,
        )


def test_strength_renews_a_depleted_resource_without_weakening_party_protection() -> None:
    world_map = terrain((".....", "....."))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    plan = plan_strength(
        world_map,
        rules(),
        initial,
        StrengthGoal((0, 3)),
        raw((0, 0)),
    )
    world = StrengthWorld(
        raw=replace(
            raw((0, 0)),
            bag_items=((0x39, 1),),
            repel_remaining_steps=0,
        )
    )

    report = Gen1StrengthExecutor(
        cast(RouteActionPort, world),
        cast(PokemonRedStateReader, world),
        cast(ReadOnlyMemory, world),
        resource_manager=cast(RouteResourceManager, StrengthResourceManager(world)),
        resource_observer=cast(TraversalObserver, world),
    ).execute(plan)

    assert report.passed
    assert len(report.resource_renewals) == 1
    assert report.resource_renewals[0].after_remaining == 250
    assert world.raw.bag_items == ()


def test_executor_accepts_transient_dust_when_a_map_script_consumes_the_push_flag() -> None:
    world_map = terrain((".....",))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 1)),))
    plan = plan_strength(
        world_map,
        rules(),
        initial,
        StrengthGoal((0, 2)),
        raw((0, 0)),
    )
    world = StrengthWorld(
        boulders={1: (0, 1)},
        suppress_pushed_flag=True,
        expose_boulder_dust=True,
    )

    report = Gen1StrengthExecutor(
        cast(RouteActionPort, world),
        cast(PokemonRedStateReader, world),
        cast(ReadOnlyMemory, world),
    ).execute(plan)

    assert report.passed
    assert report.pushes[0].boulder_dust_observed
    assert not report.pushes[0].pushed_flag_observed
    assert report.pushes[0].engine_acknowledged


def test_executor_acknowledges_an_exact_terminal_boulder_removal() -> None:
    world_map = terrain((".....",))
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 1)),))
    plan = plan_strength(
        world_map,
        rules(),
        initial,
        StrengthGoal((0, 2), boulder_index=1, remove_boulder=True),
        raw((0, 0)),
    )
    world = StrengthWorld(boulders={1: (0, 1)})

    original_execute = world.execute

    def execute_and_remove(action: MacroAction) -> object:
        result = original_execute(action)
        if action.kind is MacroActionKind.WAIT and world.pushed:
            world.boulders.clear()
        return result

    world.execute = execute_and_remove  # type: ignore[method-assign]
    report = Gen1StrengthExecutor(
        cast(RouteActionPort, world),
        cast(PokemonRedStateReader, world),
        cast(ReadOnlyMemory, world),
    ).execute(plan)

    assert report.passed
    assert report.pushes[0].boulder_removed
    assert report.pushes[0].boulder_after == (0, 2)


def test_executor_fails_closed_if_a_push_moves_the_player_or_lacks_engine_ack() -> None:
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
    with pytest.raises(StrengthPlanningError, match="lacked an engine push acknowledgement"):
        Gen1StrengthExecutor(
            cast(RouteActionPort, no_flag),
            cast(PokemonRedStateReader, no_flag),
            cast(ReadOnlyMemory, no_flag),
        ).execute(plan)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "unbound",
        "trainer",
        "hp",
        "pp",
        "money",
        "species",
        "position",
        "boulder",
        "receipt",
        "unready",
        "handler_failure",
    ],
)
def test_strength_wild_recovery_keeps_exact_state_and_resource_guards(fault):
    from types import SimpleNamespace

    from pokemon_red_completion.route_executor import InterruptionReceipt

    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    plan = plan_strength(
        terrain((".....", ".....")), rules(), initial, StrengthGoal((0, 3)), raw((0, 0))
    )
    world = StrengthWorld()
    original = world.execute
    seen = []

    def execute(action):
        original(action)
        if (
            action.kind is MacroActionKind.MOVE
            and len([a for a in world.actions if a.kind is MacroActionKind.MOVE]) == 1
        ):
            world.raw = replace(world.raw, battle_state=2 if fault == "trainer" else 1)

    world.execute = execute

    def observe():
        return TraversalSnapshot(
            7,
            (world.raw.player_y, world.raw.player_x),
            ready=world.raw.battle_state == 0 and fault != "unready",
            interruption="wild_battle" if world.raw.battle_state == 1 else None,
        )

    def recover(snapshot):
        seen.append(snapshot)
        if fault == "handler_failure":
            raise RuntimeError("retained escape failure")
        world.raw = replace(world.raw, battle_state=0)
        updates = {
            "hp": {"party_hp": (1,)},
            "pp": {"party_pp": ((0,),)},
            "money": {"player_money": 0},
            "species": {"party_species_ids": (1,)},
            "position": {"player_x": 4},
        }
        if fault in updates:
            world.raw = replace(world.raw, **updates[fault])
        if fault == "boulder":
            world.boulders[1] = (1, 2)
        return InterruptionReceipt(
            "trainer_battle" if fault == "receipt" else "wild_battle", 7, snapshot.at
        )

    executor = Gen1StrengthExecutor(
        world,
        world,
        world,
        interruption_observer=None if fault == "unbound" else SimpleNamespace(observe=observe),
        interruption_handler=None if fault == "unbound" else SimpleNamespace(handle=recover),
    )
    if fault is None:
        report = executor.execute(plan)
        assert report.passed and len(report.interruptions) == len(seen) == 1
        assert [a.value for a in world.actions if a.kind is MacroActionKind.MOVE] == [
            "right",
            "right",
        ]
    else:
        with pytest.raises((StrengthPlanningError, RuntimeError)):
            executor.execute(plan)
        assert len(seen) == (0 if fault in {"unbound", "trainer"} else 1)


@pytest.mark.parametrize("option", ["interruption_handler", "interruption_observer"])
def test_strength_partial_recovery_binding_refuses_before_input(option):
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    plan = plan_strength(
        terrain((".....", ".....")), rules(), initial, StrengthGoal((0, 3)), raw((0, 0))
    )
    world = StrengthWorld()
    with pytest.raises(StrengthPlanningError, match="handler and observer"):
        Gen1StrengthExecutor(world, world, world, **{option: object()}).execute(plan)
    assert not world.actions


@pytest.mark.parametrize(
    "fault", [None, "repeated", "no_battle", "moved_boulder", "hp", "pp", "inactive", "stale_push"]
)
def test_interrupted_push_reissues_only_after_proven_unchanged_escape(fault):
    from types import SimpleNamespace

    from pokemon_red_completion.route_executor import InterruptionReceipt

    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 1)),))
    plan = plan_strength(
        terrain((".....", ".....")), rules(), initial, StrengthGoal((0, 2)), raw((0, 0))
    )
    world = StrengthWorld(boulders={1: (0, 1)})
    original = world.execute
    moves = []

    def execute(action):
        if action.kind is MacroActionKind.MOVE:
            moves.append(action)
            if len(moves) == 1 or fault == "repeated":
                world.actions.append(action)
                world.raw = replace(world.raw, battle_state=0 if fault == "no_battle" else 1)
                return
        original(action)

    world.execute = execute

    def observe():
        return TraversalSnapshot(
            7,
            (world.raw.player_y, world.raw.player_x),
            ready=world.raw.battle_state == 0,
            interruption="wild_battle" if world.raw.battle_state == 1 else None,
        )

    def recover(snapshot):
        world.raw = replace(world.raw, battle_state=0)
        if fault == "moved_boulder":
            world.boulders[1] = (1, 1)
        if fault == "hp":
            world.raw = replace(world.raw, party_hp=(1,))
        if fault == "pp":
            world.raw = replace(world.raw, party_pp=((0,),))
        if fault == "inactive":
            world.status_flags_1 = 0
        if fault == "stale_push":
            world.pushed = True
        return InterruptionReceipt("wild_battle", 7, snapshot.at)

    executor = Gen1StrengthExecutor(
        world,
        world,
        world,
        interruption_observer=SimpleNamespace(observe=observe),
        interruption_handler=SimpleNamespace(handle=recover),
    )
    if fault is None:
        report = executor.execute(plan)
        assert report.passed and len(moves) == 2 and report.controller_inputs == 2
        assert len(report.interruptions) == 1 and report.pushes[0].interrupted_attempts == 1
        assert report.pushes[0].engine_acknowledged
    else:
        with pytest.raises(StrengthPlanningError):
            executor.execute(plan)
        assert len(moves) == (4 if fault == "repeated" else 1)
        assert not executor.push_receipts


@pytest.mark.parametrize("fault", [
    None, "already_facing", "wrong_facing", "moved", "hp", "ack",
    "prior_push", "prior_push_already_facing", "prior_push_dust",
])
def test_turn_only_push_retries_only_after_observed_facing_change(fault):
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 1)),))
    plan = plan_strength(terrain((".....", ".....")), rules(), initial,
                         StrengthGoal((0, 2)), raw((0, 0)))
    world = StrengthWorld(boulders={1: (0, 1)})
    original = world.execute
    world.pushed = fault in {"prior_push", "prior_push_already_facing", "prior_push_dust"}
    facing = ["right" if fault in {"already_facing", "prior_push_already_facing"} else "up"]
    world.read_player_facing = lambda: facing[0]
    moves = []

    def execute(action):
        if action.kind is MacroActionKind.MOVE:
            moves.append(action)
            if len(moves) == 1:
                world.actions.append(action)
                facing[0] = "down" if fault == "wrong_facing" else "right"
                if fault == "moved":
                    world.raw = replace(world.raw, player_y=1)
                if fault == "hp":
                    world.raw = replace(world.raw, party_hp=(1,))
                if fault == "ack":
                    world.pushed = True
                if fault == "prior_push_dust":
                    world.boulder_dust = True
                return
        return original(action)

    world.execute = execute
    executor = Gen1StrengthExecutor(world, world, world)
    if fault in {None, "prior_push"}:
        report = executor.execute(plan)
        assert report.passed and len(moves) == 2
        assert report.pushes[0].facing_adjustments == 1
        assert report.pushes[0].interrupted_attempts == 0
        assert report.pushes[0].engine_acknowledged
    else:
        with pytest.raises(StrengthPlanningError):
            executor.execute(plan)
        assert len(moves) == 1 and not executor.push_receipts
@pytest.mark.parametrize("push", [False, True])
@pytest.mark.parametrize(
    "fault",
    [None, "unproved", "proof_hp", "healing", "faint", "pp", "status", "bag",
     "money", "species", "position", "boulder", "receipt", "outside_battle"],
)
def test_opt_in_strength_retains_only_exact_verified_wild_lead_damage(push, fault):
    from types import SimpleNamespace

    from pokemon_red_completion.route_executor import InterruptionReceipt

    at = (0, 1) if push else (0, 2)
    initial = StrengthState((0, 0), (StrengthBoulder(1, at),))
    plan = plan_strength(
        terrain((".....", ".....")), rules(), initial,
        StrengthGoal((0, at[1] + 1)), raw((0, 0)),
    )
    world = StrengthWorld(boulders={1: at})
    original = world.execute
    moves = 0

    def execute(action):
        nonlocal moves
        if action.kind is MacroActionKind.MOVE:
            moves += 1
            if moves == 1:
                if fault == "outside_battle":
                    original(action)
                    world.raw = replace(world.raw, party_hp=(8,))
                elif push:
                    world.actions.append(action)
                    world.raw = replace(world.raw, battle_state=1)
                else:
                    original(action)
                    world.raw = replace(world.raw, battle_state=1)
                return
        original(action)

    world.execute = execute

    def observe():
        return TraversalSnapshot(
            7, (world.raw.player_y, world.raw.player_x),
            ready=world.raw.battle_state == 0,
            interruption="wild_battle" if world.raw.battle_state == 1 else None,
        )

    def recover(snapshot):
        hp = 11 if fault == "healing" else 0 if fault == "faint" else 8
        world.raw = replace(world.raw, battle_state=0, party_hp=(hp,))
        changes = {
            "pp": {"party_pp": ((0,),)}, "status": {"party_status": (8,)},
            "bag": {"bag_items": ((1, 1),)}, "money": {"player_money": 0},
            "species": {"party_species_ids": (1,)}, "position": {"player_x": 4},
        }
        if fault in changes:
            world.raw = replace(world.raw, **changes[fault])
        if fault == "boulder":
            world.boulders[1] = (1, 2)
        return InterruptionReceipt(
            "trainer_battle" if fault == "receipt" else "wild_battle", 7, snapshot.at,
            details={"verified": fault != "unproved", "hp_scope": "first_party_member",
                     "initial_hp": 9 if fault == "proof_hp" else 10, "final_hp": hp},
        )

    executor = Gen1StrengthExecutor(
        world, world, world, allow_verified_wild_hp_loss=True,
        interruption_observer=SimpleNamespace(observe=observe),
        interruption_handler=SimpleNamespace(handle=recover),
    )
    if fault is None:
        report = executor.execute(plan)
        assert report.passed and world.raw.party_hp == (8,)
        assert len(report.interruptions) == 1
        assert report.interruptions[0].details["initial_hp"] == 10
        assert report.interruptions[0].details["final_hp"] == 8
        assert report.terminal == plan.states[-1]
    else:
        with pytest.raises(StrengthPlanningError):
            executor.execute(plan)


@pytest.mark.parametrize("permission", [None, 0, 1, "yes"])
def test_strength_wild_damage_permission_must_be_boolean(permission):
    world = StrengthWorld()
    initial = StrengthState((0, 0), (StrengthBoulder(1, (0, 2)),))
    plan = plan_strength(
        terrain((".....", ".....")), rules(), initial, StrengthGoal((0, 3)), raw((0, 0))
    )
    with pytest.raises(StrengthPlanningError, match="permission must be boolean"):
        Gen1StrengthExecutor(world, world, world,
                            allow_verified_wild_hp_loss=permission).execute(plan)
    assert not world.actions
