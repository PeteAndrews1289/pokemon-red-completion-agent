from dataclasses import replace
from types import SimpleNamespace

import pytest
import run_paired_red_bounded_player as runner
from test_red_acquisition import _observation

from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_acquisition_alternatives import level_acquisition_edges
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime


def _catalog():
    return replace(RED_ACQUISITION_CATALOG, remaining_demand=True, level_evolution_edges=(
        (red_species_ref(96), red_species_ref(97)),
    ))


def _missing(catalog, source, species, living):
    survey = summarize_red_area_survey(source, _observation(*living), catalog)
    return next(row.missing_count for row in survey.requirements
                if row.species_ref == red_species_ref(species))


def test_hypno_direct_and_spare_drowzee_are_real_alternatives_not_double_demand():
    catalog = _catalog()
    assert _missing(catalog, "wild:Route11:grass", 96, (96,)) == 1
    assert _missing(catalog, "wild:CeruleanCave1F:grass", 97, (96,)) == 1
    for held in ((96, 96), (96, 97)):
        assert _missing(catalog, "wild:Route11:grass", 96, held) == 0
        assert _missing(catalog, "wild:CeruleanCave1F:grass", 97, held) == 0
    assert _missing(catalog, "wild:Route11:grass", 96, (97, 97)) == 1
    assert _missing(catalog, "wild:Route5:grass", 56, (56, 57)) == 0
    old = replace(catalog, level_evolution_edges=())
    assert _missing(old, "wild:Route11:grass", 96, (96,)) == 0
    assert catalog.methods == RED_ACQUISITION_CATALOG.methods


def test_level_edges_are_derived_not_species_allowlisted_and_exclude_other_mechanics():
    graph = {
        96: (Evolution(96, 97, EvolutionMethod.LEVEL, 26),),
        16: (Evolution(16, 17, EvolutionMethod.LEVEL, 18),),
        25: (Evolution(25, 26, EvolutionMethod.STONE, 1),),
        64: (Evolution(64, 65, EvolutionMethod.TRADE),),
    }
    assert level_acquisition_edges(graph) == (
        (red_species_ref(16), red_species_ref(17)), (red_species_ref(96), red_species_ref(97)),
    )


@pytest.mark.parametrize("rule", [
    Evolution(95, 97, EvolutionMethod.LEVEL, 26),
    Evolution(96, 96, EvolutionMethod.LEVEL, 26),
    Evolution(96, 97, EvolutionMethod.LEVEL, True),
    Evolution(96, 97, EvolutionMethod.LEVEL, 101),
])
def test_invalid_level_rule_rejects(rule):
    with pytest.raises(ValueError):
        level_acquisition_edges({96: (rule,)})


def test_alternatives_require_the_explicit_remaining_demand_mode():
    with pytest.raises(ValueError, match="remaining"):
        replace(_catalog(), remaining_demand=False)


def test_observer_binds_cartridge_edges_prospectively_and_clears_for_old_mode(monkeypatch):
    runtime = RedGoalContextRuntime(
        profile=SimpleNamespace(providers=()), capture=None, emulator=None, reader=None,
        observer=None, adapter=None,
    )
    edges = ((red_species_ref(96), red_species_ref(97)),)
    def derive(rom):
        assert rom == b"authenticated-cartridge"
        return edges
    monkeypatch.setattr(
        "pokemon_red_completion.red_acquisition_alternatives.cartridge_level_acquisition_edges",
        derive,
    )
    monkeypatch.setattr(runner, "RedResourceGoalRouter",
                        lambda *_args, **_kwargs: SimpleNamespace(enumerate=None))
    monkeypatch.setattr(runner, "RedBoundedPlayerObserver",
                        lambda **kwargs: SimpleNamespace(**kwargs))
    observer = runner._player_observer(
        runtime, None, SimpleNamespace(rom=b"authenticated-cartridge"),
        remaining_acquisition_demand=True, level_evolution_acquisitions=True,
    )
    assert observer.runtime.level_evolution_acquisition_edges == edges
    assert runtime.level_evolution_acquisition_edges == ()  # Parent was not rewritten.
    old = runner._player_observer(observer.runtime, None, None)
    assert old.runtime.level_evolution_acquisition_edges == ()
    assert old.runtime.remaining_acquisition_demand is False


@pytest.mark.parametrize("enabled,demand,world", [(True, False, object()), (True, True, None),
                                                 ("true", True, object())])
def test_observer_rejects_unauthenticated_alternative_scope(enabled, demand, world):
    runtime = RedGoalContextRuntime(
        profile=SimpleNamespace(providers=()), capture=None, emulator=None, reader=None,
        observer=None, adapter=None,
    )
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="acquisitions_scope"):
        runner._player_observer(runtime, None, world, remaining_acquisition_demand=demand,
                                level_evolution_acquisitions=enabled)
