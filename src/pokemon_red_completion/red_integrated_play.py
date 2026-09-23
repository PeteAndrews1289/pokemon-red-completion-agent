"""Narrow, opt-in contract for continuous paid-search / native-exchange play.

This is a referee, never a destination selector. Unknown mechanics stop rather
than disappearing from the menu. Failed searches remain failed examples.
"""

from collections.abc import Mapping
from dataclasses import replace

from .goal_manager import GoalKind
from .goal_search_memory import GoalSearchMemory
from .provenance import canonical_sha256

PAID_SEARCH = "pokemon.red:paid-safari:"
NATIVE_EXCHANGE = "pokemon.red:npc-trade:"


def spending_bound(binding):
    """Known maximum cash debit, not an estimated reward or policy mask."""
    if binding.kind is not GoalKind.ACQUIRE_SPECIES:
        return None
    source = binding.search_memory_source
    if source.startswith(PAID_SEARCH):
        return 500
    if source.startswith(NATIVE_EXCHANGE):
        return 0
    return None


def objective_key(facts):
    """Legacy fallback for bindings without observed source-specific targets."""
    owned = facts.get("owned_species")
    if not isinstance(owned, (list, tuple)) or not owned or any(
        not isinstance(species, str) for species in owned
    ):
        raise ValueError("integrated play requires observed registration context")
    return canonical_sha256({"registered": sorted(owned)})


def search_objective_key(binding, fallback: str) -> str:
    """Adapter-private target context; never a policy feature or availability rule."""
    return binding.search_objective_sha256 or fallback


def menu_with_search_history(options, memory: GoalSearchMemory, objective: str):
    """Only measured semantic counts reach the existing feature-v4 ranker."""
    candidates = tuple(
        replace(candidate, search_history=memory.lookup(
            binding.search_memory_source, search_objective_key(binding, objective)))
        if binding.kind is GoalKind.ACQUIRE_SPECIES else candidate
        for candidate, binding in zip(options.menu.candidates, options.bindings, strict=True)
    )
    return replace(options, menu=replace(options.menu, candidates=candidates))


def measured_cost(before, after, report):
    if report is None:
        return None
    names = ("actions", "completed_actions", "frames", "cash")
    if any(type(facts.get(name)) is not int or facts[name] < 0
           for facts in (before, after) for name in names):
        return None
    actions = after["actions"] - before["actions"]
    frames = after["frames"] - before["frames"]
    if (actions <= 0 or frames <= 0
        or actions != after["completed_actions"] - before["completed_actions"]
        or actions != report.actions_executed or frames != report.frames_executed):
        return None
    return {"actions": actions, "frames": frames, "cash_spent": before["cash"] - after["cash"]}


def ordinary_paid_search_setback(binding, before, terminal, report, verification, error):
    """Fail closed unless the entire unsuccessful paid visit settled normally."""
    if (error is not None or verification is None or report is None
        or not terminal.safe or not before.safe
        or not binding.search_memory_source.startswith(PAID_SEARCH)
        or verification.status.value != "failed"
        or verification.failure_reason is None
        or verification.failure_reason.value != "search_exhausted"):
        return False
    cost = measured_cost(before.facts, terminal.facts, report)
    if cost is None or cost["cash_spent"] != 500:
        return False
    evidence = report.evidence
    admission = evidence.get("admission")
    departure = evidence.get("paid_session_departure")
    if (not isinstance(admission, Mapping) or admission.get("status") != "ok"
        or admission.get("single_admission") is not True
        or not isinstance(departure, Mapping) or departure.get("passed") is not True
        or type(evidence.get("captures")) is not int or evidence["captures"] != 0
        or evidence.get("search_safety_stopped") is not False
        or not (evidence.get("search_exhausted") is True
                or evidence.get("search_resource_stopped") is True)):
        return False
    unchanged = ("owned_species", "specimen_counts", "specimens", "party_training",
                 "party_hp", "party_pp", "party_status", "bag_items")
    if any(name not in before.facts or name not in terminal.facts
           or before.facts[name] != terminal.facts[name] for name in unchanged):
        return False
    for facts in (before.facts, terminal.facts):
        session = facts.get("session")
        if (facts.get("battle_state") != 0 or facts.get("input_ready") is not True
            or facts.get("buttons_released") is not True
            or not isinstance(session, Mapping)
            or session.get("in_safari_zone") is not False
            or session.get("safari_game_over") is not False):
            return False
    return True
