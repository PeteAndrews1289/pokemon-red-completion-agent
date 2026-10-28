"""A native local survey must retain verified partial captures and requery safely."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_live_option_menu import _binding
from test_red_partial_capture_recovery import partial_capture

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalVerification
from pokemon_red_completion.red_integrated_play import ordinary_player_setback

LOCAL = "pokemon.red:acquisition:wild:test:grass:profile-" + "0" * 64 + ":config-" + "1" * 64


def local_partial(monkeypatch, **kwargs):
    _, _, before, after, receipt = partial_capture(monkeypatch, **kwargs)
    survey = deepcopy(receipt.evidence["capture_survey"])
    captures = survey["captures"]
    evidence = dict(
        bounded=True, source_normalized=False,
        initial_missing=2, final_missing=1,
        initial_missing_specimens=captures + 1, final_missing_specimens=1,
        capture_survey=survey,
        capture_diagnostics=deepcopy(receipt.evidence["capture_diagnostics"]),
        **survey,
    )
    before = replace(before, facts={**before.facts, "diagnostics": {"map_id": 59}})
    after = replace(after, facts={**after.facts, "diagnostics": {"map_id": 59}})
    return before, after, replace(receipt, evidence=evidence)


def accepted(before, after, receipt, *, ref=LOCAL, reason=GoalFailureReason.RESOURCE_LOST, error=None):
    return ordinary_player_setback(
        _binding(GoalKind.ACQUIRE_SPECIES, binding_ref=ref, calls=[]),
        before, after, receipt, GoalVerification.failed(reason), error,
    )


@pytest.mark.parametrize("in_party", [False, True])
@pytest.mark.parametrize("captures", [1, 2])
@pytest.mark.parametrize("evolve", [False, True])
def test_verified_local_partial_capture_returns_to_model_without_success(
    monkeypatch, in_party, captures, evolve,
):
    before, after, receipt = local_partial(
        monkeypatch, in_party=in_party, captures=captures, evolve=evolve,
    )
    assert accepted(before, after, receipt)
    assert GoalVerification.failed(GoalFailureReason.RESOURCE_LOST).status.value == "failed"
    assert receipt.evidence["final_missing"] == 1


@pytest.mark.parametrize("fault", [
    "unknown_binding", "missing_map", "boolean_map", "map_jump", "unbounded",
    "boolean_bound", "missing_normalization", "unknown_normalization", "unknown_schema",
    "count_mismatch", "boolean_count", "flag_mismatch", "missing_survey",
    "no_remaining_target", "wrong_missing_delta", "wrong_source", "partial_input",
    "unsafe", "unready", "unknown_reason", "exception", "changed_guard",
])
def test_native_local_partial_recovery_rejects_missing_or_inconsistent_authority(monkeypatch, fault):
    before, after, receipt = local_partial(monkeypatch)
    bf, af, evidence = deepcopy(dict(before.facts)), deepcopy(dict(after.facts)), deepcopy(dict(receipt.evidence))
    ref, reason, error = LOCAL, GoalFailureReason.RESOURCE_LOST, None
    if fault == "unknown_binding":
        ref = "unknown:local:capture"
    elif fault == "missing_map":
        af.pop("diagnostics")
    elif fault == "boolean_map":
        bf["diagnostics"]["map_id"] = af["diagnostics"]["map_id"] = True
    elif fault == "map_jump":
        af["diagnostics"]["map_id"] = 60
    elif fault == "unbounded":
        evidence["bounded"] = False
    elif fault == "boolean_bound":
        evidence["bounded"] = 1
    elif fault == "missing_normalization":
        evidence.pop("source_normalized")
    elif fault == "unknown_normalization":
        evidence["source_normalized"] = 0
    elif fault == "unknown_schema":
        evidence["schema"] = "unknown"
    elif fault == "count_mismatch":
        evidence["captures"] += 1
    elif fault == "boolean_count":
        evidence["captures"] = True
    elif fault == "flag_mismatch":
        evidence["safety_stopped"] = False
    elif fault == "missing_survey":
        evidence.pop("capture_survey")
    elif fault == "no_remaining_target":
        evidence["final_missing"] = 0
    elif fault == "wrong_missing_delta":
        evidence["initial_missing_specimens"] += 1
    elif fault == "wrong_source":
        evidence["capture_diagnostics"]["events"][0]["source_id"] = "wild:other:grass"
    elif fault == "partial_input":
        af["completed_actions"] = af["actions"] - 1
    elif fault == "unsafe":
        after = replace(after, safe=False)
    elif fault == "unready":
        af["input_ready"] = False
    elif fault == "unknown_reason":
        reason = GoalFailureReason.OUTCOME_NOT_VERIFIED
    elif fault == "exception":
        error = RuntimeError("unfinished work")
    elif fault == "changed_guard":
        af["retained_party_continuation"]["guard_sha256"] = "f" * 64
    assert not accepted(
        replace(before, facts=bf), replace(after, facts=af),
        replace(receipt, evidence=evidence), ref=ref, reason=reason, error=error,
    )
