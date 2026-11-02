"""Neutral recovery never chooses a goal or dismisses gameplay."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_red_field_settlement import settle

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import InputReadiness


class Fake:
    def __init__(self, remaining=5):
        self.remaining = remaining
        self.frames = 0
        self.pressed_buttons = frozenset()
        self.raw = SimpleNamespace(map_id=22, battle_state=0)
        self.dialogue = False
        self.script = 0
        self.money = 1073

    def read(self):
        return SimpleNamespace(**vars(self.raw))

    def read_input_readiness(self):
        return InputReadiness(self.script, 0, 0, 2 if self.remaining else 0, 0, 0, self.remaining)

    def read_bottom_dialogue_box_visible(self):
        return self.dialogue

    def execute(self, action):
        assert action.kind is MacroActionKind.WAIT and action.repeat == 1
        self.frames += 1
        self.remaining = max(0, self.remaining - 1)


def test_neutral_settlement_completes_only_remaining_movement():
    fake = Fake()
    assert settle(fake, fake, fake, lambda: fake.money) == 5
    assert fake.frames == 5


@pytest.mark.parametrize("blocked", ["buttons", "battle", "dialogue", "script"])
def test_settlement_rejects_non_neutral_boundary_without_input(blocked):
    fake = Fake()
    if blocked == "buttons":
        fake.pressed_buttons = frozenset({"up"})
    elif blocked == "battle":
        fake.raw.battle_state = 1
    elif blocked == "dialogue":
        fake.dialogue = True
    else:
        fake.script = 1
    with pytest.raises(ValueError, match="safe boundary"):
        settle(fake, fake, fake, lambda: fake.money)
    assert fake.frames == 0


@pytest.mark.parametrize("changed", ["map", "money", "battle"])
def test_settlement_stops_immediately_on_transition(changed):
    fake = Fake()
    original = fake.execute

    def execute(action):
        original(action)
        if changed == "map":
            fake.raw.map_id = 23
        elif changed == "money":
            fake.money -= 1
        else:
            fake.raw.battle_state = 1

    fake.execute = execute
    with pytest.raises(ValueError, match="safe boundary"):
        settle(fake, fake, fake, lambda: fake.money)
    assert fake.frames == 1


def test_settlement_has_hard_64_neutral_frame_limit():
    fake = Fake(100)
    with pytest.raises(ValueError, match="64 frames"):
        settle(fake, fake, fake, lambda: fake.money)
    assert fake.frames == 64
