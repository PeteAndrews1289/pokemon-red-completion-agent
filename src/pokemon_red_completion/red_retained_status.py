"""Add native status observations to retained TRAIN targets without relabeling.

The caller reopens authenticated snapshots with zero inputs. This pure merge
checks the observation boundary and preserves every measured return and legal
inventory; its receipt is not a new outcome or a continuation-policy admission.
"""

from copy import deepcopy

from .battle_scenario_capture import OBSERVATION_SCHEMA_V2
from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition


def enrich_retained_status(target, capture, legacy, observed):
    manifest = capture.manifest
    if (
        target.get("schema") != "pokemon.red.trainer-practice-three-head-targets.v1"
        or target.get("partition") != "train"
        or manifest.partition is not ScenarioPartition.TRAIN
        or target.get("observation_schema") != OBSERVATION_SCHEMA_V2
        or manifest.observation_schema != OBSERVATION_SCHEMA_V2
        or target.get("capture_id") != manifest.capture_id
        or target.get("root_lineage_id") != manifest.root_lineage_id
        or target.get("manifest_sha256") != capture.manifest_sha256
    ):
        raise ValueError("retained TRAIN capture binding differs")
    if (
        target.get("observation") != legacy
        or canonical_sha256(legacy) != manifest.initial_observation_sha256
    ):
        raise ValueError("retained native observation differs")
    previous = legacy["features"]["battle"]
    if "status_context" in previous:
        raise ValueError("retained observation already has status context")
    enriched = deepcopy(observed)
    context = enriched["features"]["battle"].pop("status_context", None)
    if enriched != legacy:
        raise ValueError("status reobservation changed an original field")
    if (
        not isinstance(context, dict)
        or set(context)
        != {
            "schema",
            "player_confused",
            "opponent_confused",
            "player_stages",
            "opponent_stages",
        }
        or context["schema"] != "pokemon.core.battle.status-context.v1"
        or any(type(context[k]) is not bool for k in ("player_confused", "opponent_confused"))
        or any(
            not isinstance(context[k], list)
            or len(context[k]) != 6
            or any(type(v) is not int or not -6 <= v <= 6 for v in context[k])
            for k in ("player_stages", "opponent_stages")
        )
    ):
        raise ValueError("native status context is incomplete")
    result = deepcopy(target)
    result["observation"] = deepcopy(observed)
    return result, {
        "capture_id": manifest.capture_id,
        "parent_target_sha256": canonical_sha256(target),
        "enriched_target_sha256": canonical_sha256(result),
        "state_sha256": manifest.state_sha256,
        "manifest_sha256": capture.manifest_sha256,
        "legacy_observation_sha256": manifest.initial_observation_sha256,
        "status_observation_sha256": canonical_sha256(observed),
        "returns_changed": False,
        "legal_inventories_changed": False,
        "new_training_outcomes": 0,
    }
