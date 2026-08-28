from __future__ import annotations

import numpy as np

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK,
    RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LivingDexOptionContext,
)
from pokemon_red_completion.red_living_dex_setup_policy import (
    red_living_dex_setup_candidate_features,
)


def test_frozen_red_projection_rank_matches_the_full_reachable_subspace() -> None:
    rows: list[tuple[float, ...]] = []
    for ordinal in range(2_100):
        kind = RED_DIRECT_CAUSAL_OPTION_KINDS[ordinal % len(RED_DIRECT_CAUSAL_OPTION_KINDS)]
        context = LivingDexOptionContext(
            *(
                ((ordinal * prime + offset) % 101) / 100
                for offset, prime in enumerate((2, 3, 5, 7, 11, 13, 17))
            )
        )
        features = red_living_dex_setup_candidate_features(
            kind,
            route_controller_actions=(ordinal * 19) % 997,
            maximum_controller_actions=1_000,
            estimated_effort=((ordinal * 23 + 1) % 101) / 100,
            estimated_risk=((ordinal * 29 + 2) % 101) / 100,
            storage_unit=((ordinal * 31 + 3) % 101) / 100,
        )
        rows.append(features.vector(context))

    matrix = np.asarray(rows, dtype=np.float64)
    rank = int(np.linalg.matrix_rank(matrix))
    zero_features = tuple(
        name
        for index, name in enumerate(LIVING_DEX_OPTION_FEATURE_NAMES)
        if np.all(matrix[:, index] == 0.0)
    )

    assert rank == RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK == 16
    assert zero_features == RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES
