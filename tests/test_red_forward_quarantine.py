"""Real aborted artifacts stay diagnostic, even with settled forward returns."""

import base64
import hashlib
from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_forward_dataset import episode, rebuild_forward
from test_red_living_dex_causal_adapter import _store_and_registry

from pokemon_red_completion.forward_goal import ForwardGoalOutcome
from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.red_forward_dataset import load_red_forward_episode
from pokemon_red_completion.red_forward_quarantine import audit_failed_red_forward_episode
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode

ROM_SHA = "a" * 64
STATE_BYTES = b"synthetic failed save, never loaded in an emulator"
STATE_SHA = hashlib.sha256(STATE_BYTES).hexdigest()


def failed_episode(tmp_path, *, terminal="failure", mutate=None, episode_id="goal-episode-1"):
    (tmp_path / "source").mkdir()
    (tmp_path / "failed").mkdir()
    original = episode(tmp_path / "source", terminal=terminal, episode_id=episode_id)
    reader = original.store.open_episode(episode_id)
    streams = {name: list(reader.iter_stream(name)) for name in reader.stream_names}
    streams["episode"][0]["metadata"].update(rom_sha256=ROM_SHA, context_origin="training")
    counters = original.observed.counters
    streams["failure_state"] = [
        {
            "schema": "pokemon.red.private-failure-state.v1",
            "state_base64": base64.urlsafe_b64encode(STATE_BYTES).decode(),
            "state_sha256": STATE_SHA,
            "held_buttons": [],
            "safe_checkpoint": False,
            "admitted_continuation": False,
            "training_target": False,
            "actions": counters.actions,
            "frames": counters.frames,
        }
    ]
    streams["events"][-1]["payload"] = {"status": "failed", "reason": "unsafe_checkpoint"}
    if mutate is not None:
        mutate(streams, original)
    store, _ = _store_and_registry(tmp_path / "failed")
    store.publish_sealed_record(
        f"rp-plan-{original.training.plan_sha256}",
        kind="red_player_training_plan",
        record=dict(original.training.document),
    )
    writer = store.begin_episode(episode_id)
    for name, rows in streams.items():
        for row in rows:
            writer.append(name, row)
    artifact = writer.abort("terminal_checkpoint_unsafe_boundary")
    original.store = store
    original.manifest = artifact.manifest_sha256
    return original


def audit(item, **changes):
    return audit_failed_red_forward_episode(
        item.store,
        **{
            "episode_id": "goal-episode-1",
            "expected_manifest_sha256": item.manifest,
            "expected_failure_state_sha256": STATE_SHA,
            "expected_rom_sha256": ROM_SHA,
            "training_plan": item.training,
            "behavior_model": item.model,
            "forward_plan": item.forward,
            "objective_id": "defeat_champion",
            **changes,
        },
    )


def test_real_failed_artifact_preserves_known_zero_without_fitting_authority(tmp_path):
    item = failed_episode(tmp_path)
    result = audit(item)
    assert not isinstance(result, ForwardGoalOutcome)
    assert not hasattr(result, "target") and not hasattr(result, "outcome")
    assert result.terminal == "stopped" and result.observed_goal is False
    assert result.recorded_return == pytest.approx((0, 0.16675555555555555))
    assert (result.actions, result.frames, result.macros, result.resources) == (2, 120, 2, 1)
    assert (result.sampled_training_rows, result.excluded_nonexploratory_steps) == (1, 1)
    report = result.public_dict()
    assert report["admission"] == "quarantined-not-for-fitting"
    for flag in (
        "fitting_authorized",
        "checkpoint_authorized",
        "retry_authorized",
        "in_game_loss_inferred",
    ):
        assert report[flag] is False
    assert item.store.open_failed_episode("goal-episode-1").summary.status == "failed"
    with pytest.raises(PrivateArtifactError):
        load_red_player_training_episode(
            item.store,
            episode_id="goal-episode-1",
            expected_manifest_sha256=item.manifest,
            plan=item.training,
            behavior_model=item.model,
        )
    with pytest.raises(PrivateArtifactError):
        load_red_forward_episode(
            item.store,
            episode_id="goal-episode-1",
            expected_manifest_sha256=item.manifest,
            training_plan=item.training,
            behavior_model=item.model,
            forward_plan=item.forward,
            objective_id="defeat_champion",
        )


@pytest.mark.parametrize(
    "terminal,observed,expected",
    [
        ("success", True, 1.0),
        ("interrupted", None, None),
    ],
)
def test_later_checkpoint_failure_does_not_rewrite_recorded_knowledge(
    tmp_path, terminal, observed, expected
):
    result = audit(failed_episode(tmp_path, terminal=terminal))
    assert result.observed_goal is observed
    if expected is None:
        assert result.recorded_return is None
        assert result.terminal == "interrupted"
        assert result.prefix_cost > 0 and result.actions == 1
    else:
        assert result.recorded_return[0] == expected
        assert result.terminal == "reached"


@pytest.mark.parametrize(
    "field,value",
    [
        ("actions", 3),
        ("frames", 121),
        ("actions", True),
        ("frames", False),
        ("held_buttons", ["a"]),
        ("safe_checkpoint", True),
        ("admitted_continuation", True),
        ("training_target", True),
        ("safe_checkpoint", 0),
        ("admitted_continuation", 0),
        ("training_target", 0),
        ("state_sha256", "f" * 64),
        ("state_base64", "malformed!!!"),
        ("state_base64", base64.urlsafe_b64encode(b"different save").decode()),
        pytest.param("state_base64", "a" * 699053, id="oversized-encoding"),
    ],
)
def test_failure_capture_tampering_rejected_after_real_manifest_authentication(
    tmp_path, field, value
):
    item = failed_episode(
        tmp_path, mutate=lambda s, _: s["failure_state"][-1].update({field: value})
    )
    with pytest.raises(ValueError):
        audit(item)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s, _: s["forward_goal"].pop(),
        lambda s, _: s["executions"].append(deepcopy(s["executions"][-1])),
        lambda s, _: s["forward_goal"][-1].update(red_evidence=None),
        lambda s, _: s["episode"][0]["metadata"].update(source_bundle_sha256="f" * 64),
        lambda s, _: s["episode"][0]["metadata"].update(trainer_funding=True),
        lambda s, _: s["failure_state"].clear(),
        lambda s, _: s["episode"][0]["metadata"].update(rom_sha256="f" * 64),
        lambda s, _: s["episode"][0]["metadata"].update(context_origin="development"),
    ],
)
def test_missing_or_mismatched_recorded_evidence_never_produces_a_return(tmp_path, mutation):
    item = failed_episode(tmp_path, mutate=mutation)
    with pytest.raises((ValueError, PrivateArtifactError)):
        audit(item)


@pytest.mark.parametrize(
    "change",
    [
        lambda c: replace(c, probabilities=tuple(reversed(c.probabilities))),
        lambda c: replace(c, decision_sha256="f" * 64),
        lambda c: replace(c, context=tuple(0.5 for _ in c.context)),
    ],
)
def test_internally_valid_forward_anchor_cannot_override_actual_sample(tmp_path, change):
    item = failed_episode(
        tmp_path,
        mutate=lambda s, original: rebuild_forward(
            s,
            original.forward,
            change_choice=change,
        ),
    )
    with pytest.raises(ValueError):
        audit(item)


def test_consistent_generic_cost_record_must_match_actual_prefix(tmp_path):
    item = failed_episode(
        tmp_path,
        mutate=lambda s, original: rebuild_forward(
            s,
            original.forward,
            change_counters=lambda _, c: replace(c, frames=c.frames + 1),
        ),
    )
    with pytest.raises(ValueError, match="frames"):
        audit(item)


def test_wrong_expected_identities_reject(tmp_path):
    item = failed_episode(tmp_path)
    for key in ("expected_manifest_sha256", "expected_failure_state_sha256", "expected_rom_sha256"):
        with pytest.raises(ValueError):
            audit(item, **{key: "f" * 64})
