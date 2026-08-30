from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion import living_dex_causal_journal as causal_journal_module
from pokemon_red_completion.living_dex_causal_integration_readiness import (
    LivingDexCausalIntegrationReadinessError,
    audit_living_dex_causal_integration_readiness,
    require_living_dex_causal_integration_ready,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexAuthenticatedCausalExample,
    LivingDexCausalBehaviorCommitment,
    LivingDexCausalBehaviorDecision,
    LivingDexCausalIdentity,
    LivingDexCausalTerminal,
    LivingDexCausalTerminalStatus,
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
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_policy import (
    red_living_dex_setup_candidate_features,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _row(
    index: int,
    *,
    selected_kind: LivingDexOptionKind,
    lineage: str | None = None,
    partition: str = "train",
    constant_target: bool = False,
    censored: bool = False,
    unsupported_candidate: bool = False,
) -> LivingDexAuthenticatedCausalExample:
    other_kinds = tuple(
        kind
        for kind in (
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.EVOLVE,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.RESUPPLY,
            LivingDexOptionKind.EXPLORE,
            LivingDexOptionKind.UNLOCK_ACCESS,
        )
        if kind is not selected_kind
    )
    kinds = (selected_kind, *other_kinds[:2])
    context = LivingDexOptionContext(
        collection_pressure=(index % 5) / 5,
        dependency_pressure=((index + 1) % 5) / 5,
        access_pressure=((index + 2) % 5) / 5,
        resource_pressure=((index + 3) % 5) / 5,
        storage_pressure=((index + 4) % 5) / 5,
        party_pressure=(index % 4) / 4,
        knowledge_pressure=((index + 1) % 4) / 4,
    )
    candidates: list[LivingDexOptionCandidate] = []
    for candidate_index, kind in enumerate(kinds):
        features = red_living_dex_setup_candidate_features(
            kind,
            route_controller_actions=20 + index * 3 + candidate_index,
            maximum_controller_actions=1_000,
            estimated_effort=(10 + index + candidate_index) / 100,
            estimated_risk=(5 + index + candidate_index) / 100,
            storage_unit=(index + candidate_index + 1) / 100,
        )
        if unsupported_candidate and candidate_index == 2:
            features = LivingDexOptionFeatures(
                kind=features.kind,
                completion_gain=features.completion_gain,
                dependency_unlock_gain=features.dependency_unlock_gain,
                travel_effort=features.travel_effort,
                execution_effort=features.execution_effort,
                resource_cost=0.1,
                storage_cost=features.storage_cost,
                party_risk=features.party_risk,
                irreversibility_risk=features.irreversibility_risk,
                uncertainty=features.uncertainty,
            )
        candidates.append(
            LivingDexOptionCandidate(
                f"private-row-{index}-{candidate_index}",
                features,
                LivingDexOptionAvailability.AVAILABLE,
            )
        )
    menu = LivingDexOptionMenu(context, tuple(candidates))
    identity = LivingDexCausalIdentity(
        source_commit="a" * 40,
        partition=partition,
        lineage_sha256=_sha(("lineage", index)) if lineage is None else lineage,
        setup_terminal_sha256=_sha(("setup-terminal", index)),
        setup_pair_claim_sha256=_sha(("setup-pair", index)),
        setup_attestation_sha256=_sha(("setup-attestation", index)),
        state_sha256=_sha(("state", index)),
        envelope_sha256=_sha(("envelope", index)),
        menu_sha256=menu.policy_sha256,
        binding_roster_sha256=_sha(("binding-roster", index)),
        origin_observation_sha256=_sha(("origin", index)),
        observer_binding_sha256=_sha(("observer", index)),
        effect_meter_binding_sha256=_sha(("meter", index)),
        runner_sha256=_sha(("runner", index)),
    )
    behavior: LivingDexCausalBehaviorDecision | None = None
    for seed_index in range(1, 1_000):
        commitment = LivingDexCausalBehaviorCommitment(
            identity.identity_sha256,
            partition,
            menu.policy_sha256,
            f"{index * 1_000 + seed_index:064x}",
        )
        weights, probabilities, selected = (
            causal_journal_module._behavior_decision_values(
                len(menu.candidates),
                menu.available_indices,
                commitment=commitment,
            )
        )
        if selected == 0:
            behavior = LivingDexCausalBehaviorDecision(
                commitment,
                menu.available_indices,
                weights,
                probabilities,
                selected,
            )
            break
    assert behavior is not None

    if censored:
        outcome = LivingDexObservedOutcome(
            LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
        )
    else:
        outcome = LivingDexObservedOutcome(
            LivingDexOutcomeStatus.SETTLED,
            verified_success=True if constant_target else index % 2 == 0,
            completion_gain=0.5 if constant_target else (index % 3) / 3,
            dependency_unlock_gain=0.25 if constant_target else (index % 4) / 4,
            action_cost=0.1 if constant_target else ((index % 8) + 1) / 10,
            frame_cost=0.2 if constant_target else ((index % 7) + 2) / 10,
            resource_cost=0.0,
            party_cost=0.0 if constant_target else (index % 2) / 10,
            storage_cost=0.1,
            irreversible_loss=0.0,
        )
    example = LivingDexObservedArmExample(
        decision_sha256=_sha(("decision", index)),
        partition=partition,
        menu=menu,
        selected_candidate_index=0,
        behavior_probabilities=behavior.probabilities,
        outcome=outcome,
    )
    record_sha256 = _sha(("example-record", index))
    terminal = LivingDexCausalTerminal(
        identity.identity_sha256,
        _sha(("pair", index)),
        LivingDexCausalTerminalStatus.COMPLETE,
        record_sha256,
        None,
        1,
    )
    return LivingDexAuthenticatedCausalExample(
        identity,
        behavior,
        example,
        terminal,
        record_sha256,
    )


def _ready_rows() -> tuple[LivingDexAuthenticatedCausalExample, ...]:
    kinds = (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.RESUPPLY,
    )
    return tuple(
        _row(index, selected_kind=kinds[index % len(kinds)])
        for index in range(8)
    )


def test_complete_supported_diverse_denominator_opens_only_the_plumbing_fit() -> None:
    audit = audit_living_dex_causal_integration_readiness(_ready_rows())
    public = audit.public_dict()

    assert audit.ready
    assert audit.authentic_examples == 8
    assert audit.distinct_lineages == 8
    assert audit.distinct_selected_option_kinds == 4
    assert audit.distinct_selected_feature_rows == 8
    assert audit.variable_target_heads >= 1
    assert audit.verified_success_varies
    assert public["fit_authority_if_ready"] == "non-authoritative-integration-only"
    assert public["fit_executions"] == 0
    assert public["model_predictions"] == 0
    assert public["controller_actions"] == 0
    assert public["teacher_queries"] == 0
    assert public["private_identity_fields"] == 0
    assert public["private_path_fields"] == 0


def test_denominator_cannot_be_shrunk_or_filled_with_censored_or_development_rows() -> None:
    rows = _ready_rows()
    partial = audit_living_dex_causal_integration_readiness(rows[:-1])
    assert not partial.ready
    assert "authentic_example_denominator_differs" in partial.reasons

    censored = audit_living_dex_causal_integration_readiness(
        (*rows[:-1], _row(20, selected_kind=LivingDexOptionKind.ACQUIRE, censored=True))
    )
    assert not censored.ready
    assert "unsettled_or_censored_example_present" in censored.reasons

    development = audit_living_dex_causal_integration_readiness(
        (
            *rows[:-1],
            _row(
                21,
                selected_kind=LivingDexOptionKind.ACQUIRE,
                partition="development",
            ),
        )
    )
    assert not development.ready
    assert "train_only_partition_differs" in development.reasons


def test_lineage_kind_feature_and_target_contrast_each_fail_closed() -> None:
    repeated_lineage = _sha("one-lineage")
    lineage_rows = tuple(
        _row(
            index,
            selected_kind=LivingDexOptionKind.ACQUIRE,
            lineage=repeated_lineage if index < 3 else _sha(("lineage", index)),
        )
        for index in range(8)
    )
    lineage_audit = audit_living_dex_causal_integration_readiness(lineage_rows)
    assert "lineage_multiplicity_exceeds_bound" in lineage_audit.reasons
    assert "insufficient_selected_option_kinds" in lineage_audit.reasons

    rows = list(_ready_rows())
    rows[-1] = _row(
        30,
        selected_kind=LivingDexOptionKind.RESUPPLY,
        unsupported_candidate=True,
    )
    unsupported = audit_living_dex_causal_integration_readiness(tuple(rows))
    assert "unsupported_red_candidate_feature_row" in unsupported.reasons

    constant = tuple(
        _row(
            index,
            selected_kind=(
                LivingDexOptionKind.ACQUIRE
                if index % 2 == 0
                else LivingDexOptionKind.EVOLVE
            ),
            constant_target=True,
        )
        for index in range(8)
    )
    constant_audit = audit_living_dex_causal_integration_readiness(constant)
    assert "insufficient_target_variation" in constant_audit.reasons


def test_repeated_decision_is_not_an_independent_example() -> None:
    rows = list(_ready_rows())
    rows[1] = replace(
        rows[1],
        example=replace(
            rows[1].example,
            decision_sha256=rows[0].example.decision_sha256,
        ),
    )

    audit = audit_living_dex_causal_integration_readiness(tuple(rows))

    assert not audit.ready
    assert "repeated_decision_identity" in audit.reasons


def test_require_gate_stops_before_a_low_information_fit() -> None:
    constant = tuple(
        _row(
            index,
            selected_kind=(
                LivingDexOptionKind.ACQUIRE
                if index % 2 == 0
                else LivingDexOptionKind.EVOLVE
            ),
            constant_target=True,
        )
        for index in range(8)
    )
    with pytest.raises(
        LivingDexCausalIntegrationReadinessError,
        match="failed closed",
    ):
        require_living_dex_causal_integration_ready(constant)
