from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_static_approach as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "event",
        "endpoint",
        "cash",
        "bag",
        "party",
        "badge",
        "route_error",
        "unavailable",
        "consumed",
        "frontier",
        "frontier_blocked",
        "frontier_unavailable",
    ],
)
@pytest.mark.parametrize("descriptor", [False, True])
@pytest.mark.parametrize("continuous", [False, True])
def test_observed_map_boundary_never_activates_oneoff(
    monkeypatch, fault, descriptor, continuous,
):
    raw = N(
        map_id=182,
        player_y=3,
        player_x=3,
        player_money=4000,
        bag_items=((73, 1),),
        party_species_ids=(1,),
        event_flags=b"flags",
        badge_bits=15,
    )
    em = N(frame_count=0, state=b"source")
    em.save_state_bytes = lambda: em.state
    actions = N(actions_executed=0)
    rt = N(
        reader=N(read=lambda: N(**vars(raw))),
        emulator=em,
        adapter=N(
            observe=lambda: N(game_state=None),
            graph=N(
                available_objectives=lambda _: (
                    () if fault == "unavailable" else (N(id="reach_fuchsia"),)
                )
            ),
        ),
    )
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_origin", lambda *a: None)
    monkeypatch.setattr(
        s, "observe_static_capture", lambda *a: N(registered=False, consumed=fault == "consumed")
    )

    def frontier(*args):
        if fault == "frontier_unavailable":
            raise s.RoutePlanningError("gate remains closed")
        return 10, (18, 1)

    monkeypatch.setattr(s, "story_frontier_target", frontier)

    @dataclass
    class Route:
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        @property
        def route_world(self):
            def plan(*a, **k):
                if str(fault).startswith("frontier") and (
                    a[1] == 23 or fault == "frontier_blocked"
                ):
                    raise s.RoutePlanningError("future NPC or actual trainer blocks route")
                return N(
                    cost=100, terminal_at=(61, 10), steps=(N(expected_map=10, expected_at=(18, 1)),),
                    segments=(N(target_map=10, transition=N(arrival_at=(18, 1))),),
                )

            return N(plan_feasible_to_map=plan)

        def __call__(self, *a):
            if fault == "route_error":
                raise s.RoutePlanningError("observed future obstruction remains")
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            if fault == "event":
                raw.event_flags = b"changed"
            if fault == "endpoint":
                raw.player_y += 1
            if fault == "cash":
                raw.player_money += 1
            if fault == "bag":
                raw.bag_items = ()
            if fault == "party":
                raw.party_species_ids = (2,)
            if fault == "badge":
                raw.badge_bits = 31
            actions.actions_executed += 1
            em.frame_count += 16
            em.state = b"terminal"

    function = s.static_approach_option if descriptor else s.static_approach_binding
    row = function(
        rt,
        actions,
        route=Route(),
        target=N(map_id=23, at=(62, 10)),
        objective_id="reach_fuchsia",
        battler=None,
        continuous_travel=continuous,
        **({"combat_levels": (44, 31)} if descriptor else {}),
    )
    binding = row[0] if descriptor and row is not None else row
    if descriptor and row is not None:
        assert not row[1].combat_required and not row[1].opposition_known
        assert binding.story_objective_ref == "reach_fuchsia"
    assert actions.actions_executed == 0
    if fault in {"unavailable", "consumed", "frontier_blocked", "frontier_unavailable"}:
        assert binding is None
    elif fault == "route_error":
        with pytest.raises(s.RoutePlanningError, match="future obstruction"):
            binding.execute()
        assert em.state == b"source" and actions.actions_executed == 0
    elif fault in {"event", "endpoint", "cash", "bag", "party", "badge"}:
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        # A future map's trainer sight is not observed yet. Even a continuous
        # request returns at the first boundary so the next menu can quote it.
        full_target = False
        assert raw.map_id == (23 if full_target else 10)
        assert not report.evidence["activated"]
        assert report.evidence["complete_target_approach"] is full_target
        assert report.evidence["continuous_travel_requested"] is continuous
        assert not report.evidence["objective_completed"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        with pytest.raises(ValueError):
            binding.execute()


@pytest.mark.parametrize("continuous", [False, True])
@pytest.mark.parametrize("leaves_current_map", [False, True])
def test_static_complete_approach_requires_one_observed_map(
    monkeypatch, continuous, leaves_current_map,
):
    """Also stop a same-map destination whose proposed detour visits another map."""
    raw = N(map_id=23, player_y=20, player_x=10, player_money=4000,
            bag_items=((73, 1),), party_species_ids=(1,), event_flags=b"flags",
            badge_bits=15)
    emulator = N(frame_count=0, state=b"source")
    emulator.save_state_bytes = lambda: emulator.state
    actions = N(actions_executed=0)
    runtime = N(reader=N(read=lambda: N(**vars(raw))), emulator=emulator,
                adapter=N(observe=lambda: N(game_state=None), graph=N(
                    available_objectives=lambda _: (N(id="reach_fuchsia"),))))
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_origin", lambda *_: None)
    monkeypatch.setattr(s, "observe_static_capture", lambda *_: N(
        registered=False, consumed=False))
    steps = ((N(expected_map=8, expected_at=(0, 5)),
              N(expected_map=23, expected_at=(61, 10))) if leaves_current_map
             else (N(expected_map=23, expected_at=(61, 10)),))

    @dataclass
    class Route:
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *_a, **_k: N(
                cost=100, terminal_at=(61, 10), steps=steps,
                segments=(N(target_map=8, transition=N(arrival_at=(0, 5))),
                          N(target_map=23, transition=N(arrival_at=(61, 10))))
                         if leaves_current_map else ()))

        def __call__(self, *_):
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            emulator.state = b"terminal"
            actions.actions_executed += 1
            emulator.frame_count += 16

    binding = s.static_approach_binding(runtime, actions, route=Route(),
        target=N(map_id=23, at=(62, 10)), objective_id="reach_fuchsia", battler=None,
        continuous_travel=continuous)
    assert actions.actions_executed == 0
    report = binding.execute()
    assert (raw.map_id, raw.player_y, raw.player_x) == (
        (8, 0, 5) if leaves_current_map else (23, 61, 10))
    assert report.evidence["complete_target_approach"] is (
        continuous and not leaves_current_map)
    assert not report.evidence["activated"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize("levels", [None, [], (), (True,), (0,), (101,), (3.5,)])
def test_static_challenge_requires_actual_role_levels(levels):
    with pytest.raises(ValueError, match="combat-role levels"):
        s.static_approach_option(None, None, route=None, target=None,
                                objective_id="reach_fuchsia", battler=None,
                                combat_levels=levels)


@pytest.mark.parametrize("scope", [None, 0, 1, "true", [], {}])
@pytest.mark.parametrize("descriptor", [False, True])
def test_static_travel_scope_requires_a_boolean(scope, descriptor):
    function = s.static_approach_option if descriptor else s.static_approach_binding
    with pytest.raises(TypeError, match="travel scope"):
        function(None, None, route=None, target=None, objective_id="reach_fuchsia",
                 battler=None, continuous_travel=scope,
                 **({"combat_levels": (40,)} if descriptor else {}))


@pytest.mark.parametrize("continuous", [False, True])
def test_already_adjacent_static_target_is_not_activated(monkeypatch, continuous):
    raw = N(map_id=23, player_y=61, player_x=10)
    rt = N(reader=N(read=lambda: raw), adapter=N(
        observe=lambda: N(game_state=None), graph=N(
            available_objectives=lambda _: (N(id="reach_fuchsia"),))))
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "observe_static_capture", lambda *_: N(
        registered=False, consumed=False))
    monkeypatch.setattr(s, "_origin", lambda *_: pytest.fail("no approach at adjacent tile"))
    assert s.static_approach_binding(rt, None, route=None,
        target=N(map_id=23, at=(62, 10)), objective_id="reach_fuchsia", battler=None,
        continuous_travel=continuous) is None


def test_static_obstruction_quotes_the_actual_trainer_not_the_static_pokemon(monkeypatch):
    from test_red_live_option_menu import _binding

    from pokemon_red_completion.goal_manager import GoalKind

    raw = N(map_id=23, player_y=0, player_x=8)
    rt = N(reader=N(read=lambda: raw, read_current_map_objects=lambda: ()),
           adapter=N(observe=lambda: N(game_state=None),
                     graph=N(available_objectives=lambda _: (N(id="reach_fuchsia"),))))
    target = N(map_id=23, at=(62, 10), level=30)
    trainer = N(trainer_class=202, trainer_set=3, event_flag=243)
    contract = object()
    binding = _binding(GoalKind.ADVANCE_STORY, binding_ref="trainer", calls=[])
    calls = []

    def blocked(*_, **__):
        raise s.RoutePlanningError("real trainer sight")

    def battle(*args, **kwargs):
        calls.append(kwargs)
        return binding

    def quote(rom, trainer_class, trainer_set):
        assert (rom, trainer_class, trainer_set) == (b"rom", 202, 3)
        return N(party=(N(level=20), N(level=21)))

    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_origin", lambda *_: object())
    monkeypatch.setattr(s, "observe_static_capture", lambda *_: N(registered=False, consumed=False))
    monkeypatch.setattr(s, "trainer_headers", lambda *_, **__: ())
    monkeypatch.setattr(s, "map_object_events", lambda *_: ())
    monkeypatch.setattr(s, "trainer_sight_zones", lambda *_: ())
    monkeypatch.setattr(s, "blocking_story_trainers", lambda *_, **__: (
        N(trainer=trainer, approach=N(cost=1)),))
    monkeypatch.setattr(s.StoryTrainerContract, "from_cartridge", lambda *_, **__: contract)
    monkeypatch.setattr(s, "story_battle_binding", battle)
    monkeypatch.setattr(s, "trainer_party_quote", quote)
    route = N(rom=b"rom", route_world=N(plan_feasible_to_map=blocked))
    result, challenge = s.static_approach_option(rt, object(), route=route, target=target,
        objective_id="reach_fuchsia", battler=object(), combat_levels=(44, 31))
    assert result is binding and calls[0]["contract"] is contract
    assert calls[0]["completes_objective"] is False
    assert challenge.combat_required and challenge.opposition_known
    assert challenge.opponent_fraction == 2 / 6
    assert challenge.maximum_level_deficit == pytest.approx(-.165)
    assert challenge.median_level_deficit == pytest.approx(-.17)
    assert "trainer" not in str(challenge.public_dict())
