"""Zero-emulator preflight for the same direct teacher session used by execution."""
from pathlib import Path
from datetime import datetime, timezone
from inspect import signature
import hashlib
import json

from .red_teacher_case import validate_plan_case, build_teacher_session_kwargs, require


def preflight_direct(plan, *, plan_sha256, worker_sha256, loader_definitions, output):
    """No emulator construction, state loading, input, fit, or guard claim.

    Existing package authentication may hash its ROM asset; no native execution or
    cartridge interpretation occurs in this phase.
    """
    read = lambda path: json.loads(Path(path).read_bytes())
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    require(datetime.now(timezone.utc) < datetime.fromisoformat(plan["cutoff_utc"]), "expired case")
    for path, digest in plan["pins"].items():
        require(sha(path) == digest, "input pin differs: " + path)
    catalog = read(plan["source_catalog"])
    rows = [row for row in catalog["sources"] if row["condition"] == plan["condition"]]
    require(len(rows) == 1, "source catalog row ambiguous")
    row = rows[0]
    spec = validate_plan_case(plan, row)
    require(catalog["metadata_gate_passed"] is True and row["fit_allowed"] is True, "TRAIN catalog custody failed")
    require(sha(plan["source"]) == spec.document()["source_sha256"], "retained source bytes differ")
    envelope = read(plan["source_envelope"])
    teacher = read(plan["assisted_progress"])
    require(envelope["state_sha256"] == plan["source_sha256"] and teacher["partition"] == "train"
            and teacher["campaign_eligible"] is False and teacher["envelope"] == envelope,
            "teacher declaration/source envelope differs")
    parent = read(plan["source_parent_authentication"])
    require(all(parent.get(key) is True for key in ("passed", "all_original_processes_absent", "controls_released",
            "preinput_verified", "supervisor_cgroup_empty", "windows_parents_absent")) and
            parent["terminal_sha256"] == plan["source_sha256"], "retained source parent not closed")
    loader_definitions["validate_diagnostic_startup"](plan, read(plan["retained_source_custody"]), row)
    from .red_player_package import bind_player_package
    bind_player_package(Path(plan["package"]), plan["package_sha256"], history_output=Path(output))
    from .red_native_player import NativePlayerSession, NativeExecutionIdentity
    from .red_player_model import load_player_goal_model_record
    from .living_dex_option_value import upgrade_option_value_model_for_move_change
    model = load_player_goal_model_record(Path(plan["goal_model_record"]["path"]),
                                         expected_model_sha256=plan["goal_model_sha256"]).model
    require(upgrade_option_value_model_for_move_change(model).model_sha256 == plan["zero_extended_goal_model_sha256"],
            "zero-extension changed existing model")
    kwargs = build_teacher_session_kwargs(spec, store=None, emulator=None, runtime_factory=None,
        source=dict(partition="train", state_sha256=plan["source_sha256"]),
        execution=NativeExecutionIdentity("preflight", "teacher-assigned-train", plan["zero_extended_goal_model_sha256"], plan["seed"]),
        output=Path("unused-preflight-output"), battle_observer=lambda: None,
        teacher_receipt_sha256=sha(plan["assisted_progress"]), callbacks={})
    signature(NativePlayerSession).bind(**kwargs)
    return dict(passed=True, phase="preflight", plan_sha256=plan_sha256, worker_sha256=worker_sha256,
                teacher_case=spec.document(), package_sha256=plan["package_sha256"],
                session_configuration=spec.document()["session"], emulators=0, loads=0, inputs=0, frames=0,
                fits=0, new_weights=0, native_observation_pending=True,
                scope="static source/pins/constructor only; full menu, PP, roles and native contract still gate before input")
