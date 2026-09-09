"""Real probe-arm owner with synthetic observations and the spent-state harness."""

from dataclasses import replace
from inspect import getclosurevars
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _quote, _quoted_question, _supply_model
from test_red_forward_runner_wiring import (
    _spent_arm_failure_harness,
    champion_raw,
    forward_readiness,
    observation,
)
from test_red_player_training import _plan

from pokemon_red_completion.forward_first_choice_policy import FirstChoiceForwardTrainingPolicy
from pokemon_red_completion.forward_goal_learning import ForwardGoalModel
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from pokemon_red_completion.living_dex_option_value import (
    option_feature_names,
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.red_forward_goal import (
    RED_FORWARD_CONTEXT_NAMES,
    red_forward_execution_flags,
)
from pokemon_red_completion.red_forward_probe import RedForwardProbeSpec


def probe_wired(monkeypatch, *, stage="verifier", terminal_error=None, check_singleton=False):
    h = _spent_arm_failure_harness(monkeypatch, stage=stage)
    closure = getclosurevars(h.run).nonlocals
    old, run_arm = closure["readiness"], closure["run_arm"]
    ns = run_arm.__globals__
    tail = upgrade_option_value_model_for_optional_recovery(_supply_model())
    native = _plan(tail)
    values = dict(vars(old))
    values.update(
        legacy_model=None,
        causal_record=SimpleNamespace(model=tail),
        calibration_record=None,
        model_file_sha256="8" * 64,
        model_sha256=tail.model_sha256,
        output_path=Path("unused-output"),
        protected_paths=(),
        training_plan=native,
        decision_limit=2,
        profile=forward_readiness().profile,
        continuation=SimpleNamespace(search_memory=None),
        continuation_chain=(),
        continuation_root_lineage_id=native.document["root_lineage_id"],
    )
    ready = ns["_Readiness"](**values)
    fitted_plan = ns["_forward_goal_plan"](
        replace(
            ready,
            forward_story_objective="defeat_champion",
            forward_resource_budget=2,
        )
    )
    names = option_feature_names(3)
    width = (len(RED_FORWARD_CONTEXT_NAMES) + 5) * (len(names) + 1) - 1
    model = ForwardGoalModel(
        fitted_plan.contract,
        RED_FORWARD_CONTEXT_NAMES,
        names,
        (0.0,) * width,
        (1.0,) * width,
        ((0.0, 0.0),) * width,
        (0.5, 0.2),
        "a" * 64,
        4,
        0,
        1.0,
        10.0,
    )
    probe = RedForwardProbeSpec(
        model,
        fitted_plan,
        "b" * 64,
        tail.model_sha256,
        native.document["behavior_policy_id"],
        23,
        "defeat_champion",
        ready.profile.profile_sha256,
        ready.source_bundle_sha256,
        tuple(red_forward_execution_flags().items()),
    )
    ns["_require_forward_probe_scope"](ready, probe)  # Actual validation, not a stub.
    monkeypatch.setitem(ns, "_verify_continuation_restore", lambda *_: None)
    holder = [observation()]
    monkeypatch.setitem(
        ns,
        "build_red_goal_context_runtime",
        lambda **_: SimpleNamespace(
            adapter=SimpleNamespace(observe=lambda: holder[0]),
        ),
    )
    meter = ns["CompositionIndependentBudgetMeter"]()
    meter.checkpoint = lambda: CompositionBudgetCheckpoint(
        h.emulator.inputs, h.emulator.frame_count
    )
    writer = ready.private_root.begin_episode("unused")
    original_append = writer.append
    logs, headers, trajectories, calls, captures = [], [], [], [], []

    def append(stream, document, **kwargs):
        if stream == "forward_probe":
            assert kwargs == {"durable": True} and not h.emulator.closed
            if document.get("kind") == "forward_probe_terminal" and terminal_error is not None:
                raise terminal_error
            logs.append(document)
            h.order.append(document.get("role", document.get("kind")))
            return
        assert stream not in {"forward_goal", "player_training"}
        return original_append(stream, document, **kwargs)

    writer.append = append
    ns["EpisodeTrajectorySink"]().write_episode_header = lambda **kwargs: headers.append(
        kwargs["metadata"]
    )

    def trajectory(**kwargs):
        trajectories.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setitem(ns, "ViewerGoalTrajectory", trajectory)
    for name in ("RedPlayerTrainingTrajectory", "RedForwardTrainingTrajectory"):
        monkeypatch.setitem(
            ns, name, lambda **_: pytest.fail("probe must not use a fitting recorder")
        )
    original_player = ns["run_bounded_player_episode"]
    bindings = []
    for kind in (GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM):
        spec = next(s for s in ready.profile.providers if s.kind is kind)
        bindings.append(
            ExecutableGoalBinding(
                f"synthetic-direct:profile-{ready.profile.profile_sha256}:config-{spec.configuration_sha256}",
                kind,
                0.1,
                0.1,
                lambda: pytest.fail("no real macro"),
                lambda _: pytest.fail("no verifier"),
            )
        )
    menu = GoalBindingSet(tuple(b.opportunity for b in bindings), tuple(bindings))
    question = GoalManagerQuestion(_quoted_question(_quote()).situation, menu.opportunities)

    def player(**kwargs):
        calls.append(kwargs)
        actor = kwargs["authority"]
        assert isinstance(actor, FirstChoiceForwardTrainingPolicy)
        assert actor.forward_model is model and actor.tail_model is tail
        assert kwargs["completion_satisfied"](None) is False
        kwargs["validate_choice_menu"](SimpleNamespace(binding_set=menu))
        singleton = GoalBindingSet(
            (
                menu.opportunities[0],
                replace(
                    menu.opportunities[1],
                    availability=GoalAvailability.UNAVAILABLE,
                    estimated_effort=None,
                    estimated_risk=None,
                    unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE,
                ),
            ),
            (menu.bindings[0],),
        )
        if check_singleton:
            with pytest.raises(RuntimeError, match="forward_probe_initial_singleton"):
                kwargs["validate_choice_menu"](SimpleNamespace(binding_set=singleton))
            assert h.emulator.inputs == actor.forward_decisions == 0
        actor.select(question)
        assert h.emulator.inputs == 0 and logs[-1]["role"] == "forward_first"
        if check_singleton:
            kwargs["validate_choice_menu"](SimpleNamespace(binding_set=singleton))
            assert actor.forward_decisions == 1 and actor.tail_decisions == 0
        return original_player(**kwargs)

    monkeypatch.setitem(ns, "run_bounded_player_episode", player)
    original_capture = ns["capture_red_player_terminal"]

    def capture(**kwargs):
        captures.append(kwargs)
        assert kwargs["model_sha256"] == headers[0]["model_sha256"] == model.sha256
        return original_capture(**kwargs)

    monkeypatch.setitem(ns, "capture_red_player_terminal", capture)
    return SimpleNamespace(
        run=lambda: run_arm(
            ready, arm_id=ns["FORWARD_PROBE_ARM_ID"], authority=object(), forward_probe=probe
        ),
        h=h,
        ready=ready,
        probe=probe,
        logs=logs,
        headers=headers,
        trajectories=trajectories,
        calls=calls,
        captures=captures,
        holder=holder,
        ns=ns,
        menu=menu,
        question=question,
    )


def test_actual_probe_arm_replaces_actor_and_never_claims_native_training(monkeypatch):
    f = probe_wired(monkeypatch)
    with pytest.raises(ValueError) as caught:
        f.run()
    assert caught.value is f.h.error
    header = f.headers[0]
    assert header["model_sha256"] == f.probe.model.sha256
    assert header["tail_model_sha256"] == f.ready.model_sha256
    assert header["model_sha256"] != header["tail_model_sha256"]
    assert header["training_eligible"] is header["native_training_admission"] is False
    assert "player_training_plan" not in header and "player_training_plan_sha256" not in header
    assert "forward_goal_plan" not in header
    assert header["forward_probe"] == f.probe.header()
    recorded = f.trajectories[0]
    assert recorded["displayed_authority"] is f.calls[0]["authority"]
    assert recorded["partition"] == "train" and recorded["policy_id"] == f.probe.policy_id
    assert (
        not {"observe_training", "training_meter", "training_plan_sha256", "forward"}
        & recorded.keys()
    )
    assert f.h.order.index("forward_first") < f.h.order.index("input")
    assert f.h.order.index("failure_state") < f.h.order.index("close")
    assert len(f.h.saved) == 1


def test_probe_terminal_capture_uses_first_actor_identity_and_keeps_nonfit_terminal(monkeypatch):
    f = probe_wired(monkeypatch, stage="terminal_capture")
    with pytest.raises(ValueError) as caught:
        f.run()
    assert caught.value is f.h.error
    assert len(f.captures) == 1
    terminal = f.logs[-1]
    assert terminal["kind"] == "forward_probe_terminal"
    assert terminal["native_training_admission"] is terminal["model_fitted"] is False
    assert terminal["independent_evaluation"] is False
    assert len(f.h.saved) == 1


def test_probe_rejects_initial_singleton_but_allows_honest_tail_without_query(monkeypatch):
    f = probe_wired(monkeypatch, check_singleton=True)
    with pytest.raises(ValueError) as caught:
        f.run()
    assert caught.value is f.h.error
    actor = f.calls[0]["authority"]
    assert actor.forward_decisions == 1 and actor.tail_decisions == 0
    assert len(f.logs) == 1


def test_probe_terminal_log_failure_retains_spent_state_without_masking_error(monkeypatch):
    error = OSError("terminal role log failed")
    f = probe_wired(monkeypatch, stage="terminal_capture", terminal_error=error)
    with pytest.raises(OSError) as caught:
        f.run()
    assert caught.value is error
    assert f.captures == [] and len(f.h.saved) == 1
    assert f.h.order.index("failure_state") < f.h.order.index("close")


def test_probe_goal_predicate_uses_current_simultaneous_completion_and_scope_guard(monkeypatch):
    f = probe_wired(monkeypatch)
    with pytest.raises(ValueError):
        f.run()
    predicate = f.calls[0]["completion_satisfied"]
    f.holder[0] = observation(champion_raw())
    assert predicate(None) is True
    f.holder[0] = observation()
    assert predicate(None) is False  # No previously observed completion latch.
    bad = replace(f.menu.bindings[0], binding_ref="routed-center-unsupported")
    others = f.menu.bindings[1:]
    menu = GoalBindingSet(tuple(b.opportunity for b in (bad, *others)), (bad, *others))
    with pytest.raises(RuntimeError, match="unsupported_binding"):
        f.calls[0]["validate_choice_menu"](SimpleNamespace(binding_set=menu))


@pytest.mark.parametrize("field,value", [
    ("training_plan", None), ("continuation", None), ("continuation_root_lineage_id", ""),
    ("model_sha256", "0" * 64), ("forward_story_objective", "defeat_champion"),
    ("forward_resource_budget", 2), ("decision_limit", 3),
    ("challenger_arm_id", "baseline"), ("routed_recovery", True),
])
def test_probe_actual_scope_rejects_changed_authority_or_limits_before_input(
    monkeypatch, field, value
):
    f = probe_wired(monkeypatch)
    with pytest.raises(RuntimeError):
        f.ns["_require_forward_probe_scope"](replace(f.ready, **{field: value}), f.probe)
    assert f.h.emulator.inputs == 0 and not f.logs and not f.headers


def test_new_source_is_explicit_probe_compatibility_not_claimed_fitted_equivalence(monkeypatch):
    f = probe_wired(monkeypatch)
    ready = replace(f.ready, source_bundle_sha256="9" * 64)
    f.ns["_require_forward_probe_scope"](ready, f.probe)
    assert f.probe.header()["fitted_source_bundle_sha256"] != ready.source_bundle_sha256
    assert f.probe.header()["continuation_source_equivalence_claimed"] is False


@pytest.mark.parametrize("enabled", [False, True])
def test_probe_checkpoint_recovers_its_own_completion_dose_without_native_plan(
    monkeypatch, enabled
):
    f = probe_wired(monkeypatch)
    header = {
        "metadata": {
            "completion_dose": enabled,
            "forward_probe": {
                **f.probe.header(),
                "execution_flags": {"completion_dose": enabled},
            },
        }
    }
    assert f.ns["_checkpoint_completion_dose"](header) is enabled


@pytest.mark.parametrize("mutation", ["missing", "integer", "disagree", "schema", "flags"])
def test_probe_checkpoint_rejects_ambiguous_observer_settings(monkeypatch, mutation):
    f = probe_wired(monkeypatch)
    metadata = {
        "completion_dose": True,
        "forward_probe": {
            **f.probe.header(),
            "execution_flags": {"completion_dose": True},
        },
    }
    if mutation == "missing":
        del metadata["completion_dose"]
    elif mutation == "integer":
        metadata["completion_dose"] = 1
    elif mutation == "disagree":
        metadata["forward_probe"]["execution_flags"]["completion_dose"] = False
    elif mutation == "schema":
        metadata["forward_probe"]["schema"] = "unknown"
    else:
        metadata["forward_probe"]["execution_flags"] = None
    with pytest.raises(RuntimeError, match="probe_observer_mode"):
        f.ns["_checkpoint_completion_dose"]({"metadata": metadata})
