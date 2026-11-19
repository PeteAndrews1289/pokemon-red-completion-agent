"""Credit measured effort of one verified ordinary survey at the same physical site.

The optional first-menu observation describes the preceding survey, including all
its travel. It makes no claim about a capture of the remaining species.
"""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from .gen1_traversal import Direction
from .goal_manager import GoalKind
from .goal_search_memory import GoalSearchHistory
from .living_dex_option_value import LivingDexOptionKind
from .observation import ItemId
from .provenance import canonical_sha256
from .red_fishing_acquisition import red_species_number, red_super_rod_destination_offers

MODE = "compare_successful_fishing_site_effort"
PREFIX = "pokemon.red:fishing-live:"


def declared_survey_comparison(plan):
    enabled = plan.get(MODE, False)
    from .red_collection_campaign_scope import development_campaign_scope
    if enabled is True and development_campaign_scope(plan):
        return True
    if type(enabled) is not bool or enabled and (
        plan.get("partition") != "development"
        or plan.get("diagnostic_only") is not True or plan.get("new_campaign") is not False
        or any(k in plan for k in ("matched_collection_order", "collection_transfer_capture", "collection_menu_probe"))
        or plan.get("official_acceptance") is not False or plan.get("fit_allowed") is not False
        or plan.get("copy_back") is not False or plan.get("actual_gameplay_resume_authorized", False) is not False
    ):
        raise ValueError("same-site survey comparison requires an isolated DEVELOPMENT copy")
    return enabled


def _read(path):
    return json.loads(path.read_bytes())


def _digest(path):
    return sha256(path.read_bytes()).hexdigest()


def _stocked(facts):
    d = facts["diagnostics"]
    return (facts["input_ready"] is True and facts["buttons_released"] is True
            and facts["battle_state"] == 0 and d["immediate_capture_slots"] > 0
            and any(i in (ItemId.ULTRA_BALL, ItemId.GREAT_BALL, ItemId.POKE_BALL) and q > 0 for i, q in d["bag_items"]))


def _rebound(rom, outcome, previous):
    before, after, report = outcome["before"], outcome["after"], outcome["evidence"]
    gained = set(after["owned_species"]) - set(before["owned_species"])
    if (not set(before["owned_species"]) <= set(after["owned_species"])
            or len(gained) != report["new_registrations"] or not _stocked(after)):
        return None
    native = after["diagnostics"]
    map_id, y, x = native["map_id"], native["player_y"], native["player_x"]

    def missing(facts):
        owned = {red_species_number(s) for s in facts["owned_species"]}
        return next((o.missing_species_numbers for o in red_super_rod_destination_offers(rom, owned)
                     if o.map_id == map_id), ())

    old_pool, remaining = missing(before), missing(after)
    if (len(old_pool) != report["initial_missing_count"] or len(remaining) != report["final_missing_count"]
            or set(old_pool) - set(remaining) != {red_species_number(s) for s in gained}):
        return None
    for direction in Direction:
        dy, dx = direction.delta
        site = dict(map=map_id, stance=(y, x), facing=direction.value, water=(y + dy, x + dx))
        # These are the exact ordinary production binding fields; physical,
        # Safari, nonlocal and differently bounded surveys cannot match.
        old_ref = PREFIX + canonical_sha256(dict(site, missing=old_pool, casts=24))
        if old_ref == previous:
            return (canonical_sha256(dict(site, method="ordinary-super-rod")),
                    PREFIX + canonical_sha256(dict(site, missing=remaining, casts=24)))
    return None


def previous_successful_survey(parent, plan, rom):
    """Read the final actually executed predecessor from the paired chunk only."""
    if not declared_survey_comparison(plan):
        return None
    parent = Path(parent)
    if parent.resolve() != Path(plan["actual_parent"]).resolve():
        raise ValueError("survey parent differs from configured source")
    result, context = _read(parent / "RESULT.json"), _read(parent / "CONTEXT.json")
    state = plan["source_sha256"]
    if (state != result["state_sha256"] or state != context["state_sha256"]
            or state != _digest(parent / "terminal.state") or plan["context_sha256"] != result["context_sha256"]
            or plan["context_sha256"] != _digest(parent / "CONTEXT.json")):
        raise ValueError("survey state/context pairing differs")
    episode = result.get("episode") or {}
    outcomes = episode.get("outcomes") or []
    if not outcomes or len(outcomes) != episode.get("executed_decisions"):
        return None
    out = outcomes[-1]
    report = out.get("evidence") or {}
    if (out.get("ordinal") != len(outcomes) - 1 or out.get("terminal_state_sha256") != state
            or out.get("verification") != "succeeded" or out.get("safe_terminal") is not True
            or out.get("error") is not None or out.get("ordinary_setback") is not False
            or out.get("selected_kind") != "acquire_species"
            or report.get("schema") != "pokemon.red.registered-fishing-capture.v1"
            or report.get("status") != "succeeded" or report.get("final_missing_count", 0) < 1
            or report.get("new_registrations", 0) < 1 or report.get("search_exhausted") is not False
            or report.get("capture_items_exhausted") is not False or report.get("physical_acquisitions") != 0):
        return None
    step = parent / "native" / "episode" / f"step-{out['ordinal']:03d}"
    if _read(step / "outcome.json") != out or _digest(step / "terminal.state") != state:
        raise ValueError("last survey outcome or terminal differs")
    intent, start = _read(step / "intent.json"), _read(step / "execution-started.json")
    decision = _read(step / "decision.json")
    refs = intent["private_selection_authority"]["live_bindings"]
    if (out["choice"] != decision or decision["mode"] != "model_greedy"
            or start["state_sha256"] != out["before_state_sha256"]
            or start["state_sha256"] != intent["state_sha256"]
            or start["state_sha256"] != _digest(step / "before.state")
            or start["menu_sha256"] != decision["menu_sha256"] or start["selected_kind"] != out["selected_kind"]
            or refs[decision["selected_candidate_index"]]["binding_ref"] != start["selected_binding_ref"]):
        raise ValueError("last survey's native decision differs")
    old_ref = start["selected_binding_ref"]
    if not old_ref.startswith(PREFIX):
        return None
    site = _rebound(rom, out, old_ref)
    if site is None:
        return None
    actions, frames = (out["measured_cost"][k] for k in ("actions", "frames"))
    if (actions <= 0 or frames <= 0 or any(out["after"][k] - out["before"][k] != v
            for k, v in (("actions",actions),("frames",frames),("completed_actions",actions)))):
        raise ValueError("preceding survey effort differs from measured counters")
    before, after = (_read(step / f"search-memory-{phase}.json") for phase in ("before", "after"))
    objective = before["objectives_by_binding"][old_ref]
    key = canonical_sha256(dict(source=old_ref, objective=objective))
    if (objective != after["objective_sha256"] or before["state_sha256"] != out["before_state_sha256"]
            or after["state_sha256"] != state or after["outcome_sha256"] != canonical_sha256(out)
            or after["memory"]["entries"] != context["search_memory"]["entries"]):
        raise ValueError("preceding survey effort is not retained in parent")
    earlier = before["memory"]["entries"].get(key, GoalSearchHistory().public_dict())
    later = after["memory"]["entries"][key]
    if tuple(later[k] - earlier[k] for k in ("attempts", "exhausted", "actions", "frames")) != (1, 0, actions, frames):
        raise ValueError("preceding survey effort is not a single successful delta")
    return dict(state=state, site_sha256=site[0], live_binding=site[1], source_binding=old_ref,
                source_outcome_sha256=canonical_sha256(out), actions=actions, frames=frames)


def observe_rebound_effort(options, before, survey):
    """Apply a single verified predecessor to one empty ordinary-fishing row."""
    candidates = options.menu.candidates
    if before.sha256 != survey["state"] or not _stocked(before.facts):
        return options, None
    eligible = [i for i, (candidate, binding) in enumerate(zip(candidates, options.bindings, strict=True))
                if binding.binding_ref == survey["live_binding"] and i in options.menu.available_indices
                and binding.kind is GoalKind.ACQUIRE_SPECIES and candidate.features.kind is LivingDexOptionKind.ACQUIRE
                and candidate.features.travel_effort == 0 and candidate.search_history == GoalSearchHistory()]
    if len(eligible) != 1:
        return options, None
    index = eligible[0]
    prior = GoalSearchHistory(1, 0, survey["actions"], survey["frames"])
    rows = (*candidates[:index], replace(candidates[index], search_history=prior), *candidates[index + 1:])
    return replace(options, menu=replace(options.menu, candidates=rows)), dict(
        schema="pokemon.red.observed-same-site-survey.v1", candidate_index=index,
        source_outcome_sha256=survey["source_outcome_sha256"], site_sha256=survey["site_sha256"],
        state_sha256=before.sha256, previous_verification="succeeded", prior=prior.public_dict(),
        cumulative_memory_written=False, score_override=False)
