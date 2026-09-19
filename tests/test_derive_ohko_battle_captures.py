from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from derive_ohko_battle_captures import (  # noqa: E402
    _insert_ohko_move,
    _require_source_partitions,
)

from pokemon_red_completion.observation import PARTY_MOVES_OFFSET, PARTY_PP_OFFSET  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


def test_train_only_derivation_excludes_development() -> None:
    _require_source_partitions(
        (ScenarioPartition.TRAIN, ScenarioPartition.TRAIN), train_only=True
    )
    with pytest.raises(ValueError, match="train sources only"):
        _require_source_partitions(
            (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT),
            train_only=True,
        )
    with pytest.raises(ValueError, match="both train and development"):
        _require_source_partitions((ScenarioPartition.TRAIN,), train_only=False)


def test_development_only_derivation_excludes_train() -> None:
    _require_source_partitions(
        (ScenarioPartition.DEVELOPMENT, ScenarioPartition.DEVELOPMENT),
        train_only=False,
        development_only=True,
    )
    with pytest.raises(ValueError, match="development sources only"):
        _require_source_partitions(
            (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT),
            train_only=False,
            development_only=True,
        )
    with pytest.raises(ValueError, match="one derivation partition mode"):
        _require_source_partitions(
            (ScenarioPartition.TRAIN,), train_only=True, development_only=True
        )


def test_slot_four_assistance_updates_only_declared_battle_and_party_pairs() -> None:
    memory: dict[int, int] = {}
    party_base = 0xD200
    _insert_ohko_move(memory, party_base=party_base, slot=4)
    assert memory == {
        0xD01F: 12,
        0xD030: 5,
        party_base + PARTY_MOVES_OFFSET + 3: 12,
        party_base + PARTY_PP_OFFSET + 3: 5,
    }


@pytest.mark.parametrize("slot", (0, 5, True))
def test_assistance_rejects_invalid_slot(slot: int | bool) -> None:
    with pytest.raises(ValueError, match="replacement slot"):
        _insert_ohko_move({}, party_base=0xD200, slot=slot)
