from copy import deepcopy

import pytest
from run_red_trainer_broad_fit import LATE_MODEL_SHA
from run_red_trainer_learner_continuation import (
    POLICY,
    bind_target,
    first_choice,
    select_cases,
    unwrap_target,
)


def test_policy_target_contract_is_explicit_and_legacy_incompatible():
    target = {"capture_id": "train1", "partition": "train", "heads": {}}
    wrapper = bind_target(target, policy_id=POLICY, model_sha256=LATE_MODEL_SHA)
    assert "heads" not in wrapper
    assert unwrap_target(wrapper) == target
    for key, value in (
        ("policy_id", "teacher"),
        ("model_sha256", "0" * 64),
        ("history_initialization", "oracle"),
        ("player_turn_horizon", 2),
    ):
        changed = deepcopy(wrapper)
        changed["continuation"][key] = value
        with pytest.raises(ValueError, match="contract"):
            unwrap_target(changed)
    with pytest.raises(ValueError, match="wrapper"):
        unwrap_target(target)
    with pytest.raises(ValueError, match="TRAIN"):
        bind_target(
            {**target, "partition": "development"}, policy_id=POLICY, model_sha256=LATE_MODEL_SHA
        )


def test_selection_is_return_blind_balanced_and_unique():
    rows = []
    for root in range(4):
        for kind, context, profile in (
            ("assisted-train-a", "main", "late"),
            ("assisted-train-b", "main", "late-main"),
            ("terminal-intermediate-a", "forced", "late"),
            ("terminal-intermediate-b", "main", "late-main"),
        ):
            rows.append(
                {
                    "capture_id": f"{kind}-{root}",
                    "decision_context": context,
                    "root_lineage_id": str(root),
                    "source_profile": profile,
                }
            )
    assert len(select_cases(rows)) == 16
    assert select_cases(rows) == select_cases(rows[::-1])
    with pytest.raises(ValueError, match="useful"):
        select_cases(rows[:-1])
    with pytest.raises(ValueError, match="origins"):
        select_cases(rows[:4])


@pytest.mark.parametrize(
    "ref",
    [
        "pokemon.core:battle:move:1",
        "pokemon.core:battle:switch:3",
        "pokemon.core:battle:decline-switch",
    ],
)
def test_first_choice_handles_all_decision_contexts(ref):
    assert first_choice(ref).semantic_ref == ref


def test_first_choice_rejects_other_actions():
    with pytest.raises(ValueError):
        first_choice("pokemon.core:battle:item:1")
