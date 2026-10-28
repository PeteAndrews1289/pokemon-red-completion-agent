from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuPhase, RawGameState
from pokemon_red_completion.route_1_wild import flee_wild
from pokemon_red_completion.wild_party_flee import flee_with_fainted_lead, validate_flee_party


def state():
    return RawGameState(
        True,
        17,
        14,
        10,
        4,
        1,
        first_party_hp=0,
        party_species_ids=(1, 2, 3, 4),
        party_levels=(24, 45, 25, 26),
        party_hp=(0, 140, 27, 63),
        party_max_hp=(40, 140, 66, 71),
        party_moves=((1, 2, 3, 4),) * 4,
        party_pp=((20, 20, 20, 20),) * 4,
        party_status=(0, 0, 0, 0),
        bag_items=(),
        player_money=4583,
        badge_bits=15,
        event_flags=bytes(320),
        active_party_index=0,
        active_party_hp=0,
        enemy_species_id=185,
        enemy_level=16,
        enemy_hp=41,
    )


@pytest.mark.parametrize("original", (141, 73, 74, 75, 131, 132, None))
def test_ordinary_native_opponent_ko_is_not_misreported_as_run(original):
    initial=replace(state(),enemy_hp=0,enemy_species_id=141,enemy_level=55)
    live=[initial]
    actions=[]

    def execute(action):
        actions.append(action.kind)
        if action.kind is MacroActionKind.CANCEL:
            live[0]=replace(initial,battle_state=0,battle_result=0)

    reader=NS(read=lambda:live[0],read_input_readiness=lambda:NS(ready=True),
        read_retained_wild_identity=lambda: (
            None if original is None else NS(original_species_id=original)
        ),
        read_battle_menu_state=lambda _:NS(phase=BattleMenuPhase.UNKNOWN))
    options=dict(expected_map_id=17,route_name="ordinary retained KO",stabilization_frames=24,
        error_type=RuntimeError,allow_new_faints=True,allow_opponent_ko_exit=True)
    if original != 141:
        with pytest.raises(RuntimeError,match="protected native identity"):
            flee_with_fainted_lead(NS(execute=execute),reader,initial,**options)
        assert actions==[]
    else:
        result=flee_with_fainted_lead(NS(execute=execute),reader,initial,**options)
        assert result.verified and result.ordinary_opponent_ko_exit
        assert result.battle_result==0 and result.run_attempts==0
        assert not replace(result,ordinary_opponent_ko_exit=False).verified


@pytest.mark.parametrize("start", [
    "hm_refusal", "forget_move", "replace_move", "abandon_yes", "abandon_no",
])
def test_retained_victory_declines_move_learning_then_verifies_whole_party(start):
    initial = replace(state(), enemy_hp=0, active_party_index=1, active_party_hp=140)
    live = dict(raw=initial, phase=start, buttons=[])
    prompts = {"forget_move": ("forget_move", 0), "replace_move": ("replace_move", 0),
               "abandon_yes": ("abandon_learning", 0), "abandon_no": ("abandon_learning", 1)}

    def execute(action):
        if action.kind is MacroActionKind.WAIT:
            return
        live["buttons"].append((action.kind, action.value))
        phase = live["phase"]
        if phase in {"hm_refusal", "forget_move", "replace_move"}:
            assert action.kind is MacroActionKind.CANCEL
            live["phase"] = "forget_move" if phase == "hm_refusal" else "abandon_yes"
        elif phase == "abandon_no":
            assert (action.kind, action.value) == (MacroActionKind.MOVE, "up")
            live["phase"] = "abandon_yes"
        else:
            assert phase == "abandon_yes" and action.kind is MacroActionKind.CONFIRM
            live.update(raw=replace(initial, battle_state=0, battle_result=0), phase="field")

    reader = NS(read=lambda: live["raw"], read_input_readiness=lambda: NS(ready=True),
        read_retained_wild_identity=lambda: NS(original_species_id=185),
        read_move_learning_prompt=lambda raw: prompts.get(live["phase"]),
        read_battle_menu_state=lambda raw: NS(phase=BattleMenuPhase.UNKNOWN))
    evidence = flee_with_fainted_lead(NS(execute=execute), reader, initial,
        expected_map_id=17, route_name="retained move dialogue", stabilization_frames=24,
        error_type=RuntimeError, allow_opponent_ko_exit=True)
    assert evidence.verified and evidence.ordinary_opponent_ko_exit
    assert evidence.run_attempts == 0 and not evidence.forced_switch_slots
    assert not evidence.faint_prompt_exit
    assert not replace(evidence, ordinary_opponent_ko_exit=False).verified
    assert not replace(evidence, battle_result=2).verified
    assert not replace(evidence, hp_scope="first_party_member").verified
    assert live["raw"].party_moves == initial.party_moves
    assert live["raw"].party_pp == initial.party_pp
    assert len(live["buttons"]) <= 3


@pytest.mark.parametrize("allowed,enemy_hp", [(False, 0), (True, 41)])
def test_escape_move_prompt_requires_explicit_ordinary_defeated_enemy(allowed, enemy_hp):
    initial = replace(state(), enemy_hp=enemy_hp, active_party_index=1, active_party_hp=140)
    actions = []
    reader = NS(read=lambda: initial, read_input_readiness=lambda: NS(ready=True),
        read_retained_wild_identity=lambda: NS(original_species_id=185),
        read_move_learning_prompt=lambda raw: pytest.fail("unqualified move prompt queried"),
        read_battle_menu_state=lambda raw: NS(phase=BattleMenuPhase.UNKNOWN))
    with pytest.raises(RuntimeError, match="transition budget"):
        flee_with_fainted_lead(NS(execute=lambda action: actions.append(action.kind)), reader,
            initial, expected_map_id=17, route_name="unqualified dialogue", stabilization_frames=24,
            error_type=RuntimeError, allow_opponent_ko_exit=allowed)
    assert set(actions) == {MacroActionKind.CANCEL, MacroActionKind.WAIT}


@pytest.mark.parametrize("changed", [{"party_moves": ((19, 2, 3, 4),) * 4},
                                   {"party_pp": ((19, 20, 20, 20),) * 4},
                                   {"party_levels": (24, 46, 25, 26)},
                                   {"player_money": 4584}, {"bag_items": ((1, 1),)}])
def test_move_dialogue_escape_still_rejects_unexplained_resources(changed):
    initial = replace(state(), enemy_hp=0, active_party_index=1, active_party_hp=140)
    live = [initial]

    def execute(action):
        if action.kind is MacroActionKind.CONFIRM:
            live[0] = replace(initial, battle_state=0, battle_result=0, **changed)

    reader = NS(read=lambda: live[0], read_input_readiness=lambda: NS(ready=True),
        read_retained_wild_identity=lambda: NS(original_species_id=185),
        read_move_learning_prompt=lambda raw: ("abandon_learning", 0))
    with pytest.raises(RuntimeError, match="resources changed|protected state changed"):
        flee_with_fainted_lead(NS(execute=execute), reader, initial, expected_map_id=17,
            route_name="strict move dialogue", stabilization_frames=24,
            error_type=RuntimeError, allow_opponent_ko_exit=True)


@pytest.mark.parametrize("slot", [1, 2, 3])
@pytest.mark.parametrize("entry_delay", [0, 3])
def test_fainted_lead_dispatch_settles_entry_and_preserves_all_party(slot, entry_delay):
    initial = state()
    live = {"raw": initial, "waits": 0, "run": False}

    def execute(action):
        if action.kind is MacroActionKind.WAIT:
            live["waits"] += 1
            if live["waits"] >= entry_delay and not live["run"]:
                live["raw"] = replace(
                    initial, active_party_index=slot, active_party_hp=initial.party_hp[slot]
                )
        elif action.kind is MacroActionKind.CONFIRM:
            live["run"] = True
            live["raw"] = replace(live["raw"], battle_state=0, battle_result=2)
        else:
            assert action.kind is MacroActionKind.CANCEL

    if entry_delay == 0:
        live["raw"] = replace(
            initial, active_party_index=slot, active_party_hp=initial.party_hp[slot]
        )
    reader = NS(
        read=lambda: live["raw"],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda raw: NS(
            phase=BattleMenuPhase.MAIN if raw.active_party_hp else BattleMenuPhase.UNKNOWN,
            selected_main_command=3,
        ),
    )
    result = flee_wild(
        NS(execute=execute),
        reader,
        initial,
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
    )
    assert result.verified and result.hp_scope == "whole_party" and result.run_attempts == 1
    assert result.final_hp == 230 and live["raw"].party_hp[0] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"party_hp": (0, 0, 0, 0)},
        {"party_hp": (0, 140, 0, 63)},
        {"party_hp": (1, 140, 27, 63)},
        {"party_hp": (0, 140, 28, 63)},
        {"party_pp": None},
        {"party_count": 3},
        {"party_status": (0, 0, 8, 0)},
        {"player_money": 4582},
        {"bag_items": ((1, 1),)},
        {"party_species_ids": (1, 2, 4, 3)},
        {"party_moves": ((2, 2, 3, 4),) * 4},
        {"event_flags": bytes(319) + b"x"},
    ],
)
def test_party_resource_changes_fail_closed(changes):
    with pytest.raises(ValueError):
        validate_flee_party(state(), replace(state(), **changes))


def test_all_fainted_origin_refused():
    raw = replace(state(), party_hp=(0, 0, 0, 0))
    with pytest.raises(ValueError):
        validate_flee_party(raw, raw)


def test_hp_damage_is_retained_without_allowing_new_faint():
    validate_flee_party(state(), replace(state(), party_hp=(0, 133, 27, 63)))


def test_declining_next_mon_is_a_verified_escape_without_run_selection():
    initial = state()
    live = [initial]

    def execute(action):
        if action.kind is MacroActionKind.CANCEL:
            live[0] = replace(initial, battle_state=0, battle_result=2)
        else:
            assert action.kind is MacroActionKind.WAIT

    reader = NS(
        read=lambda: live[0],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda raw: NS(phase=BattleMenuPhase.UNKNOWN),
    )
    result = flee_wild(
        NS(execute=execute),
        reader,
        initial,
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
    )
    assert result.verified and result.faint_prompt_exit and result.run_attempts == 0
    assert not replace(result, faint_prompt_exit=False).verified
    assert not replace(result, hp_scope="first_party_member").verified


@pytest.mark.parametrize("allowed", [False, True])
def test_native_faint_during_failed_run_is_explicit_and_retained(allowed):
    initial = replace(state(), first_party_hp=10, party_hp=(10, 140, 27, 63), active_party_hp=10)
    live = [initial]

    def execute(action):
        if action.kind is MacroActionKind.CONFIRM:
            live[0] = replace(
                initial, first_party_hp=0, active_party_hp=0, party_hp=(0, 140, 27, 63)
            )
        elif action.kind is MacroActionKind.CANCEL:
            live[0] = replace(live[0], battle_state=0, battle_result=2)
        else:
            assert action.kind is MacroActionKind.WAIT

    reader = NS(
        read=lambda: live[0],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda raw: NS(
            phase=BattleMenuPhase.MAIN if raw.active_party_hp else BattleMenuPhase.UNKNOWN,
            selected_main_command=3,
        ),
    )
    args = dict(
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
        allow_new_faints=allowed,
    )
    if not allowed:
        with pytest.raises(RuntimeError, match="new faint"):
            flee_with_fainted_lead(NS(execute=execute), reader, initial, **args)
        return
    result = flee_with_fainted_lead(NS(execute=execute), reader, initial, **args)
    assert result.verified and result.new_fainted_slots == (1,)
    assert result.initial_hp == 240 and result.final_hp == 230
    assert result.public_dict()["new_fainted_slots"] == [1]
    assert not replace(result, party_faints_allowed=False).verified
    assert live[0].party_pp == initial.party_pp


@pytest.mark.parametrize(
    "changes",
    [
        dict(party_hp=(0, 0, 0, 0)),
        dict(party_hp=(1, 140, 27, 63)),
        dict(party_hp=(0, 141, 27, 63)),
        dict(party_pp=None),
        dict(player_money=4582),
        dict(bag_items=((1, 1),)),
        dict(party_status=(0, 0, 8, 0)),
        dict(party_species_ids=(1, 2, 4, 3)),
        dict(party_moves=((2, 2, 3, 4),) * 4),
        dict(event_flags=bytes(319) + b"x"),
        dict(party_levels=(25, 45, 25, 26)),
    ],
)
def test_faint_allowance_does_not_relax_other_protected_resources(changes):
    with pytest.raises(ValueError):
        validate_flee_party(state(), replace(state(), **changes), allow_new_faints=True)


def test_faint_allowance_is_not_truthy_or_implicit():
    with pytest.raises(TypeError):
        validate_flee_party(state(), state(), allow_new_faints=1)


@pytest.mark.parametrize("cursor", [0, 1])
def test_faint_text_advances_to_observed_no_without_selecting_a_reserve(cursor):
    initial = state()
    live = dict(raw=initial, phase="text", cursor=cursor, buttons=[])

    def execute(action):
        if action.kind is MacroActionKind.WAIT:
            return
        live["buttons"].append((action.kind, action.value))
        if live["phase"] == "text":
            assert action.kind is MacroActionKind.CONFIRM
            live["phase"] = "prompt"
        elif action.kind is MacroActionKind.MOVE:
            assert live["phase"] == "prompt" and action.value == "down"
            live["cursor"] = 1
        else:
            assert action.kind is MacroActionKind.CONFIRM and live["cursor"] == 1
            live.update(raw=replace(initial, battle_state=0, battle_result=2), phase="field")

    reader = NS(
        read=lambda: live["raw"],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda _: NS(phase=BattleMenuPhase.UNKNOWN),
        read_wild_next_mon_prompt=lambda _: live["cursor"] if live["phase"] == "prompt" else None,
    )
    result = flee_with_fainted_lead(
        NS(execute=execute),
        reader,
        initial,
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
    )
    assert result.verified and result.faint_prompt_exit and result.run_attempts == 0
    assert live["raw"].party_hp == initial.party_hp
    assert all(kind is not MacroActionKind.CANCEL for kind, _ in live["buttons"])


def test_existing_forced_party_menu_reuses_guarded_switch_and_discloses_slot(monkeypatch):
    initial = state()
    live = [initial]
    switches = []
    monkeypatch.setattr(
        "pokemon_red_completion.battle_recovery._forced_party_menu_ready",
        lambda *a: live[0].battler_hp == 0,
    )

    def switch(actions, reader, emulator, target, **kwargs):
        assert kwargs["resume_forced_switch"] and kwargs["expected_battle_state"] == 1
        switches.append(target)
        live[0] = replace(
            initial, active_party_index=target, active_party_hp=initial.party_hp[target]
        )

    monkeypatch.setattr("pokemon_red_completion.battle_recovery.switch_active_battler", switch)

    def execute(action):
        if action.kind is MacroActionKind.CONFIRM:
            live[0] = replace(live[0], battle_state=0, battle_result=2)
        else:
            assert action.kind is MacroActionKind.WAIT

    reader = NS(
        read=lambda: live[0],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda _: NS(phase=BattleMenuPhase.MAIN, selected_main_command=3),
    )
    result = flee_with_fainted_lead(
        NS(execute=execute),
        reader,
        initial,
        emulator=NS(),
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
    )
    assert result.verified and switches == [1]
    assert result.forced_switch_slots == (2,)
    assert result.public_dict()["learned_replacement"] is False


@pytest.mark.parametrize("status", [*range(8), 8, 16, 32, 64])
def test_explicit_native_status_allowance_accepts_only_semantic_codes(status):
    after = replace(state(), party_status=(0, status, 0, 0))
    validate_flee_party(state(), after, allow_status_changes=True)
    if status:
        with pytest.raises(ValueError):
            validate_flee_party(state(), after)


@pytest.mark.parametrize("status", [-1, 9, 128, True, None])
def test_native_status_allowance_rejects_invalid_or_missing_codes(status):
    with pytest.raises(ValueError):
        validate_flee_party(
            state(), replace(state(), party_status=(0, status, 0, 0)), allow_status_changes=True
        )


def test_verified_escape_retains_native_burn_and_hp_cost():
    initial = state()
    live = [replace(initial, active_party_index=1, active_party_hp=140)]

    def execute(action):
        if action.kind is MacroActionKind.CONFIRM:
            live[0] = replace(
                live[0],
                battle_state=0,
                battle_result=2,
                party_hp=(0, 133, 27, 63),
                party_status=(0, 16, 0, 0),
            )
        else:
            assert action.kind is MacroActionKind.WAIT

    reader = NS(
        read=lambda: live[0],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda _: NS(phase=BattleMenuPhase.MAIN, selected_main_command=3),
    )
    evidence = flee_with_fainted_lead(
        NS(execute=execute),
        reader,
        initial,
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
        allow_status_changes=True,
    )
    assert evidence.verified and not evidence.status_preserved
    assert evidence.native_status_changes == ((2, 0, 16),)
    assert evidence.final_hp == evidence.initial_hp - 7
    assert not replace(evidence, status_changes_allowed=False).verified
