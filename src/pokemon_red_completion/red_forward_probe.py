"""Explicit training-probe scope for a first-choice head and a frozen old tail.

This is not fitted-data admission or a calibrated production promotion. The new
owner's source is recorded separately from the source that produced the fit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from .forward_goal import ForwardGoalPlan
from .forward_goal_learning import ForwardGoalModel
from .forward_goal_records import restore_forward_goal_model, restore_forward_goal_outcome
from .living_dex_option_value import LivingDexOptionValueModel, option_feature_names
from .living_dex_player_exploration import RECOVERY_EXPLORATION_POLICY_ID
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .red_forward_controller_batch import (
    CONTROLLER_RETURN_CONTRACT,
    load_red_forward_controller_batch,
)
from .red_forward_goal import (
    RED_FORWARD_CONTEXT_NAMES,
    RED_FORWARD_EXECUTION_FLAGS,
    red_forward_continuation_sha256,
    red_forward_execution_flags,
    red_forward_verifier_sha256,
)


@dataclass(frozen=True, slots=True)
class RedForwardProbeSpec:
    model: ForwardGoalModel
    fitted_plan: ForwardGoalPlan
    fit_record_sha256: str
    tail_model_sha256: str
    tail_policy_id: str
    tail_seed: int
    objective_id: str
    profile_sha256: str
    fitted_source_bundle_sha256: str
    execution_flags: tuple[tuple[str, bool], ...]
    fit_contract: str = "complete-forward.v1"

    def __post_init__(self) -> None:
        if (
            self.model.contract != self.fitted_plan.contract
            or self.fitted_plan.goal_family != "red-story-objective"
            or self.model.context_names != RED_FORWARD_CONTEXT_NAMES
            or self.model.candidate_names != option_feature_names(3)
            or self.model.public_dict()["authority"] != "unqualified-shadow"
            or self.fitted_plan.max_macros != 2
            or self.tail_policy_id != RECOVERY_EXPLORATION_POLICY_ID
            or type(self.tail_seed) is not int
            or self.tail_seed < 0
            or self.fit_contract not in {"complete-forward.v1", CONTROLLER_RETURN_CONTRACT}
            or self.fitted_plan.verifier_sha256 != red_forward_verifier_sha256(self.objective_id)
        ):
            raise ValueError("forward probe model/tail contract differs")
        if any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (
                self.fit_record_sha256,
                self.tail_model_sha256,
                self.profile_sha256,
                self.fitted_source_bundle_sha256,
            )
        ):
            raise ValueError("forward probe provenance digest differs")
        flags = dict(self.execution_flags)
        if len(flags) != len(self.execution_flags) or tuple(flags) != RED_FORWARD_EXECUTION_FLAGS:
            raise ValueError("forward probe execution flags differ")
        if self.fitted_plan.continuation_sha256 != red_forward_continuation_sha256(
            behavior_policy_id=self.tail_policy_id,
            model_sha256=self.tail_model_sha256,
            source_bundle_sha256=self.fitted_source_bundle_sha256,
            profile_sha256=self.profile_sha256,
            execution_flags=flags,
        ):
            raise ValueError("forward probe fitted continuation differs")

    @property
    def policy_id(self) -> str:
        return f"red-forward-first-probe-{self.model.sha256[:16]}"

    def header(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.forward-first-choice-training-probe.v1",
            "first_actor_model_sha256": self.model.sha256,
            "fit_record_sha256": self.fit_record_sha256,
            "fit_contract": self.fit_contract,
            "fitted_plan": self.fitted_plan.public_dict(),
            "fitted_plan_sha256": self.fitted_plan.sha256,
            "fitted_source_bundle_sha256": self.fitted_source_bundle_sha256,
            "tail_model_sha256": self.tail_model_sha256,
            "tail_behavior_policy_id": self.tail_policy_id,
            "tail_seed": self.tail_seed,
            "tail_rng": "independently-seeded-at-first-tail-choice",
            "profile_sha256": self.profile_sha256,
            "execution_flags": dict(self.execution_flags),
            "objective_id": self.objective_id,
            "selector": "max-predicted-completion-then-min-cost-then-menu-index",
            "authority": "bounded-training-probe-not-production",
            "continuation_source_equivalence_claimed": False,
            "recursive_forward_control": False,
            "native_training_admission": False,
            "independent_evaluation": False,
            "calibrated_probabilities": False,
        }


def load_red_forward_probe(
    store: PrivateArtifactRoot,
    *,
    record_id: str,
    expected_record_sha256: str,
    expected_model_sha256: str,
    tail_seed: int,
) -> RedForwardProbeSpec:
    sealed = store.find_sealed_record(record_id, expected_kind="red_forward_goal_shadow_fit")
    if sealed is None or sealed.summary.record_sha256 != expected_record_sha256:
        raise ValueError("forward probe fit record authentication differs")
    doc = sealed.read()
    if (
        doc.get("schema") != "pokemon.red.forward-goal-shadow-fit.v1"
        or record_id != f"red-forward-fit-{canonical_sha256(doc)}"
        or doc.get("authority") != "unqualified-shadow"
        or doc.get("player_model_changed") is not False
        or doc.get("independent_evaluation") is not False
    ):
        raise ValueError("forward probe fit authority differs")
    model = restore_forward_goal_model(doc["model"])
    if model.sha256 != expected_model_sha256 or doc.get("model_sha256") != model.sha256:
        raise ValueError("forward probe model identity differs")
    outcomes = doc.get("outcomes")
    episodes = doc.get("episodes")
    if (
        not isinstance(outcomes, list)
        or not outcomes
        or not isinstance(episodes, list)
        or not episodes
    ):
        raise ValueError("forward probe fit has no native evidence")
    rows = tuple(restore_forward_goal_outcome(row) for row in outcomes)
    plan = rows[0].plan
    if any(row.plan != plan or row.choice.partition != "train" for row in rows):
        raise ValueError("forward probe fitted batch contract differs")
    first = cast(Mapping[str, Any], episodes[0])
    reader = store.open_episode(first["episode_id"])
    if reader.manifest_sha256 != first["manifest_sha256"]:
        raise ValueError("forward probe fitted episode changed")
    metadata = cast(Mapping[str, Any], reader.read_header()["metadata"])
    native = metadata["player_training_plan"]
    if (
        metadata.get("forward_goal_plan_sha256") != plan.sha256
        or first.get("training_plan_sha256") != canonical_sha256(native)
        or native["model_sha256"] != doc.get("behavior_model_sha256")
    ):
        raise ValueError("forward probe native continuation differs")
    return RedForwardProbeSpec(
        model,
        plan,
        expected_record_sha256,
        native["model_sha256"],
        native["behavior_policy_id"],
        tail_seed,
        metadata["forward_story_objective"],
        native["profile_sha256"],
        native["source_bundle_sha256"],
        tuple(red_forward_execution_flags(metadata).items()),
    )


def load_red_forward_controller_probe(
    store: PrivateArtifactRoot,
    *,
    record_id: str,
    expected_record_sha256: str,
    expected_model_sha256: str,
    behavior_model: LivingDexOptionValueModel,
    tail_seed: int,
) -> RedForwardProbeSpec:
    """Explicit bounded training use, after whole controller-batch readmission.

    This never falls back to the ordinary loader. The source that executes the
    probe is separately recorded; fitting does not establish calibrated support.
    """
    sealed = store.find_sealed_record(record_id, expected_kind="red_forward_controller_shadow_fit")
    if sealed is None or sealed.summary.record_sha256 != expected_record_sha256:
        raise ValueError("controller probe fit record authentication differs")
    doc = sealed.read()
    if (
        doc.get("schema") != "pokemon.red.forward-controller-shadow-fit.v1"
        or record_id != f"red-ctrl-fit-{canonical_sha256(doc)}"
        or doc.get("return_contract") != CONTROLLER_RETURN_CONTRACT
        or doc.get("authority") != "unqualified-shadow"
        or doc.get("player_model_changed") is not False
        or doc.get("independent_evaluation") is not False
        or doc.get("in_game_loss_inferred") is not False
        or doc.get("behavior_model_sha256") != behavior_model.model_sha256
    ):
        raise ValueError("controller probe fitted authority differs")
    model = restore_forward_goal_model(doc["model"])
    if model.sha256 != expected_model_sha256 or doc.get("model_sha256") != model.sha256:
        raise ValueError("controller probe model identity differs")
    batch = load_red_forward_controller_batch(
        store,
        batch_record_id=cast(str, doc.get("batch_record_id")),
        expected_batch_record_sha256=cast(str, doc.get("batch_record_sha256")),
        behavior_model=behavior_model,
    )
    rows = tuple(sorted(batch.outcomes, key=lambda row: row.choice.decision_sha256))
    public = [row.public_dict() for row in rows]
    if (
        doc.get("outcomes") != public
        or model.dataset_sha256
        != canonical_sha256({"schema": "pokemon.core.forward-goal-dataset.v1", "outcomes": public})
        or doc.get("episodes")
        != sorted(batch.episode_requests, key=lambda row: str(row["episode_id"]))
        or doc.get("cancelled_episode_ids") != list(batch.cancelled_episode_ids)
        or type(doc.get("failed_controller_stops")) is not int
        or doc["failed_controller_stops"] != batch.failed_stops
        or model.settled_examples != sum(row.target is not None for row in rows)
        or model.censored_examples != sum(row.target is None for row in rows)
    ):
        raise ValueError("controller probe fit differs from its entire admitted batch")
    complete = [row for row in batch.episode_requests if row["status"] == "complete"]
    if not complete:
        raise ValueError("controller probe lacks a complete originating episode")
    reader = store.open_episode(cast(str, complete[0]["episode_id"]))
    if reader.manifest_sha256 != complete[0]["manifest_sha256"]:
        raise ValueError("controller probe origin changed after admission")
    metadata = cast(Mapping[str, Any], reader.read_header()["metadata"])
    native = metadata["player_training_plan"]
    return RedForwardProbeSpec(
        model,
        rows[0].plan,
        expected_record_sha256,
        native["model_sha256"],
        native["behavior_policy_id"],
        tail_seed,
        metadata["forward_story_objective"],
        native["profile_sha256"],
        native["source_bundle_sha256"],
        tuple(red_forward_execution_flags(metadata).items()),
        CONTROLLER_RETURN_CONTRACT,
    )
