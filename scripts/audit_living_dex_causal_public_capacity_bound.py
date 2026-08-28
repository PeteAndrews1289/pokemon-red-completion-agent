#!/usr/bin/env python3
"""Reproduce the public upper bound on remaining Red causal root capacity.

Only checked-in, path-free receipts are read.  The result is an upper bound,
not a claim that every remaining root satisfies the new menu, pressure,
family, location, lineage, or feature requirements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = PROJECT_ROOT / "configs/living-dex-causal-curriculum-v1.json"
PROVIDER_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-provider-plan-freeze-result-v1-2026-08-26.json"
)
FREEZE_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-causal-campaign-freeze-result-v1-2026-08-27.json"
)
TERMINAL_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-causal-campaign-terminal-v1-2026-08-27.json"
)
OUTPUT_PATH = (
    PROJECT_ROOT / "docs/evidence/living-dex-causal-public-capacity-bound-v1-2026-08-27.json"
)


def _load(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError("public capacity source document differs")
    return document, hashlib.sha256(payload).hexdigest()


def build_public_capacity_bound() -> dict[str, object]:
    design, design_file_sha256 = _load(DESIGN_PATH)
    provider, provider_sha256 = _load(PROVIDER_PATH)
    freeze, freeze_sha256 = _load(FREEZE_PATH)
    terminal, terminal_sha256 = _load(TERMINAL_PATH)
    training = design.get("training")
    evaluation = design.get("evaluation")
    freeze_receipt = freeze.get("freeze_receipt")
    campaign = terminal.get("campaign_execution")
    counter_deltas = terminal.get("counter_deltas")
    if not all(
        isinstance(value, dict)
        for value in (training, evaluation, freeze_receipt, campaign, counter_deltas)
    ):
        raise ValueError("public capacity source schema differs")
    assert isinstance(training, dict)
    assert isinstance(evaluation, dict)
    assert isinstance(freeze_receipt, dict)
    assert isinstance(campaign, dict)
    assert isinstance(counter_deltas, dict)
    historical = provider.get("eligible_root_pool")
    retired = freeze_receipt.get("retired_root_exclusions")
    claimed = campaign.get("root_claims")
    train_required = training.get("prospective_contexts")
    development_required = (
        design.get("independence", {}).get("development_contexts")
        if isinstance(design.get("independence"), dict)
        else None
    )
    if (
        provider.get("schema") != "pokemon.red.living-dex-provider-plan-freeze-public-result.v1"
        or freeze.get("schema")
        != "pokemon.red.living-dex-causal-campaign-freeze-result-evidence.v1"
        or terminal.get("schema") != "pokemon.red.living-dex-causal-campaign-terminal-evidence.v1"
        or design.get("status") != "design_only_capacity_unproven"
        or not all(
            type(value) is int and value >= 0  # noqa: E721
            for value in (
                historical,
                retired,
                claimed,
                train_required,
                development_required,
            )
        )
        or freeze_receipt.get("selected_slots") != 1
        or counter_deltas.get("causal_train_examples") != 1
        or terminal.get("adjudication", {}).get("causal_train_example_admitted") is not True
    ):
        raise ValueError("public capacity source facts differ")
    assert isinstance(historical, int)
    assert isinstance(retired, int)
    assert isinstance(claimed, int)
    assert isinstance(train_required, int)
    assert isinstance(development_required, int)
    remaining_upper_bound = max(0, historical - retired - claimed)
    combined_required = train_required + development_required
    return {
        "authorization": {
            "crystal_execution": False,
            "model_fit": False,
            "private_context_access": False,
            "red_controller_execution": False,
            "root_generation": False,
            "sealed_red": False,
        },
        "capacity": {
            "combined_new_root_minimum": max(0, combined_required - remaining_upper_bound),
            "combined_required_contexts": combined_required,
            "development_required_contexts": development_required,
            "historical_eligible_root_pool": historical,
            "later_claimed_roots": claimed,
            "later_retired_root_exclusions": retired,
            "remaining_root_upper_bound": remaining_upper_bound,
            "train_new_root_minimum_if_all_remaining_qualify": max(
                0, train_required - remaining_upper_bound
            ),
            "train_required_contexts": train_required,
        },
        "counter_deltas": {
            "causal_train_examples": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "root_claims": 0,
            "teacher_queries": 0,
        },
        "design_sha256": design.get("design_sha256"),
        "interpretation": {
            "capacity_ready": False,
            "independence_rule": (
                "one_unique_physical_root_and_authenticated_prospective_harness_"
                "episode_lineage_per_context_clones_inherit_parent_lineage"
            ),
            "next_gate": ("action_free_exact_capacity_census_then_prospective_root_expansion"),
            "root_reuse_allowed": False,
            "stage_order": ("populate_and_collect_train_before_materializing_untouched_evaluation"),
            "upper_bound_caveat": (
                "actual_compatible_capacity_can_only_be_lower_after_menu_pressure_"
                "family_location_lineage_and_feature_checks"
            ),
        },
        "recorded_on": "2026-08-27",
        "schema": "pokemon.core.living-dex-causal-public-capacity-bound.v1",
        "source_receipts": {
            "causal_freeze": freeze_sha256,
            "causal_terminal": terminal_sha256,
            "curriculum_config": design_file_sha256,
            "provider_inventory": provider_sha256,
        },
        "status": "insufficient_public_upper_bound_requires_new_roots",
        "unsupported_claims": [
            "all_remaining_roots_are_compatible",
            "causal_curriculum_capacity_ready",
            "model_training_ready",
            "powered_red_benchmark_ready",
            "statistical_independence_already_proven",
        ],
    }


def canonical_bytes() -> bytes:
    return (
        json.dumps(
            build_public_capacity_bound(),
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = canonical_bytes()
    if args.check:
        if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_bytes() != payload:
            raise SystemExit("public causal capacity evidence is stale")
        print("public causal capacity evidence is current")
        return 0
    print(payload.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
