"""The rejected Flash execution path cannot touch runtime or private inputs."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from pokemon_red_completion.red_collection_continuation import (
    ContinuationUnavailableError,
    run_collection_continuation_campaign,
)


@pytest.mark.parametrize("resume", [False, True])
def test_unqualified_coordinator_rejects_before_callbacks(tmp_path, resume):
    def forbidden(*args, **kwargs):
        pytest.fail("unqualified execution touched a callback")

    output = tmp_path / "never-created"
    with pytest.raises(ContinuationUnavailableError, match="not qualified"):
        run_collection_continuation_campaign(
            output=output,
            snapshot=forbidden,
            observe=forbidden,
            runtime=None,
            world=None,
            actions=None,
            model=None,
            plan={},
            provenance={},
            resume=resume,
        )
    assert not output.exists()


@pytest.mark.parametrize("resume", [False, True, "true"])
def test_cli_rejects_continuation_before_payload_loading(tmp_path, monkeypatch, resume):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"mode": "collection_continuation", "resume": resume}))
    script = Path(__file__).resolve().parents[1] / "scripts/run_red_autonomous_collection.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--plan", str(plan)])
    # Deliberately no ROM/model/checkpoint/output fields. Rejection must precede opening them.
    with pytest.raises(ValueError, match="not qualified"):
        runpy.run_path(str(script), run_name="__main__")
