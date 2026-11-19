"""Opt-in paid-search recurrence; no score, mask, target or success inference."""
from types import SimpleNamespace
from dataclasses import replace

from .red_integrated_play import PAID_SEARCH, objective_key, search_objective_key, ordinary_paid_search_setback
from .red_movement_recurrence import movement_boundary


def cashless_progress(facts):
    cash = facts.get("cash")
    if type(cash) is not int or not 0 <= cash <= 999999:
        return None
    boundary = movement_boundary(dict(facts, cash=0))
    return None if boundary is None else boundary[1]


def search_contexts(options, facts):
    return [dict(binding_ref=b.binding_ref,
                 source_ref=b.search_memory_source if b.tracks_search_effort
                 and b.search_memory_source.startswith(PAID_SEARCH) else None,
                 objective_sha256=(b.search_objective_sha256 if b.search_objective_sha256 is not None else objective_key(facts))
                 if b.tracks_search_effort and b.search_memory_source.startswith(PAID_SEARCH)
                 else None)
            for b in options.bindings]


def witnesses(contexts, memory, facts):
    progress = cashless_progress(facts)
    result = []
    for c in contexts:
        if set(c) != {"binding_ref", "source_ref", "objective_sha256"}:
            raise ValueError("costly search context fields differ")
        if c["source_ref"] is None:
            if c["objective_sha256"] is not None:
                raise ValueError("costly search absent source has target")
            result.append(False)
        else:
            if type(c["source_ref"]) is not str or not c["source_ref"].startswith(PAID_SEARCH):
                raise ValueError("costly search source differs")
            # Validate keys even when physical facts are unknown.
            memory.lookup(c["source_ref"], c["objective_sha256"])
            result.append(None if progress is None else memory.costly_search_seen(
                c["source_ref"], c["objective_sha256"], progress, facts["cash"]))
    return tuple(result)


def record_failure(memory, context, before, terminal, report, verification, error):
    if context["source_ref"] is None:
        return False
    binding = SimpleNamespace(search_memory_source=context["source_ref"])
    first, last = cashless_progress(before.facts), cashless_progress(terminal.facts)
    if first is None or first != last:
        return False
    before_proof, terminal_proof = paid_search_snapshot(before), paid_search_snapshot(terminal)
    if before_proof is None or terminal_proof is None or not ordinary_paid_search_setback(
            binding, before_proof, terminal_proof, report, verification, error):
        return False
    if first is None or first != last:
        return False
    memory.record_costly_search_failure(context["source_ref"], context["objective_sha256"],
                                       last, terminal.facts["cash"])
    return True


def paid_search_snapshot(snapshot):
    """Map known current native facts into the existing strict paid-search proof.

    The live Safari session must be read by the native adapter. Do not infer an
    inactive session from a location, a departure claim or absent old fields.
    No missing observation is filled with zero. Old integrated snapshots retain
    their unchanged certificate and contract.
    """
    facts = snapshot.facts
    old = ("specimens", "party_training", "party_hp", "party_pp", "party_status", "bag_items", "session")
    if all(k in facts for k in old):
        return snapshot
    if cashless_progress(facts) is None:
        return None
    session = facts.get("costly_search_session")
    if (not isinstance(session, dict)
            or any(type(session.get(k)) is not bool for k in ("in_safari_zone", "safari_game_over"))
            or any(type(v) is not int or v <= 0 for v in facts["specimen_counts"].values())):
        return None
    party = facts["player_lesson"]["party"]
    projected = dict(facts,
        specimens=sum(facts["specimen_counts"].values()),
        party_training=[[m["species_id"], m["level"], m["experience"]] for m in party],
        party_hp=[m["hp"] for m in party], party_status=[m["status"] for m in party],
        party_pp=[[pair[1] for pair in m["moves"]] for m in party],
        bag_items=facts["diagnostics"]["bag_items"], session=session)
    return replace(snapshot, facts=projected)
