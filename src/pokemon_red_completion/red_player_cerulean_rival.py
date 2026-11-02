"""One selected rival gate, not the fixed-order Cascade chapter.

The cartridge party matching the persistent rival starter is quoted before
input. Routing reaches the south approach; the native script starts combat.
Every combat decision belongs to the qualified frozen battler.
"""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import (
    CERULEAN_RIVAL_TRIGGER_XS,
    CERULEAN_RIVAL_TRIGGER_Y,
    EventFlag,
    MapId,
    event_flag_is_set,
)
from .red_player_cash_exposure import (
    certified_cash_safe_transition,
    single_blackout_cash_bound,
)
from .red_player_field_goals import _field_ready
from .red_scoped_training_battlers import resolve_story_battler
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError


def cerulean_rival_contract(rom, reader):
    verify_rom_bytes(rom)
    raw = reader.read()
    event = int(EventFlag.BEAT_CERULEAN_RIVAL)
    if raw.event_flags is None or event_flag_is_set(raw.event_flags, event):
        raise ValueError("Cerulean rival is consumed or unreadable")
    objects = [o for o in map_object_events(rom, {int(MapId.CERULEAN_CITY)}) if o.object_index == 1]
    if len(objects) != 1 or (objects[0].sprite_id, objects[0].movement) != (2, 255):
        raise ValueError("Cerulean rival cartridge object differs")
    starter = reader.read_rival_starter()
    matches = [
        q
        for n in (7, 8, 9)
        if (q := trainer_party_quote(rom, 225, n)).party and q.party[-1].internal_species == starter
    ]
    if len(matches) != 1:
        raise ValueError("Cerulean rival party must match the observed starter")
    quote = matches[0]
    return StoryTrainerContract(
        "help_bill",
        "cerulean-rival-gate",
        int(MapId.CERULEAN_CITY),
        (225, 25, quote.trainer_set),
        event,
        quote.expected_victory_money,
    )


def cerulean_rival_binding(runtime, actions, *, route, battler):
    return scripted_rival_binding(
        runtime,
        actions,
        route=route,
        battler=battler,
        objective_id="help_bill",
        map_id=int(MapId.CERULEAN_CITY),
        contract_factory=cerulean_rival_contract,
        already_defeated=lambda: event_flag_is_set(
            runtime.reader.read().event_flags, int(EventFlag.BEAT_CERULEAN_RIVAL)
        ),
        entries=tuple(
            ((CERULEAN_RIVAL_TRIGGER_Y + 1, x), "up") for x in sorted(CERULEAN_RIVAL_TRIGGER_XS)
        ),
    )


def scripted_rival_binding(
    runtime,
    actions,
    *,
    route,
    battler,
    objective_id,
    map_id,
    contract_factory,
    already_defeated,
    entries,
    scripted_entry=None,
    hazard_projector=None,
):
    """Reuse the owned battle lifecycle at a declared native coordinate trigger."""
    if scripted_entry is not None and not callable(scripted_entry):
        raise TypeError("scripted rival entry must be callable")
    if not _field_ready(runtime):
        return None
    before = runtime.adapter.observe()
    raw = before.raw
    if (
        raw.map_id != map_id
        or already_defeated()
        or objective_id
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
        or not raw.party_hp
        or not any(raw.party_hp)
    ):
        return None
    contract = contract_factory(route.rom, runtime.reader)
    start = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=hazard_projector
        or Gen1TrainerSightProjector(route.rom, runtime.reader, full_event_offsets=True),
    ).observe()
    plans = []
    for at, direction in entries:
        try:
            plan = route.route_world.plan_feasible_to_map(start, contract.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        plans.append((plan, direction))
    if not plans:
        return None
    plan, direction = min(plans, key=lambda p: p[0].cost)
    cash_route = certified_cash_safe_transition(route, raw, plan)
    source = runtime.emulator.save_state_bytes()
    actor = resolve_story_battler(battler, contract)
    controller = FrozenStoryBattleController(actor, (contract,), evolution_rom=route.rom)
    used, terminal, result = False, None, None

    def execute():
        nonlocal used, terminal, result
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("rival gate is stale or consumed")
        if resolve_story_battler(battler, contract) is not actor:
            raise ValueError("rival actor changed before execution")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        if contract_factory(route.rom, runtime.reader) != contract:
            raise ValueError("rival entry contract changed")
        if scripted_entry is not None:
            # The revision-bound entry owns its safe-prefix route and one
            # script trigger. It may not choose any combat action.
            scripted_entry()
        else:
            replace(
                cash_route or route,
                destination_map=contract.map_id,
                destination_at=plan.terminal_at,
            )(actions, runtime.reader, runtime.emulator)
            at = runtime.reader.read()
            if (
                at.map_id != contract.map_id
                or (at.player_y, at.player_x) != plan.terminal_at
                or contract_factory(route.rom, runtime.reader) != contract
            ):
                raise ValueError("rival trigger approach changed")
            actions.execute(MacroAction(MacroActionKind.MOVE, direction))
        for _ in range(48):
            current = runtime.reader.read()
            if current.battle_state == 2:
                if runtime.reader.read_active_trainer_identity() != contract.trainer_identity:
                    raise ValueError("native rival battle identity differs")
                break
            if current.battle_state or current.map_id != contract.map_id:
                raise ValueError("unexpected rival introduction")
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=144))
            if runtime.reader.read().battle_state == 0:
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
        else:
            raise RuntimeError("rival introduction exceeded bound")
        result = controller.run(
            runtime.reader,
            actions,
            objective_id=contract.objective_id,
            battle_plan_id=contract.battle_plan_id,
            expected_map=contract.map_id,
        )
        if (
            result.outcome not in {"won", "lost"}
            or not result.field_ready
            or not _field_ready(runtime)
        ):
            raise RuntimeError("rival battle did not settle")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective=objective_id,
                objective_completed=False,
                battle=result.public_dict(),
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
                support="cartridge_rival_gate_and_dialogue",
                automatic_preparation=False,
            ),
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if result.outcome == "lost":
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        if not already_defeated():
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:rival-gate:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.2 + plan.cost / 3000),
        0.4,
        execute,
        verify,
        maximum_cash_debit=single_blackout_cash_bound(raw, cash_route),
    )
