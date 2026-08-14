from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fit_goal_manager import GoalManagerFitError, _validation_gate  # noqa: E402

from pokemon_red_completion.goal_manager_model import (  # noqa: E402
    goal_manager_fit_configuration,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    goal_manager_contract_document,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _metrics() -> dict[str, object]:
    return {
        "accuracy": 0.80,
        "baselines": {
            "fixed_priority": {
                "accuracy": 0.30,
                "paired_comparison": {"wins": 15, "losses": 1, "two_sided_exact_p": 0.001},
            },
            "highest_pressure": {
                "accuracy": 0.75,
                "paired_comparison": {"wins": 3, "losses": 1, "two_sided_exact_p": 0.625},
            },
            "lowest_effort": {
                "accuracy": 0.20,
                "paired_comparison": {"wins": 17, "losses": 1, "two_sided_exact_p": 0.0001},
            },
        },
        "selected_kind_accuracy": {kind: 0.75 for kind in ("story", "collect", "heal")},
    }


def test_validation_gate_requires_baseline_and_per_kind_evidence() -> None:
    assert _validation_gate(_metrics())["passed"] is True

    weak = _metrics()
    weak["selected_kind_accuracy"] = {"story": 0.49}
    assert _validation_gate(weak)["passed"] is False

    with pytest.raises(GoalManagerFitError, match="baseline is absent"):
        _validation_gate({"accuracy": 1.0, "baselines": {}, "selected_kind_accuracy": {}})


def test_fit_script_help_exposes_only_private_root_and_output_contract() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/fit_goal_manager.py", "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--private-root" in result.stdout
    assert "--out-model" in result.stdout
    assert "--out-summary" in result.stdout
    assert "--epochs" not in result.stdout
    assert "--learning-rate" not in result.stdout
    assert "--l2" not in result.stdout
    assert "ROM" not in result.stdout


def test_counted_fit_configuration_is_fixed_in_the_source_bound_contract() -> None:
    configuration = goal_manager_fit_configuration()

    assert configuration == goal_manager_contract_document()["fit"]
    assert configuration["selection"] == "fixed_before_context_collection"
