from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_J_SHA256,
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
)
from pokemon_red_completion.red_trainer_battle_lifecycle import (
    TrainerBattleLifecycleError,
    continue_learned_trainer_battle,
)


def fixture(outcome="won", fault=None):
    initial = RawGameState(
        True,
        61,
        4,
        5,
        2,
        2,
        badge_bits=1,
        event_flags=bytes(4),
        party_species_ids=(107, 179),
        party_hp=(28, 0),
        party_max_hp=(28, 51),
        party_status=(0, 0),
        bag_items=((4, 3),),
        player_money=1706,
    )
    state = SimpleNamespace(raw=initial, dialogue=False, ready=True, actions=[], seen=[])
    reader = SimpleNamespace(
        read=lambda: state.raw,
        read_active_trainer_identity=lambda: (230, 30, 4),
        read_pokedex_state=lambda: SimpleNamespace(owned_species={7, 8, 41}),
        read_last_blackout_map=lambda: 3,
        read_input_readiness=lambda: SimpleNamespace(ready=state.ready),
        read_bottom_dialogue_box_visible=lambda: state.dialogue,
        read_total_pay_day_money=lambda: 0,
    )
    episode = SimpleNamespace(
        battle_won=outcome == "won",
        stop_reason={"won": "battle_won", "lost": "party_defeated"}.get(
            outcome,
            "decision_budget",
        ),
        public_dict=lambda: {"outcome": outcome},
    )

    def play(_reader, _executor, **kwargs):
        guard = kwargs["decision_guard"]
        guard(initial)  # Fainted reserve is allowed by this contract.
        if fault in {"bag", "party", "money", "hp", "map", "status"}:
            changes = {
                "bag": {"bag_items": ()},
                "party": {"party_species_ids": (1, 2)},
                "money": {"player_money": 9999},
                "hp": {"party_hp": (-1, 0)},
                "map": {"map_id": 4},
                "status": {"party_status": None},
            }[fault]
            guard(replace(initial, **changes))
            pytest.fail("mutated active state accepted")
        state.seen.append("model_replacement")
        if outcome == "won":
            state.raw = replace(
                initial,
                battle_state=0,
                battle_result=0,
                player_money=2186,
                event_flags=bytes((0, 1, 0, 0)),
                party_hp=(12, 0),
            )
            if fault == "payout":
                state.raw = replace(state.raw, player_money=2187)
            if fault == "event":
                state.raw = replace(state.raw, event_flags=bytes(4))
        elif outcome == "lost":
            state.raw = replace(initial, party_hp=(0, 0))
            state.dialogue = True
        return episode

    def execute(action):
        state.actions.append(action)
        if action.kind is MacroActionKind.CONFIRM:
            state.raw = replace(
                initial,
                battle_state=0,
                battle_result=1,
                player_money=853,
                map_id=3,
                party_hp=(28, 51),
            )
            state.dialogue = False
            if fault == "blackout_map":
                state.raw = replace(state.raw, map_id=4)
            if fault == "blackout_money":
                state.raw = replace(state.raw, player_money=1706)

    return (
        state,
        reader,
        SimpleNamespace(
            continue_battle=play, model_sha256=FROZEN_J_SHA256, qualification_sha256=None
        ),
        SimpleNamespace(execute=execute),
    )


@pytest.mark.parametrize("fault", [None, "scope", "entry", "guard_present", "payout"])
def test_poster_guard_needs_native_disappearance_and_exact_payout(fault):
    state, reader, battler, executor = fixture()
    initial = replace(state.raw, map_id=135)
    state.raw = initial
    state.present = fault != "entry"
    reader.read_current_map_objects = lambda: (
        (SimpleNamespace(sprite_index=11, picture_id=24),) if state.present else ()
    )
    reader.read_active_trainer_identity = lambda: (230, 30, 7)
    battler.model_sha256 = FROZEN_K_SHA256
    battler.qualification_sha256 = K_QUALIFICATION_SHA256

    def play(*a, **kw):
        kw["decision_guard"](state.raw)
        state.raw = replace(
            initial,
            battle_state=0,
            battle_result=0,
            player_money=2187 if fault == "payout" else 2186,
        )
        state.present = fault == "guard_present"
        return SimpleNamespace(battle_won=True, stop_reason="battle_won")

    battler.continue_battle = play
    executor.execute = lambda action: state.actions.append(action)
    kwargs = dict(
        trainer_identity=(230, 30, 7),
        defeated_event=None,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        story_authority=fault != "scope",
        maximum_settle_pulses=2,
    )
    if fault:
        with pytest.raises((ValueError, TrainerBattleLifecycleError)):
            continue_learned_trainer_battle(battler, reader, executor, **kwargs)
    else:
        assert continue_learned_trainer_battle(battler, reader, executor, **kwargs).outcome == "won"
    assert not any(a.kind is MacroActionKind.CONFIRM for a in state.actions)


@pytest.mark.parametrize("count,qualified", [(3, True), (4, True), (6, True), (4, False)])
def test_retained_k_party_scope_and_decision_remainder(count, qualified):
    state, reader, battler, executor = fixture("unresolved")
    state.raw = replace(
        state.raw,
        party_count=count,
        party_species_ids=(107,) * count,
        party_hp=(28,) * (count - 1) + (0,),
        party_max_hp=(28,) * count,
        party_status=(0,) * count,
    )
    battler.model_sha256 = FROZEN_K_SHA256
    battler.qualification_sha256 = K_QUALIFICATION_SHA256 if qualified else None
    calls = []

    def play(_reader, _executor, **kwargs):
        kwargs["decision_guard"](state.raw)
        calls.append(kwargs["maximum_decisions"])
        return SimpleNamespace(battle_won=False, stop_reason="decision_budget")

    battler.continue_battle = play
    kwargs = dict(
        trainer_identity=(230, 30, 4),
        defeated_event=8,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        remaining_decisions=79,
    )
    if qualified:
        result = continue_learned_trainer_battle(battler, reader, executor, **kwargs)
        assert result.outcome == "unresolved" and calls == [79]
    else:
        with pytest.raises(TrainerBattleLifecycleError):
            continue_learned_trainer_battle(battler, reader, executor, **kwargs)
        assert not calls


@pytest.mark.parametrize("fault", [None, "undeclared", "active", "event", "extra"])
def test_story_rewards_only_after_verified_victory(fault):
    state, reader, battler, executor = fixture()
    battler.model_sha256 = FROZEN_K_SHA256
    battler.qualification_sha256 = K_QUALIFICATION_SHA256
    original = battler.continue_battle

    def play(*a, **kw):
        if fault == "active":
            kw["decision_guard"](replace(state.raw, bag_items=((4, 3), (246, 1))))
        result = original(*a, **kw)
        state.raw = replace(
            state.raw,
            bag_items=((4, 3), (246, 2 if fault == "extra" else 1)),
            badge_bits=33,
            event_flags=bytes(4) if fault == "event" else state.raw.event_flags,
        )
        return result

    battler.continue_battle = play
    kwargs = dict(
        trainer_identity=(230, 30, 4),
        defeated_event=8,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        story_authority=True,
    )
    if fault != "undeclared":
        kwargs.update(victory_items=((246, 1),), victory_badge_bits=32)
    if fault:
        with pytest.raises(TrainerBattleLifecycleError):
            continue_learned_trainer_battle(battler, reader, executor, **kwargs)
    else:
        assert continue_learned_trainer_battle(battler, reader, executor, **kwargs).outcome == "won"


@pytest.mark.parametrize("outcome", ["won", "lost"])
@pytest.mark.parametrize("fault", [None, "scope", "entry", "terminal", "payout"])
def test_ship_rival_uses_native_room_script_and_retains_money_proof(outcome, fault):
    state, reader, battler, executor = fixture(outcome)
    initial = replace(state.raw, map_id=96)
    state.raw, state.stage = initial, (1 if fault == "entry" else 2)
    reader.read_ss_anne_rival_script = lambda: state.stage
    reader.read_active_trainer_identity = lambda: (242, 42, 1)
    battler.model_sha256 = FROZEN_K_SHA256
    battler.qualification_sha256 = K_QUALIFICATION_SHA256

    def play(*args, **kwargs):
        kwargs["decision_guard"](state.raw)
        state.stage = 3 if fault == "terminal" else (4 if outcome == "won" else 0)
        if outcome == "won":
            state.raw = replace(
                initial,
                battle_state=0,
                battle_result=0,
                player_money=2187 if fault == "payout" else 2186,
                party_hp=(12, 0),
            )
        else:
            state.raw = replace(initial, party_hp=(0, 0))
            state.dialogue = True
        return SimpleNamespace(
            battle_won=outcome == "won",
            stop_reason="battle_won" if outcome == "won" else "party_defeated",
        )

    battler.continue_battle = play
    original = executor.execute

    def execute(action):
        original(action)
        if fault == "payout" and outcome == "lost":
            state.raw = replace(state.raw, player_money=1706)

    executor.execute = execute
    kwargs = dict(
        trainer_identity=(242, 42, 1),
        defeated_event=None,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        story_authority=fault != "scope",
    )
    if fault:
        with pytest.raises((TrainerBattleLifecycleError, ValueError)):
            continue_learned_trainer_battle(battler, reader, executor, **kwargs)
    else:
        assert (
            continue_learned_trainer_battle(battler, reader, executor, **kwargs).outcome == outcome
        )


def run(f):
    _, reader, battler, executor = f
    return continue_learned_trainer_battle(
        battler,
        reader,
        executor,
        trainer_identity=(230, 30, 4),
        defeated_event=8,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
    )


@pytest.mark.parametrize("fault", [None, "payout", "event", "result"])
def test_field_roster_alias_requires_independent_native_win_proof(fault):
    f = fixture("won", fault=fault)
    state, _, battler, _ = f
    original = battler.continue_battle

    def aliased(*args, **kwargs):
        episode = original(*args, **kwargs)
        episode.battle_won = False
        episode.stop_reason = "battle_exited_without_win"
        if fault == "result":
            state.raw = replace(state.raw, battle_result=1)
        return episode

    battler.continue_battle = aliased
    if fault in {"payout", "event"}:
        with pytest.raises(TrainerBattleLifecycleError, match="verification"):
            run(f)
    else:
        result = run(f)
        assert result.outcome == ("unresolved" if fault else "won")
        # Preserve the raw episode classification, even in new receipts.
        assert result.episode.stop_reason == "battle_exited_without_win"
        assert not state.actions


@pytest.mark.parametrize("cash,payday,expected", [(999900, 0, 999999), (1706, 120, 2306)])
def test_roster_alias_win_accounts_for_capped_cash_and_payday(cash, payday, expected):
    f = fixture("won")
    state, reader, battler, _ = f
    state.raw = replace(state.raw, player_money=cash)
    initial = state.raw
    reader.read_total_pay_day_money = lambda: payday

    def play(*args, **kwargs):
        kwargs["decision_guard"](initial)
        state.raw = replace(
            initial,
            battle_state=0,
            battle_result=0,
            player_money=expected,
            event_flags=bytes((0, 1, 0, 0)),
        )
        return SimpleNamespace(battle_won=False, stop_reason="battle_exited_without_win")

    battler.continue_battle = play
    assert run(f).outcome == "won"


@pytest.mark.parametrize("outcome", ["won", "lost", "unresolved"])
def test_battle_outcomes_are_distinct_from_funding_acceptance(outcome):
    f = fixture(outcome)
    result = run(f)
    assert result.outcome == outcome
    assert result.field_ready == (outcome != "unresolved")
    assert result.recovery_required == (outcome != "lost")
    assert 2 in result.fainted_party_slots
    assert result.money_delta == {"won": 480, "lost": -853, "unresolved": 0}[outcome]
    assert result.public_dict()["funding_success"] is False
    assert result.public_dict()["no_faint_constraint_met"] is False
    assert f[0].seen == ["model_replacement"]
    if outcome != "lost":
        assert f[0].actions == []


@pytest.mark.parametrize(
    "fault",
    [
        "bag",
        "party",
        "money",
        "hp",
        "map",
        "status",
        "payout",
        "event",
        "blackout_map",
        "blackout_money",
    ],
)
def test_integrity_and_terminal_verification_are_not_relaxed(fault):
    f = fixture("lost" if fault.startswith("blackout") else "won", fault)
    with pytest.raises(TrainerBattleLifecycleError):
        run(f)


def test_original_strict_funding_verifier_still_rejects_faints():
    from test_red_trainer_funding_battle import make_candidate, make_state

    from pokemon_red_completion.red_trainer_funding_battle import (
        TrainerFundingBattleError,
        _check_postbattle_fatal,
    )

    target = make_candidate()
    initial = make_state()
    final = replace(initial, party_hp=tuple(0 for _ in initial.party_hp))
    with pytest.raises(TrainerFundingBattleError, match="fainted"):
        _check_postbattle_fatal(final, initial, target)


def test_settlement_budget_and_no_unowned_battle_choice():
    f = fixture("lost")
    f[3].execute = lambda action: None
    with pytest.raises(TrainerBattleLifecycleError, match="pulse budget"):
        run(f)


def test_registration_loss_rejects_otherwise_valid_win():
    f = fixture()
    values = iter(({7, 8, 41}, {7, 8}))
    f[1].read_pokedex_state = lambda: SimpleNamespace(owned_species=next(values))
    with pytest.raises(TrainerBattleLifecycleError, match="handoff"):
        run(f)
