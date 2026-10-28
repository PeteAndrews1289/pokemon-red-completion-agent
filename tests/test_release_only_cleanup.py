"""Release-only teardown owns no gameplay or strategic recovery action."""
from types import SimpleNamespace
import pytest
from pokemon_red_completion.executor import release_pressed_buttons

def test_release_cleanup_never_presses_ticks_or_discards_prior_counter():
    held = {"a", "up"}
    released = []
    def release(button):
        released.append(button)
        held.remove(button)
    port = SimpleNamespace(pressed_buttons=held, frames=73, release=release,
        press=lambda *_: pytest.fail("cleanup pressed a control"),
        tick=lambda *_: pytest.fail("cleanup advanced the game"))
    assert release_pressed_buttons(port) == ("a", "up")
    assert released == ["a", "up"] and not held and port.frames == 73
    assert release_pressed_buttons(port) == ()

def test_release_failure_remains_visible_and_does_not_advance_game():
    error = RuntimeError("release failed")
    def release(_):
        raise error
    with pytest.raises(RuntimeError) as caught:
        release_pressed_buttons(SimpleNamespace(pressed_buttons={"a"}, release=release))
    assert caught.value is error
