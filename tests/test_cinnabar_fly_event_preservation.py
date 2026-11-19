from dataclasses import replace

import pytest
from test_gen1_fly import FlyWorld, _port, _raw

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError, fly_story_events_preserved
from pokemon_red_completion.observation import EventFlag, MapId


def events(*flags):
    value = bytearray(320)
    for flag in flags:
        value[int(flag)//8] |= 1 << (int(flag)%8)
    return bytes(value)


@pytest.mark.parametrize('flags', [(), (EventFlag.MANSION_SWITCH_ON,),
    (EventFlag.LAB_STILL_REVIVING_FOSSIL,),
    (EventFlag.MANSION_SWITCH_ON, EventFlag.LAB_STILL_REVIVING_FOSSIL)])
def test_exact_native_cinnabar_reset_preserves_all_other_flags(flags):
    before = replace(_raw(), badge_bits=63, event_flags=events(100, *flags))
    after = replace(before, map_id=MapId.CINNABAR_ISLAND, event_flags=events(100))
    assert fly_story_events_preserved(before, after, MapId.CINNABAR_ISLAND, departure=False)


@pytest.mark.parametrize('fault', ['departure','wrong_map','wrong_destination','badge_change',
    'unrelated_set','unrelated_clear','partial_reset','set_switch','set_lab','missing','truncated'])
def test_cinnabar_allowance_rejects_non_native_event_changes(fault):
    before = replace(_raw(), badge_bits=63,
        event_flags=events(100,EventFlag.MANSION_SWITCH_ON,EventFlag.LAB_STILL_REVIVING_FOSSIL))
    after = replace(before, map_id=MapId.CINNABAR_ISLAND, event_flags=events(100))
    if fault == 'wrong_map':after=replace(after,map_id=MapId.FUCHSIA_CITY)
    if fault == 'badge_change':after=replace(after,badge_bits=127)
    if fault == 'unrelated_set':after=replace(after,event_flags=events(100,101))
    if fault == 'unrelated_clear':after=replace(after,event_flags=events())
    if fault == 'partial_reset':after=replace(after,event_flags=events(100,EventFlag.LAB_STILL_REVIVING_FOSSIL))
    if fault in ('set_switch','set_lab'):
        before=replace(before,event_flags=events(100))
        after=replace(after,event_flags=events(100,EventFlag.MANSION_SWITCH_ON if fault=='set_switch'else EventFlag.LAB_STILL_REVIVING_FOSSIL))
    if fault == 'missing':after=replace(after,event_flags=None)
    if fault == 'truncated':before=replace(before,event_flags=bytes(3))
    destination=MapId.VIRIDIAN_CITY if fault=='wrong_destination'else MapId.CINNABAR_ISLAND
    assert not fly_story_events_preserved(before,after,destination,departure=fault=='departure')


class CinnabarWorld(FlyWorld):
    extra_event = False
    def execute(self,action):
        result=super().execute(action)
        if self.raw.map_id==MapId.CINNABAR_ISLAND:
            value=bytearray(self.raw.event_flags)
            for flag in (EventFlag.MANSION_SWITCH_ON,EventFlag.LAB_STILL_REVIVING_FOSSIL):
                value[int(flag)//8] &= ~(1 << (int(flag)%8))
            if self.extra_event:value[12] |= 1
            self.raw=replace(self.raw,event_flags=bytes(value))
        return result


@pytest.mark.parametrize('extra_event',[False,True])
def test_full_fly_executor_accepts_native_reset_and_retains_rogue_failure(extra_event):
    before=replace(_raw(),badge_bits=63,event_flags=events(EventFlag.MANSION_SWITCH_ON,EventFlag.LAB_STILL_REVIVING_FOSSIL))
    world=CinnabarWorld(raw=before,available=(8,),selected=8)
    world.extra_event=extra_event
    action=MacroAction(MacroActionKind.FIELD_MOVE,'fly:cinnabar_island')
    if extra_event:
        with pytest.raises(Gen1FieldMoveError,match='protected'):_port(world).execute(action)
    else:
        receipt=_port(world).execute(action)
        assert receipt.destination_map==8 and world.raw.event_flags==events()
    assert world.flight_confirms==1
    assert world.raw.party_hp==before.party_hp and world.raw.bag_items==before.bag_items
    assert world.raw.player_money==before.player_money
