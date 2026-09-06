from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from test_living_dex_causal_journal import _scenario, _store_and_registry
from test_living_dex_policy_development import _model

from pokemon_red_completion.goal_manager import GoalSituation
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalObservation,
    LivingDexCausalResolvedArm,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionValueModel,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.living_dex_paired_development import (
    LivingDexPairedDevelopmentError,
    completion_first_question,
    execute_living_dex_paired_development,
    read_paired_record,
)
from pokemon_red_completion.provenance import canonical_sha256


def _pair():  # type: ignore[no-untyped-def]
    scenario, harness = _scenario("paired-development")
    situation = GoalSituation(0.2, 0.2, 0.1, 0.95, 0.1, 0.1, 0.1, 0.0, 0.1)
    origin = {**scenario.origin_observation, "situation": situation.policy_dict()}
    menu = replace(
        scenario.menu,
        context=living_dex_option_context_from_goal_situation(situation),
        candidates=scenario.menu.candidates[:2],
    )
    bindings = scenario.binding_sha256s[:2]
    identity = replace(
        scenario.identity,
        partition="development",
        menu_sha256=menu.policy_sha256,
        origin_observation_sha256=canonical_sha256(origin),
        binding_roster_sha256=canonical_sha256(
            {
                "binding_sha256s": list(bindings),
                "schema": "pokemon.core.living-dex-causal-binding-roster.v1",
            }
        ),
    )
    return replace(
        scenario,
        identity=identity,
        menu=menu,
        origin_observation=origin,
        binding_sha256s=bindings,
    ), harness


def _run(scenario, store, registry, **kwargs):  # type: ignore[no-untyped-def]
    model = kwargs.pop("model", _model())
    return execute_living_dex_paired_development(
        scenario,
        model,
        expected_model_sha256=model.model_sha256,
        store=store,
        claim_registry=registry,
        **kwargs,
    )


def test_both_different_choices_are_durable_before_any_runtime(tmp_path: Path) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)
    original = scenario.resolve_selected

    @contextmanager
    def checked_resolver(index, gate):  # type: ignore[no-untyped-def]
        record = read_paired_record(
            store, "lpd-pair-" + scenario.identity.identity_sha256[:32] + "-choices"
        )
        assert record is not None
        assert record["model_decision"]["selected_candidate_index"] == 0
        assert record["control_selected_candidate_index"] == 1
        with original(index, gate) as arm:
            yield arm

    result = _run(replace(scenario, resolve_selected=checked_resolver), store, registry)
    assert harness.executions == [0, 1]
    assert harness.resolver_calls == [0, 1]
    assert harness.observations == ["observed", "observed"]
    assert [arm["controller_actions"] for arm in result.arms] == [3, 3]
    assert [arm["emulator_frames"] for arm in result.arms] == [12, 12]
    public = result.public_dict()
    assert public["utility_delta"] == 0.0
    assert public["descriptive_model_win"] is False
    assert public["training_targets_emitted"] == 0
    assert public["promotion_authorized"] is False
    assert "private.paired-development" not in str(public)


def test_complete_recovery_does_not_predict_execute_or_observe_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)
    result = _run(scenario, store, registry)

    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("completed pair must not predict again")

    monkeypatch.setattr(LivingDexOptionValueModel, "predict_candidate", forbidden)
    assert _run(scenario, store, registry) == result
    assert harness.executions == [0, 1]
    assert harness.resolver_calls == [0, 1]
    assert len(harness.observations) == 2


@pytest.mark.parametrize("stage", ["after_model_attempt", "after_model_release"])
def test_interrupted_model_arm_never_retries_but_unstarted_control_continues(
    tmp_path: Path,
    stage: str,
) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)

    def failpoint(value: str) -> None:
        if value == stage:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(scenario, store, registry, failpoint=failpoint)
    assert harness.executions == []
    result = _run(scenario, store, registry)
    assert harness.executions == [1]
    assert result.arms[0]["status"] == "interrupted"
    assert result.arms[0]["outcome"] is None
    assert result.public_dict()["utility_delta"] is None
    assert _run(scenario, store, registry) == result
    assert harness.executions == [1]


def test_completed_first_arm_survives_power_loss_before_second(tmp_path: Path) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)

    def failpoint(stage: str) -> None:
        if stage == "after_model_terminal":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(scenario, store, registry, failpoint=failpoint)
    assert harness.executions == [0]
    result = _run(scenario, store, registry)
    assert harness.executions == [0, 1]
    assert result.arms[0]["status"] == "settled"


@pytest.mark.parametrize("drift", ["binding", "meter", "early_gate", "hidden_input"])
def test_runtime_drift_cannot_release_input_or_create_an_outcome(
    tmp_path: Path, drift: str
) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)
    original = scenario.resolve_selected

    @contextmanager
    def wrong(index, gate):  # type: ignore[no-untyped-def]
        with original(index, gate) as arm:
            if drift == "binding":
                arm = replace(arm, binding_sha256="f" * 64)
            elif drift == "meter":
                arm = replace(arm, effect_meter=replace(harness.meter))
            elif drift == "early_gate":
                gate.authorize_controller_input()
            else:
                harness.meter.controller_actions += 1
            yield arm

    result = _run(replace(scenario, resolve_selected=wrong), store, registry)
    assert harness.executions == []
    assert harness.observations == []
    assert [arm["status"] for arm in result.arms] == ["failed", "failed"]
    assert result.public_dict()["utility_delta"] is None


def test_private_execution_diagnostic_is_retained_but_not_published(tmp_path: Path) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)
    original = scenario.resolve_selected
    sensitive = str(tmp_path / "private-case" / "cartridge.gb")

    @contextmanager
    def throwing(index, gate):  # type: ignore[no-untyped-def]
        with original(index, gate) as arm:

            def execute(token):  # type: ignore[no-untyped-def]
                arm.execute(token)
                raise RuntimeError("precise failure at " + sensitive)

            yield LivingDexCausalResolvedArm(
                arm.binding_sha256, arm.effect_meter, execute, arm.action_trace
            )

    result = _run(replace(scenario, resolve_selected=throwing), store, registry)
    assert "Path-bearing exception message withheld" in str(result.arms[0]["private_diagnostic"])
    assert sensitive not in str(result.arms[0]["private_diagnostic"])
    assert "RuntimeError" in str(result.arms[0]["private_diagnostic"])
    assert sensitive not in str(result.public_dict())
    assert result.public_dict()["descriptive_model_win"] is False
    assert harness.executions == [0, 1]


def test_model_only_loss_cannot_be_hidden_by_higher_utility(tmp_path: Path) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)
    original = scenario.observe_after

    def outcome():  # type: ignore[no-untyped-def]
        observed = original()
        first = harness.executions[-1] == 0
        return LivingDexCausalObservation(
            replace(
                observed.outcome,
                completion_gain=1.0 if first else 0.0,
                irreversible_loss=0.01 if first else 0.0,
            ),
            observed.provenance,
        )

    public = _run(replace(scenario, observe_after=outcome), store, registry).public_dict()
    assert public["utility_delta"] == pytest.approx(3.96)
    assert public["model_only_irreversible_loss"] is True
    assert public["descriptive_model_win"] is False


@pytest.mark.parametrize("drift", ["train", "pressure", "model"])
def test_wrong_inputs_fail_without_claims_or_input(tmp_path: Path, drift: str) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)
    model = _model()
    expected = model.model_sha256
    if drift == "train":
        scenario = replace(scenario, identity=replace(scenario.identity, partition="train"))
    elif drift == "pressure":
        origin = {
            **scenario.origin_observation,
            "situation": GoalSituation(*([0.1] * 9)).policy_dict(),
        }
        scenario = replace(
            scenario,
            origin_observation=origin,
            identity=replace(
                scenario.identity,
                origin_observation_sha256=canonical_sha256(origin),
            ),
        )
    else:
        expected = "f" * 64
    with pytest.raises(LivingDexPairedDevelopmentError):
        execute_living_dex_paired_development(
            scenario, model, expected_model_sha256=expected, store=store, claim_registry=registry
        )
    assert harness.executions == []
    assert harness.resolver_calls == []
    assert not list(registry.glob("claim-pair-v1-*.json"))


def test_control_reconstructs_original_needs_without_private_bindings() -> None:
    scenario, _ = _pair()
    question = completion_first_question(scenario)
    assert question.situation.evolution_pressure == 0.95
    assert question.situation.team_pressure == 0.1
    assert question.situation.recovery_pressure == 0.0
    assert question.opportunities[1].estimated_effort == pytest.approx(0.4)
    assert all(
        "private.paired-development" not in item.binding_ref for item in question.opportunities
    )


def test_view_failure_does_not_change_choices_or_abort_control(tmp_path: Path) -> None:
    scenario, harness = _pair()
    store, registry = _store_and_registry(tmp_path)

    def broken_view(*args):  # type: ignore[no-untyped-def]
        raise ConnectionError("viewer disconnected")

    result = _run(scenario, store, registry, observer=broken_view)
    assert harness.executions == [0, 1]
    assert result.public_dict()["utility_delta"] == 0.0
