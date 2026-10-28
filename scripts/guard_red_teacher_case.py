"""Shared existing-pattern lifecycle claim; no native imports or case-specific code."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
import os
import re


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_source_claim(claim, mission):
    require(claim.get("source_writer_active") is True
            and claim["source_writer_mission"] == mission and claim["actual_running"] is False
            and claim["all_native_workers_stopped"] is True and claim.get("active_probe") is None,
            "exclusive active mission/source claim is not clear")


def validate_guard_spec(spec, resource, plan):
    """Pure validation is also used by the Windows/chain golden tests."""
    phase = spec["phase"]
    require(phase in ("preflight", "direct"), "unsupported teacher phase")
    case = Path(spec["case"]).resolve()
    capacity = Path(spec["capacity_root"]).resolve()
    require(case.parent == capacity, "case outside declared capacity root")
    require(Path(spec["worker"]).resolve().is_relative_to(capacity), "shared worker outside supervisor scope")
    require(Path(spec["plan"]).resolve() == case / "PLAN.json", "shared case plan differs")
    require(Path(plan["case"]).resolve() == case, "plan case identity differs")
    if phase == "direct":
        require(plan.get("native_execution_authorized") is True, "native execution disabled")
    require(spec["guard_sha256"] == sha(spec["guard"]), "guard file differs")
    command = [spec["python"], "-I", "-B", spec["worker"], "--case", str(case),
               "--plan-sha256", spec["plan_sha256"], "--phase", phase]
    require(spec["worker_command"] == resource["command"] == command, "exact declared worker command differs")
    require(resource["script_sha256"] == spec["worker_sha256"], "resource worker pin differs")
    require(resource["absolute_cutoff_utc"] == plan["cutoff_utc"], "resource cutoff differs")
    require(resource["outer_seconds"] == (plan["preflight_root_seconds"] if phase == "preflight" else plan["full_hold_seconds"]),
            "phase resource duration differs")
    require(spec["linux_user"] == "pokemon" and isinstance(spec["distribution"], str)
            and re.fullmatch(r"[A-Za-z0-9_.-]+", spec["distribution"]), "host identity declaration invalid")
    require(plan["mission"] == spec["mission"], "mission identity differs")
    require(spec["guard_arguments"][:1] == ["--spec"] and len(spec["guard_arguments"]) == 2,
            "guard interface differs")
    return case / "preflight" if phase == "preflight" else case


def actors(capacity):
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            command = [os.fsdecode(item) for item in (proc / "cmdline").read_bytes().split(b"\0") if item]
        except (OSError, ProcessLookupError):
            continue
        if any(arg.startswith(str(capacity) + "/") and arg.endswith(".py") for arg in command):
            found.append(dict(pid=int(proc.name), command=command))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--spec-sha256", required=True)
    args = parser.parse_args(argv)
    require(sha(args.spec) == args.spec_sha256, "launch specification differs")
    spec = read(args.spec)
    for key in ("worker", "plan", "package", "supervisor", "resource_plan", "guard"):
        require(sha(spec[key]) == spec[key + "_sha256"], "pin differs: " + key)
    for path, digest in spec["additional_pins"].items():
        require(sha(path) == digest, "additional pin differs: " + path)
    plan, resource = read(spec["plan"]), read(spec["resource_plan"])
    output = validate_guard_spec(spec, resource, plan)
    # The specification cannot pin its own digest. The caller supplies it and the
    # launcher fills these arguments after verifying the complete specification.
    require(spec["guard_arguments"][1] == str(args.spec), "guard targets another specification")
    with Path(spec["source_lock"]).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        claim = read(spec["source_claim"])
        validate_source_claim(claim, spec["mission"])
        inventory = actors(Path(spec["capacity_root"]))
        require(not inventory, "another capacity process is present: " + repr(inventory))
        cutoff = datetime.fromisoformat(plan["cutoff_utc"])
        minimum = plan["aggregate_full_hold_seconds"] if spec["phase"] == "preflight" else plan["full_hold_seconds"] + plan["closeout_seconds"]
        require((cutoff - datetime.now(timezone.utc)).total_seconds() >= minimum, "insufficient fixed-cutoff hold")
        require(cutoff <= datetime.fromisoformat(read(spec["mission"])["deadline_utc"]), "case exceeds mission cutoff")
        require(not (output / "EARLY-LINUX-IDENTITY.json").exists(), "phase already started")
        if spec["phase"] == "direct":
            auth = read(Path(spec["case"]) / "preflight/TERMINAL-AUTHENTICATION.json")
            require(all(auth[key] is True for key in ("passed", "all_original_processes_absent", "controls_released", "supervisor_cgroup_empty", "windows_parents_absent")), "preflight not closed")
            qualification = read(Path(spec["case"]) / "preflight/QUALIFICATION.json")
            require(qualification["passed"] is True and qualification["plan_sha256"] == spec["plan_sha256"]
                    and qualification["worker_sha256"] == spec["worker_sha256"]
                    and qualification["package_sha256"] == spec["package_sha256"], "preflight pins differ")
        with (output / "LAUNCH-CLAIM.json").open("x") as stream:
            json.dump(dict(phase=spec["phase"], observed_at_utc=datetime.now(timezone.utc).isoformat(),
                           plan_sha256=spec["plan_sha256"], actor_inventory=[]), stream, indent=2)
        claim.update(active_probe=str(output), all_native_workers_stopped=spec["phase"] == "preflight")
        Path(spec["source_claim"]).write_text(json.dumps(claim, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
