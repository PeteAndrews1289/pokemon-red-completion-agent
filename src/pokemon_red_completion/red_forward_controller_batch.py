"""Whole declared batches of finite returns under one frozen Red controller.

This separate path can include authenticated known stops from failed physical
artifacts. It never changes complete-only native admission or turns an unknown
interruption into zero. Batch identity is pinned before fitting; no row selector
is exposed to a fitting caller.
"""

from dataclasses import dataclass
from typing import cast

from .forward_goal import ForwardGoalOutcome
from .forward_goal_records import _mapping, restore_forward_goal_plan
from .living_dex_option_value import LivingDexOptionValueModel
from .private_artifacts import PrivateArtifactRoot
from .red_forward_dataset import load_red_forward_episode
from .red_forward_quarantine import load_failed_red_forward_controller_return
from .red_player_training_plan import RedPlayerTrainingPlan

CONTROLLER_RETURN_CONTRACT = "finite-goal-under-frozen-controller.v1"
CONTROLLER_BATCH_KIND = "red_forward_controller_batch"
CONTROLLER_BATCH_SCHEMA = "pokemon.red.forward-controller-batch.v1"


@dataclass(frozen=True, slots=True)
class RedForwardControllerBatch:
    outcomes: tuple[ForwardGoalOutcome, ...]
    cancelled_episode_ids: tuple[str, ...]
    attempted_episode_ids: tuple[str, ...]
    batch_record_sha256: str
    failed_stops: int
    episode_requests: tuple[dict[str, object], ...]


def load_red_forward_controller_batch(
    store: PrivateArtifactRoot,
    *,
    batch_record_id: str,
    expected_batch_record_sha256: str,
    behavior_model: LivingDexOptionValueModel,
) -> RedForwardControllerBatch:
    """Admit every attempted row in the pinned declaration or return nothing."""
    record = store.find_sealed_record(batch_record_id, expected_kind=CONTROLLER_BATCH_KIND)
    if record is None or record.summary.record_sha256 != expected_batch_record_sha256:
        raise ValueError("controller-return batch declaration differs")
    doc = record.read()
    if set(doc) != {
        "schema",
        "return_contract",
        "behavior_model_sha256",
        "forward_plan_sha256",
        "declared_episode_ids",
        "episodes",
        "cancelled_episode_ids",
        "independent_evaluation",
    } or (
        doc["schema"] != CONTROLLER_BATCH_SCHEMA
        or doc["return_contract"] != CONTROLLER_RETURN_CONTRACT
        or doc["behavior_model_sha256"] != behavior_model.model_sha256
        or doc["independent_evaluation"] is not False
    ):
        raise ValueError("controller-return batch scope differs")
    declared = _identities(doc["declared_episode_ids"])
    cancelled = _identities(doc["cancelled_episode_ids"])
    rows = doc["episodes"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= 512:
        raise ValueError("controller-return batch must contain every attempted episode")
    requests = tuple(_mapping(row) for row in rows)
    attempted = _identities([row.get("episode_id") for row in requests])
    if set(attempted) & set(cancelled) or set(attempted) | set(cancelled) != set(declared):
        raise ValueError("controller-return batch omits or replaces a declared episode")
    if any(store.inspect_episode_state(episode_id).status != "absent" for episode_id in cancelled):
        raise ValueError("controller-return batch cancels an existing episode artifact")
    outcomes = []
    failed_stops = 0
    for request in requests:
        failed = request.get("status") == "failed_stopped"
        fields = {"episode_id", "manifest_sha256", "status"}
        if failed:
            fields |= {"failure_state_sha256", "rom_sha256"}
        if set(request) != fields or request.get("status") not in {"complete", "failed_stopped"}:
            raise ValueError("controller-return episode declaration differs")
        episode_id = cast(str, request["episode_id"])
        reader = store.open_failed_episode(episode_id) if failed else store.open_episode(episode_id)
        if reader.manifest_sha256 != request["manifest_sha256"]:
            raise ValueError("controller-return episode manifest differs")
        metadata = _mapping(reader.read_header()["metadata"])
        plan = RedPlayerTrainingPlan(_mapping(metadata["player_training_plan"]))
        forward = restore_forward_goal_plan(metadata["forward_goal_plan"])
        if forward.sha256 != doc["forward_plan_sha256"]:
            raise ValueError("controller-return goal or continuation differs across batch")
        if failed:
            outcome = load_failed_red_forward_controller_return(
                store,
                episode_id=episode_id,
                expected_manifest_sha256=cast(str, request["manifest_sha256"]),
                training_plan=plan,
                behavior_model=behavior_model,
                forward_plan=forward,
                objective_id=cast(str, metadata["forward_story_objective"]),
                expected_failure_state_sha256=cast(str, request["failure_state_sha256"]),
                expected_rom_sha256=cast(str, request["rom_sha256"]),
                return_contract=CONTROLLER_RETURN_CONTRACT,
            )
            failed_stops += 1
        else:
            outcome = load_red_forward_episode(
                store,
                episode_id=episode_id,
                expected_manifest_sha256=cast(str, request["manifest_sha256"]),
                training_plan=plan,
                behavior_model=behavior_model,
                forward_plan=forward,
                objective_id=cast(str, metadata["forward_story_objective"]),
            )
        outcomes.append(outcome)
    return RedForwardControllerBatch(
        tuple(outcomes),
        cancelled,
        attempted,
        record.summary.record_sha256,
        failed_stops,
        tuple(dict(row) for row in requests),
    )


def _identities(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > 1024
        or any(not isinstance(item, str) or not item or len(item) > 160 for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("controller-return episode identities differ")
    return tuple(value)
