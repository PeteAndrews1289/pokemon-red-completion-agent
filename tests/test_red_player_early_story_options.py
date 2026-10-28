from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion import red_player_early_story_options as p
from pokemon_red_completion.goal_manager import GoalKind


def fixture(
    monkeypatch, *, objective="obtain_cut", room=95, ready=True, legal=True, flags=(), script=0
):
    events = bytearray(320)
    for event in flags:
        events[event // 8] |= 1 << (event % 8)
    raw = N(map_id=room, event_flags=bytes(events), status_flags_1=0)
    rt = N(
        reader=N(
            read=lambda: raw,
            read_ss_anne_rival_script=lambda: script,
            read_current_map_objects=lambda: (),
        ),
        adapter=N(
            observe=lambda: N(game_state=None),
            graph=N(available_objectives=lambda _: (N(id=objective),) if legal else ()),
        ),
    )
    calls = []
    binding = _binding(GoalKind.ADVANCE_STORY, binding_ref="selected-native", calls=[])
    contract = N(trainer_identity=(242, 42, 1))
    monkeypatch.setattr(p, "_field_ready", lambda _: ready)
    for name in (
        "scripted_rival_binding",
        "captain_interaction_binding",
        "hideout_interaction_binding",
        "hideout_elevator_binding",
        "hideout_restoration_binding",
        "fuji_binding",
        "marowak_binding",
        "blocking_field_item_binding",
        "story_travel_binding",
        "obstructing_story_battle_binding",
        "saffron_access_binding",
        "parcel_story_binding",
        "story_battle_binding",
        "fossil_pickup_binding",
    ):

        def stub(*args, _name=name, **kwargs):
            calls.append((_name, kwargs))
            return None

        monkeypatch.setattr(p, name, stub)
    for name in ("ss_anne_rival_contract", "tower_rival_contract", "hideout_scripted_contract",
                 "fossil_guard_contract"):
        monkeypatch.setattr(p, name, lambda *a: contract)
    monkeypatch.setattr(p, "trainer_party_quote", lambda *a: N(party=(N(level=20), N(level=16))))
    return rt, N(rom=b"fixture"), N(), binding, calls, raw


@pytest.mark.parametrize("room", [199, 202, 203])
def test_fuji_departure_reuses_verified_healthy_hideout_return(monkeypatch, room):
    rt, route, actor, _, calls, _ = fixture(
        monkeypatch, objective="rescue_fuji", room=room,
    )
    original = _binding(GoalKind.RESTORE_TEAM, binding_ref="verified-return", calls=[])

    def returning(*args, **kwargs):
        calls.append(("return", kwargs))
        return original

    monkeypatch.setattr(p, "hideout_restoration_binding", returning)
    row = p.fuji_story_option(rt, N(), route=route, battler=actor, combat_levels=(38,))
    assert calls == [("return", dict(route=route, return_only=True))]
    assert row[0].story_objective_ref == "rescue_fuji"
    assert row[0].kind is GoalKind.ADVANCE_STORY
    assert original.kind is GoalKind.RESTORE_TEAM
    assert row[0].execute is original.execute and row[0].verify is original.verify
    assert not row[1].combat_required


@pytest.mark.parametrize("room", [199, 202, 203])
def test_unavailable_hideout_return_cannot_use_static_elevator_fallback(monkeypatch, room):
    rt, route, actor, _, calls, _ = fixture(
        monkeypatch, objective="rescue_fuji", room=room,
    )
    assert p.fuji_story_option(
        rt, N(), route=route, battler=actor, combat_levels=(38,),
    ) is None
    assert [name for name, _ in calls] == ["hideout_restoration_binding"]


@pytest.mark.parametrize("ready,legal", [(False, True), (True, False)])
@pytest.mark.parametrize(
    "objective",
    [
        "obtain_cut",
        "receive_pokedex",
        "clear_rocket_hideout",
        "rescue_fuji",
        "reach_saffron",
        "help_bill",
    ],
)
def test_unready_or_illegal_goals_do_not_build_any_executor(monkeypatch, ready, legal, objective):
    rt, route, actor, _, calls, _ = fixture(
        monkeypatch, objective=objective, ready=ready, legal=legal
    )
    shared = dict(route=route, battler=actor, combat_levels=(17,))
    if objective == "clear_rocket_hideout":
        result = p.hideout_story_option(rt, N(), objective_id=objective, **shared)
    elif objective == "receive_pokedex":
        result = p.parcel_story_option(rt, N(), route=route)
    elif objective == "reach_saffron":
        result = p.saffron_story_option(rt, N(), route=route, battler=actor)
    else:
        fn = {
            "obtain_cut": p.cut_story_option,
            "rescue_fuji": p.fuji_story_option,
            "help_bill": p.bill_story_option,
        }[objective]
        result = fn(rt, N(), **shared)
    assert result is None and calls == []


@pytest.mark.parametrize("ready,legal", [(False, True), (True, False)])
def test_cerulean_arrival_respects_readiness_and_graph_legality(monkeypatch, ready, legal):
    rt, route, actor, _, calls, _ = fixture(
        monkeypatch, objective="reach_cerulean", room=61, ready=ready, legal=legal
    )
    assert p.cerulean_arrival_story_option(
        rt, N(), route=route, battler=actor, combat_levels=(16,)
    ) is None
    assert calls == []


def test_cerulean_arrival_does_not_replace_an_executable_travel_option(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(
        monkeypatch, objective="reach_cerulean", room=61
    )
    monkeypatch.setattr(p, "story_travel_binding", lambda *a, **k: binding)
    row = p.cerulean_arrival_story_option(rt, N(), route=route, battler=actor, combat_levels=(16,))
    assert row[0].story_objective_ref == "reach_cerulean" and not row[1].opposition_known
    assert calls == []


@pytest.mark.parametrize("fault", ["map", "missing_events", "short_events"])
def test_cerulean_fossil_gate_requires_its_actual_readable_map(monkeypatch, fault):
    rt, route, actor, _, calls, raw = fixture(
        monkeypatch, objective="reach_cerulean", room=60 if fault == "map" else 61
    )
    if fault != "map":
        raw.event_flags = None if fault == "missing_events" else b"\x00"
    assert p.cerulean_arrival_story_option(
        rt, N(), route=route, battler=actor, combat_levels=(16,)
    ) is None
    assert not any(name in {"story_battle_binding", "fossil_pickup_binding"} for name, _ in calls)


def test_cerulean_arrival_reuses_exact_scripted_guard_without_completion(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(
        monkeypatch, objective="reach_cerulean", room=61
    )
    monkeypatch.setattr(
        p, "story_battle_binding", lambda *a, **k: calls.append(("battle", k)) or binding
    )
    row = p.cerulean_arrival_story_option(rt, N(), route=route, battler=actor, combat_levels=(16,))
    assert row[0].story_objective_ref == "reach_cerulean" and row[1].opposition_known
    kwargs = calls[-1][1]
    assert kwargs["battler"] is actor and kwargs["scripted_fossil_guard"] is True
    assert kwargs["completes_objective"] is False
    assert not any(name == "fossil_pickup_binding" for name, _ in calls)


def test_cerulean_arrival_after_guard_reuses_pickup_not_a_battle(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(
        monkeypatch, objective="reach_cerulean", room=61,
        flags=(int(p.EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD),)
    )
    monkeypatch.setattr(p, "fossil_pickup_binding", lambda *a, **k: binding)
    row = p.cerulean_arrival_story_option(rt, N(), route=route, battler=actor, combat_levels=(16,))
    assert row[0].story_objective_ref == "reach_cerulean" and not row[1].opposition_known
    assert not any(name == "story_battle_binding" for name, _ in calls)


def test_cut_native_rival_keeps_actual_actor_and_exact_preview(monkeypatch):
    rt, route, actor, binding, _, _ = fixture(monkeypatch, room=int(p.MapId.SS_ANNE_2F))
    captured = []
    monkeypatch.setattr(p, "scripted_rival_binding", lambda *a, **k: captured.append(k) or binding)
    row = p.cut_story_option(rt, N(), route=route, battler=actor, combat_levels=(17,))
    assert row[0].story_objective_ref == "obtain_cut"
    assert row[1].opposition_known and row[1].maximum_level_deficit == 0.03
    assert captured[0]["battler"] is actor and captured[0]["objective_id"] == "obtain_cut"
    assert captured[0]["already_defeated"]() is False


def test_captain_reward_does_not_retrigger_ship_rival(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(
        monkeypatch, room=int(p.MapId.SS_ANNE_CAPTAINS_ROOM), script=4
    )
    monkeypatch.setattr(p, "captain_interaction_binding", lambda *a, **k: binding)
    row = p.cut_story_option(rt, N(), route=route, battler=actor, combat_levels=(20,))
    assert row[0].story_objective_ref == "obtain_cut" and not row[1].combat_required
    assert calls == []


def test_bill_departure_quotes_observed_exit_before_future_police_permission(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(monkeypatch, room=int(p.MapId.BILLS_HOUSE))

    def travel(*a, **k):
        calls.append(("travel", k))
        return binding

    monkeypatch.setattr(p, "story_travel_binding", travel)
    row = p.cut_story_option(rt, N(), route=route, battler=actor, combat_levels=(20,))
    assert row[0].story_objective_ref == "obtain_cut"
    assert calls[0][1]["intermediate_map"] == int(p.MapId.ROUTE_25)
    assert calls[0][1]["frontier"] is False


@pytest.mark.parametrize("fault", [None, "objective", "map", "missing", "zero", "boolean"])
def test_only_ticketed_vermilion_cut_uses_bounded_boarding_route(monkeypatch, fault):
    from test_red_training_ground_route import _world

    objective = "reach_celadon" if fault == "objective" else "obtain_cut"
    room = int(p.MapId.CERULEAN_CITY) if fault == "map" else int(p.MapId.VERMILION_CITY)
    rt, _, actor, binding, calls, raw = fixture(
        monkeypatch, objective=objective, room=room,
    )
    quantity = {"zero": 0, "boolean": True}.get(fault, 1)
    raw.bag_items = None if fault == "missing" else ((int(p.ItemId.SS_TICKET), quantity),)
    route = p.RedVermilionGroundTransition(
        b"fixture", _world(), allow_wild_faints=True, allow_field_faint_dialogue=True,
    )

    def travel(*args, **kwargs):
        calls.append(("travel", kwargs))
        return binding

    monkeypatch.setattr(p, "story_travel_binding", travel)
    row = p.early_story_travel_option(
        rt, N(), objective_id=objective, route=route, battler=actor,
    )
    assert row[0].story_objective_ref == objective
    assert row[1].combat_required is False
    passed = calls[0][1]
    if fault is None:
        assert passed["certify_cash_approach"] is False
        assert passed["route"].maximum_scripted_dialogues == 1
        assert not passed["route"].allow_wild_faints
        assert not passed["route"].allow_field_faint_dialogue
        assert not passed["route"].require_cash_safe
        assert passed["route"].route_world is route.route_world
    else:
        assert "certify_cash_approach" not in passed
        assert passed["route"] is route
    assert route.maximum_scripted_dialogues == 0
    assert route.allow_wild_faints and route.allow_field_faint_dialogue
    assert not any(name in {"battle", "captain_interaction_binding"} for name, _ in calls)


def test_ticketed_boarding_does_not_change_an_unknown_route_type(monkeypatch):
    rt, route, actor, binding, calls, raw = fixture(
        monkeypatch, room=int(p.MapId.VERMILION_CITY),
    )
    raw.bag_items = ((int(p.ItemId.SS_TICKET), 1),)
    monkeypatch.setattr(
        p, "story_travel_binding", lambda *a, **k: calls.append(("travel", k)) or binding,
    )
    assert p.early_story_travel_option(
        rt, N(), objective_id="obtain_cut", route=route, battler=actor,
    ) is not None
    assert calls[0][1]["route"] is route
    assert "certify_cash_approach" not in calls[0][1]


def test_bill_reuses_independent_existing_branch_not_misty_order(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(monkeypatch, objective="help_bill")
    challenge = p.OptionChallenge(False, False, 0.0, 0.0, 0.0)
    monkeypatch.setattr(
        p,
        "cerulean_story_options",
        lambda *a, **k: (
            N(
                objective_id="defeat_misty",
                binding=replace(binding, binding_ref="misty"),
                challenge=challenge,
            ),
            N(objective_id="help_bill", binding=binding, challenge=challenge),
        ),
    )
    assert p.bill_story_option(rt, N(), route=route, battler=actor, combat_levels=(17,)) == (
        binding,
        challenge,
    )
    assert calls == []


def test_hideout_quotes_all_executable_guards_then_nearest_not_fixed_order(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(
        monkeypatch, objective="clear_rocket_hideout", room=202
    )
    monkeypatch.setattr(
        p.StoryTrainerContract,
        "from_cartridge",
        lambda *a, **k: N(trainer_identity=(230, 30, 1), defeated_event=k["defeated_event"]),
    )
    seen = []

    def battle(*a, **k):
        event = getattr(k["contract"], "defeated_event", 1703)
        seen.append(event)
        return replace(
            binding,
            binding_ref=str(event),
            estimated_effort={1700: 0.4, 1698: 0.3, 1699: 0.1, 1703: 0.5}[event],
        )

    monkeypatch.setattr(p, "story_battle_binding", battle)
    row = p.hideout_story_option(
        rt,
        N(),
        objective_id="clear_rocket_hideout",
        route=route,
        battler=actor,
        combat_levels=(22,),
    )
    assert set(seen) == {1700, 1698, 1699, 1703}
    assert row[0].binding_ref == "1699" and row[1].opposition_known


def test_scope_reward_goal_cannot_advertise_a_new_giovanni_fight(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(
        monkeypatch, objective="obtain_silph_scope", room=202
    )
    monkeypatch.setattr(p, "hideout_interaction_binding", lambda *a, **k: binding)
    row = p.hideout_story_option(
        rt, N(), objective_id="obtain_silph_scope", route=route, battler=actor, combat_levels=(22,)
    )
    assert row[0].story_objective_ref == "obtain_silph_scope" and not row[1].combat_required
    assert calls == []
    with pytest.raises(ValueError, match="own graph"):
        p.hideout_story_option(
            rt, N(), objective_id="help_bill", route=route, battler=actor, combat_levels=()
        )


def test_fuji_gift_is_native_phase_not_automatic_tower_return(monkeypatch):
    rt, route, actor, binding, calls, _ = fixture(monkeypatch, objective="rescue_fuji", room=149)
    monkeypatch.setattr(p, "fuji_binding", lambda *a, **k: binding)
    row = p.fuji_story_option(rt, N(), route=route, battler=actor, combat_levels=(30,))
    assert row[0].story_objective_ref == "rescue_fuji" and not row[1].combat_required
    assert calls == []


@pytest.mark.parametrize("separate_trainer", [False, True])
def test_ghost_uses_existing_exact_actor_and_stays_combat_unknown(monkeypatch, separate_trainer):
    rt, route, actor, binding, calls, _ = fixture(monkeypatch, objective="rescue_fuji", room=147)
    monkeypatch.setattr(p, "marowak_pending", lambda _: True)
    captured = []
    monkeypatch.setattr(
        p, "marowak_binding", lambda *a, **k: captured.append(k["battler"]) or binding
    )
    row = p.fuji_story_option(rt, N(), route=route, battler=actor, combat_levels=(30,),
                             trainer_battler=N() if separate_trainer else None)
    assert captured == [actor] and row[1].combat_required and not row[1].opposition_known


@pytest.mark.parametrize("separate_trainer", [False, True])
@pytest.mark.parametrize("room", [143, 147, 148])
def test_fuji_ordinary_trainers_use_explicit_actor_without_replacing_wild(
    monkeypatch, separate_trainer, room
):
    rt, route, actor, binding, calls, _ = fixture(monkeypatch, objective="rescue_fuji", room=room)
    trainer = N() if separate_trainer else None
    expected = actor if trainer is None else trainer
    captured = []
    def battle(*args, **kwargs):
        captured.append(kwargs["battler"])
        return binding
    if room == 143:
        monkeypatch.setattr(p, "scripted_rival_binding", battle)
    elif room == 147:
        monkeypatch.setattr(p, "marowak_pending", lambda _: True)
        monkeypatch.setattr(p, "obstructing_story_battle_binding", battle)
    else:
        monkeypatch.setattr(p, "map_object_events", lambda *a: (N(object_index=4, y=2, x=3),))
        monkeypatch.setattr(p, "StoryTrainerContract", N(from_cartridge=lambda *a, **k:
            N(trainer_identity=(242, 42, 1))))
        monkeypatch.setattr(p, "story_battle_binding", battle)
    row = p.fuji_story_option(rt, N(), route=route, battler=actor, combat_levels=(30,),
                             trainer_battler=trainer)
    assert row is not None and row[0].story_objective_ref == "rescue_fuji"
    assert captured and all(candidate is expected for candidate in captured)
    if room == 147:
        ghost = next(kwargs for name, kwargs in calls if name == "marowak_binding")
        assert ghost["battler"] is actor


def test_saffron_gate_purchase_only_when_access_closed(monkeypatch):
    rt, route, actor, binding, calls, raw = fixture(
        monkeypatch, objective="reach_saffron", room=133
    )
    monkeypatch.setattr(p, "saffron_access_binding", lambda *a, **k: binding)
    assert (
        p.saffron_story_option(rt, N(), route=route, battler=actor)[0].story_objective_ref
        == "reach_saffron"
    )
    raw.status_flags_1 = p.SAFFRON_GUARD_ACCESS_MASK
    assert p.saffron_story_option(rt, N(), route=route, battler=actor) is None
    assert [name for name, _ in calls] == [
        "story_travel_binding",
        "obstructing_story_battle_binding",
    ]
