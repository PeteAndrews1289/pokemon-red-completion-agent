"""One-based native records, rather than a zero-based hardcoded prompt index."""
from copy import deepcopy

import pytest
from audit_red_trainer_prompt_handoff import PromptHandoffAuditError, audit_first_prompt_handoff


def evidence():
    before = {
        "active_pp": [15, 5, 10, 0], "active_party_slot": 1,
        "opponent_party_position": 0, "opponent_hp": 1,
        "party_status": [2, 0], "party_hp": [96, 80], "party_pp": [[15, 5, 10, 0], [20, 0, 0, 0]],
    }
    after = {**deepcopy(before), "opponent_party_position": 1, "opponent_hp": 107,
             "party_status": [1, 0], "party_hp": [75, 80]}
    attack = {"decision_index": 1, "kind": "attack", "outcome": {"move_executed": False},
              "state_before": before, "state_after": after}
    prompt = {"decision_index": 2, "kind": "switch_prompt", "party_slot": None,
              "legal_party_slots": [2], "model_diagnostics": {"policy": "frozen"},
              "state_before": deepcopy(after), "state_after": deepcopy(after)}
    guard = {"caller": "_recover_sleep_transition", "resources": deepcopy(after),
             "pp": [15, 5, 10, 0], "sleep": 1, "controller_inputs": 0}
    return {"decisions": [attack, prompt]}, guard


@pytest.mark.parametrize("chosen", [None, 2])
def test_next_one_based_decision_proves_decline_or_selected_switch(chosen):
    episode, guard = evidence()
    episode["decisions"][1]["party_slot"] = chosen
    episode["decisions"][1]["state_after"]["active_party_slot"] = chosen or 1
    result = audit_first_prompt_handoff(episode, guard)
    assert result["passed"] and result["attack_decision"] == 1 and result["prompt_decision"] == 2


@pytest.mark.parametrize("indices", [(0, 1), (1, 1), (1, 3), (True, 2)])
def test_bad_index_sequence_rejected(indices):
    episode, guard = evidence()
    for decision, index in zip(episode["decisions"], indices, strict=True):
        decision["decision_index"] = index
    with pytest.raises(PromptHandoffAuditError):
        audit_first_prompt_handoff(episode, guard)


@pytest.mark.parametrize("field,value", [
    ("kind", "voluntary_switch"), ("party_slot", 3), ("party_slot", True),
    ("model_diagnostics", {"forced_first_choice_ref": "pokemon.core:battle:decline-switch"}),
])
def test_prompt_must_be_model_owned_and_legal(field, value):
    episode, guard = evidence()
    episode["decisions"][1][field] = value
    with pytest.raises(PromptHandoffAuditError):
        audit_first_prompt_handoff(episode, guard)


@pytest.mark.parametrize("mutation", [
    "spent", "pp", "awake", "guard_input", "guard_sleep", "state_gap",
    "resolved_hp", "resolved_pp", "resolved_slot", "missing_prompt",
])
def test_semantic_and_resource_proofs_cannot_be_bypassed(mutation):
    episode, guard = evidence()
    attack, prompt = episode["decisions"]
    if mutation == "spent":
        attack["outcome"]["move_executed"] = True
    elif mutation == "pp":
        attack["state_after"]["active_pp"][0] -= 1
    elif mutation == "awake":
        attack["state_after"]["party_status"][0] = 0
    elif mutation == "guard_input":
        guard["controller_inputs"] = 1
    elif mutation == "guard_sleep":
        guard["sleep"] = 2
    elif mutation == "state_gap":
        prompt["state_before"]["opponent_hp"] -= 1
    elif mutation == "resolved_hp":
        prompt["state_after"]["party_hp"][0] -= 1
    elif mutation == "resolved_pp":
        prompt["state_after"]["party_pp"][0][0] -= 1
    elif mutation == "resolved_slot":
        prompt["state_after"]["active_party_slot"] = 2
    else:
        episode["decisions"].pop()
    with pytest.raises(PromptHandoffAuditError):
        audit_first_prompt_handoff(episode, guard)
