"""Game-specific memory readers and semantic state extraction for Pokemon Crystal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CrystalBattleMenuPhase(StrEnum):
    UNKNOWN = "unknown"
    MAIN = "main"
    MOVE = "move"


@dataclass(frozen=True, slots=True)
class CrystalBattleMenuState:
    """Revision-pinned menu meaning without exposing menu RAM to route code."""

    phase: CrystalBattleMenuPhase
    selected_move_slot: int | None = None
    selected_main_command: int | None = None


class CrystalBattleStateReader(Protocol):
    """Semantic subset of the Crystal StateReader used by the controller."""

    # Note: A full RawGameState for Crystal will be defined here later.
    def read_battle_menu_state(self, raw: object) -> CrystalBattleMenuState: ...
