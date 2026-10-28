"""One versioned CAP entrypoint; case differences are pinned data, never script copies."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import runpy
import sys
import time
import traceback


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    from collections.abc import Mapping
    def encode(item):
        if isinstance(item, Mapping):
            return dict(item)
        raise TypeError("unsupported receipt value: " + type(item).__name__)
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, default=encode)
        stream.write("\n")


def identity(pid):
    proc = Path("/proc") / str(pid)
    stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    return dict(pid=pid, parent_pid=int(stat[1]), start_ticks=int(stat[19]), uid=proc.stat().st_uid,
                command=[os.fsdecode(item) for item in (proc / "cmdline").read_bytes().split(b"\0") if item])


def bootstrap(plan, worker):
    if plan["driver_sha256"] != sha(worker):
        raise ValueError("shared entrypoint file differs")
    package = Path(plan["package"]).parent
    if sha(plan["package"]) != plan["package_sha256"]:
        raise ValueError("frozen manifest differs")
    manifest = read(plan["package"])
    loader = package / "checkout/scripts/launch_frozen_red_player.py"
    if sha(loader) != manifest["pins"][str(loader)]:
        raise ValueError("frozen loader differs")
    if any(name == "pokemon_red_completion" or name.startswith("pokemon_red_completion.") for name in sys.modules):
        raise ValueError("source imported before frozen authentication")
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(package / "checkout/src"), str(package / "helpers"), str(package / "checkout/scripts")]
    definitions = runpy.run_path(str(loader), run_name="teacher_frozen_loader")
    sys.meta_path.insert(0, definitions["FrozenSourceFinder"](package, manifest["pins"], manifest["environment_pins"]))
    return definitions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--phase", choices=("preflight", "direct"), required=True)
    args = parser.parse_args(argv)
    case = args.case.resolve()
    plan_path = case / "PLAN.json"
    if sha(plan_path) != args.plan_sha256:
        raise ValueError("exact prospective plan differs")
    plan = read(plan_path)
    if not Path(plan["case"]).is_absolute() or Path(plan["case"]).resolve() != case:
        raise ValueError("exact allocated case identity differs")
    if args.phase == "direct" and plan.get("native_execution_authorized") is not True:
        raise ValueError("native execution disabled")
    output = case / "preflight" if args.phase == "preflight" else case
    if not output.is_dir():
        raise ValueError("root must allocate the phase directory")
    worker = Path(__file__).resolve()
    parent = identity(os.getppid())
    write(output / "EARLY-LINUX-IDENTITY.json", dict(
        processes=[identity(os.getpid()), parent], supervisor=identity(parent["parent_pid"]), worker_sha256=sha(worker),
        plan_sha256=args.plan_sha256, boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(), phase=args.phase))
    started = time.monotonic()
    result = dict(passed=False, phase=args.phase, emulators=0, loads=0, inputs=0, frames=0, fits=0, native_dispatch_entered=False)
    try:
        definitions = bootstrap(plan, worker)
        if args.phase == "preflight":
            from pokemon_red_completion.red_teacher_preflight import preflight_direct
            result = preflight_direct(plan, plan_sha256=args.plan_sha256, worker_sha256=sha(worker), loader_definitions=definitions, output=output)
            write(output / "QUALIFICATION.json", result)
        else:
            from pokemon_red_completion.red_teacher_direct import run_direct
            result["native_dispatch_entered"] = True
            result = run_direct(plan, output=output, worker_path=worker,
                                loader_definitions=definitions, started=started, write=write)
    except BaseException as error:
        result.update(passed=False, error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    finally:
        result.update(seconds=time.monotonic()-started, finished_at_utc=datetime.now(timezone.utc).isoformat())
        write(output / "RESULT.json", result)
    print(json.dumps({key: value for key, value in result.items() if key not in ("row", "traceback", "teacher_case")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
