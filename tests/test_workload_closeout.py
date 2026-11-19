"""Use fixed local synthetic receipts; no ROM or native replay."""

import copy
import runpy
from pathlib import Path

import pytest


def records():
    plan = dict(
        schema="pokemon.red.native-venue-workload-TRAIN-case.v2",
        source_sha256="a" * 64,
        allow_direct_evolution=True,
        sources=[dict(xp_condition="fixture_level", fixture_level=49)],
    )
    binding = dict(partition="train", initial_state_sha256="b" * 64)
    result = dict(
        teacher_selected=True,
        training_admission=True,
        new_fits=0,
        new_weights=0,
        copy_back=False,
        campaign_progress=False,
        frames=100,
        actions=20,
        terminal_sha256="c" * 64,
    )
    decision = dict(
        binding=binding,
        candidate_set=[1, 2, 3],
        teacher_forced_venue=True,
        outcomes_not_opened=True,
        assigned_index=0,
        state_sha256="d" * 64,
        common_prefix_inputs=2,
        common_prefix_frames=10,
        all_common_prefix_costs_included=True,
    )
    document = dict(
        fit_eligible=True,
        actual_progress=False,
        settled_native_attempt=True,
        controller_costs_are_full_native_totals=True,
        frames=100,
        actions=20,
        terminal_state_sha256="c" * 64,
        prospective_binding=binding,
        candidate_set=[1, 2, 3],
        assigned_index=0,
    )
    setup = dict(
        partition="train",
        evaluation_partition="train",
        teacher_only=True,
        xp_condition="fixture_level",
        current_level=49,
        non_target_party_fields_unchanged=True,
        native_protected_party_fields_unchanged=False,
        writes=[dict(address=1)],
        original_state_sha256="a" * 64,
        frames=0,
        inputs=0,
        state_sha256="b" * 64,
    )
    return plan, result, document, decision, setup


@pytest.mark.parametrize(
    "fault", [None, "level", "copyback", "prefix", "uncharged", "source", "non_target", "no_prefix"]
)
def test_workload_closeout_distinguishes_fixture_from_charged_decision_prefix(fault):
    verify = runpy.run_path(str(Path("scripts/authenticate_red_teacher_case.py")))[
        "verify_venue_teacher_outcome"
    ]
    plan, result, document, decision, setup = copy.deepcopy(records())
    if fault == "level":
        setup["current_level"] = 22
    if fault == "copyback":
        result["copy_back"] = True
    if fault == "prefix":
        decision["common_prefix_inputs"] = 21
    if fault == "uncharged":
        decision["all_common_prefix_costs_included"] = False
    if fault == "source":
        decision["binding"]["initial_state_sha256"] = "a" * 64
    if fault == "non_target":
        setup["non_target_party_fields_unchanged"] = False
    if fault == "no_prefix":
        decision["common_prefix_inputs"] = 0
    if fault is None:
        verify(plan, result, document, decision, setup)
    else:
        with pytest.raises(AssertionError):
            verify(plan, result, document, decision, setup)
