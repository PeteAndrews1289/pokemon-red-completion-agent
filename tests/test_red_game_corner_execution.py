from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_game_corner_execution as module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import RawGameState, MenuCursorState


def raw(*, map_id=module.GAME_CORNER, money=1000, case=True):
    return RawGameState(game_started=True, map_id=map_id, player_x=5, player_y=8,
        party_count=1, battle_state=0, player_money=money, badge_bits=0,
        party_species_ids=(177,), party_levels=(5,), party_hp=(19,), party_max_hp=(19,),
        party_moves=((33,39,0,0),), party_pp=((35,30,0,0),), party_status=(0,),
        party_stats=((10,10,10,10),), event_flags=bytes(319),
        bag_items=((module.COIN_CASE,1),) if case else ())


class Reader:
    def __init__(self, state, coins=0):
        self.state,self.coins=state,coins
        self.stage="field"
        self.index=0
        self.boxes=NS(current_box_index=0,boxes=tuple(
            NS(box_index=i,species_ids=(),levels=()) for i in range(12)))
        self.owned={7}
        self.seen={7}
    def read(self): return self.state
    def read_input_readiness(self): return NS(ready=self.stage=="field")
    def read_bottom_dialogue_box_visible(self): return self.stage!="field"
    def read_player_facing(self): return "up"
    def read_game_corner_coins(self): return self.coins
    def read_all_box_states(self): return self.boxes
    def read_pokedex_state(self):
        return NS(owned_species=frozenset(self.owned),seen_species=frozenset(self.seen))
    def read_pc_items(self): return ()
    def read_current_map_objects(self):
        return (NS(sprite_index=2,visible=True,moving=False,at=(6,5),picture_id=38),)
    def read_screen_text_rows(self):
        return ("YES NO",) if self.stage=="yes" else ("PORYGON 9999",) if self.stage=="prize" else ()
    def read_menu_cursor_state(self):
        return MenuCursorState(self.index,0,3 if self.stage=="prize" else 1,
            1 if self.stage=="prize" else 14,4 if self.stage=="prize" else 7)


class Actions:
    def __init__(self,reader,mode="coin",wrong_debit=False):
        self.reader,self.mode,self.wrong_debit=reader,mode,wrong_debit
        self.calls=[]
    def execute(self,action):
        self.calls.append(action)
        r=self.reader
        if action.kind is MacroActionKind.INTERACT:
            r.stage="prize" if self.mode=="prize" else "yes"
            r.index=0
        elif action.kind is MacroActionKind.MOVE:
            r.index += 1 if action.value=="down" else -1
        elif action.kind is MacroActionKind.CONFIRM:
            if r.stage=="prize": r.stage="yes";r.index=0
            elif r.stage=="yes":
                if self.mode=="coin":
                    r.state=replace(r.state,player_money=r.state.player_money-(900 if self.wrong_debit else 1000))
                    r.coins=min(9999,r.coins+50)
                else:
                    r.state=replace(r.state,party_count=2,party_species_ids=(177,170),party_levels=(5,26),
                        party_hp=(19,70),party_max_hp=(19,70),party_moves=((33,39,0,0),(33,0,0,0)),
                        party_pp=((35,30,0,0),(35,0,0,0)),party_status=(0,0),
                        party_stats=((10,10,10,10),(40,40,40,40)))
                    r.owned.add(137);r.seen.add(137);r.coins-=9999
                r.stage="field"


@pytest.fixture
def vendor(monkeypatch):
    monkeypatch.setattr(module,"authenticate_coin_vendor",lambda _:(69,50,1000,9990,9999))


@pytest.mark.parametrize("coins,money,case",[(0,999,True),(9990,1000,True),(9999,1000,True),(0,1000,False)])
def test_unaffordable_or_unavailable_coin_lot_emits_no_input(vendor,coins,money,case):
    reader=Reader(raw(money=money,case=case),coins)
    actions=Actions(reader)
    with pytest.raises(ValueError): module.buy_coin_lot(actions,reader,rom=b"fixture")
    assert actions.calls==[]


@pytest.mark.parametrize("coins,expected",[(0,50),(9950,9999),(9989,9999)])
def test_coin_lot_requires_observed_yes_and_exact_native_debit(vendor,coins,expected):
    reader=Reader(raw(),coins);actions=Actions(reader)
    result=module.buy_coin_lot(actions,reader,rom=b"fixture")
    assert result["cash_debit"]==1000 and result["coins_after"]==expected
    assert result["coins_added"]==expected-coins and not result["learned"]
    assert reader.state.player_money==0


def test_wrong_debit_is_failure_not_success(vendor):
    reader=Reader(raw());actions=Actions(reader,wrong_debit=True)
    with pytest.raises(RuntimeError): module.buy_coin_lot(actions,reader,rom=b"fixture")


def test_wrong_clerk_or_stance_emits_no_input(vendor):
    reader=Reader(replace(raw(),player_x=4));actions=Actions(reader)
    with pytest.raises(ValueError): module.buy_coin_lot(actions,reader,rom=b"fixture")
    assert not actions.calls


def test_vendor_does_not_decode_stale_cursor_before_yes_no_dialogue(vendor):
    class StaleReader(Reader):
        def read_screen_text_rows(self):
            return ("BUY 50 COINS FOR 1000?",) if self.stage=="intro" else super().read_screen_text_rows()
        def read_menu_cursor_state(self):
            if self.stage=="intro":
                raise ValueError("selected menu index cannot exceed its visible maximum")
            return super().read_menu_cursor_state()
    class IntroActions(Actions):
        def execute(self,action):
            old=self.reader.stage
            super().execute(action)
            if action.kind is MacroActionKind.INTERACT: self.reader.stage="intro"
            elif action.kind is MacroActionKind.CONFIRM and old=="intro": self.reader.stage="yes"
    reader=StaleReader(raw())
    result=module.buy_coin_lot(IntroActions(reader),reader,rom=b"fixture")
    assert result["cash_debit"]==1000


def prize_contract(monkeypatch):
    monkeypatch.setattr(module,"game_corner_prizes",lambda _:tuple(
        NS(species=s,level=26,cost=9999) for s in (63,35,30,147,123,137)))
    monkeypatch.setattr(module,"internal_to_dex",lambda _:{177:7,170:137})


def test_native_prize_selection_adds_one_specimen_and_exact_coin_debit(monkeypatch):
    prize_contract(monkeypatch)
    reader=Reader(replace(raw(map_id=module.PRIZE_ROOM),player_x=4,player_y=3),9999)
    actions=Actions(reader,mode="prize")
    result=module.receive_pokemon_prize(actions,reader,rom=b"fixture",species=137)
    assert result["coins_spent"]==9999 and result["coins_after"]==0
    assert result["local_registration_added"] and result["specimen_added"]
    assert result["destination"]=="party" and not result["learned"]
    assert reader.state.player_money==1000


def test_prize_shortfall_cannot_emit_input(monkeypatch):
    prize_contract(monkeypatch)
    reader=Reader(replace(raw(map_id=module.PRIZE_ROOM),player_x=4,player_y=3),9998)
    actions=Actions(reader,mode="prize")
    with pytest.raises(ValueError): module.receive_pokemon_prize(actions,reader,rom=b"fixture",species=137)
    assert not actions.calls


def test_confirmed_prize_waits_for_coherent_native_dex(monkeypatch):
    prize_contract(monkeypatch)
    class TransientReader(Reader):
        def read_pokedex_state(self):
            if self.stage=="writing":
                raise ValueError("owned/seen native writes have not settled")
            return super().read_pokedex_state()
    class TransientActions(Actions):
        pending=0
        def execute(self,action):
            old_stage=self.reader.stage
            super().execute(action)
            if action.kind is MacroActionKind.CONFIRM and old_stage=="yes":
                self.reader.stage="writing"
                self.pending=2
            elif action.kind is MacroActionKind.WAIT and self.pending:
                self.pending-=1
                if not self.pending: self.reader.stage="field"
    reader=TransientReader(replace(raw(map_id=module.PRIZE_ROOM),player_x=4,player_y=3),9999)
    actions=TransientActions(reader,mode="prize")
    result=module.receive_pokemon_prize(actions,reader,rom=b"fixture",species=137)
    assert result["specimen_added"] and reader.stage=="field"


def test_full_party_prize_is_verified_in_current_box(monkeypatch):
    prize_contract(monkeypatch)
    before=replace(raw(map_id=module.PRIZE_ROOM),player_x=4,player_y=3,party_count=6,
        party_species_ids=(177,)*6,party_levels=(5,)*6,party_hp=(19,)*6,party_max_hp=(19,)*6,
        party_moves=((33,39,0,0),)*6,party_pp=((35,30,0,0),)*6,party_status=(0,)*6,
        party_stats=((10,10,10,10),)*6)
    reader=Reader(before,9999)
    class BoxActions(Actions):
        def execute(self,action):
            old_stage=self.reader.stage
            super().execute(action)
            if action.kind is MacroActionKind.CONFIRM and old_stage=="yes":
                self.reader.state=before
                self.reader.boxes=NS(current_box_index=0,boxes=(
                    NS(box_index=0,species_ids=(170,),levels=(26,)),*self.reader.boxes.boxes[1:]))
    result=module.receive_pokemon_prize(BoxActions(reader,mode="prize"),reader,rom=b"fixture",species=137)
    assert result["destination"]==0 and reader.state==before


def test_full_party_and_full_current_box_reject_before_input(monkeypatch):
    prize_contract(monkeypatch)
    reader=Reader(replace(raw(map_id=module.PRIZE_ROOM),player_x=4,player_y=3,party_count=6),9999)
    reader.boxes=NS(current_box_index=0,boxes=(NS(box_index=0,species_ids=(177,)*20,levels=(5,)*20),))
    actions=Actions(reader,mode="prize")
    with pytest.raises(ValueError,match="immediate storage"):
        module.receive_pokemon_prize(actions,reader,rom=b"fixture",species=137)
    assert not actions.calls


def test_prize_cannot_add_unrelated_seen_flags(monkeypatch):
    prize_contract(monkeypatch)
    reader=Reader(replace(raw(map_id=module.PRIZE_ROOM),player_x=4,player_y=3),9999)
    class ChangedSeenActions(Actions):
        def execute(self,action):
            super().execute(action)
            if 137 in self.reader.owned: self.reader.seen.add(8)
    with pytest.raises(RuntimeError,match="unrelated seen"):
        module.receive_pokemon_prize(ChangedSeenActions(reader,mode="prize"),reader,rom=b"fixture",species=137)


def test_changed_cartridge_rejects_coin_case_gift():
    with pytest.raises((module.CartridgeReadError,IndexError,ValueError)):
        module.coin_case_gift_contract(bytes(0x10000))
