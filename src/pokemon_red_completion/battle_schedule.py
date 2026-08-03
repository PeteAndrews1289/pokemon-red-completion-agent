"""Strict collection-harness scheduling for preregistered battle variation.

The controller owns only immutable schedule state. It cannot read the game,
choose an action, or operate the emulator. The battle runtime remains the sole
caller that may translate a claimed offset into a semantic WAIT action.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.collection_protocol import (
    BattleStartOffset,
    battle_start_offsets_sha256,
)


class BattleScheduleError(RuntimeError):
    """Raised when a planned collection run diverges from its frozen roster."""


class BattlePlanIntent(Protocol):
    """Minimal immutable intent view needed by the collection harness."""

    @property
    def battle_plan_id(self) -> str: ...


class BattleStartScheduleController:
    """Consume one frozen timing offset for every expected physical battle."""

    __slots__ = (
        "_active_intent",
        "_applied",
        "_claimed",
        "_failed",
        "_next_index",
        "_offsets",
        "_schedule_sha256",
    )

    def __init__(self, offsets: Sequence[BattleStartOffset]) -> None:
        frozen = tuple(offsets)
        if len(frozen) != len(RED_BATTLE_PLAN_IDS):
            raise BattleScheduleError("battle-start schedule does not cover the qualified route")
        for index, offset in enumerate(frozen):
            if not isinstance(offset, BattleStartOffset):
                raise TypeError("battle-start offsets must be BattleStartOffset values")
            if offset.battle_plan_id != RED_BATTLE_PLAN_IDS[index]:
                raise BattleScheduleError(
                    "battle-start schedule does not match the qualified route"
                )
            if (
                type(offset.frames) is not int  # noqa: E721
                or not 0 <= offset.frames <= 255
            ):
                raise BattleScheduleError(
                    "battle-start offset must be an integer from 0 through 255"
                )
        self._offsets = frozen
        self._schedule_sha256 = battle_start_offsets_sha256(frozen)
        self._next_index = 0
        self._active_intent: BattlePlanIntent | None = None
        self._claimed: BattleStartOffset | None = None
        self._applied = False
        self._failed = False

    @property
    def finished_count(self) -> int:
        return self._next_index

    @property
    def expected_count(self) -> int:
        return len(self._offsets)

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def schedule_sha256(self) -> str:
        return self._schedule_sha256

    def start_or_resume(self, intent: BattlePlanIntent | None) -> None:
        """Start the next declared battle or resume the identical active one."""

        self._require_healthy()
        if intent is None or not isinstance(getattr(intent, "battle_plan_id", None), str):
            self._fail("planned battle is missing an explicit intent")
        if self._active_intent is not None:
            if intent != self._active_intent:
                self._fail("planned battle intent changed during re-entry")
            return
        if self._next_index >= len(self._offsets):
            self._fail("planned run observed an unexpected extra battle")
        expected = self._offsets[self._next_index]
        if intent.battle_plan_id != expected.battle_plan_id:
            self._fail("planned battle order does not match the frozen roster")
        self._active_intent = intent
        self._claimed = None
        self._applied = False

    def claim_at_main(
        self,
        intent: BattlePlanIntent | None,
    ) -> BattleStartOffset | None:
        """Claim the active offset once at the first stable main-menu boundary."""

        self._require_active(intent)
        if self._applied:
            return None
        if self._claimed is not None:
            self._fail("planned battle offset was claimed but not applied")
        self._claimed = self._offsets[self._next_index]
        return self._claimed

    def mark_applied(
        self,
        intent: BattlePlanIntent | None,
        offset: BattleStartOffset,
    ) -> None:
        """Commit a claim only after runtime WAIT and semantic revalidation."""

        self._require_active(intent)
        if self._claimed is None or offset != self._claimed or self._applied:
            self._fail("planned battle offset application is inconsistent")
        self._applied = True

    def mark_failed(self) -> None:
        """Permanently poison a partially applied or semantically invalid plan."""

        self._failed = True

    def finish(self, intent: BattlePlanIntent | None) -> None:
        """Close exactly one battle after its offset was safely applied."""

        self._require_active(intent)
        if not self._applied:
            self._fail("planned battle ended before its offset was applied")
        self._next_index += 1
        self._active_intent = None
        self._claimed = None
        self._applied = False

    def finish_if_active(self, intent: BattlePlanIntent | None) -> bool:
        """Close a matching battle settled by a bounded external recovery path."""

        self._require_healthy()
        if self._active_intent is None:
            return False
        self.finish(intent)
        return True

    def require_complete(self) -> None:
        """Fail unless every declared battle finished exactly once."""

        self._require_healthy()
        if self._active_intent is not None or self._next_index != len(self._offsets):
            self._fail("planned battle-start schedule is incomplete")

    def _require_active(self, intent: BattlePlanIntent | None) -> None:
        self._require_healthy()
        if self._active_intent is None:
            self._fail("planned battle schedule has no active battle")
        if intent is None or intent != self._active_intent:
            self._fail("planned battle intent does not match the active battle")

    def _require_healthy(self) -> None:
        if self._failed:
            raise BattleScheduleError("planned battle-start schedule has failed")

    def _fail(self, message: str) -> None:
        self._failed = True
        raise BattleScheduleError(message)


_BOUND_BATTLE_START_SCHEDULE: ContextVar[BattleStartScheduleController | None] = ContextVar(
    "pokemon_red_battle_start_schedule", default=None
)


@contextmanager
def bind_battle_start_schedule(
    controller: BattleStartScheduleController,
) -> Iterator[None]:
    """Bind one schedule to the current full-run execution context."""

    if not isinstance(controller, BattleStartScheduleController):
        raise TypeError("controller must be a BattleStartScheduleController")
    if _BOUND_BATTLE_START_SCHEDULE.get() is not None:
        raise BattleScheduleError("a battle-start schedule is already bound")
    token = _BOUND_BATTLE_START_SCHEDULE.set(controller)
    try:
        yield
    finally:
        _BOUND_BATTLE_START_SCHEDULE.reset(token)


def bound_battle_start_schedule() -> BattleStartScheduleController | None:
    """Return the concurrency-local collection schedule, when one is bound."""

    return _BOUND_BATTLE_START_SCHEDULE.get()
