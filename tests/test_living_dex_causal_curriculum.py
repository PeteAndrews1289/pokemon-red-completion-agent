from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_causal_curriculum import (
    LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT,
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK,
    RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES,
    LivingDexCausalCapacityContext,
    LivingDexCausalCurriculumDesign,
    LivingDexCausalCurriculumError,
    audit_living_dex_causal_capacity,
    canonical_living_dex_causal_curriculum_bytes,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LivingDexOptionContext,
    LivingDexOptionKind,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = PROJECT_ROOT / "configs" / "living-dex-causal-curriculum-v1.json"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _option_context(index: int, *, distinct_values: int) -> LivingDexOptionContext:
    values = tuple(
        ((index + offset) % distinct_values) / (distinct_values - 1) for offset in range(7)
    )
    return LivingDexOptionContext(*values)


def _menu_with_focus(
    focus: LivingDexOptionKind,
    *,
    assigned_index: int,
) -> tuple[LivingDexOptionKind, ...]:
    remaining = tuple(kind for kind in RED_DIRECT_CAUSAL_OPTION_KINDS if kind is not focus)
    menu = [remaining[0], remaining[1], remaining[2]]
    menu[assigned_index] = focus
    if len(set(menu)) != 3:
        menu = [focus, remaining[0], remaining[1]]
        menu[0], menu[assigned_index] = menu[assigned_index], menu[0]
    return tuple(menu)


def _capacity_rows() -> tuple[LivingDexCausalCapacityContext, ...]:
    design = LivingDexCausalCurriculumDesign()
    train_focus = tuple(
        kind
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
        for _ in range(design.prospective_selected_kind_counts[kind.value])
    )
    development_focus = tuple(
        kind
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
        for _ in range(design.minimum_development_contexts_per_focus_kind)
    )
    rows: list[LivingDexCausalCapacityContext] = []
    for partition, focuses in (
        ("train", train_focus),
        ("development", development_focus),
    ):
        for ordinal, focus in enumerate(focuses):
            assigned_index = ordinal % 3 if partition == "train" else 0
            menu = _menu_with_focus(focus, assigned_index=assigned_index)
            prefix = f"{partition}-{ordinal}"
            rows.append(
                LivingDexCausalCapacityContext(
                    context_identity_sha256=_digest(f"context-{prefix}"),
                    physical_root_sha256=_digest(f"root-{prefix}"),
                    independence_lineage_sha256=_digest(f"lineage-{prefix}"),
                    family_scope_sha256=_digest(f"{partition}-family-scope-{ordinal % 6}"),
                    location_scope_sha256=_digest(f"{partition}-location-scope-{ordinal % 5}"),
                    template_scope_sha256=_digest(
                        f"{partition}-template-{ordinal % (10 if partition == 'train' else 5)}"
                    ),
                    menu_shape_sha256=_digest(f"menu-{prefix}"),
                    semantic_family_sha256s=tuple(
                        _digest(f"{partition}-semantic-{ordinal}-{index}") for index in range(3)
                    ),
                    partition=partition,  # type: ignore[arg-type]
                    option_kinds=menu,
                    focus_kind=focus,
                    option_context=_option_context(
                        ordinal,
                        distinct_values=5 if partition == "train" else 3,
                    ),
                    assigned_candidate_index=(assigned_index if partition == "train" else None),
                    root_available=True,
                    same_reset_policy_forks_feasible=True,
                )
            )
    return tuple(rows)


def test_design_separates_integration_fit_and_powered_policy_evaluation() -> None:
    design = LivingDexCausalCurriculumDesign()
    document = design.public_dict()

    assert len(LIVING_DEX_OPTION_FEATURE_NAMES) == 24
    assert design.minimum_settled_train_examples == 60
    assert design.prospective_train_contexts == 90
    assert design.prospective_development_contexts == 105
    assert design.minimum_complete_development_pairs == 102
    assert design.minimum_train_feature_rank == RED_SETUP_POLICY_MAXIMUM_FEATURE_RANK == 16
    assert design.maximum_censored_development_contexts == 3
    assert design.paired_design.minimum_contexts == 67
    assert design.paired_design.achieved_power == pytest.approx(0.9438267911243665)
    assert design.worst_case_censoring_power == pytest.approx(0.8321468701455965)
    assert design.paired_design.adequately_powered
    assert document["integration_floor"] == {
        "development_examples": 4,
        "grants_authority": False,
        "purpose": "plumbing_shapes_and_censoring_only",
        "train_examples": 8,
    }
    assert document["evaluation"]["endpoint"] == (  # type: ignore[index]
        LIVING_DEX_CAUSAL_EVALUATION_ENDPOINT
    )
    assert document["evaluation"]["baseline_envelope"] == [  # type: ignore[index]
        "frozen_random",
        "cost_only",
        "myopic_completion_greedy",
    ]
    assert document["authorization"] == {
        "crystal_execution": False,
        "full_game_replay": False,
        "model_fit": False,
        "private_context_access": False,
        "red_gameplay": False,
        "sealed_red": False,
    }
    assert document["feature_contract"][  # type: ignore[index]
        "red_setup_policy_structurally_zero_features"
    ] == list(RED_SETUP_POLICY_STRUCTURALLY_ZERO_FEATURES)
    assert document["transfer_authority"] == {  # type: ignore[index]
        "crystal_adaptation_required_for_trade_authority": True,
        "red_unseen_kinds_receive_zero_kind_coefficient": ["trade"],
        "red_unseen_mechanics_are_abstention_falsifiers": [
            "trade",
            "time_dependent_availability",
            "breeding_recoverability",
            "held_item_state",
        ],
        "zero_shot_crystal_claim_scope": "shared_supported_kinds_only_before_adaptation",
    }


def test_canonical_design_is_replayable_path_free_and_digest_bound() -> None:
    payload = canonical_living_dex_causal_curriculum_bytes()
    document = json.loads(payload)
    design = LivingDexCausalCurriculumDesign()

    assert payload.endswith(b"\n")
    assert document == design.public_dict()
    assert document["design_sha256"] == design.design_sha256
    assert (
        design.design_sha256
        == hashlib.sha256(
            json.dumps(
                design.public_dict(include_digest=False),
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        ).hexdigest()
    )
    encoded = payload.decode("ascii")
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "state_sha256",
        "physical_root_sha256",
        "species_ref",
        "map_id",
    ):
        assert forbidden not in encoded
    configured_rom = os.environ.get("POKEMON_RED_ROM")
    if configured_rom is not None:
        assert configured_rom not in encoded


def test_committed_design_matches_generator_and_check_mode() -> None:
    assert DESIGN_PATH.read_bytes() == canonical_living_dex_causal_curriculum_bytes()
    subprocess.run(
        [
            sys.executable,
            "scripts/regenerate_living_dex_causal_curriculum.py",
            "--check",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_balanced_abstractly_varied_capacity_passes_without_private_projection() -> None:
    audit = audit_living_dex_causal_capacity(_capacity_rows())
    public = audit.public_dict()

    assert audit.ready
    assert audit.reasons == ()
    assert audit.train_contexts == 90
    assert audit.development_contexts == 105
    assert audit.distinct_physical_roots == 195
    assert audit.distinct_independence_lineages == 195
    assert dict(audit.train_candidate_index_counts) == {"0": 30, "1": 30, "2": 30}
    assert set(dict(audit.train_focus_kind_counts)) == {
        kind.value for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    }
    assert set(dict(audit.development_focus_kind_counts)) == {
        kind.value for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
    }
    assert audit.train_pressure_value_counts == (5,) * 7
    assert audit.development_pressure_value_counts == (3,) * 7
    assert audit.train_menu_templates == 10
    assert audit.train_template_context_counts == (9,) * 10
    assert audit.train_template_candidate_schedules_balanced == 10
    assert audit.development_menu_templates == 5
    assert public["private_identity_fields"] == 0
    assert public["private_path_fields"] == 0
    assert public["model_predictions"] == 0
    assert public["red_gameplay_executions"] == 0


def test_integration_floor_fails_capacity_instead_of_becoming_training() -> None:
    rows = _capacity_rows()
    integration_only = (*rows[:10], *rows[90:95])
    audit = audit_living_dex_causal_capacity(integration_only)

    assert not audit.ready
    assert "insufficient_train_contexts" in audit.reasons
    assert "insufficient_development_contexts" in audit.reasons
    assert "insufficient_train_kind_schedule" in audit.reasons
    assert "insufficient_development_kind_schedule" in audit.reasons
    assert "train_candidate_position_imbalance" in audit.reasons


def test_capacity_distinguishes_lineage_pressure_and_fork_failures() -> None:
    rows = list(_capacity_rows())
    rows[1] = replace(
        rows[1],
        independence_lineage_sha256=rows[0].independence_lineage_sha256,
    )
    for index, row in enumerate(rows):
        context = row.option_context
        rows[index] = replace(
            row,
            option_context=LivingDexOptionContext(
                0.5,
                context.dependency_pressure,
                context.access_pressure,
                context.resource_pressure,
                context.storage_pressure,
                context.party_pressure,
                context.knowledge_pressure,
            ),
        )
    rows[-1] = replace(rows[-1], same_reset_policy_forks_feasible=False)

    audit = audit_living_dex_causal_capacity(rows)

    assert not audit.ready
    assert "duplicate_independence_lineage" in audit.reasons
    assert "insufficient_train_pressure_variation" in audit.reasons
    assert "insufficient_development_pressure_variation" in audit.reasons
    assert "insufficient_same_reset_policy_fork_capacity" in audit.reasons


def test_capacity_rejects_aggregate_balance_that_skips_a_menu_template() -> None:
    rows = list(_capacity_rows())
    rows[0] = replace(
        rows[0],
        template_scope_sha256=rows[1].template_scope_sha256,
    )

    audit = audit_living_dex_causal_capacity(rows)

    assert not audit.ready
    assert "train_menu_template_schedule_differs" in audit.reasons
    assert "train_template_candidate_schedule_differs" in audit.reasons


def test_capacity_rejects_a_train_answer_or_trade_row_disguised_as_red() -> None:
    rows = _capacity_rows()
    with pytest.raises(
        LivingDexCausalCurriculumError,
        match="development capacity cannot contain",
    ):
        replace(rows[-1], assigned_candidate_index=0)
    with pytest.raises(
        LivingDexCausalCurriculumError,
        match="directly executable kinds",
    ):
        replace(
            rows[0],
            option_kinds=(
                LivingDexOptionKind.TRADE,
                LivingDexOptionKind.ACQUIRE,
                LivingDexOptionKind.EXPLORE,
            ),
            focus_kind=LivingDexOptionKind.TRADE,
            assigned_candidate_index=0,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("minimum_settled_train_examples", 49),
        ("prospective_train_contexts", 60),
        ("prospective_development_contexts", 98),
        ("minimum_complete_development_pairs", 101),
        ("minimum_development_contexts_per_focus_kind", 14),
        ("minimum_train_feature_rank", 15),
        ("minimum_train_feature_rank", 17),
    ),
)
def test_design_rejects_mutations_that_recreate_an_underpowered_gate(
    field: str,
    value: int,
) -> None:
    with pytest.raises(LivingDexCausalCurriculumError):
        replace(LivingDexCausalCurriculumDesign(), **{field: value})
