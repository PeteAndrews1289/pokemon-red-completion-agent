"""ROM-free semantic audit of an unspent attack yielding a trainer prompt.

Native logs use one-based decision identifiers. Sequence adjacency, unchanged
resources and the recorded semantic guard establish handoff, not a magic index.
This does not authenticate files or qualify an entire native test matrix.
"""
from collections.abc import Mapping, Sequence


class PromptHandoffAuditError(ValueError):
    """Saved evidence does not prove the required actor-owned handoff."""


def audit_first_prompt_handoff(
    episode: Mapping[str, object], guard: Mapping[str, object]
) -> dict[str, object]:
    decisions = episode.get("decisions")
    if not isinstance(decisions, Sequence) or len(decisions) < 2:
        raise PromptHandoffAuditError("handoff needs two adjacent completed decisions")
    for expected, decision in enumerate(decisions, 1):
        index = decision.get("decision_index")
        if type(index) is not int or index != expected:
            raise PromptHandoffAuditError("decision identifiers must be contiguous and one-based")
    attack, prompt = decisions[:2]
    before, after = attack.get("state_before"), attack.get("state_after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise PromptHandoffAuditError("attack resources missing")
    pp = before.get("active_pp")
    slot = before.get("active_party_slot")
    if (
        attack.get("kind") != "attack"
        or attack.get("outcome", {}).get("move_executed") is not False
        or not isinstance(pp, list) or not pp
        or any(type(value) is not int or value < 0 for value in pp)
        or after.get("active_pp") != pp
        or type(slot) is not int or slot < 1
        or after.get("active_party_slot") != slot
        or before.get("opponent_party_position") == after.get("opponent_party_position")
    ):
        raise PromptHandoffAuditError("unspent same-actor opponent replacement not proved")
    status = after.get("party_status")
    if (
        not isinstance(status, list) or len(status) < slot
        or type(status[slot - 1]) is not int or not status[slot - 1] & 7
        or guard.get("caller") not in ("_recover_sleep_transition", "_execute_policy_turn")
        or guard.get("resources") != after
        or guard.get("pp") != pp
        or type(guard.get("sleep")) is not int
        or guard["sleep"] != status[slot - 1] & 7
        or type(guard.get("controller_inputs")) is not int
        or guard["controller_inputs"] != 0
    ):
        raise PromptHandoffAuditError("sleeping zero-input semantic guard evidence differs")
    if (
        prompt.get("kind") != "switch_prompt"
        or prompt.get("state_before") != after
        or not isinstance(prompt.get("model_diagnostics"), Mapping)
        or "forced_first_choice_ref" in prompt["model_diagnostics"]
    ):
        raise PromptHandoffAuditError("next completed decision is not a model-owned prompt")
    chosen = prompt.get("party_slot")
    if chosen is not None and (
        type(chosen) is not int or chosen not in prompt.get("legal_party_slots", [])
    ):
        raise PromptHandoffAuditError("model switch target is not legal")
    resolved = prompt.get("state_after")
    if (
        not isinstance(resolved, Mapping)
        or resolved.get("active_party_slot") != (slot if chosen is None else chosen)
        or resolved.get("party_hp") != after.get("party_hp")
        or resolved.get("party_pp") != after.get("party_pp")
        or resolved.get("opponent_party_position") != after.get("opponent_party_position")
        or resolved.get("opponent_hp") != after.get("opponent_hp")
    ):
        raise PromptHandoffAuditError("prompt resolution changed unapproved resources or target")
    return {
        "passed": True,
        "attack_decision": attack["decision_index"],
        "prompt_decision": prompt["decision_index"],
        "selected_party_slot": chosen,
        "guard_caller": guard["caller"],
        "sleep_count": guard["sleep"],
        "new_controller_inputs": 0,
        "scope": "one recorded boundary; not whole-matrix or battle-quality qualification",
    }
