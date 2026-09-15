from types import SimpleNamespace

import pytest
from test_red_measured_terminal_checkpoint import _measured_checkpoint_case, _write_measured_episode

from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.red_correlated_reset import (
    claim_correlated_reset,
    declare_correlated_reset,
    require_correlated_claim,
    require_correlated_parent,
    reset_record_id,
)
from pokemon_red_completion.red_player_checkpoint import (
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
)
from pokemon_red_completion.red_player_training_plan import (
    CORRELATED_REGISTERED_TRAINING_PLAN_SCHEMA,
    RedPlayerTrainingPlan,
)
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE


@pytest.fixture
def case(tmp_path, monkeypatch):
    store, _, parent, document, segment, _, _ = _measured_checkpoint_case(tmp_path, monkeypatch)
    _write_measured_episode(store, document, segment)
    summary = publish_red_player_checkpoint(store, document)
    opened = open_red_player_checkpoint(
        store,
        episode_id=document["episode_id"],
        expected_record_sha256=summary["record_sha256"],
        original_parent=parent.capture,
        expected_profile_sha256=document["profile_sha256"],
        expected_rom_sha256=document["rom_sha256"],
        expected_context_origin="training",
    )
    kwargs = dict(
        parent_episode_id=document["episode_id"],
        parent_checkpoint_sha256=summary["record_sha256"],
        reset_id="practice-one",
        episode_id="new-player-episode",
        seed=123,
        state_sha256=opened.capture.state_sha256,
        envelope_sha256=opened.capture.envelope_sha256,
        restore_profile_sha256=document["profile_sha256"],
        execution_profile_sha256="c" * 64,
        model_sha256=document["model_sha256"],
        source_commit="d" * 40,
        source_bundle_sha256="e" * 64,
        feature_version=3,
    )
    return store, document, kwargs


def registered(store, kwargs):
    plan = declare_correlated_reset(store, **kwargs)
    return RedPlayerTrainingPlan(
        {
            **plan.document,
            "schema": CORRELATED_REGISTERED_TRAINING_PLAN_SCHEMA,
            "objective": REGISTERED_OBJECTIVE,
            "registration_binding_sha256": "f" * 64,
        }
    )


def test_reset_preserves_lower_trust_parent_and_admits_only_new_episode(case):
    store, document, kwargs = case
    original = store.open_episode(document["episode_id"]).manifest_sha256
    plan = registered(store, kwargs)
    assert plan.maximum_actions == 30_000 and plan.maximum_frames == 3_000_000
    assert plan.document["decision_limit"] == 1
    assert "catalog_source_commit" not in plan.document
    assert plan.document["catalog_admitted"] is False
    assert plan.document["independent_root"] is False
    assert plan.document["root_lineage_id"] == "measured-root"
    claim_correlated_reset(store, plan)
    require_correlated_claim(store, plan)
    assert store.open_episode(document["episode_id"]).manifest_sha256 == original
    assert (
        store.open_episode(document["episode_id"]).read_header()["metadata"]["training_eligible"]
        is False
    )


@pytest.mark.parametrize(
    "key",
    [
        "parent_checkpoint_sha256",
        "state_sha256",
        "envelope_sha256",
        "restore_profile_sha256",
        "model_sha256",
    ],
)
def test_reset_rejects_substituted_parent_identity(case, key):
    store, _, kwargs = case
    with pytest.raises(ValueError, match="parent"):
        declare_correlated_reset(store, **{**kwargs, key: "0" * 64})


@pytest.mark.parametrize(
    "key,value",
    [
        ("decision_limit", 2),
        ("independent_root", True),
        ("catalog_admitted", True),
        ("independent_evaluation", True),
        ("episode_retry_after_input", True),
        ("parent_evidence_tier", "native-action-trace"),
        ("maximum_actions", 30001),
    ],
)
def test_reset_rejects_scope_widening(case, key, value):
    store, _, kwargs = case
    plan = registered(store, kwargs)
    with pytest.raises(ValueError):
        RedPlayerTrainingPlan({**plan.document, key: value})


@pytest.mark.parametrize(
    "key,value",
    [
        ("root_lineage_id", "fresh-root"),
        ("parent_manifest_sha256", "0" * 64),
        ("origin_state_sha256", "0" * 64),
        ("origin_envelope_sha256", "0" * 64),
        ("context_catalog_sha256", "0" * 64),
    ],
)
def test_fit_rechecks_parent_and_reset_context(case, key, value):
    store, _, kwargs = case
    plan = registered(store, kwargs)
    with pytest.raises(ValueError, match="provenance"):
        require_correlated_parent(store, RedPlayerTrainingPlan({**plan.document, key: value}))


def test_same_reset_cannot_be_reissued_after_claim_or_changed_source(case):
    store, _, kwargs = case
    plan = registered(store, kwargs)
    claim_correlated_reset(store, plan)
    with pytest.raises(PrivateArtifactError, match="present"):
        claim_correlated_reset(store, plan)
    for changes in ({}, {"seed": 124}, {"episode_id": "replacement"}, {"source_commit": "0" * 40}):
        with pytest.raises(ValueError, match="consumed"):
            declare_correlated_reset(store, **{**kwargs, **changes})


def test_partial_claim_remains_consumed(case):
    store, _, kwargs = case
    plan = registered(store, kwargs)
    with store.begin_episode(reset_record_id(plan)):
        pass  # interrupted before the declaration or any gameplay
    with pytest.raises(ValueError, match="consumed"):
        declare_correlated_reset(store, **kwargs)


def test_fit_rejects_missing_or_changed_claim(case):
    store, _, kwargs = case
    plan = registered(store, kwargs)
    with pytest.raises(PrivateArtifactError):
        require_correlated_claim(store, plan)
    claim_correlated_reset(store, plan)
    with pytest.raises(ValueError, match="claim differs"):
        require_correlated_claim(store, RedPlayerTrainingPlan({**plan.document, "seed": 124}))


def test_gate_failure_claims_before_preflight_and_never_runs_again(case, monkeypatch):
    import run_paired_red_bounded_player as runner

    store, _, kwargs = case
    plan = registered(store, kwargs)
    readiness = SimpleNamespace(training_plan=plan, private_root=store)
    calls = []

    def failed(_):
        require_correlated_claim(store, plan)
        calls.append("preflight")
        raise ValueError("two_family_gate")

    monkeypatch.setattr(runner, "_run_prepared_impl", failed)
    with pytest.raises(ValueError, match="two_family_gate"):
        runner._run_prepared(readiness)
    terminal = store.find_sealed_record(reset_record_id(plan) + "-result").read()
    assert terminal["status"] == "failed"
    with pytest.raises(PrivateArtifactError):
        runner._run_prepared(readiness)
    assert calls == ["preflight"]


def test_observe_only_preflight_never_samples_or_executes():
    from test_red_bounded_player import _composition_observation, _Meter

    from pokemon_red_completion.red_bounded_player import preflight_red_bounded_player

    def forbidden(*_):
        pytest.fail("observation-only gate sampled an authority")

    authority = SimpleNamespace(select=forbidden)
    result = preflight_red_bounded_player(
        observe=_composition_observation,
        budget_meter=_Meter({"actions": 0, "frames": 0}),
        assignment_id="reset-gate",
        authorities=(("learner", authority), ("teacher", authority)),
        observe_only=True,
    )
    assert not result.choices
    assert len(result.available_goal_kinds) == 2


@pytest.mark.parametrize("status", ["succeeded", "failed", "interrupted"])
def test_correlated_economy_recorder_replay_retains_outcomes(tmp_path, monkeypatch, status):
    from test_red_player_economy import _setup
    from test_red_player_training import _episode

    from pokemon_red_completion.goal_manager import GoalDecisionOutcome
    from pokemon_red_completion.red_player_training_plan import (
        CORRELATED_ECONOMY_TRAINING_PLAN_SCHEMA,
    )

    run, kwargs = _setup(tmp_path, monkeypatch, cash_after=9500)
    old = kwargs["plan_transform"]

    def declare(store, plan):
        document = dict(old(store, plan).document)
        document.pop("catalog_source_commit")
        document.update(
            schema=CORRELATED_ECONOMY_TRAINING_PLAN_SCHEMA,
            reset_id="reset-test",
            decision_limit=1,
            parent_manifest_sha256="e" * 64,
            parent_evidence_tier="registered-measured-terminal",
            independent_root=False,
            catalog_admitted=False,
        )
        return RedPlayerTrainingPlan(document)

    kwargs["plan_transform"] = declare
    # Isolate native recorder/replay here; the real-store tests above exercise
    # parent and exclusive claim authentication without this stub.
    checked = []
    monkeypatch.setattr(
        "pokemon_red_completion.red_correlated_reset.require_correlated_claim",
        lambda *args: checked.append(args[1].document["schema"]),
    )
    result = _episode(run, **kwargs, status=GoalDecisionOutcome(status))
    assert checked == [CORRELATED_ECONOMY_TRAINING_PLAN_SCHEMA]
    assert len(result.examples) == 1
    outcome = result.examples[0].outcome
    if status == "interrupted":
        assert outcome.economy is None and outcome.status.value == "censored"
    else:
        assert outcome.economy.cash_delta == -500
        assert outcome.action_cost > 0 and outcome.frame_cost > 0


def test_intermediate_plan_is_never_fit_eligible(case):
    store, _, kwargs = case
    with pytest.raises(ValueError, match="unregistered"):
        require_correlated_claim(store, declare_correlated_reset(store, **kwargs))


def test_process_interruption_retains_consumed_reset(case, monkeypatch):
    import run_paired_red_bounded_player as runner

    store, _, kwargs = case
    plan = registered(store, kwargs)

    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run_prepared_impl", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner._run_prepared(SimpleNamespace(training_plan=plan, private_root=store))
    assert (
        store.find_sealed_record(reset_record_id(plan) + "-result").read()["status"]
        == "interrupted"
    )
    with pytest.raises(ValueError, match="consumed"):
        declare_correlated_reset(store, **kwargs)


def test_gate_failure_retains_typed_family_reasons(case, monkeypatch):
    import run_paired_red_bounded_player as runner

    from pokemon_red_completion.goal_manager import GoalUnavailableReason
    from pokemon_red_completion.red_acquisition import RedAcquisitionKind
    from pokemon_red_completion.red_full_pokedex_goal_proposal import (
        RedFullPokedexFamilyDiagnostic,
        RedFullPokedexFamilyReason,
        RedFullPokedexGoalProposalError,
    )

    store, _, kwargs = case
    plan = registered(store, kwargs)
    error = RedFullPokedexGoalProposalError(
        "two families unavailable",
        family_diagnostics=(
            RedFullPokedexFamilyDiagnostic(
                RedAcquisitionKind.WILD,
                RedFullPokedexFamilyReason.ROUTER_BINDING_UNAVAILABLE,
                (GoalUnavailableReason.MISSING_CAPABILITY,),
            ),
            RedFullPokedexFamilyDiagnostic(
                RedAcquisitionKind.EVOLUTION, RedFullPokedexFamilyReason.READY
            ),
        ),
    )

    def fail(_):
        raise error

    monkeypatch.setattr(runner, "_run_prepared_impl", fail)
    with pytest.raises(RedFullPokedexGoalProposalError):
        runner._run_prepared(SimpleNamespace(training_plan=plan, private_root=store))
    terminal = store.find_sealed_record(reset_record_id(plan) + "-result").read()
    assert terminal["family_diagnostics"] == error.public_family_diagnostics()
