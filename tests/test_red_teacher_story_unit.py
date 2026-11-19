"""ROM-free contract tests for the proposed existing-entry noncombat mode."""

import json
from dataclasses import replace
from datetime import UTC
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.observation import EVENT_FLAG_BYTES, ItemId
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.red_teacher_story_unit import (
    SCHEMA,
    TeacherStoryUnitCaseSpec,
    authenticate_story_unit_source,
    require_mansion_start,
    verify_partial_unit_row,
)


def case(state="1" * 64, assignment="2" * 64):
    return dict(
        schema=SCHEMA,
        mode="mansion_partial_switch",
        partition="train",
        role="train_sampling",
        source_state_sha256=state,
        historical_assignment_id=assignment,
        historical_root_lineage_id="red-scenario-root-" + assignment,
        objective_id="obtain_secret_key",
        approach=None,
        unit=dict(
            kind="events",
            map_id=215,
            events=[632],
            story_unit_scope=OptionStoryUnit("interaction", True).public_dict(),
        ),
        maximum_actions=1800,
        maximum_frames=180000,
        native_seconds=180,
    )


def test_case_roundtrip_and_legacy_combat_contract_unchanged():
    from pokemon_red_completion.red_teacher_case import TeacherTrainCaseSpec

    value = case()
    assert TeacherStoryUnitCaseSpec.from_dict(value).document() == value
    with pytest.raises(ValueError):
        TeacherTrainCaseSpec.from_dict(value)


@pytest.mark.parametrize(
    "fault",
    [
        "partition",
        "role",
        "terminal",
        "movement",
        "map",
        "event",
        "objective",
        "family",
        "native_cap",
        "bool_cap",
        "extra",
        "mode",
    ],
)
def test_noncombat_scope_falsifiers(fault):
    value = case()
    if fault == "partition":
        value["partition"] = "development"
    elif fault == "role":
        value["role"] = "benchmark"
    elif fault == "terminal":
        value["unit"]["story_unit_scope"]["requires_further_selected_unit"] = False
    elif fault == "movement":
        value["unit"]["story_unit_scope"]["mode"] = "movement"
    elif fault == "map":
        value["unit"]["map_id"] = 198
    elif fault == "event":
        value["unit"]["events"] = [1632]
    elif fault == "objective":
        value["objective_id"] = "defeat_blaine"
    elif fault == "family":
        value["historical_root_lineage_id"] = "independent-new-root"
    elif fault == "native_cap":
        value["native_seconds"] = 181
    elif fault == "bool_cap":
        value["maximum_actions"] = True
    elif fault == "mode":
        value["mode"] = "observed_story_obstruction"
    else:
        value["trainer_identity"] = [239, 39, 1]
    with pytest.raises(ValueError):
        TeacherStoryUnitCaseSpec.from_dict(value)
    with pytest.raises(ValueError):
        TeacherStoryUnitCaseSpec(json.dumps(value, sort_keys=True, separators=(",", ":")))


def source_plan(tmp_path):
    from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
    from pokemon_red_completion.strategic_navigation_protocol import StrategicNavigationExecution
    from pokemon_red_completion.strategic_navigation_scenarios import (
        load_strategic_navigation_scenario_registry,
    )

    package = tmp_path / "package"
    checkout = package / "checkout"
    configs = checkout / "configs"
    configs.mkdir(parents=True)
    project = Path(__import__("pokemon_red_completion").__file__).resolve().parents[2]
    for name in (
        "red-strategic-navigation-scenarios-v2.json",
        "red-strategic-navigation-scenarios-v2.digest.json",
    ):
        (configs / name).write_bytes((project / "configs" / name).read_bytes())
    registry = load_strategic_navigation_scenario_registry(checkout)
    scenario = registry.scenario("red-strategic-scenario-v2-041-train")
    payload = b"synthetic unit-test bytes: never an emulator source"
    envelope = CapturedProgressEnvelope(
        sha256(payload).hexdigest(),
        "unit-test-train",
        "synthetic contract test",
        len(scenario.completed_objective_ids),
        312,
        scenario.completed_objective_ids,
    )
    execution = StrategicNavigationExecution(*(["3" * 64] * 5), source_commit="4" * 40)
    assignment = registry.learning_assignment(
        scenario.scenario_id, capture=envelope, execution=execution
    )
    metadata = dict(
        collection=dict(
            assignment_id=assignment.assignment_id,
            attempt=dict(attempts_per_slot=1, counted=True),
            capture=dict(
                state_sha256=envelope.state_sha256,
                envelope_sha256=assignment.capture_envelope_sha256,
            ),
            scenario=dict(
                scenario_id=scenario.scenario_id,
                scenario_sha256=scenario.scenario_sha256,
                partition="train",
            ),
            registry_sha256=registry.registry_sha256,
        ),
        split=dict(partition="train", root_lineage_id=assignment.root_lineage_id),
        configuration=dict(scenario_rehearsal=False),
        source=dict(git_commit=execution.source_commit),
    )
    episode = json.dumps(dict(episode_id=assignment.episode_id, metadata=metadata)).encode() + b"\n"
    manifest = dict(
        status="complete",
        episode_id=assignment.episode_id,
        files=[
            dict(
                filename="episode.jsonl",
                records=1,
                bytes=len(episode),
                sha256=sha256(episode).hexdigest(),
            )
        ],
    )
    execution_dict = dict(
        source_bundle_sha256=execution.source_bundle_sha256,
        behavior_configuration_sha256=execution.behavior_configuration_sha256,
        objective_graph_sha256=execution.objective_graph_sha256,
        decision_contract_sha256=execution.decision_contract_sha256,
        teacher_execution_sha256=execution.teacher_execution_sha256,
        schema="historical-test",
    )
    files = dict(
        state=payload,
        envelope=json.dumps(envelope.to_dict()).encode(),
        episode=episode,
        manifest=json.dumps(manifest).encode(),
        collection_registry=json.dumps(dict(execution=execution_dict)).encode(),
    )
    refs = {}
    pins = {}
    for key, value in files.items():
        p = tmp_path / key
        p.write_bytes(value)
        refs[key] = dict(path=str(p), sha256=sha256(value).hexdigest())
        pins[str(p)] = refs[key]["sha256"]
    return dict(
        teacher_case=case(envelope.state_sha256, assignment.assignment_id),
        historical_train_source=refs,
        pins=pins,
        source=refs["state"]["path"],
        source_envelope=refs["envelope"]["path"],
        source_sha256=envelope.state_sha256,
        original_TRAIN_state_sha256=envelope.state_sha256,
        package=str(package / "PACKAGE.json"),
        copy_back=False,
        campaign_writes=False,
        fit_allowed=False,
        partition="train",
        caps=dict(emulators=1, state_loads=1, new_fits=0, outer_seconds=300),
        native_limits=dict(seconds=180),
    )


def test_positive_historical_train_assignment_reconstruction(tmp_path):
    plan = source_plan(tmp_path)
    spec, capture, payload, proof = authenticate_story_unit_source(plan)
    assert (
        spec.document() == plan["teacher_case"]
        and capture.state_sha256 == sha256(payload).hexdigest()
    )
    assert proof["partition"] == "train" and proof["old_slot_reopened"] is False
    assert proof["independent_origin"] is False and proof["complete_genesis_dag_known"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "rehearsal",
        "heldout",
        "wrong_family",
        "wrong_state",
        "unsealed",
        "changed_bytes",
        "copyback",
        "fit",
    ],
)
def test_source_role_and_custody_falsifiers(tmp_path, fault):
    plan = source_plan(tmp_path)
    if fault in ("rehearsal", "heldout", "wrong_family"):
        p = Path(plan["historical_train_source"]["episode"]["path"])
        doc = json.loads(p.read_bytes())
        if fault == "rehearsal":
            doc["metadata"]["collection"]["attempt"]["counted"] = False
        elif fault == "heldout":
            doc["metadata"]["split"]["partition"] = "validation"
        else:
            doc["metadata"]["split"]["root_lineage_id"] = "another-root"
        p.write_bytes(json.dumps(doc).encode() + b"\n")
        manifest_path = Path(plan["historical_train_source"]["manifest"]["path"])
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"][0].update(
            bytes=p.stat().st_size, sha256=sha256(p.read_bytes()).hexdigest()
        )
        manifest_path.write_bytes(json.dumps(manifest).encode())
        for name in ("episode", "manifest"):
            ref = plan["historical_train_source"][name]
            ref["sha256"] = sha256(Path(ref["path"]).read_bytes()).hexdigest()
            plan["pins"][ref["path"]] = ref["sha256"]
    elif fault == "wrong_state":
        plan["teacher_case"]["source_state_sha256"] = "5" * 64
    elif fault == "unsealed":
        p = Path(plan["historical_train_source"]["manifest"]["path"])
        doc = json.loads(p.read_bytes())
        doc["status"] = "failed"
        p.write_bytes(json.dumps(doc).encode())
        ref = plan["historical_train_source"]["manifest"]
        ref["sha256"] = sha256(p.read_bytes()).hexdigest()
        plan["pins"][str(p)] = ref["sha256"]
    elif fault == "changed_bytes":
        Path(plan["source"]).write_bytes(b"substituted")
    elif fault == "copyback":
        plan["copy_back"] = True
    else:
        plan["fit_allowed"] = True
    with pytest.raises(ValueError):
        authenticate_story_unit_source(plan)


@pytest.mark.parametrize(
    "fault", [None, "map", "battle", "key", "switch", "flags", "faint", "unready"]
)
def test_ready_unset_source_gate(fault):
    flags = bytearray(EVENT_FLAG_BYTES)
    raw = N(
        map_id=171,
        battle_state=0,
        bag_items=(),
        event_flags=bytes(flags),
        party_hp=(137, 53, 37, 137),
    )
    if fault == "map":
        raw.map_id = 165
    elif fault == "battle":
        raw.battle_state = 1
    elif fault == "key":
        raw.bag_items = ((int(ItemId.SECRET_KEY), 1),)
    elif fault == "switch":
        flags[632 // 8] |= 1 << (632 % 8)
        raw.event_flags = bytes(flags)
    elif fault == "flags":
        raw.event_flags = None
    elif fault == "faint":
        raw.party_hp = (0, 53, 37, 137)
    if fault:
        with pytest.raises(ValueError):
            require_mansion_start(raw, fault != "unready")
    else:
        require_mansion_start(raw, True)


def test_verified_partial_interaction_is_success_without_whole_quest_gain(tmp_path):
    from test_red_story_approach_curriculum import approach_records

    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_native_curriculum import (
        SCOPED_STORY_UNIT_CONTRACT,
        SCOPED_STORY_UNIT_OUTCOME_SCHEMA,
        SCOPED_STORY_UNIT_PLAN_SCHEMA,
        reconstruct_native_curriculum,
    )

    plan, result = approach_records(tmp_path)
    plan.update(
        schema=SCOPED_STORY_UNIT_PLAN_SCHEMA,
        contract=SCOPED_STORY_UNIT_CONTRACT,
        story_unit_scope=OptionStoryUnit("interaction", True).public_dict(),
    )
    result.update(
        schema=SCOPED_STORY_UNIT_OUTCOME_SCHEMA, declaration_sha256=canonical_sha256(plan)
    )
    row = reconstruct_native_curriculum(plan, result)
    assert verify_partial_unit_row(row) is row
    with pytest.raises(ValueError):
        verify_partial_unit_row(replace(row, features=row.features[:-4] + (1.0, 1.0, 0.0, 1.0)))


def test_teacher_offer_keeps_genuine_alternative_and_old_story_is_replaced():
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
    from pokemon_red_completion.red_teacher_story_unit import prepend_teacher_unit

    old = ExecutableGoalBinding(
        "old-story", GoalKind.ADVANCE_STORY, 0.1, 0.1, lambda: None, lambda _: None
    )
    restore = ExecutableGoalBinding(
        "actual-restore", GoalKind.RESTORE_TEAM, 0.2, 0.1, lambda: None, lambda _: None
    )
    unit = replace(
        old,
        binding_ref="observed-unit",
        story_approach_only=True,
        story_objective_ref="obtain_secret_key",
        story_unit=OptionStoryUnit("interaction", True),
    )
    original = GoalBindingSet((old.opportunity, restore.opportunity), (old, restore))
    revised = prepend_teacher_unit(original, unit)
    assert revised.opportunities == (unit.opportunity, restore.opportunity)
    assert revised.bindings == (unit, restore)
    assert original.opportunities == (old.opportunity, restore.opportunity)


def test_noncombat_route_uses_real_constructor_and_grants_no_battler(monkeypatch):
    from test_red_training_ground_route import _world

    from pokemon_red_completion.red_teacher_story_unit import build_noncombat_story_route
    from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition

    base = RedVermilionGroundTransition(rom=b"fixture", route_world=_world())
    monkeypatch.setattr(RedVermilionGroundTransition, "from_rom", lambda rom: base)
    route = build_noncombat_story_route(b"fixture")
    assert route.trainer_binding_factory is None
    assert 1 <= route.maximum_learned_trainers <= 32
    assert route.maximum_flees == 16 and route.full_event_offsets and route.observe_terrain


@pytest.mark.parametrize(
    "fault", [None, "missing_origin", "wrong_origin", "missing_cost", "invalid_cost"]
)
def test_preflight_requires_closeout_metadata_before_native(monkeypatch, tmp_path, fault):
    from datetime import datetime, timedelta

    from pokemon_red_completion import red_teacher_story_unit as unit

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "condition": "partial",
                        "source_partition": "train",
                        "role": "train_sampling",
                        "historical_root_lineage_id": "root",
                    }
                ]
            }
        )
    )
    custody = tmp_path / "custody.json"
    custody.write_text("{}")
    plan = {
        "cutoff_utc": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "pins": {},
        "source_catalog": str(catalog),
        "condition": "partial",
        "retained_source_custody": str(custody),
        "shared_origin_id": "root",
        "separate_acquisition_cost": {"status": "unknown historical"},
    }
    monkeypatch.setattr(
        unit,
        "authenticate_story_unit_source",
        lambda _: (None, None, b"fixture", {"root_lineage_id": "root"}),
    )
    if fault == "missing_origin":
        plan.pop("shared_origin_id")
    elif fault == "wrong_origin":
        plan["shared_origin_id"] = "another"
    elif fault == "missing_cost":
        plan.pop("separate_acquisition_cost")
    elif fault == "invalid_cost":
        plan["separate_acquisition_cost"] = 0
    definitions = {"validate_diagnostic_startup": lambda *_: 60}
    if fault is None:
        assert unit._validate_common(plan, definitions)[-1] == 60
    else:
        with pytest.raises(ValueError):
            unit._validate_common(plan, definitions)


def test_direct_teacher_reuses_interaction_executor_without_story_corridor(monkeypatch):
    from pokemon_red_completion import red_player_lesson, red_player_mansion
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
    from pokemon_red_completion.player_option_challenge import OptionChallenge
    from pokemon_red_completion.red_teacher_story_unit import existing_unit_offer

    binding = ExecutableGoalBinding(
        "pokemon.red:mansion-interaction:source",
        GoalKind.ADVANCE_STORY,
        0.1,
        0.1,
        lambda: None,
        lambda _: None,
        story_objective_ref="obtain_secret_key",
        story_approach_only=True,
        story_unit=OptionStoryUnit("interaction", True),
    )
    observed = []
    before, lesson, runtime, actions, route = object(), {}, object(), object(), object()
    monkeypatch.setattr(
        red_player_lesson, "capture_player_lesson_snapshot", lambda r: (before, lesson)
    )

    def existing(r, a, **kwargs):
        observed.append((r, a, kwargs))
        return binding, OptionChallenge(False, False, 0.0, 0.0, 0.0)

    monkeypatch.setattr(red_player_mansion, "_mansion_interaction_option", existing)
    result = existing_unit_offer(runtime, actions, phase="interaction", route=route)
    assert result[0] is binding
    assert observed == [
        (
            runtime,
            actions,
            dict(
                route=route,
                before=before,
                lesson=lesson,
                switch=False,
                drop=False,
                target_map=red_player_mansion.UPPER_STATUE[0],
                at=red_player_mansion.UPPER_STATUE[1],
                objective="obtain_secret_key",
            ),
        )
    ]
    with pytest.raises(ValueError):
        existing_unit_offer(runtime, actions, phase="approach", route=route)


def test_direct_teacher_disallows_separate_setup_lesson():
    value = case()
    value["approach"] = dict(kind="arrival", map_id=215, at=None)
    with pytest.raises(ValueError):
        TeacherStoryUnitCaseSpec.from_dict(value)
