from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MACHINE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-powered-v2-capacity-machine-result-v1-2026-08-31.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-powered-v2-capacity-result-v1-2026-08-31.json"
)
MACHINE_SHA256 = "86f829cd84e6de2df4ad5754e226a87d6afcedb1bcf98bed1b6ac76902fb705c"
RESULT_SHA256 = "6509f735bb88f080c696d8591493d729c3d8d6bc83e7c5f254357ea408a8a013"


def test_powered_v2_capacity_evidence_matches_the_exact_action_free_census() -> None:
    machine_payload = MACHINE_PATH.read_bytes()
    result_payload = RESULT_PATH.read_bytes()
    machine = json.loads(machine_payload)
    result = json.loads(result_payload)
    design = LivingDexClusteredPoweredDesign()

    assert hashlib.sha256(machine_payload).hexdigest() == MACHINE_SHA256
    assert hashlib.sha256(result_payload).hexdigest() == RESULT_SHA256
    assert result["source"]["machine_result_sha256"] == MACHINE_SHA256
    assert machine["design_sha256"] == design.design_sha256
    assert result["source"]["design_sha256"] == design.design_sha256
    assert machine["status"] == (
        "authenticated_action_free_capacity_falsified_before_gameplay"
    )
    assert result["status"] == (
        "clustered_powered_v2_capacity_falsified_gameplay_closed"
    )


def test_powered_v2_capacity_shortfall_is_decisive_and_exact() -> None:
    machine = json.loads(MACHINE_PATH.read_text(encoding="ascii"))
    result = json.loads(RESULT_PATH.read_text(encoding="ascii"))

    assert machine["authenticated_contexts"] == 81
    assert machine["consumed_contexts"] == 29
    assert machine["eligible_root_pool"] == 43
    assert machine["lineages_observed"] == 43
    assert machine["lineages_with_any_scenario"] == 36
    assert machine["train_lineages_available"] == 14
    assert machine["train_lineage_deficit"] == 22
    assert machine["train_attempt_upper_bound"] == 28
    assert machine["development_lineages_available"] == 22
    assert machine["development_lineage_deficit"] == 78
    assert machine["contingency_lineage_upper_bound"] == 0
    assert machine["contingency_lineage_deficit"] == 3
    assert machine["total_lineage_deficit"] == 103
    assert machine["capacity_proven"] is False
    assert machine["allocation_witness_valid"] is False
    assert result["capacity_gate"]["hard_capacity_reasons"] == machine[
        "hard_capacity_reasons"
    ]
    assert result["interpretation"]["gameplay_collection_allowed_now"] is False


def test_powered_v2_capacity_census_preserved_every_protected_boundary() -> None:
    for path in (MACHINE_PATH, RESULT_PATH):
        payload = path.read_text(encoding="ascii")
        assert "/Users/" not in payload
        assert "/Volumes/" not in payload

    machine = json.loads(MACHINE_PATH.read_text(encoding="ascii"))
    result = json.loads(RESULT_PATH.read_text(encoding="ascii"))
    assert machine["private_identity_fields"] == 0
    assert machine["private_path_fields"] == 0
    assert result["protected_effects"]["collection_authorized"] is False
    assert all(
        value == 0
        for key, value in result["protected_effects"].items()
        if key != "collection_authorized"
    )
    for key in (
        "controller_actions",
        "emulator_frames",
        "model_fits",
        "model_predictions",
        "outcomes",
        "provider_executions",
        "red_gameplay_executions",
        "root_claims",
        "teacher_queries",
    ):
        assert machine[key] == 0
