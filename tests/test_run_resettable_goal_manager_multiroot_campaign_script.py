from __future__ import annotations

import runpy
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_resettable_goal_manager_multiroot_campaign.py"),
    run_name="resettable_goal_manager_multiroot_campaign_script_test",
)


def _readiness():  # type: ignore[no-untyped-def]
    base = SimpleNamespace(
        source=SimpleNamespace(git_commit="a" * 40),
        source_bundle_sha256="b" * 64,
        runtime=SimpleNamespace(sha256="c" * 64),
        numpy_runtime_sha256="d" * 64,
        skill_manifest_sha256="e" * 64,
        context_plan_sha256="f" * 64,
    )
    paired = SimpleNamespace(
        development=base,
        candidate_model_canonical_sha256="1" * 64,
        prior_campaign_sha256=("4" * 64, "5" * 64),
    )
    return SimpleNamespace(paired=paired, runner_sha256="2" * 64)


def _plan() -> dict[str, object]:
    specs = (
        ("train", "acquire_species"),
        ("train", "manage_storage"),
        ("train", "develop_team"),
        ("train", "restore_team"),
        ("development", "acquire_species"),
        ("development", "develop_team"),
    )
    roots = []
    for index, (partition, focus) in enumerate(specs):
        state = f"{100 + index:064x}"
        envelope = f"{200 + index:064x}"
        roots.append(
            {
                "partition": partition,
                "root_consumption_sha256": root_consumption_sha256(
                    state_sha256=state,
                    envelope_sha256=envelope,
                ),
                "root": {
                    "entry_index": index,
                    "focus_kind": focus,
                    "state_sha256": state,
                    "envelope_sha256": envelope,
                },
            }
        )
    trials = [
        {
            "maximum_decisions": 1,
            "partition": "train" if root_index < 4 else "development",
            "root_index": root_index,
            "seed": 30_000 + root_index * 100 + offset,
            "trial_index": root_index * 2 + offset,
        }
        for root_index in range(6)
        for offset in range(2)
    ]
    identity = {
        "base_model_canonical_sha256": "1" * 64,
        "context_plan_sha256": "f" * 64,
        "numpy_runtime_sha256": "d" * 64,
        "outcome_objective": SCRIPT["development"].goal_manager_development_outcome_objective(),
        "private_root_identity_sha256": "3" * 64,
        "prior_campaign_sha256": ["4" * 64, "5" * 64],
        "roots": roots,
        "runner_sha256": "2" * 64,
        "runtime_sha256": "c" * 64,
        "schema": SCRIPT["CAMPAIGN_SCHEMA"],
        "skill_manifest_sha256": "e" * 64,
        "source_bundle_sha256": "b" * 64,
        "source_commit": "a" * 40,
        "trials": trials,
    }
    campaign_id = canonical_sha256(identity)
    full_trials = [
        {
            **trial,
            "episode_id": f"red-multiroot-{campaign_id[:32]}-{trial['trial_index']:02d}",
            "trial_claim_sha256": canonical_sha256(
                {
                    "campaign_id": campaign_id,
                    "schema": "pokemon.red.resettable-goal-manager-trial-claim.v1",
                    "trial_index": trial["trial_index"],
                }
            ),
        }
        for trial in trials
    ]
    return {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": "pokemon.red.resettable-goal-manager-campaign-consumption.v1",
            }
        ),
        "trials": full_trials,
    }


def _rebind_plan_identity(plan: dict[str, object]) -> None:
    trials = plan["trials"]
    assert isinstance(trials, list)
    stripped_trials = []
    for trial in trials:
        assert isinstance(trial, dict)
        stripped = dict(trial)
        stripped.pop("episode_id")
        stripped.pop("trial_claim_sha256")
        stripped_trials.append(stripped)
    identity = dict(plan)
    identity.pop("campaign_id")
    identity.pop("campaign_consumption_sha256")
    identity["trials"] = stripped_trials
    campaign_id = canonical_sha256(identity)
    plan["campaign_id"] = campaign_id
    plan["campaign_consumption_sha256"] = canonical_sha256(
        {
            "campaign_id": campaign_id,
            "schema": "pokemon.red.resettable-goal-manager-campaign-consumption.v1",
        }
    )
    for trial in trials:
        assert isinstance(trial, dict)
        trial_index = trial["trial_index"]
        assert isinstance(trial_index, int)
        trial["episode_id"] = f"red-multiroot-{campaign_id[:32]}-{trial_index:02d}"
        trial["trial_claim_sha256"] = canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": "pokemon.red.resettable-goal-manager-trial-claim.v1",
                "trial_index": trial_index,
            }
        )


def test_validates_exact_four_by_two_plus_two_by_two_layout() -> None:
    SCRIPT["_validate_plan"](
        _readiness(),
        _plan(),
        private_root_identity="3" * 64,
    )


def test_rejects_development_root_relabelled_as_train() -> None:
    plan = deepcopy(_plan())
    plan["roots"][4]["partition"] = "train"  # type: ignore[index]

    with pytest.raises(SCRIPT["ResettableMultirootRunError"], match="campaign_layout"):
        SCRIPT["_validate_plan"](
            _readiness(),
            plan,
            private_root_identity="3" * 64,
        )


def test_rejects_duplicate_physical_root_across_train_and_development() -> None:
    plan = deepcopy(_plan())
    roots = plan["roots"]
    assert isinstance(roots, list)
    train = roots[0]
    development = roots[4]
    assert isinstance(train, dict)
    assert isinstance(development, dict)
    train_root = train["root"]
    development_root = development["root"]
    assert isinstance(train_root, dict)
    assert isinstance(development_root, dict)
    development_root["state_sha256"] = train_root["state_sha256"]
    development_root["envelope_sha256"] = train_root["envelope_sha256"]
    development["root_consumption_sha256"] = train["root_consumption_sha256"]
    _rebind_plan_identity(plan)

    with pytest.raises(SCRIPT["ResettableMultirootRunError"], match="campaign_layout"):
        SCRIPT["_validate_plan"](
            _readiness(),
            plan,
            private_root_identity="3" * 64,
        )


def test_rejects_more_than_one_decision_per_reset() -> None:
    plan = deepcopy(_plan())
    plan["trials"][0]["maximum_decisions"] = 2  # type: ignore[index]

    with pytest.raises(SCRIPT["ResettableMultirootRunError"], match="campaign_layout"):
        SCRIPT["_validate_plan"](
            _readiness(),
            plan,
            private_root_identity="3" * 64,
        )


def test_public_runner_does_not_expose_train_or_development_label_admission() -> None:
    choices = SCRIPT["_parser"]()._option_string_actions["--mode"].choices

    assert tuple(choices) == ("freeze", "preflight", "execute", "resume")


def test_multiroot_readiness_opts_into_historical_context_plan_exclusions() -> None:
    build = SCRIPT["_paired_readiness_args"]
    values = {
        name: name
        for name in (
            "context_plan",
            "context_catalog",
            "base_model",
            "base_fit_summary",
            "candidate_model",
            "candidate_fit_summary",
            "fit_result_receipt",
            "prior_campaign",
            "expected_prior_campaign_sha256",
            "expected_fit_result_receipt_sha256",
            "expected_source_commit",
            "expected_source_bundle_sha256",
            "expected_paired_runner_sha256",
            "expected_development_runner_sha256",
            "expected_runtime_sha256",
            "expected_numpy_runtime_sha256",
            "expected_skill_manifest_sha256",
            "expected_context_plan_sha256",
            "rom",
        )
    }

    paired_args = build(SimpleNamespace(**values))

    assert paired_args.allow_historical_context_plan is True


def test_prior_root_exclusion_survives_lineage_rollover() -> None:
    prior = {
        "roots": [
            {
                "root_lineage_id": "red-goal-root-" + "1" * 64,
                "state_sha256": "2" * 64,
                "envelope_sha256": "3" * 64,
            }
        ]
    }

    lineages, physical = SCRIPT["_prior_root_identities"]((prior,))

    assert "red-goal-root-" + "1" * 64 in lineages
    assert ("2" * 64, "3" * 64) in physical


def test_pre_writer_failure_does_not_claim_a_retained_terminal() -> None:
    trial = _plan()["trials"][0]  # type: ignore[index]

    absent = SCRIPT["_failure_row"](
        trial,
        artifact_state="absent",
        error=SCRIPT["ResettableMultirootRunError"]("root_drift_after_claim"),
    )
    retained = SCRIPT["_failure_row"](
        trial,
        artifact_state="failed",
        error=SCRIPT["ResettableMultirootRunError"]("development_runtime"),
    )

    assert absent["status"] == "consumed_without_durable_failure_terminal"
    assert retained["status"] == "failed_terminal_retained"


def test_campaign_terminal_identity_is_distinct_and_plan_bound() -> None:
    first = SimpleNamespace(plan_sha256="6" * 64)
    second = SimpleNamespace(plan_sha256="7" * 64)

    first_identity = SCRIPT["_campaign_terminal_identity"](first)
    second_identity = SCRIPT["_campaign_terminal_identity"](second)

    assert first_identity != second_identity
    assert first_identity != _plan()["campaign_consumption_sha256"]


def test_campaign_terminal_authenticates_exact_execution(monkeypatch) -> None:
    ready = _readiness()
    qualified = SimpleNamespace(plan_sha256="6" * 64)
    expected_identity = SCRIPT["_campaign_execution_identity"](ready, qualified)
    expected_terminal = SCRIPT["_campaign_terminal_identity"](qualified)

    monkeypatch.setitem(
        SCRIPT["_require_campaign_terminal"].__globals__,
        "read_root_claim",
        lambda registry, identity: {
            "execution_identity_sha256": expected_identity,
            "runner_sha256": ready.runner_sha256,
            "schema": "pokemon.red.goal-manager-root-claim.v1",
            "source_commit": ready.paired.development.source.git_commit,
            "root_consumption_sha256": identity,
        },
    )

    SCRIPT["_require_campaign_terminal"](ready, qualified, Path("registry"))

    monkeypatch.setitem(
        SCRIPT["_require_campaign_terminal"].__globals__,
        "read_root_claim",
        lambda registry, identity: {
            "execution_identity_sha256": "8" * 64,
            "runner_sha256": ready.runner_sha256,
            "source_commit": ready.paired.development.source.git_commit,
            "root_consumption_sha256": expected_terminal,
        },
    )
    with pytest.raises(
        SCRIPT["ResettableMultirootRunError"],
        match="campaign_terminal_authentication",
    ):
        SCRIPT["_require_campaign_terminal"](ready, qualified, Path("registry"))


def test_resume_never_retries_existing_cells_and_closes_campaign(monkeypatch) -> None:
    ready = _readiness()
    plan = _plan()

    class _Session:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return False

        def inspect_episode(self, episode_id: str):  # type: ignore[no-untyped-def]
            return SimpleNamespace(status="complete")

        def recover_interrupted_episode(self, episode_id: str):  # type: ignore[no-untyped-def]
            pytest.fail("a complete episode was recovered")

    qualified = SimpleNamespace(
        plan=plan,
        plan_sha256="6" * 64,
        store=SimpleNamespace(collection_session=lambda campaign_id: _Session()),
    )
    writes: list[dict[str, object]] = []
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("registry"))
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda registry, exclusive: nullcontext(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda registry, identity: True)
    monkeypatch.setitem(globals_, "_require_consumption_claims", lambda *args: None)
    monkeypatch.setitem(globals_, "_require_trial_claims", lambda *args: None)
    monkeypatch.setitem(
        globals_,
        "_execute_trial",
        lambda *args, **kwargs: pytest.fail("an existing trial was retried"),
    )
    monkeypatch.setitem(
        globals_,
        "write_root_claim",
        lambda registry, **payload: writes.append(payload),
    )

    result = SCRIPT["_execute"](ready, qualified, resume=True)

    assert result["complete_trials"] == 12
    assert result["failed_trials"] == 0
    assert {row["status"] for row in result["trials"]} == {"existing_terminal_not_retried"}
    assert len(writes) == 1
    assert writes[0]["root_consumption_sha256"] == SCRIPT["_campaign_terminal_identity"](qualified)


def test_overlapping_resume_cannot_observe_or_close_active_campaign(monkeypatch) -> None:
    ready = _readiness()
    qualified = SimpleNamespace(
        plan=_plan(),
        plan_sha256="6" * 64,
        store=SimpleNamespace(
            collection_session=lambda campaign_id: (_ for _ in ()).throw(
                RuntimeError("collection is already active")
            )
        ),
    )
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        lambda: pytest.fail("registry opened before campaign lock"),
    )
    monkeypatch.setitem(
        globals_,
        "write_root_claim",
        lambda *args, **kwargs: pytest.fail("active campaign was closed"),
    )

    with pytest.raises(RuntimeError, match="collection is already active"):
        SCRIPT["_execute"](ready, qualified, resume=True)


def test_resume_recovers_partial_before_campaign_terminal(monkeypatch) -> None:
    ready = _readiness()
    plan = _plan()
    trials = plan["trials"]
    assert isinstance(trials, list)
    states = {
        trial["episode_id"]: "partial" if index == 0 else "complete"
        for index, trial in enumerate(trials)
        if isinstance(trial, dict)
    }

    class _Session:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return False

        def inspect_episode(self, episode_id: str):  # type: ignore[no-untyped-def]
            return SimpleNamespace(status=states[episode_id])

        def recover_interrupted_episode(self, episode_id: str):  # type: ignore[no-untyped-def]
            states[episode_id] = "interrupted"
            return SimpleNamespace(status="interrupted")

    qualified = SimpleNamespace(
        plan=plan,
        plan_sha256="6" * 64,
        store=SimpleNamespace(collection_session=lambda campaign_id: _Session()),
    )
    writes: list[dict[str, object]] = []
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("registry"))
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda registry, exclusive: nullcontext(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda registry, identity: True)
    monkeypatch.setitem(globals_, "_require_consumption_claims", lambda *args: None)
    monkeypatch.setitem(globals_, "_require_trial_claims", lambda *args: None)
    monkeypatch.setitem(
        globals_,
        "_execute_trial",
        lambda *args, **kwargs: pytest.fail("an existing trial was retried"),
    )
    monkeypatch.setitem(
        globals_,
        "write_root_claim",
        lambda registry, **payload: writes.append(payload),
    )

    result = SCRIPT["_execute"](ready, qualified, resume=True)

    first = trials[0]
    assert isinstance(first, dict)
    assert states[first["episode_id"]] == "interrupted"
    assert result["complete_trials"] == 11
    assert result["failed_trials"] == 1
    assert len(writes) == 1
