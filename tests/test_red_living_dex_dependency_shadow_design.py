from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    adapt_red_living_dex_dependencies,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = PROJECT_ROOT / "configs/red-living-dex-dependency-shadow-decision-v1.json"
ADAPTER_PATH = PROJECT_ROOT / "src/pokemon_red_completion/red_living_dex_dependency_adapter.py"
ADAPTER_QUALIFICATION_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-dependency-observation-adapter-qualification-v1-2026-08-21.json"
)
COMPARISON_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-v2-comparison-result-2026-08-21.json"
)


def _document() -> dict[str, object]:
    value = json.loads(DESIGN_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True).encode(
            "ascii"
        )
        + b"\n"
    )


def _rankable_policy_rows() -> tuple[dict[str, int | str], ...]:
    specimens = (
        LivingSpecimen(red_species_ref(147), 30, CollectionLocation.BOX, slot_index=0),
        LivingSpecimen(red_species_ref(148), 30, CollectionLocation.BOX, slot_index=1),
    )
    observation = CollectionObservation(
        owned_species=frozenset(item.species_ref for item in specimens),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(2,),
        current_box_index=0,
        box_capacity=20,
    )
    result = adapt_red_living_dex_dependencies(
        observation,
        execution_facts=RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset({red_species_ref(147)})
        ),
    )
    opportunity = next(
        item
        for item in result.opportunities
        if item.binding.precursor_species_ref == red_species_ref(147)
        and item.binding.evolved_species_ref == red_species_ref(148)
    )
    assert opportunity.execution_qualified
    return opportunity.policy_rows()


def test_shadow_design_is_canonical_and_binds_exact_published_inputs() -> None:
    design = _document()
    bindings = design["binding_contract"]
    assert isinstance(bindings, dict)

    assert DESIGN_PATH.read_bytes() == _canonical_json(design)
    assert design["schema"] == "pokemon.red.living-dex-dependency-shadow-decision-design.v1"
    assert design["lane_id"] == "red-living-dex-dependency-shadow-decision-v1"
    assert bindings["adapter_sha256"] == _sha256(ADAPTER_PATH)
    assert bindings["adapter_qualification_receipt_sha256"] == _sha256(ADAPTER_QUALIFICATION_PATH)
    assert bindings["comparison_result_receipt_sha256"] == _sha256(COMPARISON_RESULT_PATH)
    assert bindings["model_sha256"] == (
        "a42db6420d3ff999a894c8ca54fbca7714509bbe95a2020cf85c9cee195f6582"
    )


def test_shadow_design_uses_exact_adapter_rows_and_pre_score_selection() -> None:
    design = _document()
    policy = design["policy_contract"]
    eligibility = design["eligibility_contract"]
    assert isinstance(policy, dict)
    assert isinstance(eligibility, dict)
    rows = _rankable_policy_rows()

    assert policy["candidate_count"] == 2
    assert policy["candidate_order"] == ["acquire_precursor", "transform_precursor"]
    assert policy["candidate_policy_keys"] == list(rows[0]) == list(rows[1])
    assert rows[0]["adds_precursor"] == 1
    assert rows[0]["consumes_precursor"] == 0
    assert rows[1]["adds_precursor"] == 0
    assert rows[1]["consumes_precursor"] == 1
    assert eligibility["first_catalog_order_eligible_opportunity_only"] is True
    assert eligibility["model_guided_context_or_opportunity_search"] is False
    assert eligibility["model_predictions_before_context_and_opportunity_freeze"] == 0
    assert eligibility["contexts_opened_maximum"] == 1
    assert eligibility["context_replacement_after_read"] is False


def test_shadow_design_hard_stops_after_one_prediction_and_zero_actions() -> None:
    design = _document()
    policy = design["policy_contract"]
    stages = design["stage_contract"]
    authority = design["authority_contract"]
    counters = design["counter_contract"]
    assert isinstance(policy, dict)
    assert isinstance(stages, dict)
    assert isinstance(authority, dict)
    assert isinstance(counters, dict)

    assert policy["maximum_model_predictions"] == 1
    assert policy["controller_actions_maximum"] == 0
    assert policy["emulator_frames_advanced_maximum"] == 0
    assert policy["teacher_queries"] == 0
    assert policy["teacher_fallbacks"] == 0
    assert policy["model_update_allowed"] is False
    assert stages["design_stage_private_accesses"] == 0
    assert stages["design_stage_predictions"] == 0
    assert stages["retry_same_execution_identity_after_prediction"] is False
    assert stages["terminal_required_on_every_post_prediction_path"] is True
    assert set(authority.values()) == {False}
    assert set(counters.values()) == {0}


def test_shadow_design_public_surface_contains_no_private_path_or_species_binding() -> None:
    design = _document()
    result = design["result_contract"]
    assert isinstance(result, dict)
    encoded = json.dumps(design, sort_keys=True)

    assert result["public_identity_fields"] == 0
    assert result["private_terminal_binds_context_and_opportunity"] is True
    assert "species_ref" not in encoded
    assert "source_id" not in encoded
    assert "item_ref" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
