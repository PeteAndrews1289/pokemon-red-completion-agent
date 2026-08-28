from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK,
)
from pokemon_red_completion.living_dex_causal_fit_readiness import (
    LivingDexCausalFitReadinessError,
    audit_living_dex_causal_fit_readiness,
    fit_powered_living_dex_causal_model,
    require_living_dex_causal_fit_ready,
)
from pokemon_red_completion.living_dex_causal_training_schedule import (
    freeze_living_dex_blocked_behavior_schedule,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_policy import (
    red_living_dex_setup_candidate_features,
)


def _train_templates() -> tuple[tuple[LivingDexOptionKind, ...], ...]:
    return tuple(
        slot.available_option_kinds
        for slot in build_red_living_dex_prospective_capture_plan().slots
        if slot.partition is LivingDexCapturePartition.TRAIN
    )


def _context(ordinal: int, *, collapsed: bool) -> LivingDexOptionContext:
    index = 0 if collapsed else ordinal
    values = tuple(
        ((index * prime + offset) % 17) / 16
        for offset, prime in enumerate((2, 3, 5, 7, 11, 13, 16))
    )
    return LivingDexOptionContext(*values)


def _features(
    kind: LivingDexOptionKind,
    *,
    ordinal: int,
    candidate_index: int,
    collapsed: bool,
) -> LivingDexOptionFeatures:
    index = tuple(LivingDexOptionKind).index(kind) if collapsed else ordinal
    return red_living_dex_setup_candidate_features(
        kind,
        route_controller_actions=(index * 17 + candidate_index * 11) % 997,
        maximum_controller_actions=1_000,
        estimated_effort=((index * 19 + candidate_index * 7) % 101) / 100,
        estimated_risk=((index * 23 + candidate_index * 5) % 101) / 100,
        storage_unit=((index * 29 + candidate_index * 3) % 101) / 100,
    )


def _outcome(ordinal: int, *, constant_success: bool = False) -> LivingDexObservedOutcome:
    success = True if constant_success else ordinal % 3 != 0
    values = tuple(
        ((ordinal * prime + offset) % 11) / 10
        for offset, prime in enumerate((2, 3, 5, 7, 8, 9, 10, 4))
    )
    return LivingDexObservedOutcome(
        LivingDexOutcomeStatus.SETTLED,
        success,
        *values,
    )


def _prospective_examples(
    *,
    collapsed: bool = False,
    constant_success: bool = False,
) -> tuple[LivingDexObservedArmExample, ...]:
    schedule = freeze_living_dex_blocked_behavior_schedule(
        _train_templates(),
        entropy=bytes(range(32)),
    )
    rows: list[LivingDexObservedArmExample] = []
    for ordinal, assignment in enumerate(schedule.assignments):
        kinds = schedule.menu_templates[assignment.template_ordinal]
        menu = LivingDexOptionMenu(
            _context(ordinal, collapsed=collapsed),
            tuple(
                LivingDexOptionCandidate(
                    f"private-binding-{ordinal}-{candidate_index}",
                    _features(
                        kind,
                        ordinal=ordinal,
                        candidate_index=candidate_index,
                        collapsed=collapsed,
                    ),
                    LivingDexOptionAvailability.AVAILABLE,
                )
                for candidate_index, kind in enumerate(kinds)
            ),
        )
        rows.append(
            LivingDexObservedArmExample(
                decision_sha256=f"{ordinal + 1:064x}",
                partition="train",
                menu=menu,
                selected_candidate_index=assignment.candidate_index,
                behavior_probabilities=(1.0 / 3.0,) * 3,
                outcome=_outcome(ordinal, constant_success=constant_success),
            )
        )
    return tuple(rows)


def _prefix(row: LivingDexObservedArmExample) -> tuple[LivingDexObservedArmExample, ...]:
    return (
        replace(
            row,
            decision_sha256="f" * 64,
            outcome=_outcome(91),
        ),
    )


def test_informative_complete_denominator_is_ready_without_fitting() -> None:
    rows = _prospective_examples()
    audit = audit_living_dex_causal_fit_readiness(
        rows,
        prefix_examples=_prefix(rows[0]),
    )
    public = audit.public_dict()

    assert audit.ready
    assert audit.prospective_examples == 90
    assert audit.prospective_settled_examples == 90
    assert audit.prefix_settled_examples == 1
    assert audit.distinct_selected_feature_rows >= 50
    assert audit.selected_feature_rank >= RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK
    assert audit.successful_examples == 60
    assert audit.unsuccessful_examples == 30
    assert len(audit.variable_outcome_heads) >= 5
    assert public["fit_executions"] == 0
    assert public["model_predictions"] == 0
    assert public["unexecuted_action_targets"] == 0
    assert public["private_identity_fields"] == 0


def test_censoring_cannot_shrink_the_denominator_into_a_fit() -> None:
    rows = list(_prospective_examples())
    censored = LivingDexObservedOutcome(
        LivingDexOutcomeStatus.CENSORED,
        censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
    )
    for index in range(31):
        rows[index] = replace(rows[index], outcome=censored)

    audit = audit_living_dex_causal_fit_readiness(
        rows,
        prefix_examples=_prefix(rows[-1]),
    )

    assert not audit.ready
    assert audit.prospective_examples == 90
    assert audit.prospective_settled_examples == 59
    assert sum(dict(audit.censored_candidate_index_counts).values()) == 31
    assert sum(dict(audit.censored_kind_counts).values()) == 31
    assert dict(audit.censor_reason_counts) == {"external_interruption": 31}
    assert "insufficient_settled_train_examples" in audit.reasons


def test_rank_and_distinctness_are_checked_on_observed_selected_rows() -> None:
    rows = _prospective_examples(collapsed=True)
    audit = audit_living_dex_causal_fit_readiness(
        rows,
        prefix_examples=_prefix(rows[0]),
    )

    assert not audit.ready
    assert audit.distinct_selected_feature_rows < 50
    assert audit.selected_feature_rank < RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK
    assert "insufficient_distinct_selected_feature_rows" in audit.reasons
    assert "insufficient_selected_feature_rank" in audit.reasons


def test_constant_success_cannot_be_called_an_informative_multioutcome_fit() -> None:
    rows = _prospective_examples(constant_success=True)
    audit = audit_living_dex_causal_fit_readiness(
        rows,
        prefix_examples=_prefix(rows[0]),
    )

    assert not audit.ready
    assert audit.successful_examples == 90
    assert audit.unsuccessful_examples == 0
    assert "insufficient_unsuccessful_train_examples" in audit.reasons
    assert "verified_success_head_is_constant" in audit.reasons


def test_behavior_schedule_and_immutable_prefix_remain_frozen() -> None:
    rows = list(_prospective_examples())
    rows[0] = replace(rows[0], behavior_probabilities=(0.5, 0.25, 0.25))
    audit = audit_living_dex_causal_fit_readiness(rows, prefix_examples=())

    assert not audit.ready
    assert "prospective_behavior_policy_differs" in audit.reasons
    assert "immutable_prefix_denominator_differs" in audit.reasons


def test_require_gate_stops_before_a_low_information_fit() -> None:
    rows = _prospective_examples(constant_success=True)
    with pytest.raises(LivingDexCausalFitReadinessError, match="readiness failed"):
        require_living_dex_causal_fit_ready(
            rows,
            prefix_examples=_prefix(rows[0]),
        )


def test_powered_entry_point_fits_the_complete_passing_denominator_once() -> None:
    rows = _prospective_examples()
    prefix = _prefix(rows[0])

    result = fit_powered_living_dex_causal_model(
        rows,
        prefix_examples=prefix,
    )

    assert result.readiness.ready
    assert result.fit.report.total_examples == 91
    assert result.fit.report.settled_examples == 91
    assert result.fit.report.train_dataset_sha256 == result.fit.model.train_dataset_sha256


def test_powered_entry_point_never_calls_fitter_after_a_failed_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pokemon_red_completion.living_dex_causal_fit_readiness as readiness_module

    rows = _prospective_examples(constant_success=True)
    fitter_calls = 0

    def forbidden_fit(*_args: object, **_kwargs: object) -> object:
        nonlocal fitter_calls
        fitter_calls += 1
        raise AssertionError("fitter must remain closed")

    monkeypatch.setattr(readiness_module, "fit_living_dex_option_value", forbidden_fit)
    with pytest.raises(LivingDexCausalFitReadinessError, match="readiness failed"):
        fit_powered_living_dex_causal_model(
            rows,
            prefix_examples=_prefix(rows[0]),
        )
    assert fitter_calls == 0
