from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_red_living_dex_development_supplement_plan import _inputs, _plan

from pokemon_red_completion.red_living_dex_targeted_exclusions import (
    RedLivingDexTargetedExclusionError,
    build_red_living_dex_targeted_exclusions,
)


def test_builds_private_complete_exclusions_with_aggregate_only_public_result() -> None:
    _capabilities, supply, _contexts, _bindings = _inputs()

    result = build_red_living_dex_targeted_exclusions(supply, _plan().supplement)

    assert len(result.train_lineages) == 18
    assert len(result.development_lineages) == 7
    assert len(result.development_physical_roots) == 7
    assert result.historical_development_roots == 4
    assert result.supplemental_development_roots == 3
    public = result.public_dict()
    assert public["train_lineages_excluded"] == 18
    assert public["development_lineages_excluded"] == 7
    assert public["outcomes_opened"] == 0
    encoded = json.dumps(public, sort_keys=True)
    assert all(lineage not in encoded for lineage in result.excluded_lineages)
    assert all(root not in encoded for root in result.development_physical_roots)


def test_rejects_supplement_that_reuses_a_historical_lineage() -> None:
    _capabilities, supply, _contexts, _bindings = _inputs()
    supplement = _plan().supplement
    repeated = replace(
        supplement.assignments[0],
        lineage_sha256=supply.historical_roots[0].lineage_sha256,
    )

    with pytest.raises(RedLivingDexTargetedExclusionError, match="repeats"):
        build_red_living_dex_targeted_exclusions(
            supply,
            replace(supplement, assignments=(repeated, *supplement.assignments[1:])),
        )
