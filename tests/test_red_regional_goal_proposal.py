import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_red_player_training import _episode
from test_red_regional_acquisition import _candidate

from pokemon_red_completion.red_goal_context_profile import (
    _thaw,
    build_red_goal_context_profile_payload,
)
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_regional_goal_proposal import (
    REGIONAL_PROPOSAL_KIND,
    REGIONAL_PROPOSAL_SCHEMA,
    load_regional_proposal_profile,
    regional_proposal_record_id,
    regional_proposal_seed,
    regional_proposal_source_effort,
)


def recorded(
    tmp_path,
    *,
    kind="resupply",
    omit_header=False,
    selected_source="wild:Route11:grass",
    source_mode="sampled",
):
    profile = _candidate("wild:Route11:grass").profile

    def declare(store, plan, _model):
        record = store.publish_sealed_record(
            regional_proposal_record_id("goal-episode-1"),
            kind=REGIONAL_PROPOSAL_KIND,
            record={
                "schema": REGIONAL_PROPOSAL_SCHEMA,
                "episode_id": "goal-episode-1",
                "source_proposal_fitted": False,
                "controller_input_before_commit": False,
                "parent_overridden": False,
                "independent_evaluation": False,
                "profile_sha256": plan.document["profile_sha256"],
                "parent_plan": dict(plan.document),
                "selected_source": selected_source,
                "source_mode": source_mode,
                "profile": json.loads(
                    build_red_goal_context_profile_payload(
                        profile_id=profile.profile_id,
                        providers=tuple(
                            (spec.kind, spec.mechanic, _thaw(spec.parameters))
                            for spec in profile.providers
                        ),
                    )
                ),
            },
        )
        return (
            {} if omit_header else {"regional_proposal_record_sha256": record.summary.record_sha256}
        )

    store, plan, model, completed = _episode(
        tmp_path,
        before_episode=declare,
        return_inputs=True,
        plan_profile_sha=profile.profile_sha256,
    )
    terminal = store.publish_sealed_record(
        checkpoint_record_id("goal-episode-1"),
        kind=CHECKPOINT_KIND,
        record={
            "trajectory_manifest_sha256": completed.manifest_sha256,
            "profile_sha256": plan.document["profile_sha256"],
            "terminal_result": {
                "steps": [
                    {
                        "status": "failed",
                        "selected_kind": kind,
                        "failure_reason": "search_exhausted",
                        "actions_executed": 7,
                        "frames_executed": 420,
                        "collection_before": {"required_specimens_sha256": "f" * 64},
                    }
                ]
            },
        },
    )
    return store, terminal, plan, model, completed


def test_supply_parent_adds_native_row_but_no_capture_attempt_or_extra_row(tmp_path):
    store, terminal, plan, model, completed = recorded(tmp_path)
    assert (
        regional_proposal_source_effort(store, "goal-episode-1", terminal.summary.record_sha256)
        is None
    )
    dataset = load_red_player_training_episode(
        store,
        episode_id="goal-episode-1",
        expected_manifest_sha256=completed.manifest_sha256,
        plan=plan,
        behavior_model=model,
    )
    assert len(dataset.examples) == 1


def test_exact_sealed_proposal_profile_can_be_restored(tmp_path):
    store, _terminal, plan, *_ = recorded(tmp_path)
    proposal = store.find_sealed_record(
        regional_proposal_record_id("goal-episode-1"),
        expected_kind=REGIONAL_PROPOSAL_KIND,
    )
    profile = load_regional_proposal_profile(
        store,
        "goal-episode-1",
        proposal.summary.record_sha256,
        expected_parent_plan=plan.document,
    )
    assert profile.profile_sha256 == plan.document["profile_sha256"]
    with pytest.raises(ValueError, match="absent or changed"):
        load_regional_proposal_profile(
            store,
            "goal-episode-1",
            "0" * 64,
            expected_parent_plan=plan.document,
        )


def test_actual_capture_parent_preserves_failed_source_effort(tmp_path):
    store, terminal, *_ = recorded(tmp_path, kind="acquire_species")
    assert regional_proposal_source_effort(
        store, "goal-episode-1", terminal.summary.record_sha256
    ) == ("wild:Route11:grass", "f" * 64, True, 7, 420)


def test_native_nonencounter_acquisition_has_no_capture_source_effort(tmp_path):
    store, terminal, *_ = recorded(
        tmp_path,
        kind="acquire_species",
        selected_source=None,
        source_mode="no_source",
    )
    assert (
        regional_proposal_source_effort(
            store,
            "goal-episode-1",
            terminal.summary.record_sha256,
        )
        is None
    )


def test_uncommitted_proposal_cannot_become_source_memory(tmp_path):
    store, terminal, *_ = recorded(tmp_path, omit_header=True)
    with pytest.raises(ValueError, match="terminal/header binding"):
        regional_proposal_source_effort(store, "goal-episode-1", terminal.summary.record_sha256)


@pytest.mark.parametrize(
    "field,value",
    [
        ("trajectory_manifest_sha256", "a" * 64),
        ("profile_sha256", "b" * 64),
        ("terminal_result", {"steps": []}),
    ],
)
def test_changed_terminal_cannot_supply_plausible_memory(tmp_path, field, value):
    store, terminal, *_ = recorded(tmp_path, kind="acquire_species")
    document = deepcopy(terminal.read())
    document[field] = value

    def find(identifier, **kwargs):
        if kwargs.get("expected_kind") == CHECKPOINT_KIND:
            return SimpleNamespace(summary=terminal.summary, read=lambda: document)
        return store.find_sealed_record(identifier, **kwargs)

    proxy = SimpleNamespace(find_sealed_record=find, open_episode=store.open_episode)
    with pytest.raises(ValueError):
        regional_proposal_source_effort(proxy, "goal-episode-1", terminal.summary.record_sha256)


def test_goal_and_source_proposal_random_streams_are_distinct_and_reproducible():
    assert regional_proposal_seed(17) == regional_proposal_seed(17)
    assert regional_proposal_seed(17) not in {17, regional_proposal_seed(18)}
    for bad in (True, -1, 2.5):
        with pytest.raises(ValueError):
            regional_proposal_seed(bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("selected_source", "wild:Route24:grass"),
        ("source_proposal_fitted", True),
        ("parent_plan", {}),
        ("controller_input_before_commit", True),
    ],
)
def test_inconsistent_proposal_cannot_invent_source_effort(tmp_path, field, value):
    store, terminal, *_ = recorded(tmp_path, kind="acquire_species")
    original = store.find_sealed_record(
        regional_proposal_record_id("goal-episode-1"), expected_kind=REGIONAL_PROPOSAL_KIND
    )
    doc = deepcopy(original.read())
    doc[field] = value

    def find(identifier, **kwargs):
        if kwargs.get("expected_kind") == REGIONAL_PROPOSAL_KIND:
            return SimpleNamespace(summary=original.summary, read=lambda: doc)
        return store.find_sealed_record(identifier, **kwargs)

    with pytest.raises(ValueError):
        regional_proposal_source_effort(
            SimpleNamespace(find_sealed_record=find, open_episode=store.open_episode),
            "goal-episode-1",
            terminal.summary.record_sha256,
        )
