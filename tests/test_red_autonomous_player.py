import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_live_option_menu import _binding, _mixed, _model, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_autonomous_player import (
    AutonomousSnapshot,
    continuation_binding,
    run_assisted_safari_probe,
    run_autonomous_goal_continuation,
    run_autonomous_options,
)
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def _assisted_safari_provenance():
    return {"training_assistance": {
        "kind": "money_override", "final_run_eligible": False,
    }}


def test_assisted_safari_probe_records_teacher_selection_and_never_fits(tmp_path):
    output = tmp_path / "probe"
    state = {"version": 0}
    calls = []
    ordinary = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="evolve", calls=calls)
    safari = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref=f"pokemon.red:safari-live:{'a' * 64}", calls=calls,
    )

    def execute():
        assert (output / "execution-started.json").exists()
        state["version"] = 1
        return GoalExecutionReport(3, 40, {"admission_cost": 500})

    safari = replace(safari, execute=execute, verify=lambda _: GoalVerification.succeeded())

    def snapshot():
        return AutonomousSnapshot(str(state["version"]).encode(), {
            "cash": 500 if state["version"] == 0 else 0,
        }, True)

    options = SimpleNamespace(
        bindings=(ordinary, safari),
        menu=SimpleNamespace(available_indices=(0, 1), policy_sha256="b" * 64),
    )
    result = run_assisted_safari_probe(
        output=output, snapshot=snapshot, observe=lambda _: options,
        provenance=_assisted_safari_provenance(),
    )
    assert result["status"] == "complete"
    assert result["model_queries"] == result["model_decisions"] == 0
    assert result["goal_value_fit_allowed"] is False
    assert result["outcome"]["learning_eligible"] is False
    assert result["outcome"]["evidence"] == {"admission_cost": 500}
    assert json.loads((output / "execution-started.json").read_text())[
        "selection_authority"
    ] == "teacher_training_only"
    assert (output / "terminal.state").read_bytes() == b"1"
    assert calls == []


def test_assisted_safari_probe_rejects_unmarked_or_ambiguous_selection(tmp_path):
    state = {"version": 0}

    def snapshot():
        return AutonomousSnapshot(str(state["version"]).encode(), {}, True)

    with pytest.raises(ValueError, match="marked non-final"):
        run_assisted_safari_probe(
            output=tmp_path / "unmarked", snapshot=snapshot,
            observe=lambda _: pytest.fail("unmarked probe must not inspect"),
            provenance={},
        )
    assert not (tmp_path / "unmarked").exists()
    safari = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref=f"pokemon.red:safari-live:{'a' * 64}", calls=[],
    )
    options = SimpleNamespace(
        bindings=(safari, safari),
        menu=SimpleNamespace(available_indices=(0, 1), policy_sha256="b" * 64),
    )
    with pytest.raises(ValueError, match="exactly one"):
        run_assisted_safari_probe(
            output=tmp_path / "ambiguous", snapshot=snapshot, observe=lambda _: options,
            provenance=_assisted_safari_provenance(),
        )
    assert (tmp_path / "ambiguous/admission-failure.json").exists()
    assert not (tmp_path / "ambiguous/execution-started.json").exists()


def test_assisted_safari_probe_retains_failed_terminal_without_retry(tmp_path):
    output = tmp_path / "failed"
    state = {"version": 0}
    safari = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref=f"pokemon.red:safari-live:{'a' * 64}", calls=[],
    )

    def execute():
        state["version"] = 1
        raise RuntimeError("admission failed after input")

    safari = replace(safari, execute=execute)
    options = SimpleNamespace(
        bindings=(safari,),
        menu=SimpleNamespace(available_indices=(0,), policy_sha256="b" * 64),
    )
    result = run_assisted_safari_probe(
        output=output,
        snapshot=lambda: AutonomousSnapshot(str(state["version"]).encode(), {}, True),
        observe=lambda _: options,
        provenance=_assisted_safari_provenance(),
    )
    assert result["status"] == "stopped"
    assert result["outcome"]["error_chain"][0]["error_type"] == "RuntimeError"
    assert (output / "terminal.state").read_bytes() == b"1"
    with pytest.raises(FileExistsError):
        run_assisted_safari_probe(
            output=output,
            snapshot=lambda: AutonomousSnapshot(b"1", {}, True),
            observe=lambda _: options,
            provenance=_assisted_safari_provenance(),
        )


def test_saved_goal_continuation_uses_unique_private_fingerprint_without_new_choice(tmp_path):
    suffix = "a" * 64
    calls = []
    state = {"xp": 4905}

    def snapshot():
        return AutonomousSnapshot(
            str(state["xp"]).encode(),
            {"party_training": [[1, 78, state["xp"]]], "actions": len(calls)},
            True,
        )

    binding = _binding(
        GoalKind.EVOLVE_SPECIES, binding_ref=f"new-origin:{suffix}", calls=calls,
    )

    def execute():
        assert (tmp_path / "continuation/execution-started.json").exists()
        calls.append("execute")
        state["xp"] += 153
        return GoalExecutionReport(50, 5000, {"evolution_partial": True})

    binding = replace(
        binding, execute=execute,
        verify=lambda _: GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED),
    )
    options = SimpleNamespace(
        bindings=(binding,), menu=SimpleNamespace(policy_sha256="b" * 64),
    )
    result = run_autonomous_goal_continuation(
        output=tmp_path / "continuation", snapshot=snapshot,
        observe=lambda _: options, prior_binding_ref=f"old-origin:{suffix}",
        prior_outcome_sha256="c" * 64, provenance={},
    )
    assert result["status"] == "pending"
    assert result["experience_gain"] == 153
    assert result["model_queries"] == result["model_decisions"] == 0
    assert calls == ["execute"]
    assert (tmp_path / "continuation/terminal.state").read_bytes() == b"5058"


def test_goal_continuation_rejects_missing_or_duplicate_target():
    suffix = "a" * 64
    binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref=f"new:{suffix}", calls=[])
    with pytest.raises(ValueError, match="no unique"):
        continuation_binding(SimpleNamespace(bindings=()), f"old:{suffix}")
    with pytest.raises(ValueError, match="no unique"):
        continuation_binding(SimpleNamespace(bindings=(binding, binding)), f"old:{suffix}")


def test_targeted_continuation_skips_full_menu_and_records_private_inventory(tmp_path):
    suffix = "a" * 64
    state = {"xp": 7095}
    binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref=f"new:{suffix}", calls=[])

    def execute():
        assert (tmp_path / "run/execution-started.json").exists()
        state["xp"] += 90
        return GoalExecutionReport(50, 5000, {"evolution_partial": True})

    binding = replace(
        binding, execute=execute,
        verify=lambda _: GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED),
    )

    def snapshot():
        return AutonomousSnapshot(str(state["xp"]).encode(), {
            "party_training": [[1, 78, state["xp"]]],
        }, True)

    result = run_autonomous_goal_continuation(
        output=tmp_path / "run", snapshot=snapshot,
        observe=lambda _: pytest.fail("full policy menu must not be rebuilt"),
        targeted_observe=lambda: (binding,), prior_binding_ref=f"old:{suffix}",
        prior_outcome_sha256="b" * 64, provenance={},
    )
    marker = json.loads((tmp_path / "run/execution-started.json").read_text())
    assert marker["binding_scope"] == "targeted_evolution"
    assert marker["menu_sha256"] is None
    assert marker["private_inventory_sha256"] is not None
    assert result["status"] == "pending"
    assert result["model_queries"] == 0


def test_targeted_continuation_cannot_execute_if_discovery_mutates_state(tmp_path):
    suffix = "a" * 64
    state = {"xp": 7095}
    binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref=f"new:{suffix}", calls=[])

    def snapshot():
        return AutonomousSnapshot(str(state["xp"]).encode(), {}, True)

    def mutate():
        state["xp"] += 1
        return (binding,)

    with pytest.raises(ValueError, match="changed the game"):
        run_autonomous_goal_continuation(
            output=tmp_path / "run", snapshot=snapshot,
            observe=lambda _: pytest.fail("full menu must not run"),
            targeted_observe=mutate, prior_binding_ref=f"old:{suffix}",
            prior_outcome_sha256="b" * 64, provenance={},
        )
    assert not (tmp_path / "run/execution-started.json").exists()
    assert (tmp_path / "run/admission-failure.json").exists()


def _environment(output, *, fail=False, verify_fails=False, unsafe=False):
    state = {"version": 0, "observations": [], "selected": []}

    def snapshot():
        return AutonomousSnapshot(
            str(state["version"]).encode(),
            {"version": state["version"]},
            not (unsafe and state["version"]),
        )

    def observe(ordinal):
        state["observations"].append(state["version"])
        options = _mixed([])
        # Avoid a deterministic resource emergency for the model-control tests.
        options = replace(options, situation=_situation(resources=0.1))
        bindings = []
        for index, binding in enumerate(options.bindings):

            def execute(index=index):
                saved = json.loads((output / f"step-{ordinal:03d}" / "decision.json").read_text())
                assert saved["selected_candidate_index"] == index
                state["selected"].append(index)
                state["version"] += 1
                if fail:
                    raise RuntimeError("failure after real state change")
                return GoalExecutionReport(1, 1, {})

            def verify(report):
                if verify_fails:
                    raise ValueError("verification failed after execution")
                return GoalVerification.succeeded()

            bindings.append(replace(binding, execute=execute, verify=verify))
        return replace(options, bindings=tuple(bindings))

    return state, snapshot, observe


def test_three_model_choices_execute_only_saved_arms_and_reobserve_earned_states(tmp_path):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        provenance={},
    )
    assert result["successful_decisions"] == 3
    assert state["observations"] == [0, 1, 2]
    assert len(state["selected"]) == 3
    assert result["stop_reason"] == "decision_budget"
    assert (output / "step-002/terminal.state").read_bytes() == b"3"


@pytest.mark.parametrize("failure", ["execute", "verify", "unsafe"])
def test_partial_state_and_decision_survive_failure_without_next_query(tmp_path, failure):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(
        output,
        fail=failure == "execute",
        verify_fails=failure == "verify",
        unsafe=failure == "unsafe",
    )
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        provenance={},
    )
    assert result["executed_decisions"] == 1
    assert state["observations"] == [0]
    assert (output / "step-000/decision.json").exists()
    assert (output / "step-000/terminal.state").read_bytes() == b"1"
    assert not (output / "step-001").exists()


def test_execution_failure_preserves_typed_cause_chain(tmp_path):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)
    original = observe

    def caused_observe(ordinal):
        options = original(ordinal)
        rebound = []
        for binding in options.bindings:
            def execute():
                state["version"] += 1
                try:
                    raise ValueError("battle introduction exceeded its bound")
                except ValueError as cause:
                    error = RuntimeError("travel capture controller failed")
                    error.reason_code = "capture_controller_failed"
                    raise error from cause

            rebound.append(replace(binding, execute=execute))
        return replace(options, bindings=tuple(rebound))

    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=caused_observe,
        seed=17,
        provenance={},
    )

    assert result["outcomes"][0]["error_chain"] == [
        {
            "error_type": "RuntimeError",
            "error": "travel capture controller failed",
            "reason_code": "capture_controller_failed",
        },
        {
            "error_type": "ValueError",
            "error": "battle introduction exceeded its bound",
        },
    ]


def test_decision_write_failure_prevents_every_controller_action(tmp_path, monkeypatch):
    import pokemon_red_completion.red_autonomous_player as module

    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)
    original = module._record

    def fail_decision(path, payload):
        if path.name == "decision.json":
            raise OSError("disk failed")
        original(path, payload)

    monkeypatch.setattr(module, "_record", fail_decision)
    with pytest.raises(OSError, match="disk failed"):
        run_autonomous_options(
            model=_model(),
            output=output,
            snapshot=snapshot,
            observe=observe,
            seed=17,
            provenance={},
        )
    assert state["version"] == 0
    assert (output / "step-000/intent.json").exists()
    with pytest.raises(FileExistsError):
        run_autonomous_options(
            model=_model(),
            output=output,
            snapshot=snapshot,
            observe=observe,
            seed=17,
            provenance={},
        )


def test_teacher_safety_choice_is_persisted_but_never_executed(tmp_path):
    calls = []
    options = build_red_live_option_set(
        situation=_situation(resources=0.1, safety=1.0),
        binding_set=_ordinary_bindings(calls),
        supplements=(),
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(400, ()),
        target_cash=400,
    )
    output = tmp_path / "run"
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=lambda: AutonomousSnapshot(b"same", {}, True),
        observe=lambda _: options,
        seed=17,
        provenance={},
    )
    assert result["executed_decisions"] == 0
    assert result["stop_reason"] == "safety_boundary_requires_separate_recovery"
    assert (output / "step-000/decision.json").exists()
    assert calls == []


def test_storage_safety_executes_as_nonlearning_support_then_requeries_model(tmp_path):
    output = tmp_path / "run"
    state = {"version": 0}

    def snapshot():
        return AutonomousSnapshot(str(state["version"]).encode(), {}, True)

    def observe(_ordinal):
        calls = []
        ordinary = _ordinary_bindings(calls)
        storage = _binding(
            GoalKind.MANAGE_STORAGE,
            binding_ref="private:red:storage",
            calls=calls,
        )
        ordinary = GoalBindingSet(
            tuple(
                storage.opportunity if item.kind is GoalKind.MANAGE_STORAGE else item
                for item in ordinary.opportunities
            ),
            (*ordinary.bindings, storage),
        )
        options = build_red_live_option_set(
            situation=_situation(resources=0.1, storage=1.0 if not state["version"] else 0.1),
            binding_set=ordinary,
            supplements=(),
            model_feature_version=4,
            ordering_seed_sha256="c" * 64,
            economy_snapshot=EconomySnapshot(400, ()),
            target_cash=400,
        )
        rebound = []
        for binding in options.bindings:

            def execute(binding=binding):
                state["version"] += 1
                return GoalExecutionReport(1, 1, {"kind": binding.kind.value})

            rebound.append(
                replace(
                    binding,
                    execute=execute,
                    verify=lambda _: GoalVerification.succeeded(),
                )
            )
        return replace(options, bindings=tuple(rebound))

    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        maximum_decisions=2,
        provenance={},
    )

    assert result["executed_decisions"] == 2
    assert result["support_decisions"] == 1
    assert result["model_decisions"] == 1
    assert result["outcomes"][0]["support_role"] == "deterministic_storage_safety"
    assert result["outcomes"][0]["learning_eligible"] is False
    assert result["outcomes"][1]["learning_eligible"] is True


def test_mutating_menu_is_rejected_before_model_query(tmp_path):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)

    def bad_observe(ordinal):
        state["version"] += 1
        return observe(ordinal)

    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=bad_observe,
        seed=17,
        provenance={},
    )
    assert result["stop_reason"] == "menu_unavailable"
    assert not (output / "step-000/intent.json").exists()
    assert state["selected"] == []


def test_semantically_aliased_menu_executes_only_saved_choice_as_support(tmp_path, monkeypatch):
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

    output = tmp_path / "aliased"
    state, snapshot, observe = _environment(output)

    def aliased_observe(ordinal):
        options = observe(ordinal)
        first = options.menu.candidates[0]
        menu = replace(options.menu, candidates=tuple(
            replace(first, binding_ref=c.binding_ref) for c in options.menu.candidates
        ))
        return replace(options, menu=menu)

    def forbidden(*args, **kwargs):
        raise AssertionError("aliased menu queried model")

    monkeypatch.setattr(LivingDexOptionValueModel, "scores", forbidden)
    result = run_autonomous_options(
        model=_model(), output=output, snapshot=snapshot, observe=aliased_observe,
        seed=17, provenance={},
    )
    assert result["stop_reason"] == "decision_budget"
    assert result["executed_decisions"] == 3
    assert result["model_decisions"] == 0
    assert result["support_decisions"] == 3
    assert state["selected"]
    assert (output / "step-002/terminal.state").read_bytes() == b"3"
    for ordinal, selected in enumerate(state["selected"]):
        step = output / f"step-{ordinal:03d}"
        assert json.loads((step / "intent.json").read_text())["query_may_be_consumed"] is False
        decision = json.loads((step / "decision.json").read_text())
        assert decision["mode"] == "equivalent_exploration"
        assert decision["selected_candidate_index"] == selected
        outcome = json.loads((step / "outcome.json").read_text())
        assert outcome["learning_eligible"] is False
        assert outcome["support_role"] == "equivalent_goal_exploration"
