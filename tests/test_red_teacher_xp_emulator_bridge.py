from types import SimpleNamespace as N

import pytest

from test_red_collection_teacher_learning import memory
from pokemon_red_completion.red_collection_teacher_learning import (
    set_isolated_training_emulator_experience,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader


class Mapping(dict):
    def __missing__(self, key):
        return 0


def adapter():
    values = Mapping(memory().values)
    return N(pressed_buttons=frozenset(),
             _require_backend=lambda: N(memory=values)), values


def test_released_train_bridge_changes_only_declared_same_level_xp():
    emulator, values = adapter()
    before = dict(values)
    cartridge = N(species=lambda _: N(experience_at_level=lambda level: level**3))
    writes = set_isolated_training_emulator_experience(
        emulator, partition="train", isolated_training_setup=True,
        party_index=0, experience=7995, cartridge=cartridge,
    )
    assert len(writes) == 3
    changed = {row["address"] for row in writes}
    assert all(values[key] == value for key, value in before.items() if key not in changed)
    assert emulator.pressed_buttons == frozenset()
    port = N(read_u8=lambda address: values[address])
    member = PokemonRedPartyReader(port).read().members[0]
    assert member.experience == 7995 and member.level == 19


@pytest.mark.parametrize("partition,isolated,pressed", [
    ("development", True, frozenset()),
    ("train", False, frozenset()),
    ("train", True, frozenset({"a"})),
])
def test_bridge_rejects_before_backend_access(partition, isolated, pressed):
    def forbidden():
        raise AssertionError("rejected authority must never access backend")
    emulator = N(pressed_buttons=pressed, _require_backend=forbidden)
    with pytest.raises(ValueError, match="isolated TRAIN"):
        set_isolated_training_emulator_experience(
            emulator, partition=partition, isolated_training_setup=isolated,
            party_index=0, experience=7995, cartridge=None,
        )


def test_bridge_preserves_existing_level_range_guard_before_writes():
    emulator, values = adapter()
    before = dict(values)
    cartridge = N(species=lambda _: N(experience_at_level=lambda level: level**3))
    with pytest.raises(ValueError, match="retain the declared native level"):
        set_isolated_training_emulator_experience(
            emulator, partition="train", isolated_training_setup=True,
            party_index=0, experience=8000, cartridge=cartridge,
        )
    assert values == before
