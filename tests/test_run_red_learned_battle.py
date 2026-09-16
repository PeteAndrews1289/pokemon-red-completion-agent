import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_learned_battle as runner  # noqa: E402


def test_authentication_rejects_changed_source(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"original")
    reference = {"path": str(source), "sha256": hashlib.sha256(b"original").hexdigest()}
    assert runner._authenticated_bytes(reference) == b"original"
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash differs"):
        runner._authenticated_bytes(reference)


@pytest.mark.parametrize("dirty,revision", [(b"dirty", "expected"), (b"", "other")])
def test_runner_refuses_uncommitted_or_mismatched_code_before_inputs(
    tmp_path,
    monkeypatch,
    dirty,
    revision,
):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "pokemon.red.learned-encounter-plan.v1",
                "source_commit": "expected",
            }
        )
    )
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda args, **kw: dirty if args[1] == "status" else revision.encode(),
    )
    with pytest.raises(ValueError, match="implementation|commit differs"):
        runner.run(plan)
