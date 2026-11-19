from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import gen1_maps
from pokemon_red_completion import red_player_forced_motion as s
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import InputReadiness, PokemonRedStateReader, RamAddress


def setup(monkeypatch):
    raw = N(map_id=202, battle_state=0, player_y=1, player_x=2,
            player_money=9442, bag_items=((74, 1),), badge_bits=7,
            event_flags=b"unchanged", party_count=2, party_hp=(90, 90),
            party_max_hp=(90, 90), party_pp=((20, 20), (20, 20)),
            party_status=(0, 0), party_species_ids=(166, 28),
            party_levels=(36, 36), party_moves=((1, 2), (3, 4)),
            party_stats=((1, 2, 3, 4), (5, 6, 7, 8)))
    state = N(payload=b"exact-tail", ready=False, dialogue=False, menu=False,
              trainer=False, held=(), fault=None, xp=47652, boxes=("originals",))
    latches = dict(joy_ignore=0, simulated_joypad_index=0, npc_movement_script_table=0,
                   player_moving_direction=8, status_flags_5=0, movement_flags=4,
                   walk_counter=0)
    table = [2, 1, 2, 1, 202, 1, 3, 1, 202]
    memory = {0xD3AE+i: value for i, value in enumerate(table)}
    em = N(frame_count=0, save_state_bytes=lambda: state.payload,
           read_u8=lambda at: memory[at])
    type_em = type("Em", (), {"pressed_buttons": property(lambda self: state.held)})
    emulator = type_em()
    emulator.frame_count=0; emulator.save_state_bytes=em.save_state_bytes
    emulator.read_u8=em.read_u8
    reader = N(read=lambda: deepcopy(raw),
               read_input_readiness=lambda: InputReadiness(**latches),
               read_bottom_dialogue_box_visible=lambda: state.dialogue,
               read_overworld_start_menu_visible=lambda: state.menu,
               trainer_engagement_active=lambda: state.trainer)
    reader.read_retained_warp_entries=PokemonRedStateReader(emulator).read_retained_warp_entries
    rt=N(reader=reader, emulator=emulator);actions=N(actions_executed=0);calls=[]
    nodes={203:N(map_id=203,warp_locations=((1,2),(1,3))),
           202:N(warp_arrivals=((3,10),(15,25)),passages=(N(to_map=203),))}
    monkeypatch.setattr(gen1_maps,"map_graph",lambda rom:nodes)
    monkeypatch.setattr(s,"_field_ready",lambda runtime:state.ready)
    monkeypatch.setattr(s,"capture_player_lesson_snapshot",
                        lambda runtime:(N(),dict(xp=state.xp,party="same")))
    monkeypatch.setattr(s,"_purified_message_custody",
                        lambda runtime:(state.xp,state.boxes,"same refs/dex/pc"))
    def execute(action):
        assert action.kind is MacroActionKind.WAIT
        calls.append(action);actions.actions_executed+=1
        emulator.frame_count+=action.repeat;state.payload=b"after-wait"
        if state.fault!="stuck":
            raw.player_y,raw.player_x=15,25;state.ready=True
        if state.fault=="map":raw.map_id=199
        if state.fault=="battle":raw.battle_state=2
        if state.fault=="coordinate":raw.player_x=24
        if state.fault=="dialogue":state.dialogue=True
        if state.fault=="menu":state.menu=True
        if state.fault=="trainer":state.trainer=True
        if state.fault=="held":state.held=("up",)
        if state.fault=="xp":state.xp+=1
        if state.fault=="boxes":state.boxes=("changed",)
        if state.fault=="cash":raw.player_money-=1
        if state.fault=="bag":raw.bag_items=()
        if state.fault=="event":raw.event_flags=b"changed"
        if state.fault=="hp":raw.party_hp=(89,90)
        if state.fault=="pp":raw.party_pp=()
        if state.fault=="stats":raw.party_stats=()
    actions.execute=execute
    return rt,actions,raw,state,latches,memory,nodes,calls


def test_exact_pending_lift_arrival_only_waits_and_verifies_cartridge_endpoint(monkeypatch):
    rt,actions,raw,state,*_,calls=setup(monkeypatch)
    b=s.interrupted_motion_binding(rt,actions,rom=b"verified cartridge")
    assert b.binding_ref.startswith("pokemon.red:retained-motion:") and not calls
    report=b.execute()
    assert b.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert (raw.map_id,raw.player_y,raw.player_x)==(202,15,25)
    assert report.evidence["mechanic"]=="native_pending_lift_arrival_settlement"
    assert report.evidence["directional_inputs"]==report.evidence["model_queries"]==0
    assert report.actions_executed==1 and report.frames_executed==120
    with pytest.raises(ValueError,match="consumed"):b.execute()
    state.payload=b"changed"
    assert b.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault",["map","battle","ready","held","joy","sim","npc",
    "status","direction","forced","dialogue","menu","trainer","off_lift",
    "count","row","target","index","ambiguous","no_floor_link","unqualified_arrival"])
def test_unproven_motion_is_not_a_generic_recovery_override(monkeypatch,fault):
    rt,actions,raw,state,latches,memory,nodes,calls=setup(monkeypatch)
    if fault=="map":raw.map_id=1
    if fault=="battle":raw.battle_state=2
    if fault=="ready":state.ready=True
    if fault=="held":state.held=("up",)
    if fault=="joy":latches["joy_ignore"]=255
    if fault=="sim":latches["simulated_joypad_index"]=1
    if fault=="npc":latches["npc_movement_script_table"]=1
    if fault=="status":latches["status_flags_5"]=0x80
    if fault=="direction":latches["player_moving_direction"]=0
    if fault=="forced":latches["movement_flags"]=128
    if fault=="dialogue":state.dialogue=True
    if fault=="menu":state.menu=True
    if fault=="trainer":state.trainer=True
    if fault=="off_lift":raw.player_x=4
    if fault=="count":memory[0xD3AE]=1
    if fault=="row":memory[0xD3AF]=2
    if fault=="target":memory[0xD3B2]=199
    if fault=="index":memory[0xD3B1]=8
    if fault=="ambiguous":memory[0xD3B5]=0
    if fault=="no_floor_link":nodes[202].passages=()
    if fault=="unqualified_arrival":nodes[202].warp_arrivals=None
    assert s._interrupted_lift_arrival_binding(rt,actions,rom=b"rom",maximum_waits=2,settle_frames=120)is None
    assert not calls and not actions.actions_executed and not rt.emulator.frame_count


@pytest.mark.parametrize("fault",["map","battle","coordinate","dialogue","menu","trainer",
    "held","xp","boxes","cash","bag","event","hp","pp","stats","stuck"])
def test_wait_only_settlement_preserves_all_custody_and_bounded_scope(monkeypatch,fault):
    rt,actions,raw,state,*_,calls=setup(monkeypatch);state.fault=fault
    b=s.interrupted_motion_binding(rt,actions,rom=b"rom",maximum_waits=2)
    with pytest.raises(RuntimeError,match="lift arrival"):b.execute()
    assert b.verify(None).status is GoalDecisionOutcome.FAILED
    assert len(calls)<=2 and all(a.kind is MacroActionKind.WAIT for a in calls)


def test_stale_pending_arrival_never_sends_input(monkeypatch):
    rt,actions,raw,state,*_,calls=setup(monkeypatch)
    b=s.interrupted_motion_binding(rt,actions,rom=b"rom");state.payload=b"stale"
    with pytest.raises(ValueError,match="stale"):b.execute()
    assert not calls


def test_retained_warp_reader_is_typed_read_only_and_does_not_claim_current_map():
    data={int(RamAddress.NUMBER_OF_WARPS):2}
    data.update({int(RamAddress.WARP_ENTRIES)+i:v for i,v in enumerate([1,2,1,202,1,3,1,202])})
    before=deepcopy(data);rows=PokemonRedStateReader(N(read_u8=lambda at:data[at])).read_retained_warp_entries()
    assert tuple((r.at,r.destination_warp_index,r.destination_map)for r in rows)==(((1,2),1,202),((1,3),1,202))
    assert data==before


def test_retained_warp_reader_rejects_impossible_count_without_table_reads():
    calls=[]
    def read(at):calls.append(at);return 33
    with pytest.raises(ValueError,match="count"):PokemonRedStateReader(N(read_u8=read)).read_retained_warp_entries()
    assert calls==[RamAddress.NUMBER_OF_WARPS]


def test_retained_warp_reader_rejects_incoherent_count():
    calls=[]
    def read(at):
        calls.append(at)
        return 0 if len(calls)==1 else 1
    with pytest.raises(ValueError,match="changed"):PokemonRedStateReader(N(read_u8=read)).read_retained_warp_entries()
