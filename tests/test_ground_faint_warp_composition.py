"""Exercise ground transport and its real strict faint guard together, ROM free."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_route_runtime import FakeReader, raw, reader_as_real
from test_red_training_ground_route import _world

from pokemon_red_completion import red_training_ground_route as ground
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


@pytest.mark.parametrize("fault", [None, "wrong_landing", "unplanned_warp", "cash", "disabled"])
def test_ground_route_faint_finishes_only_its_selected_plan_warp(monkeypatch, fault):
    origin, endpoint = (14, (5, 18)), (68, (7, 3))
    initial = replace(raw(), map_id=origin[0], player_y=origin[1][0],
        player_x=origin[1][1], party_count=3, party_species_ids=(28, 166, 151),
        party_hp=(5, 1, 3), party_status=(8, 8, 8), player_money=100)
    fake = FakeReader(initial)
    fake.read_all_box_states = lambda: ()
    fake.read_pokedex_state = lambda: ()
    actions = []

    class Port:
        def execute(self, action):
            actions.append(action)
            if action.kind is MacroActionKind.CANCEL:
                fake.ready, fake.dialogue_visible, fake.moving_direction = True, False, 0
                changes = dict(map_id=endpoint[0], player_y=endpoint[1][0],
                               player_x=endpoint[1][1], party_hp=(5, 0, 2))
                if fault == "wrong_landing":
                    changes["player_x"] = endpoint[1][1] + 1
                elif fault == "unplanned_warp":
                    changes["map_id"] = 69
                elif fault == "cash":
                    changes["player_money"] = 101
                fake.raw = replace(fake.raw, **changes)
            return action

    def observe():
        value = fake.read()
        return TraversalSnapshot(value.map_id, (value.player_y, value.player_x), True)

    observer = SimpleNamespace(observe=observe)
    monkeypatch.setattr(ground, "Gen1TraversalObserver", lambda *a, **k: observer)
    monkeypatch.setattr(ground, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(ground, "Gen1FieldMovePort", lambda port, *a, **k: port)
    edge = SimpleNamespace(source_map=origin[0], target_map=endpoint[0], passage_kind="warp",
        transition=SimpleNamespace(exit_at=origin[1], arrival_at=endpoint[1]))
    plan = SimpleNamespace(segments=(
        SimpleNamespace(passage_kind="walk"), edge,
        SimpleNamespace(source_map=68, target_map=68, passage_kind="warp"),
    ))
    monkeypatch.setattr(StrategicScenarioRouteWorld, "plan_feasible_to_map", lambda *a, **k: plan)
    monkeypatch.setattr(StrategicScenarioRouteWorld, "replanner", lambda *a: lambda r: plan)
    receipts = []

    def execute(selected, port, traversal, *, interruption_handler, **kwargs):
        assert selected is plan and port is actions_port and traversal is observer
        fake.dialogue_visible, fake.moving_direction = True, 4
        fake.raw = replace(initial, party_hp=(5, 0, 3), party_status=(8, 0, 8))
        receipts.append(interruption_handler.handle(
            TraversalSnapshot(*origin, False, "scripted_dialogue")))

    monkeypatch.setattr(ground, "execute_route", execute)
    actions_port = Port()
    transition = ground.RedVermilionGroundTransition(b"rom", _world(),
        destination_map=endpoint[0], destination_at=endpoint[1],
        allow_wild_faints=True, allow_field_faint_dialogue=fault != "disabled")
    if fault:
        with pytest.raises(RouteExecutionError):
            transition(actions_port, reader_as_real(fake), SimpleNamespace(pressed_buttons=()))
        assert not receipts
    else:
        transition(actions_port, reader_as_real(fake), SimpleNamespace(pressed_buttons=()))
        assert len(receipts) == 1
        receipt = receipts[0]
        assert (receipt.resumed_map, receipt.resumed_at) == endpoint
        assert receipt.details["new_fainted_slots"] == [2]
        assert receipt.details["pending_native_poison_tick_slots"] == [3]
        assert receipt.details["model_queries"] == 0
        assert receipt.allows_map_transition and receipt.allows_relocation
        assert [action.kind for action in actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]
