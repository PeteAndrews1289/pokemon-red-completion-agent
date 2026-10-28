"""A declared native location flag is not an arbitrary story/resource waiver."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_wild_party_flee import state

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
from pokemon_red_completion.observation import BattleMenuPhase, EventFlag, MapId
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.wild_party_flee import purified_zone_escape_event, validate_flee_party


def flags(*set_bits):
    result = bytearray(320)
    for bit in set_bits:
        result[int(bit) // 8] |= 1 << (int(bit) % 8)
    return bytes(result)


def encounter(at=(9, 11), *, inside=False):
    return replace(
        state(),
        map_id=int(MapId.POKEMON_TOWER_5F),
        player_y=at[0],
        player_x=at[1],
        party_hp=(40, 140, 66, 71),
        first_party_hp=40,
        active_party_hp=40,
        party_moves=((33, 0, 0, 0),) * 4,
        party_pp=((35, 0, 0, 0),) * 4,
        party_stats=((40, 40, 40, 40),) * 4,
        enemy_species_id=17,
        enemy_level=22,
        event_flags=flags(*((EventFlag.IN_PURIFIED_ZONE,) if inside else ())),
    )


@pytest.mark.parametrize(
    "at,entry",
    [
        ((8, 10), True),
        ((8, 11), True),
        ((9, 10), True),
        ((9, 11), True),
        ((7, 10), False),
        ((10, 11), False),
        ((9, 9), False),
        ((9, 12), False),
    ],
)
def test_native_zone_membership_change_requires_opt_in_and_keeps_origin(at, entry):
    before = encounter(at, inside=not entry)
    after = replace(
        before,
        battle_state=0,
        battle_result=2,
        event_flags=flags(*((EventFlag.IN_PURIFIED_ZONE,) if entry else ())),
    )
    original = before.event_flags
    with pytest.raises(ValueError, match="protected state"):
        validate_flee_party(before, after)
    validate_flee_party(before, after, allow_native_purified_transition=True)
    proof = purified_zone_escape_event(before, after)
    assert proof["before"] is not entry and proof["after"] is entry
    assert proof["event"] == "IN_PURIFIED_ZONE" and not proof["healing_performed_by_handler"]
    assert before.event_flags == original


@pytest.mark.parametrize(
    "fault",
    [
        "map",
        "tile",
        "drift",
        "still_battle",
        "wrong_exit",
        "enemy",
        "level",
        "other_event",
        "reverse_event",
        "no_flags",
        "stats",
        "cash",
        "bag",
        "badge",
        "moves",
        "pp",
        "unhealed_before",
        "unhealed_after",
        "status",
        "source_status",
        "encoded_capacity",
    ],
)
def test_zone_certificate_refuses_every_other_boundary_and_resource_change(fault):
    before = encounter()
    after = replace(
        before, battle_state=0, battle_result=2, event_flags=flags(EventFlag.IN_PURIFIED_ZONE)
    )
    if fault == "map":
        before, after = replace(before, map_id=145), replace(after, map_id=145)
    elif fault == "tile":
        before, after = replace(before, player_x=12), replace(after, player_x=12)
    elif fault == "drift":
        after = replace(after, player_x=10)
    elif fault == "still_battle":
        after = replace(after, battle_state=1)
    elif fault == "wrong_exit":
        after = replace(after, battle_result=0)
    elif fault == "enemy":
        after = replace(after, enemy_species_id=25)
    elif fault == "level":
        after = replace(after, enemy_level=21)
    elif fault == "other_event":
        after = replace(after, event_flags=flags(EventFlag.IN_PURIFIED_ZONE, 271))
    elif fault == "reverse_event":
        before, after = (
            replace(before, event_flags=flags(EventFlag.IN_PURIFIED_ZONE)),
            replace(after, event_flags=flags()),
        )
    elif fault == "no_flags":
        after = replace(after, event_flags=None)
    elif fault == "stats":
        after = replace(after, party_stats=((41, 40, 40, 40),) * 4)
    elif fault == "cash":
        after = replace(after, player_money=after.player_money + 1)
    elif fault == "bag":
        after = replace(after, bag_items=((1, 1),))
    elif fault == "badge":
        after = replace(after, badge_bits=after.badge_bits + 1)
    elif fault == "moves":
        after = replace(after, party_moves=((1, 0, 0, 0),) * 4)
    elif fault == "pp":
        after = replace(after, party_pp=((34, 0, 0, 0),) * 4)
    elif fault == "unhealed_before":
        before = replace(before, party_hp=(39, 140, 66, 71))
    elif fault == "unhealed_after":
        after = replace(after, party_hp=(39, 140, 66, 71))
    elif fault == "status":
        after = replace(after, party_status=(8, 0, 0, 0))
    elif fault == "source_status":
        before = replace(before, party_status=(8, 0, 0, 0))
    elif fault == "encoded_capacity":
        before, after = (
            replace(before, party_pp=((64 + 35, 0, 0, 0),) * 4),
            replace(after, party_pp=((64 + 35, 0, 0, 0),) * 4),
        )
    with pytest.raises(ValueError):
        validate_flee_party(
            before,
            after,
            allow_native_purified_transition=True,
            allow_new_faints=True,
            allow_status_changes=True,
        )


@pytest.mark.parametrize("allow", [True, False])
def test_native_handler_records_certificate_without_new_inputs_or_budget_reset(allow):
    initial = encounter()
    current, inputs, events = [initial], [], []

    def execute(action):
        inputs.append(action.kind)
        if action.kind is MacroActionKind.CONFIRM:
            current[0] = replace(
                initial,
                battle_state=0,
                battle_result=2,
                event_flags=flags(EventFlag.IN_PURIFIED_ZONE),
            )

    reader = N(
        read=lambda: current[0],
        read_input_readiness=lambda: N(ready=True),
        read_battle_menu_state=lambda _: N(phase=BattleMenuPhase.MAIN, selected_main_command=3),
        trainer_engagement_active=lambda: False,
    )
    actions = N(
        execute=execute, record_diagnostic_event=lambda kind, row: events.append((kind, row))
    )
    handler = Gen1WildFleeHandler(
        actions,
        reader,
        maximum_flees=1,
        stabilization_frames=24,
        allow_party_faints=True,
        allow_field_faint_dialogue=allow,
    )
    boundary = TraversalSnapshot(146, (9, 11), False, "wild_battle")
    if not allow:
        with pytest.raises(RouteExecutionError, match="protected state"):
            handler.handle(boundary)
        assert not handler.evidence and not events
    else:
        result = handler.handle(boundary)
        assert result.details["verified"] and result.details["native_field_event"]["after"]
        assert len(handler.evidence) == len(events) == 1
        assert events[0][0] == "native_purified_zone_escape"
        assert inputs == [MacroActionKind.CONFIRM, MacroActionKind.WAIT, MacroActionKind.WAIT]
        with pytest.raises(RouteExecutionError, match="flee budget"):
            handler.handle(boundary)


@pytest.mark.parametrize("value", [1, None, "yes"])
def test_native_transition_permission_is_a_strict_boolean(value):
    before = encounter()
    with pytest.raises(TypeError, match="purification allowance"):
        validate_flee_party(before, before, allow_native_purified_transition=value)
