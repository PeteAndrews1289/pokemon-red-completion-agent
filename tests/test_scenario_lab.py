from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.scenario_lab import (
    ScenarioAuthority,
    ScenarioCatalog,
    ScenarioFailureKind,
    ScenarioFamily,
    ScenarioLabError,
    ScenarioObservation,
    ScenarioPartition,
    ScenarioPolicyDecision,
    ScenarioSpec,
    ScenarioStep,
    ScenarioVerdict,
    ScenarioVerdictStatus,
    run_scenario_episode,
)


def _spec(
    family: ScenarioFamily,
    *,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
    authority: ScenarioAuthority = ScenarioAuthority.TEACHER_FREE,
    maximum_actions: int = 4,
    maximum_frames: int = 40,
) -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id=f"lab-{family.value}-{partition.value}",
        family=family,
        partition=partition,
        environment_id="synthetic-bounded-environment-v1",
        observation_schema_id="semantic-lab-observation-v1",
        source_commit="c" * 40,
        root_lineage_id=f"root-{family.value}-{partition.value}",
        initial_state_sha256=("a" if partition is ScenarioPartition.TRAIN else "b") * 64,
        allowed_action_kinds=("advance", "recover"),
        randomization_dimensions=("timing_offset", "semantic_start"),
        verifier_id="bounded-progress-v1",
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
        authority=authority,
    )


class Environment:
    def __init__(self, *, target: int = 3, frames: int = 5) -> None:
        self.progress = 0
        self.target = target
        self.frames = frames

    def reset(self, seed: int) -> ScenarioObservation:
        self.progress = seed % 2
        return ScenarioObservation(
            {"progress": self.progress, "target": self.target, "ready": True}
        )

    def step(self, action_kind: str) -> ScenarioStep:
        if action_kind == "advance":
            self.progress += 1
        elif action_kind == "recover":
            self.progress = max(0, self.progress - 1)
        return ScenarioStep(
            ScenarioObservation(
                {"progress": self.progress, "target": self.target, "ready": True}
            ),
            self.frames,
        )


class Policy:
    policy_id = "semantic-policy-v1"

    def __init__(self, action: str | None = "advance") -> None:
        self.action = action

    def choose(
        self,
        family: ScenarioFamily,
        observation: ScenarioObservation,
        allowed_action_kinds: tuple[str, ...],
    ) -> ScenarioPolicyDecision:
        del family, observation, allowed_action_kinds
        if self.action is None:
            return ScenarioPolicyDecision(None, requests_intervention=True)
        return ScenarioPolicyDecision(self.action, confidence=0.8)


class Verifier:
    verifier_id = "bounded-progress-v1"

    def evaluate(self, observation: ScenarioObservation) -> ScenarioVerdict:
        progress = observation.semantic_state["progress"]
        target = observation.semantic_state["target"]
        assert isinstance(progress, int) and isinstance(target, int)
        return ScenarioVerdict(
            ScenarioVerdictStatus.SUCCEEDED
            if progress >= target
            else ScenarioVerdictStatus.ONGOING
        )


@pytest.mark.parametrize("family", tuple(ScenarioFamily))
def test_each_core_family_runs_hundreds_of_bounded_contract_episodes(
    family: ScenarioFamily,
) -> None:
    spec = _spec(family)
    results = tuple(
        run_scenario_episode(
            spec,
            seed=seed,
            environment=Environment(),
            policy=Policy(),
            verifier=Verifier(),
        )
        for seed in range(200)
    )

    assert all(result.passed for result in results)
    assert all(result.actions_executed <= spec.maximum_actions for result in results)
    assert len({result.assignment_sha256 for result in results}) == 200
    assert all(result.learner_update_eligible for result in results)


def test_test_partition_never_becomes_a_learner_update() -> None:
    result = run_scenario_episode(
        _spec(ScenarioFamily.BATTLE, partition=ScenarioPartition.TEST),
        seed=1,
        environment=Environment(),
        policy=Policy(),
        verifier=Verifier(),
    )

    assert result.passed
    assert not result.learner_update_eligible


def test_intervention_is_explicit_and_counted() -> None:
    spec = _spec(
        ScenarioFamily.PARTY_DEVELOPMENT,
        authority=ScenarioAuthority.INTERVENTION_BACKED,
    )
    result = run_scenario_episode(
        spec,
        seed=0,
        environment=Environment(),
        policy=Policy(action=None),
        intervention_policy=Policy(),
        verifier=Verifier(),
    )

    assert result.passed
    assert result.teacher_interventions == 3
    assert result.intervention_policy_id == "semantic-policy-v1"

    class AlternateIntervention(Policy):
        policy_id = "alternate-intervention-v1"

    alternate = run_scenario_episode(
        spec,
        seed=0,
        environment=Environment(),
        policy=Policy(action=None),
        intervention_policy=AlternateIntervention(),
        verifier=Verifier(),
    )
    assert alternate.assignment_sha256 != result.assignment_sha256


def test_action_and_frame_budgets_have_distinct_terminal_reasons() -> None:
    action_limited = run_scenario_episode(
        _spec(ScenarioFamily.NAVIGATION, maximum_actions=1),
        seed=0,
        environment=Environment(),
        policy=Policy(),
        verifier=Verifier(),
    )
    frame_limited = run_scenario_episode(
        _spec(ScenarioFamily.NAVIGATION, maximum_frames=3),
        seed=0,
        environment=Environment(frames=5),
        policy=Policy(),
        verifier=Verifier(),
    )

    assert action_limited.failure_kind is ScenarioFailureKind.ACTION_BUDGET_EXHAUSTED
    assert frame_limited.failure_kind is ScenarioFailureKind.FRAME_BUDGET_EXHAUSTED


def test_catalog_rejects_lineage_or_state_leakage_between_partitions() -> None:
    train = _spec(ScenarioFamily.BATTLE)
    validation = _spec(
        ScenarioFamily.BATTLE,
        partition=ScenarioPartition.DEVELOPMENT,
    )
    with pytest.raises(ScenarioLabError, match="lineage"):
        ScenarioCatalog((train, replace(validation, root_lineage_id=train.root_lineage_id)))
    with pytest.raises(ScenarioLabError, match="initial state"):
        ScenarioCatalog(
            (train, replace(validation, initial_state_sha256=train.initial_state_sha256))
        )


def test_public_overlap_counts_are_derived_even_if_constructor_is_bypassed() -> None:
    train = _spec(ScenarioFamily.BATTLE)
    development = replace(
        _spec(ScenarioFamily.BATTLE, partition=ScenarioPartition.DEVELOPMENT),
        root_lineage_id=train.root_lineage_id,
        initial_state_sha256=train.initial_state_sha256,
    )
    catalog = object.__new__(ScenarioCatalog)
    object.__setattr__(catalog, "specs", (train, development))

    public = catalog.public_dict()

    assert public["lineage_partition_overlap"] == 1
    assert public["initial_state_partition_overlap"] == 1


def test_public_spec_binds_environment_schema_and_exact_source() -> None:
    public = _spec(ScenarioFamily.NAVIGATION).public_dict()

    assert public["environment_id"] == "synthetic-bounded-environment-v1"
    assert public["observation_schema_id"] == "semantic-lab-observation-v1"
    assert public["source_commit"] == "c" * 40
    with pytest.raises(ScenarioLabError, match="source commit"):
        replace(_spec(ScenarioFamily.NAVIGATION), source_commit="dirty")


def test_policy_observation_rejects_labels_paths_and_title_identity() -> None:
    with pytest.raises(ScenarioLabError, match="forbidden key"):
        ScenarioObservation({"progress": 1, "teacher_choice": "advance"})
    with pytest.raises(ScenarioLabError, match="private path"):
        ScenarioObservation({"source": "/Users/example/private.state"})


def test_environment_exception_is_classified_without_public_exception_text() -> None:
    class BrokenEnvironment(Environment):
        def step(self, action_kind: str) -> ScenarioStep:
            del action_kind
            raise RuntimeError("private diagnostic text")

    result = run_scenario_episode(
        _spec(ScenarioFamily.BATTLE),
        seed=0,
        environment=BrokenEnvironment(),
        policy=Policy(),
        verifier=Verifier(),
    )

    public = result.public_dict()
    assert result.failure_kind is ScenarioFailureKind.ENVIRONMENT_ERROR
    assert result.failure_message_sha256 is not None
    assert not result.learner_update_eligible
    assert "private diagnostic text" not in str(public)


@pytest.mark.parametrize(
    ("component", "expected"),
    (
        ("policy", ScenarioFailureKind.POLICY_ERROR),
        ("verifier", ScenarioFailureKind.VERIFIER_ERROR),
    ),
)
def test_policy_and_verifier_faults_are_not_gameplay_training_outcomes(
    component: str,
    expected: ScenarioFailureKind,
) -> None:
    class BrokenPolicy(Policy):
        def choose(
            self,
            family: ScenarioFamily,
            observation: ScenarioObservation,
            allowed_action_kinds: tuple[str, ...],
        ) -> ScenarioPolicyDecision:
            del family, observation, allowed_action_kinds
            raise RuntimeError("private policy diagnostic")

    class BrokenVerifier(Verifier):
        def evaluate(self, observation: ScenarioObservation) -> ScenarioVerdict:
            del observation
            raise RuntimeError("private verifier diagnostic")

    result = run_scenario_episode(
        _spec(ScenarioFamily.BATTLE),
        seed=0,
        environment=Environment(),
        policy=BrokenPolicy() if component == "policy" else Policy(),
        verifier=BrokenVerifier() if component == "verifier" else Verifier(),
    )

    assert result.failure_kind is expected
    assert result.failure_message_sha256 is not None
    assert not result.learner_update_eligible
    assert "private policy diagnostic" not in str(result.public_dict())
    assert "private verifier diagnostic" not in str(result.public_dict())


@pytest.mark.parametrize(
    ("component", "expected"),
    (
        ("policy", ScenarioFailureKind.POLICY_ERROR),
        ("verifier", ScenarioFailureKind.VERIFIER_ERROR),
    ),
)
def test_invalid_component_results_are_typed_not_called_environment_failures(
    component: str,
    expected: ScenarioFailureKind,
) -> None:
    class InvalidPolicy(Policy):
        def choose(  # type: ignore[override]
            self,
            family: ScenarioFamily,
            observation: ScenarioObservation,
            allowed_action_kinds: tuple[str, ...],
        ) -> object:
            del family, observation, allowed_action_kinds
            return object()

    class InvalidVerifier(Verifier):
        def evaluate(self, observation: ScenarioObservation) -> object:  # type: ignore[override]
            del observation
            return object()

    result = run_scenario_episode(
        _spec(ScenarioFamily.BATTLE),
        seed=0,
        environment=Environment(),
        policy=InvalidPolicy() if component == "policy" else Policy(),  # type: ignore[arg-type]
        verifier=InvalidVerifier() if component == "verifier" else Verifier(),  # type: ignore[arg-type]
    )

    assert result.failure_kind is expected
    assert not result.learner_update_eligible
