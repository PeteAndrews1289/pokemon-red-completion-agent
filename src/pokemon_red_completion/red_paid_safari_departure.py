"""Metered native departure from an earned paid Safari session.

Mechanical recovery only: no new target, model query, admission fee or learning
label. The original search remains failed. Plans come from the cartridge graph.
"""

from __future__ import annotations

import json
from dataclasses import replace
from functools import partial

from .gen1_field_moves import Gen1FieldMovePort
from .gen1_route_runtime import Gen1TraversalObserver
from .goal_manager import GoalDecisionOutcome
from .observation import MapId
from .provenance import canonical_sha256
from .red_autonomous_player import _exception_chain, _record, _write
from .red_resource_goal_router import _ROUTE_LIMITS, _supported_plan, collection_field_capabilities
from .red_routed_recovery import guarded_collection_route_handler
from .red_routed_semantic_goal import RedSemanticTransportRoute
from .red_safari_exit import (
    RedSafariDepartureInterruptionHandler,
    RedSafariExitDialogueHandler,
    normalize_active_safari_exit_plan,
    safari_departure_within_steps,
)

EXIT_SCHEMA = "pokemon.red.paid-safari-departure.v1"
PROTECTED_FACTS = (
    "cash",
    "owned_species",
    "registered_species",
    "specimen_counts",
    "specimens",
    "bag_items",
    "party_hp",
    "party_pp",
    "party_training",
)
PARK_MAPS = frozenset(
    {
        int(MapId.SAFARI_ZONE_CENTER),
        int(MapId.SAFARI_ZONE_EAST),
        int(MapId.SAFARI_ZONE_NORTH),
        int(MapId.SAFARI_ZONE_WEST),
    }
)


def paid_search_step_reserve(controller, reader, world, patrol):
    """Price the exit from BOTH reversible patrol endpoints before searching."""
    traversal = Gen1TraversalObserver(
        reader,
        capability_projector=partial(
            collection_field_capabilities, controller, allow_cut=False, allow_surf=True
        ),
    )
    start = traversal.observe()
    if start.map_id != patrol.map_id or start.at not in {patrol.first_at, patrol.second_at}:
        raise ValueError("paid search is not at its bound patrol")
    plans = [
        plan_paid_safari_departure(replace(start, at=point), world, reader)
        for point in (patrol.first_at, patrol.second_at)
    ]
    # Include the full route, the existing sixteen-step escape allowance and
    # one extra patrol step. Do not spend this reserve on rare encounters.
    return max(len(plan.steps) for plan in plans) + 18


def exit_paid_search(controller, actions, reader, world):
    """Return after capture or exhaustion; exit is not acquisition success."""
    from .red_party import PokemonRedPartyReader
    from .red_safari_exit import _full_collection_state

    def resources():
        raw = reader.read()
        return (
            raw.player_money,
            raw.bag_items,
            PokemonRedPartyReader(controller).read(),
            _full_collection_state(reader),
        )

    before = resources()
    binding, _ = bind_paid_safari_departure(controller, actions, reader, world)
    report = binding.execute()
    if (
        binding.verify(report).status is not GoalDecisionOutcome.SUCCEEDED
        or resources() != before
        or reader.read_safari_session_state().in_safari_zone
    ):
        raise ValueError("paid search departure did not preserve its earned resources")
    return dict(report.evidence)


def plan_paid_safari_departure(start, world, reader):
    """Reject unsafe, unsupported or over-timer routes without controller input."""
    session = reader.read_safari_session_state()
    if (
        not start.ready
        or start.interruption is not None
        or start.map_id not in PARK_MAPS
        or start.mode not in {"land", "water"}
        or not session.in_safari_zone
        or session.safari_game_over
        or session.safari_balls <= 0
        or start.last_outside_map != int(MapId.FUCHSIA_CITY)
    ):
        raise ValueError("paid Safari departure needs a ready active park boundary")
    plan = world.plan_feasible_to_map(start, int(MapId.FUCHSIA_CITY))
    plan = normalize_active_safari_exit_plan(plan)
    allowed = PARK_MAPS | {int(MapId.SAFARI_ZONE_GATE), int(MapId.FUCHSIA_CITY)}
    if (
        plan is None
        or not plan.steps
        or not _supported_plan(plan, allow_surf=True)
        or plan.terminal_map != int(MapId.FUCHSIA_CITY)
        or plan.terminal_mode != "land"
        or not set(plan.macro_path.maps) <= allowed
        or not safari_departure_within_steps(plan, reader)
    ):
        raise ValueError("paid Safari departure lacks a supported step-safe exit")
    return plan


def bind_paid_safari_departure(controller, actions, reader, world):
    traversal = Gen1TraversalObserver(
        reader,
        capability_projector=partial(
            collection_field_capabilities, controller, allow_cut=False, allow_surf=True
        ),
    )
    start = traversal.observe()
    plan = plan_paid_safari_departure(start, world, reader)
    fallback = guarded_collection_route_handler(
        actions, reader, route_name="paid Safari departure", maximum_scripted_dialogues=1
    )
    handler = RedSafariDepartureInterruptionHandler(
        controller, actions, reader, RedSafariExitDialogueHandler(actions, reader, fallback)
    )
    origin_sha = canonical_sha256(
        {
            "map_id": start.map_id,
            "at": start.at,
            "mode": start.mode,
            "capabilities": sorted(start.capabilities),
        }
    )
    transport = RedSemanticTransportRoute(
        binding_ref="paid-safari-departure:" + origin_sha,
        origin_observation_sha256=origin_sha,
        planner_binding_sha256=canonical_sha256({"schema": EXIT_SCHEMA}),
        plan=plan,
        actions=actions,
        traversal_observer=traversal,
        emulator=controller,
        interruption_handler=handler,
        route_limits=_ROUTE_LIMITS,
        field_actions=Gen1FieldMovePort(actions, reader, controller),
    )
    # No unbounded replanning: unexpected displacement remains a retained failure.
    return transport.route_binding(), transport.public_dict()


def require_departure_facts(before, after):
    for key in PROTECTED_FACTS:
        if key not in before or key not in after or before[key] != after[key]:
            raise ValueError("paid Safari departure changed " + key)
    session = after["session"]
    if (
        after["map_id"] != int(MapId.FUCHSIA_CITY)
        or after["battle_state"] != 0
        or after["input_ready"] is not True
        or session["in_safari_zone"] is not False
        or session["safari_game_over"] is not False
        or not before["session"]["in_safari_zone"]
    ):
        raise ValueError("paid Safari departure did not reach an inactive outdoor boundary")


def run_paid_safari_departure(*, output, snapshot, binding, route, provenance):
    """Claim once and retain both the terminal and failure, including exceptions."""
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": EXIT_SCHEMA,
            "provenance": dict(provenance),
            "model_queries": 0,
            "learning_eligible": False,
            "route": route,
        },
    )
    before = snapshot()
    _write(output / "before.state", before.state)
    _record(
        output / "execution-started.json",
        {"state_sha256": before.sha256, "binding_ref": binding.binding_ref, "model_queries": 0},
    )
    error = report = verification = None
    try:
        if not before.safe:
            raise ValueError("unsafe paid departure origin")
        report = binding.execute()
        verification = binding.verify(report)
        if verification.status is not GoalDecisionOutcome.SUCCEEDED:
            raise ValueError("native paid departure route did not verify")
        require_departure_facts(before.facts, snapshot().facts)
    except BaseException as caught:
        error = caught
    finally:
        terminal = snapshot()
        _write(output / "terminal.state", terminal.state)
        outcome = {
            "before_state_sha256": before.sha256,
            "terminal_state_sha256": terminal.sha256,
            "before": dict(before.facts),
            "after": dict(terminal.facts),
            "safe_terminal": terminal.safe,
            "verification": "paid_session_exited" if error is None else None,
            "evidence": None if report is None else dict(report.evidence),
            "error_chain": _exception_chain(error),
            "model_queries": 0,
            "learning_eligible": False,
        }
        _record(output / "outcome.json", outcome)
        result = {
            "schema": EXIT_SCHEMA.replace(".v1", "-result.v1"),
            "status": "complete" if error is None and terminal.safe else "failed",
            "model_queries": 0,
            "extra_payment": 0,
            "outcome": outcome,
        }
        _record(output / "result.json", result)
    if error is not None and not isinstance(error, Exception):
        raise error
    return result


def verify_departure_parent(parent, outcome, payloads):
    """A failed/partial exit cannot masquerade as an ordinary collection parent."""
    try:
        result = json.loads(payloads["prior_result"])
        if (
            result["schema"] != EXIT_SCHEMA.replace(".v1", "-result.v1")
            or result["status"] != "complete"
            or result["outcome"] != outcome
            or outcome["verification"] != "paid_session_exited"
            or outcome["error_chain"]
            or outcome["learning_eligible"] is not False
            or any(
                type(row["model_queries"]) is not int or row["model_queries"] != 0
                for row in (parent, result, outcome)
            )
            or type(result["extra_payment"]) is not int
            or result["extra_payment"] != 0
        ):
            raise ValueError("unverified paid Safari departure")
        require_departure_facts(outcome["before"], outcome["after"])
        for key in ("actions", "frames"):
            before, after = outcome["before"][key], outcome["after"][key]
            cap = parent["provenance"]["maximum_" + key]
            if (
                any(type(value) is not int for value in (before, after, cap))
                or not 0 <= before <= after <= cap
            ):
                raise ValueError("paid Safari departure exceeds its bound")
    except (KeyError, TypeError) as error:
        raise ValueError("malformed paid Safari departure parent") from error
