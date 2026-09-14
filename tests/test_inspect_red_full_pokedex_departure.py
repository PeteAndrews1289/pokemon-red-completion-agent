from types import SimpleNamespace

import inspect_red_full_pokedex_departure as inspection
import pytest
from test_red_full_pokedex_goal_proposal import setup  # noqa: F401


@pytest.mark.parametrize("failure", [None, "pins", "state_mutation", "route"])
def test_inspector_pins_one_context_and_preserves_read_only_state(
    setup, tmp_path, monkeypatch, failure,  # noqa: F811
):
    rom = tmp_path / "fixture.gb"
    rom.write_bytes(b"ROM-free fixture; no cartridge is decoded")
    monkeypatch.setattr(inspection, "open_goal_manager_context_capture",
                        lambda *_: setup.runtime.capture)
    monkeypatch.setattr(inspection, "load_red_goal_context_profile",
                        lambda *_: setup.runtime.profile)
    monkeypatch.setattr(inspection, "StrategicScenarioRouteWorld",
                        SimpleNamespace(from_rom=lambda _: setup.world))
    monkeypatch.setattr(inspection, "PokemonRedStateReader", lambda _: setup.reader)

    class Emulator:
        frame_count = 0
        pressed_buttons = frozenset()
        saves = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def load_state_bytes(self, state):
            assert state == setup.runtime.capture.state_bytes

        def save_state_bytes(self):
            self.saves += 1
            return b"mutated" if failure == "state_mutation" and self.saves > 1 else b"frozen"

        def read_u8(self, address):
            return setup.runtime.emulator.read_u8(address)

        def tick(self, _):
            pytest.fail("tick escaped read-only controller")

        press = release = tick

    opened = []

    def emulator(*_, **__):
        opened.append(True)
        return Emulator()

    monkeypatch.setattr(inspection, "PyBoyAdapter", emulator)
    setup.world.fail = failure == "route"
    kwargs = dict(
        rom_path=rom, state_path=tmp_path / "unused", envelope_path=tmp_path / "unused",
        profile_path=tmp_path / "unused", expected_state_sha256=setup.runtime.capture.state_sha256,
        expected_profile_sha256="0" * 64 if failure == "pins"
        else setup.runtime.profile.profile_sha256,
    )
    if failure in {"pins", "state_mutation"}:
        with pytest.raises(ValueError, match="pins differ" if failure == "pins" else "changed"):
            inspection.inspect_departure(**kwargs)
        if failure == "pins":
            assert opened == []
    else:
        result = inspection.inspect_departure(**kwargs)
        assert result["passed"] is (failure is None)
        assert result["local_target_count"] == 151
        assert result["controller_actions"] == result["emulator_frames"] == 0
        assert result["state_bytes_unchanged"]
        assert not result["upstream_independence_verified"]
