"""Explicit train-only reuse of a registered measured terminal.

This does not admit the parent to the catalog, repair its missing action trace,
or turn repeated observations into independent roots. The new episode records
its own native action trace and measured outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from .living_dex_player_exploration import exploration_policy_id
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .red_player_checkpoint import CHECKPOINT_KIND, _join_episode, checkpoint_record_id
from .red_player_training_plan import (
    COMPLETION_ACTIONS,
    COMPLETION_FRAMES,
    CORRELATED_COMPLETION_TRAINING_PLAN_SCHEMA,
    CORRELATED_ECONOMY_TRAINING_PLAN_SCHEMA,
    CORRELATED_REGISTERED_TRAINING_PLAN_SCHEMA,
    RedPlayerTrainingPlan,
)
from .red_recorded_support import REGISTERED_MEASURED_CHECKPOINT_SCHEMA


def _parent(store: PrivateArtifactRoot, episode_id: str, checkpoint_sha256: str):
    record = store.find_sealed_record(
        checkpoint_record_id(episode_id), expected_kind=CHECKPOINT_KIND
    )
    if record is None or record.summary.record_sha256 != checkpoint_sha256:
        raise ValueError("correlated reset parent checkpoint differs")
    document = record.read()
    episode = store.open_episode(episode_id)
    metadata = episode.read_header().get("metadata")
    split = metadata.get("split") if isinstance(metadata, Mapping) else None
    if (
        document.get("schema") != REGISTERED_MEASURED_CHECKPOINT_SCHEMA
        or document.get("context_origin") != "training"
        or not isinstance(metadata, Mapping)
        or metadata.get("training_eligible") is not False
        or not isinstance(split, Mapping)
        or split.get("partition") != "train"
        or _join_episode(store, document, verified_episode=episode)
        != document.get("trajectory_manifest_sha256")
    ):
        raise ValueError("correlated reset requires an authenticated measured train parent")
    return document, split


def reset_record_id(plan: RedPlayerTrainingPlan) -> str:
    # Source/model/seed/child-name changes cannot reissue the same declared reset.
    return "rp-reset-" + canonical_sha256(
        {
            "parent": plan.document["continuation_checkpoint_sha256"],
            "reset_id": plan.document["reset_id"],
        }
    )


def declare_correlated_reset(
    store: PrivateArtifactRoot,
    *,
    parent_episode_id: str,
    parent_checkpoint_sha256: str,
    reset_id: str,
    episode_id: str,
    state_sha256: str,
    envelope_sha256: str,
    restore_profile_sha256: str,
    execution_profile_sha256: str,
    model_sha256: str,
    source_commit: str,
    source_bundle_sha256: str,
    seed: int,
    feature_version: int,
) -> RedPlayerTrainingPlan:
    exploration_policy_id(feature_version)  # Reject unknown versions before any parent read.
    parent, split = _parent(store, parent_episode_id, parent_checkpoint_sha256)
    identity = canonical_sha256({"parent": parent_checkpoint_sha256, "reset_id": reset_id})
    plan = RedPlayerTrainingPlan(
        {
            "schema": CORRELATED_COMPLETION_TRAINING_PLAN_SCHEMA,
            "episode_id": episode_id,
            "reset_id": reset_id,
            "partition": "train",
            "seed": seed,
            "decision_limit": 1,
            "behavior_policy_id": exploration_policy_id(min(feature_version, 3)),
            "economic_contract": "known-spend-and-bounded-consumption-v2",
            "context_catalog_sha256": identity,
            "context_id": identity,
            "binding_manifest_sha256": identity,
            "catalog_admitted": False,
            "independent_root": False,
            "parent_evidence_tier": "registered-measured-terminal",
            "parent_manifest_sha256": parent["trajectory_manifest_sha256"],
            "root_lineage_id": split["root_lineage_id"],
            "origin_state_sha256": parent["original_state_sha256"],
            "origin_envelope_sha256": parent["original_envelope_sha256"],
            "continuation_episode_id": parent_episode_id,
            "continuation_checkpoint_sha256": parent_checkpoint_sha256,
            "restore_profile_sha256": restore_profile_sha256,
            "state_sha256": state_sha256,
            "envelope_sha256": envelope_sha256,
            "profile_sha256": execution_profile_sha256,
            "model_sha256": model_sha256,
            "source_commit": source_commit,
            "source_bundle_sha256": source_bundle_sha256,
            "maximum_actions": COMPLETION_ACTIONS,
            "maximum_frames": COMPLETION_FRAMES,
            "independent_evaluation": False,
            "historical_trial_retry": False,
            "episode_retry_after_input": False,
        }
    )
    require_correlated_parent(store, plan)
    if store.inspect_episode_state(reset_record_id(plan)).status != "absent":
        raise ValueError("correlated reset identity already consumed")
    return plan


def require_correlated_parent(store: PrivateArtifactRoot, plan: RedPlayerTrainingPlan) -> None:
    p = plan.document
    parent, split = _parent(
        store,
        cast(str, p["continuation_episode_id"]),
        cast(str, p["continuation_checkpoint_sha256"]),
    )
    expected = {
        "state_sha256": parent["state_sha256"],
        "envelope_sha256": hashlib.sha256(
            json.dumps(parent["envelope"]).encode("ascii")
        ).hexdigest(),
        "restore_profile_sha256": parent["profile_sha256"],
        "model_sha256": parent["model_sha256"],
        "parent_manifest_sha256": parent["trajectory_manifest_sha256"],
        "origin_state_sha256": parent["original_state_sha256"],
        "origin_envelope_sha256": parent["original_envelope_sha256"],
        "root_lineage_id": split["root_lineage_id"],
    }
    identity = canonical_sha256(
        {"parent": p["continuation_checkpoint_sha256"], "reset_id": p["reset_id"]}
    )
    expected.update(
        {
            key: identity
            for key in ("context_catalog_sha256", "context_id", "binding_manifest_sha256")
        }
    )
    if any(p.get(key) != value for key, value in expected.items()):
        raise ValueError("correlated reset parent provenance differs")


def claim_correlated_reset(store: PrivateArtifactRoot, plan: RedPlayerTrainingPlan) -> None:
    """Exclusive durable declaration before preflight, query or controller input.

    A preflight failure or process interruption consumes this identity too. The
    claim remains even if no native episode can be completed.
    """
    if plan.document["schema"] not in {
        CORRELATED_REGISTERED_TRAINING_PLAN_SCHEMA,
        CORRELATED_ECONOMY_TRAINING_PLAN_SCHEMA,
    }:
        raise ValueError("correlated reset requires its registered objective")
    require_correlated_parent(store, plan)
    # Sealed-record publication is idempotent, so it is not a one-shot lock.
    # The episode namespace is exclusive even after a partial/crashed write.
    identity = reset_record_id(plan)
    with store.begin_episode(identity) as writer:
        writer.append(
            "episode",
            {"episode_id": identity, "metadata": {"correlated_reset_plan": dict(plan.document)}},
            durable=True,
        )
        writer.complete()


def require_correlated_claim(store: PrivateArtifactRoot, plan: RedPlayerTrainingPlan) -> None:
    if plan.document["schema"] not in {
        CORRELATED_REGISTERED_TRAINING_PLAN_SCHEMA, CORRELATED_ECONOMY_TRAINING_PLAN_SCHEMA,
    }:
        raise ValueError("unregistered correlated reset cannot be fitted")
    require_correlated_parent(store, plan)
    record = store.open_episode(reset_record_id(plan))
    if record.read_header().get("metadata") != {"correlated_reset_plan": dict(plan.document)}:
        raise ValueError("correlated reset write-ahead claim differs")
