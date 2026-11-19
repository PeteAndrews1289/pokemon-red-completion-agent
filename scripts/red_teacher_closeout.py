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
        return dict(
            controls_released=True,
            release_basis="zero-emulator preflight and closed process chain",
            terminal_available=False,
            native_costs_known=True,
            native_costs=dict(actions=0, frames=0, native_seconds=0),
        )
    if phase != "direct":
        raise ValueError("unsupported phase")
    physical = result.get("physical_emulator_accounting")
    if physical is None:
        if result.get("native_dispatch_entered") is not False or result.get("passed") is not False:
            raise ValueError("missing physical accounting after native dispatch")
        physical = dict(
            construction_attempts=0, emulators_constructed=0, load_attempts=0, state_loads=0
        )
    keys = ("construction_attempts", "emulators_constructed", "load_attempts", "state_loads")
    if set(physical) != set(keys) or any(
        type(physical[key]) is not int or not 0 <= physical[key] <= 1 for key in keys
    ):
        raise ValueError("physical accounting exceeds one declared load")
    if not (
        physical["state_loads"]
        <= physical["load_attempts"]
        <= physical["emulators_constructed"]
        <= physical["construction_attempts"]
    ):
        raise ValueError("physical accounting order differs")
    terminal = result.get("terminal_sha256")
    if terminal is not None and terminal != terminal_sha256:
        raise ValueError("exported terminal digest differs")
    if terminal_sha256 is not None and terminal is None:
        raise ValueError("unclaimed terminal file present")
    if result.get("passed") is True and (
        terminal is None
        or result.get("controls_released") is not True
        or any(physical[key] != 1 for key in keys)
    ):
        raise ValueError("successful native case lacks native terminal/release proof")
    no_attempt = physical["construction_attempts"] == 0
    metrics = {
        key: result.get(key)
        for key in (
            "actions",
            "frames",
            "goal_attempts",
            "heals",
            "native_seconds",
            "wild_battles",
            "story_battles",
        )
    }
    if no_attempt:
        if any(value not in (None, 0) for value in metrics.values()):
            raise ValueError("preconstruction failure claims native work")
        metrics = {key: 0 for key in metrics}
    return dict(
        controls_released=True,
        release_basis=(
            "native release receipt and closed process chain"
            if result.get("controls_released") is True
            else "all authenticated actor/supervisor processes absent and cgroup empty"
        ),
        native_release_observed=result.get("controls_released") is True,
        terminal_available=terminal is not None,
        resumable_terminal_claim=bool(terminal is not None and physical["state_loads"] == 1),
        native_costs_known=all(value is not None for value in metrics.values()),
        native_costs=metrics,
        physical_emulator_accounting=physical,
        row_requires_separate_readback=bool(result.get("row")),
        native_admission_authority=False,
        continuation_authority=False,
    )


def classify_decision_ownership(choice):
    """Count declared parent queries without losing branch-free singleton rows.

    Raw model choice modes call the parent once, even without a child receipt.
    Unknown receipts remain unknown; missing evidence must not count as support.
    This classifies provenance only and never grants execution authority.
    """
    if not isinstance(choice, dict):
        raise ValueError("decision ownership requires a receipt dictionary")
    branch = choice.get("branch_recovery", {})
    if not isinstance(branch, dict):
        raise ValueError("branch ownership receipt differs")
    parent = branch.get("parent_model_queries", choice.get("model_queries"))
    if parent is None:
        if choice.get("schema") == "pokemon.red.live-mixed-option-choice.v1":
            if choice.get("mode") in {"model_greedy", "model_exploration"}:
                parent = 1
            elif choice.get("mode") in {
                "equivalent_exploration", "deterministic_safety", "forced_singleton_support"
            }:
                parent = 0
    if parent is not None and (type(parent) is not int or parent < 0):
        raise ValueError("parent query count differs")
    child = branch.get("child_model_queries", 0)
    if type(child) is not int or child < 0:
        raise ValueError("child query count differs")
    return dict(
        parent_queries=parent,
        owner=("parent_model" if parent else "disclosed_support")
        if parent is not None else "unknown",
        child_queries=child,
        child_overrode=branch.get("child_overrode_parent_binding", False),
    )
