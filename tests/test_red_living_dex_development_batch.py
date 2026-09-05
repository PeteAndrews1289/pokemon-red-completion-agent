from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_red_living_dex_clustered_development_execution import (
    _consumer,
    _model_record,
)
from test_red_living_dex_clustered_train_runner import _clustered_fixture
from test_red_living_dex_development_supplement_plan import _plan as _supplement_plan
from test_red_living_dex_development_supplement_reader import _binding as _supplement_binding
from test_red_living_dex_setup_recipe import _store

from pokemon_red_completion import red_living_dex_development_batch as batch
from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentPreflightReceipt,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    authenticate_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_development_batch import (
    RedLivingDexDevelopmentBatchAssignment,
    RedLivingDexDevelopmentBatchError,
    inspect_red_living_dex_development_batch_inputs,
    preflight_red_living_dex_development_batch,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
)


def _assignments() -> tuple[
    tuple[RedLivingDexDevelopmentBatchAssignment, ...],
    dict[tuple[str, int], tuple[Any, Any]],
    Any,
    Any,
]:
    historical, historical_binding = _clustered_fixture()
    supplement = _supplement_plan()
    supplement_binding = _supplement_binding(supplement)
    assignments: list[RedLivingDexDevelopmentBatchAssignment] = []
    expected: dict[tuple[str, int], tuple[Any, Any]] = {}
    for ordinal in (10, 11):
        selection = authenticate_red_living_dex_development_selection(
            historical.private_dict(),
            ordinal,
            binding=historical_binding,
        )
        root = historical.assignments[ordinal].capability.root.root
        assignments.append(
            RedLivingDexDevelopmentBatchAssignment(historical_binding, ordinal, root)
        )
        expected[(historical_binding.private_plan_sha256, ordinal)] = (selection, root)
    for ordinal in range(3):
        selection = authenticate_red_living_dex_development_selection(
            supplement.private_dict(),
            ordinal,
            binding=supplement_binding,
        )
        root = supplement.assignments[ordinal].capability.root.root
        assignments.append(
            RedLivingDexDevelopmentBatchAssignment(supplement_binding, ordinal, root)
        )
        expected[(supplement_binding.private_plan_sha256, ordinal)] = (selection, root)
    return tuple(assignments), expected, historical_binding, supplement_binding


def test_batch_preflight_authenticates_exactly_two_historical_and_three_supplement_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, historical_binding, supplement_binding = _assignments()
    model_record = _model_record()
    calls: list[tuple[str, int]] = []
    meter = RedLivingDexSetupEffectMeter()
    before = meter.checkpoint()
    monkeypatch.setattr(
        batch,
        "_HISTORICAL_CASES",
        ((historical_binding, 10), (historical_binding, 11)),
    )
    monkeypatch.setattr(
        batch,
        "FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT",
        supplement_binding,
    )
    monkeypatch.setattr(
        batch,
        "load_red_living_dex_development_model",
        lambda *_args, **_kwargs: model_record,
    )

    def preflight(*_args: object, **kwargs: object) -> Any:
        binding = kwargs["binding"]
        ordinal = kwargs["ordinal"]
        assert hasattr(binding, "private_plan_sha256")
        assert isinstance(ordinal, int)
        key = (binding.private_plan_sha256, ordinal)
        selection, root = expected[key]
        assert kwargs["root_loader"](selection) == root
        calls.append(key)
        return RedLivingDexClusteredDevelopmentPreflightReceipt(
            selection,
            model_record.model.model_sha256,
        )

    monkeypatch.setattr(
        batch,
        "preflight_red_living_dex_development_assignment",
        preflight,
    )

    receipt = preflight_red_living_dex_development_batch(
        tmp_path,
        _store(tmp_path),
        consumer=_consumer(),
        assignments=assignments,
        meter=meter,
    )

    assert len(calls) == 5
    assert receipt.public_dict()["historical_cases_ready"] == 2
    assert receipt.public_dict()["supplement_cases_ready"] == 3
    assert receipt.public_dict()["model_predictions"] == 0
    assert receipt.public_dict()["controller_actions"] == 0
    assert meter.checkpoint() == before


def test_repeatable_input_readiness_joins_five_unclaimed_roots_without_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, historical_binding, supplement_binding = _assignments()
    model_record = _model_record()
    opened: list[tuple[str, int]] = []
    meter = RedLivingDexSetupEffectMeter()
    before = meter.checkpoint()
    monkeypatch.setattr(
        batch,
        "_HISTORICAL_CASES",
        ((historical_binding, 10), (historical_binding, 11)),
    )
    monkeypatch.setattr(
        batch,
        "FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT",
        supplement_binding,
    )
    monkeypatch.setattr(
        batch,
        "load_red_living_dex_development_model",
        lambda *_args, **_kwargs: model_record,
    )

    def load(_store: object, ordinal: int, *, binding: Any) -> tuple[Any, dict]:
        assert hasattr(binding, "private_plan_sha256")
        key = (binding.private_plan_sha256, ordinal)
        selection, _root = expected[key]
        opened.append(key)
        return selection, {"runtime_identity_sha256": "a" * 64}

    monkeypatch.setattr(batch, "load_red_living_dex_development_selection", load)
    monkeypatch.setattr(batch, "fixed_account_claim_registry_root", lambda: tmp_path)
    monkeypatch.setattr(
        batch,
        "observe_claim_first_pair_availability",
        lambda *_args: True,
    )

    receipt = inspect_red_living_dex_development_batch_inputs(
        _store(tmp_path),
        assignments=assignments,
        meter=meter,
    )

    public = receipt.public_dict()
    assert len(opened) == 5
    assert public["status"] == "five_development_inputs_ready_without_runtime_or_effects"
    assert public["claims_available"] == 5
    assert public["runtime_authenticated"] is False
    assert public["production_resolver_rehearsed"] is False
    assert public["exact_source_ci_binding"] is False
    assert public["model_predictions"] == 0
    assert meter.checkpoint() == before


def test_repeatable_input_readiness_rejects_consumed_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, historical_binding, supplement_binding = _assignments()
    model_record = _model_record()
    monkeypatch.setattr(
        batch,
        "_HISTORICAL_CASES",
        ((historical_binding, 10), (historical_binding, 11)),
    )
    monkeypatch.setattr(
        batch,
        "FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT",
        supplement_binding,
    )
    monkeypatch.setattr(
        batch,
        "load_red_living_dex_development_model",
        lambda *_args, **_kwargs: model_record,
    )

    def load(_store: object, ordinal: int, *, binding: Any) -> tuple[Any, dict]:
        selection, _root = expected[(binding.private_plan_sha256, ordinal)]
        return selection, {}

    availability = iter((True, True, False, True, True))
    monkeypatch.setattr(batch, "load_red_living_dex_development_selection", load)
    monkeypatch.setattr(batch, "fixed_account_claim_registry_root", lambda: tmp_path)
    monkeypatch.setattr(
        batch,
        "observe_claim_first_pair_availability",
        lambda *_args: next(availability),
    )

    with pytest.raises(RedLivingDexDevelopmentBatchError, match="unavailable"):
        inspect_red_living_dex_development_batch_inputs(
            _store(tmp_path),
            assignments=assignments,
            meter=RedLivingDexSetupEffectMeter(),
        )


def test_batch_shape_rejects_train_crossover_before_model_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, _expected, historical_binding, supplement_binding = _assignments()
    opened_model = False
    invalid = (
        RedLivingDexDevelopmentBatchAssignment(
            historical_binding,
            0,
            assignments[0].root,
        ),
        *assignments[1:],
    )
    monkeypatch.setattr(
        batch,
        "_HISTORICAL_CASES",
        ((historical_binding, 10), (historical_binding, 11)),
    )
    monkeypatch.setattr(
        batch,
        "FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT",
        supplement_binding,
    )

    def forbidden_model(*_args: object, **_kwargs: object) -> object:
        nonlocal opened_model
        opened_model = True
        raise AssertionError("train crossover opened the model")

    monkeypatch.setattr(batch, "load_red_living_dex_development_model", forbidden_model)

    with pytest.raises(RedLivingDexDevelopmentBatchError, match="shape differs"):
        preflight_red_living_dex_development_batch(
            tmp_path,
            _store(tmp_path),
            consumer=_consumer(),
            assignments=invalid,
            meter=RedLivingDexSetupEffectMeter(),
        )

    assert opened_model is False
