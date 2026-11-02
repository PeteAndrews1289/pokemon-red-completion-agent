"""Safe-prefix navigation and one native scripted rival trigger, no combat."""

from dataclasses import dataclass, replace

from .actions import MacroAction, MacroActionKind
from .gen1_route22_script import route22_script_binding
from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .route_executor import DEFAULT_ROUTE_EXECUTION_LIMITS, TraversalHazard, execute_route
from .route_plan import RoutePlanningError
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class ScriptedRivalError(RuntimeError):
    """Retain the actual terminal; never repeat the trigger after this error."""


@dataclass(frozen=True)
class ScriptedApproach:
    prefix: tuple[int, int]
    edge: object
    steps: int


def plan_scripted_approaches(world, start, triggers):
    """Keep every trigger blocked during planning; quote one ordinary final edge."""
    if not start.ready or start.interruption is not None or start.mode != "land":
        return ()
    hazards = {h.at for h in start.hazards}
    if not set(triggers).issubset(hazards):
        raise ScriptedRivalError("all scripted triggers must remain blocked")
    found = []
    for prefix, edges in world.local_graphs[start.map_id].edges.items():
        if prefix in hazards or prefix in start.occupied:
            continue
        for edge in edges:
            delta = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}.get(
                edge.action
            )
            if (
                edge.target not in triggers
                or edge.target in start.occupied
                or edge.kind != "walk"
                or edge.action_kind != MacroActionKind.MOVE
                or edge.via
                or edge.transient is not None
                or delta is None
                or not edge.permits_mode(start.mode)
                or edge.next_mode(start.mode) != start.mode
                or not edge.requirements.issubset(start.capabilities)
                or edge.target != (prefix[0] + delta[0], prefix[1] + delta[1])
                or any(h.at == edge.target and h.kind != "scripted_rival" for h in start.hazards)
            ):
                continue
            try:
                plan = world.plan_feasible_to_map(start, start.map_id, goal_at=prefix)
            except RoutePlanningError:
                continue
            if not plan.segments:
                found.append(ScriptedApproach(prefix, edge, len(plan.steps)))
    return tuple(sorted(found, key=lambda p: (p.steps, p.prefix, p.edge.target)))


_PROTECTED = (
    "party_count",
    "party_species_ids",
    "party_levels",
    "party_hp",
    "party_moves",
    "party_pp",
    "party_status",
    "bag_items",
    "player_money",
    "badge_bits",
    "event_flags",
)


def await_scripted_rival(reader, actions, *, binding, before, approach, maximum_actions):
    """Only waits/script-owned dialogue. Never selects a battle action or retriggers."""
    if type(maximum_actions) is not int or not 0 <= maximum_actions <= 160:
        raise ValueError("scripted transition needs a remaining action bound")
    for used in range(maximum_actions + 1):
        raw = reader.read()
        if (
            raw.map_id != binding.map_id
            or any(getattr(raw, k) != getattr(before, k) for k in _PROTECTED)
            or (raw.player_y, raw.player_x) not in (approach.prefix, approach.edge.target)
        ):
            raise ScriptedRivalError("scripted entry changed protected state")
        phase = reader.read_route22_script()
        if raw.battle_state == 2:
            if phase != 5 or reader.read_active_trainer_identity() != binding.identity:
                raise ScriptedRivalError("wrong scripted battle identity")
            return {
                "trainer_identity": binding.identity,
                "transition_actions": used,
                "trigger_at": approach.edge.target,
                "combat_choices": 0,
            }
        if raw.battle_state != 0 or phase not in (0, 4, 5):
            raise ScriptedRivalError("unexpected scripted entry phase")
        pending = reader.read_pending_trainer_battle_identity()
        if pending is not None and pending != (binding.identity[0], binding.identity[2]):
            raise ScriptedRivalError("wrong pending scripted identity")
        if used == maximum_actions:
            break
        if reader.read_bottom_dialogue_box_visible():
            if phase != 4:
                raise ScriptedRivalError("dialogue is outside qualified rival phase")
            action = MacroAction(MacroActionKind.INTERACT)
        else:
            action = MacroAction(MacroActionKind.WAIT, repeat=12)
        actions.execute(action)
    raise ScriptedRivalError("scripted entry transition budget consumed")


def engage_scripted_rival(emulator, reader, actions, *, rom, binding, maximum_actions=160):
    if type(maximum_actions) is not int or not 1 <= maximum_actions <= 160:
        raise ValueError("scripted entry requires1..160 transition actions")
    before = reader.read()

    def require_binding():
        raw = reader.read()
        binding.require_available(raw)
        if (
            route22_script_binding(rom, reader.read_rival_starter()) != binding
            or raw.map_id != binding.map_id
            or raw.battle_state
            or reader.read_route22_script() != 0
            or reader.read_pending_trainer_battle_identity() is not None
            or not reader.read_input_readiness().ready
            or reader.read_bottom_dialogue_box_visible()
        ):
            raise ScriptedRivalError("stale scripted rival entry")

    require_binding()
    ordinary = Gen1TrainerSightProjector(rom, reader, full_event_offsets=True)

    class Hazards:
        def observe_hazards(self, raw):
            return ordinary.observe_hazards(raw) + tuple(
                TraversalHazard(at, "scripted_rival") for at in binding.triggers
            )

    observer = Gen1TraversalObserver(reader, Hazards(), cut_capabilities)
    base = StrategicScenarioRouteWorld.from_rom(rom)
    # Map-local only: never leave/re-enter to bypass a trigger or hazard.
    base = replace(base, macro_graph=replace(base.macro_graph, edges={}))
    world = base.with_current_blocks(reader.read_current_map_blocks())
    start = observer.observe()
    options = plan_scripted_approaches(world, start, binding.triggers)
    if not options:
        raise ScriptedRivalError("no protected prefix reaches scripted rival")
    approach = options[0]
    plan = world.plan_feasible_to_map(start, start.map_id, goal_at=approach.prefix)
    execute_route(
        plan,
        actions,
        observer,
        interruption_handler=Gen1WildFleeHandler(
            actions,
            reader,
            maximum_flees=4,
            stabilization_frames=120,
            route_name="scripted rival protected approach",
        ),
        replanner=lambda request: base.with_current_blocks(
            reader.read_current_map_blocks()
        ).replanner()(request),
        limits=replace(DEFAULT_ROUTE_EXECUTION_LIMITS, max_readiness_waits=100),
    )
    require_binding()
    live = reader.read()
    candidates = plan_scripted_approaches(
        base.with_current_blocks(reader.read_current_map_blocks()),
        observer.observe(),
        binding.triggers,
    )
    if (
        (live.player_y, live.player_x) != approach.prefix
        or any(getattr(live, k) != getattr(before, k) for k in _PROTECTED)
        or not any(p.prefix == approach.prefix and p.edge == approach.edge for p in candidates)
    ):
        raise ScriptedRivalError("scripted approach changed before trigger")
    actions.execute(approach.edge.macro_action)
    result = await_scripted_rival(
        reader,
        actions,
        binding=binding,
        before=before,
        approach=approach,
        maximum_actions=maximum_actions - 1,
    )
    return dict(
        result, transition_actions=result["transition_actions"] + 1, prefix_at=approach.prefix
    )
