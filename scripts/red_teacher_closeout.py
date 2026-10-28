"""Pure classification after independent process-chain and empty-cgroup proof.

Closing a failed process is not admitting its row, recovering a save, or granting
another launch. Unknown native costs and unavailable terminals remain explicit.
"""


def classify_closed_phase(result, *, phase, processes_absent, cgroup_empty, terminal_sha256=None):
    if processes_absent is not True or cgroup_empty is not True:
        raise ValueError("complete process closure required")
    if phase == "preflight":
        if any(result.get(key) != 0 for key in ("emulators", "loads", "inputs", "frames")):
            raise ValueError("preflight native quantities differ")
        return dict(controls_released=True, release_basis="zero-emulator preflight and closed process chain",
                    terminal_available=False, native_costs_known=True, native_costs=dict(actions=0, frames=0, native_seconds=0))
    if phase != "direct":
        raise ValueError("unsupported phase")
    physical = result.get("physical_emulator_accounting")
    if physical is None:
        if result.get("native_dispatch_entered") is not False or result.get("passed") is not False:
            raise ValueError("missing physical accounting after native dispatch")
        physical = dict(construction_attempts=0, emulators_constructed=0, load_attempts=0, state_loads=0)
    keys = ("construction_attempts", "emulators_constructed", "load_attempts", "state_loads")
    if set(physical) != set(keys) or any(type(physical[key]) is not int or not 0 <= physical[key] <= 1 for key in keys):
        raise ValueError("physical accounting exceeds one declared load")
    if not (physical["state_loads"] <= physical["load_attempts"] <= physical["emulators_constructed"] <= physical["construction_attempts"]):
        raise ValueError("physical accounting order differs")
    terminal = result.get("terminal_sha256")
    if terminal is not None and terminal != terminal_sha256:
        raise ValueError("exported terminal digest differs")
    if terminal_sha256 is not None and terminal is None:
        raise ValueError("unclaimed terminal file present")
    if result.get("passed") is True:
        if (terminal is None or result.get("controls_released") is not True or
                any(physical[key] != 1 for key in keys)):
            raise ValueError("successful native case lacks native terminal/release proof")
    no_attempt = physical["construction_attempts"] == 0
    metrics = {key: result.get(key) for key in ("actions", "frames", "goal_attempts", "heals", "native_seconds", "wild_battles", "story_battles")}
    if no_attempt:
        if any(value not in (None, 0) for value in metrics.values()):
            raise ValueError("preconstruction failure claims native work")
        metrics = {key: 0 for key in metrics}
    return dict(controls_released=True,
                release_basis=("native release receipt and closed process chain" if result.get("controls_released") is True
                               else "all authenticated actor/supervisor processes absent and cgroup empty"),
                native_release_observed=result.get("controls_released") is True,
                terminal_available=terminal is not None,
                resumable_terminal_claim=bool(terminal is not None and physical["state_loads"] == 1),
                native_costs_known=all(value is not None for value in metrics.values()),
                native_costs=metrics, physical_emulator_accounting=physical,
                row_requires_separate_readback=bool(result.get("row")),
                native_admission_authority=False, continuation_authority=False)
