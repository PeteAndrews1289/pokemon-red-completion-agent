from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.red_safari_objective_route import require_objective_route


@pytest.mark.parametrize(
    "fault", [None, "house", "expired", "low_steps", "balls", "outside", "field_move", "water"]
)
def test_paid_objective_route_admission(fault):
    step = NS(
        source_map=220,
        expected_map=222 if fault == "house" else 219,
        kind="warp",
        action_kind=MacroActionKind.FIELD_MOVE if fault == "field_move" else MacroActionKind.MOVE,
        source_mode="land",
        expected_mode="water" if fault == "water" else "land",
    )
    plan = NS(
        steps=(step,),
        terminal_map=7 if fault == "outside" else step.expected_map,
        terminal_mode="land",
    )
    session = NS(
        in_safari_zone=True,
        safari_game_over=fault == "expired",
        safari_steps=17 if fault == "low_steps" else 200,
        safari_balls=1 if fault == "balls" else 30,
    )
    if fault in {None, "house"}:
        require_objective_route(plan, session)
    else:
        with pytest.raises(ValueError):
            require_objective_route(plan, session)


@pytest.mark.parametrize(
    "fault", [None, "money", "balls", "expired", "position", "not_ready", "route_failed"]
)
def test_objective_execution_conserves_native_boundary(monkeypatch, fault):
    from pokemon_red_completion import red_safari_objective_route as module

    raw = NS(
        map_id=220,
        player_y=25,
        player_x=15,
        battle_state=0,
        bag_items=((4, 1),),
        player_money=6649,
        party_species_ids=(28,),
        party_levels=(48,),
        party_moves=((57,),),
        party_pp=((15,),),
        party_hp=(150,),
        party_status=(0,),
    )
    session = NS(in_safari_zone=True, safari_game_over=False, safari_steps=500, safari_balls=30)
    ready = True
    reader = NS(
        read=lambda: raw,
        read_safari_session_state=lambda: session,
        read_input_readiness=lambda: NS(ready=ready),
        read_current_map_blocks=lambda: None,
    )
    monkeypatch.setattr(
        module,
        "Gen1TraversalObserver",
        lambda r: NS(observe=lambda: NS(ready=True, interruption=None, map_id=220)),
    )
    step = NS(
        source_map=220,
        expected_map=219,
        kind="walk",
        action_kind=MacroActionKind.MOVE,
        source_mode="land",
        expected_mode="land",
    )
    plan = NS(steps=(step,), terminal_map=219, terminal_mode="land")
    world = NS(plan_feasible_to_map=lambda *args, **kwargs: plan)
    world.with_current_blocks = lambda _: world

    def execute(*args, **kwargs):
        nonlocal raw, session, ready
        raw = NS(**(vars(raw) | {"map_id": 219, "player_y": 8, "player_x": 19}))
        session = NS(**(vars(session) | {"safari_steps": 499}))
        if fault == "money":
            raw.player_money -= 500
        if fault == "balls":
            session.safari_balls -= 1
        if fault == "expired":
            session.safari_game_over = True
        if fault == "position":
            raw.player_x = 18
        if fault == "not_ready":
            ready = False
        return NS(passed=fault != "route_failed")

    monkeypatch.setattr(module, "execute_route", execute)
    if fault:
        with pytest.raises(RuntimeError):
            module.route_safari_objective(None, reader, None, world, map_id=219, at=(8, 19))
    else:
        assert (
            module.route_safari_objective(None, reader, None, world, map_id=219, at=(8, 19))[
                "steps_after"
            ]
            == 499
        )
