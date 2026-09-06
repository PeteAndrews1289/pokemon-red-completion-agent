from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
from test_living_dex_policy_development import _model
from test_red_living_dex_causal_campaign import _registry
from test_red_living_dex_setup_recipe import _ArmFactory, _identity, _Reader, _store
from test_red_living_dex_targeted_bank_retirement_reader import _payload
from test_red_living_dex_targeted_train_runner import (
    _FailingProductionResolver,
    _SyntheticProductionResolver,
)

from pokemon_red_completion.observation import RedBoxCollectionState, RedCurrentBoxState
from pokemon_red_completion.red_living_dex_retired_bank_paired import (
    RedLivingDexRetiredPairedAssignment,
    RedLivingDexRetiredPairedError,
    retired_paired_campaign_summary,
    run_red_living_dex_retired_paired_assignment,
)
from pokemon_red_completion.red_living_dex_setup_trust import RedLivingDexSetupEffectMeter


class _RunnableReader(_Reader):
    """Prospective fixture resources genuinely require storage and supply options."""

    def read(self):  # type: ignore[no-untyped-def]
        raw = super().read()
        return replace(
            raw, bag_items=tuple((item, 2 if item == 4 else count) for item, count in raw.bag_items)
        )

    def read_all_box_states(self):  # type: ignore[no-untyped-def]
        return RedBoxCollectionState(
            (
                RedCurrentBoxState(0, (84,) * 19, (10,) * 19),
                *(RedCurrentBoxState(index, (), ()) for index in range(1, 12)),
            ),
            0,
            False,
        )


class _RunnableFactory(_ArmFactory):
    def __call__(self, *args):  # type: ignore[no-untyped-def]
        arm = super().__call__(*args)
        arm.reader = _RunnableReader(arm)
        return arm


@lru_cache(maxsize=1)
def _binding():  # type: ignore[no-untyped-def]
    return _payload(9)[0].binding


def _inputs(tmp_path: Path, *, failing: bool = False):  # type: ignore[no-untyped-def]
    assignment = RedLivingDexRetiredPairedAssignment(_binding(), 8)
    identity = _identity()
    meter = RedLivingDexSetupEffectMeter()
    factory = _RunnableFactory(identity, meter)
    resolver_type = _FailingProductionResolver if failing else _SyntheticProductionResolver
    resolver = resolver_type(assignment.capability.recipe, identity, factory)
    model = _model()
    return (
        assignment,
        model,
        dict(
            expected_model_sha256=model.model_sha256,
            store=_store(tmp_path),
            claim_registry=_registry(tmp_path),
            setup_execution_identity=identity,
            resolver=resolver,
            meter=meter,
        ),
    )


@pytest.mark.parametrize("ordinal", [0, 7, 12, -1, True])
def test_train_and_reserve_are_inaccessible(ordinal: int) -> None:
    with pytest.raises(RedLivingDexRetiredPairedError):
        RedLivingDexRetiredPairedAssignment(_binding(), ordinal)


def test_real_setup_and_selected_executor_seams_recover_without_more_input(tmp_path: Path) -> None:
    assignment, model, kwargs = _inputs(tmp_path)
    result = run_red_living_dex_retired_paired_assignment(assignment, model, **kwargs)
    assert result.setup["status"] == "complete", result.setup
    assert result.comparison is not None
    assert len(result.comparison.arms) == 2
    assert kwargs["meter"].provider_executions == 2
    assert kwargs["resolver"].calls == 3
    before = kwargs["meter"].checkpoint()
    recovered = run_red_living_dex_retired_paired_assignment(assignment, model, **kwargs)
    assert recovered == result
    assert kwargs["meter"].checkpoint() == before
    assert kwargs["resolver"].calls == 3
    assert result.public_dict()["training_targets_emitted"] == 0


def test_setup_failure_retains_cause_without_retry_or_model_prediction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment, model, kwargs = _inputs(tmp_path, failing=True)

    def no_prediction(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("setup failure must not predict")

    monkeypatch.setattr(type(model), "predict_candidate", no_prediction)
    result = run_red_living_dex_retired_paired_assignment(assignment, model, **kwargs)
    assert result.comparison is None
    assert result.setup["status"] == "failed"
    assert (
        result.setup["private_diagnostic"]["exception_type"] == "RedLivingDexProductionRuntimeError"
    )
    assert result.setup["private_diagnostic"]["frames"]
    assert "private diagnostic" not in str(result.public_dict())
    assert run_red_living_dex_retired_paired_assignment(assignment, model, **kwargs) == result
    assert kwargs["resolver"].calls == 1
    assert kwargs["meter"].provider_executions == 0


def test_interrupted_setup_is_not_reconstructed(tmp_path: Path) -> None:
    assignment, model, kwargs = _inputs(tmp_path)

    def interrupt(stage: str) -> None:
        if stage == "after_setup_claim":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_red_living_dex_retired_paired_assignment(
            assignment, model, **kwargs, failpoint=interrupt
        )
    result = run_red_living_dex_retired_paired_assignment(assignment, model, **kwargs)
    assert result.setup["status"] == "interrupted"
    assert result.comparison is None
    assert kwargs["resolver"].calls == 0


def test_incomplete_denominator_cannot_be_reported_as_campaign(tmp_path: Path) -> None:
    assignment, model, kwargs = _inputs(tmp_path, failing=True)
    result = run_red_living_dex_retired_paired_assignment(assignment, model, **kwargs)
    with pytest.raises(RedLivingDexRetiredPairedError, match="four-root denominator"):
        retired_paired_campaign_summary((result,))
