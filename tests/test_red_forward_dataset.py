"""Admit complete synthetic private episodes through the real native sampler reader."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_goal_manager_trajectory import _Reader
from test_red_elixir_plan import finished, state
from test_red_forward_goal import EXECUTION_FLAGS, champion_raw, observation
from test_red_forward_training import harness, opportunities, run_macro, sampled
from test_red_living_dex_causal_adapter import _store_and_registry
from test_red_player_training import _plan

from pokemon_red_completion.forward_goal import (
    ForwardGoalCounters,
    ForwardGoalPlan,
    ForwardGoalRecorder,
    ForwardGoalTerminal,
)
from pokemon_red_completion.forward_goal_records import restore_forward_goal_choice
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalSelectionMode
from pokemon_red_completion.red_forward_dataset import load_red_forward_episode
from pokemon_red_completion.red_forward_goal import (
    RedForwardGoalCollector,
    red_forward_continuation_sha256,
    red_forward_verifier_sha256,
)
from pokemon_red_completion.red_player_training import TRAINING_EVENT
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.trajectory import SparseEvent
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink


def episode(tmp_path, *, terminal="success", singleton=True, execution_flags=None):
    store, _ = _store_and_registry(tmp_path)
    h = harness(seed=1)
    training = RedPlayerTrainingPlan(
        {
            **_plan(h.policy.model).document,
            "seed": 1,
            "decision_limit": 2,
        }
    )
    forward = ForwardGoalPlan(
        "red-story-objective",
        red_forward_verifier_sha256("defeat_champion"),
        red_forward_continuation_sha256(
            **{
                key: training.document[key]
                for key in (
                    "behavior_policy_id",
                    "model_sha256",
                    "source_bundle_sha256",
                    "profile_sha256",
                )
            },
            execution_flags=execution_flags,
        ),
        training.maximum_actions * 2,
        training.maximum_frames * 2,
        2,
        2,
    )
    store.publish_sealed_record(
        f"rp-plan-{training.plan_sha256}",
        kind="red_player_training_plan",
        record=dict(training.document),
    )
    writer = store.begin_episode("goal-episode-1")
    sink = EpisodeTrajectorySink(writer, "goal-episode-1", "pokemon.red", durable_writes=True)
    metadata = _Reader([], []).read_header()["metadata"]
    metadata.update(
        {
            key: training.document[key]
            for key in (
                "source_commit",
                "source_bundle_sha256",
                "state_sha256",
                "envelope_sha256",
                "profile_sha256",
                "model_sha256",
            )
        }
    )
    metadata.update(
        player_training_plan=dict(training.document),
        player_training_plan_sha256=training.plan_sha256,
        teacher_queries=0,
        teacher_fallbacks=0,
        forward_goal_plan=forward.public_dict(),
        forward_goal_plan_sha256=forward.sha256,
        forward_story_objective="defeat_champion",
        forward_goal_authority="recording-only-existing-actor",
    )
    if execution_flags is not None:
        metadata.update(execution_flags)
    sink.write_episode_header(metadata=metadata)
    h.events.clear()

    def append_forward(event):
        writer.append("forward_goal", event, durable=True)
        h.events.append(event)

    collector = RedForwardGoalCollector(
        forward,
        "defeat_champion",
        lambda: h.holder[0],
        h.meter,
        append_forward,
    )
    h.collector = collector
    h.trajectory.forward = collector
    h.trajectory.sink = h.executor.sink = sink
    h.trajectory.training_plan_sha256 = training.plan_sha256
    h.trajectory.maximum_actions = training.maximum_actions
    h.trajectory.maximum_frames = training.maximum_frames

    def execute(_action):
        assert h.trajectory.pending_was_recorded
        assert [event["kind"] for event in h.events[:2]] == [
            "forward_goal_declaration",
            "forward_goal_anchor",
        ]
        h.meter.spend(1, 60)
        if h.queued:
            h.holder[0] = h.queued.pop(0)
        return SimpleNamespace(frames=60, buttons=())

    h.executor.delegate = SimpleNamespace(execute=execute)
    collector.prepare()
    first = sampled(h)
    if terminal == "interrupted":
        run_macro(h, first, status=GoalDecisionOutcome.INTERRUPTED)
    else:
        run_macro(h, first, after=observation(finished(state())))
        if singleton:
            question = h.trajectory.ordered_question(
                h.holder[0].situation, opportunities(singleton=True)
            )
            second = h.trajectory.record_selection(
                question,
                question.available_indices[0],
                selection_mode=GoalSelectionMode.FORCED_SINGLETON,
            )
        else:
            second = sampled(h)
        after = finished(champion_raw()) if terminal == "success" else finished(state())
        run_macro(
            h,
            second,
            after=observation(after),
            status=(
                GoalDecisionOutcome.SUCCEEDED
                if terminal == "success"
                else GoalDecisionOutcome.FAILED
            ),
        )
    collector.finish()
    sink.record_event(
        SparseEvent(
            "goal-episode-1:terminal",
            "goal-episode-1",
            h.executor.next_step_index,
            "terminal",
            {"status": "complete"},
        )
    )
    sink.finalize()
    artifact = writer.complete()
    return SimpleNamespace(
        store=store,
        training=training,
        forward=forward,
        model=h.policy.model,
        manifest=artifact.manifest_sha256,
        observed=collector.outcome,
    )


def load(item, *, store=None, **changes):
    return load_red_forward_episode(
        item.store if store is None else store,
        **{
            "episode_id": "goal-episode-1",
            "expected_manifest_sha256": item.manifest,
            "training_plan": item.training,
            "behavior_model": item.model,
            "forward_plan": item.forward,
            "objective_id": "defeat_champion",
            **changes,
        },
    )


def altered(item, mutation):
    """Mutate after real artifact authentication; parent semantic admission still runs."""
    reader = item.store.open_episode("goal-episode-1")
    streams = {name: list(reader.iter_stream(name)) for name in reader.stream_names}
    mutation(streams)

    def iter_stream(name, *, max_records=None):
        values = streams.get(name, [])
        if max_records is not None and len(values) > max_records:
            raise ValueError("synthetic stream exceeds requested record limit")
        return iter(deepcopy(values))

    proxy = SimpleNamespace(
        manifest_sha256=reader.manifest_sha256,
        stream_names=tuple(streams),
        read_header=lambda: deepcopy(streams["episode"][0]),
        iter_stream=iter_stream,
    )
    return SimpleNamespace(
        open_episode=lambda _: proxy,
        find_sealed_record=item.store.find_sealed_record,
    )


def test_native_sample_and_honest_singleton_admit_from_real_complete_episode(tmp_path):
    item = episode(tmp_path)
    immediate = load_red_player_training_episode(
        item.store,
        episode_id="goal-episode-1",
        expected_manifest_sha256=item.manifest,
        plan=item.training,
        behavior_model=item.model,
    )
    assert immediate.decisions == 2 and len(immediate.examples) == 1
    assert immediate.excluded_nonexploratory == 1
    actual = load(item)
    assert actual == item.observed
    assert actual.terminal is ForwardGoalTerminal.REACHED
    assert actual.counters.public_dict() == {
        "actions": 2,
        "frames": 120,
        "resources": 1,
        "macros": 2,
    }
    assert actual.target == pytest.approx((1.0, 0.16675555555555555))


def test_finite_failed_attempt_retains_whole_attempt_cost(tmp_path):
    item = episode(tmp_path, terminal="failure")
    outcome = load(item)
    assert outcome.terminal is ForwardGoalTerminal.STOPPED
    assert outcome.target == pytest.approx((0.0, 0.16675555555555555))


def test_interrupted_native_choice_admits_only_censored_prefix(tmp_path):
    item = episode(tmp_path, terminal="interrupted")
    outcome = load(item)
    assert outcome.terminal is ForwardGoalTerminal.INTERRUPTED
    assert outcome.target is None
    assert outcome.counters.public_dict() == {
        "actions": 1,
        "frames": 60,
        "resources": 0,
        "macros": 0,
    }


def rebuild_forward(streams, plan, *, change_choice=None, change_counters=None):
    """Keep generic records internally consistent while attacking Red evidence joins."""
    original, emitted = streams["forward_goal"], []
    recorder = ForwardGoalRecorder(plan, emitted.append)
    recorder.declare(initial_goal=False)
    anchored = restore_forward_goal_choice(original[1]["choice"])
    recorder.anchor(anchored if change_choice is None else change_choice(anchored))
    for index, event in enumerate(original[2:]):
        counters = ForwardGoalCounters(**event["counters"])
        if change_counters is not None:
            counters = change_counters(index, counters)
        recorder.observe(
            counters,
            goal=event["goal"],
            stop=event["outcome"] is not None,
            interrupted=event["outcome"] is not None
            and event["outcome"]["terminal"] == "interrupted",
        )
    for new, old in zip(emitted, original, strict=True):
        new["red_evidence"] = deepcopy(old["red_evidence"])
    streams["forward_goal"] = emitted


@pytest.mark.parametrize(
    "field",
    [
        "forward_goal_plan",
        "forward_goal_plan_sha256",
        "forward_story_objective",
        "forward_goal_authority",
    ],
)
def test_missing_prospective_header_cannot_convert_historical_rows(tmp_path, field):
    item = episode(tmp_path)
    store = altered(item, lambda rows: rows["episode"][0]["metadata"].pop(field))
    with pytest.raises(ValueError, match="prospective header"):
        load(item, store=store)


def test_missing_forward_stream_cannot_be_recreated_from_immediate_successes(tmp_path):
    item = episode(tmp_path)
    store = altered(item, lambda rows: rows.pop("forward_goal"))
    with pytest.raises(ValueError, match="prospective header"):
        load(item, store=store)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_actions", 12001),
        ("max_frames", 1200001),
        ("max_resources", 1),
        ("max_macros", 3),
        ("continuation_sha256", "e" * 64),
        ("verifier_sha256", "f" * 64),
    ],
)
def test_declared_continuation_and_limits_must_match_native_plan(tmp_path, field, value):
    item = episode(tmp_path)
    with pytest.raises(ValueError, match="scope|prospective header"):
        load(item, forward_plan=replace(item.forward, **{field: value}))


@pytest.mark.parametrize(
    "changes",
    [
        {"decision_sha256": "e" * 64},
        {"root_sha256": "f" * 64},
        {"selected_index": 1},
        {"probabilities": (0.25, 0.75)},
    ],
)
def test_self_consistent_forward_anchor_must_join_actual_native_sample(tmp_path, changes):
    item = episode(tmp_path)
    original_choice = item.observed.choice
    if "selected_index" in changes:
        changes = {"selected_index": 1 - original_choice.selected_index}
    store = altered(
        item,
        lambda rows: rebuild_forward(
            rows,
            item.forward,
            change_choice=lambda selected: replace(selected, **changes),
        ),
    )
    with pytest.raises(ValueError, match="anchor differs"):
        load(item, store=store)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda evidence: evidence.update(mode="overworld"),
        lambda evidence: evidence.update(
            current_facts=[f for f in evidence["current_facts"] if f != "league:champion_defeated"]
        ),
        lambda evidence: evidence.update(
            current_facts=[f for f in evidence["current_facts"] if f != "game:hall_of_fame"]
        ),
    ],
)
def test_success_label_requires_current_simultaneous_verifier_evidence(tmp_path, mutation):
    item = episode(tmp_path)
    store = altered(item, lambda rows: mutation(rows["forward_goal"][-1]["red_evidence"]))
    with pytest.raises(ValueError, match="current verifier"):
        load(item, store=store)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda evidence: evidence.update(undeclared=True),
        lambda evidence: evidence["context"].__setitem__(0, True),
        lambda evidence: evidence["context"].__setitem__(1, float("nan")),
        lambda evidence: evidence["consumables"].pop("82"),
        lambda evidence: evidence["consumables"].__setitem__("82", True),
        lambda evidence: evidence["consumables"].__setitem__("82", 100),
        lambda evidence: evidence.update(current_facts=["duplicate", "duplicate"]),
    ],
)
def test_current_red_evidence_is_strict(tmp_path, mutation):
    item = episode(tmp_path)
    store = altered(item, lambda rows: mutation(rows["forward_goal"][-1]["red_evidence"]))
    with pytest.raises(ValueError):
        load(item, store=store)


def test_zero_cost_rewrite_cannot_hide_owned_elixir_consumption(tmp_path):
    item = episode(tmp_path)
    store = altered(
        item,
        lambda rows: rebuild_forward(
            rows,
            item.forward,
            change_counters=lambda _, c: replace(c, resources=0),
        ),
    )
    with pytest.raises(ValueError, match="resource cost"):
        load(item, store=store)


def test_inventory_evidence_cannot_erase_consumption_without_changing_target(tmp_path):
    item = episode(tmp_path)

    def mutation(rows):
        for event in rows["forward_goal"][2:]:
            event["red_evidence"]["consumables"]["82"] = 1

    with pytest.raises(ValueError, match="resource cost"):
        load(item, store=altered(item, mutation))


@pytest.mark.parametrize(
    "change",
    [
        lambda _, c: replace(c, frames=c.frames + 1),
        lambda i, c: replace(c, actions=0, frames=0) if i == 0 else c,
        lambda i, c: replace(c, macros=1) if i == 1 else c,
        lambda i, c: replace(c, actions=1, frames=60) if i == 1 else c,
    ],
)
def test_generic_consistent_costs_must_match_actual_macro_trace(tmp_path, change):
    item = episode(tmp_path)
    store = altered(item, lambda rows: rebuild_forward(rows, item.forward, change_counters=change))
    with pytest.raises(ValueError, match="frames|macro|controller"):
        load(item, store=store)


def test_forced_continuation_frames_are_checked_even_without_second_training_row(tmp_path):
    item = episode(tmp_path)
    store = altered(item, lambda rows: rows["executions"][1].update(frames=61))
    with pytest.raises(ValueError, match="frames"):
        load(item, store=store)


def test_censored_prefix_cannot_claim_current_terminal_observation(tmp_path):
    item = episode(tmp_path, terminal="interrupted")
    store = altered(
        item,
        lambda rows: rows["forward_goal"][-1].update(
            red_evidence=deepcopy(rows["forward_goal"][0]["red_evidence"]),
        ),
    )
    with pytest.raises(ValueError, match="censored"):
        load(item, store=store)


def test_sampler_admission_is_not_bypassed_by_forward_success(tmp_path):
    item = episode(tmp_path)

    def mutation(rows):
        event = next(event for event in rows["events"] if event["kind"] == TRAINING_EVENT)
        event["payload"]["example"]["behavior_probabilities"] = [0.25, 0.75]

    with pytest.raises(ValueError):
        load(item, store=altered(item, mutation))


def test_missing_native_declaration_or_wrong_manifest_blocks_forward_admission(tmp_path):
    item = episode(tmp_path)
    with pytest.raises(ValueError, match="episode identity"):
        load(item, expected_manifest_sha256="e" * 64)
    unsealed = SimpleNamespace(
        open_episode=item.store.open_episode,
        find_sealed_record=lambda *args, **kwargs: None,
    )
    with pytest.raises(ValueError, match="prospective player training declaration"):
        load(item, store=unsealed)


def test_later_verified_native_row_cannot_substitute_for_first_choice(tmp_path, monkeypatch):
    """Negative seam injection: real admission runs, then its first row is excluded."""
    import pokemon_red_completion.red_forward_dataset as dataset_module

    item = episode(tmp_path, singleton=False)
    native = load_red_player_training_episode(
        item.store,
        episode_id="goal-episode-1",
        expected_manifest_sha256=item.manifest,
        plan=item.training,
        behavior_model=item.model,
    )
    assert len(native.examples) == 2
    later = native.examples[1]
    store = altered(
        item,
        lambda rows: rebuild_forward(
            rows,
            item.forward,
            change_choice=lambda first: replace(
                first,
                candidates=tuple(
                    later.menu.candidate_vector(i, feature_version=3)
                    for i in range(len(later.menu.candidates))
                ),
                selected_index=later.selected_candidate_index,
                probabilities=later.behavior_probabilities,
            ),
        ),
    )
    verified_calls = []

    def verified_then_exclude(*args, **kwargs):
        verified = load_red_player_training_episode(*args, **kwargs)
        assert len(verified.examples) == 2
        verified_calls.append(True)
        return replace(verified, examples=verified.examples[1:], excluded_nonexploratory=1)

    monkeypatch.setattr(dataset_module, "load_red_player_training_episode", verified_then_exclude)
    with pytest.raises(ValueError, match="anchor differs"):
        load(item, store=store)
    assert verified_calls == [True]


@pytest.mark.parametrize("mutate_anchor", [False, True])
def test_initial_observation_and_anchor_resource_context_must_agree(tmp_path, mutate_anchor):
    item = episode(tmp_path)

    def mutation(rows):
        index = 1 if mutate_anchor else 0
        rows["forward_goal"][index]["red_evidence"]["context"][0] = 0.1

    with pytest.raises(ValueError, match="initial observation or anchor"):
        load(item, store=altered(item, mutation))


def test_initial_goal_cannot_already_be_present_in_recorded_current_evidence(tmp_path):
    item = episode(tmp_path)

    def mutation(rows):
        for event in rows["forward_goal"][:2]:
            evidence = event["red_evidence"]
            evidence["mode"] = "hall_of_fame"
            evidence["current_facts"] = sorted(
                {
                    *evidence["current_facts"],
                    "league:champion_defeated",
                    "game:hall_of_fame",
                }
            )

    with pytest.raises(ValueError, match="initial observation or anchor"):
        load(item, store=altered(item, mutation))


def test_explicit_all_false_header_is_compatible_with_absent_flags(tmp_path):
    item = episode(tmp_path, execution_flags={name: False for name in EXECUTION_FLAGS})
    assert load(item) == item.observed

    def omit_flags(rows):
        metadata = rows["episode"][0]["metadata"]
        for name in EXECUTION_FLAGS:
            metadata.pop(name)

    assert load(item, store=altered(item, omit_flags)) == item.observed


def test_declared_enabled_execution_flags_admit_from_authenticated_header(tmp_path):
    item = episode(tmp_path, execution_flags={name: True for name in EXECUTION_FLAGS})
    assert load(item) == item.observed


@pytest.mark.parametrize("name", EXECUTION_FLAGS)
def test_header_cannot_enable_unbound_execution_capability(tmp_path, name):
    item = episode(tmp_path)
    store = altered(item, lambda rows: rows["episode"][0]["metadata"].update({name: True}))
    with pytest.raises(ValueError, match="authenticated execution flags"):
        load(item, store=store)


@pytest.mark.parametrize("name", EXECUTION_FLAGS)
def test_header_cannot_disable_or_omit_a_bound_execution_capability(tmp_path, name):
    item = episode(tmp_path, execution_flags={key: True for key in EXECUTION_FLAGS})
    store = altered(item, lambda rows: rows["episode"][0]["metadata"].pop(name))
    with pytest.raises(ValueError, match="authenticated execution flags"):
        load(item, store=store)


@pytest.mark.parametrize("bad", [None, 0, 1, "false", [], {}])
def test_authenticated_header_execution_values_must_be_exact_booleans(tmp_path, bad):
    item = episode(tmp_path)
    store = altered(
        item,
        lambda rows: rows["episode"][0]["metadata"].update(
            trainer_funding=bad,
        ),
    )
    with pytest.raises(ValueError, match="execution flag trainer_funding must be a boolean"):
        load(item, store=store)


def test_native_authentication_still_precedes_execution_flag_interpretation(tmp_path):
    item = episode(tmp_path)
    malformed = altered(
        item,
        lambda rows: rows["episode"][0]["metadata"].update(
            routed_recovery="not a boolean",
        ),
    )
    unsealed = SimpleNamespace(
        open_episode=malformed.open_episode,
        find_sealed_record=lambda *args, **kwargs: None,
    )
    with pytest.raises(ValueError, match="prospective player training declaration"):
        load(item, store=unsealed)
