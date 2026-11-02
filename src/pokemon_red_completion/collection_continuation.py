"""Title-neutral continuation boundaries and cumulative lifetime accounting.

This module provides the ROM-free core for bounded collection continuation:
typed session directives, distinct stop reasons, cumulative budget accounting,
and progress evaluation.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ContinuationDirective(StrEnum):
    """Next structural action determined by continuation policy."""

    CONTINUE_SAME_GOAL = "continue_same_goal"
    REPLAN = "replan"
    COMPLETE = "complete"
    SAFE_STOP = "safe_stop"
    AMBIGUOUS_STOP = "ambiguous_stop"


class ContinuationStopReason(StrEnum):
    """Distinct typed reason codes for stopping a chunk or campaign."""

    BALLS_EXHAUSTED = "balls_exhausted"
    STEPS_RESERVE_EXHAUSTED = "steps_reserve_exhausted"
    ENCOUNTER_CAP_REACHED = "encounter_cap_reached"
    LOCAL_QUANTUM_EXHAUSTED = "local_quantum_exhausted"
    GLOBAL_ACTION_BUDGET_EXHAUSTED = "global_action_budget_exhausted"
    GLOBAL_FRAME_BUDGET_EXHAUSTED = "global_frame_budget_exhausted"
    DECISION_BUDGET_EXHAUSTED = "decision_budget_exhausted"
    CHUNK_BUDGET_EXHAUSTED = "chunk_budget_exhausted"
    CASH_BUDGET_EXHAUSTED = "cash_budget_exhausted"
    WALL_TIME_EXHAUSTED = "wall_time_exhausted"
    NO_PROGRESS_LIMIT_EXHAUSTED = "no_progress_limit_exhausted"
    GOAL_COMPLETED = "goal_completed"
    STORAGE_BLOCKED = "storage_blocked"
    SESSION_ENDED = "session_ended"
    UNSAFE_TERMINAL = "unsafe_terminal"
    VERIFICATION_FAILED = "verification_failed"
    AMBIGUOUS_EXECUTION = "ambiguous_execution"
    UNKNOWN_ERROR = "unknown_error"


class ContinuationBudgetExhausted(RuntimeError):
    """Raised when a shared budget cannot accommodate the requested operation."""

    def __init__(self, reason: ContinuationStopReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail


def _validate_non_negative_int(name: str, value: Any) -> int:
    if type(value) is not int:  # Reject bool-as-int and non-integers explicitly
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def _validate_positive_int(name: str, value: Any) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class ContinuationBudgetCaps:
    """Declared finite caps across one autonomous collection campaign."""

    maximum_decisions: int = 3
    maximum_continuation_chunks_per_goal: int = 5
    maximum_continuation_chunks_per_campaign: int = 15
    maximum_actions: int = 30_000
    maximum_frames: int = 3_000_000
    maximum_cash_spend: int = 5_000
    maximum_encounters: int = 1_000
    maximum_consecutive_no_progress: int = 3
    maximum_wall_seconds: float = 7_200.0

    def __post_init__(self) -> None:
        _validate_positive_int("maximum_decisions", self.maximum_decisions)
        _validate_positive_int(
            "maximum_continuation_chunks_per_goal",
            self.maximum_continuation_chunks_per_goal,
        )
        _validate_positive_int(
            "maximum_continuation_chunks_per_campaign",
            self.maximum_continuation_chunks_per_campaign,
        )
        if (
            self.maximum_continuation_chunks_per_goal
            > self.maximum_continuation_chunks_per_campaign
        ):
            raise ValueError(
                "chunks per goal cannot exceed chunks per campaign: "
                f"{self.maximum_continuation_chunks_per_goal} > "
                f"{self.maximum_continuation_chunks_per_campaign}"
            )
        _validate_positive_int("maximum_actions", self.maximum_actions)
        _validate_positive_int("maximum_frames", self.maximum_frames)
        _validate_non_negative_int("maximum_cash_spend", self.maximum_cash_spend)
        _validate_non_negative_int("maximum_encounters", self.maximum_encounters)
        _validate_positive_int(
            "maximum_consecutive_no_progress", self.maximum_consecutive_no_progress
        )

        if type(self.maximum_wall_seconds) is bool:
            raise TypeError("maximum_wall_seconds cannot be a bool")
        if not isinstance(self.maximum_wall_seconds, (int, float)):
            raise TypeError(
                "maximum_wall_seconds must be a float, got "
                f"{type(self.maximum_wall_seconds).__name__}"
            )
        if not math.isfinite(self.maximum_wall_seconds) or self.maximum_wall_seconds <= 0:
            raise ValueError(
                f"maximum_wall_seconds must be positive and finite, got {self.maximum_wall_seconds}"
            )


@dataclass(frozen=True, slots=True)
class ContinuationPolicy:
    """Declared execution policy parameters for continuation chunks."""

    step_reserve: int = 50
    local_action_quantum: int = 2_000
    local_frame_quantum: int = 200_000
    local_encounter_quantum: int = 10

    def __post_init__(self) -> None:
        _validate_positive_int("step_reserve", self.step_reserve)
        _validate_positive_int("local_action_quantum", self.local_action_quantum)
        _validate_positive_int("local_frame_quantum", self.local_frame_quantum)
        _validate_positive_int("local_encounter_quantum", self.local_encounter_quantum)


class ContinuationBudgetLedger:
    """Cumulative accounting, not a controller-input enforcement wrapper.

    Callers must constrain actual execution before inputs. Settlement records
    observed overruns and raises; it never erases the work already performed.
    Live orchestration is deliberately unavailable until that wiring is qualified.
    """

    def __init__(
        self,
        caps: ContinuationBudgetCaps,
        *,
        clock: Callable[[], float],
        start_time: float | None = None,
        elapsed_seconds: float = 0.0,
        decisions_used: int = 0,
        goal_continuation_chunks: int = 0,
        campaign_continuation_chunks: int = 0,
        actions_spent: int = 0,
        frames_spent: int = 0,
        cash_spent: int = 0,
        encounters_seen: int = 0,
        consecutive_no_progress: int = 0,
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.caps = caps
        self._clock = clock

        now = float(self._clock())
        if not math.isfinite(now):
            raise ValueError("clock returned non-finite timestamp")

        self.start_time = now if start_time is None else float(start_time)
        if not math.isfinite(self.start_time):
            raise ValueError("start_time must be finite")

        if type(elapsed_seconds) is bool or not isinstance(elapsed_seconds, (int, float)):
            raise TypeError("elapsed_seconds must be numeric")
        if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite non-negative")
        self._prior_elapsed = float(elapsed_seconds)
        self._session_start_clock = now
        self._max_seen_session_elapsed = 0.0

        self.decisions_used = _validate_non_negative_int("decisions_used", decisions_used)
        self.goal_continuation_chunks = _validate_non_negative_int(
            "goal_continuation_chunks", goal_continuation_chunks
        )
        self.campaign_continuation_chunks = _validate_non_negative_int(
            "campaign_continuation_chunks", campaign_continuation_chunks
        )
        self.actions_spent = _validate_non_negative_int("actions_spent", actions_spent)
        self.frames_spent = _validate_non_negative_int("frames_spent", frames_spent)
        self.cash_spent = _validate_non_negative_int("cash_spent", cash_spent)
        self.encounters_seen = _validate_non_negative_int("encounters_seen", encounters_seen)
        self.consecutive_no_progress = _validate_non_negative_int(
            "consecutive_no_progress", consecutive_no_progress
        )

        self._in_flight_action_reservation = 0

    @property
    def elapsed_seconds(self) -> float:
        now = float(self._clock())
        if not math.isfinite(now):
            raise ValueError("clock returned non-finite timestamp")
        # Handle clock rollback conservatively: time never rolls backward
        current_session = now - self._session_start_clock
        if current_session > self._max_seen_session_elapsed:
            self._max_seen_session_elapsed = current_session
        return self._prior_elapsed + self._max_seen_session_elapsed

    @property
    def remaining_wall_seconds(self) -> float:
        return max(0.0, self.caps.maximum_wall_seconds - self.elapsed_seconds)

    @property
    def is_wall_time_exhausted(self) -> bool:
        return self.elapsed_seconds >= self.caps.maximum_wall_seconds

    def check_preflight_budget(self) -> ContinuationStopReason | None:
        """Check whether budget allows the next costly operation."""
        if self.is_wall_time_exhausted:
            return ContinuationStopReason.WALL_TIME_EXHAUSTED
        if self.actions_spent >= self.caps.maximum_actions:
            return ContinuationStopReason.GLOBAL_ACTION_BUDGET_EXHAUSTED
        if self.frames_spent >= self.caps.maximum_frames:
            return ContinuationStopReason.GLOBAL_FRAME_BUDGET_EXHAUSTED
        if self.campaign_continuation_chunks >= self.caps.maximum_continuation_chunks_per_campaign:
            return ContinuationStopReason.CHUNK_BUDGET_EXHAUSTED
        if self.consecutive_no_progress >= self.caps.maximum_consecutive_no_progress:
            return ContinuationStopReason.NO_PROGRESS_LIMIT_EXHAUSTED
        if self.cash_spent > self.caps.maximum_cash_spend:
            return ContinuationStopReason.CASH_BUDGET_EXHAUSTED
        if self.encounters_seen > self.caps.maximum_encounters:
            return ContinuationStopReason.CHUNK_BUDGET_EXHAUSTED
        return None

    def admit_decision(self) -> None:
        """Admit a new model decision and reset per-goal continuation chunks."""
        exhausted = self.check_preflight_budget()
        if exhausted is not None:
            raise ContinuationBudgetExhausted(
                exhausted, f"cannot admit decision: {exhausted.value}"
            )
        if self.decisions_used >= self.caps.maximum_decisions:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.DECISION_BUDGET_EXHAUSTED,
                f"decision cap reached: {self.decisions_used}/{self.caps.maximum_decisions}",
            )
        self.decisions_used += 1
        self.goal_continuation_chunks = 0

    def admit_continuation_chunk(self) -> None:
        """Admit a same-goal continuation chunk under goal and campaign caps."""
        exhausted = self.check_preflight_budget()
        if exhausted is not None:
            raise ContinuationBudgetExhausted(
                exhausted, f"cannot admit continuation chunk: {exhausted.value}"
            )
        if self.goal_continuation_chunks >= self.caps.maximum_continuation_chunks_per_goal:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.CHUNK_BUDGET_EXHAUSTED,
                f"goal continuation cap reached: {self.goal_continuation_chunks}/"
                f"{self.caps.maximum_continuation_chunks_per_goal}",
            )
        if self.campaign_continuation_chunks >= self.caps.maximum_continuation_chunks_per_campaign:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.CHUNK_BUDGET_EXHAUSTED,
                f"campaign continuation cap reached: {self.campaign_continuation_chunks}/"
                f"{self.caps.maximum_continuation_chunks_per_campaign}",
            )
        self.goal_continuation_chunks += 1
        self.campaign_continuation_chunks += 1

    def reserve_actions(self, count: int) -> int:
        """Reserve actions before an expensive operation. Returns allocated amount."""
        _validate_positive_int("reserve count", count)
        exhausted = self.check_preflight_budget()
        if exhausted is not None:
            raise ContinuationBudgetExhausted(exhausted, "campaign budget exhausted")
        remaining = self.caps.maximum_actions - (
            self.actions_spent + self._in_flight_action_reservation
        )
        if remaining <= 0:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.GLOBAL_ACTION_BUDGET_EXHAUSTED,
                f"no actions remaining: {self.actions_spent}/{self.caps.maximum_actions}",
            )
        allocated = min(count, remaining)
        self._in_flight_action_reservation += allocated
        return allocated

    def settle_actions(
        self,
        *,
        attempted: int,
        completed: int,
        frames: int,
    ) -> None:
        """Settle in-flight action reservation with verified attempted and completed counts."""
        _validate_non_negative_int("attempted actions", attempted)
        _validate_non_negative_int("completed actions", completed)
        _validate_non_negative_int("frames", frames)
        if completed > attempted:
            raise ValueError(f"completed ({completed}) cannot exceed attempted ({attempted})")

        # Every attempted action consumes global budget
        reservation = self._in_flight_action_reservation
        self.actions_spent += attempted
        self.frames_spent += frames
        self._in_flight_action_reservation = 0
        if self.actions_spent > self.caps.maximum_actions or (
            reservation and attempted > reservation
        ):
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.GLOBAL_ACTION_BUDGET_EXHAUSTED,
                "observed action overrun retained; caller did not enforce its reservation",
            )
        if self.frames_spent > self.caps.maximum_frames:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.GLOBAL_FRAME_BUDGET_EXHAUSTED,
                "observed frame overrun retained",
            )

    def record_cash_spend(self, amount: int) -> None:
        """Record verified actual cash spend (non-negative delta)."""
        _validate_non_negative_int("cash spend", amount)
        self.cash_spent += amount
        if self.cash_spent > self.caps.maximum_cash_spend:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.CASH_BUDGET_EXHAUSTED,
                f"cash spend ({self.cash_spent}) exceeds cap {self.caps.maximum_cash_spend}",
            )

    def record_encounters(self, count: int) -> None:
        _validate_non_negative_int("encounters", count)
        self.encounters_seen += count
        if self.encounters_seen > self.caps.maximum_encounters:
            raise ContinuationBudgetExhausted(
                ContinuationStopReason.CHUNK_BUDGET_EXHAUSTED,
                "observed encounter overrun retained",
            )

    def record_progress(self, made_progress: bool) -> None:
        if type(made_progress) is not bool:
            raise TypeError("made_progress must be a bool")
        if made_progress:
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1

    def remaining_budgets(self) -> dict[str, Any]:
        return {
            "decisions": max(0, self.caps.maximum_decisions - self.decisions_used),
            "goal_continuation_chunks": max(
                0,
                self.caps.maximum_continuation_chunks_per_goal - self.goal_continuation_chunks,
            ),
            "campaign_continuation_chunks": max(
                0,
                self.caps.maximum_continuation_chunks_per_campaign
                - self.campaign_continuation_chunks,
            ),
            "actions": max(0, self.caps.maximum_actions - self.actions_spent),
            "frames": max(0, self.caps.maximum_frames - self.frames_spent),
            "cash": max(0, self.caps.maximum_cash_spend - self.cash_spent),
            "encounters": max(0, self.caps.maximum_encounters - self.encounters_seen),
            "consecutive_no_progress_remaining": max(
                0,
                self.caps.maximum_consecutive_no_progress - self.consecutive_no_progress,
            ),
            "wall_seconds": self.remaining_wall_seconds,
        }

    def to_dict(self) -> dict[str, Any]:
        if self._in_flight_action_reservation:
            raise ValueError("cannot checkpoint an unsettled action reservation")
        return {
            "schema": "pokemon.core.continuation-budget-ledger.v2",
            "caps": asdict(self.caps),
            "elapsed_seconds": self.elapsed_seconds,
            "decisions_used": self.decisions_used,
            "goal_continuation_chunks": self.goal_continuation_chunks,
            "campaign_continuation_chunks": self.campaign_continuation_chunks,
            "actions_spent": self.actions_spent,
            "frames_spent": self.frames_spent,
            "cash_spent": self.cash_spent,
            "encounters_seen": self.encounters_seen,
            "consecutive_no_progress": self.consecutive_no_progress,
            "remaining": self.remaining_budgets(),
        }

    @classmethod
    def inherit_from(
        cls,
        parent_ledger_data: Mapping[str, Any],
        caps: ContinuationBudgetCaps,
        *,
        clock: Callable[[], float],
        downtime_seconds: float,
    ) -> ContinuationBudgetLedger:
        """Create a new ledger inheriting elapsed costs and remaining budgets."""
        saved_caps = parent_ledger_data.get("caps")
        if not isinstance(saved_caps, Mapping):
            raise ValueError("missing immutable caps")
        validated_caps = ContinuationBudgetCaps(**saved_caps)
        if (
            parent_ledger_data.get("schema") != "pokemon.core.continuation-budget-ledger.v2"
            or validated_caps != caps
            or saved_caps != asdict(caps)
        ):
            raise ValueError("ledger schema or immutable caps differ")
        if (
            type(downtime_seconds) not in (int, float)
            or not math.isfinite(downtime_seconds)
            or downtime_seconds < 0
        ):
            raise ValueError("resume downtime must be explicit, finite and non-negative")
        names = (
            "decisions_used",
            "goal_continuation_chunks",
            "campaign_continuation_chunks",
            "actions_spent",
            "frames_spent",
            "cash_spent",
            "encounters_seen",
            "consecutive_no_progress",
        )
        if any(name not in parent_ledger_data for name in (*names, "elapsed_seconds")):
            raise ValueError("incomplete cumulative ledger")
        counters = {
            name: _validate_non_negative_int(name, parent_ledger_data[name]) for name in names
        }
        elapsed = parent_ledger_data["elapsed_seconds"]
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("invalid cumulative elapsed time")
        return cls(caps=caps, clock=clock, elapsed_seconds=elapsed + downtime_seconds, **counters)


def evaluate_semantic_progress(
    before_facts: Mapping[str, Any],
    after_facts: Mapping[str, Any],
) -> bool:
    """Conservatively evaluate whether meaningful semantic progress was made.

    Byte changes, RAM changes, or party reordering alone do NOT count as progress.
    Recognized progress requires:
    - Increase in registered species count
    - Increase in living specimens count / new capture
    - Actual party experience gain for slot/species-matched Pokémon
    """
    before_reg = before_facts.get("registered_species")
    after_reg = after_facts.get("registered_species")
    if (
        type(before_reg) is int
        and type(after_reg) is int
        and before_reg >= 0
        and after_reg > before_reg
    ):
        return True

    before_specimens = before_facts.get("specimens")
    after_specimens = after_facts.get("specimens")
    if (
        type(before_specimens) is int
        and type(after_specimens) is int
        and before_specimens >= 0
        and after_specimens > before_specimens
    ):
        return True

    # Experience gain check: slot and species matched
    old_party = before_facts.get("party_training")
    new_party = after_facts.get("party_training")
    if isinstance(old_party, list) and isinstance(new_party, list):
        for prior, current in zip(old_party, new_party, strict=False):
            if (
                isinstance(prior, (list, tuple))
                and isinstance(current, (list, tuple))
                and len(prior) >= 3
                and len(current) >= 3
                and all(type(v) is int and v >= 0 for v in (*prior[:3], *current[:3]))
                and prior[0] == current[0]  # same slot
                and prior[1] == current[1]  # same species
                and current[2] > prior[2]  # increased exp
            ):
                return True

    return False
