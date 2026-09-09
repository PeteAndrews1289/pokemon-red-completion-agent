"""The registered scorer must not borrow historical learning credit."""

import hashlib
import json
from pathlib import Path

import pytest
from product_focus import ProductFocusError, _validate_registered_counter
from run_product_focus_dashboard import _training_projection

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "docs/evidence/red-registered-live-learning-2026-09-09.json"


def test_actual_registered_fit_has_separate_dashboard_identity():
    receipt = json.loads(RECEIPT.read_text())
    training, component = _training_projection(receipt)
    assert training.samples_before == 2
    assert training.samples_after == 3
    assert training.successful_examples == 1
    assert component.name == "Registered-Pokédex goal scorer"
    assert component.validation_examples == 0
    assert component.model_sha256 == receipt["fit"]["model"]["model_sha256"]


@pytest.mark.parametrize(
    "mutation", [None, "count", "schema", "objective", "rewards", "weights", "bytes"]
)
def test_registered_counter_checks_actual_receipt(tmp_path, mutation):
    receipt = json.loads(RECEIPT.read_text())
    progress = {"registered_train_examples": 3}
    if mutation == "count":
        progress["registered_train_examples"] = 114
    elif mutation == "schema":
        receipt["fit"]["model"]["schema"] = "pokemon.red.native-player-model.v1"
    elif mutation == "objective":
        receipt["fit"]["model"]["objective"] = "legacy"
    elif mutation == "rewards":
        receipt["fit"]["historical_rewards_reused"] = True
    elif mutation == "weights":
        receipt["fit"]["parameter_warm_start"] = True
    payload = json.dumps(receipt).encode()
    (tmp_path / "receipt.json").write_bytes(payload)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/dashboard-learning-evidence.json").write_text(
        json.dumps(
            {
                "path": "receipt.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    )
    if mutation == "bytes":
        (tmp_path / "receipt.json").write_bytes(payload + b" ")
    if mutation is None:
        _validate_registered_counter(progress, tmp_path)
    else:
        with pytest.raises(ProductFocusError, match="registered learning counter"):
            _validate_registered_counter(progress, tmp_path)


@pytest.mark.parametrize("key", ["historical_rewards_reused", "parameter_warm_start"])
def test_registered_dashboard_rejects_mixed_objective_claim(key):
    receipt = json.loads(RECEIPT.read_text())
    receipt["fit"][key] = True
    with pytest.raises(ValueError, match="registered objective boundary"):
        _training_projection(receipt)
