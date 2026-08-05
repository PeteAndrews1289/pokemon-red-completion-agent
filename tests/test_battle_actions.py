from __future__ import annotations

import pytest

from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleActionKind,
    BattleBoostStat,
    BattleControlRequest,
    LearnedBattleControlRequest,
    control_request_matches,
)


def test_battle_actions_have_stable_game_neutral_references() -> None:
    assert BattleAction.move(3).semantic_ref == "pokemon.core:battle:move:3"
    assert BattleAction.recovery().semantic_ref == "pokemon.core:battle:recovery"
    assert (
        BattleAction.boost(BattleBoostStat.ACCURACY).semantic_ref
        == "pokemon.core:battle:boost:accuracy"
    )
    assert BattleAction.switch().semantic_ref == "pokemon.core:battle:switch:select"
    assert BattleAction.capture().semantic_ref == "pokemon.core:battle:capture"
    assert BattleAction.flee().semantic_ref == "pokemon.core:battle:flee"
    assert BattleAction.switch(4).public_dict() == {
        "kind": "switch",
        "semantic_ref": "pokemon.core:battle:switch:4",
        "move_slot": None,
        "party_slot": 4,
        "boost_stat": None,
    }
    assert BattleAction.from_dict(BattleAction.switch(4).public_dict()) == BattleAction.switch(4)


@pytest.mark.parametrize(
    "action",
    (
        BattleAction(BattleActionKind.USE_RECOVERY),
        BattleAction(BattleActionKind.USE_BOOST, boost_stat=BattleBoostStat.SPECIAL),
        BattleAction(BattleActionKind.SWITCH),
        BattleAction(BattleActionKind.ATTEMPT_CAPTURE),
        BattleAction(BattleActionKind.FLEE),
    ),
)
def test_control_request_preserves_non_move_action(action: BattleAction) -> None:
    assert BattleControlRequest(action).action == action


@pytest.mark.parametrize(
    "arguments",
    (
        {"kind": BattleActionKind.SELECT_MOVE},
        {"kind": BattleActionKind.SELECT_MOVE, "move_slot": 5},
        {"kind": BattleActionKind.USE_RECOVERY, "move_slot": 1},
        {"kind": BattleActionKind.USE_BOOST},
        {"kind": BattleActionKind.SWITCH, "party_slot": 7},
    ),
)
def test_battle_actions_reject_incompatible_parameters(arguments: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        BattleAction(**arguments)  # type: ignore[arg-type]


def test_control_request_rejects_move_actions() -> None:
    with pytest.raises(ValueError, match="return normally"):
        BattleControlRequest(BattleAction.move(1))


def test_learned_requests_match_teacher_handlers_by_semantic_action() -> None:
    request = LearnedBattleControlRequest(BattleAction.boost(BattleBoostStat.SPECIAL))
    assert control_request_matches(request, BattleAction.boost(BattleBoostStat.SPECIAL))
    assert not control_request_matches(request, BattleAction.boost(BattleBoostStat.ACCURACY))
    assert not control_request_matches(request, BattleAction.recovery())
