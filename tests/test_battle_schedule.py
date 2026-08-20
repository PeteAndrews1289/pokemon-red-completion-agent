from __future__ import annotations

from dataclasses import dataclass

import pytest

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.battle_schedule import (
    BattleScheduleError,
    BattleStartScheduleController,
    bind_battle_start_schedule,
    bound_battle_start_schedule,
)
from pokemon_red_completion.collection_protocol import BattleStartOffset


@dataclass(frozen=True)
class _Intent:
    battle_plan_id: str
    objective_id: str = "test_objective"


def _offsets() -> tuple[BattleStartOffset, ...]:
    return tuple(
        BattleStartOffset(battle_plan_id, index % 256)
        for index, battle_plan_id in enumerate(RED_BATTLE_PLAN_IDS)
    )


def test_controller_consumes_the_exact_frozen_route_once() -> None:
    controller = BattleStartScheduleController(_offsets())

    for index, battle_plan_id in enumerate(RED_BATTLE_PLAN_IDS):
        intent = _Intent(battle_plan_id)
        controller.start_or_resume(intent)
        controller.start_or_resume(intent)
        offset = controller.claim_at_main(intent)
        assert offset == BattleStartOffset(battle_plan_id, index % 256)
        controller.mark_applied(intent, offset)
        assert controller.claim_at_main(intent) is None
        controller.finish(intent)

    controller.require_complete()
    assert controller.finished_count == 74
    assert controller.expected_count == 74
    assert controller.failed is False


def test_controller_rejects_missing_reordered_and_extra_battles() -> None:
    missing = BattleStartScheduleController(_offsets())
    with pytest.raises(BattleScheduleError, match="missing an explicit intent"):
        missing.start_or_resume(None)
    assert missing.failed is True

    reordered = BattleStartScheduleController(_offsets())
    with pytest.raises(BattleScheduleError, match="order"):
        reordered.start_or_resume(_Intent(RED_BATTLE_PLAN_IDS[1]))
    assert reordered.failed is True

    extra = BattleStartScheduleController(_offsets())
    for battle_plan_id in RED_BATTLE_PLAN_IDS:
        intent = _Intent(battle_plan_id)
        extra.start_or_resume(intent)
        offset = extra.claim_at_main(intent)
        assert offset is not None
        extra.mark_applied(intent, offset)
        extra.finish(intent)
    with pytest.raises(BattleScheduleError, match="extra battle"):
        extra.start_or_resume(_Intent(RED_BATTLE_PLAN_IDS[-1]))


def test_controller_poisoning_prevents_partial_claim_retries() -> None:
    controller = BattleStartScheduleController(_offsets())
    intent = _Intent(RED_BATTLE_PLAN_IDS[0])
    controller.start_or_resume(intent)
    assert controller.claim_at_main(intent) is not None

    with pytest.raises(BattleScheduleError, match="claimed but not applied"):
        controller.claim_at_main(intent)
    with pytest.raises(BattleScheduleError, match="has failed"):
        controller.start_or_resume(intent)


def test_controller_keys_reentry_to_plan_identity_and_rejects_a_changed_plan() -> None:
    changed = BattleStartScheduleController(_offsets())
    first = _Intent(RED_BATTLE_PLAN_IDS[0])
    changed.start_or_resume(first)
    live_intent = _Intent(RED_BATTLE_PLAN_IDS[0], objective_id="live_capabilities_changed")
    changed.start_or_resume(live_intent)
    offset = changed.claim_at_main(live_intent)
    assert offset is not None
    changed.mark_applied(first, offset)
    changed.finish(live_intent)

    changed.start_or_resume(_Intent(RED_BATTLE_PLAN_IDS[1]))
    with pytest.raises(BattleScheduleError, match="identity changed"):
        changed.start_or_resume(_Intent(RED_BATTLE_PLAN_IDS[2]))

    unfinished = BattleStartScheduleController(_offsets())
    unfinished.start_or_resume(first)
    with pytest.raises(BattleScheduleError, match="before its offset was applied"):
        unfinished.finish(first)


def test_controller_can_close_one_externally_settled_active_battle_once() -> None:
    controller = BattleStartScheduleController(_offsets())
    intent = _Intent(RED_BATTLE_PLAN_IDS[0])
    controller.start_or_resume(intent)
    offset = controller.claim_at_main(intent)
    assert offset is not None
    controller.mark_applied(intent, offset)

    assert controller.finish_if_active(intent) is True
    assert controller.finish_if_active(intent) is False
    assert controller.finished_count == 1


def test_controller_requires_all_declared_battles_and_exact_roster() -> None:
    with pytest.raises(BattleScheduleError, match="cover"):
        BattleStartScheduleController(_offsets()[:-1])

    wrong = list(_offsets())
    wrong[1] = BattleStartOffset(RED_BATTLE_PLAN_IDS[0], 1)
    with pytest.raises(BattleScheduleError, match="match"):
        BattleStartScheduleController(wrong)

    controller = BattleStartScheduleController(_offsets())
    with pytest.raises(BattleScheduleError, match="incomplete"):
        controller.require_complete()


def test_binding_is_context_local_and_rejects_nesting() -> None:
    controller = BattleStartScheduleController(_offsets())
    assert bound_battle_start_schedule() is None

    with bind_battle_start_schedule(controller):
        assert bound_battle_start_schedule() is controller
        with (
            pytest.raises(BattleScheduleError, match="already bound"),
            bind_battle_start_schedule(BattleStartScheduleController(_offsets())),
        ):
            pass

    assert bound_battle_start_schedule() is None
