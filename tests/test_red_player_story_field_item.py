from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_field_item as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.route_plan import RoutePlanningError


def setup(monkeypatch):
    key, objective_id = int(ItemId.SECRET_KEY), "obtain_secret_key"
    raw = N(
        map_id=int(MapId.POKEMON_MANSION_B1F),
        bag_items=((4, 5),),
        player_money=14409,
        badge_bits=63,
        party_species_ids=(28,),
        party_hp=(100,),
        facts=frozenset(),
        ready=True,
    )
    state = N(
        payload=b"source",
        present=True,
        visible=True,
        moving=False,
        blocked=False,
        pickup_failure=False,
        gain_cash=False,
        lose_item=False,
        latched=False,
        target_count=1,
        target_map=raw.map_id,
    )
    target = s.RedFieldItem(key, raw.map_id, 8, 61, (13, 5))
    objective = N(id=objective_id, completion_facts=frozenset({"item:secret_key"}))
    calls, travel_calls = [], []

    @dataclass
    class World:
        def with_current_observation(self, reader):
            return self

        def plan_feasible_to_map(self, start, map_id, *, goal_at):
            if state.blocked:
                raise RoutePlanningError("closed native door")
            return N(cost=1, terminal_at=goal_at)

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = raw.map_id
        destination_at: tuple = (0, 0)

        def __call__(self, actions, reader, emulator):
            calls.append(self.destination_at)
            state.visible = True
            state.payload = b"approached"
            actions.actions_executed += 1
            emulator.frame_count += 10

    rt = N(
        reader=N(
            read=lambda: N(**vars(raw)),
            read_current_map_objects=lambda: (
                [
                    N(
                        sprite_index=8,
                        visible=state.visible,
                        moving=state.moving,
                        picture_id=61,
                        at=target.at,
                    )
                ]
                if state.present
                else []
            ),
        ),
        emulator=N(frame_count=0, save_state_bytes=lambda: state.payload),
        adapter=N(
            graph=N(objective=lambda _: objective, available_objectives=lambda _: (objective,))
        ),
        observer=N(latch_verified_facts=lambda facts: setattr(state, "latched", True)),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: raw.ready)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (
            N(raw=N(**vars(raw)), game_state=object()),
            {
                "completed_objectives": ["reach_cinnabar"]
                + ([objective_id] if state.latched else [])
            },
        ),
    )
    monkeypatch.setattr(
        s,
        "red_field_items",
        lambda *a: tuple(
            s.RedFieldItem(key, state.target_map, 8, 61, target.at)
            for _ in range(state.target_count)
        ),
    )
    monkeypatch.setattr(
        s,
        "Gen1TraversalObserver",
        lambda *a, **k: N(observe=lambda: N(map_id=raw.map_id, at=(14, 5))),
    )
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(s, "semantic_facts", lambda r: r.facts)
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)
    monkeypatch.setattr(s, "settle_story_interaction", lambda *a: None)

    def collect(actions, reader, observed):
        assert observed == target and len(calls) == 1
        if state.pickup_failure:
            raise RuntimeError("native pickup failed")
        expected = dict(raw.bag_items)
        expected[key] = 1
        if state.lose_item:
            del expected[4]
        raw.bag_items = tuple(expected.items())
        raw.facts = objective.completion_facts
        raw.player_money += int(state.gain_cash)
        state.present = False
        state.payload = b"collected"
        actions.actions_executed += 1
        rt.emulator.frame_count += 10

    monkeypatch.setattr(s, "collect_visible_field_item", collect)

    def travel(*args, **kwargs):
        travel_calls.append(kwargs)
        return N(story_objective_ref=objective_id)

    monkeypatch.setattr(s, "story_travel_binding", travel)
    return rt, actions, Route(World()), raw, state, calls, travel_calls


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "unready",
        "unavailable",
        "unknown_bag",
        "full_bag",
        "owned",
        "unknown_cash",
        "empty_party",
        "fainted_party",
        "absent",
        "invisible",
        "moving",
        "blocked",
    ],
)
def test_observed_story_item_requires_legality_capacity_and_live_path(monkeypatch, fault):
    rt, actions, route, raw, state, calls, travel_calls = setup(monkeypatch)
    if fault == "unready":
        raw.ready = False
    if fault == "unavailable":
        rt.adapter.graph.available_objectives = lambda _: ()
    if fault == "unknown_bag":
        raw.bag_items = None
    if fault == "full_bag":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    if fault == "owned":
        raw.bag_items = ((int(ItemId.SECRET_KEY), 1),)
    if fault == "unknown_cash":
        raw.player_money = None
    if fault == "empty_party":
        raw.party_species_ids = ()
    if fault == "fainted_party":
        raw.party_hp = (0,)
    if fault == "absent":
        state.present = False
    if fault == "invisible":
        state.visible = False
    if fault == "moving":
        state.moving = True
    if fault == "blocked":
        state.blocked = True
    row = s.field_item_story_option(
        rt, actions, route=route, objective_id="obtain_secret_key", item_id=int(ItemId.SECRET_KEY)
    )
    assert (row is not None) is (fault in {None, "invisible"})
    assert not calls and not travel_calls and actions.actions_executed == 0
    assert rt.emulator.frame_count == 0 and state.payload == b"source" and not state.latched


@pytest.mark.parametrize(
    "fault", [None, "stale", "pickup_failure", "gain_cash", "lose_item", "changed_terminal"]
)
def test_only_actual_verified_pickup_completes_objective(monkeypatch, fault):
    rt, actions, route, raw, state, calls, _ = setup(monkeypatch)
    binding, challenge = s.field_item_story_option(
        rt, actions, route=route, objective_id="obtain_secret_key", item_id=int(ItemId.SECRET_KEY)
    )
    assert binding.story_objective_ref == "obtain_secret_key" and not challenge.opposition_known
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    if fault == "stale":
        state.payload = b"other"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not calls
        return
    if fault in {"pickup_failure", "gain_cash", "lose_item"}:
        setattr(state, fault, True)
        with pytest.raises(RuntimeError):
            binding.execute()
        assert not state.latched and binding.verify(None).status is GoalDecisionOutcome.FAILED
    else:
        report = binding.execute()
        assert state.latched and report.evidence["objective_completed"]
        assert report.evidence["purchases"] == report.evidence["trainer_battles"] == 0
        assert report.actions_executed == 2 and report.frames_executed == 20
        if fault == "changed_terminal":
            state.payload = b"changed"
        assert binding.verify(report).status is (
            GoalDecisionOutcome.FAILED
            if fault == "changed_terminal"
            else GoalDecisionOutcome.SUCCEEDED
        )
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_off_map_travel_is_reobserved_without_claiming_key(monkeypatch):
    rt, actions, route, raw, state, calls, travel_calls = setup(monkeypatch)
    raw.map_id = int(MapId.CINNABAR_POKECENTER)
    row = s.field_item_story_option(
        rt, actions, route=route, objective_id="obtain_secret_key", item_id=int(ItemId.SECRET_KEY)
    )
    assert row[0].story_objective_ref == "obtain_secret_key"
    assert travel_calls[0]["frontier"] and travel_calls[0]["stop_at_map_boundary"]
    assert not calls and actions.actions_executed == 0 and not state.latched


@pytest.mark.parametrize("bad", [True, 0, 251, "43"])
def test_invalid_item_rejected_without_inputs(monkeypatch, bad):
    rt, actions, route, _, _, calls, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="cartridge item"):
        s.field_item_story_option(
            rt, actions, route=route, objective_id="obtain_secret_key", item_id=bad
        )
    assert not calls and actions.actions_executed == 0


@pytest.mark.parametrize("fault", ["missing", "ambiguous", "wrong_map"])
def test_cartridge_target_must_be_unique_and_match_declared_objective(monkeypatch, fault):
    rt, actions, route, _, state, calls, _ = setup(monkeypatch)
    if fault == "missing":
        state.target_count = 0
    if fault == "ambiguous":
        state.target_count = 2
    if fault == "wrong_map":
        state.target_map = 10
    with pytest.raises(ValueError, match="one matching"):
        s.field_item_story_option(
            rt,
            actions,
            route=route,
            objective_id="obtain_secret_key",
            item_id=int(ItemId.SECRET_KEY),
        )
    assert not calls and actions.actions_executed == 0


@pytest.mark.parametrize(
    "case",
    ["settled", "pending_wild", "trainer", "missing_escape", "unverified", "shifted", "blocked"],
)
def test_pending_wild_settles_before_any_interaction(monkeypatch, case):
    from pokemon_red_completion import red_player_wild_recovery as recovery

    raw = N(map_id=215, player_y=6, player_x=10, battle_state=0)
    calls = []
    state = N(ready=True)
    rt = N(reader=N(read=lambda: N(**vars(raw))))

    def wait(action):
        assert action.kind is s.MacroActionKind.WAIT and action.repeat == 120
        calls.append("wait")
        if case not in {"settled", "shifted", "blocked"}:
            raw.battle_state = 2 if case == "trainer" else 1
            state.ready = False
        if case == "shifted":
            raw.player_x += 1
        if case == "blocked":
            state.ready = False

    def escape():
        calls.append("escape")
        raw.battle_state, state.ready = 0, True
        return N(evidence={"native_escape": True})

    binding = N(
        execute=escape,
        verify=lambda report: N(
            status=GoalDecisionOutcome.FAILED
            if case == "unverified"
            else GoalDecisionOutcome.SUCCEEDED
        ),
    )
    monkeypatch.setattr(
        recovery,
        "interrupted_wild_binding",
        lambda *a, **k: None if case == "missing_escape" else binding,
    )
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    actions = N(execute=wait)
    if case in {"settled", "pending_wild"}:
        result = s.settle_story_interaction(rt, actions)
        assert result == (None if case == "settled" else {"native_escape": True})
    else:
        with pytest.raises(RuntimeError):
            s.settle_story_interaction(rt, actions)
    assert calls[0] == "wait" and all(c in {"wait", "escape"} for c in calls)
