from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from test_red_trainer_battle_lifecycle import fixture, run
from test_red_league_funding import qualified
from test_red_battle_scenario import _raw, Reader
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_trainer_practice_episode import forced_struggle_available
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.observation import MapId, EventFlag
import pokemon_red_completion.red_league_funding as league


@pytest.mark.parametrize("status,pp,expected",[(True,30,True),(False,30,False),(True,0,False)])
def test_focus_energy_remains_a_model_option_only_with_supported_status_scope(status,pp,expected):
    raw=replace(_raw(),battle_state=2,party_count=2,party_hp=(22,0),
                active_party_moves=(106,31,116,15),active_party_pp=(0,0,pp,0))
    encoder=PokemonRedObservationEncoder.from_state_reader(Reader())
    result=prepare_red_battle_scenario(encoder,raw,allow_no_attack=True,allow_status_moves=status)
    assert result.supported_candidate_mask==(False,False,expected,False)
    assert forced_struggle_available(raw) is (pp==0)


def test_focus_energy_is_single_turn_status_metadata_not_a_damage_claim():
    move=RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(116))
    assert move.power==0 and move.category=="status"
    assert not RED_BATTLE_CATALOG.status_move_supported(pokemon_red_move_ref(116))


@pytest.mark.parametrize("stop",["unsupported_struggle_boundary","decision_budget"])
def test_unresolved_battler_boundary_never_selects_unrecorded_replacement_moves(stop):
    f=fixture("unresolved");state,reader,battler,executor=f
    original=battler.continue_battle
    def play(*args,**kwargs):
        episode=original(*args,**kwargs);episode.stop_reason=stop;episode.decisions=(N(),)
        return episode
    battler.continue_battle=play
    result=run(f)
    assert result.outcome=="unresolved" and result.episode.stop_reason==stop
    assert not state.actions


def in_room(qualified,monkeypatch,*,started=True,defeated=False):
    obs,reader,world=qualified;flags=bytearray(obs.raw.event_flags)
    if defeated:flags[int(EventFlag.BEAT_LORELEI)//8]|=1<<(int(EventFlag.BEAT_LORELEI)%8)
    raw=replace(obs.raw,map_id=int(MapId.LORELEIS_ROOM),player_y=5,player_x=4,event_flags=bytes(flags))
    obs.raw=raw;reader.read_league_challenge_started=lambda:started
    start=TraversalSnapshot(raw.map_id,(5,4),True,mode="land",last_outside_map=9)
    monkeypatch.setattr(league,"Gen1TraversalObserver",lambda reader:N(observe=lambda:start))
    calls=[]
    def plan(origin,target,**kwargs):
        calls.append((origin,target,kwargs))
        assert origin==start and target==raw.map_id and kwargs=={"goal_at":start.at}
        return N(steps=(),terminal_map=raw.map_id,terminal_at=start.at)
    return obs,reader,N(plan_feasible_to_map=plan),calls


def test_started_lorelei_income_continues_without_inventing_exit_fly_or_supply(qualified,monkeypatch):
    obs,reader,world,calls=in_room(qualified,monkeypatch)
    result=league.qualify_red_league_funding(b"rom",obs,reader,world,learned_development=True)
    assert result.resume_at_lorelei and not result.fly_required
    assert result.exit_plan is None and not result.entry_plan.steps and not result.supply.route.steps
    assert not result.reset_stale_league_events and result.supply.purchase_cost==0
    assert len(calls)==1 and len(result.battles)==5 and result.expected_gross_income==1500


@pytest.mark.parametrize("started,defeated",[(False,False),(True,True)])
def test_in_room_income_rejects_unstarted_or_consumed_challenge(qualified,monkeypatch,started,defeated):
    obs,reader,world,calls=in_room(qualified,monkeypatch,started=started,defeated=defeated)
    with pytest.raises(league.RedLeagueFundingError,match="fresh started"):
        league.qualify_red_league_funding(b"rom",obs,reader,world,learned_development=True)
    assert not calls


def test_in_room_continuation_cannot_carry_fabricated_transport(qualified,monkeypatch):
    obs,reader,world,calls=in_room(qualified,monkeypatch)
    result=league.qualify_red_league_funding(b"rom",obs,reader,world,learned_development=True)
    with pytest.raises(ValueError,match="invent"):
        replace(result,fly_required=True)


def test_resumed_income_does_not_redecode_already_consumed_arrival(monkeypatch):
    from test_red_league_funding_execution import _runtime,_actions,_binding,_qualification
    import pokemon_red_completion.red_league_funding_execution as ex
    runtime,obs=_runtime()
    obs.raw.map_id=245
    stay=N(steps=())
    q=replace(_qualification(),exit_plan=None,fly_required=False,
              supply=league.RedLeagueSupplyPlan(stay,(),0),entry_plan=stay,resume_at_lorelei=True)
    monkeypatch.setattr(ex,"qualify_red_league_funding",lambda *a,**k:q)
    monkeypatch.setattr(ex,"learned_league_controller",lambda rt:N(field_recovery=None))
    monkeypatch.setattr(ex,"dependency_specimen_ledger",lambda obs:())
    monkeypatch.setattr(ex,"trainer_room_arrival",lambda *a,**k:pytest.fail("arrival already consumed"))
    monkeypatch.setattr(ex,"execute_route",lambda *a,**k:pytest.fail("no replayed transport"))
    def battle(*a,**k):raise RuntimeError("reached owned battle binding")
    monkeypatch.setattr(ex,"_run_battle",battle)
    reuse=ex.ScopedLeagueIncomeReuse("a"*64,"b"*64,lambda *a:None)
    with pytest.raises(ex.RedLeagueFundingExecutionError) as err:
        ex.execute_red_league_funding(runtime,_actions(runtime),N(rom=b"rom"),_binding(runtime,q),development_reuse=reuse)
    assert str(err.value.__cause__)=="reached owned battle binding"


@pytest.mark.parametrize("reserve,other_move,other_pp",[(True,31,0),(False,31,1),(False,100,20),(False,68,10)])
def test_forced_focus_support_preserves_normal_and_unsupported_alternatives(reserve,other_move,other_pp):
    raw=replace(_raw(),battle_state=2,party_count=2,party_hp=(22,20 if reserve else 0),
                active_party_moves=(other_move,0,116,0),active_party_pp=(other_pp,0,30,0))
    encoder=PokemonRedObservationEncoder.from_state_reader(Reader())
    result=prepare_red_battle_scenario(encoder,raw,allow_no_attack=True,allow_status_moves=True)
    assert result.supported_candidate_mask[-1] is False


def test_disabled_focus_is_not_admitted_as_a_move():
    raw=replace(_raw(),battle_state=2,party_count=2,party_hp=(22,0),
                active_party_moves=(0,0,116,0),active_party_pp=(0,0,30,0),
                player_disabled_move_slot=3,player_disable_turns=2)
    result=prepare_red_battle_scenario(PokemonRedObservationEncoder.from_state_reader(Reader()),raw,
                                      allow_no_attack=True,allow_status_moves=True)
    assert not any(result.supported_candidate_mask)


@pytest.mark.parametrize("trainer, reserve, disabled, pp, expected", [
    (True, False, False, 20, True),
    (False, False, False, 20, False),
    (True, True, False, 20, False),
    (True, False, True, 20, False),
    (True, False, False, 0, False),
])
def test_stranded_teleport_is_legal_only_at_narrow_trainer_boundary(trainer, reserve, disabled, pp, expected):
    raw = replace(_raw(), battle_state=2 if trainer else 1, party_count=2,
                  party_hp=(22, 20 if reserve else 0), active_party_moves=(100, 0, 0, 0),
                  active_party_pp=(pp, 0, 0, 0), player_disabled_move_slot=1 if disabled else None,
                  player_disable_turns=2 if disabled else 0)
    encoder = PokemonRedObservationEncoder.from_state_reader(Reader())
    result = prepare_red_battle_scenario(encoder, raw, allow_no_attack=True, allow_status_moves=False, allow_stranded_accuracy_move=True)
    assert result.supported_candidate_mask == (expected,)
