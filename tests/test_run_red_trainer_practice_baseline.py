import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_trainer_practice_baseline as baseline  # noqa: E402


def test_baseline_requires_exact_bound_bytes(tmp_path):
    path = tmp_path / "private-model.json"
    path.write_bytes(b"{}")
    binding = {"path": str(path), "sha256": hashlib.sha256(b"{}").hexdigest()}
    assert baseline._bound_file(binding, "model") == b"{}"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="model hash differs"):
        baseline._bound_file(binding, "model")


def test_baseline_rejects_wrong_plan_before_cartridge_access():
    with pytest.raises(ValueError, match="plan differs"):
        baseline._authenticate({"schema": "not-a-trainer-plan"})
