"""Exercise the real inspection boundary, including no-input verification."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import run_red_regional_source_choice as driver


@dataclass
class Runtime:
    remaining_acquisition_demand: object = None


def fixture(monkeypatch, *, count=2, mutation=None):
    events = []

    class Emulator:
        frame_count = 0
        pressed_buttons = ()
        state = b"parent"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def load_state_bytes(self, value):
            assert value == b"parent"
            events.append("restore")

        def save_state_bytes(self):
            return self.state

    emulator = Emulator()
    actions = SimpleNamespace(actions_executed=0)
    observed, candidates, memory, menu = object(), tuple(range(count)), object(), object()
    ready = SimpleNamespace(
        continuation=object(),
        training_plan=SimpleNamespace(maximum_actions=100, maximum_frames=600),
        causal_record=object(), rom_path="unused", capture=SimpleNamespace(state_bytes=b"parent"),
        profile=object(), remaining_acquisition_demand=object(), level_evolution_acquisitions=False,
        routed_recovery=True, completion_dose=True,
    )
    monkeypatch.setattr(driver.base, "_route_world", lambda _: object())
    monkeypatch.setattr(driver.base, "PyBoyAdapter", lambda *_a, **_k: emulator)
    monkeypatch.setattr(driver.base, "_verify_continuation_restore",
                        lambda *_: events.append("verify_restore"))
    monkeypatch.setattr(driver.base, "ReadOnlyController", lambda x: x)
    monkeypatch.setattr(driver.base, "PokemonRedStateReader", lambda _: object())
    monkeypatch.setattr(driver.base, "build_red_goal_context_runtime", lambda **_: Runtime())
    monkeypatch.setattr(driver.base, "_registered_runtime", lambda _r, runtime: runtime)
    monkeypatch.setattr(driver.base, "FrameSafeExecutor", lambda *_: object())
    monkeypatch.setattr(driver.base, "CountingExecutor", lambda _: actions)
    monkeypatch.setattr(driver.base, "_training_observation", lambda _: observed)

    def enumerate_(*args, **kwargs):
        assert args[0].remaining_acquisition_demand is ready.remaining_acquisition_demand
        events.append("enumerate")
        if mutation == "state":
            emulator.state = b"changed"
        elif mutation == "frames":
            emulator.frame_count = 1
        elif mutation == "buttons":
            emulator.pressed_buttons = ("a",)
        elif mutation == "actions":
            actions.actions_executed = 1
        return candidates

    def history(_):
        events.append("history")
        return memory

    def rank_input(o, c, m):
        assert o is observed and c is candidates and m is memory
        events.append("menu")
        return menu

    monkeypatch.setattr(driver, "enumerate_red_regional_acquisitions", enumerate_)
    monkeypatch.setattr(driver, "source_search_memory", history)
    monkeypatch.setattr(driver, "regional_acquisition_menu", rank_input)
    return ready, events, observed, candidates, menu


def test_inventory_skips_only_unused_history_not_fresh_state(monkeypatch):
    ready, events, observed, candidates, _ = fixture(monkeypatch)
    assert driver.inspect_sources(ready, include_menu=False) == (observed, candidates, None)
    assert events == ["restore", "verify_restore", "enumerate"]


def test_actual_choice_still_builds_authenticated_history(monkeypatch):
    ready, events, observed, candidates, menu = fixture(monkeypatch)
    assert driver.inspect_sources(ready) == (observed, candidates, menu)
    assert events == ["restore", "verify_restore", "enumerate", "history", "menu"]
    monkeypatch.setattr(driver, "source_search_memory",
                        lambda _: (_ for _ in ()).throw(ValueError("invalid ancestry")))
    with pytest.raises(ValueError, match="invalid ancestry"):
        driver.inspect_sources(ready)


@pytest.mark.parametrize("count", [0, 1])
def test_allowed_absent_choice_does_not_build_unused_menu(monkeypatch, count):
    ready, events, observed, candidates, _ = fixture(monkeypatch, count=count)
    assert driver.inspect_sources(ready, allow_no_choice=True) == (observed, candidates, None)
    assert "history" not in events


@pytest.mark.parametrize("mutation", ["state", "frames", "buttons", "actions"])
def test_inventory_still_rejects_observation_side_effects(monkeypatch, mutation):
    ready, _, _, _, _ = fixture(monkeypatch, mutation=mutation)
    with pytest.raises(ValueError, match="changed the saved game"):
        driver.inspect_sources(ready, include_menu=False)


@pytest.mark.parametrize("bad", [0, 1, None, "false"])
def test_skip_flag_does_not_coerce_before_opening_anything(bad):
    with pytest.raises(ValueError, match="boolean"):
        driver.inspect_sources(None, include_menu=bad)
