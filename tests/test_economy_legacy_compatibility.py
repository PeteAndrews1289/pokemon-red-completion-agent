"""Frozen synthetic outputs measured before the prospective economy extension.

Baselines were computed from fcc33fae, not from the implementation under test.
These are regression fixtures, not private gameplay or training evidence.
"""

import pytest
from test_living_dex_goal_policy import _model
from test_living_dex_option_value import _menu

from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_optional_recovery,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.provenance import canonical_sha256


@pytest.mark.parametrize(('version', 'expected'), [
    (1, '57595a71df6cf6f204b0fdf7ac81cfe3eee3878b8b585ed487269bc494517922'),
    (2, '7882553fe830c900067dc7be325b7ef7afd5964c0a92e3e156ed27c1c3e102a5'),
    (3, '8523efddbca876bdca30a146424727f49ba0756ec348d303af3f79ebc458c9c7'),
])
def test_pre_economy_models_vectors_and_predictions_are_frozen(version, expected):
    model, menu = _model(), _menu()
    if version >= 2:
        model = upgrade_option_value_model_for_search_history(model)
    if version >= 3:
        model = upgrade_option_value_model_for_optional_recovery(model)
    document = {
        'model': model.to_dict(),
        'vectors': [list(c.vector(menu.context, feature_version=version))
                    for c in menu.candidates],
        'predictions': [list(model.predict_candidate(menu.context, c).vector())
                        for c in menu.candidates],
        'menu': menu.policy_dict(),
    }
    assert canonical_sha256(document) == expected
