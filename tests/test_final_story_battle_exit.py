from dataclasses import replace

import pytest
from test_battle_runtime import NOT_READY, FakeRuntime, _raw

from pokemon_red_completion.battle_runtime import (
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)


@pytest.mark.parametrize("reject", [False, True])
def test_explicit_exit_guard_observes_and_hands_off_without_scene_input(reject):
    initial = _raw()
    exited = replace(initial, battle_state=0, battle_result=0)
    runtime = FakeRuntime(raw=initial, controls=NOT_READY)
    reads = [initial, exited]
    runtime.read = lambda: reads.pop(0) if reads else exited
    seen = []
    def guard(raw):
        seen.append(raw)
        assert raw == exited
        if reject:
            raise ValueError("exit rejected")
    def run():
        return run_adaptive_trainer_battle(
            runtime, runtime, lambda _: pytest.fail("no policy query after battle exit"),
            expected_map=initial.map_id, consume_battle_start_schedule=False,
            battle_exit_guard=guard,
        )
    if reject:
        with pytest.raises(ValueError, match="exit rejected"):
            run()
    else:
        assert run() == exited
    assert seen == [exited] and runtime.actions == []


def test_default_exit_still_waits_for_ordinary_input_readiness():
    initial = _raw()
    exited = replace(initial, battle_state=0, battle_result=0)
    runtime = FakeRuntime(raw=initial, controls=NOT_READY)
    reads = [initial, exited]
    runtime.read = lambda: reads.pop(0) if reads else exited
    with pytest.raises(RuntimeError, match="exceeded"):
        run_adaptive_trainer_battle(
            runtime, runtime, lambda _: pytest.fail("no policy query after battle exit"),
            expected_map=initial.map_id, consume_battle_start_schedule=False,
            timing=BattleRuntimeTiming(max_runtime_pulses=2),
        )
    assert runtime.actions  # default settlement was not globally removed


def test_noncallable_scene_exit_guard_is_rejected_before_input():
    runtime = FakeRuntime()
    with pytest.raises(TypeError, match="battle_exit_guard"):
        run_adaptive_trainer_battle(runtime, runtime, lambda _: 1,
                                   expected_map=runtime.raw.map_id, battle_exit_guard=True)
    assert runtime.actions == []
