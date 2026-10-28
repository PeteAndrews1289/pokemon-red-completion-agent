import math

import pytest

from pokemon_red_completion.red_player_training_dataset import (
    _replay_probabilities_match,
    _replay_scores_match,
)


def test_historical_machine_rounding_preserves_recorded_probability_evidence():
    recorded = (0.0, 0.2807393324351535, 0.7192606675648465)
    replayed = (0.0, 0.2807393324351536, 0.7192606675648464)
    assert _replay_probabilities_match(recorded, replayed)
    assert recorded == (0.0, 0.2807393324351535, 0.7192606675648465)


@pytest.mark.parametrize(
    "recorded,replayed",
    [
        ((0.4, 0.6), (0.400000001, 0.599999999)),
        ((0.0, 1.0), (1e-17, 1.0)),
        ((1e-17, 1.0), (0.0, 1.0)),
        ((0.5, 0.5), (0.5,)),
        ((0.0, 0.0), (0.0, 0.0)),
        ((math.nan, 1.0), (0.0, 1.0)),
        ((0.0, 1.0), (math.inf, 1.0)),
        ((-1e-17, 1.0), (0.0, 1.0)),
        ((0.0, 1.0), (0.0, 1.000000000000001)),
        ((False, True), (0.0, 1.0)),
    ],
)
def test_replay_rejects_drift_illegal_support_and_malformed_evidence(recorded, replayed):
    assert not _replay_probabilities_match(recorded, replayed)


def test_score_rounding_preserves_unavailable_candidates():
    assert _replay_scores_match((0.8720703828430213, None), (0.8720703828430217, None))


@pytest.mark.parametrize(
    "recorded,replayed",
    [
        ((0.0, None), (0.0, 0.0)),
        ((0.0, 1.0), (0.0,)),
        ((0.0, 1.0), (0.0, 1.00000001)),
        ((math.nan,), (0.0,)),
        ((0.0,), (math.inf,)),
        ((False,), (0.0,)),
        ((), ()),
    ],
)
def test_score_replay_rejects_material_drift_and_malformed_support(recorded, replayed):
    assert not _replay_scores_match(recorded, replayed)
