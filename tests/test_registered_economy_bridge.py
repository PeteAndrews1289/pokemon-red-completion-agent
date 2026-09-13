"""Exercise the prospective bridge with valid synthetic registration evidence."""

import pytest
from test_registered_learning_bridge import observations

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_economy_learning import red_registered_economy_outcome
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.red_registered_outcome import red_registered_outcome_from_observations
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


@pytest.mark.parametrize(('succeeded', 'cash_after', 'gain', 'loss'), [
    (True, 900, 0.4, 0.0), (False, 200, 0.0, 0.3),
])
def test_settled_cash_metadata_retains_real_costs_without_relabeling_targets(
    tmp_path, succeeded, cash_after, gain, loss,
):
    _, before, _, policy = observations(tmp_path)
    observed = project_registered_observation(before, policy).public_dict()
    kwargs = dict(selected_kind=GoalKind.RESUPPLY, succeeded=succeeded,
                  actions=20, frames=200, maximum_actions=100, maximum_frames=1000)
    legacy = red_registered_outcome_from_observations(observed, observed, **kwargs)
    outcome = red_registered_economy_outcome(
        observed, observed, **kwargs, target_cash=1000,
        before_economy=EconomySnapshot(500, ()),
        after_economy=EconomySnapshot(cash_after, ()),
    )
    assert outcome.economy.useful_liquidity_gain == gain
    assert outcome.economy.cash_loss == loss
    assert outcome.economy.cash_delta == cash_after - 500
    assert outcome.completion_gain == 0
    assert outcome.action_cost == outcome.frame_cost == 0.2
    # Deliberate current limitation: metadata is not yet an economy target head.
    assert outcome.target_vector == legacy.target_vector
