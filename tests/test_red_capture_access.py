"""Independent item/state changes, not encounter species, govern capturability."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_skills import _ActionPort, _adapter, _AreaExecutor, _raw, _Reader

import pokemon_red_completion.surge as surge
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalUnavailableReason
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_capture_access import (
    is_unidentified_ghost_encounter,
    required_wild_source_items,
)
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider


@pytest.mark.parametrize('floor', range(1, 8))
def test_tower_source_requires_scope_independent_of_player_position(floor):
    assert required_wild_source_items(f'wild:PokemonTower{floor}F:grass') == (ItemId.SILPH_SCOPE,)


@pytest.mark.parametrize('source', ['wild:Route2:grass', 'wild:PokemonMansion1F:grass',
                                  'wild:NotPokemonTower3F:grass'])
def test_unrelated_sources_do_not_inherit_tower_requirements(source):
    assert required_wild_source_items(source) == ()


@pytest.mark.parametrize('map_id', [int(MapId.POKEMON_TOWER_1F), int(MapId.POKEMON_TOWER_7F)])
@pytest.mark.parametrize('count,expected', [(0, True), (1, False)])
def test_live_wild_ghost_depends_on_carried_item_not_underlying_species(map_id, count, expected):
    raw = replace(_raw(), map_id=map_id, battle_state=1, enemy_species_id=25,
                  bag_items=((int(ItemId.POKE_BALL), 20), (int(ItemId.SILPH_SCOPE), count)))
    assert is_unidentified_ghost_encounter(raw) is expected
    assert not is_unidentified_ghost_encounter(replace(raw, battle_state=2))
    assert not is_unidentified_ghost_encounter(replace(raw, battle_state=0))
    assert not is_unidentified_ghost_encounter(replace(raw, map_id=int(MapId.ROUTE_2)))


@pytest.mark.parametrize('count', [0, 1])
def test_provider_checks_destination_prerequisite_before_transport(count):
    reader = _Reader(raw=replace(_raw(poke_balls=20), map_id=int(MapId.ROUTE_1),
        bag_items=((4, 20), (int(ItemId.SILPH_SCOPE), count))), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedAreaSurveyGoalProvider(
        source_id='wild:PokemonTower3F:grass', area_executor=_AreaExecutor(reader, actions),
        actions=actions, emulator=port, adapter=adapter,
        required_capture_items=required_wild_source_items('wild:PokemonTower3F:grass'))
    availability = provider.resource_availability(adapter.observe())
    assert availability.executable is bool(count)
    if not count:
        assert availability.unavailable_reason is GoalUnavailableReason.MISSING_RESOURCE
    assert actions.actions_executed == 0


def test_unidentified_capture_fails_before_any_ball_or_controller_access(monkeypatch):
    raw = replace(_raw(poke_balls=20), map_id=int(MapId.POKEMON_TOWER_3F),
                  battle_state=1, enemy_species_id=25)
    reader = SimpleNamespace(read=lambda: raw)
    def forbidden(*_args, **_kwargs):
        pytest.fail('unidentified ghost must stop before controller or ball access')
    monkeypatch.setattr(surge, '_bag', forbidden)
    monkeypatch.setattr(surge, '_pulse', forbidden)
    monkeypatch.setattr(surge, '_navigate_main', forbidden)
    with pytest.raises(surge.SurgeChapterError, match='unidentified ghost'):
        surge._try_catch_wild(object(), object(), reader, 25, 'ghost guard', max_throws=5)


def test_scope_loss_during_preparation_stops_before_ball_menu(monkeypatch):
    state = SimpleNamespace(raw=replace(_raw(poke_balls=20),
        map_id=int(MapId.POKEMON_TOWER_3F), battle_state=1, enemy_species_id=25,
        bag_items=((4, 20), (int(ItemId.SILPH_SCOPE), 1))))
    reader = SimpleNamespace(read=lambda: state.raw)
    monkeypatch.setattr(surge, '_bag', lambda _: dict(state.raw.bag_items))
    monkeypatch.setattr(surge, '_living_specimen_count', lambda _: 1)
    monkeypatch.setattr(
        surge, '_navigate_main', lambda *_: pytest.fail('no throw after scope loss'))
    def prepare():
        state.raw = replace(state.raw, bag_items=((4, 20),))
        return True
    with pytest.raises(surge.SurgeChapterError, match='lost its required Silph Scope'):
        surge._try_catch_wild(object(), object(), reader, 25, 'ghost guard',
                             max_throws=5, before_throw=prepare)


def test_capture_access_transition_is_explicit_and_survives_retarget(monkeypatch):
    import runpy
    from pathlib import Path

    from test_red_living_dex_wild_corridor import _graph, _local_discovery_profile, _terrain

    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )
    module = runpy.run_path(str(
        Path(__file__).parents[1]/'scripts/run_paired_red_bounded_player.py'))
    derive = module['_regional_profiles']
    monkeypatch.setitem(derive.__globals__, '_route_world', lambda _: object())
    before = _local_discovery_profile()
    old, new = derive(before, ('capture-fly', 'capture-access-requirements'), object())
    assert 'capture_access_requirements' not in old.providers[0].parameters
    assert new.providers[0].parameters['capture_access_requirements'] is True
    assert derive(before, ('capture-fly',), object()) == (old,)
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget('wild:Route2:grass'), _terrain(), _graph())
    assert retarget_red_wild_profile(new, corridor).providers[0].parameters[
        'capture_access_requirements'] is True


@pytest.mark.parametrize('enabled', [False, True])
def test_runtime_factory_only_adds_requirement_to_prospective_profile(monkeypatch, enabled):
    from pokemon_red_completion.red_goal_context import _wild_provider
    from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic

    captured = {}
    monkeypatch.setattr('pokemon_red_completion.red_goal_context.LiveWildCorridorSurveyExecutor',
                        lambda *_a, **_k: SimpleNamespace(finish_at_starting_endpoint=lambda: None))
    def provider(**kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr(
        'pokemon_red_completion.red_goal_context.RedAreaSurveyGoalProvider', provider)
    parameters = dict(source_id='wild:PokemonTower3F:grass', label='synthetic Tower',
                      map_id=int(MapId.POKEMON_TOWER_3F), player_x=1, player_y=2,
                      forward_directions=('up',), starting_endpoint='south',
                      maximum_legs=8, maximum_seek_steps=64, maximum_encounters=16)
    if enabled:
        parameters['capture_access_requirements'] = True
    _wild_provider(SimpleNamespace(emulator=object(), reader=object(), adapter=object(),
        registration_policy=None, remaining_acquisition_demand=False,
        level_evolution_acquisition_edges=()),
        SimpleNamespace(parameters=parameters, mechanic=RedGoalMechanic.WILD_CORRIDOR_CAPTURE),
        CountingExecutor(SimpleNamespace(execute=lambda _: None)))
    assert captured['required_capture_items'] == ((ItemId.SILPH_SCOPE,) if enabled else ())
