from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_gym as s
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalVerification
from pokemon_red_completion.red_gym_reward import KOGA_REWARD


@pytest.mark.parametrize("full", [False, True])
def test_pending_reward_finishes_native_tm_without_replaying_battle(monkeypatch, full):
    from pokemon_red_completion import red_gym_reward as gym
    from pokemon_red_completion.observation import ItemId

    reward = gym.GIOVANNI_REWARD
    events = bytearray(256)
    events[reward.defeated_event // 8] |= 1 << (reward.defeated_event % 8)
    bag = {i: 1 for i in range(19)} if full else {3: 8}
    if full:
        bag[int(ItemId.CARD_KEY)] = 1
    raw = N(
        map_id=reward.map_id,
        player_y=2,
        player_x=2,
        battle_state=0,
        event_flags=bytes(events),
        badge_bits=255,
        bag_items=tuple(bag.items()),
        player_money=20747,
    )
    actions, emulator = N(actions_executed=0), N(frame_count=0, pressed_buttons=frozenset())
    emulator.save_state_bytes = lambda: str(actions.actions_executed).encode()
    reader = N(
        read=lambda: raw,
        read_input_readiness=lambda: N(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    runtime = N(reader=reader, emulator=emulator)
    calls = []

    def spend(name):
        calls.append(name)
        actions.actions_executed += 1
        emulator.frame_count += 12

    dialogue = [True]
    reader.read_bottom_dialogue_box_visible = lambda: dialogue[0]
    monkeypatch.setattr(s, "_field_ready", lambda _: not dialogue[0])

    def button(action):
        if action.kind is s.MacroActionKind.CANCEL:
            dialogue[0] = False
            spend("cancel")
        else:
            spend("wait")

    actions.execute = button
    monkeypatch.setattr(s, "map_object_events", lambda *_: (N(object_index=1, y=2, x=3),))
    monkeypatch.setattr(s, "_face_trainer_boundary", lambda *args: spend("face"))
    monkeypatch.setattr(s, "replace", lambda route, **kw: lambda *_: spend("return"))

    def store():
        spend("storage")
        bag.pop(int(ItemId.CARD_KEY))
        raw.bag_items = tuple(bag.items())
        return N(evidence={"stored_items": [int(ItemId.CARD_KEY)]})

    monkeypatch.setattr(
        s,
        "completed_key_storage_binding",
        lambda *a, **kw: N(
            execute=store,
            verify=lambda _: GoalVerification.succeeded(),
        ),
    )

    def interact(*_):
        spend("reward")
        bag[reward.item] = 1
        raw.bag_items = tuple(bag.items())
        events[reward.reward_event // 8] |= 1 << (reward.reward_event % 8)
        raw.event_flags = bytes(events)

    monkeypatch.setattr(gym.silph, "_interact", interact)
    binding = s.pending_gym_reward_binding(runtime, actions, route=N(rom=b"rom"))
    assert binding.kind is GoalKind.RECOVER_CONTROL and not calls
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert report.evidence["new_battles"] == report.evidence["sales"] == 0
    assert report.evidence["model_queries"] == 0
    assert raw.player_money == 20747 and reward.received(raw)
    assert calls == (
        ["cancel", "wait", "storage", "return", "face", "reward"]
        if full
        else ["cancel", "wait", "face", "reward"]
    )
    assert report.actions_executed == len(calls)
    with pytest.raises(ValueError, match="stale or consumed"):
        binding.execute()
    assert s.pending_gym_reward_binding(runtime, actions, route=N(rom=b"rom")) is None


@pytest.mark.parametrize("phase", ["travel", "leader", "obstruction", "completed", "unready"])
def test_gym_composes_existing_binding_and_honest_component_preview(monkeypatch, phase):
    raw = N(map_id=157 if phase in {"leader", "obstruction"} else 154, bag_items=())
    rt = N(
        reader=N(read=lambda: raw),
        emulator=object(),
        adapter=N(
            observe=lambda: N(game_state=object()),
            graph=N(
                available_objectives=lambda _: (
                    () if phase == "completed" else (N(id="defeat_koga"),)
                )
            ),
        ),
    )
    binding = ExecutableGoalBinding(
        "test",
        GoalKind.ADVANCE_STORY,
        0.1,
        0.1,
        lambda: pytest.fail("inventory executed game input"),
        lambda _: GoalVerification.succeeded(),
    )
    monkeypatch.setattr(s, "_field_ready", lambda _: phase != "unready")
    monkeypatch.setattr(s.GymReward, "contract", lambda *args: object())
    monkeypatch.setattr(
        s, "story_battle_binding", lambda *a, **kw: binding if phase == "leader" else None
    )
    monkeypatch.setattr(s, "story_travel_binding", lambda *a, **kw: binding)
    monkeypatch.setattr(s, "obstructing_story_battle_binding", lambda *a, **kw: binding)
    monkeypatch.setattr(s, "map_object_events", lambda *a: (N(object_index=1, y=10, x=4),))
    monkeypatch.setattr(
        s,
        "observe_preparation_members",
        lambda *a: (
            N(purpose=s.PreparationPurpose.COMBAT, observation=N(level=29)),
            N(purpose=s.PreparationPurpose.FIELD_UTILITY, observation=N(level=19)),
        ),
    )
    monkeypatch.setattr(
        s, "trainer_party_quote", lambda *a: N(party=tuple(N(level=n) for n in (37, 39, 37, 43)))
    )
    row = s.gym_story_option(
        rt,
        object(),
        reward=KOGA_REWARD,
        route=N(rom=b"rom"),
        battler=object(),
        preparation_plan=object(),
    )
    if phase in {"completed", "unready"}:
        assert row is None
    else:
        selected, challenge = row
        assert selected.execute is binding.execute and selected.story_objective_ref == "defeat_koga"
        assert challenge.combat_required == (phase != "travel")
        assert challenge.opposition_known == (phase == "leader")
        if phase == "leader":
            assert challenge.maximum_level_deficit == 0.14
            assert challenge.median_level_deficit == 0.09


def test_koga_travel_is_supported_but_does_not_award_badge(monkeypatch):
    from test_red_player_story_travel import setup

    from pokemon_red_completion import red_player_story_travel as travel

    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="defeat_koga", completion_facts=frozenset({"badge:soul"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    binding = travel.story_travel_binding(rt, actions, objective_id="defeat_koga", route=route)
    assert actions.actions_executed == 0
    report = binding.execute()
    assert raw.map_id == 157 and raw.badge_bits == 0
    assert not report.evidence["objective_completed"]
    assert "defeat_koga" not in lesson["completed_objectives"]


@pytest.mark.parametrize("continuous", [False, True])
@pytest.mark.parametrize("surf", [False, True])
@pytest.mark.parametrize("mansion", [None, "POKEMON_MANSION_1F", "POKEMON_MANSION_2F",
                                    "POKEMON_MANSION_3F", "POKEMON_MANSION_B1F"])
def test_continuous_gym_route_retains_selected_destination_not_border_choice(
    monkeypatch, continuous, surf, mansion
):
    rt = N(
        reader=N(read=lambda: N(map_id=154 if mansion is None else int(getattr(s.MapId, mansion)),
                               bag_items=())),
        adapter=N(
            observe=lambda: N(game_state=object()),
            graph=N(available_objectives=lambda _: (N(id="defeat_koga"),)),
        ),
    )
    binding = ExecutableGoalBinding(
        "travel",
        GoalKind.ADVANCE_STORY,
        0.1,
        0.1,
        lambda: pytest.fail("enumeration made an input"),
        lambda _: GoalVerification.succeeded(),
    )
    quotes = []
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "story_travel_binding", lambda *a, **kw: quotes.append(kw) or binding)
    row = s.gym_story_option(
        rt,
        object(),
        reward=KOGA_REWARD,
        route=N(rom=b"rom", allow_surf=surf),
        battler=object(),
        preparation_plan=object(),
        continuous_travel=continuous,
        allow_surf=surf,
    )
    assert quotes[0]["objective_id"] == "defeat_koga"
    assert quotes[0]["frontier"] is (not continuous or mansion is not None)
    assert quotes[0]["stop_at_map_boundary"] is (not continuous or mansion is not None)
    assert quotes[0]["allow_surf"] is surf
    assert row[0].execute is binding.execute and row[0].story_objective_ref == "defeat_koga"
    assert not row[1].combat_required and not row[1].opposition_known


@pytest.mark.parametrize("continuous", [False, True])
@pytest.mark.parametrize("frontier_available", [False, True])
def test_unavailable_complete_gym_route_reuses_real_frontier_before_obstruction(
    monkeypatch, continuous, frontier_available
):
    rt = N(reader=N(read=lambda: N(map_id=int(s.MapId.FUCHSIA_POKECENTER),bag_items=())),
        adapter=N(observe=lambda: N(game_state=object()),
            graph=N(available_objectives=lambda _: (N(id="defeat_giovanni"),))))
    binding = ExecutableGoalBinding("real-frontier",GoalKind.ADVANCE_STORY,0.1,0.1,
        lambda: pytest.fail("quotation cannot move the player"),
        lambda _: GoalVerification.succeeded())
    quotes,obstructions = [],[]

    def quote(*args,**kwargs):
        quotes.append(kwargs)
        return binding if kwargs['frontier'] and frontier_available else None

    monkeypatch.setattr(s,"_field_ready",lambda _: True)
    monkeypatch.setattr(s,"story_travel_binding",quote)
    monkeypatch.setattr(s,"obstructing_story_battle_binding",
                        lambda *a,**kw: obstructions.append(kw) or None)
    row = s.gym_story_option(rt,object(),reward=s.GIOVANNI_REWARD,
        route=N(rom=b"rom",allow_surf=True),battler=object(),preparation_plan=object(),
        continuous_travel=continuous,allow_surf=True)
    assert [q['frontier'] for q in quotes] == ([False,True] if continuous else [True])
    assert all(q['objective_id']=="defeat_giovanni" and q['allow_surf'] for q in quotes)
    assert all(q['stop_at_map_boundary'] is q['frontier'] for q in quotes)
    assert bool(obstructions) is (not frontier_available)
    if frontier_available:
        assert row[0].execute is binding.execute and row[0].story_objective_ref=="defeat_giovanni"
        assert not row[1].combat_required and not row[1].opposition_known
    else:
        assert row is None


@pytest.mark.parametrize("invalid", [None, 1, "yes", ()])
def test_continuous_travel_refuses_untyped_scope_before_observation(invalid):
    with pytest.raises(TypeError, match="continuous gym travel"):
        s.gym_story_option(
            object(),
            object(),
            reward=KOGA_REWARD,
            route=object(),
            battler=object(),
            preparation_plan=object(),
            continuous_travel=invalid,
        )


@pytest.mark.parametrize("invalid", [None, 1, "yes", ()])
def test_gym_surf_scope_requires_explicit_boolean(invalid):
    with pytest.raises(TypeError, match="gym Surf"):
        s.gym_story_option(
            None,
            None,
            reward=KOGA_REWARD,
            route=None,
            battler=None,
            preparation_plan=None,
            allow_surf=invalid,
        )


def test_gym_surf_scope_refuses_mismatched_executor_before_input():
    with pytest.raises(ValueError, match="Surf-enabled"):
        s.gym_story_option(
            None,
            None,
            reward=KOGA_REWARD,
            route=N(allow_surf=False),
            battler=None,
            preparation_plan=None,
            allow_surf=True,
        )


@pytest.mark.parametrize("leader", [False, True])
def test_obstruction_resolver_is_separate_from_the_leader_actor(monkeypatch, leader):
    raw = N(map_id=KOGA_REWARD.map_id, bag_items=())
    rt = N(
        reader=N(read=lambda: raw),
        adapter=N(
            observe=lambda: N(game_state=None),
            graph=N(available_objectives=lambda _: (N(id="defeat_koga"),)),
        ),
        emulator=None,
    )
    actor, contract = object(), object()

    def resolver(_):
        pytest.fail("gym must pass the resolver, not call it itself")

    binding = ExecutableGoalBinding(
        "binding",
        GoalKind.ADVANCE_STORY,
        0.1,
        0.1,
        lambda: pytest.fail("quote executed"),
        lambda _: GoalVerification.succeeded(),
    )
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s.GymReward, "contract", lambda *a: contract)
    monkeypatch.setattr(s, "map_object_events", lambda *a: (N(object_index=1, y=10, x=4),))
    monkeypatch.setattr(
        s,
        "observe_preparation_members",
        lambda *a: (N(purpose=s.PreparationPurpose.COMBAT, observation=N(level=34)),),
    )
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(party=(N(level=38),)))

    def leader_quote(*a, **kw):
        assert kw["battler"] is actor and kw["contract"] is contract
        assert "trainer_battler_for_contract" not in kw
        return binding if leader else None

    def obstruction(*a, **kw):
        assert kw["battler"] is actor and kw["trainer_battler_for_contract"] is resolver
        return binding

    monkeypatch.setattr(s, "story_battle_binding", leader_quote)
    monkeypatch.setattr(s, "obstructing_story_battle_binding", obstruction)
    row = s.gym_story_option(
        rt,
        None,
        reward=KOGA_REWARD,
        route=N(rom=b"rom"),
        battler=actor,
        preparation_plan=None,
        trainer_battler_for_contract=resolver,
    )
    assert row[0].execute is binding.execute and row[1].opposition_known is leader
