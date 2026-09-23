import hashlib
import io
import json
from types import SimpleNamespace

import pytest
import qualify_red_safari_training_setup as driver


def test_failed_controller_call_is_retained():
    def fail(_):
        raise RuntimeError("budget")

    delegate = SimpleNamespace(frame_count=4, tick=fail)
    stream = io.StringIO()
    controller = driver.TracedController(delegate, stream)
    with pytest.raises(RuntimeError, match="budget"):
        controller.tick(8)
    rows = [json.loads(row) for row in stream.getvalue().splitlines()]
    assert [row["status"] for row in rows] == ["attempt", "failed"]
    assert rows[1]["error"] == "budget"
    assert rows[0]["value"] == 8


def setup(monkeypatch, tmp_path):
    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"test-only")
    monkeypatch.setattr(driver, "RED_ROM_SHA256", hashlib.sha256(b"test-only").hexdigest())
    monkeypatch.setattr(driver.subprocess, "check_output", lambda args, **kw:
                        b"" if "status" in args else b"a" * 40)
    monkeypatch.setattr(driver.StrategicScenarioRouteWorld, "from_rom", lambda _: object())
    return rom


def test_wrong_rom_never_claims_or_opens_emulator(monkeypatch, tmp_path):
    rom = setup(monkeypatch, tmp_path)
    rom.write_bytes(b"wrong")
    monkeypatch.setattr(driver, "PyBoyAdapter", lambda *a, **kw: pytest.fail("opened emulator"))
    with pytest.raises(ValueError, match="ROM differs"):
        driver.run(rom, tmp_path)
    assert not (tmp_path / driver.CLAIM_ID).exists()


def test_consumed_claim_never_opens_emulator(monkeypatch, tmp_path):
    rom = setup(monkeypatch, tmp_path)
    (tmp_path / driver.CLAIM_ID).mkdir()
    monkeypatch.setattr(driver, "PyBoyAdapter", lambda *a, **kw: pytest.fail("opened emulator"))
    with pytest.raises(FileExistsError):
        driver.run(rom, tmp_path)


def test_opening_failure_is_retained_without_intervention_or_retry(monkeypatch, tmp_path):
    rom = setup(monkeypatch, tmp_path)
    events = []

    class Emulator:
        frame_count = 0
        pressed_buttons = frozenset()

        def __enter__(self):
            claim = json.loads((tmp_path / driver.CLAIM_ID / "claim.json").read_text())
            assert claim["retry_allowed"] is False
            assert claim["load_state_allowed"] is False
            events.append("opened")
            return self

        def __exit__(self, *args):
            events.append("closed")

        def save_state_bytes(self):
            return b"retained-failure"

    monkeypatch.setattr(driver, "PyBoyAdapter", lambda *a, **kw: Emulator())
    raw = SimpleNamespace(map_id=40, player_x=7, player_y=4, battle_state=0, player_money=3000)
    monkeypatch.setattr(driver, "PokemonRedStateReader",
                        lambda _: SimpleNamespace(read=lambda: raw))
    monkeypatch.setattr(driver, "run_opening_chapter",
                        lambda *a, **kw: SimpleNamespace(passed=False))
    monkeypatch.setattr(driver, "redirect_fresh_lab_exit",
                        lambda *a, **kw: pytest.fail("intervened after failed opening"))
    result = driver.run(rom, tmp_path)
    assert result["status"] == "failed"
    assert result["stage"] == "fresh_opening"
    assert result["new_fitted_examples"] == result["model_queries"] == 0
    assert (tmp_path / driver.CLAIM_ID / "terminal.state").read_bytes() == b"retained-failure"
    assert json.loads((tmp_path / driver.CLAIM_ID / "result.json").read_text()) == result
    assert events == ["opened", "closed"]
    with pytest.raises(FileExistsError):
        driver.run(rom, tmp_path)
    assert events == ["opened", "closed"]


def state(map_id=40, y=10, x=4, battle=0):
    return SimpleNamespace(map_id=map_id, player_y=y, player_x=x, battle_state=battle)


def exit_fixture(states, *, ready=True, pressed=frozenset()):
    observations = iter(states)
    reader = SimpleNamespace(read=lambda: next(observations),
                             read_input_readiness=lambda: SimpleNamespace(ready=ready))
    emitted = []
    actions = SimpleNamespace(execute=emitted.append)
    return actions, reader, SimpleNamespace(pressed_buttons=pressed), emitted


@pytest.mark.parametrize("observations,expected_actions", [
    ([state(), state(156, 5, 3)], 2),
    ([state(), state(y=11), state(156, 5, 3)], 4),
])
def test_exit_checks_destination_or_one_explicit_doorway_handshake(observations, expected_actions):
    actions, reader, emulator, emitted = exit_fixture(observations)
    driver.finish_lab_exit(actions, reader, emulator)
    assert len(emitted) == expected_actions
    assert [a.value for a in emitted[::2]] == ["down"] * (expected_actions // 2)


@pytest.mark.parametrize("bad", [
    state(), state(y=11, x=5), state(7, 5, 3), state(156, 5, 3, battle=1),
])
def test_exit_never_retries_other_failed_boundaries(bad):
    actions, reader, emulator, emitted = exit_fixture([state(), bad])
    with pytest.raises(ValueError, match="native exit"):
        driver.finish_lab_exit(actions, reader, emulator)
    assert len(emitted) == 2


def test_exit_second_doorway_failure_stops_without_third_pulse():
    actions, reader, emulator, emitted = exit_fixture([state(), state(y=11), state(y=11)])
    with pytest.raises(ValueError, match="native exit"):
        driver.finish_lab_exit(actions, reader, emulator)
    assert len(emitted) == 4


@pytest.mark.parametrize("initial,ready,pressed", [
    (state(y=11), True, frozenset()), (state(battle=1), True, frozenset()),
    (state(), False, frozenset()), (state(), True, frozenset({"a"})),
])
def test_exit_requires_exact_released_approach_before_acting(initial, ready, pressed):
    actions, reader, emulator, emitted = exit_fixture([initial], ready=ready, pressed=pressed)
    with pytest.raises(ValueError, match="verified approach"):
        driver.finish_lab_exit(actions, reader, emulator)
    assert emitted == []
