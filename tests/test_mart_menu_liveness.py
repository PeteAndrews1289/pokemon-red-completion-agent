from dataclasses import replace
from types import SimpleNamespace
import pytest
from pokemon_red_completion.observation import PokemonRedStateReader,MenuCursorState,MapId,RamAddress,ItemId
from pokemon_red_completion.red_goal_skills import RedMartResupplyGoalProvider,RedMartPurchase,RedGoalSkillError
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion import red_player_forced_motion as motion
from test_retained_field_party_menu import setup

def reader(monkeypatch,*,active=True,signature=(1,1,2),words='>BUY SELL QUIT MONEY',map_id=MapId.CERULEAN_MART,battle=0):
    memory=SimpleNamespace(read_u8=lambda addr:{RamAddress.IS_IN_BATTLE:battle,RamAddress.CURRENT_MAP:int(map_id)}.get(addr,0))
    r=PokemonRedStateReader(memory)
    y,x,maximum=signature
    monkeypatch.setattr(r,'_active_menu_cursor',lambda:active)
    monkeypatch.setattr(r,'read_menu_cursor_state',lambda:MenuCursorState(0,0,maximum,x,y))
    monkeypatch.setattr(r,'read_screen_text_rows',lambda:(words,))
    return r

@pytest.mark.parametrize('active,signature,words,map_id,battle',[
    (False,(4,5,3),'MONEY POKe BALL 200',MapId.CERULEAN_MART,0),
    (True,(4,5,3),'BAG ITEMS',MapId.CERULEAN_MART,0),
    (True,(1,1,2),'BUY SELL QUIT MONEY',MapId.CERULEAN_CITY,0),
    (True,(1,1,2),'BUY SELL QUIT MONEY',MapId.CERULEAN_MART,1),
    (True,(1,1,2),'SELL QUIT MONEY',MapId.CERULEAN_MART,0),
])
def test_stale_or_nonshop_cursor_does_not_own_shop_input(monkeypatch,active,signature,words,map_id,battle):
    assert reader(monkeypatch,active=active,signature=signature,words=words,map_id=map_id,battle=battle).read_mart_input()is None

def test_rendered_offer_and_priced_list_are_distinct(monkeypatch):
    assert reader(monkeypatch).read_mart_input()==('offer',0)
    assert reader(monkeypatch,signature=(4,5,3),words='MONEY >POKe BALL 200').read_mart_input()==('buy',0)

def provider(reader,actions):
    return RedMartResupplyGoalProvider(map_id=MapId.CERULEAN_MART,player_x=5,player_y=2,
        interaction_direction='up',purchases=(RedMartPurchase(0,ItemId.POKE_BALL,5,200),),
        actions=SimpleNamespace(execute=actions.append),reader=reader,emulator=None,adapter=None,wait_frames=1)

def test_provider_does_not_accept_stale_priced_coordinates():
    phases=iter([None,('offer',0),('buy',0)]);actions=[]
    p=provider(SimpleNamespace(read_mart_input=lambda:next(phases)),actions)
    p._open_buy_list()
    assert [a.kind for a in actions]==[MacroActionKind.CONFIRM,MacroActionKind.WAIT]*2

def test_provider_fails_closed_when_no_rendered_priced_list_arrives():
    actions=[];p=provider(SimpleNamespace(read_mart_input=lambda:None),actions)
    with pytest.raises(RedGoalSkillError):p._open_buy_list()
    assert len(actions)==16

@pytest.mark.parametrize('fault',[None,'cash','pp','relocation','custody','bound'])
def test_retained_mart_cancel_reuses_strict_custody_and_never_confirms(monkeypatch,fault):
    rt,actions,live=setup(monkeypatch,fault=fault,signature=None)
    rt.reader.read_mart_input=lambda:('offer',0)if live['party']else None
    binding=motion._interrupted_field_party_menu_binding(rt,actions,maximum_cancels=4,settle_frames=30,menu_kind='mart')
    assert binding is not None
    if fault:
        with pytest.raises(RuntimeError):binding.execute()
    else:
        report=binding.execute();assert binding.verify(report).status.value=='succeeded'
        assert report.evidence['mechanic']=='native_retained_field_mart_cancel'
        assert report.evidence['confirms']==report.evidence['model_queries']==0
    assert set(live['actions'])<={MacroActionKind.CANCEL,MacroActionKind.WAIT}

def test_retained_mart_source_change_rejects_before_input(monkeypatch):
    rt,actions,live=setup(monkeypatch,signature=None);rt.reader.read_mart_input=lambda:('offer',0)
    binding=motion._interrupted_field_party_menu_binding(rt,actions,maximum_cancels=4,settle_frames=30,menu_kind='mart')
    live['extra']=True
    with pytest.raises(ValueError):binding.execute()
    assert not live['actions']


@pytest.mark.parametrize("map_id", [MapId.INDIGO_PLATEAU_LOBBY, MapId.CERULEAN_MART])
def test_shared_lobby_shop_observes_offer_and_priced_list(monkeypatch, map_id):
    assert reader(monkeypatch, map_id=map_id).read_mart_input() == ("offer", 0)
    assert reader(monkeypatch, map_id=map_id, signature=(4,5,2), words="MONEY >ULTRA BALL 1200").read_mart_input() == ("buy", 0)


@pytest.mark.parametrize("active,words,battle", [(False,"MONEY BUY SELL QUIT",0), (True,"POKEMON CENTER",0), (True,"MONEY BUY SELL QUIT",1)])
def test_lobby_alone_never_grants_shop_input(monkeypatch, active, words, battle):
    assert reader(monkeypatch, map_id=MapId.INDIGO_PLATEAU_LOBBY, active=active, words=words, battle=battle).read_mart_input() is None


def test_provider_cancels_unowned_quantity_instead_of_purchasing():
    phases = iter([("quantity", 2), ("buy", 0)])
    actions = []
    p = provider(SimpleNamespace(read_mart_input=lambda: next(phases)), actions)
    p._open_buy_list()
    assert [a.kind for a in actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]


@pytest.mark.parametrize("fault", [None,"border","digits","count","currency","map","battle","money"])
def test_mart_quantity_requires_rendered_native_frame_and_matching_count(monkeypatch, fault):
    r = reader(monkeypatch, active=False, signature=(4,5,2), words="MONEY ULTRA BALL", map_id=MapId.INDIGO_PLATEAU_LOBBY)
    tiles = {(7,9):0x79,(19,9):0x7b,(7,11):0x7d,(19,11):0x7e,(7,10):0x7c,(19,10):0x7c,(8,10):0xf1,(14,10):0xf0,(9,10):0xf6,(10,10):0xf7}
    tiles.update({(12,10):0x7f,(13,10):0x7f,(15,10):0xf7,(16,10):0xf8,(17,10):0xf6,(18,10):0xf6})
    if fault == "border": tiles[(19,11)] = 0
    if fault == "digits": tiles[(9,10)] = 0
    if fault == "currency": tiles[(14,10)] = 0
    if fault == "money": monkeypatch.setattr(r,"read_screen_text_rows",lambda:("BAG ITEMS",))
    values = {RamAddress.IS_IN_BATTLE: int(fault == "battle"), RamAddress.CURRENT_MAP: int(MapId.CERULEAN_CITY if fault == "map" else MapId.INDIGO_PLATEAU_LOBBY)}
    def read(address):
        if address in values: return values[address]
        offset = address - int(RamAddress.TILE_MAP)
        return tiles.get((offset % 20, offset // 20),0)
    r._memory.read_u8 = read
    monkeypatch.setattr(r,"read_item_quantity_selection",lambda:(2,2 if fault == "count" else 1))
    assert r.read_mart_input() == (("quantity",1) if fault is None else None)


@pytest.mark.parametrize("quantity", [1, 9, 99])
def test_retained_quantity_uses_existing_cancel_only_custody_recovery(monkeypatch, quantity):
    rt, actions, live = setup(monkeypatch, signature=None)
    rt.reader.read_mart_input=lambda: ("quantity",quantity) if live["party"] else None
    binding=motion._interrupted_field_party_menu_binding(rt,actions,maximum_cancels=4,settle_frames=30,menu_kind="mart")
    assert binding is not None
    report=binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert report.evidence["confirms"] == report.evidence["directional_inputs"] == 0
    assert set(live["actions"]) <= {MacroActionKind.CANCEL,MacroActionKind.WAIT}


@pytest.mark.parametrize("quantity", [0, -1, 100, True])
def test_retained_quantity_rejects_invalid_counts_before_input(monkeypatch,quantity):
    rt,actions,live=setup(monkeypatch, signature=None)
    rt.reader.read_mart_input=lambda:("quantity",quantity)
    assert motion._interrupted_field_party_menu_binding(rt,actions,maximum_cancels=4,settle_frames=30,menu_kind="mart") is None
    assert not live["actions"]


@pytest.mark.parametrize("fault", ["no_money","invalid_cursor"])
def test_field_shop_observation_never_constructs_unowned_stale_cursor(monkeypatch,fault):
    r=reader(monkeypatch,active=False,words="MONEY" if fault=="invalid_cursor" else "POKEMON CENTER",map_id=MapId.INDIGO_PLATEAU_LOBBY)
    values={RamAddress.IS_IN_BATTLE:0,RamAddress.CURRENT_MAP:int(MapId.INDIGO_PLATEAU_LOBBY),RamAddress.CURRENT_MENU_ITEM:3,RamAddress.MAX_MENU_ITEM:2}
    r._memory.read_u8=lambda address:values.get(address,0)
    monkeypatch.setattr(r,"read_menu_cursor_state",lambda:(_ for _ in()).throw(AssertionError("unowned cursor must not be constructed")))
    assert r.read_mart_input() is None


@pytest.mark.parametrize("quantity,total",[(1,100),(1,1200),(9,10800),(98,117600),(99,297000)])
def test_quantity_recognition_keeps_native_right_aligned_total_width(monkeypatch,quantity,total):
    r=reader(monkeypatch,active=False,signature=(4,5,2),words="MONEY ULTRA BALL",map_id=MapId.INDIGO_PLATEAU_LOBBY)
    tiles={(7,9):0x79,(19,9):0x7b,(7,11):0x7d,(19,11):0x7e,(7,10):0x7c,(19,10):0x7c,(8,10):0xf1,(9,10):0xf6+quantity//10,(10,10):0xf6+quantity%10}
    for x in range(12,19):tiles[(x,10)]=0x7f
    digits=str(total);currency_x=18-len(digits);tiles[(currency_x,10)]=0xf0
    for i,digit in enumerate(digits):tiles[(currency_x+i+1,10)]=0xf6+int(digit)
    values={RamAddress.IS_IN_BATTLE:0,RamAddress.CURRENT_MAP:int(MapId.INDIGO_PLATEAU_LOBBY)}
    def read(address):
        if address in values:return values[address]
        offset=address-int(RamAddress.TILE_MAP)
        return tiles.get((offset%20,offset//20),0)
    r._memory.read_u8=read
    monkeypatch.setattr(r,"read_item_quantity_selection",lambda:(2,quantity))
    assert r.read_mart_input()==("quantity",quantity)
