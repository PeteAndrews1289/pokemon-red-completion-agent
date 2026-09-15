"""Bounded execution evidence, collected without extra game reads or inputs.

The recorder observes existing semantic reads and attempted/completed actions.
It neither chooses actions nor changes exception propagation. Runtime callers
can retain ``error.battle_runtime_diagnostic.to_dict()`` with their terminal.
Messages, paths, frame locals, saves and ROM data are deliberately excluded.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.observation import BattleMenuState, RawGameState

P = ParamSpec("P")
R = TypeVar("R")
TRACE_LIMIT = 128


@dataclass(frozen=True)
class BattleRuntimeDiagnostic:
    """A failure's bounded evidence, separate from learning or outcome credit."""

    phase: str
    total_events: int
    recording_failures: int
    selection: dict[str, object] | None
    events: tuple[dict[str, object], ...]
    exception_chain: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.battle-runtime-diagnostic.v1",
            "phase": self.phase,
            "total_events": self.total_events,
            "recording_failures": self.recording_failures,
            "selection": self.selection,
            "truncated_events": self.total_events - len(self.events),
            "events": list(self.events),
            "exception_chain": list(self.exception_chain),
        }


class _Trace:
    def __init__(self) -> None:
        self.phase = "entry"
        self.total = 0
        self.recording_failures = 0
        self.selection: dict[str, object] | None = None
        self.events: deque[dict[str, object]] = deque(maxlen=TRACE_LIMIT)

    def note(self, kind: str, **values: object) -> None:
        self.total += 1
        self.events.append({"ordinal": self.total, "kind": kind, **values})

    def failure(self, error: Exception) -> BattleRuntimeDiagnostic:
        chain: list[dict[str, object]] = []
        seen: set[int] = set()
        current: BaseException | None = error
        while current is not None and id(current) not in seen and len(chain) < 4:
            seen.add(id(current))
            frames: deque[dict[str, object]] = deque(maxlen=12)
            cursor = current.__traceback__
            while cursor is not None:
                module = cursor.tb_frame.f_globals.get("__name__", "")
                if isinstance(module, str) and module.startswith("pokemon_red_completion."):
                    frames.append(
                        {
                            "function": cursor.tb_frame.f_code.co_name,
                            "line": cursor.tb_lineno,
                        }
                    )
                cursor = cursor.tb_next
            chain.append({"error_type": type(current).__name__, "frames": list(frames)})
            current = current.__cause__ or current.__context__
        return BattleRuntimeDiagnostic(
            self.phase,
            self.total,
            self.recording_failures,
            self.selection,
            tuple(self.events),
            tuple(chain),
        )


_TRACE: ContextVar[_Trace | None] = ContextVar("battle_runtime_trace", default=None)
_FAILURE_SINK: ContextVar[Callable[[BattleRuntimeDiagnostic], None] | None] = ContextVar(
    "battle_runtime_failure_sink", default=None
)


@contextmanager
def bind_battle_runtime_failure_sink(
    sink: Callable[[BattleRuntimeDiagnostic], None],
) -> Iterator[None]:
    """Let an episode writer persist evidence before outer code handles errors.

    The caller owns the destination and durability contract. Ordinary sink
    exceptions never change gameplay or mask the original error; they are
    counted on the diagnostic still attached to that error. Process interrupts
    (KeyboardInterrupt/SystemExit) propagate, retaining the actor error as context.
    """
    if not callable(sink):
        raise TypeError("battle runtime failure sink must be callable")
    token = _FAILURE_SINK.set(sink)
    try:
        yield
    finally:
        _FAILURE_SINK.reset(token)


def diagnose_battle_runtime(function: Callable[P, R]) -> Callable[P, R]:
    """Attach a trace to failures; nested runtime calls share the outer scope."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if _TRACE.get() is not None:
            return function(*args, **kwargs)
        trace = _Trace()
        token = _TRACE.set(trace)
        try:
            return function(*args, **kwargs)
        except Exception as error:
            # Diagnostics must never replace an executor/policy exception.
            with suppress(Exception):
                if (sink := _FAILURE_SINK.get()) is not None:
                    try:
                        sink(trace.failure(error))
                    except Exception:
                        trace.recording_failures += 1
                error.battle_runtime_diagnostic = trace.failure(error)  # type: ignore[attr-defined]
            raise
        finally:
            _TRACE.reset(token)

    return wrapped


def _observational(function: Callable[P, None]) -> Callable[P, None]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            function(*args, **kwargs)
        except Exception:
            if (trace := _TRACE.get()) is not None:
                trace.recording_failures += 1

    return wrapped


@_observational
def trace_phase(phase: str) -> None:
    if (trace := _TRACE.get()) is not None:
        trace.phase = phase
        trace.note("phase", phase=phase)


@_observational
def trace_selection(raw: RawGameState, slot: int) -> None:
    if (trace := _TRACE.get()) is not None:
        trace.selection = {
            "slot": slot,
            "active_party_index": raw.active_party_index,
            "pp": raw.battler_pp,
            "moves": raw.battler_moves,
        }
        trace.note("selection", **trace.selection)


@_observational
def trace_state(raw: RawGameState) -> None:
    if (trace := _TRACE.get()) is not None:
        trace.note(
            "state",
            battle_state=raw.battle_state,
            active_party_index=raw.active_party_index,
            hp=raw.battler_hp,
            status=raw.battler_status,
            moves=raw.battler_moves,
            pp=raw.battler_pp,
            enemy_hp=raw.enemy_hp,
            enemy_trapping=raw.enemy_using_trapping_move,
            disabled_slot=raw.player_disabled_move_slot,
            disable_turns=raw.player_disable_turns,
        )


@_observational
def trace_menu(menu: BattleMenuState) -> None:
    if (trace := _TRACE.get()) is not None:
        trace.note(
            "menu",
            phase=menu.phase.value,
            command=menu.selected_main_command,
            slot=menu.selected_move_slot,
        )


@_observational
def trace_action(action: MacroAction, *, completed: bool) -> None:
    if (trace := _TRACE.get()) is not None:
        direction = action.value if action.value in {"up", "down", "left", "right"} else None
        trace.note(
            "action",
            action=action.kind.value,
            direction=direction,
            repeat=action.repeat,
            completed=completed,
        )
