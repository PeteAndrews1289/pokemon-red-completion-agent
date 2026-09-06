from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_red_living_dex_development_supplement_plan import _inputs, _plan
from test_red_living_dex_development_supply import (
    _bindings_for_same_plan,
    _publish_model,
    _sha,
    _train_rows,
)
from test_red_living_dex_setup_recipe import _store

from pokemon_red_completion.red_living_dex_development_supply import (
    RedLivingDexDevelopmentSupplyError,
    load_red_living_dex_development_model,
)
from pokemon_red_completion.red_living_dex_targeted_exclusions import (
    RedLivingDexTargetedExclusionError,
    build_red_living_dex_targeted_exclusions,
    load_red_living_dex_targeted_training_exclusions,
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


def test_training_exclusions_preserve_unfitted_suffix_without_weakening_evaluation(
    tmp_path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    bindings, _ = _bindings_for_same_plan(store)
    model, record = _publish_model(store, _sha("prior-18-dataset"))
    rows = _train_rows(23)
    for module in ("red_living_dex_targeted_exclusions", "red_living_dex_development_supply"):
        monkeypatch.setattr(
            f"pokemon_red_completion.{module}.load_living_dex_authenticated_causal_examples",
            lambda _store: rows,
        )
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_development_supply."
        "living_dex_option_train_dataset_sha256",
        lambda _rows: _sha("current-23-dataset"),
    )
    with pytest.raises(RedLivingDexDevelopmentSupplyError, match="model record differs"):
        load_red_living_dex_development_model(
            store,
            expected_model_sha256=model.model_sha256,
            expected_model_record_sha256=record.summary.record_sha256,
        )
    supplement = _plan().supplement
    # The stock supplement fixture deliberately draws historical capabilities;
    # this fixture represents three genuinely disjoint later supplemental roots.
    supplement = replace(
        supplement,
        assignments=tuple(
            replace(
                item,
                lineage_sha256=_sha(("later-lineage", ordinal)),
                physical_root_sha256=_sha(("later-physical-root", ordinal)),
            )
            for ordinal, item in enumerate(supplement.assignments)
        ),
    )
    result = load_red_living_dex_targeted_training_exclusions(
        store,
        supplement,
        bindings=bindings,
    )
    assert result.train_lineages == frozenset(row.identity.lineage_sha256 for row in rows)
    assert result.historical_development_roots == 4
    assert result.supplemental_development_roots == 3
    assert result.public_dict()["model_fits"] == 0


def test_training_exclusion_loader_rejects_development_rows(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    rows = _train_rows(23)
    rows[-1].identity.partition = "development"
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_targeted_exclusions."
        "load_living_dex_authenticated_causal_examples",
        lambda _store: rows,
    )
    with pytest.raises(RedLivingDexTargetedExclusionError, match="corpus differs"):
        load_red_living_dex_targeted_training_exclusions(store, _plan().supplement)
