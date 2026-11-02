"""Exact earned admission; no private model or emulator needed for guard tests."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.red_lorelei_story import (
    FrozenEarnedChampionStoryController,
    story_league_controller,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads


@pytest.fixture
def setup(tmp_path, monkeypatch):
    model = fit_trainer_practice_three_heads(
        [_target()], seed=1, epochs=1, require_corpus_floor=False
    )
    monkeypatch.setattr(
        learned, "AGATHA_STORY_MODEL_SHA256", learned.canonical_sha256(model.to_dict())
    )
    actor = learned.FrozenTrainerBattler(
        None,
        model,
        tmp_path,
        "a" * 40,
        "root",
        learned.CHAMPION_STORY_SOURCE_SHA256,
        {},
        model_sha256=learned.AGATHA_STORY_SHA256,
        qualification_sha256=learned.CHAMPION_STORY_ADMISSION_SHA256,
    )
    contract = StoryTrainerContract(
        "defeat_champion", "cartridge-final-story", 120, (243, 43, 2), 2305, 6435
    )
    admission = (
        Path(__file__).parents[1] / "docs/evidence/red-earned-champion-admission-2026-09-25.json"
    ).read_bytes()
    return actor, contract, admission


def test_exact_admission_is_not_ordinary_funding(setup):
    actor, contract, admission = setup
    assert sha256(admission).hexdigest() == learned.CHAMPION_STORY_ADMISSION_SHA256
    ctl = FrozenEarnedChampionStoryController(actor, contract, admission)
    assert story_league_controller(NS(league_story_battle_controller=ctl), "defeat_champion") is ctl
    assert learned.qualified_party_limit(actor.model_sha256, actor.qualification_sha256) == 0
    with pytest.raises(ValueError):
        learned.load_frozen_trainer_model(b"{}", actor.model_sha256, qualification=admission)


@pytest.mark.parametrize(
    "change",
    [
        {"objective_id": "defeat_lance"},
        {"battle_plan_id": "ordinary-trainer-funding"},
        {"map_id": 248},
        {"trainer_identity": (247, 47, 2)},
        {"defeated_event": 8},
        {"victory_money": 1},
        {"victory_items": ((1, 1),)},
        {"victory_badge_bits": 1},
    ],
)
def test_other_contracts_rejected_before_input(setup, change):
    actor, contract, admission = setup
    with pytest.raises(ValueError):
        FrozenEarnedChampionStoryController(actor, replace(contract, **change), admission)
    assert not list(actor.output.iterdir())


@pytest.mark.parametrize("fault", ["source", "weights", "receipt", "model_label", "calls", "claim"])
def test_mutation_and_replay_rejected(setup, fault):
    actor, contract, admission = setup
    ctl = FrozenEarnedChampionStoryController(actor, contract, admission)
    if fault == "source":
        actor.source_state_sha256 = "0" * 64
    elif fault == "weights":
        actor.model = None
    elif fault == "receipt":
        ctl.admission += b" "
    elif fault == "model_label":
        actor.model_sha256 = learned.DAMAGE_STORY_SHA256
    elif fault == "calls":
        actor.calls = 1
    else:
        (actor.output / "battle-0001").mkdir()
    with pytest.raises(ValueError):
        ctl.require_identity()


@pytest.mark.parametrize("objective,rematch", [("defeat_lance", False), ("defeat_champion", True)])
def test_no_next_room_or_rematch(setup, objective, rematch):
    ctl = FrozenEarnedChampionStoryController(*setup)
    with pytest.raises(ValueError):
        story_league_controller(NS(league_story_battle_controller=ctl), objective, rematch=rematch)


@pytest.mark.parametrize("fault", ["authority", "map", "identity", "resume", "win", "wild"])
def test_direct_runtime_cannot_bypass_scope(setup, fault):
    actor, _, _ = setup
    raw = NS(map_id=120, battle_state=2)
    reader = NS(
        read=lambda: raw,
        read_active_trainer_identity=lambda: (243, 43, 1) if fault == "identity" else (243, 43, 2),
    )
    with pytest.raises(ValueError):
        actor._play(
            reader,
            None,
            expected_map=248 if fault == "map" else 120,
            timing=None,
            label="test",
            decision_guard=lambda _: None,
            resume=fault != "resume",
            require_win=fault == "win",
            wild_training=fault == "wild",
            authority=None if fault == "authority" else "frozen-risk-cost-champion-development",
        )
    assert actor.calls == 0 and not list(actor.output.iterdir())


@pytest.mark.parametrize("mode", ["won", "lost", "unresolved"])
def test_real_story_lifecycle_retains_outcome_and_never_calls_teacher(setup, monkeypatch, mode):
    from pokemon_red_completion import red_lorelei_story as bridge
    from pokemon_red_completion import red_story_battle
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
    from pokemon_red_completion.observation import EventFlag, RawGameState
    ctl = FrozenEarnedChampionStoryController(*setup, maximum_decisions=73)
    initial = RawGameState(
        True,
        120,
        3,
        5,
        2,
        2,
        badge_bits=255,
        event_flags=bytes(320),
        party_species_ids=(28, 104),
        party_hp=(50, 0),
        party_max_hp=(100, 80),
        party_status=(0, 0),
        bag_items=((4, 3),),
        player_money=27000,
    )
    state = NS(raw=initial, dialogue=False, inputs=[])
    reader = NS(
        read=lambda: state.raw,
        read_active_trainer_identity=lambda: (243, 43, 2),
        read_pokedex_state=lambda: NS(owned_species={9, 135}),
        read_last_blackout_map=lambda: 9,
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: state.dialogue,
        read_total_pay_day_money=lambda: 0,
    )
    episode = NS(
        battle_won=mode == "won",
        stop_reason={
            "won": "battle_won",
            "lost": "party_defeated",
            "unresolved": "decision_budget",
        }[mode],
        decisions=({"kind": "attack"},),
    )

    def play(r, e, **kwargs):
        assert kwargs["story_authority"] is True and kwargs["maximum_decisions"] == 73
        kwargs["decision_guard"](state.raw)
        if mode == "won":
            flags = bytearray(initial.event_flags)
            n = int(EventFlag.BEAT_CHAMPION_RIVAL)
            flags[n // 8] |= 1 << (n % 8)
            state.raw = replace(
                initial,
                battle_state=0,
                battle_result=0,
                player_money=33435,
                event_flags=bytes(flags),
                party_hp=(20, 0),
            )
        elif mode == "lost":
            state.raw = replace(initial, party_hp=(0, 0))
            state.dialogue = True
        return episode

    ctl.battler.continue_battle = play

    def execute(action):
        state.inputs.append(action)
        if action.kind is MacroActionKind.CONFIRM:
            state.raw = replace(
                initial,
                map_id=9,
                battle_state=0,
                battle_result=1,
                party_hp=(100, 80),
                player_money=13500,
            )
            state.dialogue = False

    monkeypatch.setattr(red_story_battle, "advance_battle_to_policy_boundary", lambda *a, **k: None)

    def forbidden(*a, **k):
        pytest.fail("teacher fallback")

    kwargs = dict(
        expected_map=120,
        intent=BattleIntent("defeat_champion", "cartridge-final-story"),
        timing=BattleRuntimeTiming(),
        label="test",
        consume_battle_start_schedule=False,
        move_decision_guard=lambda raw: None,
    )
    if mode == "won":
        assert ctl.run(reader, NS(execute=execute), forbidden, **kwargs) == state.raw
        assert state.raw.party_hp == (20, 0) and not state.inputs
    else:
        with pytest.raises(bridge.LoreleiStoryBattleStopped, match=mode):
            ctl.run(reader, NS(execute=execute), forbidden, **kwargs)
        assert bool(state.inputs) == (mode == "lost")
    assert ctl.last_completion.outcome == mode and ctl.moves_selected == 1
    if mode == "lost":
        assert state.raw.map_id == 9 and state.raw.player_money == 13500


@pytest.mark.parametrize("fault", ["old_source", "old_receipt", "old_controller"])
def test_agatha_permission_cannot_be_reused(setup, fault):
    from pokemon_red_completion.red_lorelei_story import FrozenEarnedAgathaStoryController
    actor, contract, admission = setup
    if fault == "old_source":
        actor.source_state_sha256 = learned.AGATHA_STORY_SOURCE_SHA256
    elif fault == "old_receipt":
        actor.qualification_sha256 = learned.AGATHA_STORY_ADMISSION_SHA256
    controller = (FrozenEarnedAgathaStoryController if fault == "old_controller"
                  else FrozenEarnedChampionStoryController)
    with pytest.raises(ValueError):
        controller(actor, contract, admission)
    assert actor.calls == 0 and not list(actor.output.iterdir())
