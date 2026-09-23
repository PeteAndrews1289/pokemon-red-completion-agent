"""Indoor paid acquisition must exit, recheck, then execute only the real child."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_live_safari import _area

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.red_live_option_menu import supplemental_live_option
from pokemon_red_completion.red_live_safari import RedLiveSafariInventory


def setup(monkeypatch, fault=None, all_areas=False, fuchsia=False, active=False,
          wrong_map=False, outdoor=False):
    import pokemon_red_completion.red_indoor_safari as mod

    raw = RawGameState(
        True, 89, 3, 3, 6, 0, player_money=1073, party_species_ids=(1, 2, 3, 4, 5, 6), bag_items=()
    )
    if outdoor:
        raw = replace(raw, map_id=int(MapId.FUCHSIA_CITY))
    state = NS(raw=raw, actions_executed=0, frame_count=0, pressed_buttons=frozenset())
    reader = NS(
        read=lambda: state.raw,
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_input_readiness=lambda: NS(ready=True),
        read_safari_session_state=lambda: NS(in_safari_zone=active, safari_game_over=False),
    )
    start = NS(map_id=raw.map_id, at=(3, 3))
    monkeypatch.setattr(mod, "Gen1TraversalObserver", lambda _r: NS(observe=lambda: start))
    plan = NS(terminal_map=int(MapId.FUCHSIA_CITY) if fuchsia else 5,
              terminal_at=(8, 21), steps=(1, 2, 3))
    monkeypatch.setattr(mod, "bounded_indoor_departure", lambda *_: plan)
    gate = NS(terminal_map=int(MapId.SAFARI_ZONE_GATE), terminal_at=(5, 4), steps=(
        NS(source_map=raw.map_id, expected_map=7),
        NS(source_map=7, expected_map=9 if wrong_map else int(MapId.SAFARI_ZONE_GATE)),
    ))
    world = NS(plan_feasible_to_map=lambda *_: gate)
    monkeypatch.setattr(mod, "_walking_plan", lambda p: True)
    target = int(MapId.SAFARI_ZONE_GATE) if fuchsia else 5
    arrival = (5, 4) if fuchsia else (8, 21)
    calls = []
    areas = (_area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 3, 4),)
    if all_areas:
        areas += (_area("wild:SafariZoneNorth:grass", int(MapId.SAFARI_ZONE_NORTH), 2, 2),)

    def inventory(*args, **kwargs):
        projected = kwargs["reader"] is not reader
        calls.append("project" if projected else "rebind")
        assert kwargs["reader"].read().map_id == target

        def execute():
            assert not projected, "projected executor must never run"
            calls.append("spend")
            state.actions_executed += 10
            state.frame_count += 50
            return GoalExecutionReport(10, 50, {"admission": {"money_spent": 500}})

        binding = ExecutableGoalBinding(
            "child",
            GoalKind.ACQUIRE_SPECIES,
            0.1,
            0,
            execute,
            lambda _r: GoalVerification.succeeded(),
        )
        features = LivingDexOptionFeatures(LivingDexOptionKind.ACQUIRE, *([0.1] * 9))
        candidate = LivingDexOptionCandidate(
            "child", features, LivingDexOptionAvailability.AVAILABLE
        )
        if fault == "rebind" and not projected:
            return RedLiveSafariInventory((), ())
        if all_areas:
            assert kwargs["expose_all_areas"] is True
            def second_execute():
                result = execute()
                calls.append("second")
                return result
            second = replace(binding, binding_ref="second", execute=second_execute)
            if fault == "identity" and not projected:
                second = replace(second, binding_ref="replacement")
            options = (
                supplemental_live_option(binding, candidate),
                supplemental_live_option(second, candidate),
            )
            # Changed enumeration order must not change the selected destination.
            return RedLiveSafariInventory(areas, options if projected else options[::-1])
        return RedLiveSafariInventory(areas, (supplemental_live_option(binding, candidate),))

    monkeypatch.setattr(mod, "build_red_live_safari_inventory", inventory)

    def route(*args, **kwargs):
        calls.append("exit")
        state.actions_executed += 3
        state.frame_count += 20
        state.raw = replace(
            state.raw,
            map_id=target,
            player_y=arrival[0],
            player_x=arrival[1],
            player_money=1000 if fault == "cash" else 1073,
        )
        return NS(passed=True)

    monkeypatch.setattr(mod, "execute_route", route)
    monkeypatch.setattr(mod, "public_route_execution", lambda _r: {"passed": True})
    result = mod.indoor_safari_inventory(
        b"rom",
        (),
        object(),
        free_storage_slots=2,
        world=world,
        controller=state,
        actions=state,
        reader=reader,
        expose_all_areas=all_areas,
    )
    if all_areas:
        return result, state, calls
    return result.supplements[0].binding, state, calls


def test_indoor_safari_only_executes_fresh_rebound_offer_with_shared_costs(monkeypatch):
    binding, state, calls = setup(monkeypatch)
    assert calls == ["project"] and state.frame_count == 0
    report = binding.execute()
    assert calls == ["project", "exit", "rebind", "spend"]
    assert report.actions_executed == 13 and report.frames_executed == 70
    assert binding.verify(report) == GoalVerification.succeeded()
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_multiple_indoor_areas_preserve_selected_child_and_one_shot(monkeypatch):
    inventory, state, calls = setup(monkeypatch, all_areas=True)
    selected = inventory.supplements[1].binding
    report = selected.execute()
    assert calls == ["project", "exit", "rebind", "spend", "second"]
    assert report.actions_executed == 13 and report.frames_executed == 70
    assert selected.verify(report) == GoalVerification.succeeded()
    with pytest.raises(ValueError, match="consumed"):
        inventory.supplements[0].binding.execute()


def test_multiple_indoor_areas_reject_selected_child_substitution(monkeypatch):
    inventory, state, calls = setup(monkeypatch, fault="identity", all_areas=True)
    with pytest.raises(ValueError, match="Selected Safari offer changed"):
        inventory.supplements[1].binding.execute()
    assert "spend" not in calls and state.actions_executed == 3


@pytest.mark.parametrize("fault", ["cash", "rebind"])
def test_indoor_safari_does_not_spend_after_changed_exit_or_offer(monkeypatch, fault):
    binding, state, calls = setup(monkeypatch, fault)
    with pytest.raises(ValueError, match="changed"):
        binding.execute()
    assert "spend" not in calls and state.actions_executed == 3


def test_indoor_safari_stale_origin_never_sends_input(monkeypatch):
    binding, state, calls = setup(monkeypatch)
    state.raw = replace(state.raw, player_x=4)
    with pytest.raises(ValueError, match="changed before input"):
        binding.execute()
    assert calls == ["project"] and state.frame_count == 0


def test_fuchsia_indoor_departure_walks_to_unpaid_gate_without_redundant_flight(monkeypatch):
    inventory, state, calls = setup(monkeypatch, all_areas=True, fuchsia=True)
    assert calls == ["project"] and state.frame_count == 0
    selected = inventory.supplements[1].binding
    report = selected.execute()
    assert selected.verify(report) == GoalVerification.succeeded()
    assert calls == ["project", "exit", "rebind", "spend", "second"]


def test_fuchsia_outdoor_arrival_exposes_real_area_choices_without_redundant_flight(monkeypatch):
    inventory, state, calls = setup(monkeypatch, all_areas=True, fuchsia=True, outdoor=True)
    assert calls == ["project"] and state.frame_count == 0
    selected = inventory.supplements[1].binding
    assert selected.verify(selected.execute()) == GoalVerification.succeeded()
    assert calls == ["project", "exit", "rebind", "spend", "second"]


def test_fuchsia_outdoor_rejects_an_active_session(monkeypatch):
    inventory, state, calls = setup(monkeypatch, all_areas=True, fuchsia=True,
                                    outdoor=True, active=True)
    assert not inventory.supplements and not calls and state.frame_count == 0


@pytest.mark.parametrize("fault", ["active", "unrelated_map"])
def test_fuchsia_gate_departure_refuses_active_session_or_unrelated_route(monkeypatch, fault):
    inventory, state, calls = setup(monkeypatch, all_areas=True, fuchsia=True,
                                    active=fault == "active", wrong_map=fault == "unrelated_map")
    assert not inventory.supplements and not calls and state.frame_count == 0
