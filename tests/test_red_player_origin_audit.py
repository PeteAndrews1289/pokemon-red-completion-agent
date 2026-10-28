"""Read-only origin audit using the existing creation fixture, not real ROM data."""

import json
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_player_origins import Emulator, fixture

import pokemon_red_completion.red_player_origins as origins


class AuditEmulator(Emulator):
    state = b"0"

    def load_state_bytes(self, state):
        self.state = state

    def save_state_bytes(self):
        return self.state

    def tick(self, frames):
        pytest.fail("origin audit cannot advance a frame")


def setup(tmp_path, monkeypatch):
    root, args = fixture(tmp_path, monkeypatch)
    origins.capture_origin(root, "train-01", **args)
    monkeypatch.setattr(origins, "PyBoyAdapter", AuditEmulator)
    monkeypatch.setattr(origins, "PokemonRedStateReader", lambda em: NS(
        read=lambda: NS(party_count=1, battle_state=0),
        read_opening_control_state=lambda raw: NS(phase=origins.OpeningPhase.STARTER_OBTAINED),
    ))
    args.pop("repository")
    payload = (root / "train-01/result.json").read_bytes()
    args["expected_result_sha256"] = sha256(payload).hexdigest()
    return root, args


def test_creation_reopens_without_reallocation_or_training_eligibility(tmp_path, monkeypatch):
    root, args = setup(tmp_path, monkeypatch)
    original = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = origins.audit_origin(root, "train-01", **args)
    assert result["partition"] == "train" and result["audit_frames"] == 0
    assert not result["training_eligible"] and not result["reuse_authorized"]
    assert origins.audit_origin(root, "train-01", **args) == result
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == original
    assert all(
        em.frame_count == 0 for em in AuditEmulator.instances if isinstance(em, AuditEmulator)
    )


@pytest.mark.parametrize("fault", [
    "partition", "loads", "frames", "nan_seconds", "incomplete", "code", "hash",
    "terminal", "power", "extra_action", "missing_action", "changed_action", "claim",
])
def test_origin_audit_rejects_incomplete_or_changed_lineage(tmp_path, monkeypatch, fault):
    root, args = setup(tmp_path, monkeypatch)
    directory = root / "train-01"
    path = directory / "result.json"
    row = json.loads(path.read_bytes())
    if fault == "partition":
        row["partition"] = "development"
    elif fault == "loads":
        row["state_loads"] = 1
    elif fault == "frames":
        row["frames"] += 1
    elif fault == "nan_seconds":
        row["seconds"] = float("nan")
    elif fault == "incomplete":
        row["actions_completed"] -= 1
    elif fault == "code":
        row["source_bundle_sha256"] = "f" * 64
    elif fault == "terminal":
        (directory / "terminal.state").write_bytes(b"wrong")
    elif fault == "power":
        (directory / "power-on.state").write_bytes(b"wrong")
    elif fault == "extra_action":
        (directory / "action-0002-intent.json").write_text("{}")
    elif fault == "missing_action":
        (directory / "action-0001-result.json").unlink()
    elif fault == "changed_action":
        p = directory / "action-0000-result.json"
        changed = json.loads(p.read_bytes())
        changed["succeeded"] = False
        p.write_text(json.dumps(changed))
    elif fault == "claim":
        (directory / "claim.json").write_text("{}")
    path.write_text(json.dumps(row))
    args["expected_result_sha256"] = (
        "f" * 64 if fault == "hash" else sha256(path.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError):
        origins.audit_origin(root, "train-01", **args)


def test_native_state_and_partition_catalog_cannot_be_asserted_by_caller(tmp_path, monkeypatch):
    root, args = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="declaration"):
        origins.audit_origin(root, "train-01", tranche="comparison-05-06", **args)
    monkeypatch.setattr(origins, "PokemonRedStateReader", lambda em: NS(
        read=lambda: NS(party_count=2, battle_state=0),
        read_opening_control_state=lambda raw: NS(phase=origins.OpeningPhase.STARTER_OBTAINED),
    ))
    with pytest.raises(ValueError, match="native terminal"):
        origins.audit_origin(root, "train-01", **args)
