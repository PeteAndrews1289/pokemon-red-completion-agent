"""Native contract qualification; based on Flash's isolated draft and tightened locally."""

from dataclasses import replace

import pytest
from test_red_boxed_level_evolution import PRECURSOR, _adapter, _plan, _world

from pokemon_red_completion.red_boxed_level_evolution import (
    RedBoxedLevelEvolutionError,
    RedNativeStockEvolutionContract,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    red_dual_capability_scenario_specs,
)


@pytest.mark.parametrize("copies", [3, 5])
def test_native_contract_qualifies_without_input_and_executes_exact_delta(monkeypatch, copies):
    world = _world()
    world.box = [PRECURSOR] * copies + [0x54]
    adapter = _adapter(monkeypatch, world)
    before = dependency_specimen_ledger(world.collection())
    bound = adapter.qualify(RedNativeStockEvolutionContract(copies), before)
    assert world.actions_executed == 0 and world.log == []
    report = bound.execute()
    assert report.after_ledger.count(red_species_ref(11)) == copies - 1
    assert report.after_ledger.count(red_species_ref(12)) == 1
    assert report.public_dict()["exact_evolution_transition"] is True


@pytest.mark.parametrize("source,target", [(0, 0), (-1, 0), (True, 0), (3.0, 0),
                                         (3, 1), (3, False), (3, "0")])
def test_native_contract_rejects_noncanonical_counts(source, target):
    with pytest.raises(RedBoxedLevelEvolutionError):
        RedNativeStockEvolutionContract(source, target)


@pytest.mark.parametrize("damage", ["count", "none", "slot", "observed", "legacy1", "legacy2"])
def test_qualification_rejects_mismatch_without_input(monkeypatch, damage):
    world = _world()
    world.box = [PRECURSOR] * 3 + [0x54]
    plan = _plan()
    if damage == "slot":
        plan = replace(plan, precursor_box_slot=4)
    adapter = _adapter(monkeypatch, world, plan=plan)
    ledger = dependency_specimen_ledger(world.collection())
    contract = RedNativeStockEvolutionContract(2 if damage == "count" else 3)
    if damage == "none":
        contract = None
    elif damage.startswith("legacy"):
        contract = red_dual_capability_scenario_specs()[int(damage[-1]) - 1]
    elif damage == "observed":
        world.box.pop()
    with pytest.raises((TypeError, RedBoxedLevelEvolutionError)):
        adapter.qualify(contract, ledger)
    assert world.actions_executed == 0 and world.log == []
