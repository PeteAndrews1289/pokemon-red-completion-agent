from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_scripted_gift import GIFT, observation

from pokemon_red_completion.red_gift_curriculum import (
    gift_curriculum_outcome,
    gift_curriculum_projection,
)


def obs(owned=False, size=6):
    o = observation(owned=owned, size=size)
    o.collection_observation.box_counts = (2 + int(owned and size == 6), 0)
    o.collection_observation.current_box_index = 0
    return o


def test_native_curriculum_units_and_no_synthetic_economy_or_choice():
    before, after = obs(), obs(True)
    row = gift_curriculum_outcome(before, after, GIFT, received=True, actions=90, frames=6000)
    assert row.completion_gain == 1/124
    assert row.action_cost == 90/30000
    assert row.frame_cost == 6000/3000000
    assert row.economy is None
    assert row.verified_success
    assert row.storage_cost == 1/38


def test_party_delivery_does_not_consume_box_headroom():
    row = gift_curriculum_outcome(obs(size=1), obs(True, size=1), GIFT,
                                 received=True, actions=90, frames=6000)
    assert row.storage_cost == 0


@pytest.mark.parametrize('change', ['cash', 'flag', 'party', 'actions', 'frames'])
def test_damaged_or_unmeasured_outcome_rejected(change):
    before, after = obs(), obs(True)
    args = dict(received=True, actions=90, frames=6000)
    if change == 'cash':
        after.raw = replace(after.raw, player_money=0)
    elif change == 'flag':
        args['received'] = False
    elif change == 'party':
        after.party.members = ()
    else:
        args[change] = 0
    with pytest.raises(ValueError):
        gift_curriculum_outcome(before, after, GIFT, **args)


def test_context_uses_actual_capacity_and_no_species_identity():
    before = obs()
    context, candidate = gift_curriculum_projection(before,
        NS(binding_ref='private-only', estimated_effort=0.2, estimated_risk=0))
    assert candidate.features.execution_effort == 0.2
    assert context.storage_pressure == 0
    assert 'private-only' not in str(candidate.policy_dict(context))
    assert len(candidate.vector(context, feature_version=4)) > 24


def test_curriculum_capacity_fail_closed():
    before = obs()
    before.collection_observation.box_counts = (20, 0)
    with pytest.raises(ValueError):
        gift_curriculum_projection(before, NS(binding_ref='x', estimated_effort=0.1,
                                             estimated_risk=0))
