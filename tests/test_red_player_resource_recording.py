import json
from types import SimpleNamespace as NS

import pytest
from test_red_live_option_menu import _model
from test_red_player_lesson_runtime import fixture
from test_red_player_resource_lesson import records

import pokemon_red_completion.red_native_player as native
import pokemon_red_completion.red_player_lesson_runtime as lesson
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_readiness
from pokemon_red_completion.red_native_curriculum import (
    NativeCurriculumInput,
    load_native_curriculum,
)


@pytest.mark.parametrize("fault", [None, "false_success", "execution_failure", "invalid_verdict"])
def test_continuous_resource_admission_is_prospective_and_separate(tmp_path, monkeypatch, fault):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, kind=GoalKind.RESUPPLY,
                                      record_factory=records, fault=fault)
    original = lesson.capture_player_lesson_snapshot

    def capture(runtime):
        observation, snapshot = original(runtime)
        observation.input_ready = True
        observation.raw.battle_state = 0
        observation.collection_observation = NS(owned_species=("one",),
                                                specimens=(NS(species_ref="one"),))
        return observation, snapshot

    monkeypatch.setattr(lesson, "capture_player_lesson_snapshot", capture)
    monkeypatch.setattr(native, "capture_player_lesson_snapshot", capture)

    def factory(controller):
        rt = kwargs["runtime_factory"](controller)
        rt.reader = NS(read_bottom_dialogue_box_visible=lambda: False)
        return rt

    source = dict(kwargs["source"])
    receipt = source.pop("setup_receipt_sha256")
    output = tmp_path / "native"
    result = native.run_native_continuous_player(
        store=store, emulator=emulator, runtime_factory=factory, source=source,
        output=output, model=upgrade_option_value_model_for_readiness(_model()),
        seed=101, run_id="resource-recording-test", arm_id="train",
        combat_specimen_refs=kwargs["combat_specimen_refs"],
        battle_observer=lambda: kwargs["battle"], target_cash=3000,
        limits=native.NativePlayerLimits(decisions=1, actions=5, frames=1000, cash_debits=3000),
        resource_setup_receipt=receipt,
    )
    assert result["model_decisions"] == 0
    path = output / "resource-lesson-000.json"
    if fault in {"execution_failure", "invalid_verdict"}:
        assert not path.exists()
        assert (output / "episode/step-000/outcome.json").exists()
    else:
        admission = json.loads(path.read_text())
        assert admission["admitted"] == (fault is None)
        assert not admission["comparative_choice"] and not admission["automatic_fit"]
        if fault is None:
            row = load_native_curriculum(store, NativeCurriculumInput(**admission["item"]))
            assert row.outcome.verified_success and row.outcome.economy.cash_delta == -1000


def test_continuous_contract_does_not_relabel_teacher_or_invent_pressure(tmp_path):
    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_native_curriculum import (
        CONTINUOUS_RESOURCE_CONTRACT,
        CONTINUOUS_RESOURCE_OUTCOME_SCHEMA,
        CONTINUOUS_RESOURCE_PLAN_SCHEMA,
        curriculum_projection,
        reconstruct_native_curriculum,
    )

    plan, result = records(tmp_path)
    plan.update(schema=CONTINUOUS_RESOURCE_PLAN_SCHEMA, contract=CONTINUOUS_RESOURCE_CONTRACT,
                teacher_selected=False, capture_reserve=None,
                execution_identity=dict(run_id="r", arm_id="a", model_sha256="0"*64, seed=1))
    result.update(schema=CONTINUOUS_RESOURCE_OUTCOME_SCHEMA,
                  declaration_sha256=canonical_sha256(plan))
    assert reconstruct_native_curriculum(plan, result).outcome.verified_success
    plan["teacher_selected"] = True
    with pytest.raises(ValueError, match="scope"):
        curriculum_projection(plan)
    plan["teacher_selected"] = False
    plan["question"]["situation"]["need_pressures"]["resources"] = 0.789
    with pytest.raises(ValueError, match="question"):
        curriculum_projection(plan)


def test_continuous_projection_reconstructs_declared_reserve_without_mutation(tmp_path):
    import copy

    from pokemon_red_completion.red_native_curriculum import (
        CONTINUOUS_RESOURCE_CONTRACT,
        CONTINUOUS_RESOURCE_PLAN_SCHEMA,
        _continuous_situation,
        curriculum_projection,
    )

    plan, _ = records(tmp_path)
    plan.update(schema=CONTINUOUS_RESOURCE_PLAN_SCHEMA, contract=CONTINUOUS_RESOURCE_CONTRACT,
                teacher_selected=False,
                capture_reserve=dict(ball=4, throws=1, reserve=5, require_status=False),
                execution_identity=dict(run_id="r", arm_id="a", model_sha256="0"*64, seed=1))
    before = copy.deepcopy(plan["before"])
    plan["question"]["situation"] = _continuous_situation(plan)
    assert plan["question"]["situation"]["need_pressures"]["resources"] == 1
    curriculum_projection(plan)
    assert plan["before"] == before
    plan["question"]["situation"]["need_pressures"]["resources"] = 0.5
    with pytest.raises(ValueError, match="question"):
        curriculum_projection(plan)


def test_continuous_unit_declaration_requires_a_matching_execution_claim(tmp_path):
    from test_private_artifacts import _make_store

    from pokemon_red_completion.red_native_curriculum import (
        CONTINUOUS_RESOURCE_CONTRACT,
        CONTINUOUS_RESOURCE_PLAN_SCHEMA,
        publish_declaration,
    )

    plan, _ = records(tmp_path / "records")
    _, _, store = _make_store(tmp_path)
    plan.update(schema=CONTINUOUS_RESOURCE_PLAN_SCHEMA, contract=CONTINUOUS_RESOURCE_CONTRACT,
                teacher_selected=False, capture_reserve=None,
                execution_identity=dict(run_id="r", arm_id="a", model_sha256="0"*64, seed=1))
    with pytest.raises(ValueError, match="execution claim"):
        publish_declaration(store, plan)


def test_continuous_settled_failure_retains_observed_loss(tmp_path):
    import copy

    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_native_curriculum import (
        CONTINUOUS_RESOURCE_CONTRACT,
        CONTINUOUS_RESOURCE_OUTCOME_SCHEMA,
        CONTINUOUS_RESOURCE_PLAN_SCHEMA,
        reconstruct_native_curriculum,
    )
    from pokemon_red_completion.red_player_economy import snapshot_document
    from pokemon_red_completion.resource_economy_observation import EconomySnapshot

    plan, result = records(tmp_path)
    plan.update(schema=CONTINUOUS_RESOURCE_PLAN_SCHEMA, contract=CONTINUOUS_RESOURCE_CONTRACT,
                teacher_selected=False, capture_reserve=None,
                execution_identity=dict(run_id="r", arm_id="a", model_sha256="0"*64, seed=1))
    result.update(schema=CONTINUOUS_RESOURCE_OUTCOME_SCHEMA,
                  declaration_sha256=canonical_sha256(plan), succeeded=False,
                  after=copy.deepcopy(plan["before"]),
                  economy_after=snapshot_document(EconomySnapshot(2500, ())))
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success and row.outcome.economy.cash_delta == -500
    assert row.outcome.action_cost > 0 and row.public_dict()["comparative_choice"] is False


@pytest.mark.parametrize("missing", [False, True])
def test_resource_curriculum_empty_menu_cannot_hide_missing_species(tmp_path, monkeypatch, missing):
    from test_red_native_player import setup

    import pokemon_red_completion.red_player_curriculum as curriculum
    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalOpportunity,
        GoalUnavailableReason,
    )
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet

    args, _ = setup(tmp_path, monkeypatch)
    _, snapshot = native.capture_player_lesson_snapshot(None)
    member = snapshot["party"][0]
    args["curriculum"] = curriculum.NativeResourceCurriculum(
        tuple(snapshot["completed_objectives"]), ((member["specimen_ref"], member["level"]),),
        ("missing" if missing else "one",), (),
    )
    monkeypatch.setattr(curriculum, "_raw_party_fully_restored", lambda _: True)
    args["enumerate_bindings"] = lambda *a: GoalBindingSet(tuple(GoalOpportunity(
        kind.value, kind, GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
        for kind in (GoalKind.ACQUIRE_SPECIES, GoalKind.RESUPPLY)), ())
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == ("menu_unavailable" if missing else "curriculum_complete")
    assert result["model_decisions"] == result["executed_decisions"] == 0
    assert args["emulator"].frame_count == 0
