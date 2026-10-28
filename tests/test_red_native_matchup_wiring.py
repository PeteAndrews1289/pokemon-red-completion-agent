"""ROM-free current-binding and callback guards for matchup observations."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest

from test_red_immediate_obstruction_preview import gym_setup, contract, binding
from test_red_live_option_menu import _ordinary_bindings, _situation
from pokemon_red_completion import red_player_gym as gym
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyQuote, TrainerPartyMember
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_option_matchup import OptionMatchup
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_player_lesson_runtime import observe_native_player_options
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory, plural_story_bindings
from pokemon_red_completion.red_player_matchup import ExactTrainerMatchupWitness
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def ready_gym(monkeypatch, *, leader=False, frontier=False):
    rt, raw, _ = gym_setup(monkeypatch, frontier=frontier)
    state = [b"current boundary"]
    rt.emulator = N(save_state_bytes=lambda: state[0])
    admitted = binding()
    if leader:
        reward = gym.KOGA_REWARD
        exact = StoryTrainerContract("defeat_koga", "observed-gym-leader", raw.map_id,
            (reward.trainer_class, reward.trainer_class - 200, reward.trainer_set), 321, 500)
        monkeypatch.setattr(gym.GymReward, "contract", lambda *a: exact)
        monkeypatch.setattr(gym, "story_battle_binding", lambda *a, **k: admitted)
    else:
        exact = contract(raw.map_id)
        def obstacle(*a, **kw):
            kw["observe_binding"](exact, admitted)
            return admitted
        monkeypatch.setattr(gym, "obstructing_story_battle_binding", obstacle)
    quote = TrainerPartyQuote(exact.trainer_identity[0], exact.trainer_identity[2],
        (TrainerPartyMember(177, 7, 18),), 10, exact.victory_money)
    monkeypatch.setattr(gym, "trainer_party_quote", lambda *a: quote)
    return rt, state, exact, quote, admitted


@pytest.mark.parametrize("leader,frontier", [(False,False),(False,True),(True,False)])
def test_witness_follows_exact_final_binding(monkeypatch, leader, frontier):
    rt,state,exact,quote,admitted = ready_gym(monkeypatch,leader=leader,frontier=frontier)
    seen=[]
    result,challenge=gym.gym_story_option(rt,None,reward=gym.KOGA_REWARD,
        route=N(rom=b"rom"),battler=None,preparation_plan=None,
        observe_matchup_binding=seen.append)
    assert len(seen)==1 and isinstance(seen[0],ExactTrainerMatchupWitness)
    assert seen[0].source_sha256==sha256(state[0]).hexdigest()
    assert seen[0].binding_ref==result.binding_ref
    assert result is not admitted and result.story_objective_ref=="defeat_koga"
    assert seen[0].contract is exact and seen[0].quote is quote
    assert challenge.combat_required


@pytest.mark.parametrize("mutation",["quote","callback"])
def test_mutated_native_boundary_is_rejected(monkeypatch,mutation):
    rt,state,exact,quote,_=ready_gym(monkeypatch)
    seen=[]
    def quote_read(*a):
        if mutation=="quote":state[0]=b"changed"
        return quote
    def observe(w):
        seen.append(w)
        if mutation=="callback":state[0]=b"changed"
    monkeypatch.setattr(gym,"trainer_party_quote",quote_read)
    with pytest.raises(ValueError,match="changed"):
        gym.gym_story_option(rt,None,reward=gym.KOGA_REWARD,route=N(rom=b"rom"),
            battler=None,preparation_plan=None,observe_matchup_binding=observe)
    assert len(seen)==(0 if mutation=="quote" else 1)


def test_quote_cannot_borrow_another_trainer(monkeypatch):
    rt,_,_,quote,_=ready_gym(monkeypatch)
    monkeypatch.setattr(gym,"trainer_party_quote",lambda *a:replace(quote,trainer_set=99))
    with pytest.raises(ValueError,match="quote differs"):
        gym.gym_story_option(rt,None,reward=gym.KOGA_REWARD,route=N(rom=b"rom"),
            battler=None,preparation_plan=None,observe_matchup_binding=lambda _:None)


def test_unobserved_legacy_obstruction_does_not_fabricate_witness(monkeypatch):
    rt,_,_,_,admitted=ready_gym(monkeypatch)
    monkeypatch.setattr(gym,"obstructing_story_battle_binding",lambda *a,**kw:admitted)
    seen=[]
    _,challenge=gym.gym_story_option(rt,None,reward=gym.KOGA_REWARD,
        route=N(rom=b"rom"),battler=None,preparation_plan=None,observe_matchup_binding=seen.append)
    assert challenge.combat_required and not challenge.opposition_known and not seen


def test_bad_matchup_observer_rejected_before_runtime_read():
    with pytest.raises(TypeError,match="observer must be callable"):
        gym.gym_story_option(None,None,reward=None,route=None,battler=None,
            preparation_plan=None,observe_matchup_binding=True)


def test_inventory_default_callback_set_is_unchanged():
    i=NativeStoryBranchInventory(lambda *a:None,lambda *a:())
    assert set(i.native_callbacks())=={"enumerate_bindings","enumerate_supplements",
        "observe_challenges","observe_preparations"}


@pytest.mark.parametrize("fault",["source","binding","callback"])
def test_inventory_matchup_callback_uses_exact_fresh_boundary(fault):
    current=[b"same"];rt=N(emulator=N(save_state_bytes=lambda:current[0]))
    b=binding();bindings=N(bindings=(b,));boundary=N(state=b"same");calls=[]
    def observer(*a):
        calls.append(a)
        if fault=="callback":current[0]=b"new"
        return {}
    i=NativeStoryBranchInventory(lambda *a:None,lambda *a:(),observe_matchups=observer)
    i._observed=(rt,b"same",bindings,(),{b.binding_ref:OptionChallenge(True,False,0.,0.,0.)},{})
    if fault=="source":current[0]=b"new"
    if fault=="binding":bindings=N(bindings=(replace(b),))
    with pytest.raises(ValueError,match="stale|executors"):
        i.native_callbacks()["observe_matchups"](rt,bindings,(),boundary)
    assert len(calls)==(1 if fault=="callback" else 0)


def live_menu(*,version=15,matchups=None,challenge=True,approach=False):
    b=replace(binding(),story_approach_only=approach)
    ordinary,supplements=plural_story_bindings(_ordinary_bindings([]),(b,),_situation())
    return build_red_live_option_set(situation=_situation(),binding_set=ordinary,
        supplements=supplements,model_feature_version=version,ordering_seed_sha256="a"*64,
        economy_snapshot=EconomySnapshot(427,()),target_cash=0,
        challenges={b.binding_ref:OptionChallenge(True,False,0.,0.,0.)} if challenge else None,
        matchups=matchups)


def test_v15_menu_attaches_only_current_direct_descriptor():
    facts=OptionMatchup((0.,)*27)
    result=live_menu(matchups={"exact":facts})
    selected=next(c for c in result.menu.candidates if c.binding_ref=="exact")
    assert selected.matchup is facts
    assert all(c.matchup is None for c in result.menu.candidates if c.binding_ref!="exact")


@pytest.mark.parametrize("fault",["old_version","noncombat","approach","unknown_ref","wrong_type","nonstory"])
def test_matchup_menu_rejects_incompatible_scope(fault):
    facts=OptionMatchup((0.,)*27)
    kwargs=dict(matchups={"exact":facts})
    if fault=="old_version":kwargs["version"]=14
    if fault=="noncombat":kwargs["challenge"]=False
    if fault=="approach":kwargs["approach"]=True
    if fault=="unknown_ref":kwargs["matchups"]={"missing":facts}
    if fault=="wrong_type":kwargs["matchups"]={"exact":object()}
    if fault=="nonstory":
        kwargs["matchups"]={"private:red:center-route":facts}
    with pytest.raises(ValueError,match="matchup|combat"):
        live_menu(**kwargs)


@pytest.mark.parametrize("version,callback",[(14,lambda *a:{}),(15,True)])
def test_legacy_native_boundary_refuses_matchup_callback_before_reads(version,callback):
    with pytest.raises(ValueError,match="matchup observer"):
        observe_native_player_options(None,None,battle=None,combat_specimen_refs=(),
            remaining_budget=(1.,)*5,target_cash=0,ordering_seed_sha256="a"*64,
            observe_matchups=callback,model_feature_version=version)


def test_native_boundary_forwards_one_current_mapping(monkeypatch):
    import pokemon_red_completion.red_player_lesson_runtime as module
    runtime=N(emulator=N(save_state_bytes=lambda:b"same"))
    ordinary=_ordinary_bindings([])
    boundary=N(state=b"same",registered=N(situation=_situation()),economy=None,readiness=None)
    monkeypatch.setattr(module,"observe_native_player_boundary",lambda *a,**k:boundary)
    seen=[];facts={}
    def observe(rt,bindings,supplements,b):
        assert rt is runtime and bindings is ordinary and supplements==() and b is boundary
        seen.append("observe")
        return facts
    def build(**kw):
        assert kw["matchups"] is facts
        assert kw["model_feature_version"]==15
        seen.append("build")
        return "observed"
    monkeypatch.setattr(module,"build_red_live_option_set",build)
    got=module.observe_native_player_options(runtime,object(),battle=None,
        combat_specimen_refs=(),remaining_budget=(1.,)*5,target_cash=0,
        ordering_seed_sha256="a"*64,enumerate_bindings=lambda *a:ordinary,
        observe_matchups=observe,model_feature_version=15)
    assert got=="observed" and seen==["observe","build"]


@pytest.mark.parametrize("version,callback",[(14,lambda *a:{}),(15,False)])
def test_session_rejects_invalid_observer_before_claim_or_load(version,callback):
    from pokemon_red_completion.red_native_player import NativePlayerSession
    with pytest.raises(ValueError,match="matchup observer"):
        NativePlayerSession(store=None,emulator=None,runtime_factory=None,source={},
            execution=None,output=None,limits=None,combat_specimen_refs=(),
            battle_observer=None,target_cash=0,observe_matchups=callback,
            model_feature_version=version)


@pytest.mark.parametrize("own_count",[0,4])
def test_known_quote_count_survives_actual_live_v15_menu(own_count):
    values=[0.]*27
    values[0]=1.
    values[2]=1.
    values[4]=values[5]=own_count/6
    values[6]=1/6
    facts=OptionMatchup(tuple(values))
    b=binding()
    ordinary,supplements=plural_story_bindings(_ordinary_bindings([]),(b,),_situation())
    challenge=(OptionChallenge(True,True,1/6,.1,.1) if own_count else
               OptionChallenge(True,False,0.,0.,0.))
    result=build_red_live_option_set(situation=_situation(),binding_set=ordinary,
        supplements=supplements,model_feature_version=15,ordering_seed_sha256="a"*64,
        economy_snapshot=EconomySnapshot(427,()),target_cash=0,
        challenges={"exact":challenge},matchups={"exact":facts})
    index=next(i for i,c in enumerate(result.menu.candidates) if c.binding_ref=="exact")
    assert result.menu.candidate_vector(index,feature_version=15)[-28:]==(1.,*facts.values)
