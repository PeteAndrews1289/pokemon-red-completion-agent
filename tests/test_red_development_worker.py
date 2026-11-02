import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import run_red_development_worker as worker

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulation_batch import file_digest


@pytest.mark.parametrize("mode", ["battle", "fresh_smoke"])
def test_declared_inputs_required_and_pinned(tmp_path, monkeypatch, mode):
    path = tmp_path / "input"
    path.write_bytes(b"fake-input")
    digest = file_digest(path)
    monkeypatch.setattr(worker, "RED_ROM_SHA256", digest)
    spec = dict(
        mode=mode,
        fit_allowed=False,
        copy_back=False,
        rom=str(path),
        model=str(path),
        capture=str(path),
        manifest=str(path),
        pins={str(path): digest},
        offset=4,
        boot_offset=257,
    )
    worker.validate_spec(spec)
    worker.validate_spec(dict(spec, allow_status_moves=True))
    with pytest.raises(ValueError, match="explicit boolean"):
        worker.validate_spec(dict(spec, allow_status_moves="true"))
    for key, value in (
        ("fit_allowed", True),
        ("copy_back", True),
        ("pins", {}),
        ("mode", "campaign"),
        ("offset" if mode == "battle" else "boot_offset", 9),
    ):
        with pytest.raises(ValueError):
            worker.validate_spec(dict(spec, **{key: value}))
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash changed"):
        worker.validate_spec(spec)


class Emulator:
    def __init__(self, *args, **kwargs):
        self.frame_count = 0
        self.pressed_buttons = set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def tick(self, count):
        self.frame_count += count

    def press(self, button):
        self.pressed_buttons.add(button)

    def release(self, button):
        self.pressed_buttons.discard(button)

    def save_state_bytes(self):
        return str(self.frame_count).encode()

    def load_state_bytes(self, value):
        pytest.fail("fresh start must not load an existing save")


def test_status_scope_rejects_uncomposed_model_before_native_input(tmp_path, monkeypatch):
    model_path = tmp_path / "model.json"
    model_path.write_text("{}")
    capture = SimpleNamespace(manifest=SimpleNamespace(partition=worker.ScenarioPartition.TRAIN))
    monkeypatch.setattr(worker, "open_battle_scenario_capture", lambda *args: capture)
    monkeypatch.setattr(
        worker.TrainerPracticeThreeHeadModel,
        "from_dict",
        lambda payload: SimpleNamespace(damage_reference=None),
    )
    monkeypatch.setattr(
        worker, "PyBoyAdapter", lambda *args, **kwargs: pytest.fail("must reject before input")
    )
    with pytest.raises(ValueError, match="composed status model"):
        worker.battle(
            dict(capture="unused", manifest="unused", model=str(model_path),
                 allow_status_moves=True),
            tmp_path,
            "declared-spec-hash",
        )


@dataclass
class Native:
    battled_rival: bool = True


@pytest.mark.parametrize("fault", [None, "opening", "rival", "load"])
def test_fresh_checks_reuse_bounded_teacher_and_retain_errors(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(worker, "PyBoyAdapter", Emulator)
    raw = SimpleNamespace(battle_state=0)
    reader = SimpleNamespace(
        read=lambda: raw,
        read_opening_control_state=lambda state: SimpleNamespace(
            phase=worker.OpeningPhase.STARTER_OBTAINED
        ),
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    monkeypatch.setattr(worker, "PokemonRedStateReader", lambda port: reader)

    def opening(path, *, new_game_timing, _emulator, _executor):
        assert new_game_timing.boot_frames == worker.DEFAULT_NEW_GAME_TIMING.boot_frames + 257
        _executor.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
        if fault == "load":
            _emulator.load_state_bytes(b"forbidden")
        return SimpleNamespace(passed=fault != "opening", public_dict=lambda: {"test": True})

    monkeypatch.setattr(worker, "run_opening_chapter", opening)
    for name in ("_move", "_expect_position", "_wait"):
        monkeypatch.setattr(worker, name, lambda *args: None)
    monkeypatch.setattr(worker, "_resolve_lab_rival", lambda *args: (raw, Native(), True))
    monkeypatch.setattr(
        worker, "is_rival_resolution_verified", lambda *args, **kw: fault != "rival"
    )
    monkeypatch.setattr(worker, "is_rival_victory_verified", lambda *args, **kw: True)
    spec = dict(rom="not-opened.gb", boot_offset=257)
    if fault in ("load", "opening"):
        with pytest.raises(ValueError):
            worker.fresh_smoke(spec, tmp_path)
    else:
        result = worker.fresh_smoke(spec, tmp_path)
        assert result["valid"] == (fault is None)
        assert result["model_queries"] == result["state_loads"] == result["memory_edits"] == 0
    end = json.loads((tmp_path / "final-state.json").read_bytes())
    assert end["frames"] == 2 and not end["pressed_buttons"]
    assert end["attempted_actions"] == end["completed_actions"] == 1
    assert (tmp_path / "final.state").read_bytes() == b"2"
