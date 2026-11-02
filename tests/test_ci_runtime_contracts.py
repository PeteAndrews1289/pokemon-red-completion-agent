"""ROM-free typed boundary regressions; no emulator, model or training."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_live_safari import _area

from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context import RedGoalContextError, red_capture_source_catalog
from pokemon_red_completion.red_live_safari import RedLiveSafariError, _paid_patrol_quote_limits
from pokemon_red_completion.red_player_training_dataset import _replay_probabilities_match


@pytest.mark.parametrize(
    "quote",
    [
        {},
        {"steps_after_admission": True, "two_grass": {"exit_steps": [2, 3]}},
        {"steps_after_admission": -1, "two_grass": {"exit_steps": [2, 3]}},
        {"steps_after_admission": 100, "two_grass": None},
        {"steps_after_admission": 100, "two_grass": {"exit_steps": []}},
        {"steps_after_admission": 100, "two_grass": {"exit_steps": "23"}},
        {"steps_after_admission": 100, "two_grass": {"exit_steps": [True, 3]}},
        {"steps_after_admission": 100, "two_grass": {"exit_steps": [-1, 3]}},
    ],
)
def test_invalid_paid_patrol_quote_refused_when_area_is_constructed(quote):
    area = _area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 2, 10)
    with pytest.raises(RedLiveSafariError):
        replace(area, paid_patrol_quote=quote)


def test_paid_patrol_quote_preserves_zero_and_exact_exit_limits():
    quote = {"steps_after_admission": 100, "two_grass": {"exit_steps": [0, 3]}}
    assert _paid_patrol_quote_limits(quote) == (100, (0, 3))
    assert quote["two_grass"]["exit_steps"] == [0, 3]


def test_registered_capture_refuses_absent_observation_before_policy_query():
    class Policy:
        def goal_registered(self, observation):
            pytest.fail("missing observation must not reach the registration policy")

    with pytest.raises(RedGoalContextError, match="current collection observation"):
        red_capture_source_catalog(
            SimpleNamespace(registration_policy=Policy()), "source", None, None
        )


def test_missing_behavior_distribution_cannot_enter_replay():
    assert _replay_probabilities_match(None, (0.25, 0.75)) is False
