"""Typed admission for isolated native Safari pilot outcomes, not production promotion.

Assistance is source construction only. Failed/interrupted execution is censored,
never relabeled as a completed search. No money-injection or economy targets.
The pilot candidate is kept outside the registered production model namespace.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionContext,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_training_plan import COMPLETION_ACTIONS, COMPLETION_FRAMES
from pokemon_red_completion.red_safari_acquisition import (
    RedSafariZoneOffer,
    red_safari_area_menu,
    select_red_safari_area,
)

SCHEMA = "pokemon.red.assisted-safari-pilot-episode.v1"
SCHEMA_V2 = "pokemon.red.assisted-safari-pilot-episode.v2"
MAX_ACTIONS = 3000
MAX_FRAMES = 300_000


def reward_contract(schema):
    """Learning units are fixed separately from the smaller execution ceiling.

    V1 remains replayable with its original labels. Never mix its cost units
    into a successor fit intended to use the registered-player scale.
    """
    if schema == SCHEMA:
        return "registered-novelty-with-safari-consumables-v1"
    if schema != SCHEMA_V2:
        raise ValueError("Safari pilot reward schema differs")
    return dict(name="registered-novelty-with-safari-consumables-v2",
                actions=COMPLETION_ACTIONS, frames=COMPLETION_FRAMES,
                registrations=124, safari_balls=30,
                storage="initial_free_party_slots", economy_labels=False)


def pilot_menu(before, offers, route_steps):
    money, slots = before["money"], before["free_party_slots"]
    context = LivingDexOptionContext(
        collection_pressure=1 - len(before["target_registered"]) / 124,
        dependency_pressure=0, access_pressure=0,
        resource_pressure=min(1, 500 / max(1, money)),
        storage_pressure=1 / max(1, slots), party_pressure=0, knowledge_pressure=0,
    )
    return red_safari_area_menu(
        context, offers, route_steps=route_steps, maximum_route_steps=600,
        available_money=money, free_storage_slots=slots,
    )


def pilot_outcome(before, after, *, actions, frames, captures, schema=SCHEMA):
    """Reconstruct real novelty/physical gain and normalized consumed resources."""
    reward_contract(schema)
    old, new = set(before["registered"]), set(after["registered"])
    old_target, new_target = set(before["target_registered"]), set(after["target_registered"])
    old_counts, new_counts = dict(before["specimens"]), dict(after["specimens"])
    if (
        not old <= new or not old_target <= new_target
        or any(new_counts.get(s, 0) < n for s, n in old_counts.items())
        or not set(new_counts) <= new or not set(old_counts) <= old
        or after["money"] != before["money"] - 500
        or after["battle"] != 0 or not after["ready"]
        or not 0 < actions <= MAX_ACTIONS or not 0 < frames <= MAX_FRAMES
        or type(captures) is not int or captures not in {0, 1}
        or len(new - old) != captures or len(new_target - old_target) != captures
        or sum(new_counts.values()) - sum(old_counts.values()) != captures
        or not 0 <= after["balls"] <= 30 or not 0 <= after["steps"] <= 500
        or before["party_species"] != after["party_species"][:len(before["party_species"])]
        or before["party_hp"] != after["party_hp"][:len(before["party_hp"])]
    ):
        raise ValueError("Safari pilot native outcome or resource ledger differs")
    return LivingDexObservedOutcome(
        LivingDexOutcomeStatus.SETTLED,
        verified_success=captures == 1, completion_gain=captures / 124,
        dependency_unlock_gain=0,
        action_cost=actions / (MAX_ACTIONS if schema == SCHEMA else COMPLETION_ACTIONS),
        frame_cost=frames / (MAX_FRAMES if schema == SCHEMA else COMPLETION_FRAMES),
        resource_cost=(30 - after["balls"]) / 30,
        party_cost=0, storage_cost=captures / before["free_party_slots"],
        irreversible_loss=0,
    )


def read_episode(directory: Path, *, expected_manifest_sha256: str, behavior_model,
                 expected_partition: str, expected_source_sha256: str):
    """Authenticate all artifacts, replay the choice, and reconstruct only its outcome.

    Returns None for retained censored failures. Caller must include every scheduled
    case, and cannot fit development rows through this admission function.
    """
    payload = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_manifest_sha256:
        raise ValueError("Safari pilot manifest differs")
    manifest = json.loads(payload)
    required = {"plan.json", "result.json", "before.json", "selection.json", "after.json",
                "actions.jsonl", "terminal.state"}
    schema = manifest.get("schema")
    if set(manifest) != {"schema", "files"} or schema not in {SCHEMA, SCHEMA_V2}:
        raise ValueError("Safari pilot manifest schema differs")
    files = manifest["files"]
    recovered = set(files) == required | {"recovery.json"}
    if set(files) != required and not recovered:
        raise ValueError("Safari pilot evidence inventory differs")
    data = {}
    for name, digest in files.items():
        raw = (directory / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Safari pilot artifact digest differs")
        if name.endswith(".json"):
            data[name] = json.loads(raw)
    plan, result = data["plan.json"], data["result.json"]
    if (
        plan.get("schema") != schema or result.get("schema") != schema
        or expected_partition not in {"train", "development"}
        or plan.get("partition") != expected_partition
        or plan.get("source_state_sha256") != expected_source_sha256
        or plan.get("behavior_model_sha256") != behavior_model.model_sha256
        or plan.get("teacher_assistance") != (
            "isolated_native_gate_source_only" if schema == SCHEMA
            else "isolated_native_gate_context_only")
        or plan.get("promotion_eligible") is not False
        or result.get("plan_sha256") != canonical_sha256(plan)
        or result.get("terminal_state_sha256") != files["terminal.state"]
        or result.get("economy_label_eligible") is not False
    ):
        raise ValueError("Safari pilot scope or source differs")
    if schema == SCHEMA_V2 and (
        plan.get("reward_contract") != reward_contract(schema)
        or plan.get("maximum_actions") != MAX_ACTIONS
        or plan.get("maximum_frames") != MAX_FRAMES
    ):
        raise ValueError("Safari pilot reward units or execution ceiling differs")
    selection, before, after = data["selection.json"], data["before.json"], data["after.json"]
    offers = tuple(RedSafariZoneOffer(
        r["source_id"], r["map_id"], tuple(tuple(s) for s in r["slots"]),
        tuple(r["missing_species_numbers"]),
    ) for r in selection["offers"])
    menu = pilot_menu(before, offers, tuple(selection["route_steps"]))
    chosen = select_red_safari_area(behavior_model, menu, offers, seed=plan["seed"])
    if (selection["choice"] != chosen.public_dict()
            or selection["menu"] != menu.policy_dict()
            or result["selection_sha256"] != canonical_sha256(selection)
            or selection["controller_actions_before_commit"] != 0):
        raise ValueError("Safari pilot choice commitment differs")
    trace = [json.loads(line) for line in (directory / "actions.jsonl").read_text().splitlines()]
    if len(trace) != result["actions"] or not trace:
        raise ValueError("Safari pilot action trace count differs")
    frame = 0
    for ordinal, row in enumerate(trace, 1):
        if (row["ordinal"] != ordinal or row["before_frame"] != frame
                or row["after_frame"] < frame
                or row["selection_sha256"] != result["selection_sha256"]):
            raise ValueError("Safari pilot action trace chain differs")
        frame = row["after_frame"]
    if frame != result["frames"]:
        raise ValueError("Safari pilot frame trace differs")
    if recovered:
        recovery = data["recovery.json"]
        if (recovery.get("kind") != "exact_selected_goal_continuation"
                or recovery.get("model_queries") != 0
                or recovery.get("additional_admissions") != 0
                or recovery.get("selection_sha256") != result["selection_sha256"]
                or recovery.get("original_plan_sha256") != result["plan_sha256"]
                or not 0 < recovery.get("original_actions", 0) < result["actions"]
                or not 0 < recovery.get("original_frames", 0) < result["frames"]):
            raise ValueError("Safari pilot recovery chain differs")
        parent_id = recovery.get("original_episode_id", "")
        if not isinstance(parent_id, str) or not re.fullmatch(r"[a-z0-9-]{1,100}", parent_id):
            raise ValueError("Safari pilot recovery parent identity differs")
        parent = directory.parent / parent_id
        if parent == directory or (parent / "recovery.json").exists():
            raise ValueError("Safari pilot recovery cannot loop or chain retries")
        if read_episode(
            parent, expected_manifest_sha256=recovery["original_manifest_sha256"],
            behavior_model=behavior_model, expected_partition=expected_partition,
            expected_source_sha256=expected_source_sha256,
        ) is not None:
            raise ValueError("Safari pilot recovery requires the retained censored parent")
        parent_result = json.loads((parent / "result.json").read_bytes())
        parent_plan = json.loads((parent / "plan.json").read_bytes())
        parent_trace = (parent / "actions.jsonl").read_bytes()
        prefix = b"".join((directory / "actions.jsonl").read_bytes().splitlines(keepends=True)
                          [:recovery["original_actions"]])
        if (parent_plan != plan or prefix != parent_trace
                or hashlib.sha256(parent_trace).hexdigest() != recovery["original_trace_sha256"]
                or parent_result["terminal_state_sha256"] != recovery["original_terminal_sha256"]
                or parent_result["actions"] != recovery["original_actions"]
                or parent_result["frames"] != recovery["original_frames"]
                or parent_result["selection_sha256"] != result["selection_sha256"]):
            raise ValueError("Safari pilot original failure or cost prefix differs")
    if result["status"] == "censored":
        return None
    if (result["status"] != "settled" or any(row["error"] is not None for row in trace)
            or after["map"] != chosen.selected_offer.map_id):
        raise ValueError("Safari pilot selected native destination differs")
    report = result["execution"]
    captures = report["captures"]
    if (report["admission"]["status"] != "ok"
            or report["admission"]["single_admission"] is not True):
        raise ValueError("Safari pilot native payment differs")
    outcome = pilot_outcome(before, after, actions=len(trace), frames=frame, captures=captures,
                            schema=schema)
    return LivingDexObservedArmExample(
        canonical_sha256({"plan": plan, "selection": selection}), expected_partition,
        menu, chosen.selected_candidate_index, chosen.probabilities, outcome,
    )
