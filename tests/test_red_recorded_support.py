import base64
import copy
import hashlib
import json

import pytest
from test_red_player_checkpoint import _complete, case  # noqa: F401

from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_checkpoint import (
    RedPlayerCheckpointError,
    capture_red_player_terminal,
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
)
from pokemon_red_completion.red_recorded_support import (
    SUPPORT_HEADER_SCHEMA,
    RedRecordedSupportError,
    RedRecordedSupportResult,
    support_costs,
)


def _segment(parent, state, count, delta):
    trace = []
    for i in range(count):
        trace.extend([
            {"intent": {"kind": "move", "value": "left"}, "frame_before": i * delta},
            {"after": i + 1, "frame": (i + 1) * delta},
        ])
    return {
        "plan": {
            "parent_state_sha256": parent, "diagnostic_only": True, "fit_admission": False,
            "source_commit": "e" * 40, "maximum_actions": 9, "maximum_frames": 900,
        },
        "state_base64": base64.urlsafe_b64encode(state).decode(),
        "audit": {
            "state_sha256": hashlib.sha256(state).hexdigest(), "audit_actions": 0,
            "audit_frames": 0, "actions": count, "frames": count * delta,
        },
        "result": None,  # Preserve an incomplete original report, never invent success.
        "trace": trace,
    }


@pytest.mark.parametrize("fault", [None, "gap", "frame", "count", "truncated", "state",
                                   "audit_input", "fit", "budget", "cost"])
def test_support_chain_preserves_unequal_costs_and_incomplete_reporting(fault):
    a = _segment("a" * 64, b"first", 3, 17)
    b = _segment(a["audit"]["state_sha256"], b"second", 2, 29)
    if fault == "gap":
        b["plan"]["parent_state_sha256"] = "b" * 64
    elif fault == "frame":
        b["trace"][2]["frame_before"] += 1
    elif fault == "count":
        b["trace"][1]["after"] = 2
    elif fault == "truncated":
        b["trace"].pop()
    elif fault == "state":
        b["state_base64"] = base64.urlsafe_b64encode(b"changed").decode()
    elif fault == "audit_input":
        b["audit"]["audit_frames"] = 1
    elif fault == "fit":
        b["plan"]["fit_admission"] = True
    elif fault == "budget":
        b["plan"]["maximum_actions"] = 1
    elif fault == "cost":
        b["audit"]["actions"] = 3
    if fault:
        with pytest.raises(RedRecordedSupportError):
            support_costs([a, b], "a" * 64)
    else:
        assert support_costs([a, b], "a" * 64) == (5, 109, hashlib.sha256(b"second").hexdigest())


class _ZeroMeter:
    def checkpoint(self):
        return CompositionBudgetCheckpoint(0, 0)


@pytest.mark.parametrize("fault", [None, "labels", "cost", "scope", "split", "memory",
                                   "anchor", "state", "observer", "input"])
def test_real_private_support_checkpoint_joins_native_parent_without_model_steps(
    case, fault,  # noqa: F811
):
    store, arguments, observation = case
    parent = capture_red_player_terminal(**arguments)
    split = {"partition": "train", "root_lineage_id": "original-root"}
    _complete(store, parent, alter_header={"split": split})
    summary = publish_red_player_checkpoint(store, parent)
    # Use the writer's canonical read order, exactly as the checkpoint opener does.
    parent = list(store.open_episode(arguments["episode_id"]).iter_stream("checkpoint"))[0]
    capture = parse_goal_manager_context_capture(
        base64.urlsafe_b64decode(parent["state_base64"]), json.dumps(parent["envelope"]).encode(),
    )
    segment = _segment(capture.state_sha256, b"transport-terminal", 3, 24)
    segment["plan"].update({
        "parent_episode": arguments["episode_id"],
        "parent_checkpoint_sha256": summary["record_sha256"],
    })
    result = RedRecordedSupportResult(
        arguments["episode_id"], summary["record_sha256"],
        summary["trajectory_manifest_sha256"], canonical_sha256([segment]), 3, 72,
    )
    emulator = arguments["emulator"]
    emulator.state, emulator.frame_count = b"transport-terminal", (1 if fault == "input" else 0)
    kwargs = {**arguments, "parent": capture, "episode_id": "support-import",
              "meter": _ZeroMeter(), "result": result}
    if fault == "input":
        with pytest.raises(RedPlayerCheckpointError, match="must not execute"):
            capture_red_player_terminal(**kwargs)
        return
    document = capture_red_player_terminal(**kwargs)
    metadata = {"schema": SUPPORT_HEADER_SCHEMA, "training_eligible": False, "split": split}
    if fault == "cost":
        document["terminal_result"]["historical_support_actions"] = 4
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif fault == "scope":
        document["profile_sha256"] = "c" * 64
    elif fault == "split":
        metadata["split"] = {**split, "partition": "development"}
    elif fault == "memory":
        document["search_memory"] = {"fake": "memory"}
    elif fault == "anchor":
        segment["plan"]["parent_checkpoint_sha256"] = "d" * 64
    elif fault == "state":
        document["state_sha256"] = "a" * 64
    elif fault == "observer":
        metadata["trainer_funding"] = True
    writer = _complete(store, document, alter_header=metadata, complete=False)
    writer.append("recorded_support", copy.deepcopy(segment))
    if fault == "labels":
        writer.append("decisions", {"invented": True})
    writer.complete()
    if fault:
        with pytest.raises(RedRecordedSupportError):
            publish_red_player_checkpoint(store, document)
        return
    published = publish_red_player_checkpoint(store, document)
    opened = open_red_player_checkpoint(
        store, episode_id="support-import", expected_record_sha256=published["record_sha256"],
        original_parent=capture, expected_profile_sha256=arguments["profile_sha256"],
        expected_rom_sha256=arguments["rom_sha256"], expected_context_origin="training",
    )
    assert opened.capture.state_bytes == b"transport-terminal"
    assert opened.capture.envelope.verified_objective_ids == capture.envelope.verified_objective_ids
    assert document["terminal_result"]["steps"] == []
    assert document["terminal_result"]["total_actions"] == 0
    assert document["terminal_result"]["historical_support_actions"] == 3
