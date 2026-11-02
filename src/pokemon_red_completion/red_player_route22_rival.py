"""The decoded Route22 gate uses the existing selected-rival battle lifecycle."""

from dataclasses import replace

from .gen1_route22_script import first_route22_script_binding, route22_script_binding
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .observation import EventFlag, MapId, event_flag_is_set
from .red_player_cerulean_rival import scripted_rival_binding
from .red_player_field_goals import _field_ready
from .red_scripted_rival import engage_scripted_rival, plan_scripted_approaches
from .red_story_battle import StoryTrainerContract
from .route_executor import TraversalHazard

OBJECTIVE = "cross_victory_road"


def retained_first_route22_contract(rom, reader, *, objective_id):
    """Bind only the already-triggered first rival, with no chapter completion.

    The objective is an available accounting context, not a selected destination.
    This first encounter never borrows the second rival's eight-badge authority.
    """
    raw = reader.read()
    if raw.map_id != 33 or raw.battle_state not in (0, 2):
        return None
    if raw.event_flags is None:
        raise ValueError("first Route22 rival events are unavailable")
    if not event_flag_is_set(raw.event_flags, 0x520) or not event_flag_is_set(
        raw.event_flags, 0x527
    ):
        return None
    phase = reader.read_route22_script()
    if raw.battle_state == 0 and phase not in (1, 2):
        return None
    binding = first_route22_script_binding(rom, reader.read_rival_starter())
    binding.require_available(raw)
    if (raw.player_y, raw.player_x) not in binding.triggers:
        raise ValueError("first Route22 rival trigger differs")
    if raw.battle_state == 2:
        if phase != 2 or reader.read_active_trainer_identity() != binding.identity:
            raise ValueError("first Route22 rival battle identity differs")
    else:
        pending = reader.read_pending_trainer_battle_identity()
        if reader.read_input_readiness().ready or (
            pending is not None and pending != (binding.identity[0], binding.identity[2])
        ):
            raise ValueError("first Route22 rival control or pending identity differs")
    quote = trainer_party_quote(rom, binding.identity[0], binding.identity[2])
    if not quote.party or quote.party[-1].internal_species != reader.read_rival_starter():
        raise ValueError("first Route22 rival party differs from the native starter")
    return StoryTrainerContract(
        objective_id, "retained-route22-first-rival", binding.map_id, binding.identity,
        binding.defeated_event, quote.expected_victory_money,
    )


def route22_rival_contract(rom, reader):
    decoded = route22_script_binding(rom, reader.read_rival_starter())
    decoded.require_available(reader.read())
    quote = trainer_party_quote(rom, decoded.identity[0], decoded.identity[2])
    return StoryTrainerContract(
        OBJECTIVE,
        "route22-rival-gate",
        decoded.map_id,
        decoded.identity,
        decoded.defeated_event,
        quote.expected_victory_money,
    )


def retained_second_route22_contract(rom, reader):
    """Recognize an already-triggered late rival, without a new approach."""
    raw = reader.read()
    if (
        raw.map_id != int(MapId.ROUTE_22)
        or raw.battle_state != 0
        or raw.badge_bits != 255
        or reader.read_route22_script() not in (4, 5)
    ):
        return None
    decoded = route22_script_binding(rom, reader.read_rival_starter())
    decoded.require_available(raw)
    if (raw.player_y, raw.player_x) not in decoded.triggers:
        raise ValueError("second Route22 rival trigger differs")
    pending = reader.read_pending_trainer_battle_identity()
    if reader.read_input_readiness().ready or (
        pending is not None and pending != (decoded.identity[0], decoded.identity[2])
    ):
        raise ValueError("second Route22 rival control or pending identity differs")
    if reader.read_route22_script() == 4 and not reader.read_bottom_dialogue_box_visible():
        raise ValueError("second Route22 rival introduction text is absent")
    return route22_rival_contract(rom, reader)


def route22_preparation_contract(rom, reader, *, available_objectives):
    """Preview only a relevant late-game rival, then use the strict contract.

    Early Route22 travel and an already consumed rival need no such forecast.
    Eligible but ambiguous native script flags still raise; this is not a
    replacement for the decoded validator or an instruction to fight/train.
    """
    raw = reader.read()
    if (
        raw.map_id != int(MapId.ROUTE_22)
        or raw.badge_bits != 255
        or OBJECTIVE not in available_objectives
        or event_flag_is_set(raw.event_flags, EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE)
    ):
        return None
    return route22_rival_contract(rom, reader)


def route22_rival_binding(runtime, actions, *, route, battler):
    if not _field_ready(runtime) or runtime.reader.read().map_id != int(MapId.ROUTE_22):
        return None
    decoded = route22_script_binding(route.rom, runtime.reader.read_rival_starter())
    raw = runtime.reader.read()
    if event_flag_is_set(raw.event_flags, decoded.defeated_event):
        return None
    decoded.require_available(raw)
    ordinary = Gen1TrainerSightProjector(route.rom, runtime.reader, full_event_offsets=True)

    class Hazards:
        def observe_hazards(self, observed):
            return ordinary.observe_hazards(observed) + tuple(
                TraversalHazard(at, "scripted_rival") for at in decoded.triggers
            )

    hazards = Hazards()
    start = Gen1TraversalObserver(runtime.reader, hazards, cut_capabilities).observe()
    approaches = plan_scripted_approaches(route.route_world, start, decoded.triggers)
    if not approaches:
        return None
    binding = scripted_rival_binding(
        runtime,
        actions,
        route=route,
        battler=battler,
        objective_id=OBJECTIVE,
        map_id=decoded.map_id,
        contract_factory=route22_rival_contract,
        already_defeated=lambda: event_flag_is_set(
            runtime.reader.read().event_flags, decoded.defeated_event
        ),
        entries=tuple((p.prefix, p.edge.action) for p in approaches),
        scripted_entry=lambda: engage_scripted_rival(
            runtime.emulator, runtime.reader, actions, rom=route.rom, binding=decoded
        ),
        hazard_projector=hazards,
    )
    return None if binding is None else replace(binding, story_objective_ref=OBJECTIVE)
