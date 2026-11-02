"""The known native healing message is not general dialogue authority."""

from dataclasses import replace

import pytest
from test_gen1_route_runtime import FakeReader, raw, reader_as_real

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@pytest.mark.parametrize("fault", [
    None, "map", "event", "unhealed", "status", "trainer", "battle", "disabled",
    "cash", "bag", "changed_event", "pp", "relocation", "dex", "box",
])
def test_only_native_healed_zone_dismisses_without_resource_changes(fault):
    flags = bytearray(320)
    event = int(EventFlag.IN_PURIFIED_ZONE)
    if fault != "event":
        flags[event // 8] |= 1 << (event % 8)
    initial = replace(
        raw(), map_id=MapId.ROUTE_1 if fault == "map" else MapId.POKEMON_TOWER_5F,
        player_y=9, player_x=11, event_flags=bytes(flags), party_species_ids=(28,),
        party_hp=(99 if fault == "unhealed" else 100,), party_max_hp=(100,),
        party_status=(8 if fault == "status" else 0,), party_levels=(38,),
        party_moves=((33, 0, 0, 0),), party_pp=((35, 0, 0, 0),), player_money=29651,
        badge_bits=15, battle_state=2 if fault == "battle" else 0,
    )
    fake = FakeReader(initial, dialogue_visible=True, moving_direction=4)
    fake.trainer_engagement = fault == "trainer"
    boxes, dex, actions, diagnostics = [], [], [], []
    fake.read_all_box_states = lambda: tuple(boxes)
    fake.read_pokedex_state = lambda: tuple(dex)

    class Port:
        def record_diagnostic_event(self, kind, payload):
            diagnostics.append((kind, payload))

        def execute(self, action):
            actions.append(action)
            if action.kind is MacroActionKind.CANCEL:
                fake.ready, fake.dialogue_visible, fake.moving_direction = True, False, 0
                change = {
                    "cash": dict(player_money=29650),
                    "bag": dict(bag_items=((1, 1),)),
                    "changed_event": dict(event_flags=b"\x00" * 320),
                    "pp": dict(party_pp=((34, 0, 0, 0),)),
                    "relocation": dict(player_y=8),
                }.get(fault, {})
                fake.raw = replace(fake.raw, **change)
                if fault == "box":
                    boxes.append(1)
                if fault == "dex":
                    dex.append(1)
            return action

    handler = Gen1WildFleeHandler(
        Port(), reader_as_real(fake), maximum_flees=2, stabilization_frames=24,
        allow_party_faints=True, allow_field_faint_dialogue=fault != "disabled",
    )
    interruption = TraversalSnapshot(initial.map_id, (9, 11), False, "scripted_dialogue")
    if fault:
        with pytest.raises(RouteExecutionError):
            handler.handle(interruption)
        if fault in {"map", "event", "unhealed", "status", "trainer", "battle", "disabled"}:
            assert actions == []
    else:
        receipt = handler.handle(interruption)
        assert receipt.details["native_purified_zone"] is True
        assert receipt.details["already_healed"] is True
        assert receipt.details["model_queries"] == 0 and not receipt.allows_relocation
        assert handler.field_healing_evidence == [receipt]
        assert handler.field_faint_evidence == [] and handler.evidence == []
        assert diagnostics[0][0] == "native_purified_zone_message"
        assert diagnostics[0][1]["healing_performed_by_handler"] is False
        assert diagnostics[0][1]["actor"] == "rule_based_support"
        assert fake.raw == initial
        assert [a.kind for a in actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]
