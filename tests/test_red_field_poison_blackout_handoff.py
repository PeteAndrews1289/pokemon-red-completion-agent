"""A proved last-member poison loss is not an ordinary dismissible field faint."""
import json
from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest
from test_gen1_route_runtime import FakeReader
from test_red_player_preparation_binding import setup

from pokemon_red_completion import gen1_route_runtime as g
from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.goal_manager import GoalFailureReason
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.route_executor import (
    RouteExecutionError,
    RouteExecutionFailureReason,
    TraversalSnapshot,
)


@pytest.mark.parametrize("dead_reserve", [False, True])
@pytest.mark.parametrize("fault", [None, "no_emulator", "held", "not_poison", "already_dead",
    "survivor", "uncleared_status", "cash", "bag", "events", "species", "level", "pp",
    "trainer", "no_dialogue", "battle", "ready", "disabled", "missing_prior", "wrong_tile"])
def test_only_proved_all_party_poison_transition_hands_off_without_inputs(dead_reserve, fault):
    hp, statuses = ((0, 12), (0, 8)) if dead_reserve else ((12,), (8,))
    size = len(hp)
    before = RawGameState(True, MapId.ROUTE_2, 9, 49, size, 0,
        party_hp=hp, party_status=statuses, party_species_ids=(177,) * size,
        party_levels=(8,) * size, party_max_hp=(25,) * size,
        party_stats=((13, 17, 14, 15),) * size, party_moves=((33, 39, 145, 0),) * size,
        party_pp=((25, 30, 30, 0),) * size, player_money=3175,
        bag_items=(), badge_bits=0, event_flags=b"\0" * 320)
    if fault == "not_poison":
        before = replace(before, party_status=(0,) * size)
    if fault == "already_dead":
        before = replace(before, party_hp=(0,) * size)
    fake = FakeReader(before, dialogue_visible=True, moving_direction=4)
    actions = []
    emulator = (
        None if fault == "no_emulator" else N(pressed_buttons=("a",) if fault == "held" else ())
    )
    handler = g.Gen1WildFleeHandler(N(execute=actions.append), fake, maximum_flees=2,
        stabilization_frames=24, allow_party_faints=True, emulator=emulator,
        allow_field_faint_dialogue=fault != "disabled")
    after = replace(before, map_id=MapId.VIRIDIAN_CITY, player_x=18, player_y=18,
                    party_hp=(0,) * size, party_status=(0,) * size)
    changes = {
        "survivor": dict(party_hp=(1,) * size),
        "uncleared_status": dict(party_status=statuses),
        "cash": dict(player_money=1587), "bag": dict(bag_items=((4, 1),)),
        "events": dict(event_flags=b"\1" * 320),
        "species": dict(party_species_ids=(28,) * size),
        "level": dict(party_levels=(9,) * size),
        "pp": dict(party_pp=((24, 30, 30, 0),) * size),
        "battle": dict(battle_state=1),
    }
    fake.raw = replace(after, **changes.get(fault, {}))
    fake.trainer_engagement = fault == "trainer"
    fake.dialogue_visible = fault != "no_dialogue"
    fake.moving_direction = 0 if fault == "ready" else 4
    if fault == "missing_prior":
        handler._field_boundary = None
    interruption = TraversalSnapshot(MapId.VIRIDIAN_CITY,
        (19, 18) if fault == "wrong_tile" else (18, 18), False, "scripted_dialogue")
    with pytest.raises(RouteExecutionError) as caught:
        handler.handle(interruption)
    assert type(caught.value).__name__ == (
        "Gen1FieldBlackoutPending" if fault is None else "RouteExecutionError")
    assert not actions and not handler.field_faint_evidence


@pytest.mark.parametrize("typed", [True, False])
def test_preparation_only_connects_typed_field_loss_without_success(monkeypatch, typed):
    rt, actions, kwargs, mon = setup(monkeypatch)
    rt.emulator.save_state_bytes = lambda: b"settled"
    records, settlements = [], []
    def record(name, value):
        json.dumps(value)  # Real recorder rejects unserializable route-plan sets.
        records.append((name, value))

    kwargs["record"] = record

    def defeat(**kw):
        mon.experience += 24
        actions.actions_executed += 4
        error_type = g.Gen1FieldBlackoutPending if typed else RouteExecutionError
        error = error_type("observed all-party field poison faint requires native blackout")
        if typed:
            @dataclass
            class Step:
                source_map: int = 13

            error.attach_failure(N(
                initial_plan=N(requirements=frozenset({"field"})),
                reason=RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED,
                executed_steps=(N(step=Step()),), movement_requests=12, wait_actions=0,
            ))
        raise error

    def settle(*a, **kw):
        settlements.append(kw)
        assert kw["allow_field_loss"] is True
        actions.actions_executed += 2
        return dict(terminal_sha256=p.sha256(b"settled").hexdigest(),
            blackout=dict(cash_lost=1500), successful_preparation=False)

    monkeypatch.setattr(p, "execute_wild_preparation", defeat)
    monkeypatch.setattr(p, "settle_preparation_loss", settle)
    binding = p.preparation_binding(rt, actions, **kwargs)
    if not typed:
        with pytest.raises(RouteExecutionError):
            binding.execute()
        assert not settlements and not records
        return
    report = binding.execute()
    assert report.actions_executed == 6
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    assert [name for name, _ in records] == ["field-blackout-handoff"]
    assert records[0][1]["learned_recovery"] is False


@pytest.mark.parametrize("fault", [None, "living", "battle", "ready", "dialogue", "xp", "scope"])
def test_field_settlement_reuses_exact_blackout_and_progress_checks(monkeypatch, fault):
    from test_red_player_loss_settlement import fixture

    rt, before, _, terminal, calls, records = fixture(monkeypatch)
    before.raw.battle_state = 0
    rt.reader.read_input_readiness = lambda: N(ready=fault == "ready")
    rt.reader.read_bottom_dialogue_box_visible = lambda: not calls and fault != "dialogue"
    if fault == "living":
        before.raw.party_hp = (1,)
    if fault == "battle":
        before.raw.battle_state = 1
    if fault == "xp":
        terminal["party"][0]["experience"] += 1

    def run():
        return p.settle_preparation_loss(rt, None, record=lambda *a: records.append(a),
                                        allow_field_loss=fault != "scope")

    if fault:
        with pytest.raises(ValueError):
            run()
        assert len(calls) == (1 if fault == "xp" else 0)
    else:
        result = run()
        assert not result["successful_preparation"] and not result["learned_recovery"]
        assert result["blackout"]["cash_lost"] == 1500
        assert calls == [dict(maximum_pulses=128, allow_field_loss=True)]


@pytest.mark.parametrize("scope", [None, 1, "true"])
def test_field_settlement_scope_is_not_truthiness(scope):
    with pytest.raises(TypeError, match="explicit boolean"):
        p.settle_preparation_loss(None, None, record=None, allow_field_loss=scope)
