"""Proposed isolated noncombat TRAIN mode for the existing teacher entry.

This records existing bounded story bindings. It never grants a trainer battler,
changes a save, predicts an alternative, or converts a rehearsal into TRAIN.
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC
from hashlib import sha256
from pathlib import Path

from .provenance import canonical_sha256
from .red_teacher_case import require

SCHEMA = "pokemon.red.noncombat-story-unit-teacher-case.v3"
FIELDS = {
    "schema",
    "mode",
    "partition",
    "role",
    "source_state_sha256",
    "historical_assignment_id",
    "historical_root_lineage_id",
    "objective_id",
    "approach",
    "unit",
    "maximum_actions",
    "maximum_frames",
    "native_seconds",
}


def is_story_unit_case(plan):
    return (
        isinstance(plan.get("teacher_case"), dict) and plan["teacher_case"].get("schema") == SCHEMA
    )


@dataclass(frozen=True)
class TeacherStoryUnitCaseSpec:
    _json: str

    @classmethod
    def from_dict(cls, value):
        return cls(cls._canonical_document(value))

    @staticmethod
    def _canonical_document(value):
        require(type(value) is dict and set(value) == FIELDS, "noncombat case fields differ")
        require(
            value["schema"] == SCHEMA and value["mode"] == "mansion_partial_switch",
            "unsupported noncombat teacher mode",
        )
        require(
            (value["partition"], value["role"]) == ("train", "train_sampling"),
            "noncombat teacher requires TRAIN sampling",
        )
        for key in ("source_state_sha256", "historical_assignment_id"):
            digest = value[key]
            require(
                type(digest) is str
                and len(digest) == 64
                and all(c in "0123456789abcdef" for c in digest),
                "invalid noncombat identity",
            )
        require(
            value["historical_root_lineage_id"]
            == "red-scenario-root-" + value["historical_assignment_id"],
            "historical family differs",
        )
        require(value["objective_id"] == "obtain_secret_key", "noncombat objective differs")
        require(
            value["approach"] is None,
            "Direct interaction must not declare a separate approach lesson",
        )
        from .player_option_story_unit import OptionStoryUnit

        require(
            value["unit"]
            == dict(
                kind="events",
                map_id=215,
                events=[632],
                story_unit_scope=OptionStoryUnit("interaction", True).public_dict(),
            ),
            "partial statue endpoint or onward-work scope differs",
        )
        for key, upper in (
            ("maximum_actions", 1800),
            ("maximum_frames", 180000),
            ("native_seconds", 180),
        ):
            require(type(value[key]) is int and 0 < value[key] <= upper, "noncombat cap differs")
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def __post_init__(self):
        require(type(self._json) is str, "canonical noncombat case required")
        require(
            self._json == self._canonical_document(json.loads(self._json)),
            "noncanonical noncombat case",
        )

    def document(self):
        return json.loads(self._json)


def authenticate_story_unit_source(plan):
    """Authenticate the exact historical TRAIN assignment, not its filename."""
    from .captured_progress import parse_captured_progress
    from .strategic_navigation_protocol import StrategicNavigationExecution
    from .strategic_navigation_scenarios import load_strategic_navigation_scenario_registry

    spec = TeacherStoryUnitCaseSpec.from_dict(plan["teacher_case"])
    data = spec.document()
    refs = plan["historical_train_source"]
    require(
        set(refs) == {"state", "envelope", "episode", "manifest", "collection_registry"},
        "historical TRAIN source evidence fields differ",
    )
    payloads = {}
    for key, ref in refs.items():
        require(type(ref) is dict and set(ref) == {"path", "sha256"}, "source reference differs")
        payload = Path(ref["path"]).read_bytes()
        require(
            sha256(payload).hexdigest() == ref["sha256"], "historical source bytes differ: " + key
        )
        require(plan["pins"].get(ref["path"]) == ref["sha256"], "historical reference not pinned")
        payloads[key] = payload
    capture = parse_captured_progress(payloads["envelope"], state_bytes=payloads["state"])
    require(
        capture.state_sha256
        == data["source_state_sha256"]
        == plan["source_sha256"]
        == plan["original_TRAIN_state_sha256"],
        "source state or original TRAIN identity differs",
    )
    require(
        Path(plan["source"]).read_bytes() == payloads["state"]
        and Path(plan["source_envelope"]).read_bytes() == payloads["envelope"],
        "source aliases differ",
    )
    lines = payloads["episode"].splitlines()
    require(len(lines) == 1, "historical TRAIN episode cardinality differs")
    episode = json.loads(lines[0])
    metadata = episode["metadata"]
    collection = metadata["collection"]
    manifest = json.loads(payloads["manifest"])
    (record,) = [row for row in manifest["files"] if row["filename"] == "episode.jsonl"]
    require(
        manifest["status"] == "complete"
        and manifest["episode_id"] == episode["episode_id"]
        and record["records"] == 1
        and record["bytes"] == len(payloads["episode"])
        and record["sha256"] == sha256(payloads["episode"]).hexdigest(),
        "closed historical episode differs",
    )
    require(
        collection["attempt"] == dict(attempts_per_slot=1, counted=True)
        and metadata["split"]["partition"] == collection["scenario"]["partition"] == "train"
        and metadata["configuration"]["scenario_rehearsal"] is False,
        "rehearsal or heldout source rejected",
    )
    checkout = Path(plan["package"]).parent / "checkout"
    registry = load_strategic_navigation_scenario_registry(checkout)
    old_execution = dict(json.loads(payloads["collection_registry"])["execution"])
    old_execution.pop("schema")
    execution = StrategicNavigationExecution(
        **old_execution, source_commit=metadata["source"]["git_commit"]
    )
    assignment = registry.learning_assignment(
        collection["scenario"]["scenario_id"], capture=capture, execution=execution
    )
    require(
        assignment.assignment_id == collection["assignment_id"] == data["historical_assignment_id"]
        and assignment.root_lineage_id
        == metadata["split"]["root_lineage_id"]
        == data["historical_root_lineage_id"]
        and assignment.registry_sha256 == collection["registry_sha256"]
        and assignment.scenario_sha256 == collection["scenario"]["scenario_sha256"]
        and assignment.capture_envelope_sha256 == collection["capture"]["envelope_sha256"]
        and assignment.capture_state_sha256 == collection["capture"]["state_sha256"],
        "historical assignment reconstruction differs",
    )
    require(
        data["objective_id"] not in capture.verified_objective_ids
        and {"reach_cinnabar", "obtain_surf", "obtain_strength"}
        <= set(capture.verified_objective_ids),
        "source story frontier differs",
    )
    require(
        plan.get("copy_back") is False
        and plan.get("campaign_writes") is False
        and plan.get("fit_allowed") is False
        and plan.get("partition") == "train",
        "collection-only scope differs",
    )
    require(
        plan["caps"]["emulators"] == plan["caps"]["state_loads"] == 1
        and plan["caps"]["new_fits"] == 0
        and plan["caps"]["outer_seconds"] <= 300
        and plan["native_limits"]["seconds"] == data["native_seconds"],
        "physical allowance differs",
    )
    return (
        spec,
        capture,
        payloads["state"],
        dict(
            partition="train",
            original_state_sha256=capture.state_sha256,
            historical_assignment_id=assignment.assignment_id,
            root_lineage_id=assignment.root_lineage_id,
            historical_episode_sha256=sha256(payloads["episode"]).hexdigest(),
            independent_origin=False,
            complete_genesis_dag_known=False,
            old_slot_reopened=False,
        ),
    )


def require_mansion_start(raw, input_ready, *, expected_map=171):
    from .observation import EventFlag, ItemId, event_flag_is_set

    require(
        input_ready is True and raw.battle_state == 0 and raw.map_id == expected_map,
        "noncombat source is not the expected ready field",
    )
    require(
        raw.bag_items is not None and not dict(raw.bag_items).get(int(ItemId.SECRET_KEY), 0),
        "Secret Key source is already complete",
    )
    require(
        isinstance(raw.event_flags, bytes)
        and not event_flag_is_set(raw.event_flags, int(EventFlag.MANSION_SWITCH_ON)),
        "Mansion switch must be observed off before input",
    )
    require(raw.party_hp and all(raw.party_hp), "noncombat source has a fainted member")


def existing_unit_offer(runtime, actions, *, phase, route):
    """Return only the existing declared teacher unit; no alternate outcome labels."""
    from .goal_manager import GoalKind
    from .player_option_challenge import OptionChallenge
    from .player_option_story_unit import OptionStoryUnit
    from .red_player_lesson import capture_player_lesson_snapshot
    from .red_player_mansion import UPPER_STATUE, _mansion_interaction_option

    require(phase == "interaction", "direct teacher has only one interaction phase")
    before, lesson = capture_player_lesson_snapshot(runtime)
    # Disclosed TRAIN selection of the existing executor, including its generic
    # route to the existing cartridge statue coordinate. This is not a claim
    # that the live parent policy selected this off-route teaching example.
    observed = _mansion_interaction_option(
        runtime,
        actions,
        route=route,
        before=before,
        lesson=lesson,
        switch=False,
        drop=False,
        target_map=UPPER_STATUE[0],
        at=UPPER_STATUE[1],
        objective="obtain_secret_key",
    )
    require(observed is not None, "existing Mansion interaction route unavailable")
    binding, challenge = observed
    scope = OptionStoryUnit("interaction", True)
    require(
        binding.binding_ref.startswith("pokemon.red:mansion-interaction:"),
        "provider offered another Mansion unit: " + binding.binding_ref,
    )
    require(
        binding is not None
        and binding.kind is GoalKind.ADVANCE_STORY
        and binding.story_objective_ref == "obtain_secret_key"
        and binding.story_unit == scope
        and binding.story_approach_only is True
        and challenge == OptionChallenge(False, False, 0.0, 0.0, 0.0),
        "existing noncombat unit contract differs",
    )
    return binding, challenge


def verify_partial_unit_row(row):
    from .player_option_story_unit import OptionStoryUnit, story_unit_vector

    require(
        row.feature_version == 16
        and row.features[-4:] == story_unit_vector(OptionStoryUnit("interaction", True)),
        "recorded lesson lost partial interaction scope",
    )
    require(
        row.outcome.verified_success
        and row.outcome.completion_gain == 0
        and row.outcome.dependency_unlock_gain == 0,
        "partial unit falsely credits whole quest",
    )
    return row


def prepend_teacher_unit(original, binding):
    """Keep genuine nonstory availability; never invent a disabled alternative."""
    from .goal_manager import GoalKind
    from .goal_manager_runtime import GoalBindingSet

    return GoalBindingSet(
        (binding.opportunity,)
        + tuple(o for o in original.opportunities if o.kind is not GoalKind.ADVANCE_STORY),
        (binding,) + tuple(b for b in original.bindings if b.kind is not GoalKind.ADVANCE_STORY),
        allow_resource_variants=original.allow_resource_variants,
    )


def _error_receipt(error):
    import traceback

    return dict(
        error_type=type(error).__name__,
        error=str(error),
        traceback="".join(traceback.format_exception(error)),
    )


def retain_native_call_error(call, *, result, phase, stage, write_error):
    def guarded(*args, **kwargs):
        try:
            return call(*args, **kwargs)
        except BaseException as error:
            receipt = dict(phase=phase, stage=stage, **_error_receipt(error))
            result.setdefault("recorded_execution_errors", []).append(receipt)
            try:
                write_error(receipt)
            except BaseException as write_failure:
                result.setdefault("error_receipt_write_errors", []).append(
                    _error_receipt(write_failure)
                )
            raise

    return guarded


def record_teacher_phase(result, phase, recorder, **kwargs):
    """A thrown recorder cannot certify that its attempted actions were zero."""
    result["goal_attempts"] += 1
    result["active_phase"] = phase
    result["actions_lower_bound"] = result.get("actions_lower_bound", result["actions"])
    result["frames_lower_bound"] = result.get("frames_lower_bound", 0)
    result.update(actions=None, frames=None, actions_cost_known=False, frames_cost_known=False)
    try:
        attempt = recorder(**kwargs)
        for field in ("actions_attempted", "frames"):
            require(
                type(attempt.get(field)) is int and attempt[field] >= 0,
                "recorder returned invalid measured cost",
            )
    except BaseException as error:
        result["phase_error"] = dict(phase=phase, **_error_receipt(error))
        raise
    result["actions_lower_bound"] += attempt["actions_attempted"]
    result["frames_lower_bound"] += attempt["frames"]
    result.update(
        actions=result["actions_lower_bound"],
        frames=result["frames_lower_bound"],
        actions_cost_known=True,
        frames_cost_known=True,
        active_phase=None,
    )
    result["phase_results"].append(attempt)
    return attempt


@contextmanager
def managed_teacher_guest(
    adapter, result, *, release, export_terminal, cancel_timer, clock, native_started
):
    """Attempt every independent cleanup step without replacing a native error."""
    primary = None
    entered = False
    cleanup_errors = []
    cleanup_exceptions = []
    result.update(
        emulator_closed=None,
        emulator_close_known=False,
        controls_released=None,
        native_seconds=None,
        frames=None,
        frames_cost_known=False,
    )

    def cleanup(name, call):
        try:
            call()
        except BaseException as error:
            cleanup_errors.append(dict(stage=name, **_error_receipt(error)))
            cleanup_exceptions.append(error)

    def release_controls():
        release(adapter)
        result["controls_released"] = not adapter.pressed_buttons
        require(result["controls_released"] is True, "controls remain pressed after release")

    def capture_frames():
        value = adapter.frame_count
        require(
            type(value) is int and value >= result.get("frames_lower_bound", 0),
            "native frame count below closed-phase lower bound",
        )
        result.update(frames=value, frames_cost_known=True)

    def capture_time():
        from math import isfinite

        value = clock() - native_started
        require(isfinite(value) and value >= 0, "invalid native wall duration")
        result["native_seconds"] = value

    def capture_terminal():
        terminal = adapter.save_state_bytes()
        result.update(
            terminal_observed_sha256=sha256(terminal).hexdigest(), terminal_exported=False
        )
        export_terminal(terminal)
        result.update(terminal_sha256=result["terminal_observed_sha256"], terminal_exported=True)

    def close_guest():
        adapter.close()
        result.update(emulator_closed=True, emulator_close_known=True)

    try:
        emulator = adapter.__enter__()
        entered = True
        yield emulator
    except BaseException as error:
        primary = error
        result["native_error"] = _error_receipt(error)
        raise
    finally:
        cleanup("cancel_timer", cancel_timer)
        if entered:
            cleanup("release_controls", release_controls)
            cleanup("capture_frames", capture_frames)
            cleanup("export_terminal", capture_terminal)
        cleanup("capture_native_seconds", capture_time)
        # start() can fail after allocating a backend: close even if __enter__ failed.
        cleanup("close_guest", close_guest)
        result["cleanup_errors"] = cleanup_errors
        if primary is None and cleanup_exceptions:
            raise BaseExceptionGroup("teacher guest cleanup failed", cleanup_exceptions)


def _validate_common(plan, loader_definitions):
    from datetime import datetime

    require(datetime.now(UTC) < datetime.fromisoformat(plan["cutoff_utc"]), "expired case")
    for path, digest in plan["pins"].items():
        require(sha256(Path(path).read_bytes()).hexdigest() == digest, "case pin differs")
    spec, capture, payload, proof = authenticate_story_unit_source(plan)
    catalog = json.loads(Path(plan["source_catalog"]).read_bytes())
    rows = [r for r in catalog["sources"] if r["condition"] == plan["condition"]]
    require(len(rows) == 1, "ambiguous source row")
    row = rows[0]
    require(
        row["source_partition"] == "train"
        and row["role"] == "train_sampling"
        and row["historical_root_lineage_id"] == proof["root_lineage_id"],
        "source catalog family differs",
    )
    custody = json.loads(Path(plan["retained_source_custody"]).read_bytes())
    require(plan.get("shared_origin_id") == proof["root_lineage_id"], "closeout origin differs")
    require(
        isinstance(plan.get("separate_acquisition_cost"), dict),
        "historical cost declaration missing",
    )
    allowance = loader_definitions["validate_diagnostic_startup"](plan, custody, row)
    return spec, capture, payload, proof, allowance


def build_noncombat_story_route(rom):
    """Use the real route contract without granting a trainer binding factory."""
    from dataclasses import replace

    from .red_training_ground_route import RedVermilionGroundTransition

    return replace(
        RedVermilionGroundTransition.from_rom(rom),
        full_event_offsets=True,
        observe_terrain=True,
        maximum_flees=16,
        trainer_binding_factory=None,
    )


def preflight_story_unit(plan, *, plan_sha256, worker_sha256, loader_definitions, output):
    """Pure source and existing-constructor validation; no guest is instantiated."""
    from inspect import signature

    from .red_player_lesson_runtime import record_native_player_lesson
    from .red_player_package import bind_player_package
    from .red_player_story_unit import validate_story_unit_target

    spec, capture, payload, proof, _ = _validate_common(plan, loader_definitions)
    data = spec.document()
    route = build_noncombat_story_route(
        (
            Path(plan["package"]).parent / "data/storage-migration/roms/PokemonRoms/Pokemon Red.gb"
        ).read_bytes()
    )
    require(route.trainer_binding_factory is None, "noncombat route grants a trainer")
    bound = bind_player_package(
        Path(plan["package"]), plan["package_sha256"], history_output=Path(output)
    )
    import player_coherent_session as shared
    import player_first_restore_lesson as c

    c.FROZEN_SOURCE_COMMIT = bound["source_commit"]
    factory, _, _, source = shared.assembly(
        payload,
        Path(output) / "runtime",
        origin_sha=proof["historical_assignment_id"],
        partition="train",
        origin_id=proof["root_lineage_id"],
        objective_ids=capture.verified_objective_ids,
        protect_party_species=False,
    )
    require(
        callable(factory)
        and source["partition"] == "train"
        and source["state_sha256"] == capture.state_sha256,
        "existing TRAIN assembly differs",
    )
    target = {k: v for k, v in data["unit"].items() if k != "story_unit_scope"}
    validate_story_unit_target(target)
    signature(record_native_player_lesson).bind(
        store=None,
        emulator=None,
        runtime_factory=factory,
        source=source,
        selected_index=0,
        target={"objective": data["objective_id"]},
        battle=None,
        combat_specimen_refs=(),
        remaining_budget=(1.0, 1.0, 1.0, 1.0, 0.0),
        target_cash=0,
        maximum_actions=data["maximum_actions"],
        maximum_frames=data["maximum_frames"],
        enumerate_bindings=lambda *_: None,
        observe_challenge=lambda *_: None,
        story_unit_target=target,
        include_live_pp_readiness=True,
        preflight_only=True,
    )
    return dict(
        passed=True,
        phase="preflight",
        plan_sha256=plan_sha256,
        worker_sha256=worker_sha256,
        teacher_case=data,
        source_proof=proof,
        package_sha256=plan["package_sha256"],
        emulators=0,
        loads=0,
        inputs=0,
        frames=0,
        fits=0,
        model_queries=0,
        native_observation_pending=True,
        actual_assembly_returned=True,
        native_factory_invoked=False,
        scope=(
            "exact historical TRAIN source, frozen assembly and recorder signature; "
            "live field/event checks remain before input"
        ),
    )


def run_story_unit(plan, *, output, worker_path, loader_definitions, started, write):
    """One guest, charged approach then one existing partial interaction."""
    import signal
    import sys
    import time
    import traceback
    from dataclasses import replace
    from datetime import datetime

    import player_coherent_session as shared
    import player_first_restore_lesson as c

    from .emulator import PyBoyAdapter
    from .executor import ReadOnlyController, release_pressed_buttons
    from .private_artifacts import gitless_fast_path_worktree_probe, initialize_private_root
    from .red_native_curriculum import NativeCurriculumInput, load_native_curriculum
    from .red_party import PokemonRedPartyReader
    from .red_player_field_goals import _field_ready
    from .red_player_lesson import capture_player_lesson_snapshot
    from .red_player_lesson_runtime import record_native_player_lesson
    from .red_player_package import bind_player_package, package_read_guard
    from .red_pp_observation import observe_pp_resources

    out = Path(output)
    plan_path = out / "PLAN.json"
    package = Path(plan["package"]).parent
    physical = dict(
        construction_attempts=0, emulators_constructed=0, load_attempts=0, state_loads=0
    )
    result = dict(
        schema="pokemon.red.noncombat-story-unit-case-result.v1",
        passed=False,
        admitted=False,
        physical_emulator_accounting=physical,
        actions=0,
        frames=0,
        goal_attempts=0,
        heals=0,
        native_seconds=0.0,
        wild_battles=0,
        story_battles=0,
        goal_policy_queries=0,
        model_queries=0,
        fits=0,
        new_fits=0,
        new_weights=0,
        actual_credit=0,
        gate_credit=0,
        copy_back=False,
        campaign_progress=False,
        training_admission=False,
        phase_results=[],
        teacher_selected=True,
    )
    emulator = None
    native_started = None
    old_profile = sys.getprofile()
    original_init = PyBoyAdapter.__init__
    original_load = PyBoyAdapter.load_state_bytes
    try:
        spec, capture, payload, proof, allowance = _validate_common(plan, loader_definitions)
        data = spec.document()
        qualification = json.loads(Path(plan["qualification"]).read_bytes())
        require(
            qualification["passed"] is True
            and qualification["phase"] == "preflight"
            and qualification["plan_sha256"] == sha256(plan_path.read_bytes()).hexdigest()
            and qualification["worker_sha256"] == sha256(Path(worker_path).read_bytes()).hexdigest()
            and qualification["teacher_case"] == data
            and qualification["source_proof"] == proof
            and all(
                qualification[k] == 0
                for k in ("emulators", "loads", "inputs", "frames", "fits", "model_queries")
            ),
            "exact zero-guest qualification differs",
        )
        bound = bind_player_package(
            Path(plan["package"]), plan["package_sha256"], history_output=out
        )
        loader_definitions["preload_verified_native_dependencies"](bound)
        reads, writes = package_read_guard(
            bound,
            manifest_path=Path(plan["package"]),
            output=out,
            extra_inputs=[
                str(plan_path),
                str(Path(worker_path).resolve()),
                str(Path(__file__).resolve()),
                plan["qualification"],
                *plan["pins"],
            ],
        )
        c.FROZEN_SOURCE_COMMIT = bound["source_commit"]
        rom_path = package / "data/storage-migration/roms/PokemonRoms/Pokemon Red.gb"
        route = build_noncombat_story_route(rom_path.read_bytes())

        def one_init(self, *args, **kwargs):
            physical["construction_attempts"] += 1
            require(physical["construction_attempts"] == 1, "second native constructor rejected")
            original_init(self, *args, **kwargs)
            physical["emulators_constructed"] += 1

        def one_load(self, state):
            physical["load_attempts"] += 1
            require(
                physical["load_attempts"] == 1 and state == payload,
                "second or substituted source load rejected",
            )
            original_load(self, state)
            physical["state_loads"] += 1

        PyBoyAdapter.__init__ = one_init
        PyBoyAdapter.load_state_bytes = one_load
        prediction_names = {
            "predict",
            "predict_proba",
            "predict_candidate",
            "predict_economy_candidate",
            "raw_predictions",
            "_base_raw_predictions",
            "scores",
            "select",
            "forward",
        }

        def forbid_learning(frame, event, arg):
            if (
                event == "call"
                and str(package / "checkout/src/pokemon_red_completion") in frame.f_code.co_filename
            ):
                name = frame.f_code.co_name
                if name == "fit" or name.startswith("fit_") or name in prediction_names:
                    raise RuntimeError(
                        "noncombat teacher forbids model inference or fitting: " + name
                    )

        sys.setprofile(forbid_learning)
        journal = out / "journal"
        journal.mkdir(mode=0o700)
        store = initialize_private_root(
            journal,
            repository_root=package / "checkout",
            allow_same_device=True,
            git_worktree_probe=gitless_fast_path_worktree_probe,
            native_input_storage="flat_sealed_v1",
        )
        native_started = time.monotonic()
        remaining = min(data["native_seconds"], allowance - (native_started - started) - 2)
        require(remaining > 0, "no native allowance remains")
        signal.signal(
            signal.SIGALRM,
            lambda *_: (_ for _ in ()).throw(TimeoutError("noncombat native deadline")),
        )
        signal.setitimer(signal.ITIMER_REAL, remaining)
        result["package_guard_read_files"] = len(reads)
        result["package_guard_write_roots"] = len(writes)
        with (
            managed_teacher_guest(
                PyBoyAdapter(rom_path),
                result,
                release=release_pressed_buttons,
                export_terminal=lambda payload: (out / "terminal.state").write_bytes(payload),
                cancel_timer=lambda: signal.setitimer(signal.ITIMER_REAL, 0),
                clock=time.monotonic,
                native_started=native_started,
            ) as emulator,
        ):
            emulator.load_state_bytes(payload)
            result["wild_battles"] = (
                None  # Route flee count is not exposed by this existing recorder.
            )
            require(
                emulator.save_state_bytes() == payload
                and emulator.frame_count == 0
                and not emulator.pressed_buttons,
                "source readback differs before input",
            )
            refs = tuple(
                PokemonRedPartyReader(ReadOnlyController(emulator)).preparation_specimen_refs()
            )
            original_objectives = set(capture.verified_objective_ids)
            for ordinal, phase in enumerate(("interaction",)):
                state = emulator.save_state_bytes()
                state_hash = sha256(state).hexdigest()
                case = out / ("runtime-" + phase)
                case.mkdir(mode=0o700)
                factory, _, holder, source = shared.assembly(
                    state,
                    case,
                    origin_sha=proof["historical_assignment_id"],
                    partition="train",
                    origin_id=proof["root_lineage_id"],
                    objective_ids=capture.verified_objective_ids,
                    protect_party_species=False,
                )
                source = dict(source, setup_receipt_sha256=canonical_sha256(proof))
                rt = factory(ReadOnlyController(emulator))
                raw = rt.reader.read()
                require_mansion_start(raw, _field_ready(rt), expected_map=171)
                require(
                    tuple(holder["refs"]) == refs
                    and len(refs) == 4
                    and set(capture_player_lesson_snapshot(rt)[1]["completed_objectives"])
                    == original_objectives,
                    "party membership or observed quest frontier differs",
                )
                target = (
                    data["approach"]
                    if phase == "approach"
                    else {k: v for k, v in data["unit"].items() if k != "story_unit_scope"}
                )

                def enumerate_one(runtime, actions, before, phase=phase):
                    binding, challenge = existing_unit_offer(
                        runtime, actions, phase=phase, route=route
                    )

                    def guarded(call, name):
                        return retain_native_call_error(
                            call,
                            result=result,
                            phase=phase,
                            stage=name,
                            write_error=lambda receipt: write(
                                out / (phase + "-" + name + "-ERROR.json"), receipt
                            ),
                        )

                    binding = replace(
                        binding,
                        execute=guarded(binding.execute, "execute"),
                        verify=guarded(binding.verify, "verify"),
                    )
                    return prepend_teacher_unit(
                        runtime.enumerator(actions).enumerate(before), binding
                    )

                actions_left = data["maximum_actions"] - result["actions"]
                frames_left = data["maximum_frames"] - emulator.frame_count
                seconds_left = data["native_seconds"] - (time.monotonic() - native_started)
                require(
                    min(actions_left, frames_left, seconds_left) > 0, "native case cap exhausted"
                )
                kwargs = dict(
                    store=store,
                    emulator=emulator,
                    runtime_factory=factory,
                    source=source,
                    selected_index=0,
                    target={"objective": data["objective_id"]},
                    battle=None,
                    combat_specimen_refs=refs,
                    remaining_budget=(
                        1.0,
                        actions_left / data["maximum_actions"],
                        frames_left / data["maximum_frames"],
                        seconds_left / data["native_seconds"],
                        0.0,
                    ),
                    target_cash=0,
                    maximum_actions=actions_left,
                    maximum_frames=frames_left,
                    enumerate_bindings=enumerate_one,
                    observe_challenge=lambda *_: __import__(
                        "pokemon_red_completion.player_option_challenge",
                        fromlist=["OptionChallenge"],
                    ).OptionChallenge(False, False, 0.0, 0.0, 0.0),
                    story_unit_target=target,
                    include_live_pp_readiness=True,
                )
                preflight = record_native_player_lesson(**kwargs, preflight_only=True)
                write(out / (phase + "-PREFLIGHT.json"), preflight)
                require(
                    emulator.save_state_bytes() == state and not emulator.pressed_buttons,
                    "preinput declaration changed source",
                )
                if ordinal == 0:
                    write(
                        out / "LIVE-PP-PREINPUT-GATE.json",
                        dict(
                            passed=True,
                            source_bytes_exact=True,
                            source_sha256=state_hash,
                            combat_specimen_refs=list(refs),
                            pp=observe_pp_resources(raw).public_dict(),
                            inputs=0,
                            frames=0,
                        ),
                    )
                    write(
                        out / "PREINPUT-QUALIFICATION.json",
                        dict(
                            passed=True,
                            source_bytes_exact=True,
                            source_state_sha256=state_hash,
                            source_partition="train",
                            feature_version=16,
                            full_menu_comparison=False,
                            teacher_unit_only=True,
                            inputs=0,
                            frames=0,
                        ),
                    )
                attempt = record_teacher_phase(result, phase, record_native_player_lesson, **kwargs)
                write(out / (phase + "-RESULT.json"), attempt)
                require(
                    attempt["admitted"]
                    and attempt["succeeded"]
                    and not attempt["execution_or_verification_failed"],
                    "noncombat unit failed; retain native tail",
                )
                row = load_native_curriculum(store, NativeCurriculumInput(**attempt["outcome"]))
                require(
                    set(attempt["player_lesson"]["completed_objectives"]) == original_objectives,
                    "bounded interaction unexpectedly completed a quest",
                )
                if phase == "interaction":
                    verify_partial_unit_row(row)
                    result.update(
                        row=row.public_dict(),
                        selected_outcome=attempt["outcome"],
                        admitted=True,
                        training_admission=True,
                    )
            result["passed"] = True
    except BaseException as exc:
        result.update(
            passed=False,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
    finally:
        for name, cleanup in (
            ("cancel_timer", lambda: signal.setitimer(signal.ITIMER_REAL, 0)),
            ("restore_profile", lambda: sys.setprofile(old_profile)),
        ):
            try:
                cleanup()
            except BaseException as error:
                result.setdefault("outer_cleanup_errors", []).append(
                    dict(stage=name, **_error_receipt(error))
                )
                result["passed"] = False
        PyBoyAdapter.__init__ = original_init
        PyBoyAdapter.load_state_bytes = original_load
        result.update(
            outer_seconds=time.monotonic() - started, finished_at_utc=datetime.now(UTC).isoformat()
        )
    return result
