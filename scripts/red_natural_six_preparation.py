"""Bounded natural party preparation, never a model or a memory intervention."""
from __future__ import annotations

from collections import Counter

from pokemon_red_completion.gen1_indoor_encounters import indoor_land_encounter_mask
from pokemon_red_completion.gen1_party_menu import swap_party_slots
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.surge import (
    DEFAULT_SURGE_TIMING,
    WILD_CAPTURE_THROWS_PER_ENCOUNTER,
    LiveWildCorridorSurveyExecutor,
)

BOOTS = (3700, 3900)
MAX_STEPS, MAX_ENCOUNTERS = 320, 12


def select_patrol(graph, encounter_grid, origin, blocked):
    """A reversible adjacent pair at the observed stance, never a fixed route."""
    if origin in blocked or not encounter_grid[origin[0]][origin[1]]:
        raise ValueError("preparation stance is not safe encounter ground")

    def plain(edge):
        return (edge.kind == "walk" and not edge.requirements
                and edge.required_mode in (None, "land") and edge.result_mode in (None, "land")
                and edge.transient is None)

    for edge in sorted(graph.neighbors(origin), key=lambda e: (e.target, e.action)):
        target = edge.target
        if (plain(edge) and target not in blocked
                and encounter_grid[target[0]][target[1]]
                and any(back.target == origin and plain(back) for back in graph.neighbors(target))):
            return edge.action
    raise ValueError("no safe reversible adjacent encounter patrol")


def verify_catch(before, after, caught):
    if (type(caught) is not bool or after.battle_state != 0
            or after.map_id != before.map_id
            or after.party_count != before.party_count + int(caught)
            or tuple(after.party_species_ids or ())[:before.party_count]
            != tuple(before.party_species_ids or ())
            or after.player_money != before.player_money):
        raise ValueError("natural catch changed protected party, map or cash")
    old, new = dict(before.bag_items or ()), dict(after.bag_items or ())
    ball = int(ItemId.POKE_BALL)
    spent = old.get(ball, 0) - new.get(ball, 0)
    if (not int(caught) <= spent <= WILD_CAPTURE_THROWS_PER_ENCOUNTER
            or any(old.get(k, 0) != new.get(k, 0) for k in old.keys() | new.keys() if k != ball)):
        raise ValueError("natural catch ball or other-item accounting differs")
    return spent


def fill_party(session, actions, reader, world, record):
    before = reader.read()
    if (before.battle_state != 0 or before.party_count != 2
            or not reader.read_input_readiness().ready):
        raise ValueError("natural preparation needs the earned two-member field boundary")
    origin = (before.player_y, before.player_x)
    map_id = before.map_id
    hazards = Gen1TrainerSightProjector(world.rom, reader, full_event_offsets=True)
    blocked = (world.object_blockers[map_id]
               | reader.read_current_object_coordinates()
               | frozenset(world.macro_graph.warp_locations.get(map_id, ()))
               | frozenset(h.at for h in hazards.observe_hazards(before)))
    direction = select_patrol(world.local_graphs[map_id],
                              indoor_land_encounter_mask(world.rom, world.terrain[map_id]),
                              origin, blocked)
    walker = LiveWildCorridorSurveyExecutor(
        session, actions, reader, DEFAULT_SURGE_TIMING, label="natural six-member preparation",
        forward_directions=(direction,), starting_endpoint="south", max_legs=MAX_STEPS + 2,
    )
    encounters = balls = 0
    for step in range(MAX_STEPS):
        raw = reader.read()
        if raw.party_count == 6:
            break
        if (raw.party_count is None or not raw.party_hp or min(raw.party_hp) <= 0
                or any(raw.party_status or ())
                or dict(raw.bag_items or ()).get(int(ItemId.POKE_BALL), 0) < 6 - raw.party_count
                or encounters >= MAX_ENCOUNTERS):
            raise ValueError("natural preparation exhausted viable party, balls or encounters")
        walker.seek_encounter()
        raw = reader.read()
        if raw.battle_state:
            if raw.battle_state != 1:
                raise ValueError("unexpected trainer during party preparation")
            encounters += 1
            caught = walker.capture_encounter(walker.encountered_species_ref())
            final = reader.read()
            spent = verify_catch(raw, final, caught)
            balls += spent
            record({"encounter": encounters, "step": step + 1, "caught": caught,
                    "balls_spent": spent, "total_balls_spent": balls,
                    "party_count": final.party_count, "party_hp": final.party_hp,
                    "party_levels": final.party_levels, "cash": final.player_money})
    else:
        raise ValueError("natural preparation search steps exhausted")
    walker.finish_at_starting_endpoint()
    final = reader.read()
    if (final.party_count != 6 or final.battle_state != 0
            or (final.player_y, final.player_x) != origin or final.map_id != map_id
            or not final.party_hp or min(final.party_hp) <= 0 or any(final.party_status or ())
            or not reader.read_input_readiness().ready):
        raise ValueError("natural preparation did not retain six living ready members")
    # Ordinary menu reordering creates a reserve-use question, not an artificial stat change.
    swapped = swap_party_slots(session, actions, reader, source_index=0, destination_index=5,
                               label="natural six-member late-slot preparation")
    if Counter(swapped.party_species_ids or ()) != Counter(final.party_species_ids or ()):
        raise ValueError("natural party reorder lost a member")
    return {"encounters": encounters, "balls_spent": balls, "party_count": 6,
            "party_levels": swapped.party_levels, "party_hp": swapped.party_hp,
            "party_moves": swapped.party_moves, "cash": swapped.player_money,
            "memory_writes": 0, "model_queries": 0, "ordinary_slot_swap": [1, 6]}
