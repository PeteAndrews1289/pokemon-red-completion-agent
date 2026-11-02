"""Short, separately initialized development-pilot origins; never a campaign.

The approved protocol grants this scope, not the source labels or hashes alone.
No old snapshot is read and the opening's controller cannot load a state.
All children must inherit the source assignment; setup is not learner evidence.
"""

import json
import math
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

from .actions import MacroAction, MacroActionKind
from .bootstrap import DEFAULT_NEW_GAME_TIMING
from .emulator import PyBoyAdapter
from .executor import (
    ControllerActionLimiter,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from .observation import OpeningPhase, PokemonRedStateReader
from .opening import run_opening_chapter
from .provenance import canonical_sha256
from .red_autonomous_player import _record, _write
from .red_safari_training_setup import RED_ROM_SHA256

ASSIGNMENTS = {
    "train-01": ("train", 11),
    "comparison-01": ("development", 43),
    "comparison-02": ("development", 79),
}
LIMITS = dict(actions=450, frames=80000, seconds=180)
COMPARISON_ASSIGNMENTS = {
    "comparison-03": ("development", 113),
    "comparison-04": ("development", 149),
}
BRANCH_COMPARISON_ASSIGNMENTS = {
    "comparison-05": ("development", 181),
    "comparison-06": ("development", 223),
}
PREPARATION_COMPARISON_ASSIGNMENTS = {
    "comparison-07": ("development", 257),
    "comparison-08": ("development", 293),
}
FOCUSED_PREPARATION_COMPARISON_ASSIGNMENTS = {
    "comparison-09": ("development", 337),
    "comparison-10": ("development", 373),
}
CONNECTED_PREPARATION_COMPARISON_ASSIGNMENTS = {
    "comparison-11": ("development", 409),
    "comparison-12": ("development", 443),
}


def _tranche(tranche):
    if tranche == "initial":
        return (ASSIGNMENTS, "pokemon.red.player-independent-origins.v1",
                "docs/player-assisted-source-protocol.md")
    if tranche == "comparison-03-04":
        return (COMPARISON_ASSIGNMENTS, "pokemon.red.player-independent-origins.v2",
                "docs/player-fresh-comparison-plan-2026-09-26.md")
    if tranche == "comparison-05-06":
        return (BRANCH_COMPARISON_ASSIGNMENTS, "pokemon.red.player-independent-origins.v3",
                "docs/player-branch-comparison-plan-2026-09-27.md")
    if tranche == "comparison-07-08":
        return (PREPARATION_COMPARISON_ASSIGNMENTS, "pokemon.red.player-independent-origins.v4",
                "docs/work-sessions/2026-09-28-preparation-value-experiment.md")
    if tranche == "comparison-09-10":
        return (FOCUSED_PREPARATION_COMPARISON_ASSIGNMENTS,
                "pokemon.red.player-independent-origins.v5",
                "docs/work-sessions/2026-09-30-learned-preparation-v1.md")
    if tranche == "comparison-11-12":
        return (CONNECTED_PREPARATION_COMPARISON_ASSIGNMENTS,
                "pokemon.red.player-independent-origins.v6",
                "docs/work-sessions/2026-09-30-preparation-three-gates.md")
    raise ValueError("undeclared player origin tranche")


def source_code_identity(repository):
    """Pin executable dependencies, not directory names or a dirty HEAD label."""
    root = Path(repository)
    return canonical_sha256({
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "src/pokemon_red_completion").glob("*.py"))
    })


def freeze_origin_plan(output, *, repository, source_commit, rom_sha256, tranche="initial"):
    assignments, schema, authorization = _tranche(tranche)
    if rom_sha256 != RED_ROM_SHA256:
        raise ValueError("origin plan requires the pinned Red cartridge")
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit):
        raise ValueError("origin plan requires a source revision")
    plan = dict(
        schema=schema,
        authorization=authorization,
        rom_sha256=rom_sha256,
        source_commit=source_commit,
        source_bundle_sha256=source_code_identity(repository),
        assignments={key: dict(partition=part, extra_boot_frames=offset)
                     for key, (part, offset) in assignments.items()},
        limits=LIMITS,
        timing=asdict(DEFAULT_NEW_GAME_TIMING),
        checkpoint="starter_obtained",
        policy_queries=0,
        fits=0,
        historical_assignments_reopened=False,
    )
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(output / "plan.json", plan)
    return canonical_sha256(plan)


class _NoLoadController(FrameBudgetController):
    def load_state_bytes(self, payload):
        raise ValueError("independent origin must never load a snapshot")


class _OpeningActions:
    def __init__(self, controller, output):
        self.controller, self.output = controller, output
        self.delegate = ControllerActionLimiter(
            FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing()),
            maximum_actions=LIMITS["actions"],
        )
        self.receipts = []

    def execute(self, action):
        index = len(self.receipts)
        before = self.controller.frame_count
        intent = dict(index=index, action=asdict(action), start_frame=before)
        _record(self.output / f"action-{index:04d}-intent.json", intent)
        error = None
        try:
            return self.delegate.execute(action)
        except BaseException as caught:
            error = type(caught).__name__
            raise
        finally:
            receipt = dict(
                **intent, end_frame=self.controller.frame_count,
                succeeded=error is None, error_type=error,
                buttons_released=not self.controller.pressed_buttons,
            )
            _record(self.output / f"action-{index:04d}-result.json", receipt)
            self.receipts.append(receipt)


def capture_origin(output, source_id, *, repository, rom_path, expected_plan_sha256,
                   tranche="initial"):
    """Claim once, open one new emulator, stop at starter, retain any failure."""
    output, rom_path = Path(output), Path(rom_path)
    assignments, schema, authorization = _tranche(tranche)
    plan = json.loads((output / "plan.json").read_bytes())
    if (
        canonical_sha256(plan) != expected_plan_sha256
        or source_id not in assignments
        or plan.get("schema") != schema or plan.get("authorization") != authorization
        or plan.get("checkpoint") != "starter_obtained"
        or plan.get("policy_queries") != 0 or plan.get("fits") != 0
        or plan.get("historical_assignments_reopened") is not False
        or not isinstance(plan.get("source_commit"), str)
        or len(plan["source_commit"]) != 40
        or any(c not in "0123456789abcdef" for c in plan["source_commit"])
        or plan["source_bundle_sha256"] != source_code_identity(repository)
        or sha256(rom_path.read_bytes()).hexdigest() != RED_ROM_SHA256
        or plan["rom_sha256"] != RED_ROM_SHA256
        or plan["assignments"] != {
            key: dict(partition=part, extra_boot_frames=offset)
            for key, (part, offset) in assignments.items()
        }
        or plan["limits"] != LIMITS
        or plan["timing"] != asdict(DEFAULT_NEW_GAME_TIMING)
    ):
        raise ValueError("origin plan, code, cartridge or assignment differs")
    target = output / source_id
    target.mkdir(mode=0o700, exist_ok=False)
    _record(target / "claim.json", dict(plan_sha256=expected_plan_sha256, source_id=source_id))
    result = dict(
        schema="pokemon.red.player-independent-origin-result.v1",
        source_id=source_id, partition=assignments[source_id][0],
        plan_sha256=expected_plan_sha256, source_bundle_sha256=plan["source_bundle_sha256"],
        source_commit=plan["source_commit"], passed=False, state_loads=0,
        policy_queries=0, fits=0, setup_memory_writes=0,
        independence_scope="separate initialization; shared cartridge and opening procedure",
    )
    try:
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            if emulator.frame_count != 0 or emulator.pressed_buttons:
                raise ValueError("origin did not start at untouched power-on")
            wall = MonotonicWallTimeBudgetController(
                emulator, maximum_wall_seconds=LIMITS["seconds"],
            )
            controller = _NoLoadController(wall, maximum_frames=LIMITS["frames"])
            actions = _OpeningActions(controller, target)
            initial = controller.save_state_bytes()
            _write(target / "power-on.state", initial)
            result["power_on_sha256"] = sha256(initial).hexdigest()
            try:
                # Vary independent initializations, never load a common warm snapshot.
                timing = replace(
                    DEFAULT_NEW_GAME_TIMING,
                    boot_frames=DEFAULT_NEW_GAME_TIMING.boot_frames + assignments[source_id][1],
                )
                report = run_opening_chapter(
                    rom_path, new_game_timing=timing, _emulator=controller, _executor=actions,
                )
                if not report.passed or controller.pressed_buttons:
                    raise ValueError("native starter opening did not qualify")
                _record(target / "opening.json", report.public_dict())
                result["passed"] = True
            finally:
                terminal = controller.save_state_bytes()
                _write(target / "terminal.state", terminal)
                result.update(
                    terminal_sha256=sha256(terminal).hexdigest(),
                    frames=controller.frames_executed, seconds=wall.elapsed_seconds,
                    action_records=len(actions.receipts),
                    actions_attempted=actions.delegate.attempted_actions,
                    actions_completed=actions.delegate.completed_actions,
                    transcript_sha256=canonical_sha256(actions.receipts),
                    buttons_released=not controller.pressed_buttons,
                )
    except BaseException as error:
        result.update(passed=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        _record(target / "result.json", result)
    return result


def audit_origin(
    output, source_id, *, rom_path, expected_plan_sha256, expected_result_sha256,
    tranche="initial",
):
    """Reopen one pinned creation transcript and state without advancing frames.

    An authenticated old origin is still consumed under its original protocol.
    This provides ancestry evidence, not allocation, reset or training authority.
    Expected plan/result hashes must come from separately retained declarations.
    """
    output, rom_path = Path(output), Path(rom_path)
    assignments, schema, authorization = _tranche(tranche)
    plan = json.loads((output / "plan.json").read_bytes())
    if (source_id not in assignments or canonical_sha256(plan) != expected_plan_sha256
        or plan.get("schema") != schema or plan.get("authorization") != authorization
        or plan.get("assignments") != {
            k: dict(partition=p, extra_boot_frames=n) for k, (p, n) in assignments.items()
        }
        or plan.get("checkpoint") != "starter_obtained" or plan.get("limits") != LIMITS
        or plan.get("timing") != asdict(DEFAULT_NEW_GAME_TIMING)
        or plan.get("historical_assignments_reopened") is not False
        or plan.get("policy_queries") != 0 or plan.get("fits") != 0
        or plan.get("rom_sha256") != RED_ROM_SHA256
        or sha256(rom_path.read_bytes()).hexdigest() != RED_ROM_SHA256):
        raise ValueError("origin audit declaration differs")
    directory = output / source_id
    payload = (directory / "result.json").read_bytes()
    r = json.loads(payload)
    claim = json.loads((directory / "claim.json").read_bytes())
    count = r.get("action_records")
    if (sha256(payload).hexdigest() != expected_result_sha256
        or r.get("schema") != "pokemon.red.player-independent-origin-result.v1"
        or r.get("source_id") != source_id or r.get("passed") is not True
        or r.get("partition") != assignments[source_id][0]
        or r.get("plan_sha256") != expected_plan_sha256
        or any(r.get(k) != plan[k] for k in ("source_commit", "source_bundle_sha256"))
        or claim != dict(plan_sha256=expected_plan_sha256, source_id=source_id)
        or any(type(r.get(k)) is not int or r[k] != 0
               for k in ("state_loads", "policy_queries", "fits", "setup_memory_writes"))
        or type(count) is not int or not 1 <= count <= LIMITS["actions"]
        or type(r.get("actions_attempted")) is not int or r["actions_attempted"] != count
        or type(r.get("actions_completed")) is not int or r["actions_completed"] != count
        or type(r.get("frames")) is not int or not 0 < r["frames"] <= LIMITS["frames"]
        or type(r.get("seconds")) not in (int, float) or not math.isfinite(r["seconds"])
        or not 0 <= r["seconds"] <= LIMITS["seconds"]
        or r.get("buttons_released") is not True):
        raise ValueError("origin creation result is incomplete or differs")
    if set(directory.glob("action-*.json")) != {
        directory / f"action-{i:04d}-{phase}.json"
        for i in range(count) for phase in ("intent", "result")
    }:
        raise ValueError("origin creation action census differs")
    rows = []
    frame = 0
    for i in range(count):
        intent = json.loads((directory / f"action-{i:04d}-intent.json").read_bytes())
        row = json.loads((directory / f"action-{i:04d}-result.json").read_bytes())
        action = intent["action"]
        MacroAction(MacroActionKind(action["kind"]), action["value"], action["repeat"])
        if (set(intent) != {"index", "action", "start_frame"}
            or type(intent["index"]) is not int or intent["index"] != i
            or type(intent["start_frame"]) is not int or intent["start_frame"] != frame
            or type(row.get("end_frame")) is not int or row["end_frame"] <= frame
            or canonical_sha256(row) != canonical_sha256(dict(
                **intent, end_frame=row["end_frame"], succeeded=True, error_type=None,
                buttons_released=True,
            ))):
            raise ValueError("origin creation trace differs")
        rows.append(row)
        frame = row["end_frame"]
    if frame != r["frames"] or canonical_sha256(rows) != r.get("transcript_sha256"):
        raise ValueError("origin creation transcript total differs")
    power = (directory / "power-on.state").read_bytes()
    terminal = (directory / "terminal.state").read_bytes()
    if (sha256(power).hexdigest() != r["power_on_sha256"]
        or sha256(terminal).hexdigest() != r["terminal_sha256"]):
        raise ValueError("origin creation state bytes differ")
    with PyBoyAdapter(rom_path) as emulator:
        if emulator.frame_count != 0 or emulator.save_state_bytes() != power:
            raise ValueError("recorded origin is not this adapter's pristine power-on state")
        emulator.load_state_bytes(terminal)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if (reader.read_opening_control_state(raw).phase is not OpeningPhase.STARTER_OBTAINED
            or raw.party_count != 1 or raw.battle_state != 0
            or emulator.frame_count != 0 or emulator.pressed_buttons
            or emulator.save_state_bytes() != terminal):
            raise ValueError("origin native terminal is not a stable starter boundary")
    return dict(
        source_id=source_id, partition=assignments[source_id][0],
        plan_sha256=expected_plan_sha256, result_sha256=expected_result_sha256,
        origin_sha256=r["terminal_sha256"], transcript_sha256=r["transcript_sha256"],
        source_commit=r["source_commit"], source_bundle_sha256=r["source_bundle_sha256"],
        audit_frames=0, training_eligible=False, reuse_authorized=False,
    )
