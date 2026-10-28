import json
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.red_player_configuration import (
    PREPARATION_QUANTUM_SCHEMA, RedPlayerConfiguration, assemble_configured_player,
)
from pokemon_red_completion.red_player_preparation_binding import preparation_encounter_limits
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
from test_red_player_configuration import config


@pytest.mark.parametrize('quantum', [1, 8, 64])
@pytest.mark.parametrize('mode', ['base', 'route', 'venue', 'helper'])
def test_quantum_roundtrip_preserves_existing_capabilities_and_legacy_identity(quantum, mode):
    old = config()
    if mode in ('route', 'venue', 'helper'):
        old = replace(old, quote_capture_route_work=True)
    if mode in ('venue', 'helper'):
        old = replace(old, evolution_venue_model_sha256='e' * 64,
                      evolution_venue_scope=('route11', 'digletts_cave'))
    if mode == 'helper':
        old = replace(old, evolution_allow_direct_fights=False)
    legacy = old.to_dict()
    candidate = replace(old, preparation_encounter_quantum=quantum)
    encoded = json.loads(json.dumps(candidate.to_dict()))
    assert encoded['schema'] == PREPARATION_QUANTUM_SCHEMA
    assert encoded['preparation_encounter_quantum'] == quantum
    assert RedPlayerConfiguration.from_dict(encoded) == candidate
    assert candidate.sha256 != old.sha256
    assert replace(candidate, preparation_encounter_quantum=None).to_dict() == legacy
    assert RedPlayerConfiguration.from_dict(legacy).sha256 == old.sha256


@pytest.mark.parametrize('value', [True, False, 0, -1, 65, 8.0, '8', (), float('nan')])
def test_quantum_rejects_coercion_or_widening_at_constructor_and_reader(value):
    with pytest.raises(ValueError, match='encounter quantum'):
        replace(config(), preparation_encounter_quantum=value)
    document = replace(config(), preparation_encounter_quantum=8).to_dict()
    document['preparation_encounter_quantum'] = value
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(document)


def test_quantum_requires_its_version_and_exact_explicit_field():
    old = config().to_dict()
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(dict(old, preparation_encounter_quantum=8))
    changed = dict(old, schema=PREPARATION_QUANTUM_SCHEMA)
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(changed)
    with pytest.raises(ValueError):
        RedPlayerConfiguration.from_dict(dict(changed, preparation_encounter_quantum=None))


@pytest.mark.parametrize('quantum', [None, 1, 8, 64])
def test_only_declared_quantum_reaches_backend_and_limits_recoveries(tmp_path, quantum):
    calls = []

    def assemble(*args, **kwargs):
        calls.append(kwargs)
        menu = NativeStoryBranchInventory(lambda *_: GoalBindingSet((), ()), lambda *_: ())
        return b'unchanged', None, menu, {}, {'partition': 'development'}

    configuration = replace(config(), preparation_encounter_quantum=quantum)
    payload, _, _, _, source = assemble_configured_player(
        N(assembly=assemble), configuration, tmp_path, tmp_path,
        plan_path=tmp_path / 'PLAN.json')
    assert payload == b'unchanged'
    assert source['configuration_sha256'] == configuration.sha256
    if quantum is None:
        assert 'preparation_encounter_quantum' not in calls[0]
        assert preparation_encounter_limits() == (64, 63)
    else:
        assert calls[0]['preparation_encounter_quantum'] == quantum
        assert preparation_encounter_limits(quantum) == (quantum, quantum - 1)
