"""Small prospective declaration for repeatable, known-training player episodes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.living_dex_player_exploration import EXPLORATION_POLICY_ID
from pokemon_red_completion.provenance import canonical_sha256

TRAINING_PLAN_SCHEMA = "pokemon.red.bounded-player-training-plan.v2"
CONTINUATION_TRAINING_PLAN_SCHEMA = "pokemon.red.bounded-player-training-plan.v3"


@dataclass(frozen=True, slots=True)
class RedPlayerTrainingPlan:
    document: Mapping[str, object]

    def __post_init__(self) -> None:
        document = dict(self.document)
        continuation = document.get("schema") == CONTINUATION_TRAINING_PLAN_SCHEMA
        if document.get("schema") not in {
            TRAINING_PLAN_SCHEMA, CONTINUATION_TRAINING_PLAN_SCHEMA,
        } or document.get("partition") != "train":
            raise ValueError("player training declaration differs")
        expected_fields = {
            "schema",
            "episode_id",
            "partition",
            "seed",
            "decision_limit",
            "behavior_policy_id",
            "economic_contract",
            "context_catalog_sha256",
            "context_id",
            "catalog_source_commit",
            "binding_manifest_sha256",
            "root_lineage_id",
            "state_sha256",
            "envelope_sha256",
            "profile_sha256",
            "model_sha256",
            "source_commit",
            "source_bundle_sha256",
            "independent_evaluation",
            "historical_trial_retry",
            "episode_retry_after_input",
        }
        if continuation:
            expected_fields.update({
                "origin_state_sha256", "origin_envelope_sha256", "restore_profile_sha256",
                "continuation_episode_id", "continuation_checkpoint_sha256",
            })
        if set(document) != expected_fields:
            raise ValueError("player training declaration fields differ")
        if any(
            document[key] is not False
            for key in (
                "independent_evaluation",
                "historical_trial_retry",
                "episode_retry_after_input",
            )
        ):
            raise ValueError("player training scope differs")
        if (
            document["behavior_policy_id"] != EXPLORATION_POLICY_ID
            or document["economic_contract"] != "known-spend-and-excess-reserve-v1"
        ):
            raise ValueError("player training behavior differs")
        for name in ("source_commit", "catalog_source_commit"):
            value = document[name]
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
                raise ValueError("player training source differs")
        identities: tuple[str, ...] = ("episode_id", "root_lineage_id")
        if continuation:
            identities += ("continuation_episode_id",)
        for name in identities:
            value = document[name]
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", value) is None
            ):
                raise ValueError("player training identity differs")
        seed, limit = document.get("seed"), document.get("decision_limit")
        if type(seed) is not int or type(limit) is not int or not 1 <= limit <= 4 or seed < 0:
            raise ValueError("player training bounds differ")
        for name, value in document.items():
            if name.endswith("sha256") and (
                not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            ):
                raise ValueError("player training digest differs")
        object.__setattr__(self, "document", MappingProxyType(document))

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(dict(self.document))


def continue_red_player_training(
    original: RedPlayerTrainingPlan,
    *,
    capture: GoalManagerContextCapture,
    root_lineage_id: str,
    episode_id: str,
    checkpoint_sha256: str,
    restore_profile_sha256: str,
    execution_profile_sha256: str,
) -> RedPlayerTrainingPlan:
    """Bind an already authenticated train origin to its verified saved endpoint.

    The runner authenticates the completed checkpoint chain before calling this.
    This does not convert any earlier diagnostic choices into training targets.
    """
    if (
        original.document["schema"] != TRAINING_PLAN_SCHEMA
        or original.document["root_lineage_id"] != root_lineage_id
    ):
        raise ValueError("continued training origin differs")
    return RedPlayerTrainingPlan({
        **original.document,
        "schema": CONTINUATION_TRAINING_PLAN_SCHEMA,
        "origin_state_sha256": original.document["state_sha256"],
        "origin_envelope_sha256": original.document["envelope_sha256"],
        "state_sha256": capture.state_sha256,
        "envelope_sha256": capture.envelope_sha256,
        "profile_sha256": execution_profile_sha256,
        "restore_profile_sha256": restore_profile_sha256,
        "continuation_episode_id": episode_id,
        "continuation_checkpoint_sha256": checkpoint_sha256,
    })


def declare_red_player_training(
    *,
    repository_root: Path,
    catalog_path: Path,
    expected_catalog_sha256: str,
    capture: GoalManagerContextCapture,
    profile_sha256: str,
    model_sha256: str,
    source_commit: str,
    source_bundle_sha256: str,
    episode_id: str,
    seed: int,
    decision_limit: int,
) -> RedPlayerTrainingPlan:
    """Authenticate original train assignment without opening any other capture.

    New episodes are correlated training reuse, not retries of historical trials
    or new evaluation roots. The existing completed trials stay untouched.
    """
    if (
        type(seed) is not int
        or seed < 0
        or type(decision_limit) is not int
        or not 1 <= decision_limit <= 4
    ):
        raise ValueError("training seed or decision bound differs")
    payload = catalog_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_catalog_sha256:
        raise ValueError("training catalog digest differs")
    document = json.loads(payload)
    revision = document.get("source_commit")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("training catalog source differs")
    registry = load_committed_goal_manager_registry_at_revision(repository_root, revision)
    catalog = parse_goal_manager_context_catalog(payload, registry)
    matching = tuple(item for item in catalog.entries if item.capture_id == capture.capture_id)
    if len(matching) != 1:
        raise ValueError("training capture is not a unique catalog member")
    entry = matching[0]
    if (
        registry.assignment(entry.slot_id).partition != "train"
        or entry.state_sha256 != capture.state_sha256
        or entry.envelope_sha256 != capture.envelope_sha256
        or any(
            item.state_sha256 == capture.state_sha256
            and registry.assignment(item.slot_id).partition != "train"
            for item in catalog.entries
        )
    ):
        raise ValueError("training capture does not have an exclusively train origin")
    return RedPlayerTrainingPlan(
        {
            "schema": TRAINING_PLAN_SCHEMA,
            "episode_id": episode_id,
            "partition": "train",
            "seed": seed,
            "decision_limit": decision_limit,
            "behavior_policy_id": EXPLORATION_POLICY_ID,
            "economic_contract": "known-spend-and-excess-reserve-v1",
            "context_catalog_sha256": catalog.catalog_sha256,
            "context_id": entry.context_id,
            "catalog_source_commit": revision,
            "binding_manifest_sha256": entry.binding_manifest_sha256,
            "root_lineage_id": entry.root_lineage_id,
            "state_sha256": capture.state_sha256,
            "envelope_sha256": capture.envelope_sha256,
            "profile_sha256": profile_sha256,
            "model_sha256": model_sha256,
            "source_commit": source_commit,
            "source_bundle_sha256": source_bundle_sha256,
            "independent_evaluation": False,
            "historical_trial_retry": False,
            "episode_retry_after_input": False,
        }
    )
