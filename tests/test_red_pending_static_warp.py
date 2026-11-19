from copy import deepcopy
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import gen1_maps
from pokemon_red_completion import red_player_forced_motion as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.actions import MacroActionKind
from test_red_pending_lift_arrival import setup as lift_setup


def setup(monkeypatch, same_coordinates=False):
    rt,actions,raw,state,latches,memory,_,calls=lift_setup(monkeypatch)
    raw.map_id=60;raw.player_y=5;raw.player_x=5
    endpoint=(5,5) if same_coordinates else (15,25)
    source=[N(at=(5,5),destination_warp_index=0,destination_map=60)]
    destination=[N(at=endpoint,destination_warp_index=0,destination_map=59)]
    warps={59:deepcopy(source),60:deepcopy(destination)}
    nodes={59:N(warp_arrivals=((5,5),)),60:N(warp_arrivals=(endpoint,))}
    rt.reader.read_retained_warp_entries=lambda: tuple(source if not state.ready or state.fault=="table" else destination)
    monkeypatch.setattr(gen1_maps,"map_graph",lambda rom:nodes)
    monkeypatch.setattr(gen1_maps,"_read_headers",lambda rom:({},warps,()))
    original=actions.execute
    def execute(action):
        original(action)
        if same_coordinates and state.fault not in {"stuck","coordinate"}:
            raw.player_y,raw.player_x=endpoint
    actions.execute=execute
    return rt,actions,raw,state,latches,source,destination,warps,nodes,calls


@pytest.mark.parametrize("same",[False,True])
def test_reciprocal_committed_warp_uses_existing_wait_only_custody_verifier(monkeypatch,same):
    rt,actions,raw,state,*_,calls=setup(monkeypatch,same)
    binding=s.interrupted_motion_binding(rt,actions,rom=b"cartridge")
    assert binding is not None and not calls
    report=binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert report.evidence["mechanic"]=="native_pending_static_warp_arrival_settlement"
    assert report.actions_executed==1 and report.frames_executed==120
    assert report.evidence["directional_inputs"]==report.evidence["model_queries"]==0
    assert all(a.kind is MacroActionKind.WAIT for a in calls)
    with pytest.raises(ValueError,match="consumed"):binding.execute()


@pytest.mark.parametrize("fault",["battle","ready","held","joy","sim","npc","status0","status5","status7","direction","forced","dialogue","menu","trainer","row","ambiguous","target","index","back_map","back_index","arrival","off_warp"])
def test_uncommitted_ambiguous_or_inconsistent_warp_never_grants_input(monkeypatch,fault):
    rt,actions,raw,state,latches,source,destination,warps,nodes,calls=setup(monkeypatch)
    if fault=="battle":raw.battle_state=1
    if fault=="ready":state.ready=True
    if fault=="held":state.held=("up",)
    if fault=="joy":latches["joy_ignore"]=1
    if fault=="sim":latches["simulated_joypad_index"]=1
    if fault=="npc":latches["npc_movement_script_table"]=1
    if fault.startswith("status"):latches["status_flags_5"]=1<<int(fault[6:])
    if fault=="direction":latches["player_moving_direction"]=0
    if fault=="forced":latches["movement_flags"]=128
    if fault=="dialogue":state.dialogue=True
    if fault=="menu":state.menu=True
    if fault=="trainer":state.trainer=True
    if fault=="row":source[0].at=(4,5)
    if fault=="ambiguous":warps[61]=deepcopy(warps[59]);nodes[61]=N(warp_arrivals=((5,5),))
    if fault=="target":source[0].destination_map=61;warps[59]=deepcopy(source)
    if fault=="index":source[0].destination_warp_index=7;warps[59]=deepcopy(source)
    if fault=="back_map":warps[60][0].destination_map=61
    if fault=="back_index":warps[60][0].destination_warp_index=1
    if fault=="arrival":nodes[60].warp_arrivals=None
    if fault=="off_warp":raw.player_x=4
    assert s._interrupted_lift_arrival_binding(rt,actions,rom=b"rom",maximum_waits=2,settle_frames=120,static_warp=True)is None
    assert not calls


@pytest.mark.parametrize("fault",["map","battle","coordinate","dialogue","menu","trainer","held","xp","boxes","cash","bag","event","hp","pp","stats","stuck","table"])
def test_static_warp_keeps_all_existing_resource_and_scope_guards(monkeypatch,fault):
    rt,actions,raw,state,*_,calls=setup(monkeypatch);state.fault=fault
    binding=s._interrupted_lift_arrival_binding(rt,actions,rom=b"rom",maximum_waits=2,settle_frames=120,static_warp=True)
    with pytest.raises(RuntimeError):binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    assert len(calls)<=2 and all(a.kind is MacroActionKind.WAIT for a in calls)
