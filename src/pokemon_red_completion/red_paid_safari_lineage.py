"""Admit retained, audited paid-search failures without erasing their costs.

This is a legacy receipt adapter, not a successful acquisition or a replay permit.
The ordinary parent must still pass the runner's reserve/result-chain validation.
"""

from __future__ import annotations

import hashlib
import json

from .red_safari_lineage import FACT_KEYS

PAID_RECORDS = ("paid_safari_input", "paid_safari_plan", "paid_safari_result", "paid_safari_audit")


def _require(condition, message):
    if not condition:
        raise ValueError("paid Safari lineage: " + message)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def verify_paid_safari_lineage(plan, payloads):
    """Return authenticated current facts; reject partial or assisted chains."""
    try:
        return _verify(plan, payloads)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("paid Safari lineage: incomplete or malformed receipt") from error


def _verify(plan, payloads):
    _require(all(key in payloads for key in PAID_RECORDS), "missing receipt")
    _require("assisted_training_money" not in plan, "assistance prohibited")
    docs = {
        key: json.loads(payloads[key])
        for key in (
            *PAID_RECORDS,
            "prior_plan",
            "prior_result",
            "prior_outcome",
            "prior_execution_started",
        )
    }
    def digest(key):
        return hashlib.sha256(payloads[key]).hexdigest()
    parent, outcome = docs["prior_plan"], docs["prior_outcome"]
    started, original = docs["prior_execution_started"], docs["paid_safari_input"]
    paid, result, audit = (docs[key] for key in PAID_RECORDS[1:])
    for source, target in (
        ("parent_plan", "prior_plan"),
        ("parent_result", "prior_result"),
        ("outcome", "prior_outcome"),
        ("execution", "prior_execution_started"),
    ):
        _require(original[source]["sha256"] == digest(target), "original input mismatch")
    _require(
        parent["schema"] == "pokemon.red.autonomous-option-run.v1"
        and parent["model_sha256"] == plan["model_sha256"] == outcome["choice"]["model_sha256"]
        and not parent["provenance"].get("training_assistance")
        and original["rom"]["sha256"] == plan["rom"]["sha256"]
        and original["state"]["sha256"] == outcome["terminal_state_sha256"]
        and original["before"]["sha256"] == outcome["before_state_sha256"]
        and original["source_commit"] == paid["source_commit"],
        "origin mismatch",
    )
    _require(
        started["state_sha256"] == outcome["before_state_sha256"]
        and started["selected_kind"] == outcome["selected_kind"] == "acquire_species"
        and started["menu_sha256"] == outcome["choice"]["menu_sha256"]
        and outcome["choice"]["mode"] == "model_exploration"
        and type(outcome["choice"]["teacher_labels"]) is int
        and outcome["choice"]["teacher_labels"] == 0
        and started["selected_binding_ref"].startswith("pokemon.red:safari-live:")
        and outcome["safe_terminal"] is True
        and outcome["error_type"] == "RedAreaExecutionError"
        and outcome["error_chain"][0]["reason_code"] == "semantic_action_limit_exceeded"
        and outcome["before"]["cash"] - outcome["after"]["cash"] == 500,
        "original failed choice mismatch",
    )
    _require(
        paid["schema"] == "pokemon.red.paid-safari-continuation.v1"
        and paid["input_plan_sha256"] == digest("paid_safari_input")
        and paid["original_goal_outcome_sha256"] == digest("prior_outcome")
        and paid["original_selected_binding"] == started["selected_binding_ref"]
        and paid["before_state_sha256"] == outcome["terminal_state_sha256"]
        and result["schema"] == "pokemon.red.paid-safari-continuation-result.v1"
        and result["before_state_sha256"] == paid["before_state_sha256"]
        and result["terminal_state_sha256"] == plan["state"]["sha256"]
        and result["safe_terminal"] is True
        and result["preserved_resources"] is True
        and result["error"]["type"] == "RedAreaExecutionError"
        and result["error"]["reason_code"] == "semantic_action_limit_exceeded"
        and result["report"] is None
        and result["registered_gains"] == [],
        "paid failure mismatch",
    )
    for record, key in (
        (paid, "model_queries"),
        (result, "model_queries"),
        (result, "extra_payment"),
    ):
        _require(type(record[key]) is int and record[key] == 0, "paid search queried or repaid")
    for cost, old_cost, cap, remaining in (
        ("macros", "actions", "maximum_macros", "remaining_original_actions"),
        ("frames", "frames", "maximum_frames", "remaining_original_frames"),
    ):
        original_cap = parent["provenance"]["maximum_" + old_cost]
        spent, old_spent = result["after"][cost], outcome["after"][old_cost]
        _require(
            all(_integer(x) for x in (original_cap, spent, old_spent, paid[cap], paid[remaining]))
            and paid[remaining] == original_cap - old_spent
            and spent <= paid[cap] <= paid[remaining],
            "cost exceeds original allowance",
        )
    _require(
        audit["schema"] == "pokemon.red.paid-safari-native-audit.v1"
        and audit["status"] == "verified_native_zero_input"
        and audit["terminal_sha256"] == plan["state"]["sha256"]
        and audit["result_sha256"] == digest("paid_safari_result")
        and audit["safe"] is True
        and audit["original_inputs_unchanged"] is True
        and type(audit["frames"]) is int
        and audit["frames"] == 0,
        "independent audit mismatch",
    )
    facts, before, after = audit["facts"], outcome["after"], result["after"]
    for key in (
        "cash",
        "owned_species",
        "registered_species",
        "specimen_counts",
        "specimens",
        "bag_items",
        "party_hp",
        "party_pp",
    ):
        _require(facts[key] == before[key], "protected resource changed: " + key)
    _require(
        facts["cash"] == after["cash"]
        and facts["registered_species"] == after["registrations"]
        and facts["specimens"] == result["specimens_before"] == result["specimens_after"]
        and [facts["map_id"], *facts["position_yx"]] == after["position"]
        and facts["session"] == after["session"],
        "audit/result facts differ",
    )
    session = facts["session"]
    _require(
        session["in_safari_zone"] is True
        and session["safari_game_over"] is False
        and before["session"]["in_safari_zone"] is True
        and before["session"]["safari_game_over"] is False,
        "inactive paid session",
    )
    for key in ("safari_balls", "safari_steps"):
        _require(
            _integer(session[key], 1)
            and _integer(before["session"][key], 1)
            and session[key] <= before["session"][key],
            "paid resources increased",
        )
    return facts


def verify_paid_safari_live_facts(expected, actual):
    """Fresh native reads are mandatory before input, not just audit claims."""
    normalized = json.loads(json.dumps(actual))
    for key in FACT_KEYS:
        if key not in {"battle_state", "input_ready"}:
            _require(key in expected and normalized.get(key) == expected[key], "live " + key)
    _require(
        normalized.get("battle_state") == 0 and normalized.get("input_ready") is True,
        "live boundary is unsafe",
    )
    _require(
        normalized.get("party_training")
        == [[member["slot"], member["species_id"], member["xp"]] for member in expected["party"]],
        "live party training differs",
    )
