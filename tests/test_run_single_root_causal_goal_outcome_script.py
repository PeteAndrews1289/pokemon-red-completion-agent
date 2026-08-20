from __future__ import annotations

import json
import runpy
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_single_root_causal_goal_outcome.py"),
    run_name="single_root_causal_goal_outcome_script_test",
)


def _readiness() -> SimpleNamespace:
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
        prior_campaigns=(),
    )
    return SimpleNamespace(
        paired=paired,
        runner_sha256="2" * 64,
        multiroot_runner_sha256="9" * 64,
    )


def _plan() -> dict[str, object]:
    state = "6" * 64
    envelope = "7" * 64
    root = {
        "partition": "train",
        "root_consumption_sha256": root_consumption_sha256(
            state_sha256=state,
            envelope_sha256=envelope,
        ),
        "root": {
            "entry_index": 3,
            "focus_kind": GoalKind.ACQUIRE_SPECIES.value,
            "state_sha256": state,
            "envelope_sha256": envelope,
        },
    }
    trial = {
        "maximum_decisions": 1,
        "partition": "train",
        "root_index": 0,
        "seed": SCRIPT["TRIAL_SEED"],
        "trial_index": 0,
    }
    identity = {
        "base_model_canonical_sha256": "1" * 64,
        "context_plan_sha256": "f" * 64,
        "lane_consumption_sha256": SCRIPT["LANE_CONSUMPTION_SHA256"],
        "numpy_runtime_sha256": "d" * 64,
        "outcome_objective": SCRIPT["development"].goal_manager_development_outcome_objective(),
        "private_root_identity_sha256": "3" * 64,
        "prior_campaign_sha256": ["4" * 64, "5" * 64],
        "roots": [root],
        "runner_sha256": "2" * 64,
        "runtime_sha256": "c" * 64,
        "schema": SCRIPT["CAMPAIGN_SCHEMA"],
        "skill_manifest_sha256": "e" * 64,
        "source_bundle_sha256": "b" * 64,
        "source_commit": "a" * 40,
        "trials": [trial],
    }
    campaign_id = canonical_sha256(identity)
    return {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": SCRIPT["CAMPAIGN_CONSUMPTION_SCHEMA"],
            }
        ),
        "trials": [
            {
                **trial,
                "episode_id": f"red-causal-goal-{campaign_id[:32]}-00",
                "trial_claim_sha256": canonical_sha256(
                    {
                        "campaign_id": campaign_id,
                        "schema": SCRIPT["TRIAL_CLAIM_SCHEMA"],
                        "trial_index": 0,
                    }
                ),
            }
        ],
    }


def test_public_lane_is_one_freeze_preflight_execute_admit_sequence() -> None:
    choices = SCRIPT["_parser"]()._option_string_actions["--mode"].choices

    assert tuple(choices) == ("freeze", "preflight", "execute", "admit")


def test_validates_one_train_decision_from_an_acquisition_capable_root() -> None:
    SCRIPT["_validate_plan"](
        _readiness(),
        _plan(),
        private_root_identity="3" * 64,
    )


@pytest.mark.parametrize(
    ("mutation", "value"),
    (
        ("partition", "development"),
        ("focus_kind", GoalKind.DEVELOP_TEAM.value),
        ("maximum_decisions", 2),
    ),
)
def test_rejects_any_non_train_non_acquisition_or_multi_decision_layout(
    mutation: str,
    value: object,
) -> None:
    plan = deepcopy(_plan())
    roots = plan["roots"]
    trials = plan["trials"]
    assert isinstance(roots, list) and isinstance(roots[0], dict)
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    if mutation == "partition":
        roots[0]["partition"] = value
    elif mutation == "focus_kind":
        root = roots[0]["root"]
        assert isinstance(root, dict)
        root["focus_kind"] = value
    else:
        trials[0]["maximum_decisions"] = value

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="campaign_layout"):
        SCRIPT["_validate_plan"](
            _readiness(),
            plan,
            private_root_identity="3" * 64,
        )


def test_generic_inventory_inspects_only_first_open_unused_train_acquisition_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = tuple(SimpleNamespace(slot_id=f"slot-{index}") for index in range(5))
    prior_lineage = "red-goal-root-" + "8" * 64
    assignments = (
        SimpleNamespace(
            partition="validation",
            focus_kind=GoalKind.ACQUIRE_SPECIES,
            root_lineage_id="red-goal-root-" + "0" * 64,
            assignment_id="0" * 64,
        ),
        SimpleNamespace(
            partition="train",
            focus_kind=GoalKind.MANAGE_STORAGE,
            root_lineage_id="red-goal-root-" + "1" * 64,
            assignment_id="1" * 64,
        ),
        SimpleNamespace(
            partition="train",
            focus_kind=GoalKind.ACQUIRE_SPECIES,
            root_lineage_id=prior_lineage,
            assignment_id="2" * 64,
        ),
        SimpleNamespace(
            partition="train",
            focus_kind=GoalKind.ACQUIRE_SPECIES,
            root_lineage_id="red-goal-root-" + "3" * 64,
            assignment_id="3" * 64,
        ),
        SimpleNamespace(
            partition="train",
            focus_kind=GoalKind.ACQUIRE_SPECIES,
            root_lineage_id="red-goal-root-" + "4" * 64,
            assignment_id="4" * 64,
        ),
    )
    selected = SimpleNamespace(
        capture=SimpleNamespace(state_sha256="a" * 64, envelope_sha256="b" * 64),
        available_goal_kinds=(
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.RESTORE_TEAM.value,
        ),
    )
    base = SimpleNamespace(
        entries=entries,
        candidate=SimpleNamespace(
            registry=SimpleNamespace(
                assignment=lambda slot_id: assignments[int(slot_id.rsplit("-", 1)[1])]
            )
        ),
    )
    readiness = SimpleNamespace(
        paired=SimpleNamespace(
            development=base,
            prior_campaigns=(
                {
                    "roots": [
                        {
                            "root_lineage_id": prior_lineage,
                            "state_sha256": "c" * 64,
                            "envelope_sha256": "d" * 64,
                        }
                    ]
                },
            ),
        )
    )
    inspected: list[int] = []
    globals_ = SCRIPT["_select_unused_acquisition_root"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setattr(
        SCRIPT["development"],
        "_historical_root_is_open",
        lambda *args: True,
    )

    def inspect(*args, entry_index: int, **kwargs):  # type: ignore[no-untyped-def]
        inspected.append(entry_index)
        return selected

    monkeypatch.setattr(SCRIPT["development"], "_inspect_root", inspect)

    result = SCRIPT["_select_unused_acquisition_root"](readiness)

    assert result is selected
    assert inspected == [3]


def test_generic_inventory_does_not_replace_uninspectable_first_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = (SimpleNamespace(slot_id="slot-0"), SimpleNamespace(slot_id="slot-1"))
    assignments = tuple(
        SimpleNamespace(
            partition="train",
            focus_kind=GoalKind.ACQUIRE_SPECIES,
            root_lineage_id=f"red-goal-root-{index:064x}",
            assignment_id=f"{index:064x}",
        )
        for index in range(2)
    )
    readiness = SimpleNamespace(
        paired=SimpleNamespace(
            development=SimpleNamespace(
                entries=entries,
                candidate=SimpleNamespace(
                    registry=SimpleNamespace(
                        assignment=lambda slot_id: assignments[int(slot_id.rsplit("-", 1)[1])]
                    )
                ),
            ),
            prior_campaigns=(),
        )
    )
    inspected: list[int] = []
    globals_ = SCRIPT["_select_unused_acquisition_root"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setattr(SCRIPT["development"], "_historical_root_is_open", lambda *args: True)

    def inspect(*args, entry_index: int, **kwargs):  # type: ignore[no-untyped-def]
        inspected.append(entry_index)
        return None

    monkeypatch.setattr(SCRIPT["development"], "_inspect_root", inspect)

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="action_free_root_inventory"):
        SCRIPT["_select_unused_acquisition_root"](readiness)
    assert inspected == [0]


def test_qualification_rejects_a_plan_for_a_later_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = SimpleNamespace(slot_id="slot-0")
    assignment = SimpleNamespace(
        partition="train",
        focus_kind=GoalKind.ACQUIRE_SPECIES,
        assignment_id="1" * 64,
    )
    readiness = SimpleNamespace(
        paired=SimpleNamespace(
            development=SimpleNamespace(entries=(entry, SimpleNamespace(slot_id="slot-1"))),
            prior_campaigns=(),
        )
    )
    monkeypatch.setitem(
        SCRIPT["_reconstruct_plan_root"].__globals__,
        "_first_static_root_candidate",
        lambda *_args: (0, entry, assignment, set()),
    )

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="root_selection_authentication"):
        SCRIPT["_reconstruct_plan_root"](
            readiness,
            {"entry_index": 1},
            require_unclaimed=True,
        )


@pytest.mark.parametrize(
    ("available_goal_kinds", "prior_state_envelope"),
    (
        ((GoalKind.ACQUIRE_SPECIES.value, GoalKind.RESTORE_TEAM.value), {("a" * 64, "b" * 64)}),
        ((GoalKind.ACQUIRE_SPECIES.value,), set()),
        ((GoalKind.ACQUIRE_SPECIES.value, GoalKind.EVOLVE_SPECIES.value), set()),
    ),
)
def test_qualification_reapplies_physical_and_menu_exclusions(
    monkeypatch: pytest.MonkeyPatch,
    available_goal_kinds: tuple[str, ...],
    prior_state_envelope: set[tuple[str, str]],
) -> None:
    entry = SimpleNamespace(slot_id="slot-0")
    assignment = SimpleNamespace(
        partition="train",
        focus_kind=GoalKind.ACQUIRE_SPECIES,
        assignment_id="1" * 64,
    )
    readiness = SimpleNamespace(
        paired=SimpleNamespace(
            development=SimpleNamespace(entries=(entry,)),
            prior_campaigns=(),
        )
    )
    inspected = SimpleNamespace(
        assignment=assignment,
        capture=SimpleNamespace(state_sha256="a" * 64, envelope_sha256="b" * 64),
        available_goal_kinds=available_goal_kinds,
    )
    globals_ = SCRIPT["_reconstruct_plan_root"].__globals__
    monkeypatch.setitem(
        globals_,
        "_first_static_root_candidate",
        lambda *_args: (0, entry, assignment, prior_state_envelope),
    )
    monkeypatch.setattr(SCRIPT["development"], "_inspect_root", lambda *args, **kwargs: inspected)

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="root_drift"):
        SCRIPT["_reconstruct_plan_root"](
            readiness,
            {"entry_index": 0},
            require_unclaimed=True,
        )


def test_execution_uses_inherited_claim_before_trial_and_closes_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    inherited = SCRIPT["multiroot"]
    plan = _plan()
    trial = plan["trials"][0]
    assert isinstance(trial, dict)
    episode_id = trial["episode_id"]
    assert isinstance(episode_id, str)
    states = {episode_id: "absent"}

    class _Session:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return False

        def inspect_episode(self, value: str):  # type: ignore[no-untyped-def]
            return SimpleNamespace(status=states[value])

    qualified = SimpleNamespace(
        plan=plan,
        plan_sha256="9" * 64,
        store=SimpleNamespace(collection_session=lambda campaign_id: _Session()),
    )
    globals_ = inherited._execute.__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: True)
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        globals_, "write_root_claim", lambda *args, **kwargs: order.append("terminal")
    )
    monkeypatch.setitem(globals_, "_claim_campaign", lambda *args: order.append("claim"))
    wrapper_globals = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(
        wrapper_globals, "open_fixed_account_claim_registry", lambda: Path("claims")
    )
    monkeypatch.setitem(
        wrapper_globals,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(wrapper_globals, "root_claim_is_available", lambda *args: True)
    monkeypatch.setitem(
        wrapper_globals,
        "write_root_claim",
        lambda *args, **kwargs: order.append("lane_claim"),
    )
    monkeypatch.setattr(inherited, "_campaign_execution_identity", lambda *args: "f" * 64)

    def execute_trial(*args):  # type: ignore[no-untyped-def]
        assert order == ["lane_claim", "claim"]
        order.append("prediction")
        states[episode_id] = "complete"
        return {"status": "complete"}

    monkeypatch.setitem(globals_, "_execute_trial", execute_trial)

    result = SCRIPT["_execute"](_readiness(), qualified)

    assert order == ["lane_claim", "claim", "prediction", "terminal"]
    assert result["trial"]["status"] == "complete"  # type: ignore[index]
    assert result["development_labels_opened"] == 0
    assert result["model_fits"] == 0


def test_execution_refuses_a_consumed_lane_before_inherited_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: False)
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_execute",
        lambda *args, **kwargs: pytest.fail("consumed lane reached inherited execution"),
    )

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="lane_already_consumed"):
        SCRIPT["_execute"](_readiness(), SimpleNamespace(plan_sha256="9" * 64))


def test_execution_preserves_retained_failure_and_names_unknown_live_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_execute",
        lambda *args, **kwargs: {
            "campaign_terminal_sha256": "8" * 64,
            "trials": [
                {
                    "status": "failed_terminal_retained",
                    "failure_stage": "unexpected_failure",
                }
            ],
            "complete_trials": 0,
            "failed_trials": 1,
        },
    )
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: True)
    monkeypatch.setitem(globals_, "write_root_claim", lambda *args, **kwargs: None)
    monkeypatch.setattr(SCRIPT["multiroot"], "_campaign_execution_identity", lambda *args: "f" * 64)

    result = SCRIPT["_execute"](
        _readiness(),
        SimpleNamespace(plan_sha256="9" * 64),
    )

    assert result["trial"]["status"] == "failed_terminal_retained"  # type: ignore[index]
    assert result["trial"]["failure_stage"] == "development_execution"  # type: ignore[index]


def test_admission_reads_train_only_and_counts_one_settled_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    admitted = SimpleNamespace(
        targets=(SimpleNamespace(),),
        verified_outcomes=1,
        collection_relevant_outcomes=1,
        successful_retained_acquisitions=1,
    )
    inherited = SCRIPT["multiroot"]
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "root_claim_is_available",
        lambda *args: False,
    )
    qualified = SimpleNamespace(plan_sha256="9" * 64)
    monkeypatch.setattr(
        inherited,
        "_campaign_execution_identity",
        lambda *args: "f" * 64,
    )
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "read_root_claim",
        lambda *args: SCRIPT["_expected_lane_claim"](_readiness(), qualified),
    )
    monkeypatch.setattr(
        inherited,
        "_require_campaign_terminal",
        lambda *args: calls.append("terminal"),
    )

    def load(*args, partition: str):  # type: ignore[no-untyped-def]
        calls.append(partition)
        return (admitted,), {}

    monkeypatch.setattr(inherited, "_load_partition", load)

    result = SCRIPT["_admit"](
        _readiness(),
        qualified,
    )

    assert calls == ["terminal", "train"]
    assert result["causal_train_examples_added"] == 1
    assert result["causal_train_attempts"] == 1
    assert result["claimed_train_roots"] == 1
    assert result["atomic_goal_episodes_added"] == 1
    assert result["development_episode_attempts_added"] == 0
    assert result["verified_outcome_examples_added"] == 0
    assert result["development_labels_opened"] == 0
    assert result["model_fits_added"] == 0


def test_admission_does_not_count_interrupted_choice_as_causal_train_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = SimpleNamespace(
        targets=(),
        verified_outcomes=1,
        collection_relevant_outcomes=1,
        successful_retained_acquisitions=0,
    )
    inherited = SCRIPT["multiroot"]
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "root_claim_is_available",
        lambda *args: False,
    )
    qualified = SimpleNamespace(plan_sha256="9" * 64)
    monkeypatch.setattr(inherited, "_campaign_execution_identity", lambda *args: "f" * 64)
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "read_root_claim",
        lambda *args: SCRIPT["_expected_lane_claim"](_readiness(), qualified),
    )
    monkeypatch.setattr(inherited, "_require_campaign_terminal", lambda *args: None)
    monkeypatch.setattr(
        inherited,
        "_load_partition",
        lambda *args, **kwargs: ((admitted,), {}),
    )

    result = SCRIPT["_admit"](
        _readiness(),
        qualified,
    )

    assert result["causal_train_examples_added"] == 0
    assert result["causal_train_attempts"] == 1
    assert result["claimed_train_roots"] == 1
    assert result["atomic_goal_episodes_added"] == 1
    assert result["invalid_trial_controller_start_status"] == "not_applicable"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("root_consumption_sha256", "0" * 64),
        ("execution_identity_sha256", "1" * 64),
        ("source_commit", "2" * 40),
        ("runner_sha256", "3" * 64),
    ),
)
def test_admission_rejects_mutated_lane_claim(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    readiness = _readiness()
    qualified = SimpleNamespace(plan_sha256="9" * 64)
    inherited = SCRIPT["multiroot"]
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "root_claim_is_available",
        lambda *args: False,
    )
    monkeypatch.setattr(inherited, "_campaign_execution_identity", lambda *args: "f" * 64)
    claim = SCRIPT["_expected_lane_claim"](readiness, qualified)
    claim[field] = value
    monkeypatch.setitem(
        SCRIPT["_admit"].__globals__,
        "read_root_claim",
        lambda *args: claim,
    )

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="lane_claim_authentication"):
        SCRIPT["_admit"](readiness, qualified)


def test_retired_runner_stops_before_manifest_readiness_or_private_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_readiness",
        lambda args: calls.append("readiness"),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_freeze",
        lambda *args: calls.append("private freeze"),
    )

    assert SCRIPT["main"](["--mode", "freeze", "--rom", "/private/rom.gb"]) == 1
    output = capsys.readouterr().out
    result = json.loads(output)

    assert result["failure_stage"] == "lane_retired"
    assert result["effects"] == "no_manifest_readiness_or_private_access"
    assert "/private/rom.gb" not in output
    assert result["private_path_fields"] == 0
    assert calls == []


def test_runner_attestation_fails_before_inherited_private_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited_calls = 0

    def inherited(*args: object, **kwargs: object) -> object:
        nonlocal inherited_calls
        inherited_calls += 1
        raise AssertionError("inherited readiness must not run")

    monkeypatch.setattr(SCRIPT["multiroot"], "_readiness", inherited)
    monkeypatch.setitem(
        SCRIPT["_readiness"].__globals__,
        "_file_sha256",
        lambda path: "b" * 64,
    )

    with pytest.raises(SCRIPT["SingleRootCausalRunError"], match="executable_attestation"):
        SCRIPT["_readiness"](SimpleNamespace(expected_runner_sha256="a" * 64))

    assert inherited_calls == 0
