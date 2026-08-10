from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from run_portable_clean_start import _emit, _model_identity, main  # noqa: E402

from pokemon_red_completion.provenance import canonical_sha256  # noqa: E402


class _DictModel:
    def to_dict(self) -> dict[str, object]:
        return {"model": "test", "weights": [1.0, -2.0]}


def test_portable_clean_start_cli_imports_and_exposes_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert "uncounted portable clean-start" in captured.out
    assert "--diagnostic-seed" in captured.out
    assert "--objective-model" in captured.out
    assert "--baseline-timing" in captured.out
    assert "--allow-model-disagreement" in captured.out
    assert "--battle-control-root" in captured.out


def test_portable_clean_start_cli_rejects_incomplete_control_collection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main([
            "--objective-model",
            "private-objective-model",
            "--diagnostic-seed",
            "990026",
            "--battle-control-root",
            "private-root",
        ])

    assert raised.value.code == 2
    assert "--battle-control-root requires --battle-model" in capsys.readouterr().err

    with pytest.raises(SystemExit) as raised:
        main([
            "--objective-model",
            "private-objective-model",
            "--battle-model",
            "private-battle-model",
            "--diagnostic-seed",
            "990026",
            "--battle-control-root",
            "private-root",
        ])

    assert raised.value.code == 2
    assert "requires --allow-model-disagreement" in capsys.readouterr().err


def test_model_identity_binds_raw_artifact_and_canonical_model(tmp_path: Path) -> None:
    artifact = tmp_path / "model.json"
    artifact.write_bytes(b"private model bytes\n")

    identity = _model_identity(artifact, _DictModel())

    assert identity == {
        "artifact_sha256": hashlib.sha256(b"private model bytes\n").hexdigest(),
        "model_sha256": canonical_sha256(_DictModel().to_dict()),
    }


def test_emit_preserves_failed_rehearsal_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "nested" / "failure.json"
    payload: dict[str, object] = {
        "promotion_eligible": False,
        "status": "failed_uncounted_rehearsal",
    }

    _emit(payload, destination)

    assert destination.read_text(encoding="ascii") == capsys.readouterr().out
    assert '"promotion_eligible": false' in destination.read_text(encoding="ascii")
