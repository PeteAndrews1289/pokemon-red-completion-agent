import io
import json
from types import SimpleNamespace

import pytest
from run_red_safari_pilot_episode import ActionRecorder

from pokemon_red_completion.actions import MacroAction, MacroActionKind


@pytest.mark.parametrize("fails", [False, True])
def test_action_recorder_retains_commitment_and_partial_failure_frames(fails):
    controller = SimpleNamespace(frame_count=0)
    stream = io.StringIO()

    def execute(action):
        controller.frame_count += 5
        if fails:
            raise RuntimeError("budget exhausted")
        return "done"

    recorder = ActionRecorder(SimpleNamespace(execute=execute), controller, stream, "b" * 64)
    action = MacroAction(MacroActionKind.CONFIRM)
    if fails:
        with pytest.raises(RuntimeError, match="budget"):
            recorder.execute(action)
    else:
        assert recorder.execute(action) == "done"
    row = json.loads(stream.getvalue())
    assert row["ordinal"] == recorder.count == 1
    assert row["before_frame"] == 0 and row["after_frame"] == 5
    assert row["selection_sha256"] == "b" * 64
    assert row["error"] == ("budget exhausted" if fails else None)
