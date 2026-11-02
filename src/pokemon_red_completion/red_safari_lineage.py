"""Read-only admission of completed Safari recovery back into normal collection.

Historical failures remain failures. This adapter authenticates their exact chain;
it neither manufactures a generic success receipt nor authorizes another attempt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXACT_PLAN = "pokemon.red.safari-fishing-exact-continuation.v1"
RECORDS = frozenset(
    {
        "origin_plan",
        "origin_result",
        "origin_outcome",
        "origin_started",
        "settlement",
        "censored_plan",
        "censored_audit",
        "choice_plan",
        "choice_result",
        "choice_outcome",
        "choice_started",
    }
)
FACT_KEYS = (
    "cash",
    "owned_species",
    "registered_species",
    "specimen_counts",
    "specimens",
    "bag_items",
    "party_hp",
    "party_pp",
    "session",
    "map_id",
    "position_yx",
    "battle_state",
    "input_ready",
)


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(f"Safari lineage: {detail}")


def load_safari_lineage(payload: bytes) -> dict[str, bytes]:
    manifest = json.loads(payload)
    _require(
        manifest.get("schema") == "pokemon.red.completed-safari-lineage.v1", "unsupported manifest"
    )
    refs = manifest.get("records", {})
    _require(set(refs) == RECORDS, "missing or unexpected ancestors")
    records = {}
    for key, ref in refs.items():
        content = Path(ref["path"]).read_bytes()
        _require(
            hashlib.sha256(content).hexdigest() == ref["sha256"], f"{key} authentication failed"
        )
        records[key] = content
    return records


def _autonomous_chain(parent, result, outcome, started, reserve, model):
    provenance = parent["provenance"]
    _require(
        parent["schema"] == "pokemon.red.autonomous-option-run.v1"
        and result["schema"] == "pokemon.red.autonomous-option-result.v1"
        and parent["model_sha256"] == result["model_sha256"] == model
        and parent["teacher_actions_allowed"] is False
        and result["teacher_actions"] == 0
        and provenance["reserve_origin_state_sha256"] == reserve
        and not provenance.get("training_assistance"),
        "autonomous origin mismatch",
    )
    rows = result["outcomes"]
    _require(bool(rows) and rows[-1] == outcome, "missing failed outcome")
    state = provenance["parent_state_sha256"]
    for index, row in enumerate(rows):
        _require(
            row["ordinal"] == index
            and row["before_state_sha256"] == state
            and (index == len(rows) - 1 or row["safe_terminal"] is True),
            "broken autonomous state chain",
        )
        state = row["terminal_state_sha256"]
    choice = outcome["choice"]
    _require(
        outcome["safe_terminal"] is False
        and outcome["selected_kind"] == started["selected_kind"] == "acquire_species"
        and started["state_sha256"] == outcome["before_state_sha256"]
        and started["menu_sha256"] == choice["menu_sha256"]
        and choice["mode"] == "model_exploration"
        and choice["teacher_labels"] == 0
        and choice["model_sha256"] == model,
        "failed model choice mismatch",
    )


def verify_completed_safari(plan, payloads, records: dict[str, bytes]) -> None:
    """Validate the specialized chain against authenticated new-plan inputs."""
    try:
        _verify_completed_safari(plan, payloads, records)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("Safari lineage: incomplete or malformed receipt") from error


def _verify_completed_safari(plan, payloads, records):
    _require(set(records) == RECORDS, "missing or unexpected ancestors")
    docs = {key: json.loads(value) for key, value in records.items()}
    hashes = {key: hashlib.sha256(value).hexdigest() for key, value in records.items()}
    parent = json.loads(payloads["prior_plan"])
    final = json.loads(payloads["prior_outcome"])
    reserve, model = plan["reserve_origin"]["sha256"], plan["model_sha256"]
    _require(
        not plan.get("assisted_training_money") and plan.get("mode") is None,
        "completed chain requires ordinary unassisted collection",
    )
    for prefix in ("origin", "choice"):
        _autonomous_chain(
            *(docs[f"{prefix}_{suffix}"] for suffix in ("plan", "result", "outcome", "started")),
            reserve,
            model,
        )
    origin, settled = docs["origin_outcome"], docs["settlement"]
    _require(
        settled["schema"] == "pokemon.red.defensive-safari-settlement-result.v1"
        and settled["parent_outcome_sha256"] == hashes["origin_outcome"]
        and settled["before_state_sha256"] == origin["terminal_state_sha256"]
        and settled["safe_terminal"] is True
        and settled["preserved_resources"] is True
        and settled["error"] is None
        and settled["model_queries"] == 0
        and settled["extra_payment"] == 0,
        "defensive settlement mismatch",
    )
    censored, audit = docs["censored_plan"], docs["censored_audit"]
    _require(
        censored["schema"] == "pokemon.red.safari-fishing-goal-continuation.v1"
        and censored["parent_outcome_sha256"] == hashes["origin_outcome"]
        and censored["settlement_result_sha256"] == hashes["settlement"]
        and censored["before_state_sha256"] == settled["terminal_state_sha256"]
        and censored["selected_binding_ref"] == docs["origin_started"]["selected_binding_ref"]
        and censored["reserve_origin"]["sha256"] == reserve
        and censored["model_queries"] == 0,
        "censored continuation mismatch",
    )
    _require(
        audit["schema"] == "pokemon.red.fishing-report-serialization-audit.v1"
        and audit["plan_sha256"] == hashes["censored_plan"]
        and audit["before_state_sha256"] == censored["before_state_sha256"]
        and audit["status"] == "terminal_verified_telemetry_censored"
        and audit["safe"] is True
        and audit["resource_preservation"] is True
        and audit["replayed"] is False
        and audit["model_queries"] == 0
        and audit["actions"] is None
        and audit["frames"] is None,
        "censored audit mismatch; unknown costs must stay unknown",
    )
    choice_plan, outcome, started = (
        docs[k] for k in ("choice_plan", "choice_outcome", "choice_started")
    )
    _require(
        choice_plan["provenance"]["parent_terminal_audit_sha256"] == hashes["censored_audit"]
        and choice_plan["provenance"]["parent_state_sha256"] == audit["terminal_sha256"]
        and outcome["error_type"] == "SafariFishingError"
        and outcome["after"]["battle_state"] == 1,
        "fresh choice ancestry mismatch",
    )
    _require(
        parent["schema"] == EXACT_PLAN
        and parent["parent_outcome_sha256"] == hashes["choice_outcome"]
        and parent["parent_result_sha256"] == hashes["choice_result"]
        and parent["before_state_sha256"] == outcome["terminal_state_sha256"]
        and parent["reserve_origin"]["sha256"] == reserve
        and parent["selected_binding_ref"] == started["selected_binding_ref"]
        and started["selected_binding_ref"].startswith("pokemon.red:safari-fishing-live:")
        and parent["model_queries"] == 0
        and parent["learning_eligible"] is False,
        "exact continuation mismatch",
    )
    _require(
        final["schema"] == "pokemon.red.safari-fishing-exact-continuation-result.v1"
        and final["before_state_sha256"] == parent["before_state_sha256"]
        and final["terminal_state_sha256"] == plan["state"]["sha256"]
        and final["safe_terminal"] is True
        and final["verification"] == "succeeded"
        and final["error"] is None
        and final["model_queries"] == 0
        and final["learning_eligible"] is False,
        "unfinished or substituted terminal",
    )
    before, after = final["before"], final["after"]
    for key in FACT_KEYS:
        _require(before[key] == outcome["after"][key], f"recovery boundary drift: {key}")
    for key in ("cash", "bag_items", "party_hp", "party_pp"):
        _require(before[key] == after[key], f"protected resource drift: {key}")
    _require(
        after["battle_state"] == 0 and after["input_ready"] is True and after["safe"] is True,
        "unready final state",
    )
    for key in ("safari_balls", "safari_steps"):
        _require(0 < after["session"][key] <= before["session"][key], "session resource drift")
    _require(
        after["session"]["in_safari_zone"] is True
        and after["session"]["safari_game_over"] is False,
        "ended session",
    )
    gained = set(after["owned_species"]) - set(before["owned_species"])
    _require(
        set(before["owned_species"]) <= set(after["owned_species"])
        and len(gained) == final["evidence"]["new_registrations"] > 0
        and after["registered_species"] == len(after["owned_species"])
        and all(
            after["specimen_counts"].get(s, 0) >= n for s, n in before["specimen_counts"].items()
        )
        and after["specimens"] == sum(after["specimen_counts"].values()),
        "collection drift",
    )
    for cost, cap in (("actions", "maximum_actions"), ("frames", "maximum_frames")):
        used, maximum = final[cost], parent[cap]
        _require(
            type(used) is int
            and type(maximum) is int
            and 0 <= used <= maximum
            and maximum + outcome["after"][cost] == choice_plan["provenance"][cap],
            "recovery budget drift",
        )


def verify_safari_terminal_facts(receipt: dict, facts: dict) -> None:
    """Compare fresh zero-input observation, not just claimed receipt safety."""
    expected = receipt["after"]
    # JSON normalizes the live adapter's tuples without weakening field equality.
    actual = json.loads(json.dumps(facts))
    _require(
        all(
            key in actual and key in expected and actual[key] == expected[key] for key in FACT_KEYS
        ),
        "live terminal resource drift",
    )
