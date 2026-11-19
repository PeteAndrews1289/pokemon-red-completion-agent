"""Observed endpoint recurrence for marginal movement utility, never action choice.

Private positions and native event facts authenticate memory. Only a boolean
revisit observation enters the public menu. Unknown observations retain value.
"""
import re
from collections.abc import Mapping
from dataclasses import replace

from .player_option_story_unit import OptionStoryUnit
from .provenance import canonical_sha256


def movement_boundary(facts):
    """Return private endpoint and progress keys, excluding clock/RNG/position.

    The observed position is hashed separately. Costs, budgets and counters must
    not make a repeated doorway appear novel; actual resources/events must.
    """
    diagnostic = facts.get("diagnostics")
    lesson = facts.get("player_lesson")
    events = facts.get("movement_event_flags")
    if (not isinstance(diagnostic, Mapping) or not isinstance(lesson, Mapping)
            or type(events) is not str or not events or len(events) % 2
            or re.fullmatch(r"[0-9a-f]+", events) is None):
        return None
    position = [diagnostic.get(k) for k in ("map_id", "player_y", "player_x")]
    if any(type(v) is not int or v < 0 for v in position):
        return None
    required = ("cash", "owned_species", "specimen_counts", "completed_objectives")
    if (any(k not in facts for k in required) or "bag_items" not in diagnostic
            or "badge_bits" not in diagnostic or not lesson.get("party")):
        return None
    # Unknown physical facts cannot certify that a destination is unchanged.
    coins = facts.get("movement_coins")
    party = lesson["party"]
    bag = diagnostic["bag_items"]
    if (type(facts["cash"]) is not int or facts["cash"] < 0
            or type(coins) is not int or not 0 <= coins <= 9999
            or type(diagnostic["badge_bits"]) is not int
            or not isinstance(bag, (list, tuple))
            or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                   or any(type(v) is not int for v in pair) for pair in bag)
            or not isinstance(party, (list, tuple))
            or any(not isinstance(member, Mapping)
                   or any(type(member.get(k)) is not int for k in
                          ("species_id", "level", "experience", "hp", "max_hp"))
                   or type(member.get("status")) is not str
                   or type(member.get("specimen_ref")) is not str
                   or not isinstance(member.get("moves"), (list, tuple))
                   or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                          or any(type(v) is not int for v in pair)
                          for pair in member["moves"]) for member in party)
            or any(not isinstance(facts[k], (list, tuple))
                   or any(type(v) is not str for v in facts[k])
                   for k in ("owned_species", "completed_objectives"))
            or not isinstance(facts["specimen_counts"], Mapping)
            or any(type(k) is not str or type(v) is not int
                   for k, v in facts["specimen_counts"].items())):
        return None
    progress = {k: facts[k] for k in required}
    progress["coins"] = coins
    progress.update(events=events, bag=diagnostic["bag_items"],
                    badges=diagnostic["badge_bits"], party=lesson["party"])
    return (canonical_sha256(dict(map=position[0], at=position[1:])),
            canonical_sha256(progress))


def observe_movement_boundary(memory, facts):
    boundary = movement_boundary(facts)
    if boundary is not None:
        memory.observe_movement_endpoint(*boundary)
    return boundary


def record_movement_return(memory, before_facts, after_facts):
    """Bound repeated executed transit without changing a menu or choosing a goal.

    Novel endpoints and any observed resource/event/party change do not count.
    Two equivalent unchanged returns stop the finite actor at its settled save.
    The counter is checkpointed, so ordinary chunk renewal cannot erase it.
    """
    before, after = movement_boundary(before_facts), movement_boundary(after_facts)
    if (before is None or after is None or before[1] != after[1]
            or not memory.movement_endpoint_seen(*after)):
        return None
    count = memory.record_movement_return(before[0], after[0], after[1])
    return dict(source_endpoint_sha256=before[0], endpoint_sha256=after[0],
                progress_sha256=after[1], equivalent_unchanged_returns=count,
                stop_required=count >= 2, threshold=2,
                policy="two-equivalent-unchanged-movement-returns-v1",
                goal_selected_or_masked=False)


def menu_with_movement_history(options, memory, facts):
    """Record actual current location, then describe quoted endpoints action-free."""
    boundary = observe_movement_boundary(memory, facts)
    if boundary is None:
        return options
    _, progress = boundary
    candidates = tuple(
        replace(candidate, movement_revisit=memory.movement_endpoint_seen(
            binding.movement_endpoint_sha256, progress))
        if (binding.movement_endpoint_sha256 is not None
            and binding.story_unit == OptionStoryUnit("movement", True))
        else candidate
        for candidate, binding in zip(options.menu.candidates, options.bindings, strict=True)
    )
    return replace(options, menu=replace(options.menu, candidates=candidates))
