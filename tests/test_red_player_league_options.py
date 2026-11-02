from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_player_league_options as module
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason
from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


def raw(*, won=0, location=None, engaged=False):
    flags = bytearray(320)
    for target in module.LEAGUE_PLAYER_TARGETS[:won]:
        flags[int(target.event)//8] |= 1 << (int(target.event) % 8)
    if location is None:
        location = (MapId.INDIGO_PLATEAU_LOBBY if not won
                    else module.LEAGUE_PLAYER_TARGETS[won-1].room)
    return SimpleNamespace(event_flags=bytes(flags), battle_state=int(engaged),
                           map_id=int(location), badge_bits=255, bag_items=((16, 4),),
                           player_money=100)


@pytest.mark.parametrize("won", range(4))
def test_current_native_prefix_exposes_next_room(won):
    target = module.live_league_player_target(raw(won=won))
    assert target is module.LEAGUE_PLAYER_TARGETS[won]


@pytest.mark.parametrize("won", range(5))
def test_engaged_or_unrelated_boundary_cannot_invent_challenge(won):
    assert module.live_league_player_target(raw(won=won, engaged=True)) is None
    assert module.live_league_player_target(raw(won=won, location=MapId.VIRIDIAN_CITY)) is None


def test_completed_four_rooms_not_champion_admission():
    assert module.live_league_player_target(raw(won=4)) is None


def champion_boundary():
    observed=raw(won=4)
    flags=bytearray(observed.event_flags)
    flags[int(EventFlag.BEAT_LANCE)//8]|=1<<(int(EventFlag.BEAT_LANCE)%8)
    observed.event_flags=bytes(flags)
    return observed


@pytest.mark.parametrize('fault',(None,'last_dialogue','champion_done','wrong_room','engaged'))
def test_champion_opt_in_requires_fresh_native_lance_completion(fault):
    observed=champion_boundary()
    flags=bytearray(observed.event_flags)
    if fault=='last_dialogue':
        flags[int(EventFlag.BEAT_LANCE)//8]&=~(1<<(int(EventFlag.BEAT_LANCE)%8))
    elif fault=='champion_done':
        flags[int(EventFlag.BEAT_CHAMPION_RIVAL)//8]|=1<<(int(EventFlag.BEAT_CHAMPION_RIVAL)%8)
    elif fault=='wrong_room':
        observed.map_id=int(MapId.CHAMPIONS_ROOM)
    elif fault=='engaged':
        observed.battle_state=2
    observed.event_flags=bytes(flags)
    assert module.live_league_player_target(observed) is None
    assert module.live_league_player_target(observed,include_champion=True) is (
        module.CHAMPION_PLAYER_TARGET if fault is None else None)


@pytest.mark.parametrize('permission',(None,0,1,'yes'))
def test_champion_connection_permission_cannot_be_coerced(permission):
    with pytest.raises(TypeError,match='explicit boolean'):
        module.live_league_player_target(raw(),include_champion=permission)
    with pytest.raises(TypeError,match='explicit boolean'):
        module.league_story_option(None,None,route=None,combat_levels=(),include_champion=permission)


def test_observed_post_champion_loss_forecasts_first_room_without_changing_flags():
    observed=champion_boundary()
    observed.map_id=int(MapId.INDIGO_PLATEAU)
    native_flags=observed.event_flags
    assert module.live_league_player_target(observed,include_champion=True) is None
    assert module.live_league_player_target(observed,include_champion=True,
        development_retry_reentry=True,challenge_started=True) is module.LEAGUE_PLAYER_TARGETS[0]
    assert observed.event_flags is native_flags
    assert module.live_league_player_target(observed,include_champion=True,
        development_retry_reentry=True,challenge_started=None) is None
    with pytest.raises(ValueError,match='fresh postgame League boundary'):
        module.live_league_player_target(observed,development_retry_reentry=True,
                                        challenge_started=False)


def test_retry_forecast_cannot_turn_completed_champion_into_new_room():
    observed=champion_boundary()
    observed.map_id=int(MapId.INDIGO_PLATEAU)
    flags=bytearray(observed.event_flags)
    flags[int(EventFlag.BEAT_CHAMPION_RIVAL)//8]|=1<<(int(EventFlag.BEAT_CHAMPION_RIVAL)%8)
    observed.event_flags=bytes(flags)
    with pytest.raises(ValueError,match='fresh postgame League boundary'):
        module.live_league_player_target(observed,development_retry_reentry=True,
                                        challenge_started=True)


@pytest.mark.parametrize("flags", (None, b"", bytes(10)))
def test_missing_native_flags_do_not_create_frontier(flags):
    observed = raw()
    observed.event_flags = flags
    assert module.live_league_player_target(observed) is None


def test_nonprefix_flags_refuse_historical_progress_substitution():
    observed = raw(won=2)
    flags = bytearray(observed.event_flags)
    flags[int(EventFlag.BEAT_LORELEI)//8] &= ~(1 << (int(EventFlag.BEAT_LORELEI) % 8))
    observed.event_flags = bytes(flags)
    with pytest.raises(ValueError, match="earned prefix"):
        module.live_league_player_target(observed)


@dataclass
class LeagueRawProjection:
    event_flags: bytes
    battle_state: int
    map_id: int


@dataclass
class LeagueRuntimeProjection:
    reader: object
    trainer_battle_runner: object = None
    trainer_battle_model_sha256: str | None = None
    trainer_battle_qualification_sha256: str | None = None
    league_story_battle_controller: object = None
    trainer_story_world: object = None


def composition_fixture(tmp_path, monkeypatch, *, won=0):
    from test_red_scoped_lorelei import controller

    old = controller(tmp_path)
    actor = replace(old.battler, calls=7, development_story_scope=None,
                    qualification_sha256=None, pp_depleted_switch_screen=True)
    observed = champion_boundary() if won == 4 else raw(won=won)
    observed = LeagueRawProjection(observed.event_flags, observed.battle_state, observed.map_id)
    current = [observed]
    reader = SimpleNamespace(read=lambda: current[0],
        read_final_league_scene=lambda: SimpleNamespace(rival_starter=2))
    rt = LeagueRuntimeProjection(reader)
    targets = module.LEAGUE_PLAYER_TARGETS + (module.CHAMPION_PLAYER_TARGET,)
    identities = ((244, 44, 1), (233, 33, 1), (246, 46, 1), (247, 47, 1), (243, 43, 2))
    quotes = []

    def contract(_rom, native, **kwargs):
        target = next(t for t in targets if t.objective_id == kwargs["objective_id"])
        quotes.append((target.objective_id, native.event_flags, kwargs["allow_final_class"]))
        identity = identities[targets.index(target)]
        return module.StoryTrainerContract(target.objective_id, "cartridge-trainer-story",
            int(target.room), identity, int(target.event), 5000)

    monkeypatch.setattr(module.StoryTrainerContract, "from_cartridge", contract)
    monkeypatch.setattr(module, "_field_ready", lambda _: True)
    monkeypatch.setattr(module, "champion_script_binding", lambda *_: SimpleNamespace(
        opponent=243, trainer_set=2, active_identity=(243, 43, 2),
        event_flag=int(module.CHAMPION_PLAYER_TARGET.event)))
    monkeypatch.setattr(module, "trainer_party_quote", lambda *_: SimpleNamespace(
        expected_victory_money=6435))
    arguments = dict(battler=actor, rom=b"rom", route_world="actual-world",
        output=tmp_path / "current-room", work_order=old.admission, include_champion=True,
        development_retry_reentry=True)
    return rt, actor, current, targets, quotes, arguments


@pytest.mark.parametrize("won", range(5))
def test_continuous_composition_binds_actual_room_without_inputs(tmp_path, monkeypatch, won):
    rt, actor, current, targets, quotes, arguments = composition_fixture(
        tmp_path, monkeypatch, won=won)
    before = current[0]
    configured, scoped, target = module.bind_live_league_runtime(rt, **arguments)
    assert target is targets[won]
    assert configured.reader is rt.reader and current[0] is before
    assert configured.trainer_story_world == "actual-world"
    assert configured.league_story_battle_controller.contract.objective_id == target.objective_id
    assert scoped.calls == 0 and actor.calls == 7
    assert scoped.model is actor.model
    assert scoped.development_story_scope.allow_learned_tactics
    assert not scoped.development_story_scope.diagnostic_stay_when_productive
    assert not scoped.development_story_scope.diagnostic_prompt_stay
    configured.league_story_battle_controller.require_identity()
    assert not tuple(tmp_path.iterdir())
    assert len(quotes) == (0 if won == 4 else 1)


def test_room_transition_creates_new_contract_not_old_room_order(tmp_path, monkeypatch):
    rt, actor, current, targets, _, arguments = composition_fixture(tmp_path, monkeypatch)
    first = module.bind_live_league_runtime(rt, **arguments)
    observed = raw(won=1)
    current[0] = LeagueRawProjection(observed.event_flags, observed.battle_state, observed.map_id)
    second = module.bind_live_league_runtime(rt, **arguments)
    assert first[2] is targets[0] and second[2] is targets[1]
    assert first[1].development_story_scope.contract != second[1].development_story_scope.contract
    assert first[0].league_story_battle_controller.contract.objective_id == "defeat_lorelei"
    assert second[0].league_story_battle_controller.contract.objective_id == "defeat_bruno"
    assert actor.calls == 7 and first[1].calls == second[1].calls == 0


@pytest.mark.parametrize("won", range(5))
def test_retained_league_composition_is_explicit_exact_and_input_free(tmp_path, monkeypatch, won):
    rt, actor, current, targets, _, arguments = composition_fixture(tmp_path, monkeypatch, won=won)
    identities = ((244, 44, 1), (233, 33, 1), (246, 46, 1), (247, 47, 1), (243, 43, 2))
    current[0] = replace(current[0], battle_state=2, map_id=int(targets[won].room))
    before = current[0]
    rt.reader.read_active_trainer_identity = lambda: identities[won]
    monkeypatch.setattr(module, "_field_ready", lambda _: False)
    assert module.bind_live_league_runtime(rt, **arguments) is None
    configured, scoped, target = module.bind_live_league_runtime(
        rt, allow_engaged=True, **arguments)
    assert target is targets[won] and current[0] is before
    assert configured.reader is rt.reader and scoped.model is actor.model
    assert scoped.calls == 0 and actor.calls == 7
    assert scoped.development_story_scope.contract.trainer_identity == identities[won]
    assert not scoped.development_story_scope.diagnostic_stay_when_productive
    configured.league_story_battle_controller.require_identity()
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("fault", ("wild", "unrelated", "already_won", "identity", "prefix"))
def test_retained_league_binding_refuses_invented_frontier(tmp_path, monkeypatch, fault):
    rt, actor, current, targets, _, arguments = composition_fixture(tmp_path, monkeypatch)
    before = replace(current[0], battle_state=2, map_id=int(targets[0].room))
    rt.reader.read_active_trainer_identity = lambda: (
        (244, 44, 2) if fault == "identity" else (244, 44, 1))
    if fault == "wild":
        before = replace(before, battle_state=1)
    elif fault == "unrelated":
        before = replace(before, map_id=int(MapId.ROUTE_22))
    elif fault in {"already_won", "prefix"}:
        flags = bytearray(before.event_flags)
        event = targets[0].event if fault == "already_won" else targets[2].event
        flags[int(event)//8] |= 1 << (int(event) % 8)
        before = replace(before, event_flags=bytes(flags))
    current[0] = before
    if fault in {"identity", "prefix"}:
        with pytest.raises(ValueError, match="identity differs|earned prefix"):
            module.bind_live_league_runtime(rt, allow_engaged=True, **arguments)
    else:
        assert module.bind_live_league_runtime(rt, allow_engaged=True, **arguments) is None
    assert current[0] is before and actor.calls == 7 and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("value", (None, 0, 1, "yes"))
def test_retained_league_permission_is_never_coerced(tmp_path, monkeypatch, value):
    rt, _, _, _, _, arguments = composition_fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError, match="explicit boolean"):
        module.bind_live_league_runtime(rt, allow_engaged=value, **arguments)


@pytest.mark.parametrize(
    "fault", ("partition", "budget", "deficit", "work", "unrelated", "engaged"),
)
def test_composition_does_not_expand_native_or_source_authority(tmp_path, monkeypatch, fault):
    from pokemon_red_completion.scenario_lab import ScenarioPartition

    rt, actor, current, _, _, arguments = composition_fixture(tmp_path, monkeypatch)
    if fault == "partition":
        actor.source_partition = ScenarioPartition.TRAIN
    elif fault == "budget":
        arguments["maximum_decisions"] = 81
    elif fault == "deficit":
        arguments["maximum_level_deficit"] = True
    elif fault == "work":
        arguments["work_order"] = "untyped work order"
    elif fault == "unrelated":
        current[0] = replace(current[0], map_id=int(MapId.VIRIDIAN_CITY))
    else:
        current[0] = replace(current[0], battle_state=2)
    if fault in {"unrelated", "engaged"}:
        assert module.bind_live_league_runtime(rt, **arguments) is None
    else:
        with pytest.raises(ValueError):
            module.bind_live_league_runtime(rt, **arguments)
    assert actor.calls == 7 and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("value", (None, 0, 1, "yes"))
def test_retry_permission_is_not_coerced(value):
    with pytest.raises(TypeError, match="explicit boolean"):
        module.league_story_option(None, None, route=None, combat_levels=(50,),
                                   development_retry_reentry=value)


def test_inventory_callbacks_are_existing_bound_methods():
    inventory = NativeStoryBranchInventory(lambda *_: None, lambda *_: ())
    assert inventory.native_callbacks() == dict(
        enumerate_bindings=inventory.enumerate, enumerate_supplements=inventory.supplements,
        observe_challenges=inventory.challenges, observe_preparations=inventory.preparations)


@dataclass
class FakeReport:
    verified: bool = True


def fixture(monkeypatch, *, loss=False, malformed_loss=False):
    observed, state = raw(won=1), [b"source"]
    actions = SimpleNamespace(actions_executed=0)
    em = SimpleNamespace(frame_count=0, save_state_bytes=lambda: state[0])
    history_calls = []
    owner = SimpleNamespace(contract=SimpleNamespace(objective_id="defeat_bruno",
        trainer_identity=(233, 33, 1), victory_money=5742), controller_name="scoped",
        require_identity=lambda: None, last_completion=None)
    rt = SimpleNamespace(emulator=em, reader=SimpleNamespace(read=lambda: observed),
        adapter=SimpleNamespace(observe=lambda: SimpleNamespace(game_state="actual")),
        league_story_battle_controller=owner)
    monkeypatch.setattr(module, "_field_ready", lambda _: True)
    monkeypatch.setattr(module, "trainer_party_quote", lambda *_: SimpleNamespace(
        expected_victory_money=5742, party=(SimpleNamespace(level=53), SimpleNamespace(level=58))))
    class Skill:
        def __init__(self, *args, **kwargs):
            assert kwargs["objective_id"] == "defeat_bruno"
            assert kwargs["development_retry_reentry"] is False
        def availability(self, _):
            return SimpleNamespace(executable=True, reason="actual")
        def execute(self):
            actions.actions_executed += 4
            em.frame_count += 40
            state[0] = b"terminal"
            if loss:
                owner.last_completion = SimpleNamespace(outcome="lost", field_ready=True,
                    public_dict=lambda: {"outcome": "lost"})
                observed.player_money = 49 if malformed_loss else 50
                raise module.LoreleiStoryBattleStopped("loss")
            flags = bytearray(observed.event_flags)
            flags[int(EventFlag.BEAT_BRUNO)//8] |= 1 << (int(EventFlag.BEAT_BRUNO) % 8)
            observed.event_flags = bytes(flags)
            return FakeReport()
    monkeypatch.setattr(module, "RedCartridgeLoreleiSkill", Skill)
    # Reader snapshots are immutable in production; retain distinct origin raw here.
    monkeypatch.setattr(rt.reader, "read", lambda: SimpleNamespace(**vars(observed)))
    return rt, actions, SimpleNamespace(route_world="world", rom=b"rom"), state, history_calls


def test_fresh_binding_preserves_quote_costs_and_native_win(monkeypatch):
    rt, actions, route, state, _ = fixture(monkeypatch)
    binding, challenge = module.league_story_option(rt, actions, route=route, combat_levels=(71,))
    assert binding.story_objective_ref == "defeat_bruno"
    assert challenge.opposition_known
    assert actions.actions_executed == 0 and state[0] == b"source"
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert (report.actions_executed, report.frames_executed) == (4, 40)
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("native", range(5))
@pytest.mark.parametrize("goal", range(5))
def test_native_prerequisite_uses_room_order_not_historical_quest_credit(native, goal):
    targets = module.LEAGUE_PLAYER_TARGETS + (module.CHAMPION_PLAYER_TARGET,)
    assert module.league_native_prerequisite(targets[native], targets[goal].objective_id) is (
        native <= goal)
    assert not module.league_native_prerequisite(None, targets[goal].objective_id)
    assert not module.league_native_prerequisite(targets[native], "help_bill")


@pytest.mark.parametrize("ref,legal,available", (
    ("defeat_agatha", True, True), ("defeat_lance", True, True),
    ("defeat_lorelei", True, False), ("defeat_agatha", False, False),
))
def test_reset_room_replay_serves_unfinished_goal_without_later_victory_credit(
    monkeypatch, ref, legal, available,
):
    rt, actions, route, _, _ = fixture(monkeypatch)
    rt.adapter.graph = SimpleNamespace(
        available_objectives=lambda _: (SimpleNamespace(id=ref),) if legal else ())
    result = module.league_story_option(rt, actions, route=route, combat_levels=(71,),
                                      progress_objective_ref=ref)
    assert (result is not None) is available
    assert actions.actions_executed == 0
    if available:
        binding, _ = result
        assert binding.story_objective_ref == ref
        report = binding.execute()
        assert report.evidence["native_prerequisite"] == "defeat_bruno"
        assert report.evidence["objective_completed"] is False
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert not module.event_flag_is_set(rt.reader.read().event_flags,
                                           int(EventFlag.BEAT_AGATHA))


def test_verified_ordinary_loss_is_failed_goal_not_success(monkeypatch):
    rt, actions, route, _, calls = fixture(monkeypatch, loss=True)
    binding, _ = module.league_story_option(rt, actions, route=route, combat_levels=(71,),
        history=lambda: calls.append("verified"))
    report = binding.execute()
    assert report.evidence["native_loss_verified"] and calls == ["verified"]
    assert binding.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED


def test_unverified_loss_propagates_without_fallback(monkeypatch):
    rt, actions, route, _, _ = fixture(monkeypatch, loss=True, malformed_loss=True)
    binding, _ = module.league_story_option(rt, actions, route=route, combat_levels=(71,),
                                          history=lambda: None)
    with pytest.raises(module.LoreleiStoryBattleStopped):
        binding.execute()


def test_stale_boundary_cannot_issue_input(monkeypatch):
    rt, actions, route, state, _ = fixture(monkeypatch)
    binding, _ = module.league_story_option(rt, actions, route=route, combat_levels=(71,))
    state[0] = b"different"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert actions.actions_executed == 0


def test_wrong_controller_frontier_refused(monkeypatch):
    rt, actions, route, _, _ = fixture(monkeypatch)
    rt.league_story_battle_controller.contract.objective_id = "defeat_lorelei"
    with pytest.raises(ValueError, match="current native frontier"):
        module.league_story_option(rt, actions, route=route, combat_levels=(71,))


@pytest.mark.parametrize('identity',((247,47,1),(247,47,2),(233,33,1)))
def test_lance_uses_only_the_existing_revision_pinned_first_set_quote(monkeypatch,identity):
    rt,actions,route,state,_=fixture(monkeypatch)
    current=raw(won=3)
    current.map_id=int(MapId.AGATHAS_ROOM)
    rt.reader.read=lambda:current
    owner=rt.league_story_battle_controller
    owner.contract.objective_id='defeat_lance'
    owner.contract.trainer_identity=identity
    quotes=[]

    def quote(rom,opponent,trainer_set,**kwargs):
        quotes.append((opponent,trainer_set,kwargs))
        return SimpleNamespace(expected_victory_money=5742,party=(SimpleNamespace(level=60),))

    monkeypatch.setattr(module,'trainer_party_quote',quote)
    monkeypatch.setattr(module,'RedCartridgeLoreleiSkill',lambda *a,**k:SimpleNamespace(
        availability=lambda _:SimpleNamespace(executable=True,reason='actual')))
    if identity!=(247,47,1):
        with pytest.raises(ValueError,match='exact supported first set'):
            module.league_story_option(rt,actions,route=route,combat_levels=(71,))
        assert not quotes
    else:
        binding,challenge=module.league_story_option(rt,actions,route=route,combat_levels=(71,))
        assert binding.story_objective_ref=='defeat_lance' and challenge.opposition_known
        assert quotes==[(247,1,{'allow_final_class':True})]
    assert actions.actions_executed==0 and state[0]==b'source'


@pytest.mark.parametrize('fault',(None,'no_hall','no_champion'))
def test_champion_binding_verifies_concurrent_native_hall_and_event(monkeypatch,fault):
    rt,actions,route,state,_=fixture(monkeypatch)
    current=champion_boundary()
    rt.reader.read=lambda:SimpleNamespace(**vars(current))
    owner=rt.league_story_battle_controller
    owner.contract.objective_id='defeat_champion'
    owner.contract.trainer_identity=(243,43,1)
    constructed=[]

    class Champion:
        def __init__(self,*args,**kwargs):
            constructed.append(kwargs)
        def availability(self,_):
            return SimpleNamespace(executable=True,reason='native')
        def execute(self):
            actions.actions_executed+=7
            rt.emulator.frame_count+=70
            state[0]=b'hall'
            flags=bytearray(current.event_flags)
            if fault!='no_champion':
                flags[int(EventFlag.BEAT_CHAMPION_RIVAL)//8]|=1<<(int(EventFlag.BEAT_CHAMPION_RIVAL)%8)
            current.event_flags=bytes(flags)
            current.map_id=int(MapId.CHAMPIONS_ROOM if fault=='no_hall' else MapId.HALL_OF_FAME)
            return FakeReport()

    monkeypatch.setattr(module,'RedCartridgeChampionSkill',Champion)
    assert module.league_story_option(rt,actions,route=route,combat_levels=(73,)) is None
    binding,_=module.league_story_option(rt,actions,route=route,combat_levels=(73,),
        include_champion=True,maximum_level_deficit=30)
    assert binding.story_objective_ref=='defeat_champion'
    assert constructed==[{'recovery_controller':'scoped','rematch':True,'maximum_level_deficit':30}]
    report=binding.execute()
    assert (report.actions_executed,report.frames_executed)==(7,70)
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if fault is None else GoalDecisionOutcome.FAILED)
    with pytest.raises(ValueError,match='consumed'):
        binding.execute()
