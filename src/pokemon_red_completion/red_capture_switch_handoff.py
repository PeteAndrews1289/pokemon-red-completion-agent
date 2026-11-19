"""Certificates for a retained ordinary wild catcher-switch failure and its later settlement."""
from .provenance import canonical_sha256

ERROR = "capture protected catcher target fainted during the switch."


def catcher_switch_failure(outcome):
    chain = outcome.get("error_chain")
    return (outcome.get("error_type") == "ProtectedRecoveryError" and outcome.get("error") == ERROR
            and outcome.get("selected_kind") == "acquire_species" and outcome.get("failure_phase") == "execution"
            and type(outcome.get("safe_terminal")) is bool and isinstance(chain, (list, tuple)) and len(chain) == 1
            and isinstance(chain[0], dict) and chain[0].get("error_type") == "ProtectedRecoveryError"
            and chain[0].get("error") == ERROR)


def development_recovery(plan):
    if not isinstance(plan, dict) or (plan.get("partition") != "development"
            or plan.get("official_acceptance") is not False or plan.get("fit_allowed") is not False
            or plan.get("copy_back") is not False or plan.get("force_resource_safety") is not True
            or plan.get("actual_gameplay_resume_authorized", False) is not False):
        return False
    from .red_collection_campaign_scope import development_campaign_scope
    if plan.get("development_campaign") is True:
        return development_campaign_scope(plan)
    return (plan.get("diagnostic_only") is True and plan.get("new_campaign") is False
            and plan.get("training_admission", False) is False)


def valid_catcher_handoff(receipt):
    if not isinstance(receipt, dict):
        return False
    state, failure = receipt.get("state_sha256"), receipt.get("failed_outcome_sha256")
    return (all(isinstance(key, str) and len(key) == 64 and all(c in "0123456789abcdef" for c in key)
                for key in (state, failure))
            and receipt.get("schema") == "pokemon.red.qualified-native-control-handoff.v1"
            and receipt.get("ordinary_capture_switch_faint") is True
            and receipt.get("original_failure_reason") == "native_execution_error"
            and type(receipt.get("original_terminal_safe")) is bool and receipt.get("compulsory_settlement_required") is True
            and receipt.get("qualified") is True and receipt.get("failed_transport_preserved") is True
            and receipt.get("strategic_substitution") is False
            and receipt.get("binding_ref") == "pokemon.red:interrupted-wild:" + state
            and all(type(receipt.get(k)) is int and receipt[k] == 0 for k in ("inputs","frames","model_queries")))


def qualified_catcher_parent(result, outcome):
    receipt = result.get("qualified_native_control_handoff")
    return (result.get("continuation_reason") == "automatic_control_recovery" and valid_catcher_handoff(receipt)
            and receipt["state_sha256"] == result.get("state_sha256") == outcome.get("terminal_state_sha256")
            and receipt["original_terminal_safe"] is outcome.get("safe_terminal")
            and catcher_switch_failure(outcome) and receipt["failed_outcome_sha256"] == canonical_sha256(outcome))


def confirmed_catcher_settlement(receipt, episode):
    """Only the immediate, verified support action can settle this specific interruption."""
    if not valid_catcher_handoff(receipt) or not episode.get("outcomes"):
        return None
    outcome = episode["outcomes"][0]
    before, after = outcome.get("before") or {}, outcome.get("after") or {}
    evidence = outcome.get("evidence") or {}
    escape = evidence.get("escape") or {}
    terminal = outcome.get("terminal_state_sha256")
    if (outcome.get("before_state_sha256") != receipt["state_sha256"]
            or not isinstance(terminal,str) or len(terminal)!=64 or terminal==receipt["state_sha256"]
            or any(c not in "0123456789abcdef" for c in terminal)
            or outcome.get("selected_kind") != "recover_control" or outcome.get("support_role") != "deterministic_control_recovery"
            or outcome.get("verification") != "succeeded" or outcome.get("safe_terminal") is not True
            or outcome.get("error") is not None or outcome.get("error_type") is not None
            or before.get("battle_state") != 1 or after.get("battle_state") != 0
            or after.get("input_ready") is not True or after.get("buttons_released") is not True
            or evidence.get("model_queries") != 0 or evidence.get("learned_recovery") is not False
            or escape.get("hp_scope") != "whole_party" or escape.get("initial_battle_state") != 1
            or escape.get("final_battle_state") != 0 or escape.get("control_ready") is not True
            or any(escape.get(k) is not True for k in ("verified","party_preserved","pp_preserved","level_preserved"))
            or not ((escape.get("battle_result") == 2 and (escape.get("run_attempts",0) > 0
                         or escape.get("faint_prompt_exit") is True))
                    or (escape.get("ordinary_opponent_ko_exit") is True and escape.get("battle_result") == 0))):
        return None
    return dict(receipt, verified_settlement_terminal_sha256=terminal,
                verified_settlement_outcome_sha256=canonical_sha256(outcome))


def completed_catcher_handoff(receipt):
    if not valid_catcher_handoff(receipt):
        return False
    return (receipt["state_sha256"] != receipt.get("verified_settlement_terminal_sha256")
            and all(isinstance(v,str) and len(v)==64 and all(c in "0123456789abcdef" for c in v)
                    for v in (receipt.get("verified_settlement_terminal_sha256"),
                              receipt.get("verified_settlement_outcome_sha256"))))
