"""The exact already-open Dojo introduction is recovery,not chosen story progress."""
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_engaged_story as engaged
from pokemon_red_completion import red_scripted_story_trainer as s
from pokemon_red_completion.red_story_battle import StoryTrainerContract


@pytest.mark.parametrize("fault", [None,"map","position","badge","battle","dialogue",
    "facing","student_missing","won","object_hidden","object_wrong","object_duplicate"])
def test_dojo_introduction_requires_all_actual_native_evidence(monkeypatch,fault):
    flags=bytearray(320)
    events=(s.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_0,s.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_1,
        s.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_2,s.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_3)
    for event in events:
        if fault == "student_missing" and event is events[-1]:
            continue
        flags[int(event)//8] |= 1 << (int(event)%8)
    if fault == "won":
        event=int(s.EventFlag.BEAT_KARATE_MASTER)
        flags[event//8] |= 1 << (event%8)
    raw=N(map_id=178 if fault == "map" else 177,player_y=4 if fault == "position" else 3,
        player_x=4,badge_bits=127 if fault == "badge" else 255,
        battle_state=1 if fault == "battle" else 0,event_flags=bytes(flags))
    obj=N(sprite_index=1,visible=fault != "object_hidden",
        at=(2,5) if fault == "object_wrong" else (3,5))
    reader=N(read=lambda:raw,read_bottom_dialogue_box_visible=lambda:fault != "dialogue",
        read_player_facing=lambda:"left" if fault == "facing" else "right",
        read_current_map_objects=lambda:(obj,obj) if fault == "object_duplicate" else (obj,))
    expected=object()
    calls=[]
    monkeypatch.setattr(s,"dojo_master_contract",lambda *a:calls.append(a) or expected)
    result=s.dojo_master_introduction_contract(b"rom",reader)
    assert result is (expected if fault is None else None)
    assert bool(calls) is (fault is None)


@pytest.mark.parametrize("mode", ["intro","battle","wrong_battle","wild","wrong_context"])
@pytest.mark.parametrize("context", ["defeat_lorelei", "cross_victory_road"])
def test_late_dojo_recovery_reuses_exact_master_without_league_contract(monkeypatch,mode,context):
    contract=StoryTrainerContract("postgame_collection","scripted-dojo-master",177,
        (224,24,1),849,925)
    raw=N(map_id=177,badge_bits=255,
        battle_state=2 if "battle" in mode else 1 if mode == "wild" else 0)
    reader=N(read=lambda:raw,read_active_trainer_identity=lambda:
        (224,24,2) if mode == "wrong_battle" else (224,24,1))
    monkeypatch.setattr(s,"dojo_master_contract",lambda *a:contract)
    monkeypatch.setattr(s,"dojo_master_introduction_contract",lambda *a:
        contract if mode == "intro" else None)
    objective="defeat_misty" if mode == "wrong_context" else context
    result=engaged.engaged_story_contract(reader,b"rom",objective_id=objective,
        dojo_master_transport=True)
    assert result == (
        replace(contract,objective_id=objective) if mode in {"intro","battle"} else None
    )


@pytest.mark.parametrize("fault", [None, "chapter_closed", "early_badges", "wrong_map", "not_triggered"])
def test_pre_league_dojo_recovery_uses_existing_exact_adapter_without_approach(monkeypatch, fault):
    raw = N(map_id=178 if fault == "wrong_map" else 177,
            badge_bits=127 if fault == "early_badges" else 255, battle_state=0)
    runtime = N(reader=N(read=lambda: raw, trainer_engagement_active=lambda: False),
        adapter=N(observe=lambda: N(game_state=object()), graph=N(available_objectives=lambda _: (
            N(id="defeat_lorelei" if fault == "chapter_closed" else "cross_victory_road"),))))
    actions, battler, expected = object(), object(), object()
    calls = []
    def bind(rt, port, **kwargs):
        assert rt is runtime and port is actions and kwargs == dict(
            rom=b"rom", battler=battler, objective_id="cross_victory_road", dojo_master_transport=True)
        calls.append(True)
        return None if fault == "not_triggered" else expected
    monkeypatch.setattr(engaged, "engaged_story_binding", bind)
    result = engaged.retained_ordinary_transport_binding(runtime, actions, rom=b"rom", battler=battler)
    assert result is (expected if fault is None else None)
    assert calls == ([True] if fault in {None, "not_triggered"} else [])


def test_untriggered_master_does_not_hide_already_engaged_ordinary_dojo_trainer(monkeypatch):
    raw = N(map_id=177, badge_bits=255, battle_state=2, event_flags=b"events")
    runtime = N(reader=N(read=lambda: raw, read_active_trainer_identity=lambda: (224,24,2)),
        adapter=N(observe=lambda: N(game_state=object()),
            graph=N(available_objectives=lambda _: (N(id="cross_victory_road"),))))
    expected, calls = object(), []
    monkeypatch.setattr(engaged, "trainer_headers", lambda *a, **kw: ())
    monkeypatch.setattr(engaged, "map_object_events", lambda *a: ())
    monkeypatch.setattr(engaged, "static_trainer_sight_zones", lambda *a: (
        N(defeated=False, trainer_class=224, trainer_set=2),))
    monkeypatch.setattr(engaged, "engaged_story_contract", lambda *a, **kw:
        N(battle_plan_id="retained-native-engagement"))
    def bind(*args, **kwargs):
        calls.append(kwargs)
        return None if kwargs.get("dojo_master_transport") else expected
    monkeypatch.setattr(engaged, "engaged_story_binding", bind)
    assert engaged.retained_ordinary_transport_binding(runtime, object(), rom=b"rom", battler=object()) is expected
    assert [x.get("dojo_master_transport", False) for x in calls] == [True, False]
