"""Existing matched venue TRAIN recorder through the shared teacher entry.

The complete-evolution body reuses the qualified helper-only recorder. This
adapter adds exact source ancestry, prospective geometry and common cleanup.
"""

import hashlib
from .party_development_rank import PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID
import json
import signal
import time
import traceback

from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "pokemon.red.native-venue-geometry-TRAIN-case.v1"
HIGH_LEVEL_SCHEMA = "pokemon.red.native-venue-workload-TRAIN-case.v2"

# Disclosed teacher-only contrasts; identifiers never become policy features.
_DIVERSITY_WORKLOAD_FIXTURES = {'geodude30_to31': (169, 39, 30, False),
 'geodude40_to41': (169, 39, 40, False),
 'machop30_to31': (106, 41, 30, False),
 'machop40_to41': (106, 41, 40, False),
 'machop35_to36': (106, 41, 35, True),
 'sandshrew30_to31': (96, 97, 30, False),
 'sandshrew40_to41': (96, 97, 40, False),
 'poliwag30_to31': (71, 110, 30, False),
 'poliwag40_to41': (71, 110, 40, False),
 'poliwag35_to36': (71, 110, 35, True)}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def is_venue_case(plan):
    return plan.get("schema") in {SCHEMA, HIGH_LEVEL_SCHEMA}


def authenticate_exposed_venue_source(plan):
    """Read a pinned historical capture as exposed evaluation, never new TRAIN."""
    from .captured_progress import parse_captured_progress

    old = json.loads(Path(plan["historical_source_plan"]).read_bytes())
    (source,) = old["sources"]
    (item,) = plan["sources"]
    payload = Path(plan["source"]).read_bytes()
    envelope = Path(plan["source_envelope"]).read_bytes()
    capture = parse_captured_progress(envelope, state_bytes=payload)
    if (
        plan.get("validation_role") != "related-DEV-matched-component-no-admission"
        or source["execution_partition"] != "development"
        or source["declared_partition"] != "train"
        or item["declared_partition"] != "train"
        or item["execution_partition"] != "development"
        or item["xp_condition"] != "original"
        or item["venue_mode"] != "teacher"
        or source["path"] != plan["source"]
        or source["envelope"] != plan["source_envelope"]
        or source["state_sha256"] != capture.state_sha256
        or source["envelope_sha256"] != sha(plan["source_envelope"])
        or source["assigned_lineage"] != item["assigned_lineage"]
        or set(source["verified_objectives"]) != set(capture.verified_objective_ids)
        or plan["fit_allowed"]
        or plan["party_venue_fit_eligible"]
    ):
        raise ValueError("exposed evaluation source differs or attempted TRAIN admission")
    for name in [
        plan["source"],
        plan["source_envelope"],
        plan["historical_source_plan"],
        plan["evaluation_protocol"],
    ]:
        if plan["pins"].get(name) != sha(name):
            raise ValueError("exposed evaluation source is not pinned")
    return (
        capture,
        payload,
        dict(
            partition="development",
            original_declared_partition="train",
            original_state_sha256=capture.state_sha256,
            root_lineage_id=item["assigned_lineage"],
            independent_origin=False,
            historically_exposed=True,
            complete_genesis_dag_known=False,
            old_slot_reopened=False,
            fit_eligible=False,
        ),
    )


def venue_training_faint_recovery(plan):
    """Version recovery through an explicit pinned workload-plan opt-in."""
    enabled = plan.get("recover_training_faints", False)
    if type(enabled) is not bool or (enabled and plan.get("schema") != HIGH_LEVEL_SCHEMA):
        raise ValueError("venue training faint recovery requires explicit workload scope")
    return enabled



def venue_outcome_objective(plan):
    """Bind a declared target-task objective; preserve historical default."""
    from .party_development_outcomes import (
        PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE,
        PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE,
    )

    target_task = plan.get("target_task_efficiency", False)
    if type(target_task) is not bool:
        raise ValueError("target task efficiency requires an explicit boolean")
    return (
        PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE
        if target_task
        else PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE
    )


def observed_training_faints(events):
    """Count actual recorded faint starts once,not subsequent nurse receipts."""
    count = 0
    for event in events:
        if event["kind"] != "wild_training_faint":
            continue
        n = event["payload"].get("observed_faints")
        if type(n) is not int or n != 1:
            raise ValueError("native training faint evidence differs")
        count += n
    return count


def workload_trainee_species(item, *, validation):
    """Exact opt-in teacher fixtures;never a final-player species substitution."""
    profile = item.get("trainee_profile", "diglett")
    if profile == "diglett":
        return 59, 118
    level = item.get("fixture_level")
    if (profile == "dragonair54_to55" and validation
            and type(level) is int and level == 54):
        return 89, 66
    if (profile == "drowzee30_to31" and type(level) is int and level == 30):
        return 48, 129
    if isinstance(profile, str) and profile in _DIVERSITY_WORKLOAD_FIXTURES:
        source, target, declared_level, evaluation_only = _DIVERSITY_WORKLOAD_FIXTURES[profile]
        if type(level) is int and level == declared_level and (validation or not evaluation_only):
            return source, target
    raise ValueError("alternate trainee requires its exact declared workload profile")


def require_workload_collection_target(cartridge, target_species_id):
    """Reject version-ineligible teacher tasks before constructing a guest."""
    from .red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_ref

    national = cartridge.species(target_species_id).national_number
    if red_species_ref(national) not in RED_SOLO_COLLECTION_CONTRACT.target_species:
        raise ValueError("teacher workload target is outside the Red completion contract")


def validate_diversity_fixture_binding(item):
    """Require an exact source census and explicit slot before teacher input."""
    import re

    slot = item.get("fixture_source_slot")
    digest = item.get("fixture_source_party_sha256")
    if type(slot) is not int or not 1 <= slot <= 6 or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("diversity fixture requires its pinned original party and slot")
    return slot


def workload_fixture_target(party, item, *, high_level):
    profile = item.get("trainee_profile", "diglett")
    if profile in _DIVERSITY_WORKLOAD_FIXTURES:
        from dataclasses import asdict
        from .provenance import canonical_sha256

        slot = validate_diversity_fixture_binding(item)
        if not high_level or slot > party.size or canonical_sha256(asdict(party)) != item["fixture_source_party_sha256"]:
            raise ValueError("diversity fixture source party differs before setup")
        return party.members[slot - 1]
    targets = tuple(m for m in party.members if m.species_id == 59)
    assert len(targets) == 1
    target = targets[0]
    assert target.level == 22
    return target


def authenticate_workload_venue_source(plan):
    """Reuse original capture/registry proofs for new isolated TRAIN outcomes."""
    from .captured_progress import load_captured_progress
    from .goal_manager_protocol import parse_goal_manager_registry
    from .party_development_outcome_learning import (
        canonical_party_development_outcome_model_sha256,
        load_party_development_outcome_model,
    )

    venue_training_faint_recovery(plan)
    venue_outcome_objective(plan)
    if datetime.now(UTC) >= datetime.fromisoformat(plan["cutoff_utc"]):
        raise ValueError("expired workload venue case")
    for path, digest in plan["pins"].items():
        if sha(path) != digest:
            raise ValueError("workload input pin differs: " + path)
    if plan["source_authentication"] not in plan["pins"]:
        raise ValueError("TRAIN source authentication is not pinned")
    proof = json.loads(Path(plan["source_authentication"]).read_bytes())
    if (
        proof.get("schema") != "pokemon.authenticated-historical-goal-TRAIN-source.v1"
        or not proof.get("passed")
        or proof.get("partition") != "train"
    ):
        raise ValueError("historical TRAIN source proof differs")
    for key in ("registry", "source", "envelope", "historical_preflight", "prior_authentication"):
        item = proof[key]
        if plan["pins"].get(item["path"]) != item["sha256"] or sha(item["path"]) != item["sha256"]:
            raise ValueError("historical source proof is not pinned")
    registry = parse_goal_manager_registry(Path(proof["registry"]["path"]).read_bytes())
    assignment = registry.assignment(proof["checkpoint_id"])
    capture = load_captured_progress(Path(plan["source_envelope"]), state_path=Path(plan["source"]))
    if (
        assignment.partition != "train"
        or assignment.root_lineage_id != proof["root_lineage_id"]
        or capture.checkpoint_id != proof["checkpoint_id"]
        or capture.state_sha256 != proof["source"]["sha256"]
        or capture.state_sha256 != plan["source_sha256"]
        or registry.registry_sha256 != proof["registry_sha256"]
    ):
        raise ValueError("original TRAIN assignment differs")
    preflight = json.loads(Path(proof["historical_preflight"]["path"]).read_bytes())
    if (
        not preflight["passed"]
        or preflight["actions_executed"] != 0
        or preflight["assignment_id"] != assignment.assignment_id
        or preflight["state_sha256"] != capture.state_sha256
    ):
        raise ValueError("historical source preflight differs")
    if (
        plan["caps"]["emulators"] != 1
        or plan["caps"]["state_loads"] != 1
        or not 0 < plan["native_limits"]["seconds"] <= 420
        or plan["caps"]["outer_seconds"] > 600
    ):
        raise ValueError("workload physical allowance differs")
    model = load_party_development_outcome_model(
        plan["venue_model_path"], expected_sha256=plan["venue_model_file_sha256"]
    )
    if canonical_party_development_outcome_model_sha256(model) != plan["venue_model_sha256"]:
        raise ValueError("workload venue model identity differs")
    validation = plan.get("validation_role") is not None
    if validation:
        if plan["validation_role"] not in {
            "exposed-TRAIN-component-no-admission",
            "exposed-TRAIN-component-comparison-only",
        }:
            raise ValueError("workload validation role differs")
        fit_path = plan["validation_fit_result"]
        if plan["pins"].get(fit_path) != sha(fit_path):
            raise ValueError("workload validation fit is not pinned")
        fit = json.loads(Path(fit_path).read_bytes())
        comparison_only = _comparison_only_venue_fit(plan, fit_path, fit, capture.state_sha256)
        if (
            not fit["passed"]
            or (not fit["accepted"] and not comparison_only)
            or plan["party_venue_fit_eligible"]
            or fit["model_sha256"] != plan["venue_model_sha256"]
            or fit["model"]["sha256"] != plan["venue_model_file_sha256"]
        ):
            raise ValueError("workload validation candidate differs")
    (item,) = plan["sources"]
    if (
        item["declared_partition"] != "train"
        or item["execution_partition"] != "train"
        or item["assigned_lineage"] != assignment.root_lineage_id
        or item["state_sha256"] != capture.state_sha256
        or item["venue_mode"] not in ({"teacher", "model"} if validation else {"teacher"})
        or type(item["assigned_venue_index"]) is not int
        or item["assigned_venue_index"] not in range(3)
        or type(item["fixture_level"]) is not int
        or not 30 <= item["fixture_level"] <= 55
        or plan["allow_direct_evolution"] is not True
        or plan["venue_symbols"]
        != ["ROUTE_11_TRAINING_VENUE", "DIGLETTS_CAVE_TRAINING_VENUE", "MANSION_TRAINING_VENUE"]
        or plan["copy_back"]
        or plan["campaign_writes"]
        or plan["caps"]["new_fits"] != 0
    ):
        raise ValueError("workload TRAIN task scope differs")
    _, target_species_id = workload_trainee_species(item, validation=validation)
    from .red_battle_practice_cartridge import RedPracticeCartridge
    package_manifest = json.loads(Path(plan["package"]).read_bytes())
    rom_path = Path(plan["package"]).parent / "data/storage-migration/roms/PokemonRoms/Pokemon Red.gb"
    if package_manifest["pins"].get(str(rom_path)) != sha(rom_path):
        raise ValueError("teacher workload needs its exact pinned Red cartridge")
    require_workload_collection_target(RedPracticeCartridge(rom_path.read_bytes()), target_species_id)
    if item.get("trainee_profile") in _DIVERSITY_WORKLOAD_FIXTURES:
        validate_diversity_fixture_binding(item)
    if not validation and (
        assignment.root_lineage_id in model.outcome_training_root_lineage_ids
        or capture.state_sha256 in model.outcome_training_state_sha256
    ):
        raise ValueError("venue learner already consumed workload TRAIN source")
    return (
        capture,
        Path(plan["source"]).read_bytes(),
        dict(
            partition="train",
            original_state_sha256=capture.state_sha256,
            root_lineage_id=assignment.root_lineage_id,
            independent_origin=False,
            complete_genesis_dag_known=False,
            old_slot_reopened=False,
        ),
    )


def authenticate_venue_source(plan):
    venue_training_faint_recovery(plan)
    from .party_development_outcome_learning import (
        canonical_party_development_outcome_model_sha256,
        load_party_development_outcome_model,
    )
    from .red_teacher_story_unit import authenticate_story_unit_source

    if plan.get("schema") == HIGH_LEVEL_SCHEMA:
        return authenticate_workload_venue_source(plan)
    if datetime.now(UTC) >= datetime.fromisoformat(plan["cutoff_utc"]):
        raise ValueError("expired venue case")
    for p, h in plan["pins"].items():
        if sha(p) != h:
            raise ValueError("venue input pin differs: " + p)
    # Reuse the already-qualified historical assignment checker only for its
    # source proof. Its old collector purpose/cutoff grants no new execution.
    anchor = json.loads(Path(plan["historical_source_plan"]).read_bytes())
    if plan.get("source_kind") == "exposed_historical_development":
        capture, payload, proof = authenticate_exposed_venue_source(plan)
    else:
        _, capture, payload, proof = authenticate_story_unit_source(anchor)
    if (
        sha(plan["source"]) != capture.state_sha256
        or plan["original_TRAIN_state_sha256"] != capture.state_sha256
        or plan["shared_origin_id"] != proof["root_lineage_id"]
    ):
        raise ValueError("venue source differs from historical TRAIN proof")
    model = load_party_development_outcome_model(
        plan["venue_model_path"], expected_sha256=plan["venue_model_file_sha256"]
    )
    if canonical_party_development_outcome_model_sha256(model) != plan["venue_model_sha256"]:
        raise ValueError("venue canonical model hash differs")
    (item,) = plan["sources"]
    validation = item["venue_mode"] == "model"
    if validation:
        fit = json.loads(Path(plan["validation_fit_result"]).read_bytes())
        if (
            sha(plan["validation_fit_result"]) != plan["validation_fit_result_sha256"]
            or not fit["qualified"]
            or fit["adopted"]
            or fit["model_sha256"] != plan["venue_model_sha256"]
            or fit["model_file_sha256"] != plan["venue_model_file_sha256"]
            or item["xp_condition"] != "original"
            or plan.get("validation_role") != "exposed-TRAIN-component-no-admission"
        ):
            raise ValueError("venue model validation lacks qualified exact fit authority")
    if not validation and (
        proof["root_lineage_id"] in model.outcome_training_root_lineage_ids
        or capture.state_sha256 in model.outcome_training_state_sha256
    ):
        raise ValueError("venue learner already consumed this source")
    (item,) = plan["sources"]
    if (
        item["declared_partition"] != "train"
        or item["execution_partition"] != proof["partition"]
        or item["assigned_lineage"] != proof["root_lineage_id"]
        or item["state_sha256"] != capture.state_sha256
        or tuple(item["verified_objectives"]) != capture.verified_objective_ids
        or item["venue_mode"] not in ("teacher", "model")
        or item["xp_condition"] not in ("original", "near_next_level")
        or item["assigned_venue_index"] not in (0, 1)
        or plan["venue_symbols"]
        != (
            ["ROUTE_11_TRAINING_VENUE", "DIGLETTS_CAVE_TRAINING_VENUE", "MANSION_TRAINING_VENUE"]
            if validation and plan.get("ordinary_full_venue_menu") is True
            else ["ROUTE_11_TRAINING_VENUE", "MANSION_TRAINING_VENUE"]
        )
        or plan["allow_direct_evolution"] is not False
    ):
        raise ValueError("matched venue TRAIN task scope differs")
    if plan["copy_back"] or plan["campaign_writes"] or plan["caps"]["new_fits"] != 0:
        raise ValueError("collection scope differs")
    return capture, payload, proof


def preflight_venue(plan, *, plan_sha256, worker_sha256, loader_definitions, output):
    from inspect import signature

    from .red_level_evolution_options import enumerate_red_level_evolutions
    from .red_party_development_adapter import build_native_evolution_venue_menu
    from .red_player_package import bind_player_package

    capture, _, proof = authenticate_venue_source(plan)
    bind_player_package(Path(plan["package"]), plan["package_sha256"], history_output=Path(output))
    assert "observe_venue_decision" in signature(enumerate_red_level_evolutions).parameters
    assert "geometry_quotes" in signature(build_native_evolution_venue_menu).parameters
    return dict(
        passed=True,
        phase="preflight",
        plan_sha256=plan_sha256,
        worker_sha256=worker_sha256,
        package_sha256=plan["package_sha256"],
        source_proof=proof,
        emulators=0,
        loads=0,
        inputs=0,
        frames=0,
        fits=0,
        source_sha256=capture.state_sha256,
        native_observation_pending=True,
    )


def run_venue(plan, *, output, worker_path, loader_definitions, started, write):
    from .emulator import PyBoyAdapter
    from .executor import release_pressed_buttons
    from .red_party import PokemonRedPartyReader
    from .red_player_package import bind_player_package, package_read_guard
    from .red_teacher_story_unit import managed_teacher_guest

    out = Path(output)
    result = dict(
        passed=False,
        phase="direct",
        actions=0,
        frames=0,
        goal_attempts=0,
        heals=0,
        native_seconds=0.0,
        wild_battles=None,
        story_battles=0,
        new_fits=0,
        new_weights=0,
        copy_back=False,
        campaign_progress=False,
        teacher_selected=True,
        sources=[],
        admitted=False,
        training_admission=False,
    )
    physical = dict(
        construction_attempts=0, emulators_constructed=0, load_attempts=0, state_loads=0
    )
    result["physical_emulator_accounting"] = physical
    old_init, old_load = PyBoyAdapter.__init__, PyBoyAdapter.load_state_bytes
    old_profile = __import__("sys").getprofile()
    try:
        capture, payload, proof = authenticate_venue_source(plan)
        qualification = json.loads(Path(plan["qualification"]).read_bytes())
        assert qualification["passed"] and qualification["plan_sha256"] == sha(out / "PLAN.json")
        assert qualification["worker_sha256"] == sha(worker_path)
        bound = bind_player_package(
            Path(plan["package"]), plan["package_sha256"], history_output=out
        )
        loader_definitions["preload_verified_native_dependencies"](bound)
        package_read_guard(
            bound,
            manifest_path=Path(plan["package"]),
            output=out,
            extra_inputs=[
                str(out / "PLAN.json"),
                str(worker_path),
                plan["qualification"],
                *plan["pins"],
            ],
        )

        def one_init(self, *args, **kwargs):
            physical["construction_attempts"] += 1
            assert physical["construction_attempts"] == 1
            old_init(self, *args, **kwargs)
            physical["emulators_constructed"] += 1

        def one_load(self, state):
            physical["load_attempts"] += 1
            assert physical["load_attempts"] == 1 and state == payload
            old_load(self, state)
            physical["state_loads"] += 1

        PyBoyAdapter.__init__, PyBoyAdapter.load_state_bytes = one_init, one_load

        def timer(*_):
            raise TimeoutError("bounded venue TRAIN native allowance")

        signal.signal(signal.SIGALRM, timer)
        signal.setitimer(signal.ITIMER_REAL, plan["native_limits"]["seconds"])
        native_started = time.monotonic()
        rom = (
            Path(plan["package"]).parent / "data/storage-migration/roms/PokemonRoms/Pokemon Red.gb"
        )
        adapter = PyBoyAdapter(rom)

        def export(terminal):
            path = out / "terminal.state"
            if path.exists() and path.read_bytes() != terminal:
                write(
                    out / "TAIL-REEXPORT.json",
                    dict(old_sha256=sha(path), new_sha256=hashlib.sha256(terminal).hexdigest()),
                )
            path.write_bytes(terminal)

        with managed_teacher_guest(
            adapter,
            result,
            release=release_pressed_buttons,
            export_terminal=export,
            cancel_timer=lambda: signal.setitimer(signal.ITIMER_REAL, 0),
            clock=time.monotonic,
            native_started=native_started,
        ) as em:
            em.load_state_bytes(payload)
            assert (
                em.save_state_bytes() == payload and em.frame_count == 0 and not em.pressed_buttons
            )
            party = PokemonRedPartyReader(em).read()
            (item,) = plan["sources"]
            assert sorted(m.level for m in party.members) == item["expected_sorted_levels"]
            write(
                out / "PREINPUT-QUALIFICATION.json",
                dict(
                    passed=True,
                    source_bytes_exact=True,
                    source_state_sha256=capture.state_sha256,
                    frames=0,
                    inputs=0,
                    partition="train",
                ),
            )
            write(
                out / "LIVE-PP-PREINPUT-GATE.json",
                dict(
                    passed=True,
                    source_bytes_exact=True,
                    inputs=0,
                    frames=0,
                    party_pp=[[(m.move_id, m.current_pp) for m in p.moves] for p in party.members],
                ),
            )
            detail = execute_native_evolution(
                em, item, payload, rom, bound, plan=plan, result=result, output=out
            )
            result["sources"].append(detail)
            result["passed"] = bool(detail["settled_native_attempt"])
            if not result["passed"]:
                result.update(error=detail.get("error"), error_type=detail.get("error_type"))
            result["training_admission"] = (
                bool(detail.get("admitted_party_venue_outcomes"))
                and item["venue_mode"] == "teacher"
                and item["execution_partition"] == "train"
                and not plan.get("validation_role")
            )
    except BaseException as error:
        result.update(
            passed=False,
            error_type=type(error).__name__,
            error=str(error),
            traceback=traceback.format_exc(),
        )
    finally:
        PyBoyAdapter.__init__, PyBoyAdapter.load_state_bytes = old_init, old_load
        signal.setitimer(signal.ITIMER_REAL, 0)
        __import__("sys").setprofile(old_profile)
        result["outer_seconds"] = time.monotonic() - started
    return result


def teacher_evolution_selection(options, target_refs, candidates):
    """Select a declared TRAIN task without fabricating outer-goal alternatives."""
    from .goal_manager import GoalKind
    from .red_live_option_menu import RedLiveOptionSet
    from .red_player_support import RedPlayerSupport

    if isinstance(options, RedPlayerSupport):
        binding = options.binding
        if binding.kind is not GoalKind.EVOLVE_SPECIES or binding.binding_ref not in target_refs:
            raise ValueError("venue teacher received unrelated support")
        return binding, candidates[binding.binding_ref], None, options.public_dict()
    if not isinstance(options, RedLiveOptionSet):
        raise ValueError("venue teacher lacks a legal native task boundary")
    matches = [
        i
        for i, binding in enumerate(options.bindings)
        if binding.binding_ref in target_refs and binding.kind is GoalKind.EVOLVE_SPECIES
    ]
    if len(matches) != 1:
        raise ValueError("declared native evolution is not uniquely executable")
    index = matches[0]
    return options.binding(index), options.menu.candidates[index], index, options.menu.policy_dict()


def execute_native_evolution(
    emulator, item, original_payload, rom, manifest, *, plan, result, output
):
    OUT = Path(output)
    package = Path(plan["package"]).parent
    import hashlib
    import json
    import time
    import traceback

    from dataclasses import asdict, fields, replace

    import player_coherent_session as shared

    from pokemon_red_completion import red_goal_context as context
    from pokemon_red_completion.executor import ReadOnlyController
    from pokemon_red_completion.gen1_cartridge import evolution_graph
    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalKind,
        GoalOpportunity,
        GoalUnavailableReason,
    )
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.private_artifacts import (
        gitless_fast_path_worktree_probe,
        initialize_private_root,
    )
    from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
    from pokemon_red_completion.red_collection_teacher_learning import (
        set_isolated_training_emulator_experience,
    )
    from pokemon_red_completion.red_native_player import (
        NativeExecutionIdentity,
        NativePlayerLimits,
        NativePlayerSession,
    )
    from pokemon_red_completion.red_party import PokemonRedPartyReader
    from pokemon_red_completion.red_party_development_adapter import red_party_completion_snapshot
    from pokemon_red_completion.red_player_collection_options import (
        bind_player_collection_capabilities,
    )
    from pokemon_red_completion.red_player_field_goals import _field_ready
    from pokemon_red_completion.red_player_lesson_runtime import observe_native_player_boundary
    from pokemon_red_completion.red_player_model import load_player_goal_model_record
    from pokemon_red_completion.red_player_party_guard import (
        RedPlayerPartyGuard,
        RetainedPartyGoalStateAdapter,
    )
    from pokemon_red_completion.red_player_party_loan import _stock, restore_guarded_party_loan
    from pokemon_red_completion.red_prepared_evolution_options import prepared_stock_progress
    from pokemon_red_completion.scenario_lab import ScenarioPartition
    from pokemon_red_completion.team_training import TeamTrainingProgress

    profile = item.get("trainee_profile", "diglett")
    source_species, evolved_species = workload_trainee_species(
        item, validation=plan.get("validation_role") is not None
    )
    initial_party = PokemonRedPartyReader(emulator).read()
    high_level = plan.get("schema") == HIGH_LEVEL_SCHEMA
    target = workload_fixture_target(initial_party, item, high_level=high_level)
    trainee_index = target.slot - 1
    assert emulator.save_state_bytes() == original_payload
    if not high_level:
        assert target.slot == 3 and target.experience == 10666
    cartridge = RedPracticeCartridge(rom.read_bytes())
    xp = target.experience
    writes = ()
    if high_level:
        from .red_collection_teacher_learning import set_isolated_training_emulator_member_level

        writes = set_isolated_training_emulator_member_level(
            emulator,
            partition="train",
            isolated_training_setup=True,
            party_index=trainee_index,
            level=item["fixture_level"],
            cartridge=cartridge,
            species_id=source_species if profile != "diglett" else None,
        )
        xp = cartridge.species(source_species).experience_at_level(item["fixture_level"])
    elif item["xp_condition"] != "original":
        assert item["execution_partition"] == "train"
        floor = cartridge.species(target.species_id).experience_at_level(target.level)
        ceiling = cartridge.species(target.species_id).experience_at_level(target.level + 1)
        if item["xp_condition"] == "mid_level":
            xp = (floor + ceiling - 1) // 2
        else:
            assert item["xp_condition"] == "near_next_level"
            xp = ceiling - 1
        writes = set_isolated_training_emulator_experience(
            emulator,
            partition="train",
            isolated_training_setup=True,
            party_index=2,
            experience=xp,
            cartridge=cartridge,
        )
    conditioned_party = PokemonRedPartyReader(emulator).read()
    if high_level:
        assert all(
            new == old
            for old, new in zip(initial_party.members, conditioned_party.members, strict=True)
            if old.slot != target.slot
        )
        assert conditioned_party.members[trainee_index].level == item["fixture_level"]
        assert conditioned_party.members[trainee_index].experience == xp
    else:
        assert conditioned_party == replace(
            initial_party,
            members=tuple(
                replace(member, experience=xp) if member.slot == 3 else member
                for member in initial_party.members
            ),
        )
    assert emulator.frame_count == 0 and (not emulator.pressed_buttons)
    payload = emulator.save_state_bytes()
    payload_sha = hashlib.sha256(payload).hexdigest()
    (OUT / "setup.state").write_bytes(payload)
    setup = dict(
        schema="pokemon.red.native-evolution-TRAIN-setup.v1",
        partition="train",
        evaluation_partition=item["execution_partition"],
        original_state_sha256=item["state_sha256"],
        state_sha256=payload_sha,
        source_assignment=item["assigned_lineage"],
        teacher_only=True,
        xp_condition=item["xp_condition"],
        current_level=conditioned_party.members[trainee_index].level,
        trainee_profile=profile,
        supplied_species_id=source_species,
        target_species_id=evolved_species,
        original_species_id=target.species_id,
        fixture_interventions=(
            "level,zero stat experience,cartridge/DV-derived stats,intrinsic moves,PP,HP,status,XP"
        )
        if high_level
        else "same-level XP only",
        experience_before=target.experience,
        experience_after=xp,
        writes=list(writes),
        native_protected_party_fields_unchanged=not high_level,
        non_target_party_fields_unchanged=True,
        frames=0,
        inputs=0,
        actual_progress=False,
        old_trials_reissued=False,
    )
    (OUT / "SETUP-RECEIPT.json").write_text(json.dumps(setup, indent=2, sort_keys=True) + "\n")
    setup_sha = hashlib.sha256((OUT / "SETUP-RECEIPT.json").read_bytes()).hexdigest()
    shared.c.FROZEN_SOURCE_COMMIT = manifest["source_commit"]
    case = OUT / "runtime-case"
    case.mkdir(mode=448)
    factory0, _, holder, source = shared.assembly(
        payload,
        case,
        origin_sha=item["state_sha256"],
        partition=item["execution_partition"],
        origin_id=item["assigned_lineage"],
        objective_ids=tuple(item["verified_objectives"]),
        protect_party_species=False,
    )
    world = replace(
        shared.RedVermilionGroundTransition.from_rom(rom.read_bytes()),
        full_event_offsets=True,
        observe_terrain=True,
    ).route_world
    corridor = shared.derive_red_living_dex_wild_corridor(
        shared.RedEncounterSourceTarget("wild:Route1:grass"),
        world.terrain[int(shared.c.MapId.ROUTE_1)],
        world.local_graphs[int(shared.c.MapId.ROUTE_1)],
        cartridge=world.rom,
    )

    def factory(controller):
        runtime = factory0(controller)
        holder["fixture_roles"] = (
            tuple((ref for index, ref in enumerate(holder["refs"]) if index != trainee_index)),
            frozenset((holder["refs"][trainee_index],)),
        )
        guard = RedPlayerPartyGuard.from_rom(
            rom.read_bytes(),
            controller,
            loanable_refs=holder["fixture_roles"][1],
            storage_reader=runtime.reader,
        )
        adapter = RetainedPartyGoalStateAdapter(
            **{
                field.name: getattr(runtime.adapter, field.name)
                for field in fields(runtime.adapter)
                if field.name != "party_guard"
            },
            party_guard=guard,
        )
        runtime = bind_player_collection_capabilities(
            replace(runtime, adapter=adapter),
            seed_corridor=corridor,
            add_capture_preparation_support=False,
        )
        runtime = replace(
            runtime,
            evolution_training_faint_recovery=venue_training_faint_recovery(plan),
            evolution_settlement=lambda port: restore_guarded_party_loan(runtime, port, world),
        )
        holder["runtime"] = runtime
        guard.verify_active_roster_restored()
        return runtime

    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.party_development_outcome_learning import (
        canonical_party_development_outcome_model_sha256,
        load_party_development_outcome_model,
    )
    from pokemon_red_completion.red_level_evolution_options import enumerate_red_level_evolutions
    from pokemon_red_completion.red_live_option_menu import supplemental_live_option

    venue_model = load_party_development_outcome_model(
        plan["venue_model_path"], expected_sha256=plan["venue_model_file_sha256"]
    )
    assert (
        canonical_party_development_outcome_model_sha256(venue_model) == plan["venue_model_sha256"]
    )
    from pokemon_red_completion.red_native_boxed_evolution import level_evolution_edges

    edges = level_evolution_edges(world.rom)
    assert any(s == source_species and t == evolved_species for s, t, _ in edges)
    excluded_helpers = frozenset((s for s, _, _ in edges))
    all_venues = tuple(getattr(context, name) for name in plan["venue_symbols"])
    decision_holder = {}

    def observe_decision(native_observation, bound_venues, actual_source, actual_target):
        from pokemon_red_completion.gen1_cartridge import evolution_graph
        from pokemon_red_completion.party_development_catalog import (
            PartyDevelopmentProspectiveBinding,
        )
        from pokemon_red_completion.party_development_venue_priors import (
            PartyDevelopmentVenuePriorRegistry,
        )
        from pokemon_red_completion.red_native_boxed_evolution import (
            native_evolution_encounter_supported,
            wild_tables,
        )
        from pokemon_red_completion.red_party_development_adapter import (
            build_native_evolution_venue_menu,
            red_party_completion_snapshot,
        )
        from pokemon_red_completion.red_team_training import collection_finisher
        from pokemon_red_completion.scenario_lab import ScenarioPartition

        assert (actual_source, actual_target) == (source_species, evolved_species) and (
            not decision_holder
        )
        native_before = native_observation
        assert native_before.party == PokemonRedPartyReader(emulator).read()
        trainee = next(m for m in native_before.party.members if m.species_id == source_species)
        tables = wild_tables(world.rom)
        inventory = tuple(
            v
            for v in all_venues
            if (
                v.native_transport_ready is None
                or v.native_transport_ready(native_before.party) is True
            )
            and tables.get(v.map_id)
            and (
                collection_finisher(
                    native_before.party,
                    source_species,
                    context.MANSION_TEAM_POLICY,
                    enemy_level=v.band.rare_maximum_encounter_level
                    or v.band.maximum_encounter_level,
                    resources=False,
                    excluded_helper_species=excluded_helpers,
                )
                is not None
            )
            and all(
                (
                    native_evolution_encounter_supported(
                        native_before.party,
                        source_species,
                        context.MANSION_TEAM_POLICY,
                        level,
                        species,
                        allow_guarded_escapes=True,
                        excluded_helper_species=excluded_helpers,
                    )
                    for level, species in tables[v.map_id]
                )
            )
        )
        assert tuple(v.map_id for v in inventory) == tuple(v.map_id for v in all_venues)
        from pokemon_red_completion.red_native_venue_geometry import (
            quote_native_evolution_venue_geometry,
        )

        quotes = quote_native_evolution_venue_geometry(
            holder["runtime"], world, native_before, inventory
        )
        assert all(q.travel_steps is not None and q.recovery_steps is not None for q in quotes), (
            "Both geometry groups must be known before TRAIN input"
        )
        assert len({(q.travel_steps, q.recovery_steps) for q in quotes}) > 1, (
            "No geometry variation for this contrast"
        )
        (OUT / "PROSPECTIVE-GEOMETRY.json").write_text(
            json.dumps(
                dict(
                    geometry=[
                        dict(
                            venue=v.band.identity, planned_entry=q.planned_entry, **q.public_dict()
                        )
                        for v, q in zip(inventory, quotes, strict=True)
                    ],
                    source_state_sha256=hashlib.sha256(emulator.save_state_bytes()).hexdigest(),
                    before_outcomes=True,
                    common_prefix_frames=session.controller.frames_executed,
                    raw_field_observation_unchanged=True,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        native_menu = build_native_evolution_venue_menu(
            native_before,
            rom=world.rom,
            trainee=trainee,
            target_species_id=evolved_species,
            policy=context.MANSION_TEAM_POLICY,
            venues=inventory,
            allow_guarded_escapes=True,
            resources=True,
            excluded_helper_species=excluded_helpers,
            geometry_quotes=quotes,
            allow_direct_evolution=plan["allow_direct_evolution"],
            include_matchup_context=venue_model.feature_schema_id == PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID,
        )
        registry = PartyDevelopmentVenuePriorRegistry(
            source_commit=manifest["source_commit"], source_bundle_sha256=plan["package_sha256"]
        )
        prospective = PartyDevelopmentProspectiveBinding.build(
            scenario_id=item["scenario_id"],
            root_lineage_id=item["assigned_lineage"],
            initial_state_sha256=payload_sha,
            partition=ScenarioPartition(item["execution_partition"]),
            source_commit=manifest["source_commit"],
            source_bundle_sha256=plan["package_sha256"],
            semantic_snapshot_sha256=native_menu.semantic_snapshot_sha256,
            candidate_set=native_menu.candidate_set,
            venue_priors=native_menu.venue_priors,
            venue_prior_registry_sha256=registry.registry_sha256,
            outcome_objective_sha256=venue_outcome_objective(plan).objective_sha256,
            venue_prior_feature_mode=native_menu.venue_prior_feature_mode,
            candidate_available=native_menu.candidate_available,
            candidate_unavailable_reasons=native_menu.candidate_unavailable_reasons,
        )
        assigned_index = (
            venue_model.predict(native_menu.candidate_set)
            if item["venue_mode"] == "model"
            else item["assigned_venue_index"]
        )
        assert type(assigned_index) is int and native_menu.candidate_available[assigned_index]
        assert tuple(v.map_id for v in bound_venues) == (
            (inventory[assigned_index].map_id,)
            if item["venue_mode"] == "teacher"
            else tuple(v.map_id for v in inventory)
        )
        completion_before = red_party_completion_snapshot(
            native_before, evolutions=evolution_graph(world.rom), policy=context.MANSION_TEAM_POLICY
        )
        frozen_decision = dict(
            schema="pokemon.red.native-evolution-venue-prospective-task.v1",
            binding=prospective.public_dict(),
            candidate_set=native_menu.candidate_set.public_dict(),
            assigned_index=assigned_index,
            teacher_forced_venue=item["venue_mode"] == "teacher",
            model_sha256=plan["venue_model_sha256"],
            model_scores=venue_model.scores(native_menu.candidate_set).tolist(),
            common_prefix_inputs=len(session.recorder.trace),
            common_prefix_frames=session.controller.frames_executed,
            common_prefix_heals=None,
            before_party=asdict(native_before.party),
            completion_before=completion_before.public_dict(),
            state_sha256=hashlib.sha256(emulator.save_state_bytes()).hexdigest(),
            all_common_prefix_costs_included=True,
            outcomes_not_opened=True,
        )
        (OUT / "PROSPECTIVE-VENUE-DECISION.json").write_text(
            json.dumps(frozen_decision, indent=2, sort_keys=True) + "\n"
        )
        (OUT / "decision.state").write_bytes(emulator.save_state_bytes())
        decision_holder.update(
            native_menu=native_menu,
            native_before=native_before,
            prospective=prospective,
            assigned_index=assigned_index,
            completion_before=completion_before,
            prefix_heals=None,
        )

    task_binding_refs = set()
    target_candidates = {}

    def declared_target_binding_refs(rows):
        result = set()
        for row in rows:
            declarations = [
                provider
                for provider in row.profile.providers
                if provider.kind is GoalKind.EVOLVE_SPECIES
            ]
            if len(declarations) != 1:
                raise ValueError("Evolution row has no unique typed target declaration")
            parameters = declarations[0].parameters
            if (
                parameters.get("source_species_ref")
                == f"pokemon:national:{cartridge.species(source_species).national_number:03d}"
                and parameters.get("target_species_ref")
                == f"pokemon:national:{cartridge.species(evolved_species).national_number:03d}"
            ):
                result.add(row.binding.binding_ref)
        return result

    def ordinary(runtime, port, observation, bindings):
        arguments = (
            {
                "venue_model": venue_model,
                "venue_model_sha256": plan["venue_model_sha256"],
                "training_venues": all_venues,
            }
            if item["venue_mode"] == "model"
            else {"training_venues": (all_venues[item["assigned_venue_index"]],)}
        )
        rows = enumerate_red_level_evolutions(
            runtime,
            runtime.adapter.observe(),
            port,
            world.with_current_observation(runtime.reader),
            maximum_actions=25000,
            maximum_frames=2500000,
            maximum_quanta=64,
            maximum_wall_seconds=280,
            allow_guarded_venue_escapes=True,
            allow_direct_evolution=plan["allow_direct_evolution"],
            include_level_workload=True,
            observe_venue_decision=observe_decision,
            **arguments,
        )
        task_binding_refs.clear()
        task_binding_refs.update(declared_target_binding_refs(rows))
        result = []
        for row in rows:
            binding = row.binding
            mask = GoalOpportunity(
                "collection:projection-mask",
                GoalKind.EXPLORE,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            )
            question = GoalBindingSet((binding.opportunity, mask), (binding,)).question(
                observation.situation
            )
            candidate = project_living_dex_goal_candidate(
                question, 0, feature_version=5, binding_ref=binding.binding_ref
            )
            if candidate is None:
                raise ValueError("Level evolution lacks existing portable projection")
            candidate = replace(
                candidate, economy_offer=row.economy_offer, level_workload=row.level_workload
            )
            if row.execution_effort is not None:
                candidate = replace(
                    candidate,
                    features=replace(candidate.features, execution_effort=row.execution_effort),
                )
            target_candidates[binding.binding_ref] = candidate
            result.append(supplemental_live_option(binding, candidate))
        return tuple(result)

    def classroom(runtime, port, observation):
        return GoalBindingSet(
            tuple(
                GoalOpportunity(
                    "classroom:" + kind.value,
                    kind,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
                for kind in GoalKind
            ),
            (),
        )

    factory(ReadOnlyController(emulator))
    assert emulator.save_state_bytes() == payload
    journal = OUT / "journal"
    journal.mkdir(mode=448)
    store = initialize_private_root(
        journal,
        repository_root=package / "checkout",
        allow_same_device=True,
        git_worktree_probe=gitless_fast_path_worktree_probe,
        native_input_storage="flat_sealed_v1",
    )
    model = load_player_goal_model_record(
        Path(plan["goal_model_record"]), expected_model_sha256=plan["goal_model_sha256"]
    ).model
    identity = NativeExecutionIdentity(
        "venue-geometry-TRAIN-20261102", item["arm_id"], model.model_sha256, item["seed"]
    )
    teacher_permission = (
        {"collection_teacher_setup_receipt": setup_sha}
        if item["execution_partition"] == "train"
        else {}
    )
    session = NativePlayerSession(
        store=store,
        emulator=emulator,
        runtime_factory=factory,
        source=source,
        execution=identity,
        output=OUT / "native",
        limits=NativePlayerLimits(
            decisions=1, actions=30000, frames=3000000, seconds=300, heals=256, cash_debits=None
        ),
        combat_specimen_refs=holder["fixture_roles"][0],
        battle_observer=lambda: holder["history"](),
        target_cash=0,
        enumerate_bindings=classroom,
        enumerate_supplements=ordinary,
        model_feature_version=16,
        include_live_pp_readiness=True,
        allow_collection_restoration=True,
        **teacher_permission,
    )
    before = session.snapshot()
    stock_before = _stock(session.runtime)
    actual = dict(
        error_type=None,
        succeeded=False,
        source_sha256=before.sha256,
        declaration_sha256=None,
        teacher_only=True,
        automatic_fit=False,
    )
    detail = dict(
        qualified=False,
        actions=0,
        frames=0,
        model_choices=0,
        teacher_assigned_goal=True,
        admitted_train_examples=0,
    )
    wall_start = time.monotonic()
    try:
        observed = session.observe(0)
        binding, candidate, index, outer_menu = teacher_evolution_selection(
            observed, task_binding_refs, target_candidates
        )
        workload = candidate.level_workload
        assert (
            workload is not None
            and workload.current_level == conditioned_party.members[trainee_index].level
            and workload.target_level == (item["fixture_level"] + 1 if high_level else 26)
        )
        assert (
            workload.remaining_xp
            == cartridge.species(source_species).experience_at_level(workload.target_level) - xp
        )
        prediction = (
            None if index is None else model.predict_candidate(observed.menu.context, candidate)
        )
        menu = dict(
            menu=outer_menu,
            selected_index=index,
            selected_binding=binding.binding_ref,
            teacher_only=True,
            baseline_model_sha256=model.model_sha256,
            predicted_outcome=None if prediction is None else prediction.vector(),
            workload=workload.public_dict(),
            execution_partition=item["execution_partition"],
            venue_mode=item["venue_mode"],
            fit_eligible_protocol=False,
        )
        (OUT / "MENU.json").write_text(json.dumps(menu, indent=2, sort_keys=True) + "\n")
        result["native_execution_started"] = True
        result.update(goal_attempts=1, actions=None, heals=None)
        report = binding.execute()
        native_menu = decision_holder["native_menu"]
        native_before = decision_holder["native_before"]
        prospective = decision_holder["prospective"]
        assigned_index = decision_holder["assigned_index"]
        completion_before = decision_holder["completion_before"]
        verdict = binding.verify(report)
        session.finish_decision()
        actual.update(
            succeeded=verdict.status.value == "succeeded",
            verification=verdict.status.value,
            evidence=dict(report.evidence),
        )
    except BaseException as error:
        actual.update(
            error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc()
        )
        (OUT / "PRIMARY-ERROR.json").write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    finally:
        session.recorder.enabled = False
        session.controller.input_enabled = False
        terminal = emulator.save_state_bytes()
        (OUT / "terminal.state").write_bytes(terminal)
        actual.update(
            terminal_sha256=hashlib.sha256(terminal).hexdigest(),
            actions=len(session.recorder.trace),
            frames=session.controller.frames_executed,
            seconds=session.wall.elapsed_seconds,
            heals=session.heals,
            trace=list(session.recorder.trace),
            field_ready=False,
            buttons_released=not emulator.pressed_buttons,
            after=None,
            stock_progress=None,
        )
        try:
            snapshot = session.snapshot()
            actual.update(
                field_ready=_field_ready(session.runtime),
                buttons_released=snapshot.facts["buttons_released"],
                stock_progress=prepared_stock_progress(stock_before, _stock(session.runtime)),
            )
            after = observe_native_player_boundary(
                session.runtime,
                battle=None,
                combat_specimen_refs=session.roles,
                remaining_budget=(0.0,) * 5,
            )
            actual.update(
                after=after.registered.public_dict(),
                new_registrations=sorted(
                    set(snapshot.facts["owned_species"]) - set(before.facts["owned_species"])
                ),
            )
            from pokemon_red_completion.red_player_continuation import capture_player_continuation

            paired = capture_player_continuation(
                session.runtime,
                preparation=holder["plan"],
                battle=holder["history"](),
                spent=dict(
                    decisions=session.decisions,
                    actions=len(session.recorder.trace),
                    frames=session.controller.frames_executed,
                    seconds=session.wall.elapsed_seconds,
                    heals=session.heals,
                    cash_debits=session.actions.observed_cash_debits,
                ),
            )
            assert paired["state_sha256"] == actual["terminal_sha256"]
            (OUT / "CONTEXT.json").write_text(json.dumps(paired, indent=2, sort_keys=True) + "\n")
            actual["paired_context_sha256"] = sha(OUT / "CONTEXT.json")
        except BaseException as error:
            actual.update(
                export_error_type=type(error).__name__,
                export_error=str(error),
                export_error_traceback=traceback.format_exc(),
            )
        actual["venue_choice_events"] = [
            event
            for event in session.recorder.diagnostic_events
            if event["kind"] == "native_evolution_venue_choice"
        ]
        (OUT / "NATIVE-OUTCOME.json").write_text(
            json.dumps(actual, indent=2, sort_keys=True) + "\n"
        )
    stock = actual.get("stock_progress")
    detail.update(
        actions=actual["actions"],
        frames=actual["frames"],
        heals=actual["heals"],
        seconds=actual["seconds"],
        field_ready=actual["field_ready"],
        controls_released=actual["buttons_released"],
        stock_progress=stock,
        succeeded=actual["succeeded"],
        error_type=actual["error_type"],
        error=actual.get("error"),
        terminal_sha256=actual["terminal_sha256"],
        new_registrations=actual.get("new_registrations", []),
        whole_task_seconds=time.monotonic() - wall_start,
        source_payload_sha256=payload_sha,
        setup_receipt_sha256=setup_sha,
        execution_partition=item["execution_partition"],
    )
    detail["qualified"] = bool(
        actual["succeeded"]
        and actual["field_ready"]
        and actual["buttons_released"]
        and (actual["error_type"] is None)
        and (actual.get("export_error_type") is None)
        and (stock is not None)
        and all(stock.values())
    )
    detail["settled_native_attempt"] = bool(
        actual["field_ready"]
        and actual["buttons_released"]
        and (actual["error_type"] is None)
        and (actual.get("export_error_type") is None)
        and (stock is not None)
        and all(stock.values())
    )
    if detail["settled_native_attempt"]:
        try:
            from pokemon_red_completion.party_development_outcomes import (
                PartyDevelopmentOutcomeTrialV2,
                adapt_party_development_outcomes_v2,
            )

            native_after = replace(
                session.runtime.adapter.observe(), party=PokemonRedPartyReader(emulator).read()
            )
            completion_after = red_party_completion_snapshot(
                native_after,
                evolutions=evolution_graph(world.rom),
                policy=context.MANSION_TEAM_POLICY,
            )
            target_members = tuple(
                m
                for m in native_after.party.members
                if m.species_id in (source_species, evolved_species)
            )
            assert len(target_members) == 1
            evidence = actual["evidence"]
            progress_after = TeamTrainingProgress(
                battles_completed=evidence["completed_training_battles"],
                healing_trips=evidence["healing_trips"],
                faints=observed_training_faints(session.recorder.diagnostic_events),
            )
            trial = PartyDevelopmentOutcomeTrialV2(
                candidate=native_menu.candidate_set.candidates[assigned_index],
                target_slot=target.slot,
                before_party=native_before.party,
                after_party=native_after.party,
                after_target_slot=target_members[0].slot,
                progress_before=TeamTrainingProgress(),
                progress_after=progress_after,
                completion_before=completion_before,
                completion_after=completion_after,
                frames_executed=detail["frames"],
                evolution_completed=actual["succeeded"],
                censored=False,
            )
            example = adapt_party_development_outcomes_v2(
                native_menu.candidate_set,
                (trial,),
                scenario_id=item["scenario_id"],
                root_lineage_id=item["assigned_lineage"],
                initial_state_sha256=payload_sha,
                partition=ScenarioPartition(item["execution_partition"]),
                prospective_binding=prospective,
                total_task_efficiency=True,
                target_task_efficiency=plan.get("target_task_efficiency", False),
            )
            document = dict(
                example=example.public_dict(),
                measured_outcome=asdict(example.outcomes[assigned_index]),
                candidate_set=native_menu.candidate_set.public_dict(),
                prospective_binding=prospective.public_dict(),
                before_party=asdict(native_before.party),
                after_party=asdict(native_after.party),
                completion_after=completion_after.public_dict(),
                progress_counters=asdict(progress_after),
                grid_steps_instrumented=False,
                zero_faints_enforced_by_native_trainer=not venue_training_faint_recovery(plan),
                recovered_training_faints_observed=observed_training_faints(
                    session.recorder.diagnostic_events
                ),
                broad_loss_coverage_complete=False,
                actions=detail["actions"],
                frames=detail["frames"],
                seconds=detail["seconds"],
                settled_native_attempt=True,
                goal_succeeded=actual["succeeded"],
                assigned_index=assigned_index,
                terminal_state_sha256=detail["terminal_sha256"],
                fit_eligible=item["execution_partition"] == "train"
                and item["venue_mode"] == "teacher"
                and not plan.get("validation_role"),
                model_selected_venue=item["venue_mode"] == "model",
                validation_role=plan.get("validation_role"),
                actual_progress=False,
                controller_costs_are_full_native_totals=True,
            )
            (OUT / "PARTY-VENUE-OUTCOME.json").write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n"
            )
            detail.update(
                admitted_party_venue_outcomes=1,
                party_venue_outcome_sha256=sha(OUT / "PARTY-VENUE-OUTCOME.json"),
            )
        except BaseException as error:
            detail.update(
                admission_error_type=type(error).__name__,
                admission_error=str(error),
                admission_traceback=traceback.format_exc(),
            )
    detail["venue_choice_events"] = actual.get("venue_choice_events", [])
    result.update(
        actions=detail["actions"],
        frames=detail["frames"],
        heals=detail["heals"],
        native_seconds=detail["seconds"],
        controls_released=detail["controls_released"],
        field_ready=detail["field_ready"],
        native_outcome=detail,
    )
    return detail


def _comparison_only_venue_fit(plan, fit_path, fit, source_sha256):
    """Permit only a pinned inference comparison of a completed, unadopted fit.

    This does not change its rejected training result or admit any new rows.
    Default validation still requires the original accepted fit receipt.
    """
    if plan.get("validation_role") != "exposed-TRAIN-component-comparison-only":
        return False
    path = plan.get("comparison_authorization")
    if not isinstance(path, str) or plan["pins"].get(path) != sha(path):
        raise ValueError("diagnostic venue comparison authorization is not pinned")
    scope = json.loads(Path(path).read_bytes())
    if (
        scope.get("schema") != "pokemon.red.venue-candidate-comparison-only.v1"
        or scope.get("fit_result_sha256") != sha(fit_path)
        or scope.get("model_sha256") != fit["model_sha256"]
        or scope.get("source_state_sha256") != source_sha256
        or scope.get("training_accepted") is not fit["accepted"]
        or fit.get("passed") is not True
        or scope.get("broad_adoption") is not False
        or scope.get("fitting_forbidden") is not True
        or plan.get("fit_allowed") is not False
        or plan.get("party_venue_fit_eligible") is not False
        or plan.get("diagnostic_only") is not True
        or plan.get("copy_back") is not False
        or plan.get("campaign_writes") is not False
    ):
        raise ValueError("diagnostic venue comparison scope differs")
    return True
