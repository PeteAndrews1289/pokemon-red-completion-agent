"""Independent registered availability checks at the actual native provider seam."""

from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution


@pytest.mark.parametrize("copies,reserve,available", [
    (1, 0, True), (1, 1, False), (3, 0, True), (3, 2, True), (3, 3, False),
    (5, 4, True), (5, 5, False),
])
def test_registered_native_stock_respects_actual_reserve_without_input(
    tmp_path, monkeypatch, copies, reserve, available,
):
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.wild_tables",
        lambda _: {22: [(10, 0x21), (15, 0x6C)]},
    )
    runtime, _, _ = bound_fixture(tmp_path, count=copies, reserve=reserve)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"fixture"))
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert (offer.binding is not None) is available
    assert actions.actions_executed == 0


def test_globally_registered_target_is_not_reoffered_with_extra_local_stock(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.wild_tables",
        lambda _: {22: [(10, 0x21), (15, 0x6C)]},
    )
    runtime, _, _ = bound_fixture(tmp_path, count=3, inherited=(78,))
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"fixture"))
    actions = CountingExecutor(_ActionDelegate())
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert offer.binding is None
    assert actions.actions_executed == 0
