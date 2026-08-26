from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_ranker import (
    DEPENDENCY_RANKER_FEATURE_NAMES,
    DependencyRankerModel,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedCapability,
    BoundRedDualCapabilityScenario,
    build_red_dual_capability_scenario,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    ProspectiveRedCapabilityBinding,
    RedDependencyCapabilityRole,
    RedDependencySpeciesBinding,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.red_living_dex_option_development import (
    PreparedRedLivingDexOption,
    RedLivingDexOptionDevelopmentError,
    execute_red_living_dex_bound_selection,
    execute_red_living_dex_option,
    prepare_red_living_dex_option,
    score_red_living_dex_option,
)

PRECURSOR = "pokemon:national:050"
EVOLVED = "pokemon:national:051"
RESET = "a" * 64
CONTEXT = "b" * 64


@dataclass
class _World:
    ledger: DependencySpecimenLedger
    acquire_calls: int = 0
    evolve_calls: int = 0


def _ledger(precursor_count: int, evolved_count: int) -> DependencySpecimenLedger:
    rows = []
    if precursor_count:
        rows.append((PRECURSOR, precursor_count))
    if evolved_count:
        rows.append((EVOLVED, evolved_count))
    return DependencySpecimenLedger(tuple(rows))


def _bound(
    *,
    precursor_count: int,
    acquire_raises: bool = False,
    acquire_failure_ledger: DependencySpecimenLedger | None = None,
    acquire_base_exception: BaseException | None = None,
    evolve_raises: bool = False,
) -> tuple[BoundRedDualCapabilityScenario, _World]:
    scenario = red_dual_capability_scenario_specs()[precursor_count - 1]
    binding = RedDependencySpeciesBinding(PRECURSOR, EVOLVED)
    world = _World(_ledger(precursor_count, 0))

    def acquire() -> object:
        world.acquire_calls += 1
        if acquire_base_exception is not None:
            raise acquire_base_exception
        if acquire_raises:
            if acquire_failure_ledger is not None:
                world.ledger = acquire_failure_ledger
            raise RuntimeError("private acquisition failure")
        world.ledger = _ledger(precursor_count + 1, 0)
        return {"untrusted_after_ledger": _ledger(99, 0)}

    def evolve() -> object:
        world.evolve_calls += 1
        if evolve_raises:
            raise RuntimeError("private evolution failure")
        world.ledger = _ledger(precursor_count - 1, 1)
        return {"untrusted_after_ledger": _ledger(0, 99)}

    acquire_capability = BoundRedCapability(
        ProspectiveRedCapabilityBinding(
            GoalKind.ACQUIRE_SPECIES,
            RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE,
            RESET,
            "c" * 64,
            True,
        ),
        binding.binding_sha256,
        acquire,
    )
    evolve_capability = BoundRedCapability(
        ProspectiveRedCapabilityBinding(
            GoalKind.EVOLVE_SPECIES,
            RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
            RESET,
            "d" * 64,
            True,
        ),
        binding.binding_sha256,
        evolve,
    )
    return (
        build_red_dual_capability_scenario(
            scenario,
            binding,
            world.ledger,
            (acquire_capability, evolve_capability),
        ),
        world,
    )


def _model(
    weights: tuple[float, float, float, float] = (2.0, 0.0, -4.0, 4.0),
) -> DependencyRankerModel:
    return DependencyRankerModel(
        DEPENDENCY_RANKER_FEATURE_NAMES,
        weights,
        "e" * 64,
    )


def _prepare(
    bound: BoundRedDualCapabilityScenario,
    model: DependencyRankerModel,
) -> PreparedRedLivingDexOption:
    return prepare_red_living_dex_option(
        bound,
        model_sha256=model.model_sha256,
        context_identity_sha256=CONTEXT,
    )


def test_preparation_freezes_full_title_neutral_menu_before_scoring() -> None:
    bound, _world = _bound(precursor_count=1)
    model = _model()

    prepared = _prepare(bound, model)

    assert prepared.candidate_rows == bound.policy_rows()
    assert prepared.public_dict()["complete_menu_frozen_before_prediction"] is True
    assert prepared.public_dict()["model_predictions"] == 0
    public = json.dumps(prepared.public_dict(), sort_keys=True).lower()
    for forbidden in (PRECURSOR, EVOLVED, RESET, CONTEXT, "binding_sha256"):
        assert forbidden not in public


def test_preparation_rejects_retired_context_and_reset_state() -> None:
    bound, _world = _bound(precursor_count=1)
    model = _model()

    with pytest.raises(RedLivingDexOptionDevelopmentError, match="explicitly retired"):
        prepare_red_living_dex_option(
            bound,
            model_sha256=model.model_sha256,
            context_identity_sha256=CONTEXT,
            excluded_context_identity_sha256s=frozenset({CONTEXT}),
        )
    with pytest.raises(RedLivingDexOptionDevelopmentError, match="explicitly retired"):
        prepare_red_living_dex_option(
            bound,
            model_sha256=model.model_sha256,
            context_identity_sha256=CONTEXT,
            excluded_reset_state_sha256s=frozenset({RESET}),
        )


def test_scarce_state_model_selects_acquire_and_executes_only_that_skill() -> None:
    bound, world = _bound(precursor_count=1)
    model = _model()
    prepared = _prepare(bound, model)
    observer_calls = 0

    def observe() -> DependencySpecimenLedger:
        nonlocal observer_calls
        observer_calls += 1
        return world.ledger

    decision = score_red_living_dex_option(prepared, model)
    episode = execute_red_living_dex_option(
        decision,
        observe_after_ledger=observe,
    )

    assert decision.selected_kind is GoalKind.ACQUIRE_SPECIES
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0
    assert observer_calls == 1
    assert episode.status == "settled"
    assert episode.outcome.reward == 1
    assert episode.outcome.exact_selected_transition is True
    assert episode.public_dict()["independent_post_transition_observation"] is True
    with pytest.raises(RedLivingDexOptionDevelopmentError, match="already consumed"):
        score_red_living_dex_option(prepared, model)
    with pytest.raises(RedLivingDexOptionDevelopmentError, match="already executed"):
        execute_red_living_dex_option(
            decision,
            observe_after_ledger=lambda: world.ledger,
        )


def test_duplicate_ready_state_model_selects_evolve_and_preserves_living_pair() -> None:
    bound, world = _bound(precursor_count=2)
    model = _model()

    decision = score_red_living_dex_option(_prepare(bound, model), model)
    episode = execute_red_living_dex_option(
        decision,
        observe_after_ledger=lambda: world.ledger,
    )

    assert decision.selected_kind is GoalKind.EVOLVE_SPECIES
    assert world.acquire_calls == 0
    assert world.evolve_calls == 1
    assert episode.outcome.reward == 1
    assert episode.outcome.required_living_preserved is True
    assert episode.outcome.after_ledger == _ledger(1, 1)


def test_model_tie_is_deterministic_and_model_identity_must_match() -> None:
    bound, _world = _bound(precursor_count=1)
    tie_model = _model((0.0, 0.0, 0.0, 0.0))
    prepared = _prepare(bound, tie_model)

    decision = score_red_living_dex_option(prepared, tie_model)

    assert decision.selected_candidate_index == 0
    assert decision.selected_candidate_probability == 0.5
    mismatch = _model((1.0, 0.0, 0.0, 0.0))
    fresh = _prepare(bound, tie_model)
    with pytest.raises(RedLivingDexOptionDevelopmentError, match="model identity"):
        score_red_living_dex_option(fresh, mismatch)


def test_selected_skill_exception_is_observed_and_settled_without_fallback() -> None:
    bound, world = _bound(precursor_count=1, acquire_raises=True)
    model = _model()
    observer_calls = 0

    def observe() -> DependencySpecimenLedger:
        nonlocal observer_calls
        observer_calls += 1
        return world.ledger

    decision = score_red_living_dex_option(_prepare(bound, model), model)
    episode = execute_red_living_dex_option(decision, observe_after_ledger=observe)

    assert episode.status == "settled"
    assert episode.interruption_stage is None
    assert episode.outcome.reward == -1
    assert episode.outcome.exact_selected_transition is False
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0
    assert observer_calls == 1
    assert episode.public_dict()["independent_post_transition_observation"] is True
    encoded = json.dumps(episode.private_dict(), sort_keys=True)
    assert "private acquisition failure" not in encoded


@pytest.mark.parametrize(
    ("after_ledger", "expected_reward", "expected_exact"),
    (
        (None, -1, False),
        (_ledger(1, 1), -1, False),
        (_ledger(2, 0), 1, True),
    ),
    ids=("unchanged", "partial", "exact"),
)
def test_frozen_selection_observes_once_after_ordinary_execution_exception(
    after_ledger: DependencySpecimenLedger | None,
    expected_reward: int,
    expected_exact: bool,
) -> None:
    bound, world = _bound(
        precursor_count=1,
        acquire_raises=True,
        acquire_failure_ledger=after_ledger,
    )
    observer_calls = 0

    def observe() -> DependencySpecimenLedger:
        nonlocal observer_calls
        observer_calls += 1
        return world.ledger

    outcome, report = execute_red_living_dex_bound_selection(
        bound,
        0,
        observe_after_ledger=observe,
    )

    assert outcome.status == "settled"
    assert outcome.reward == expected_reward
    assert outcome.exact_selected_transition is expected_exact
    assert report is None
    assert observer_calls == 1
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0


def test_observer_failure_after_execution_exception_is_the_only_censor() -> None:
    bound, world = _bound(precursor_count=1, acquire_raises=True)
    model = _model()
    observer_calls = 0

    def observe() -> DependencySpecimenLedger:
        nonlocal observer_calls
        observer_calls += 1
        raise RuntimeError("private observer failure")

    decision = score_red_living_dex_option(_prepare(bound, model), model)
    episode = execute_red_living_dex_option(decision, observe_after_ledger=observe)

    assert episode.status == "interrupted"
    assert episode.interruption_stage == "independent_outcome_observation"
    assert episode.outcome.reward is None
    assert observer_calls == 1
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0


@pytest.mark.parametrize("acquire_raises", (False, True))
def test_malformed_observation_is_censored_once_without_a_report(
    acquire_raises: bool,
) -> None:
    bound, world = _bound(precursor_count=1, acquire_raises=acquire_raises)
    observer_calls = 0

    def observe() -> object:
        nonlocal observer_calls
        observer_calls += 1
        return {"not": "a specimen ledger"}

    outcome, report = execute_red_living_dex_bound_selection(
        bound,
        0,
        observe_after_ledger=observe,  # type: ignore[arg-type]
    )

    assert outcome.status == "interrupted"
    assert outcome.reward is None
    assert report is None
    assert observer_calls == 1
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0


def test_process_interruption_remains_visible_and_skips_observation() -> None:
    bound, world = _bound(
        precursor_count=1,
        acquire_base_exception=KeyboardInterrupt(),
    )
    observer_calls = 0

    def observe() -> DependencySpecimenLedger:
        nonlocal observer_calls
        observer_calls += 1
        return world.ledger

    with pytest.raises(KeyboardInterrupt):
        execute_red_living_dex_bound_selection(
            bound,
            0,
            observe_after_ledger=observe,
        )

    assert observer_calls == 0
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0


def test_observer_process_interruption_remains_visible() -> None:
    bound, world = _bound(precursor_count=1)

    with pytest.raises(KeyboardInterrupt):
        execute_red_living_dex_bound_selection(
            bound,
            0,
            observe_after_ledger=lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
        )

    assert world.acquire_calls == 1
    assert world.evolve_calls == 0


def test_observation_failure_is_censored_after_one_selected_execution() -> None:
    bound, world = _bound(precursor_count=1)
    model = _model()

    decision = score_red_living_dex_option(_prepare(bound, model), model)
    episode = execute_red_living_dex_option(
        decision,
        observe_after_ledger=lambda: (_ for _ in ()).throw(RuntimeError("private observer")),
    )

    assert episode.status == "interrupted"
    assert episode.interruption_stage == "independent_outcome_observation"
    assert episode.outcome.after_ledger is None
    assert world.acquire_calls == 1
    assert world.evolve_calls == 0


def test_outcome_uses_fresh_observer_not_selected_skill_return_value() -> None:
    bound, world = _bound(precursor_count=1)
    model = _model()

    decision = score_red_living_dex_option(_prepare(bound, model), model)
    episode = execute_red_living_dex_option(
        decision,
        observe_after_ledger=lambda: world.ledger,
    )

    assert episode.outcome.after_ledger == _ledger(2, 0)
    assert episode.outcome.after_ledger != _ledger(99, 0)


def test_forged_incomplete_preparation_and_public_identity_leak_fail() -> None:
    bound, _world = _bound(precursor_count=1)
    model = _model()
    prepared = _prepare(bound, model)

    with pytest.raises(RedLivingDexOptionDevelopmentError, match="complete frozen menu"):
        PreparedRedLivingDexOption(
            bound,
            model.model_sha256,
            CONTEXT,
            prepared.candidate_rows[:1],
            prepared.preparation_sha256,
        )

    decision = score_red_living_dex_option(prepared, model)
    encoded = json.dumps(decision.public_dict(), sort_keys=True).lower()
    for forbidden in (PRECURSOR, EVOLVED, RESET, CONTEXT, "candidate_scores"):
        assert forbidden not in encoded
