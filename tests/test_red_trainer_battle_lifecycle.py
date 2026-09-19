from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.observation import RawGameState
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

    return state, reader, SimpleNamespace(continue_battle=play), SimpleNamespace(execute=execute)


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
