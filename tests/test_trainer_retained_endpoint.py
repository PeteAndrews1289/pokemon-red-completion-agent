import hashlib
import json
from types import SimpleNamespace

import pytest
from capture_fresh_red_brock_development import BOOT_FRAMES, TEAM_BOOT_FRAMES
from run_red_trainer_practice_model import retained_session


@pytest.mark.parametrize("failure", [False, True])
def test_endpoint_is_saved_before_close_on_success_and_failure(tmp_path, failure):
    calls = []
    emulator = SimpleNamespace(
        frame_count=100,
        pressed_buttons=frozenset(),
        save_state_bytes=lambda: calls.append("save") or b"actual-final-state",
    )

    def episode():
        with retained_session(emulator, maximum_frames=200, output=tmp_path) as session:
            assert session.frame_count == 100
            emulator.frame_count = 150
            if failure:
                raise RuntimeError("actor failed")

    if failure:
        with pytest.raises(RuntimeError, match="actor failed"):
            episode()
    else:
        episode()
    assert calls == ["save"]
    assert (tmp_path / "final.state").read_bytes() == b"actual-final-state"
    receipt = json.loads((tmp_path / "final-state.json").read_bytes())
    assert receipt["state_sha256"] == hashlib.sha256(b"actual-final-state").hexdigest()
    assert receipt["episode_returned"] is not failure
    assert receipt["continuation_qualified"] is False
    assert receipt["frames"] == 150


def test_endpoint_never_overwrites_and_write_failure_is_not_success(tmp_path):
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: b"new")
    (tmp_path / "final.state").write_bytes(b"previous")
    with (
        pytest.raises(FileExistsError),
        retained_session(emulator, maximum_frames=10, output=tmp_path),
    ):
        pass
    assert (tmp_path / "final.state").read_bytes() == b"previous"
    assert not (tmp_path / "final-state.json").exists()


def test_empty_endpoint_fails_closed(tmp_path):
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: b"")
    with (
        pytest.raises(ValueError, match="empty"),
        retained_session(emulator, maximum_frames=10, output=tmp_path),
    ):
        pass
    assert not (tmp_path / "final.state").exists()


def test_endpoint_cleanup_releases_held_input_before_save(tmp_path):
    calls = []

    class Emulator:
        frame_count = 0

        def __init__(self):
            self.pressed_buttons = {"a"}

        def release(self, button):
            calls.append(("release", button))
            self.pressed_buttons.remove(button)

        def save_state_bytes(self):
            calls.append(("save", tuple(sorted(self.pressed_buttons))))
            return b"released-final-state"

    emulator = Emulator()
    with (
        pytest.raises(RuntimeError, match="actor failed"),
        retained_session(emulator, maximum_frames=10, output=tmp_path),
    ):
        raise RuntimeError("actor failed")

    assert calls == [("release", "a"), ("save", ())]
    receipt = json.loads((tmp_path / "final-state.json").read_bytes())
    assert receipt["pressed_buttons_before_cleanup"] == ["a"]
    assert receipt["pressed_buttons"] == []


def test_endpoint_cleanup_release_failure_prevents_save(tmp_path):
    calls = []

    class Emulator:
        frame_count = 0
        pressed_buttons = {"a"}

        def release(self, button):
            calls.append(("release", button))
            raise RuntimeError("release failed")

        def save_state_bytes(self):
            calls.append("save")
            return b"must-not-be-written"

    with (
        pytest.raises(RuntimeError, match="release failed"),
        retained_session(Emulator(), maximum_frames=10, output=tmp_path),
    ):
        pass

    assert calls == [("release", "a")]
    assert not (tmp_path / "final.state").exists()
    assert not (tmp_path / "final-state.json").exists()


def test_new_team_source_plan_does_not_reuse_consumed_brock_boots():
    assert TEAM_BOOT_FRAMES == (2900, 3100)
    assert not set(BOOT_FRAMES) & set(TEAM_BOOT_FRAMES)
