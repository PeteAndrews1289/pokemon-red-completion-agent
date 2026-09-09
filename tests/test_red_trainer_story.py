import json
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
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import CurrentMapBlocks, MapId
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    bind_cartridge_trainer_story_profile,
    build_red_goal_context_profile_payload,
)
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError


def lance_plan():
    local = LocalPath(
        ((4, 6), (3, 6), (2, 6)),
        (LocalEdge((3, 6), 'up'), LocalEdge((2, 6), 'up')),
        ('land', 'land', 'land'),
    )
    return RoutePlan(MacroPath((113,), ()), (4, 6), 'land', (), local, (2, 6), 'land')


def test_scripted_entry_prefix_stops_before_dialogue_without_weakening_route_success():
    plan = lance_plan()
    prefix = story._before_scripted_interaction(plan, ((1, 5), (2, 6)), TrainerFacing.UP)
    assert prefix.terminal_at == (3, 6)
    assert prefix.actions == ('up',)
    assert plan.actions == ('up', 'up') and plan.terminal_at == (2, 6)
    for triggers, facing in [(((3, 6), (2, 6)), TrainerFacing.UP),
                             (((1, 5),), TrainerFacing.UP),
                             (((2, 6),), TrainerFacing.DOWN)]:
        with pytest.raises(story.RedTrainerStoryError):
            story._before_scripted_interaction(plan, triggers, facing)


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


@pytest.mark.parametrize("objective", ["defeat_lance", "defeat_champion"])
@pytest.mark.parametrize("budget", [0, 1, 2])
def test_story_recovery_profile_reaches_real_skill_without_changing_default(objective, budget):
    from pokemon_red_completion.red_goal_context_profile import parse_red_goal_context_profile
    original = _supply_transition_profile()
    changed = bind_cartridge_trainer_story_profile(
        original, objective_id=objective, maximum_full_restores=budget,
    )
    expected = {"trainer_objective": objective}
    if budget:
        expected["maximum_full_restores"] = budget
    assert changed.providers[0].parameters == expected
    assert changed.providers[1:] == original.providers[1:]
    payload = build_red_goal_context_profile_payload(
        profile_id=changed.profile_id,
        providers=tuple((p.kind, p.mechanic, json.loads(json.dumps(
            dict(p.parameters), default=dict,
        ))) for p in changed.providers),
    )
    assert parse_red_goal_context_profile(payload).profile_sha256 == (
        changed.profile_sha256
    )
    runtime = SimpleNamespace(trainer_story_world=None, observer=object())
    provider = _build_provider(runtime, changed.providers[0], CountingExecutor(object()))
    assert provider.skills.get(objective).maximum_full_restores == budget


@pytest.mark.parametrize("budget", [True, -1, 3, 1.0, "1"])
def test_story_recovery_budget_is_explicit_bounded_integer(budget):
    with pytest.raises(RedGoalContextProfileError):
        bind_cartridge_trainer_story_profile(_supply_transition_profile(),
                                            maximum_full_restores=budget)


def test_changed_prepared_budget_and_unfunded_stock_refuse_without_input(fixture):
    skill, reader, inputs, observe, _ = fixture
    reader.raw = replace(reader.raw, bag_items=((16, 1), (4, 8)))
    skill.maximum_full_restores = 2
    assert not skill.availability(observe().game_state).executable
    skill.maximum_full_restores = 1
    assert skill.availability(observe().game_state).executable
    skill.maximum_full_restores = 2
    with pytest.raises(story.RedTrainerStoryError, match="before input"):
        skill.execute()
    assert not inputs


@pytest.fixture
def fixture(monkeypatch):
    reader = _Reader(raw=replace(_raw(), map_id=245, event_flags=bytes(320),
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
    monkeypatch.setattr(story, "trainer_party_quote", lambda *_a, **_k: roster)
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
    reader.raw = replace(reader.raw, map_id=246 if fault != "lobby" else 174)
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


@pytest.mark.parametrize('fault', [None, 'prerequisite', 'completed', 'wrong_trainer'])
def test_agatha_current_room_uses_its_own_target_and_required_bruno_fact(
    fixture, monkeypatch, fault,
):
    old, reader, inputs, observe, zone = fixture
    reader.raw = replace(reader.raw, map_id=247)
    def current():
        result = observe()
        facts = set(result.game_state.facts)
        if fault != 'prerequisite':
            facts.add('league:bruno_defeated')
        if fault == 'completed':
            facts.add('league:agatha_defeated')
        return replace(result, game_state=replace(result.game_state, facts=frozenset(facts)))
    old.runtime.adapter.observe = current
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(247, ((1,),))
    old.world.with_current_blocks = lambda _: old.world
    previous_plan = old.world.plan_feasible_to_map
    def plan(start, map_id, *, goal_at):
        assert map_id == 247
        return previous_plan(start, 245, goal_at=goal_at)
    old.world.plan_feasible_to_map = plan
    monkeypatch.setattr(story, 'static_trainer_sight_zones', lambda *_: (
        replace(zone, map_id=MapId.AGATHAS_ROOM,
                event_flag=2281 if fault == 'wrong_trainer' else 2289),
    ))
    skill = story.RedCartridgeLoreleiSkill(old.runtime, old.actions, old.world,
                                         objective_id='defeat_agatha')
    assert skill.availability(current().game_state).executable is (fault is None)
    assert not inputs
    if fault is None:
        assert skill.expected_facts == frozenset({'league:agatha_defeated'})
        assert skill._prepared[1].trainer.map_id == 247


@pytest.mark.parametrize('fault', [None, 'prerequisite', 'completed', 'wrong_battle_flag'])
def test_lance_distinguishes_battle_event_from_later_story_fact(fixture, monkeypatch, fault):
    import pokemon_red_completion.gen1_scripted_arrival as arrival
    old, reader, inputs, observe, zone = fixture
    reader.raw = replace(reader.raw, map_id=113, player_y=4, player_x=6)
    facts = set() if fault == 'prerequisite' else {'league:agatha_defeated'}
    if fault == 'completed':
        facts.add('league:lance_defeated')
    old.runtime.adapter.observe = lambda: replace(observe(), game_state=GameState(
        GameMode.OVERWORLD, frozenset(facts), 'lances_room',
    ))
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(113, ((1,),))
    old.world.with_current_blocks = lambda _: old.world
    def plan(_start, map_id, *, goal_at):
        assert map_id == 113
        if goal_at != (2, 6):
            raise RoutePlanningError('not a reachable approach')
        return lance_plan()
    old.world.plan_feasible_to_map = plan
    target = replace(zone, map_id=MapId.LANCES_ROOM, at=(1, 6),
                     event_flag=2302 if fault == 'wrong_battle_flag' else 2297)
    monkeypatch.setattr(story, 'static_trainer_sight_zones', lambda *_: (target,))
    monkeypatch.setattr(arrival, 'trainer_room_interaction_coordinates',
                        lambda *_: ((1, 5), (2, 6)))
    skill = story.RedCartridgeLoreleiSkill(old.runtime, old.actions, old.world,
                                         objective_id='defeat_lance')
    available = skill.availability(old.runtime.adapter.observe().game_state).executable
    assert available is (fault is None)
    assert not inputs
    if fault is None:
        assert skill._prepared[1].trainer.event_flag == 2297
        assert skill.expected_facts == frozenset({'league:lance_defeated'})


@pytest.mark.parametrize('fault', [
    None, 'prelatch', 'wrong_pending', 'no_pending', 'drift', 'battle_only',
    'initializing', 'initializing_timeout', 'initializing_hp', 'initializing_header',
    'initializing_sprite', 'initializing_regression',
])
def test_lance_trigger_owned_once_by_battle_controller_and_final_story_fact_verified(
    fixture, monkeypatch, fault,
):
    import pokemon_red_completion.gen1_scripted_arrival as arrival
    old, reader, inputs, observe, zone = fixture
    reader.raw = replace(reader.raw, map_id=113, player_y=4, player_x=6)
    pending = None
    initializing = isinstance(fault, str) and fault.startswith('initializing')
    sprite = 0
    waits = []
    entered_battle = []
    def current():
        facts = {'league:agatha_defeated'}
        if reader.raw.event_flags[287] & 64:
            facts.add('league:lance_defeated')
        return replace(observe(), game_state=GameState(
            GameMode.OVERWORLD, frozenset(facts), 'lances_room',
        ))
    old.runtime.adapter.observe = current
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(113, ((1,),))
    reader.read_pending_trainer_battle_identity = lambda: pending
    reader.read_bottom_dialogue_box_visible = (
        lambda: (fault == 'prelatch' or initializing) and reader.raw.player_y == 2
    )
    validated = []
    def bind(*_a, **_k):
        return lambda: validated.append(reader.raw.player_y)
    monkeypatch.setattr(story, 'bind_scripted_trainer_dialogue', bind)
    if initializing:
        import pokemon_red_completion.gen1_trainer_dialogue as dialogue
        monkeypatch.setattr(dialogue, 'verify_rom_bytes', lambda _: None)
        monkeypatch.setattr(dialogue, '_qualified_header', lambda *_: 0x4800)
        monkeypatch.setattr(story, 'bind_scripted_trainer_dialogue',
                            dialogue.bind_scripted_trainer_dialogue)
        reader.read_player_facing = lambda: 'up'
        reader.read_trainer_dialogue_context = lambda: (
            0x4801 if fault == 'initializing_header' else 0x4800,
            2 if fault == 'initializing_sprite' else sprite,
        )
    old.world.with_current_blocks = lambda _: old.world
    def plan(_start, _map_id, *, goal_at):
        if goal_at != (2, 6):
            raise RoutePlanningError('not reachable')
        return lance_plan()
    old.world.plan_feasible_to_map = plan
    target = replace(zone, map_id=MapId.LANCES_ROOM, at=(1, 6), event_flag=2297)
    monkeypatch.setattr(story, 'static_trainer_sight_zones', lambda *_: (target,))
    monkeypatch.setattr(story, 'trainer_sight_zones', lambda *_: (target,))
    monkeypatch.setattr(arrival, 'trainer_room_interaction_coordinates',
                        lambda *_: ((1, 5), (2, 6)))
    monkeypatch.setattr(story, 'prepare_trainer_lead', lambda *_a, **_k: None)
    def route(plan, *_a, **_k):
        assert plan.terminal_at == (3, 6) and plan.actions == ('up',)
        reader.raw = replace(reader.raw, player_y=3)
        return SimpleNamespace(passed=True)
    monkeypatch.setattr(story, 'execute_route', route)
    monkeypatch.setattr(story, 'face_pc_boundary',
                        lambda *_: pytest.fail('must not send facing inputs into trainer dialogue'))
    original_execute = old.actions.delegate.execute
    def execute(action):
        nonlocal pending, sprite
        original_execute(action)
        if action.kind is MacroActionKind.MOVE:
            assert action.value == 'up'
            reader.raw = replace(reader.raw, player_y=1 if fault == 'drift' else 2)
            pending = None if initializing or fault in {'no_pending', 'prelatch'} else (
                target.trainer_class, 2 if fault == 'wrong_pending' else target.trainer_set,
            )
        if initializing and action.kind is MacroActionKind.WAIT:
            assert action.repeat == 12
            waits.append(action)
            if fault in {'initializing', 'initializing_regression'} and len(waits) == 2:
                sprite = 1
            if fault == 'initializing_hp':
                reader.raw = replace(
                    reader.raw, party_hp=tuple(hp - 1 for hp in reader.raw.party_hp),
                )
    old.actions.delegate.execute = execute
    def battle(_reader, _actions, *, resume_pending_dialogue, validate_scripted_dialogue,
               validate_target, **_kwargs):
        nonlocal sprite
        assert resume_pending_dialogue is (fault != 'prelatch' and not initializing)
        if fault == 'prelatch':
            assert validated == [2]
            validate_scripted_dialogue()
        if initializing:
            assert len(waits) == 2
            if fault == 'initializing_regression':
                sprite = 0
            validate_scripted_dialogue()  # strict before any dialogue input
        validate_target()
        entered_battle.append(True)
        flags = bytearray(reader.raw.event_flags)
        flags[287] |= 2  # ordinary trainer defeat is not the later Lance story bit
        if fault != 'battle_only':
            flags[287] |= 64
        reader.raw = replace(reader.raw, event_flags=bytes(flags))
        return SimpleNamespace(payout=6200)
    monkeypatch.setattr(story, 'run_prepared_trainer_funding', battle)
    skill = story.RedCartridgeLoreleiSkill(old.runtime, old.actions, old.world,
                                         objective_id='defeat_lance')
    assert skill.availability(current().game_state).executable
    if fault not in {None, 'prelatch', 'initializing'}:
        expected_error = (
            dialogue.CartridgeReadError
            if initializing and fault != 'initializing_timeout' else story.RedTrainerStoryError
        )
        with pytest.raises(expected_error):
            skill.execute()
    else:
        assert skill.execute().evidence['story_event_verified']
    assert len([action for action in inputs if action.kind is MacroActionKind.MOVE]) == 1
    assert bool(entered_battle) is (fault in {None, 'prelatch', 'battle_only', 'initializing'})
    if fault == 'no_pending':
        assert len(inputs) == 25  # one entry plus exactly24 bounded waits; no retry
    if initializing:
        assert len(waits) == {
            'initializing': 2, 'initializing_timeout': 24, 'initializing_hp': 1,
            'initializing_header': 0, 'initializing_sprite': 0, 'initializing_regression': 2,
        }[fault]
        assert all(action.kind in {MacroActionKind.MOVE, MacroActionKind.WAIT} for action in inputs)
    count = len(inputs)
    with pytest.raises(story.RedTrainerStoryError, match='unconsumed'):
        skill.execute()
    assert len(inputs) == count


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
@pytest.mark.parametrize("recovery_budget", [0, 1, 2])
def test_selected_story_composes_existing_operators_and_verifies_result(
    fixture, monkeypatch, fault, recovery_budget,
):
    skill, reader, inputs, observe, zone = fixture
    if recovery_budget:
        reader.raw = replace(reader.raw, bag_items=((16, 2), (4, 8)))
    skill.maximum_full_restores = recovery_budget
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
        controller = battle_runner_override.__self__
        assert isinstance(controller, story.RedTrainerSurvivalController) is bool(recovery_budget)
        assert _kwargs['maximum_full_restores'] == recovery_budget
        assert _kwargs['prospective_story_recovery'] is bool(recovery_budget)
        assert intent.require_move_between_switches is (not bool(recovery_budget))
        validate_target()
        stages.append("battle")
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        flags = bytearray(rdr.raw.event_flags)
        if fault != "event":
            flags[284] |= 2
        updates = {"event_flags": bytes(flags), "player_money": 6019}
        if recovery_budget:
            controller.heals_claimed = recovery_budget
            updates['bag_items'] = (
                ((16, 1), (4, 8)) if recovery_budget == 1 else ((4, 8),)
            )
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
        assert result.evidence['bag_items_spent'] == recovery_budget
        assert result.evidence['maximum_full_restores'] == recovery_budget
    count = len(inputs)
    with pytest.raises(story.RedTrainerStoryError, match="unconsumed"):
        skill.execute()
    assert len(inputs) == count
