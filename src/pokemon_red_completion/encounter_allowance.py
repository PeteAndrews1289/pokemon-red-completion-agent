"""Prospective encounter-count ceilings, separate from execution/resources.

Opt in when binding a new session. Never rewrite a frozen attempt. Hunting
counts every encountered Pokemon, not just escapes, and requires capture-specific
resource limits; a hunting allowance does not grant travel's flee policy.
"""

from collections.abc import Callable
from dataclasses import dataclass

from .actions import MacroAction, MacroActionKind
from .route_executor import RouteActionPort

TRAVEL_ENCOUNTER_CEILING = 512
HUNTING_ENCOUNTER_CEILING = 4096


@dataclass(frozen=True, slots=True)
class EncounterAllowance:
    maximum: int
    previously_consumed: int = 0

    def __post_init__(self) -> None:
        if type(self.maximum) is not int or self.maximum <= 0:
            raise ValueError("encounter maximum must be a positive integer")
        if (
            type(self.previously_consumed) is not int
            or not 0 <= self.previously_consumed <= self.maximum
        ):
            raise ValueError("prior encounter cost must be an integer within the ceiling")

    @property
    def remaining(self) -> int:
        return self.maximum - self.previously_consumed

    def require_capacity(self, consumed: int) -> None:
        if type(consumed) is not int or consumed < 0:
            raise ValueError("current encounter cost must be a non-negative integer")
        if consumed >= self.remaining:
            raise ValueError("encounter allowance exhausted; stopped before further movement")


@dataclass
class EncounterLimitedMovementPort:
    """Stop before the next move at the count ceiling, not inside a wild battle.

    The bound encounter handler must append its settled receipt only after recovery;
    menus/waits still pass through the existing action/frame/resource safeguards.
    The same receipt counter must be shared across every route leg in the session.
    """

    delegate: RouteActionPort
    allowance: EncounterAllowance
    consumed: Callable[[], int]

    def execute(self, action: MacroAction):
        if action.kind is MacroActionKind.MOVE:
            self.allowance.require_capacity(self.consumed())
        return self.delegate.execute(action)
