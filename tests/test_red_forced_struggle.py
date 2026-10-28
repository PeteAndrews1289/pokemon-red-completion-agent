from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import battle_runtime
from pokemon_red_completion import red_forced_struggle as struggle
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_trainer_practice_admission import _valid_forced_struggle
from pokemon_red_completion.red_trainer_practice_episode import _resource_state


def raw():
    return RawGameState(
        game_started=True,
        map_id=120,
        player_x=2,
        player_y=2,
        party_count=2,
        battle_state=2,
        party_hp=(100, 0),
        party_max_hp=(100, 80),
        active_party_index=0,
        active_party_hp=100,
        active_party_max_hp=100,
        active_party_pp=(0, 0, 0, 0),
        enemy_hp=100,
    )


class Native:
    def __init__(
        self,
        *,
        own_hp=90,
        enemy_hp=80,
        terminal=False,
        prompt=False,
        stuck=False,
        selected=True,
        move_menu=False,
    ):
        self.raw = raw()
        self.actions = []
        self.phase = BattleMenuPhase.MAIN
        self.prompt = False
        self.options = own_hp, enemy_hp, terminal, prompt, stuck, selected, move_menu

    def read(self):
        return self.raw

    def read_battle_menu_state(self, _raw):
        return (
            BattleMenuState(self.phase, selected_main_command=0)
            if self.phase is BattleMenuPhase.MAIN
            else BattleMenuState(self.phase, selected_move_slot=1)
            if self.phase is BattleMenuPhase.MOVE
            else BattleMenuState(self.phase)
        )

    def trainer_switch_prompt_visible(self, _raw):
        return self.prompt

    def read_player_struggle_selected(self):
        return self.options[5]

    def read_enemy_party_roster_hp(self):
        return (self.raw.enemy_hp,)

    def execute(self, action):
        self.actions.append(action)
        own, enemy, terminal, prompt, stuck, selected, move = self.options
        if action.kind is MacroActionKind.CONFIRM and not stuck:
            self.phase = BattleMenuPhase.MOVE if move else BattleMenuPhase.UNKNOWN
        if action.kind is MacroActionKind.CANCEL:
            self.raw = replace(
                self.raw,
                party_hp=(own, 0),
                active_party_hp=own,
                enemy_hp=enemy,
                battle_state=0 if terminal else 2,
            )
            self.phase = BattleMenuPhase.MAIN if not terminal else BattleMenuPhase.UNKNOWN
            self.prompt = prompt
        return SimpleNamespace(frames=action.repeat if action.kind is MacroActionKind.WAIT else 2)


@pytest.mark.parametrize(
    "changes",
    [
        {"active_party_pp": (1, 0, 0, 0)},
        {"active_party_pp": None},
        {"active_party_pp": (0, 0)},
        {"party_hp": (100, 1)},
        {"active_party_hp": 0},
        {"party_hp": (0, 0)},
        {"active_party_index": None},
        {"battle_state": 1},
        {"enemy_hp": 0},
        {"active_party_pp": (10, 0, 0, 0), "player_disabled_move_slot": 1},
    ],
)
def test_guard_rejects_without_inputs(changes):
    native = Native()
    native.raw = replace(native.raw, **changes)
    assert not struggle.forced_struggle_available(native.raw)
    with pytest.raises(battle_runtime.BattleRuntimeError):
        struggle.execute_forced_struggle_turn(native, native, expected_map=120)
    assert native.actions == []


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"own_hp": 0},
        {"enemy_hp": 0, "terminal": True},
        {"own_hp": 0, "enemy_hp": 0},
        {"enemy_hp": 0, "prompt": True},
        {"own_hp": 100, "enemy_hp": 100},
    ],
)
def test_one_attempt_settles_recoil_faint_ko_prompt_or_no_effect(monkeypatch, options):
    monkeypatch.setattr(battle_runtime, "_preserve_moves_at_learning_prompt", lambda *a, **k: False)
    native = Native(**options)
    result = struggle.execute_forced_struggle_turn(native, native, expected_map=120)
    assert sum(a.kind is MacroActionKind.CONFIRM for a in native.actions) == 1
    assert result.final_state.battler_pp == (0, 0, 0, 0)
    assert result.final_state.battler_hp == options.get("own_hp", 90)
    assert result.public_dict()["execution_claim"] == "attempt_only"
    assert result.public_dict()["move_slot"] is None
    assert result.actions_executed == len(native.actions)


@pytest.mark.parametrize("options", [{"stuck": True}, {"selected": False}, {"move_menu": True}])
def test_no_departure_selection_or_unexpected_move_menu_fails_bounded(options):
    native = Native(**options)
    with pytest.raises(battle_runtime.BattleRuntimeError):
        struggle.execute_forced_struggle_turn(native, native, expected_map=120)
    assert len(native.actions) <= 15
    assert sum(a.kind is MacroActionKind.CONFIRM for a in native.actions) == 1


def test_selection_address_is_adapter_only():
    class Memory:
        def read_u8(self, address):
            assert address == RamAddress.PLAYER_SELECTED_MOVE == 0xCCDC
            return 165

    assert PokemonRedStateReader(Memory()).read_player_struggle_selected()


def decision():
    initial = raw()
    final = replace(initial, active_party_hp=80, party_hp=(80, 0), enemy_hp=60)
    return dict(
        kind="forced_struggle",
        authority="forced_mechanic",
        legal_party_slots=[],
        model_diagnostics={},
        policy_elapsed_ns=0,
        frames_executed=122,
        state_before=_resource_state(initial),
        state_after=_resource_state(final),
        outcome=struggle.ForcedStruggleExecution(initial, final, 2, 122).public_dict(),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority", "learner"),
        ("policy_elapsed_ns", 1),
        ("move_slot", 1),
        ("legal_party_slots", [2]),
        ("model_diagnostics", {"invented": True}),
        ("frames_executed", 121),
    ],
)
def test_admission_rejects_fabricated_authority_or_measurements(field, value):
    row = decision()
    assert _valid_forced_struggle(row)
    row[field] = value
    assert not _valid_forced_struggle(row)


def test_admission_rejects_pp_change_or_living_reserve():
    row = decision()
    row["state_after"]["active_pp"][0] = 1
    assert not _valid_forced_struggle(row)


def test_terminal_scripted_heal_is_not_an_extra_pp_spend():
    row = decision()
    row["outcome"].update(final_battle_state=0, terminal_enemy_roster_hp=[0])
    row["state_after"].update(active_party_slot=None, active_pp=[25, 20, 0, 0], opponent_hp=0)
    assert _valid_forced_struggle(row)
    row["outcome"]["terminal_enemy_roster_hp"] = [1]
    assert not _valid_forced_struggle(row)


@pytest.mark.parametrize(
    "reason,changes",
    [
        ("sleep", {"active_party_status": 2}),
        ("freeze", {"active_party_status": 32}),
        ("trapping", {"enemy_using_trapping_move": True}),
    ],
)
def test_suppression_does_not_claim_a_selected_struggle(monkeypatch, reason, changes):
    monkeypatch.setattr(battle_runtime, "_preserve_moves_at_learning_prompt", lambda *a, **k: False)
    native = Native(selected=False, own_hp=100, enemy_hp=100)
    native.raw = replace(native.raw, **changes)
    result = struggle.execute_forced_struggle_turn(native, native, expected_map=120)
    evidence = result.public_dict()
    assert evidence["suppression"] == reason
    assert evidence["cartridge_selection_observed"] is False
    assert evidence["selected_move_ref"] is None
    assert evidence["execution_claim"] == "suppressed_before_selection"
    assert sum(a.kind is MacroActionKind.CONFIRM for a in native.actions) == 1
    row = decision()
    row["outcome"] = evidence
    row["frames_executed"] = evidence["frames_executed"]
    row["observation"] = {
        "features": {
            "party": {"lead": {"status": reason}},
            "battle": {"opponent_using_trapping_move": reason == "trapping"},
        }
    }
    assert _valid_forced_struggle(row)
    row["observation"]["features"] = {}
    assert not _valid_forced_struggle(row)


def test_teacher_setup_is_train_only_and_edits_exact_pp_mirrors():
    from collections import defaultdict

    from pokemon_red_completion.observation import PARTY_PP_OFFSET
    from pokemon_red_completion.red_battle_practice_factory import _BATTLE_PP
    from pokemon_red_completion.red_status_practice import condition_train_struggle
    from pokemon_red_completion.scenario_lab import ScenarioPartition

    memory = defaultdict(lambda: 10)
    addresses = [
        base + i
        for base in (_BATTLE_PP, int(RamAddress.PARTY_MON_1) + PARTY_PP_OFFSET)
        for i in range(4)
    ]

    class Reader:
        def read(self):
            return replace(
                raw(),
                party_count=1,
                party_hp=(100,),
                active_party_pp=tuple(memory[a] for a in addresses[4:]),
            )

        def read_battle_menu_state(self, state):
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)

    with pytest.raises(ValueError, match="TRAIN"):
        condition_train_struggle(Reader(), memory, partition=ScenarioPartition.DEVELOPMENT)
    assert all(v == 10 for v in memory.values())
    result = condition_train_struggle(Reader(), memory, partition=ScenarioPartition.TRAIN)
    assert result["teacher_memory_write_count"] == 8 and result["actor_memory_writes"] == 0
    assert {k for k, v in memory.items() if v == 0} == set(addresses)


def test_terminal_referee_preserves_last_foe_damage_and_faint_after_exit():
    from pokemon_red_completion.red_trainer_practice_episode import _episode_metrics
    from pokemon_red_completion.red_trainer_practice_returns import score_trainer_practice_episode

    before = replace(
        raw(),
        enemy_hp=1,
        enemy_max_hp=100,
        enemy_party_hp=(0, 1),
        enemy_party_position=1,
        party_pp=((0, 0, 0, 0), (0, 0, 0, 0)),
    )
    after = replace(
        before,
        battle_state=0,
        active_party_index=None,
        enemy_hp=0,
        enemy_party_hp=None,
        enemy_party_position=None,
    )
    execution = struggle.ForcedStruggleExecution(before, after, 2, 122, (0, 0))
    row = decision()
    row.update(
        state_before=_resource_state(before),
        state_after=_resource_state(after),
        opponent_hp_before=1,
        opponent_hp_after=0,
        outcome=execution.public_dict(),
        observation={"features": {"battle": {"opponent_max_hp": 100}}},
        **execution.terminal_referee_evidence(),
    )
    metrics = _episode_metrics((row,))
    result = score_trainer_practice_episode(
        dict(
            decisions=[row],
            metrics=metrics,
            stop_reason="battle_won",
            frames_executed=122,
            player_turn_count=1,
        )
    )
    assert metrics["opponent_faints"] == 1
    assert result.opponent_damage_fraction == 0.01
    assert result.value == 4.005
    with pytest.raises(battle_runtime.BattleRuntimeError, match="roster"):
        replace(
            execution, initial_state=replace(before, enemy_party_hp=None)
        ).terminal_referee_evidence()
    row = decision()
    row["state_before"]["party_hp"][1] = 1
    assert not _valid_forced_struggle(row)
