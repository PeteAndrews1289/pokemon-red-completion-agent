"""Current singleton interface remains support in the TRAIN venue recorder."""

from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from pokemon_red_completion.player_readiness import READINESS_NAMES, PlayerReadiness
from pokemon_red_completion.red_player_support import RedPlayerSupport
from pokemon_red_completion.red_teacher_venue import teacher_evolution_selection


def support(kind=GoalKind.EVOLVE_SPECIES):
    b = ExecutableGoalBinding("declared-evolution", kind, 0.1, 0.1, lambda: None, lambda _: None)
    mask = GoalOpportunity(
        "masked-explore",
        GoalKind.EXPLORE,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
    )
    return RedPlayerSupport(
        GoalBindingSet((b.opportunity, mask), (b,)),
        PlayerReadiness((0.0,) * (len(READINESS_NAMES) - 1), history_observed=False),
    )


def test_singleton_teacher_keeps_support_and_real_candidate():
    options = support()
    candidate = object()
    binding, selected, index, menu = teacher_evolution_selection(
        options, {options.binding.binding_ref}, {options.binding.binding_ref: candidate}
    )
    assert binding is options.binding and selected is candidate and index is None
    assert menu["comparative_choice"] is False and menu["model_queries"] == 0


@pytest.mark.parametrize("fault", ["kind", "target", "candidate", "type"])
def test_singleton_does_not_grant_another_task_or_fake_candidate(fault):
    options = support(GoalKind.RESTORE_TEAM if fault == "kind" else GoalKind.EVOLVE_SPECIES)
    refs = {"another"} if fault == "target" else {options.binding.binding_ref}
    candidates = {} if fault == "candidate" else {options.binding.binding_ref: object()}
    if fault == "type":
        options = N()
    with pytest.raises((ValueError, KeyError)):
        teacher_evolution_selection(options, refs, candidates)


def test_conditioned_state_authentication_binds_derived_state_not_ancestor():
    import runpy
    from pathlib import Path

    verify = runpy.run_path(str(Path("scripts/authenticate_red_teacher_case.py")))[
        "verify_venue_teacher_outcome"
    ]
    plan = {
        "schema": "pokemon.red.native-venue-geometry-TRAIN-case.v1",
        "source_sha256": "a" * 64,
        "sources": [{"xp_condition": "near_next_level"}],
    }
    result = dict(
        teacher_selected=True,
        training_admission=True,
        new_fits=0,
        new_weights=0,
        copy_back=False,
        campaign_progress=False,
        frames=10,
        actions=2,
        terminal_sha256="c" * 64,
    )
    binding = dict(partition="train", initial_state_sha256="b" * 64)
    decision = dict(
        binding=binding,
        candidate_set=[1, 2],
        teacher_forced_venue=True,
        outcomes_not_opened=True,
        assigned_index=0,
        state_sha256="b" * 64,
    )
    document = dict(
        fit_eligible=True,
        actual_progress=False,
        settled_native_attempt=True,
        controller_costs_are_full_native_totals=True,
        frames=10,
        actions=2,
        terminal_state_sha256="c" * 64,
        prospective_binding=binding,
        candidate_set=[1, 2],
        assigned_index=0,
    )
    setup = dict(
        partition="train",
        evaluation_partition="train",
        teacher_only=True,
        xp_condition="near_next_level",
        original_state_sha256="a" * 64,
        frames=0,
        inputs=0,
        native_protected_party_fields_unchanged=True,
        state_sha256="b" * 64,
    )
    verify(plan, result, document, decision, setup)
    with pytest.raises(AssertionError):
        verify(plan, result, document, decision)
    binding["initial_state_sha256"] = "a" * 64
    with pytest.raises(AssertionError):
        verify(plan, result, document, decision, setup)


@pytest.mark.parametrize("fault", [None, "admission", "forced", "index", "model", "ordinary_count"])
def test_model_validation_keeps_outer_teacher_and_requires_real_venue_event(fault):
    import runpy
    from pathlib import Path

    verify = runpy.run_path(str(Path("scripts/authenticate_red_teacher_case.py")))[
        "verify_venue_teacher_outcome"
    ]
    role = "exposed-TRAIN-component-no-admission"
    menu = dict(
        candidates=[
            dict(
                candidate_index=i,
                feature_schema_id="v3",
                features={"venue.travel_steps": 0.0, "target.xp": 0.5},
            )
            for i in range(2)
        ]
    )
    plan = dict(
        schema="pokemon.red.native-venue-geometry-TRAIN-case.v1",
        source_sha256="a" * 64,
        sources=[dict(venue_mode="model", xp_condition="original")],
        validation_role=role,
        venue_model_sha256="d" * 64,
    )
    event = dict(
        actor="learned_venue_model",
        model_selected=True,
        model_sha256="d" * 64,
        selected_index=0,
        candidate_count=2,
        candidate_set=menu,
    )
    result = dict(
        teacher_selected=True,
        training_admission=False,
        new_fits=0,
        new_weights=0,
        copy_back=False,
        campaign_progress=False,
        frames=10,
        actions=2,
        terminal_sha256="c" * 64,
        native_outcome=dict(venue_choice_events=[dict(payload=event)]),
    )
    binding = dict(partition="train", initial_state_sha256="a" * 64)
    decision = dict(
        binding=binding,
        candidate_set=menu,
        teacher_forced_venue=False,
        outcomes_not_opened=True,
        assigned_index=0,
        state_sha256="a" * 64,
        model_sha256="d" * 64,
    )
    document = dict(
        fit_eligible=False,
        actual_progress=False,
        settled_native_attempt=True,
        controller_costs_are_full_native_totals=True,
        frames=10,
        actions=2,
        terminal_state_sha256="c" * 64,
        prospective_binding=binding,
        candidate_set=menu,
        assigned_index=0,
        validation_role=role,
        model_selected_venue=True,
    )
    if fault == "ordinary_count":
        plan["ordinary_full_venue_menu"] = True
    if fault == "admission":
        result["training_admission"] = True
    if fault == "forced":
        decision["teacher_forced_venue"] = True
    if fault == "index":
        event["selected_index"] = 1
    if fault == "model":
        event["model_sha256"] = "e" * 64
    if fault is None:
        verify(plan, result, document, decision)
    else:
        with pytest.raises(AssertionError):
            verify(plan, result, document, decision)


@pytest.mark.parametrize("fault", [None, "fit", "partition", "root", "xp", "pin"])
def test_exposed_capture_source_cannot_become_training(tmp_path, fault):
    import hashlib
    import json

    from pokemon_red_completion.red_teacher_venue import authenticate_exposed_venue_source

    def write(name, d):
        p = tmp_path / name
        p.write_bytes(d if isinstance(d, bytes) else json.dumps(d).encode())
        return str(p)

    def sha(p):
        from pathlib import Path

        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    state = write("source.state", b"synthetic unit state")
    envelope = write(
        "source.json",
        dict(
            schema="pokemon-private-captured-progress-v1",
            state_sha256=sha(state),
            checkpoint_id="synthetic-checkpoint",
            checkpoint_label="unit",
            checkpoints_completed=1,
            checkpoints_total=2,
            verified_objective_ids=["power_on"],
        ),
    )
    source = dict(
        execution_partition="development",
        declared_partition="train",
        path=state,
        envelope=envelope,
        state_sha256=sha(state),
        envelope_sha256=sha(envelope),
        assigned_lineage="r" * 64,
        verified_objectives=["power_on"],
    )
    old = write("old-plan.json", dict(sources=[source]))
    protocol = write("protocol.json", dict(fitting=False))
    item = dict(
        declared_partition="train",
        execution_partition="development",
        xp_condition="original",
        venue_mode="teacher",
        assigned_lineage="r" * 64,
    )
    plan = dict(
        historical_source_plan=old,
        sources=[item],
        source=state,
        source_envelope=envelope,
        validation_role="related-DEV-matched-component-no-admission",
        fit_allowed=False,
        party_venue_fit_eligible=False,
        evaluation_protocol=protocol,
        pins={p: sha(p) for p in [state, envelope, old, protocol]},
    )
    if fault == "fit":
        plan["fit_allowed"] = True
    if fault == "partition":
        item["execution_partition"] = "train"
    if fault == "root":
        item["assigned_lineage"] = "s" * 64
    if fault == "xp":
        item["xp_condition"] = "near_next_level"
    if fault == "pin":
        plan["pins"][state] = "0" * 64
    if fault is None:
        _, payload, proof = authenticate_exposed_venue_source(plan)
        assert payload == b"synthetic unit state" and proof["fit_eligible"] is False
    else:
        with pytest.raises(ValueError):
            authenticate_exposed_venue_source(plan)
