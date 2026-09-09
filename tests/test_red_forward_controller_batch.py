"""Whole-batch admission uses real complete and failed private artifact readers."""

from copy import deepcopy

import pytest
from test_red_forward_dataset import episode
from test_red_forward_quarantine import ROM_SHA, STATE_SHA, failed_episode
from test_red_living_dex_causal_adapter import _store_and_registry

from pokemon_red_completion.forward_goal import ForwardGoalTerminal
from pokemon_red_completion.red_forward_controller_batch import (
    CONTROLLER_BATCH_KIND,
    CONTROLLER_BATCH_SCHEMA,
    CONTROLLER_RETURN_CONTRACT,
    load_red_forward_controller_batch,
)
from pokemon_red_completion.red_forward_quarantine import load_failed_red_forward_controller_return


def batch(tmp_path, *, mutate=None, failed_terminal="failure"):
    for name in ("success", "failure", "combined"):
        (tmp_path / name).mkdir()
    good = episode(tmp_path / "success", episode_id="goal-episode-1")
    bad = failed_episode(
        tmp_path / "failure", episode_id="goal-episode-2", terminal=failed_terminal
    )
    store, _ = _store_and_registry(tmp_path / "combined")
    rows = []
    for item, episode_id, failed in (
        (good, "goal-episode-1", False),
        (bad, "goal-episode-2", True),
    ):
        reader = (
            item.store.open_failed_episode(episode_id)
            if failed
            else item.store.open_episode(episode_id)
        )
        writer = store.begin_episode(episode_id)
        for stream in reader.stream_names:
            for row in reader.iter_stream(stream):
                writer.append(stream, row)
        artifact = writer.abort("checkpoint_unsafe") if failed else writer.complete()
        store.publish_sealed_record(
            f"rp-plan-{item.training.plan_sha256}",
            kind="red_player_training_plan",
            record=dict(item.training.document),
        )
        row = {
            "episode_id": episode_id,
            "manifest_sha256": artifact.manifest_sha256,
            "status": "failed_stopped" if failed else "complete",
        }
        if failed:
            row.update(failure_state_sha256=STATE_SHA, rom_sha256=ROM_SHA)
        rows.append(row)
    doc = {
        "schema": CONTROLLER_BATCH_SCHEMA,
        "return_contract": CONTROLLER_RETURN_CONTRACT,
        "behavior_model_sha256": good.model.model_sha256,
        "forward_plan_sha256": good.forward.sha256,
        "declared_episode_ids": ["goal-episode-1", "goal-episode-2", "goal-episode-3"],
        "episodes": rows,
        "cancelled_episode_ids": ["goal-episode-3"],
        "independent_evaluation": False,
    }
    if mutate:
        mutate(doc)
    record = store.publish_sealed_record("controller-batch", kind=CONTROLLER_BATCH_KIND, record=doc)
    return store, good, bad, record.summary.record_sha256


def load(items, **changes):
    store, good, _, digest = items
    return load_red_forward_controller_batch(
        store,
        **{
            "batch_record_id": "controller-batch",
            "expected_batch_record_sha256": digest,
            "behavior_model": good.model,
            **changes,
        },
    )


def test_complete_and_controller_stopped_return_both_admit_without_omitting_failure(tmp_path):
    items = batch(tmp_path)
    actual = load(items)
    assert len(actual.outcomes) == 2 and actual.failed_stops == 1
    assert [row.target[0] for row in actual.outcomes] == [1, 0]
    assert actual.outcomes[1].terminal is ForwardGoalTerminal.STOPPED
    assert actual.cancelled_episode_ids == ("goal-episode-3",)
    assert actual.attempted_episode_ids == ("goal-episode-1", "goal-episode-2")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["episodes"].pop(),
        lambda d: d["episodes"].append(deepcopy(d["episodes"][0])),
        lambda d: d["cancelled_episode_ids"].append("goal-episode-2"),
        lambda d: d["cancelled_episode_ids"].clear(),
        lambda d: d["declared_episode_ids"].append("unaccounted-attempt"),
        lambda d: d.update(return_contract="ideal-player-wins"),
        lambda d: d.update(independent_evaluation=True),
        lambda d: d.update(behavior_model_sha256="f" * 64),
        lambda d: d.update(forward_plan_sha256="f" * 64),
        lambda d: d["episodes"][1].update(manifest_sha256="f" * 64),
        lambda d: d["episodes"][1].update(failure_state_sha256="f" * 64),
        lambda d: d["episodes"][1].update(status="censored_as_zero"),
        lambda d: d.update(row_subset=[0]),
    ],
)
def test_missing_selected_relabelled_or_tampered_batch_rejects(tmp_path, mutation):
    with pytest.raises((ValueError, RuntimeError)):
        load(batch(tmp_path, mutate=mutation))


@pytest.mark.parametrize("terminal", ["interrupted", "success"])
def test_failed_artifact_admission_is_only_for_known_stopped_goal(tmp_path, terminal):
    with pytest.raises(ValueError, match="known finite goal stop"):
        load(batch(tmp_path, failed_terminal=terminal))


def test_batch_pin_prevents_redeclaring_only_favorable_rows(tmp_path):
    items = batch(tmp_path)
    with pytest.raises(ValueError, match="batch declaration"):
        load(items, expected_batch_record_sha256="f" * 64)


@pytest.mark.parametrize("status", ["complete", "failed", "partial"])
def test_existing_third_attempt_cannot_be_hidden_in_cancelled_bucket(tmp_path, status):
    items = batch(tmp_path)
    store = items[0]
    writer = store.begin_episode("goal-episode-3")
    writer.append("executions", {"frames": 60, "status": "success"})
    if status == "complete":
        writer.complete()
    elif status == "failed":
        writer.abort("controller_stop")
    try:
        with pytest.raises(ValueError, match="cancels an existing episode"):
            load(items)
    finally:
        if status == "partial":
            writer.abort("test_cleanup")


def test_failed_return_needs_explicit_contract_and_does_not_open_for_generic_use(tmp_path):
    items = batch(tmp_path)
    store, _, bad, _ = items
    reader = store.open_failed_episode("goal-episode-2")
    with pytest.raises(ValueError, match="explicit controller contract"):
        load_failed_red_forward_controller_return(
            store,
            episode_id="goal-episode-2",
            expected_manifest_sha256=reader.manifest_sha256,
            expected_failure_state_sha256=STATE_SHA,
            expected_rom_sha256=ROM_SHA,
            training_plan=bad.training,
            behavior_model=bad.model,
            forward_plan=bad.forward,
            objective_id="defeat_champion",
            return_contract="",
        )
