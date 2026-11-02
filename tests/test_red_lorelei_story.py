"""ROM-free Lorelei bridge tests; model identity is tested separately from lifecycle fakes."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_red_trainer_story import fixture as story_fixture

from pokemon_red_completion import red_lorelei_story as bridge
from pokemon_red_completion import red_story_battle
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState
from pokemon_red_completion.red_learned_league import learned_league_controller
from pokemon_red_completion.red_learned_trainer import (
    DAMAGE_STORY_ADMISSION_SHA256,
    DAMAGE_STORY_SHA256,
    FrozenTrainerBattler,
)


@pytest.fixture
def fixture(monkeypatch):
    return story_fixture.__wrapped__(monkeypatch)


def receipt():
    return (
        Path(__file__).parents[1] / "docs/evidence/red-lorelei-story-admission-2026-09-23.json"
    ).read_bytes()


def actor(tmp_path, *, mock_weights=True):
    battler = FrozenTrainerBattler(
        None,
        None,
        tmp_path,
        "a" * 40,
        "root",
        "b" * 64,
        {},
        model_sha256=DAMAGE_STORY_SHA256,
        qualification_sha256=DAMAGE_STORY_ADMISSION_SHA256,
    )
    if mock_weights:
        battler.require_story_identity = lambda: None  # lifecycle fake only
    return battler


def contract():
    return red_story_battle.StoryTrainerContract(
        "defeat_lorelei",
        "cartridge-trainer-story",
        int(MapId.LORELEIS_ROOM),
        (244, 44, 1),
        int(EventFlag.BEAT_LORELEI),
        5400,
    )


def controller(tmp_path):
    return bridge.FrozenLoreleiStoryController(actor(tmp_path), contract(), receipt(), 73)


def test_admission_pinned_and_claimed_hash_does_not_hide_wrong_actual_weights(tmp_path):
    assert sha256(receipt()).hexdigest() == bridge.LORELEI_STORY_ADMISSION_SHA256
    with pytest.raises(ValueError, match="model object differs"):
        bridge.FrozenLoreleiStoryController(
            actor(tmp_path, mock_weights=False), contract(), receipt()
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "change",
    [
        {"admission": b"{}"},
        {"maximum_decisions": True},
        {"maximum_decisions": 81},
        {"contract": replace(contract(), objective_id="defeat_bruno")},
        {"contract": replace(contract(), victory_items=((1, 1),))},
        {"contract": replace(contract(), map_id=246)},
        {"contract": replace(contract(), defeated_event=8)},
    ],
)
def test_invalid_bindings_fail_before_input(tmp_path, change):
    args = dict(battler=actor(tmp_path), contract=contract(), admission=receipt())
    with pytest.raises(ValueError):
        bridge.FrozenLoreleiStoryController(**(args | change))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "objective,rematch",
    [
        ("defeat_bruno", False),
        ("defeat_agatha", False),
        ("defeat_lance", False),
        ("defeat_champion", False),
        ("defeat_lorelei", True),
    ],
)
def test_other_rooms_and_rematch_stay_closed(tmp_path, objective, rematch):
    runtime = NS(league_story_battle_controller=controller(tmp_path))
    with pytest.raises(ValueError):
        bridge.story_league_controller(runtime, objective, rematch=rematch)

def test_development_level_diagnostic_is_explicit_and_bound(fixture, tmp_path):
    skill, reader, inputs, observe, _ = fixture
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = ctl.controller_name
    skill.maximum_level_deficit = 100
    assert skill.availability(observe().game_state).executable
    skill.maximum_level_deficit = 99
    with pytest.raises(RuntimeError, match="level-screen"):
        skill.execute()
    assert not inputs

def test_level_diagnostic_does_not_change_teacher_default(fixture):
    skill, reader, inputs, observe, _ = fixture
    skill.maximum_level_deficit = 100
    assert not skill.availability(observe().game_state).executable
    assert not inputs


def test_income_default_and_conflicting_binding_fail_closed(tmp_path):
    candidate = controller(tmp_path)
    runtime = NS(league_story_battle_controller=candidate)
    assert bridge.story_league_controller(runtime, "defeat_lorelei") is candidate
    with pytest.raises(ValueError, match="not a K"):
        learned_league_controller(runtime)
    runtime.league_battle_controller = object()
    with pytest.raises(ValueError, match="conflicting"):
        bridge.story_league_controller(runtime, "defeat_lorelei")
    assert bridge.story_league_controller(NS(), "defeat_lorelei") is None


@pytest.mark.parametrize("mode", ["won", "lost", "unresolved"])
def test_real_story_lifecycle_retains_outcome_and_never_calls_teacher(tmp_path, monkeypatch, mode):
    ctl = controller(tmp_path)
    initial = RawGameState(
        True,
        245,
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
        read_active_trainer_identity=lambda: (244, 44, 1),
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
            n = int(EventFlag.BEAT_LORELEI)
            flags[n // 8] |= 1 << (n % 8)
            state.raw = replace(
                initial,
                battle_state=0,
                battle_result=0,
                player_money=32400,
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
        expected_map=245,
        intent=BattleIntent("defeat_lorelei", "cartridge-trainer-story"),
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


def test_story_skill_availability_binds_real_candidate_and_detects_mutation(fixture, tmp_path):
    skill, reader, inputs, observe, _ = fixture
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = ctl.controller_name
    assert skill.availability(observe().game_state).executable
    assert skill._battle_controller(reader) is ctl and not inputs
    ctl.maximum_decisions = 72
    with pytest.raises(RuntimeError, match="authority changed"):
        skill.execute()
    assert not inputs


@pytest.mark.parametrize(
    "mode", ["wrong_receipt", "wrong_quote", "wrong_controller", "rematch", "item"]
)
def test_story_skill_rejects_mismatch_without_inputs(fixture, tmp_path, mode):
    skill, reader, inputs, observe, _ = fixture
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = ctl.controller_name
    if mode == "wrong_receipt":
        ctl.admission = b"wrong"
    if mode == "wrong_quote":
        ctl.contract = replace(ctl.contract, victory_money=1)
    if mode == "wrong_controller":
        skill.recovery_controller = "frozen-k-development"
    if mode == "rematch":
        skill.rematch = True
    if mode == "item":
        skill.maximum_full_restores = 1
    assert not skill.availability(observe().game_state).executable
    assert not inputs


@pytest.mark.parametrize("fault", [None, "payout", "event", "bag", "species", "all_fainted"])
def test_outer_cartridge_verifier_still_checks_candidate_victory(tmp_path, monkeypatch, fault):
    from test_red_trainer_funding_battle import (
        TIMING,
        ScriptedEnvironment,
        make_candidate,
        make_state,
    )

    from pokemon_red_completion.red_trainer_funding_battle import (
        TrainerFundingBattleError,
        run_prepared_trainer_funding,
    )

    ctl = controller(tmp_path)
    initial = make_state(map_id=245, hp=(50, 0), flags=bytes(320))
    env = ScriptedEnvironment(initial, battle_identity=(244, 44, 244, 1), trainer_number=1)
    env.transitions = [(replace(initial, battle_state=2), False, True)]
    target = make_candidate(tc=244, ts=1, flag=2273, pay=5400)
    target = replace(target, trainer=replace(target.trainer, map_id=245))

    def play(self, reader, actions, **kwargs):
        flags = bytearray(320)
        if fault != "event":
            flags[284] |= 2
        env.state = replace(
            reader.read(),
            battle_state=0,
            battle_result=0,
            party_hp=(0, 0) if fault == "all_fainted" else (1, 0),
            party_species_ids=(1, 2) if fault == "species" else initial.party_species_ids,
            bag_items=() if fault == "bag" else initial.bag_items,
            event_flags=bytes(flags),
            player_money=500 if fault == "payout" else 5900,
        )
        return NS(outcome="won", field_ready=True, episode=NS(decisions=({"kind": "attack"},)))

    monkeypatch.setattr(red_story_battle.FrozenStoryBattleController, "run", play)

    def run():
        return run_prepared_trainer_funding(
            env,
            env,
            target=target,
            validate_target=lambda: None,
            move_slot_policy=lambda _: pytest.fail("teacher"),
            timing=TIMING,
            intent=BattleIntent("defeat_lorelei", "cartridge-trainer-story"),
            battle_runner_override=ctl.run,
        )

    if fault:
        with pytest.raises(TrainerFundingBattleError):
            run()
    else:
        assert run().payout == 5400 and env.state.party_hp == (1, 0)


def test_selected_skill_emits_candidate_not_k_evidence(fixture, tmp_path, monkeypatch):
    import pokemon_red_completion.red_trainer_story as story

    skill, reader, inputs, observe, _ = fixture
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = ctl.controller_name
    assert skill.availability(observe().game_state).executable
    monkeypatch.setattr(story, "prepare_trainer_lead", lambda *a, **k: None)

    def route(*a, **k):
        reader.raw = replace(reader.raw, map_id=245, player_y=3, player_x=5)
        return NS(passed=True)

    monkeypatch.setattr(story, "execute_route", route)
    monkeypatch.setattr(story, "face_pc_boundary", lambda *a: None)

    def battle(rdr, actions, **kwargs):
        assert kwargs["battle_runner_override"].__self__ is ctl
        kwargs["validate_target"]()
        flags = bytearray(rdr.raw.event_flags)
        flags[284] |= 2
        rdr.raw = replace(rdr.raw, event_flags=bytes(flags), player_money=6019)
        return NS(payout=5400)

    monkeypatch.setattr(story, "run_prepared_trainer_funding", battle)
    result = skill.execute()
    assert (
        result.evidence["authority"] == result.evidence["battle_controller"] == ctl.controller_name
    )
    assert result.evidence["learned_battle_authority"] and not result.evidence["bag_items_spent"]


@pytest.mark.parametrize("changed", ["map", "money", "identity"])
def test_direct_outer_bridge_rejects_wrong_target_before_interaction(tmp_path, changed):
    from test_red_trainer_funding_battle import ScriptedEnvironment, make_candidate, make_state

    from pokemon_red_completion.red_trainer_funding_battle import run_prepared_trainer_funding

    ctl = controller(tmp_path)
    env = ScriptedEnvironment(make_state(map_id=245))
    target = make_candidate(tc=244, ts=1, flag=2273, pay=5400)
    target = replace(target, trainer=replace(target.trainer, map_id=245))
    if changed == "map":
        target = replace(target, trainer=replace(target.trainer, map_id=246))
    elif changed == "money":
        target = replace(target, quote=replace(target.quote, expected_victory_money=1))
    else:
        target = replace(
            target,
            trainer=replace(target.trainer, trainer_set=2),
            quote=replace(target.quote, trainer_set=2),
        )
    with pytest.raises(ValueError, match="cartridge quote"):
        run_prepared_trainer_funding(
            env,
            env,
            target=target,
            validate_target=lambda: None,
            move_slot_policy=lambda _: pytest.fail("teacher"),
            timing=BattleRuntimeTiming(),
            intent=BattleIntent("defeat_lorelei", "cartridge-trainer-story"),
            battle_runner_override=ctl.run,
        )
    assert not env.actions
