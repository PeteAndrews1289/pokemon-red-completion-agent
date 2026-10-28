"""Keep strict status protection after a native copy falsified a status waiver."""

from dataclasses import replace

import pytest
from test_gen1_route_runtime import FakeReader, raw, reader_as_real

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def test_already_cleared_native_faint_preserves_strict_status_guard():
    receipt = run_transition(already_cleared=True)
    assert receipt.details["new_fainted_slots"] == [2]
    assert receipt.details["pending_native_poison_tick_slots"] == [3]
    assert receipt.details["model_queries"] == 0


def test_unwitnessed_status_clear_during_text_is_still_rejected():
    with pytest.raises(RouteExecutionError, match="protected resources"):
        run_transition(already_cleared=False)


@pytest.mark.parametrize("fault", [
    "living_cure", "earlier_cure", "different_status", "new_poison", "mixed_status",
    "boolean_status", "missing_status", "extra_faint", "healing", "cash", "bag",
    "pp", "species", "boxes", "dex", "unknown_warp",
])
def test_faint_status_exception_does_not_waive_other_native_guards(fault):
    with pytest.raises(RouteExecutionError, match="protected resources"):
        run_transition(fault=fault)


def run_transition(*, already_cleared=False, fault=None):
    initial = replace(raw(), map_id=6, player_y=13, player_x=10, party_count=3,
        party_species_ids=(28, 166, 151), party_hp=(5, 1, 3), party_status=(8, 8, 8),
        party_max_hp=(5, 20, 30), party_stats=((1, 2, 3, 4),) * 3,
        party_pp=((5,),) * 3, player_money=100)
    fake = FakeReader(initial, dialogue_visible=True, moving_direction=8)
    box, dex = [()], [()]
    fake.read_all_box_states = lambda: box[0]
    fake.read_pokedex_state = lambda: dex[0]

    class Port:
        def execute(self, action):
            if action.kind is MacroActionKind.CANCEL:
                fake.ready, fake.dialogue_visible, fake.moving_direction = True, False, 0
                changes = dict(party_hp=(5, 0, 2), party_status=(8, 0, 8))
                if fault == "living_cure":
                    changes["party_status"] = (8, 0, 0)
                elif fault == "earlier_cure":
                    changes["party_status"] = (0, 0, 8)
                elif fault == "different_status":
                    changes["party_status"] = (8, 16, 8)
                elif fault == "new_poison":
                    changes["party_status"] = (8, 8, 8)
                elif fault == "mixed_status":
                    changes["party_status"] = (8, 0, 8)
                elif fault == "boolean_status":
                    changes["party_status"] = (8, False, 8)
                elif fault == "missing_status":
                    changes["party_status"] = None
                elif fault == "extra_faint":
                    changes["party_hp"] = (5, 0, 0)
                elif fault == "healing":
                    changes["party_hp"] = (5, 1, 2)
                elif fault == "cash":
                    changes["player_money"] = 101
                elif fault == "bag":
                    changes["bag_items"] = ((4, 1),)
                elif fault == "pp":
                    changes["party_pp"] = ((5,), (5,), (4,))
                elif fault == "species":
                    changes["party_species_ids"] = (28, 166, 150)
                elif fault == "boxes":
                    box[0] = ("changed",)
                elif fault == "dex":
                    dex[0] = ("changed",)
                elif fault == "unknown_warp":
                    changes["map_id"] = 122
                fake.raw = replace(fake.raw, **changes)
            return action

    handler = Gen1WildFleeHandler(Port(), reader_as_real(fake), 0, 24,
        allow_party_faints=True, allow_field_faint_dialogue=True)
    current_status = 0 if already_cleared or fault == "new_poison" else 24 if fault == "mixed_status" else 8
    fake.raw = replace(initial, party_hp=(5, 0, 3), party_status=(8, current_status, 8))
    return handler.handle(TraversalSnapshot(6, (13, 10), False, "scripted_dialogue"))
