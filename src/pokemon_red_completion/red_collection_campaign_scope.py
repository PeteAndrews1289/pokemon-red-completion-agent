"""Actor scope of optional collection observations on normal development campaigns."""


def development_campaign_scope(plan):
    """Fresh and restored normal campaigns retain their own declaration and safety."""
    declared = plan.get("development_campaign", False)
    if type(declared) is not bool:
        raise ValueError("development_campaign must be an explicit boolean")
    if not declared:
        return False
    fresh = plan.get("new_campaign")
    if (plan.get("partition") != "development" or type(fresh) is not bool
            or plan.get("campaign_continuation", False) is not (not fresh)
            or plan.get("diagnostic_only", False) is not False
            or plan.get("qualification_only", False) is not False
            or plan.get("official_acceptance") is not False or plan.get("fit_allowed") is not False
            or plan.get("copy_back") is not False or plan.get("training_admission", False) is not False
            or plan.get("force_resource_safety") is not True
            or plan.get("actual_gameplay_resume_authorized", False) is not False
            or plan.get("acceptance_declaration") is not None
            or any(k in plan for k in ("matched_collection_order", "collection_transfer_capture",
                "collection_menu_probe", "matched_preparation", "evolution_copy_experiment"))):
        raise ValueError("collection observations require a normal non-fitting development campaign")
    return True


def collection_observation_wiring(plan):
    if development_campaign_scope(plan):
        return dict(development_campaign=True, new_campaign=plan["new_campaign"],
                    campaign_continuation=not plan["new_campaign"], diagnostic_only=False,
                    official_acceptance=False, actual_gameplay_resume_authorized=False,
                    force_resource_safety=True)
    # v1 copy observation declaration; no campaign has been inferred.
    return dict(diagnostic_only=True, new_campaign=False, official_acceptance=False)
