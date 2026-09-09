from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context_profile import _supply_transition_profile
from test_red_goal_skills import _adapter, _raw, _Reader

import pokemon_red_completion.red_trainer_story as story
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import CurrentMapBlocks, MapId
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import bind_cartridge_trainer_story_profile


def test_profile_opt_in_preserves_other_skills_and_reaches_the_real_factory():
    original = _supply_transition_profile()
    changed = bind_cartridge_trainer_story_profile(original)
    assert original.providers[0].parameters == {}
    assert changed.providers[1:] == original.providers[1:]
    assert changed.providers[0].parameters == {"trainer_objective": "defeat_lorelei"}
    assert changed.profile_sha256 != original.profile_sha256
    runtime = SimpleNamespace(trainer_story_world=None, observer=object())
    provider = _build_provider(runtime, changed.providers[0], CountingExecutor(object()))
    assert provider.kind is GoalKind.ADVANCE_STORY
    assert isinstance(provider.skills.get("defeat_lorelei"), story.RedCartridgeLoreleiSkill)
    assert provider.skills.get("defeat_bruno") is None  # no hidden legacy fallback
    assert not provider.skills.get("defeat_lorelei").availability(
        GameState(GameMode.OVERWORLD, frozenset(), "indigo_plateau")
    ).executable


@pytest.fixture
def fixture(monkeypatch):
    reader = _Reader(raw=replace(_raw(), map_id=9, event_flags=bytes(320),
                                player_money=619, badge_bits=255), ready=True)
    reader.read_current_map_objects = lambda: ()
    adapter = _adapter(reader)
    def observe():
        facts = {"story:victory_road_cleared"}
        if reader.raw.event_flags[284] & 2:
            facts.add("league:lorelei_defeated")
        return replace(adapter.observe(), game_state=GameState(
            GameMode.OVERWORLD, frozenset(facts), "indigo_plateau",
        ))
    inputs = []
    emulator = SimpleNamespace(frame_count=0)
    def execute(action):
        inputs.append(action)
        emulator.frame_count += 24
    actions = CountingExecutor(SimpleNamespace(execute=execute))
    runtime = SimpleNamespace(reader=reader, adapter=SimpleNamespace(observe=observe),
                              emulator=emulator)
    zone = TrainerSightZone(
        MapId.LORELEIS_ROOM, 1, 244, 1, (2, 5), TrainerFacing.DOWN, 0, 2273, False, True,
    )
    roster = TrainerPartyQuote(244, 1, (TrainerPartyMember(22, 130, 54),), 100, 5400)
    def plan(_start, map_id, *, goal_at):
        assert type(map_id) is int and map_id == 245
        # Unequal approaches exercise the selection, rather than all tying.
        steps = tuple(SimpleNamespace(action_kind=MacroActionKind.MOVE, action="up",
                                      source_mode="land", expected_mode="land")
                      for _ in range(1 if goal_at == (3, 5) else 4))
        return SimpleNamespace(steps=steps, terminal_at=goal_at)
    world = SimpleNamespace(rom=b"cartridge", plan_feasible_to_map=plan,
                            replanner=lambda: object())
    monkeypatch.setattr(story, "trainer_headers", lambda *_a, **_k: ())
    monkeypatch.setattr(story, "map_object_events", lambda *_: ())
    monkeypatch.setattr(story, "static_trainer_sight_zones", lambda *_: (zone,))
    monkeypatch.setattr(story, "trainer_sight_zones", lambda *_: (zone,))
    monkeypatch.setattr(story, "trainer_party_quote", lambda *_: roster)
    monkeypatch.setattr(story, "Gen1TrainerSightProjector", lambda *_a, **_k: object())
    monkeypatch.setattr(story, "Gen1TraversalObserver",
                        lambda *_: SimpleNamespace(observe=lambda: object()))
    skill = story.RedCartridgeLoreleiSkill(runtime, actions, world)
    return skill, reader, inputs, observe, zone


def test_goal_availability_is_action_free_and_prepares_the_shortest_real_target(fixture):
    skill, _, inputs, observe, _ = fixture
    assert skill.availability(observe().game_state).executable
    assert not inputs
    _, target, _ = skill._prepared
    assert target.approach.terminal_at == (3, 5)
    assert target.interaction_facing is TrainerFacing.UP
    assert len(target.approach.steps) == 1


@pytest.mark.parametrize("fault", [None, "prerequisite", "lobby", "completed", "wrong_trainer"])
def test_bruno_plans_its_actual_target_only_from_post_lorelei_region(fixture, monkeypatch, fault):
    old, reader, inputs, observe, zone = fixture
    reader.raw = replace(reader.raw, map_id=245 if fault != "lobby" else 174)
    def current():
        result = observe()
        facts = set(result.game_state.facts)
        if fault != "prerequisite":
            facts.add("league:lorelei_defeated")
        if fault == "completed":
            facts.add("league:bruno_defeated")
        return replace(result, game_state=replace(result.game_state, facts=frozenset(facts)))
    old.runtime.adapter.observe = current
    target = replace(zone, map_id=MapId.BRUNOS_ROOM,
                     event_flag=2273 if fault == "wrong_trainer" else 2281)
    def headers(_rom, maps, **_kwargs):
        assert maps == {MapId.BRUNOS_ROOM}
        return ()
    old_plan = old.world.plan_feasible_to_map
    def plan(start, map_id, *, goal_at):
        assert map_id == 246
        return old_plan(start, 245, goal_at=goal_at)
    old.world.plan_feasible_to_map = plan
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(reader.raw.map_id, ((1,),))
    old.world.with_current_blocks = lambda blocks: old.world
    monkeypatch.setattr(story, "trainer_headers", headers)
    monkeypatch.setattr(story, "static_trainer_sight_zones", lambda *_: (target,))
    skill = story.RedCartridgeLoreleiSkill(old.runtime, old.actions, old.world,
                                         objective_id="defeat_bruno")
    assert skill.availability(current().game_state).executable == (fault is None)
    if fault is None:
        assert skill._prepared[1].trainer.event_flag == 2281
        assert skill._prepared[1].trainer.map_id == 246
    assert not inputs


def test_bruno_refuses_a_changed_observed_door_before_controller_input(fixture, monkeypatch):
    old, reader, inputs, observe, zone = fixture
    reader.raw = replace(reader.raw, map_id=246)
    old.runtime.adapter.observe = lambda: replace(observe(), game_state=replace(
        observe().game_state, facts=frozenset({"league:lorelei_defeated"}),
    ))
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(246, ((1,),))
    old.world.with_current_blocks = lambda blocks: old.world
    old_plan = old.world.plan_feasible_to_map
    old.world.plan_feasible_to_map = (
        lambda start, _map, goal_at: old_plan(start, 245, goal_at=goal_at)
    )
    monkeypatch.setattr(story, "static_trainer_sight_zones", lambda *_: (
        replace(zone, map_id=MapId.BRUNOS_ROOM, event_flag=2281),
    ))
    skill = story.RedCartridgeLoreleiSkill(old.runtime, old.actions, old.world,
                                         objective_id="defeat_bruno")
    assert skill.availability(old.runtime.adapter.observe().game_state).executable
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(246, ((2,),))
    with pytest.raises(story.RedTrainerStoryError, match="terrain changed"):
        skill.execute()
    assert not inputs


@pytest.mark.parametrize("change", [{"map_id": 3}, {"battle_state": 1},
                                    {"party_hp": (0,)}])
def test_unqualified_boundary_is_not_advertised(fixture, change):
    skill, reader, inputs, observe, _ = fixture
    reader.raw = replace(reader.raw, **change)
    assert not skill.availability(observe().game_state).executable
    assert not inputs


def test_stale_selected_story_refuses_before_input(fixture):
    skill, reader, inputs, observe, _ = fixture
    assert skill.availability(observe().game_state).executable
    reader.raw = replace(reader.raw, player_money=600)
    with pytest.raises(story.RedTrainerStoryError, match="origin"):
        skill.execute()
    assert not inputs


@pytest.mark.parametrize("fault", [None, "route", "target", "bag", "event", "specimen"])
def test_selected_story_composes_existing_operators_and_verifies_result(
    fixture, monkeypatch, fault,
):
    skill, reader, inputs, observe, zone = fixture
    assert skill.availability(observe().game_state).executable
    stages = []
    def prepare(_runtime, actions, plan, *, current_quote):
        plan.require_current(observe().party, current_quote)
        stages.append("prepare")
        actions.execute(MacroAction(MacroActionKind.WAIT))
    def route(plan, actions, _observer, **_kwargs):
        stages.append("route")
        actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
        reader.raw = replace(reader.raw, map_id=245, player_y=3, player_x=5)
        return SimpleNamespace(passed=fault != "route")
    def face(actions, _reader, direction):
        assert direction == "up"
        stages.append("face")
    def battle(rdr, actions, *, target, validate_target, intent, battle_runner_override, **_kwargs):
        assert intent.objective_id == "defeat_lorelei"
        assert battle_runner_override.__self__.maximum_switches == 6
        validate_target()
        stages.append("battle")
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        flags = bytearray(rdr.raw.event_flags)
        if fault != "event":
            flags[284] |= 2
        updates = {"event_flags": bytes(flags), "player_money": 6019}
        if fault == "bag":
            updates["bag_items"] = ((4, 1),)
        if fault == "specimen":
            updates["party_species_ids"] = (104,)
        rdr.raw = replace(rdr.raw, **updates)
        return SimpleNamespace(payout=5400)
    monkeypatch.setattr(story, "prepare_trainer_lead", prepare)
    monkeypatch.setattr(story, "execute_route", route)
    monkeypatch.setattr(story, "face_pc_boundary", face)
    monkeypatch.setattr(story, "run_prepared_trainer_funding", battle)
    if fault == "target":
        monkeypatch.setattr(
            story, "trainer_sight_zones", lambda *_: (replace(zone, trainer_set=2),),
        )
    if fault:
        with pytest.raises(story.RedTrainerStoryError):
            skill.execute()
        assert "battle" not in stages if fault in {"route", "target"} else "battle" in stages
    else:
        result = skill.execute()
        assert stages == ["prepare", "route", "face", "battle"]
        assert result.actions_executed == len(inputs) == 3
        assert result.evidence["story_event_verified"] is True
        assert result.evidence["learned_battle_authority"] is False
    count = len(inputs)
    with pytest.raises(story.RedTrainerStoryError, match="unconsumed"):
        skill.execute()
    assert len(inputs) == count
