"""ROM-free retained-receipt regressions for the reusable direct TRAIN collector."""
from copy import deepcopy
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json

import pytest

from pokemon_red_completion.red_teacher_case import (
    TeacherTrainCaseSpec, build_teacher_session_kwargs, validate_plan_case,
    validate_retained_menu, validate_source_boundary, story_binding_settings,
)


def fixture(number):
    return json.loads((Path(__file__).parent / "fixtures" / ("source" + number + ".json")).read_bytes())


@pytest.mark.parametrize("number", ["047", "049"])
def test_exact_paid_native_receipts_pass_same_gate(number):
    data = fixture(number)
    spec = validate_plan_case(data["plan"], data["source_row"])
    result = validate_retained_menu(spec, data["prior"], data["observed"], data["bindings"], data["pp"])
    assert result["passed"] and result["all_other_public_menu_fields_exact"]
    assert result["private_all_binding_parity_claim"] is (number == "047")


@pytest.mark.parametrize("setting,value", [("include_live_pp_readiness", False), ("force_resource_safety", False),
    ("allow_collection_restoration", False), ("model_feature_version", 9), ("greedy_selection", True),
    ("continue_safe_route_failures", True), ("refine_preparation", True)])
def test_explicit_session_contract_rejects_unapproved_drift(setting, value):
    data = fixture("047")["case"]
    data["session"][setting] = value
    with pytest.raises(ValueError, match="session settings"):
        TeacherTrainCaseSpec.from_dict(data)


def test_missing_pp_setting_is_not_silently_defaulted():
    data = fixture("047")["case"]
    del data["session"]["include_live_pp_readiness"]
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec.from_dict(data)


@pytest.mark.parametrize("field,value", [("map_id", True), ("map_id", 256), ("defeated_event", -1),
    ("defeated_event", 999999), ("trainer_identity", [231, 30, 10]), ("trainer_identity", [231, 31, 0]),
    ("trainer_identity", [231, 31, 256]), ("trainer_identity", None), ("victory_money", True),
    ("victory_money", 1000000), ("victory_items", [[238]]), ("victory_items", [[238, True]]),
    ("victory_badge_bits", -1), ("objective_id", " "), ("battle_plan_id", None)])
def test_native_contract_json_is_rejected_before_any_emulator(field, value):
    data = fixture("047")["case"]
    data["exact_contract"][field] = value
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec.from_dict(data)


def test_direct_dataclass_constructor_cannot_bypass_spec_validation():
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec("{}")
    data = fixture("047")["case"]
    data["session"]["include_live_pp_readiness"] = False
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec(json.dumps(data, sort_keys=True, separators=(",", ":")))


@pytest.mark.parametrize("field,value", [("seed", True), ("opening_idle_frames", 4),
    ("initial_history", "missing_assumed_none"), ("partition", "development"), ("initial_kind", "develop_team")])
def test_unqualified_sampling_or_phase_semantics_rejected(field, value):
    data = fixture("047")["case"]
    data[field] = value
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec.from_dict(data)


def test_immutable_declaration_rejects_unknown_fields_and_does_not_alias():
    data = fixture("047")["case"]
    spec = TeacherTrainCaseSpec.from_dict(data)
    data["session"]["include_live_pp_readiness"] = False
    returned = spec.document()
    returned["session"]["include_live_pp_readiness"] = False
    assert spec.document()["session"]["include_live_pp_readiness"] is True
    returned["unknown_future_planner"] = True
    with pytest.raises(ValueError, match="fields differ"):
        TeacherTrainCaseSpec.from_dict(returned)


@pytest.mark.parametrize("field", ["seed", "source_sha256", "exact_contract", "native_limits"])
def test_aliases_cannot_override_typed_case(field):
    data = fixture("049")
    data["plan"][field] = None
    with pytest.raises(ValueError, match="plan/spec disagreement"):
        validate_plan_case(data["plan"], data["source_row"])


def kwargs_for(spec, observer, callbacks=None):
    from pokemon_red_completion.red_native_player import NativeExecutionIdentity
    data = spec.document()
    return build_teacher_session_kwargs(spec, store=None, emulator=None, runtime_factory=None,
        source=dict(partition="train", state_sha256=data["source_sha256"]),
        execution=NativeExecutionIdentity("synthetic", "teacher-assigned-train", "a" * 64, data["seed"]),
        output=Path("synthetic-output"), battle_observer=observer, teacher_receipt_sha256="b" * 64,
        callbacks=callbacks or {})


@pytest.mark.parametrize("number", ["047", "049"])
def test_shared_kwargs_bind_actual_constructor_without_emulator_and_keep_live_history(number, monkeypatch):
    from pokemon_red_completion.emulator import PyBoyAdapter
    from pokemon_red_completion.red_native_player import NativePlayerSession
    def forbidden(*args, **kwargs):
        raise AssertionError("ROM-free qualification attempted native construction")
    monkeypatch.setattr(PyBoyAdapter, "__init__", forbidden)
    history = [None]
    spec = TeacherTrainCaseSpec.from_dict(fixture(number)["case"])
    kwargs = kwargs_for(spec, lambda: history[0])
    signature(NativePlayerSession).bind(**kwargs)
    assert kwargs["include_live_pp_readiness"] is True and kwargs["force_resource_safety"] is True
    assert kwargs["model_feature_version"] == 10 and kwargs["limits"].decisions == 1
    assert kwargs["battle_observer"]() is None
    history[0] = object()
    assert kwargs["battle_observer"]() is history[0]
    assert tuple(kwargs["combat_specimen_refs"]) == tuple(spec.document()["combat_specimen_refs"])


def test_callbacks_cannot_override_pp_or_policy_authority():
    spec = TeacherTrainCaseSpec.from_dict(fixture("047")["case"])
    with pytest.raises(ValueError, match="callbacks cannot override"):
        kwargs_for(spec, lambda: None, dict(include_live_pp_readiness=False))


def test_obstruction_and_leader_keep_different_native_reward_semantics():
    reward = SimpleNamespace(objective_id="defeat_blaine")
    obstruction = TeacherTrainCaseSpec.from_dict(fixture("047")["case"])
    leader = TeacherTrainCaseSpec.from_dict(fixture("049")["case"])
    assert story_binding_settings(obstruction, reward) == dict(completes_objective=False, reward=None)
    assert story_binding_settings(leader, reward) == dict(completes_objective=True, reward=reward)
    corrupted = obstruction.document()
    corrupted["exact_contract"]["victory_badge_bits"] = 64
    with pytest.raises(ValueError, match="leader reward"):
        TeacherTrainCaseSpec.from_dict(corrupted)


@pytest.mark.parametrize("mutation", ["pp", "time", "other_readiness", "challenge", "private_order", "selected"])
def test_full_menu_gate_rejects_unexplained_changes(mutation):
    data = fixture("047")
    if mutation == "pp":
        data["pp"]["party_slots"][0][0][0] -= 1
    elif mutation == "time":
        readiness = data["observed"]["candidates"][0]["readiness"]
        readiness["values"][readiness["names"].index("budget.seconds")] = 1.1
    elif mutation == "other_readiness":
        readiness = data["observed"]["candidates"][0]["readiness"]
        index = next(i for i, name in enumerate(readiness["names"]) if name not in ("current.pp_known", "current.pp_fraction", "budget.seconds"))
        readiness["values"][index] += .01
    elif mutation == "challenge":
        data["observed"]["candidates"][2]["challenge"]["median_level_deficit"] = .5
    elif mutation == "private_order":
        data["bindings"][0], data["bindings"][1] = data["bindings"][1], data["bindings"][0]
    else:
        data["bindings"][2]["binding_ref"] = "pokemon.red:story-battle:wrong"
    with pytest.raises(ValueError):
        validate_retained_menu(TeacherTrainCaseSpec.from_dict(data["case"]), data["prior"], data["observed"], data["bindings"], data["pp"])


def test_no_unavailable_private_peer_parity_is_claimed_for_049():
    data = fixture("049")
    data["bindings"][0]["binding_ref"] = "pokemon.red:owned-machine:unretained-private-peer"
    result = validate_retained_menu(TeacherTrainCaseSpec.from_dict(data["case"]), data["prior"], data["observed"], data["bindings"], data["pp"])
    assert result["private_all_binding_parity_claim"] is False


def test_observed_boundary_is_retained_before_failure_with_named_coordinates():
    case = fixture("049")["case"]
    observed = dict(source_sha256=case["source_sha256"], combat_specimen_refs=case["combat_specimen_refs"][::-1],
                    map_id=166, player_x=4, player_y=12, inputs=0, frames=0, pressed_buttons=[])
    receipts = []
    with pytest.raises(ValueError, match="role order"):
        validate_source_boundary(TeacherTrainCaseSpec.from_dict(case), observed, receipts.append)
    assert receipts == [observed] and receipts[0]["player_x"] == 4 and receipts[0]["player_y"] == 12
    observed["player_x"] = 12
    assert receipts[0]["player_x"] == 4


def test_zero_emulator_preflight_uses_real_shared_kwargs_factory(tmp_path, monkeypatch):
    import hashlib
    from datetime import datetime, timezone, timedelta
    from pokemon_red_completion import red_teacher_preflight as preflight
    from pokemon_red_completion import red_player_package, red_player_model, living_dex_option_value
    from pokemon_red_completion.emulator import PyBoyAdapter
    data = fixture("047")
    plan, row = data["plan"], data["source_row"]
    payload = b"synthetic source bytes for ROM-free preflight"
    state_sha = hashlib.sha256(payload).hexdigest()
    plan["source_sha256"] = state_sha
    plan["teacher_case"]["source_sha256"] = state_sha
    row["condition"] = plan["condition"] = "synthetic-train"
    row["fit_allowed"] = True
    def file(name, value, raw=False):
        path = tmp_path / name
        path.write_bytes(value if raw else json.dumps(value).encode())
        return str(path)
    plan["source"] = file("source.state", payload, raw=True)
    envelope = dict(state_sha256=state_sha)
    plan["source_envelope"] = file("envelope.json", envelope)
    plan["assisted_progress"] = file("teacher.json", dict(envelope=envelope, partition="train", campaign_eligible=False))
    plan["source_catalog"] = file("catalog.json", dict(metadata_gate_passed=True, sources=[row]))
    plan["source_parent_authentication"] = file("parent.json", dict(terminal_sha256=state_sha, **{key: True for key in
        ("passed", "all_original_processes_absent", "controls_released", "preinput_verified", "supervisor_cgroup_empty", "windows_parents_absent")}))
    plan["retained_source_custody"] = file("custody.json", dict(scope="synthetic"))
    plan["cutoff_utc"] = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    plan.update(pins={}, package=str(tmp_path / "synthetic-package.json"), package_sha256="a" * 64,
        goal_model_record=dict(path=str(tmp_path / "synthetic-model.json")), goal_model_sha256="b" * 64,
        zero_extended_goal_model_sha256="c" * 64)
    monkeypatch.setattr(PyBoyAdapter, "__init__", lambda *args, **kwargs: pytest.fail("preflight constructed emulator"))
    monkeypatch.setattr(red_player_package, "bind_player_package", lambda *args, **kwargs: None)
    monkeypatch.setattr(red_player_model, "load_player_goal_model_record", lambda *args, **kwargs: SimpleNamespace(model=object()))
    monkeypatch.setattr(living_dex_option_value, "upgrade_option_value_model_for_move_change", lambda model: SimpleNamespace(model_sha256="c" * 64))
    seen = []
    original = preflight.build_teacher_session_kwargs
    def observed_factory(*args, **kwargs):
        result = original(*args, **kwargs)
        seen.append(result)
        return result
    monkeypatch.setattr(preflight, "build_teacher_session_kwargs", observed_factory)
    result = preflight.preflight_direct(plan, plan_sha256="d" * 64, worker_sha256="e" * 64,
        loader_definitions={"validate_diagnostic_startup": lambda *args: 60}, output=tmp_path)
    assert result["passed"] and result["emulators"] == result["loads"] == result["inputs"] == 0
    assert len(seen) == 1 and seen[0]["include_live_pp_readiness"] is True
    assert seen[0]["force_resource_safety"] is True and seen[0]["battle_observer"]() is None
