"""Synthetic recorder/replay integration, not actual Red training evidence."""

from dataclasses import replace

import pytest
from test_red_player_training import _episode
from test_registered_learning_bridge import observations

from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOutcomeStatus,
    fit_living_dex_option_value,
)
from pokemon_red_completion.living_dex_player_exploration import ECONOMY_EXPLORATION_POLICY_ID
from pokemon_red_completion.red_player_economy import ECONOMY_CONTEXT_EVENT, PlayerEconomySupply
from pokemon_red_completion.red_player_training import TRAINING_EVENT
from pokemon_red_completion.red_player_training_plan import (
    ECONOMY_TRAINING_PLAN_SCHEMA,
    RedPlayerTrainingPlan,
)
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE


def _setup(tmp_path, monkeypatch, *, cash_after=10500):
    _, before, _, policy = observations(tmp_path / "observations")
    before = replace(
        before,
        raw=replace(before.raw, player_money=10000, bag_items=((4, 10),)),
        capture_item_count=10,
        evidence=replace(
            before.evidence, resources=0.8, control=1.0, safety=1.0, team_readiness=1.0, storage=1.0
        ),
    )
    after = replace(before, raw=replace(before.raw, player_money=cash_after))
    pair = tuple(project_registered_observation(o, policy) for o in (before, after))
    supply = PlayerEconomySupply(20, 20, 2, 1200)

    def declare(store, plan):
        return RedPlayerTrainingPlan(
            {
                **plan.document,
                "schema": ECONOMY_TRAINING_PLAN_SCHEMA,
                "objective": REGISTERED_OBJECTIVE,
                "registration_binding_sha256": policy.sha256,
                "behavior_policy_id": ECONOMY_EXPLORATION_POLICY_ID,
                "maximum_actions": 30000,
                "maximum_frames": 3000000,
                "origin_state_sha256": "a" * 64,
                "origin_envelope_sha256": "b" * 64,
                "restore_profile_sha256": "c" * 64,
                "continuation_episode_id": "parent",
                "continuation_checkpoint_sha256": "d" * 64,
                **supply.plan_fields(),
            }
        )

    # Isolate recorder/replay behavior. Existing origin tests separately enforce
    # the private parent checkpoint; this synthetic fixture cannot be admitted live.
    monkeypatch.setattr(
        "pokemon_red_completion.red_player_training_dataset._require_continuation_origin",
        lambda *_: None,
    )
    run = tmp_path / "episode"
    run.mkdir()
    return run, dict(plan_transform=declare, registration_observations=pair, economy_supply=supply)


def test_economy_choice_records_replays_and_fits_only_measured_targets(tmp_path, monkeypatch):
    run, kwargs = _setup(tmp_path, monkeypatch)
    data = _episode(run, **kwargs, repeat_registered_choice=True)
    assert len(data.examples) == 2
    first, second = data.examples
    assert first.menu.context.economy_snapshot.cash == 10000
    assert second.menu.context.economy_snapshot.cash == 10500
    assert first.menu.context.target_cash == 12000
    assert first.outcome.economy.cash_delta == 500
    assert first.outcome.economy.useful_liquidity_gain == pytest.approx(500 / 12000)
    assert second.outcome.economy.cash_delta == 0
    fitted = fit_living_dex_option_value(data.examples, feature_version=4)
    assert fitted.model.economy_head.qualified_examples == 2


@pytest.mark.parametrize("status", [GoalDecisionOutcome.FAILED, GoalDecisionOutcome.INTERRUPTED])
def test_failure_and_interruption_preserve_cash_semantics(tmp_path, monkeypatch, status):
    run, kwargs = _setup(tmp_path, monkeypatch, cash_after=9500)
    row = _episode(run, **kwargs, status=status).examples[0]
    if status is GoalDecisionOutcome.INTERRUPTED:
        assert row.outcome.status is LivingDexOutcomeStatus.CENSORED
        assert row.outcome.economy is None
    else:
        assert row.outcome.economy.cash_delta == -500
        assert row.outcome.economy.cash_loss == pytest.approx(500 / 12000)


@pytest.mark.parametrize("field", ["budget", "cash", "before", "after", "question", "missing"])
def test_replay_rejects_altered_economy_evidence(tmp_path, monkeypatch, field):
    run, kwargs = _setup(tmp_path, monkeypatch)

    def corrupt(streams):
        context = next(
            e["payload"] for e in streams["events"] if e["kind"] == ECONOMY_CONTEXT_EVENT
        )
        outcome = next(e["payload"] for e in streams["events"] if e["kind"] == TRAINING_EVENT)
        if field == "budget":
            context["budget"]["target_cash"] += 1
        elif field == "cash":
            context["economy_before"]["cash"] += 1
        elif field == "before":
            outcome["before"]["semantic_observation"]["capture_item_count"] += 1
        elif field == "after":
            outcome["economy_after"]["cash"] += 1
        elif field == "question":
            context["question_sha256"] = "e" * 64
        else:
            streams["events"] = [e for e in streams["events"] if e["kind"] != ECONOMY_CONTEXT_EVENT]

    with pytest.raises(ValueError):
        _episode(run, **kwargs, mutate=corrupt)


def test_changed_cash_after_selection_stops_before_controller_input(tmp_path, monkeypatch):
    run, kwargs = _setup(tmp_path, monkeypatch)

    def alter(trajectory):
        trajectory.observe_training = lambda: kwargs["registration_observations"][1]

    with pytest.raises(ValueError, match="between selection and execution"):
        _episode(run, **kwargs, after_selection=alter)


def test_economy_plan_keeps_real_parent_and_version_gates(tmp_path, monkeypatch):
    import runpy

    from test_paired_red_bounded_player_script import SCRIPT

    from pokemon_red_completion.living_dex_player_exploration import RECOVERY_EXPLORATION_POLICY_ID
    from pokemon_red_completion.red_player_training_dataset import _require_continuation_origin
    from pokemon_red_completion.red_player_training_plan import REGISTERED_TRAINING_PLAN_SCHEMA

    run, kwargs = _setup(tmp_path, monkeypatch)
    store, plan, _, _ = _episode(run, **kwargs, return_inputs=True)
    with pytest.raises(ValueError, match="checkpoint differs"):
        _require_continuation_origin(store, plan)
    with pytest.raises(ValueError, match="fields differ"):
        RedPlayerTrainingPlan({**plan.document, "schema": REGISTERED_TRAINING_PLAN_SCHEMA})
    with pytest.raises(ValueError, match="behavior differs"):
        RedPlayerTrainingPlan(
            {**plan.document, "behavior_policy_id": RECOVERY_EXPLORATION_POLICY_ID}
        )
    module = runpy.run_path(str(SCRIPT))
    assert (
        module["_checkpoint_completion_dose"](
            {
                "metadata": {"player_training_plan": dict(plan.document)},
            }
        )
        is True
    )


def test_unknown_money_is_not_zero_or_a_training_example(tmp_path, monkeypatch):
    run, kwargs = _setup(tmp_path, monkeypatch)
    before, after = kwargs["registration_observations"]
    kwargs["registration_observations"] = (
        replace(before, raw=replace(before.raw, player_money=None)),
        after,
    )
    data = _episode(run, **kwargs)
    assert data.examples == ()
    assert data.excluded_nonexploratory == 1


@pytest.mark.parametrize("cash", [True, -1, 1000000, "100"])
def test_snapshot_numeric_bounds(cash):
    from pokemon_red_completion.red_player_economy import restore_snapshot

    with pytest.raises(ValueError):
        restore_snapshot(
            {"schema": "pokemon.core.resource-economy-snapshot.v1", "cash": cash, "inventory": []}
        )


def test_profile_bound_budget_and_unsupported_shop():
    from types import SimpleNamespace

    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_player_economy import supply_from_profile

    profile = SimpleNamespace(
        manager_config=SimpleNamespace(desired_capture_items=20),
        providers=(
            SimpleNamespace(
                kind=GoalKind.RESUPPLY,
                parameters={
                    "affordable_ball_purchase": True,
                    "purchases": ({"item_id": 2, "quantity": 10, "unit_price": 1200},),
                },
            ),
        ),
    )
    assert supply_from_profile(profile) == PlayerEconomySupply(20, 10, 2, 1200)
    profile.providers[0].parameters["affordable_ball_purchase"] = False
    with pytest.raises(ValueError, match="bounded capture purchase"):
        supply_from_profile(profile)


def test_native_update_publishes_and_reopens_economy_model(tmp_path, monkeypatch):
    from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
    from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
    from pokemon_red_completion.red_player_training_fit import (
        RedPlayerEpisodeInput,
        fit_red_player_update,
    )

    run, kwargs = _setup(tmp_path, monkeypatch)
    store, plan, behavior, completed = _episode(
        run,
        **kwargs,
        repeat_registered_choice=True,
        return_inputs=True,
    )
    prior = LivingDexGoalModelRecord(behavior, "a" * 64, "b" * 40, "c" * 64, 1, 1)
    request = RedPlayerEpisodeInput(plan, "goal-episode-1", completed.manifest_sha256, prior)
    monkeypatch.setattr(
        "pokemon_red_completion.red_player_training_fit.load_living_dex_authenticated_causal_examples",
        lambda _: pytest.fail("registered fitting opened the historical corpus"),
    )
    result = fit_red_player_update(
        store,
        prior=prior,
        episodes=(request,),
        source_commit="b" * 40,
        source_bundle_sha256="c" * 64,
        registered_objective=True,
    )
    assert result["new_settled_examples"] == 2
    sha = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rpr-model-{sha}", expected_kind="red_player_model")
    loaded = load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256=sha)
    assert loaded.objective == REGISTERED_OBJECTIVE
    assert loaded.model.economy_head.qualified_examples == 2


def test_economy_bootstrap_preserves_registered_corpus_and_predictions(tmp_path):
    from test_living_dex_option_value import _example, _settled
    from test_red_living_dex_causal_adapter import _store_and_registry

    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_player_model import (
        RedPlayerModelRecord,
        load_player_goal_model_record_bytes,
    )
    from pokemon_red_completion.red_player_training_fit import bootstrap_red_player_economy

    store, _ = _store_and_registry(tmp_path)
    rows = tuple(
        _example(
            i,
            selected=i,
            outcome=_settled(
                success=True,
                completion=0.1,
                unlock=0,
                action_cost=0.2,
            ),
        )
        for i in range(2)
    )
    model = fit_living_dex_option_value(rows, feature_version=3).model
    corpus = {"examples": [row.public_dict() for row in rows]}
    sha = canonical_sha256(corpus)
    store.publish_sealed_record(
        f"rp-corpus-{sha}", kind="red_player_training_corpus", record=corpus
    )
    prior = RedPlayerModelRecord(
        model,
        "a" * 64,
        "b" * 40,
        "c" * 64,
        sha,
        "d" * 64,
        tuple(sorted(canonical_sha256(row.public_dict()) for row in rows)),
        REGISTERED_OBJECTIVE,
    )
    result = bootstrap_red_player_economy(
        store, prior=prior, source_commit="b" * 40, source_bundle_sha256="c" * 64
    )
    assert result["new_examples"] == result["fits"] == result["controller_actions"] == 0
    assert result["economy_effect_learned"] is False
    new_sha = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rpr-model-{new_sha}", expected_kind="red_player_model")
    loaded = load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256=new_sha)
    assert loaded.corpus_sha256 == prior.corpus_sha256
    assert loaded.retained_example_sha256 == prior.retained_example_sha256
    assert loaded.objective == REGISTERED_OBJECTIVE
    assert loaded.model.feature_version == 4 and loaded.model.economy_head is None
    for row in rows:
        for candidate in row.menu.candidates:
            assert loaded.model.predict_candidate(row.menu.context, candidate) == (
                model.predict_candidate(row.menu.context, candidate)
            )
    with pytest.raises(ValueError, match="registered objective"):
        bootstrap_red_player_economy(
            store,
            prior=replace(prior, objective=None),
            source_commit="b" * 40,
            source_bundle_sha256="c" * 64,
        )
