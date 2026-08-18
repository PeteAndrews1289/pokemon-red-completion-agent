"""Repeatable, outcome-bearing development episodes for the portable goal manager.

This is the fast learning loop that sits between supervised teacher collection and sealed
evaluation.  A frozen model distribution is mixed with a small, declared exploration mass,
the sampled semantic goal is durably recorded before controller input, and an independent
verifier supplies the outcome.  Capture resets are development data, not unseen contexts.
"""

from __future__ import annotations

import hashlib
import math
import re
import stat
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import cast

import numpy as np

from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerQuestion,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_ACTIONS_PER_DECISION,
    FRESH_COMPOSITION_FRAMES_PER_DECISION,
    FRESH_COMPOSITION_MAX_ACTIONS,
    FRESH_COMPOSITION_MAX_FRAMES,
    CompositionBudgetMeter,
    GoalManagerCompositionError,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerScorer,
    canonical_goal_manager_model_record_sha256,
)
from pokemon_red_completion.goal_manager_runtime import execute_goal_manager_decision
from pokemon_red_completion.goal_manager_trajectory import (
    CollectedGoalManagerDataset,
    GoalEpisodeReader,
    GoalManagerTrajectoryError,
    GoalManagerTrajectoryObserver,
    load_goal_manager_episode,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    RED_SOLO_COLLECTION_CONTRACT,
)

DEVELOPMENT_BEHAVIOR_POLICY_ID = "pokemon.core.goal-manager.exploratory-softmax.v1"
DEVELOPMENT_EXPLORATION_MIX = 0.15
DEVELOPMENT_TEMPERATURE = 1.0
DEVELOPMENT_MAX_DECISIONS = 3
DEVELOPMENT_OUTCOME_OBJECTIVE_ID = (
    "pokemon.core.goal-manager.selected-outcome-objective.v1"
)
DEVELOPMENT_MAX_IMPORTANCE_WEIGHT = 4.0
DEVELOPMENT_CAMPAIGN_TRIALS = 12
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ROOT_LINEAGE = re.compile(r"red-goal-root-[0-9a-f]{64}\Z")


class GoalManagerDevelopmentError(RuntimeError):
    """Raised when a repeatable development episode crosses its declared boundary."""


def goal_manager_development_contract() -> dict[str, object]:
    """Return the one canonical episode-header contract for collection and admission."""

    return {
        "exploration_mix": DEVELOPMENT_EXPLORATION_MIX,
        "maximum_importance_weight": DEVELOPMENT_MAX_IMPORTANCE_WEIGHT,
        "maximum_decisions": DEVELOPMENT_MAX_DECISIONS,
        "outcome_objective_id": DEVELOPMENT_OUTCOME_OBJECTIVE_ID,
        "repeatable_capture": True,
        "temperature": DEVELOPMENT_TEMPERATURE,
        "teacher_fallbacks": 0,
        "teacher_queries": 0,
    }


def goal_manager_development_outcome_objective() -> dict[str, object]:
    """Return the frozen reward and propensity-weighting objective."""

    return {
        "failure_reward": -1.0,
        "interrupted_target": "retained_without_update",
        "maximum_importance_weight": DEVELOPMENT_MAX_IMPORTANCE_WEIGHT,
        "objective_id": DEVELOPMENT_OUTCOME_OBJECTIVE_ID,
        "success_reward": 1.0,
    }


def goal_manager_development_numpy_runtime_sha256() -> str:
    """Hash every installed NumPy package byte that can affect policy sampling."""

    # Force the exact numerical and RNG surfaces used by the behavior policy to load
    # before the origin census, so a later lazy import cannot evade the inventory.
    np.exp(np.asarray([0.0], dtype=np.float64))
    np.random.default_rng(0).choice(1, p=np.asarray([1.0], dtype=np.float64))
    try:
        distribution = metadata.distribution("numpy")
    except metadata.PackageNotFoundError:
        raise GoalManagerDevelopmentError(
            "development NumPy distribution is unavailable"
        ) from None
    version = distribution.version
    if (
        not isinstance(version, str)
        or not version
        or not version.isascii()
        or "\n" in version
        or np.__version__ != version
    ):
        raise GoalManagerDevelopmentError("development NumPy version is invalid")
    raw_files = distribution.files
    if raw_files is None:
        raise GoalManagerDevelopmentError(
            "development NumPy inventory is unavailable"
        )
    rows: list[dict[str, object]] = []
    resolved_files: set[Path] = set()
    dist_info_root = f"numpy-{version}.dist-info"
    try:
        entries = tuple(raw_files)
    except (OSError, TypeError):
        raise GoalManagerDevelopmentError(
            "development NumPy inventory is unavailable"
        ) from None
    if not 1 <= len(entries) <= 20_000:
        raise GoalManagerDevelopmentError("development NumPy inventory is invalid")
    total_bytes = 0
    for entry in entries:
        name = str(entry)
        root = name.split("/", 1)[0]
        if root not in {"numpy", "numpy.libs", dist_info_root}:
            continue
        if (
            not name.isascii()
            or name.startswith("/")
            or any(part in {"", ".", ".."} for part in name.split("/"))
        ):
            raise GoalManagerDevelopmentError(
                "development NumPy inventory name is invalid"
            )
        path = Path(str(distribution.locate_file(entry)))
        try:
            file_metadata = path.lstat()
            resolved = path.resolve(strict=True)
            payload = path.read_bytes()
        except OSError:
            raise GoalManagerDevelopmentError(
                "development NumPy file cannot be authenticated"
            ) from None
        if path.is_symlink() or not stat.S_ISREG(file_metadata.st_mode):
            raise GoalManagerDevelopmentError(
                "development NumPy file is not regular"
            )
        total_bytes += len(payload)
        if total_bytes > 2 * 1024 * 1024 * 1024:
            raise GoalManagerDevelopmentError(
                "development NumPy inventory is too large"
            )
        resolved_files.add(resolved)
        rows.append(
            {
                "bytes": len(payload),
                "name": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    loaded_origins: list[Path] = []
    for name, module in tuple(sys.modules.items()):
        if name != "numpy" and not name.startswith("numpy."):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            continue
        if not isinstance(module_file, str):
            raise GoalManagerDevelopmentError(
                "development NumPy import origin is invalid"
            )
        loaded_origins.append(Path(module_file).resolve(strict=True))
    if not rows or not loaded_origins or any(
        origin not in resolved_files for origin in loaded_origins
    ):
        raise GoalManagerDevelopmentError(
            "development NumPy import differs from its distribution"
        )
    rows.sort(key=lambda row: str(row["name"]))
    return canonical_sha256(
        {
            "distribution_name": "numpy",
            "distribution_version": version,
            "files": rows,
            "schema": "pokemon.core.goal-manager-numpy-runtime.v1",
        }
    )


def repeatable_goal_manager_trial_execution_identity(
    *,
    campaign_id: str,
    campaign_plan_sha256: str,
    model_canonical_sha256: str,
    numpy_runtime_sha256: str,
    root_lineage_id: str,
    runtime_sha256: str,
    source_commit: str,
    trial_index: int,
    trial_claim_sha256: str,
) -> str:
    """Return the one exact execution identity used by runner, claim, and admission."""

    for name, value in (
        ("campaign identity", campaign_id),
        ("campaign plan", campaign_plan_sha256),
        ("model", model_canonical_sha256),
        ("NumPy runtime", numpy_runtime_sha256),
        ("runtime", runtime_sha256),
        ("trial claim", trial_claim_sha256),
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise GoalManagerDevelopmentError(f"development {name} is invalid")
    if not isinstance(root_lineage_id, str) or _ROOT_LINEAGE.fullmatch(
        root_lineage_id
    ) is None:
        raise GoalManagerDevelopmentError("development root lineage is invalid")
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        raise GoalManagerDevelopmentError("development source commit is invalid")
    if type(trial_index) is not int or not (  # noqa: E721
        0 <= trial_index < DEVELOPMENT_CAMPAIGN_TRIALS
    ):
        raise GoalManagerDevelopmentError("development trial index is invalid")
    return canonical_sha256(
        {
            "campaign_id": campaign_id,
            "campaign_plan_sha256": campaign_plan_sha256,
            "model_canonical_sha256": model_canonical_sha256,
            "numpy_runtime_sha256": numpy_runtime_sha256,
            "root_lineage_id": root_lineage_id,
            "runtime_sha256": runtime_sha256,
            "source_commit": source_commit,
            "trial_index": trial_index,
            "trial_claim_sha256": trial_claim_sha256,
        }
    )


@dataclass(frozen=True, slots=True)
class GoalManagerDevelopmentTarget:
    """One prospective off-policy outcome target from a settled model-led choice."""

    decision_id: str
    selected_candidate_index: int
    reward: float
    behavior_probability: float
    importance_weight: float


@dataclass(frozen=True, slots=True)
class AdmittedGoalManagerDevelopmentEpisode:
    """One complete, durably terminated development episode and its frozen targets."""

    dataset: CollectedGoalManagerDataset
    stopped_reason: str
    composition: bool
    collection_relevant_outcomes: int
    successful_retained_acquisitions: int
    successful_specimen_preserving_storage: int
    targets: tuple[GoalManagerDevelopmentTarget, ...]

    @property
    def verified_outcomes(self) -> int:
        return len(self.dataset.examples)


@dataclass(slots=True)
class ExploratoryGoalManagerPolicy:
    """Sample from the learned distribution with logged, reproducible propensities."""

    model: GoalManagerScorer
    seed: int
    exploration_mix: float = DEVELOPMENT_EXPLORATION_MIX
    temperature: float = DEVELOPMENT_TEMPERATURE
    decisions: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)
    _last_metadata: dict[str, object] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:  # noqa: E721
            raise GoalManagerDevelopmentError("development seed must be non-negative")
        if (
            isinstance(self.exploration_mix, bool)
            or not isinstance(self.exploration_mix, (int, float))
            or not 0.0 < float(self.exploration_mix) < 1.0
        ):
            raise GoalManagerDevelopmentError(
                "development exploration mix must be between zero and one"
            )
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(float(self.temperature))
            or float(self.temperature) <= 0.0
        ):
            raise GoalManagerDevelopmentError("development temperature must be positive")
        self.exploration_mix = float(self.exploration_mix)
        self.temperature = float(self.temperature)
        self._rng = np.random.default_rng(self.seed)

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        base = np.asarray(self.model.probabilities(question), dtype=np.float64)
        if base.shape != (len(question.opportunities),) or not np.all(np.isfinite(base)):
            raise GoalManagerDevelopmentError("development model probabilities are invalid")
        available = np.asarray(question.available_indices, dtype=np.int64)
        if len(available) < 2:
            raise GoalManagerDevelopmentError(
                "development sampling requires at least two executable goals"
            )
        available_base = base[available]
        if np.any(available_base <= 0.0):
            raise GoalManagerDevelopmentError(
                "development model assigned no mass to an executable goal"
            )
        logits = np.log(available_base) / self.temperature
        tempered = np.exp(logits - np.max(logits))
        tempered /= np.sum(tempered)
        mixed = (1.0 - self.exploration_mix) * tempered + (
            self.exploration_mix / len(available)
        )
        mixed /= np.sum(mixed)
        position = int(self._rng.choice(len(available), p=mixed))
        selected_index = int(available[position])
        full = np.zeros(len(question.opportunities), dtype=np.float64)
        full[available] = mixed
        self._last_metadata = {
            "schema": "pokemon.core.goal-manager-behavior-policy.v1",
            "behavior_policy_id": DEVELOPMENT_BEHAVIOR_POLICY_ID,
            "candidate_probabilities": full.tolist(),
            "selected_probability": float(full[selected_index]),
            "base_selected_probability": float(base[selected_index]),
            "exploration_mix": self.exploration_mix,
            "temperature": self.temperature,
        }
        self.decisions += 1
        return bind_goal_selection(question, selected_index)

    def selection_metadata(self) -> Mapping[str, object]:
        if self._last_metadata is None:
            raise GoalManagerDevelopmentError(
                "development selection metadata is unavailable"
            )
        return dict(self._last_metadata)

    @property
    def model_sha256(self) -> str:
        return canonical_goal_manager_model_record_sha256(self.model.to_dict())


@dataclass(frozen=True, slots=True)
class GoalManagerDevelopmentStep:
    decision_ordinal: int
    selected_kind: GoalKind
    status: GoalDecisionOutcome
    behavior_probability: float
    base_probability: float
    available_goal_count: int
    actions_executed: int
    frames_executed: int
    semantic_state_changed: bool
    policy_context_sha256: str
    available_menu_sha256: str
    collection_before: LivingCollectionCheckpoint
    collection_after: LivingCollectionCheckpoint

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": self.actions_executed,
            "available_goal_count": self.available_goal_count,
            "available_menu_sha256": self.available_menu_sha256,
            "base_probability": self.base_probability,
            "behavior_probability": self.behavior_probability,
            "collection_after": _collection_evidence_dict(self.collection_after),
            "collection_before": _collection_evidence_dict(self.collection_before),
            "decision_ordinal": self.decision_ordinal,
            "frames_executed": self.frames_executed,
            "policy_context_sha256": self.policy_context_sha256,
            "selected_kind": self.selected_kind.value,
            "semantic_state_changed": self.semantic_state_changed,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerDevelopmentResult:
    model_sha256: str
    seed: int
    steps: tuple[GoalManagerDevelopmentStep, ...]
    policy_context_changes: int
    available_menu_changes: int
    stopped_reason: str

    @property
    def verified_outcomes(self) -> int:
        return len(self.steps)

    @property
    def is_composition(self) -> bool:
        return len(self.steps) >= 2 and self.policy_context_changes >= 1

    @property
    def collection_relevant_outcomes(self) -> int:
        return sum(
            step.selected_kind
            in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES, GoalKind.MANAGE_STORAGE}
            for step in self.steps
        )

    @property
    def successful_retained_acquisitions(self) -> int:
        return sum(
            step.status is GoalDecisionOutcome.SUCCEEDED
            and step.selected_kind is GoalKind.ACQUIRE_SPECIES
            for step in self.steps
        )

    @property
    def successful_specimen_preserving_storage(self) -> int:
        return sum(
            step.status is GoalDecisionOutcome.SUCCEEDED
            and step.selected_kind is GoalKind.MANAGE_STORAGE
            and step.collection_after.storage_headroom
            > step.collection_before.storage_headroom
            for step in self.steps
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "available_menu_changes": self.available_menu_changes,
            "collection_relevant_outcomes": self.collection_relevant_outcomes,
            "collection_relevant_selections": self.collection_relevant_outcomes,
            "composition": self.is_composition,
            "decisions": len(self.steps),
            "fixed_dispatches": 0,
            "model_sha256": self.model_sha256,
            "policy_context_changes": self.policy_context_changes,
            "schema": "pokemon.red.repeatable-goal-manager-development-result.v1",
            "seed": self.seed,
            "selected_goal_kinds": [step.selected_kind.value for step in self.steps],
            "status": "durable_terminal",
            "steps": [step.public_dict() for step in self.steps],
            "stopped_reason": self.stopped_reason,
            "successful_retained_acquisitions": self.successful_retained_acquisitions,
            "successful_specimen_preserving_storage": (
                self.successful_specimen_preserving_storage
            ),
            "teacher_fallbacks": 0,
            "teacher_queries": 0,
            "verified_outcomes": self.verified_outcomes,
        }


def run_repeatable_goal_manager_development_episode(
    *,
    observe: Callable[[], GoalManagerCompositionObservation],
    policy: ExploratoryGoalManagerPolicy,
    trajectory: GoalManagerTrajectoryObserver,
    budget_meter: CompositionBudgetMeter,
    maximum_decisions: int = DEVELOPMENT_MAX_DECISIONS,
) -> GoalManagerDevelopmentResult:
    """Collect one to three settled, model-led outcomes on a continuing Red state."""

    if not callable(observe):
        raise TypeError("observe must be callable")
    if not isinstance(policy, ExploratoryGoalManagerPolicy):
        raise TypeError("policy must be an ExploratoryGoalManagerPolicy")
    if not isinstance(trajectory, GoalManagerTrajectoryObserver):
        raise TypeError("trajectory must be a GoalManagerTrajectoryObserver")
    if not isinstance(budget_meter, CompositionBudgetMeter):
        raise TypeError("budget_meter must be a CompositionBudgetMeter")
    if type(maximum_decisions) is not int or not 1 <= maximum_decisions <= 3:  # noqa: E721
        raise GoalManagerDevelopmentError("development decision bound must be one to three")
    if policy.decisions != 0 or trajectory.next_decision_index != 0:
        raise GoalManagerDevelopmentError("development episode must start unused")

    initial_budget = budget_meter.checkpoint()
    current = _observation(observe())
    if budget_meter.checkpoint() != initial_budget:
        raise GoalManagerDevelopmentError("development observation attempted emulator work")
    last_budget = initial_budget
    steps: list[GoalManagerDevelopmentStep] = []
    contexts: list[str] = []
    menus: list[str] = []
    stopped_reason = "decision_limit"

    for decision_index in range(maximum_decisions):
        question = trajectory.ordered_question(
            current.situation,
            current.binding_set.opportunities,
        )
        if len(question.available_indices) < 2:
            if not steps:
                raise GoalManagerDevelopmentError(
                    "development root has fewer than two executable goals"
                )
            stopped_reason = "menu_became_singleton"
            break
        if any(
            question.opportunities[index].kind is GoalKind.EVOLVE_SPECIES
            for index in question.available_indices
        ):
            raise GoalManagerDevelopmentError(
                "development evolution requires retained lineage evidence"
            )
        execution = execute_goal_manager_decision(
            situation=current.situation,
            binding_set=current.binding_set,
            authority=policy,
            trajectory=trajectory,
            require_durable_decision=True,
        )
        if not execution.decision_recorded or not execution.outcome_recorded:
            raise GoalManagerDevelopmentError(
                "development decision or outcome was not durably recorded"
            )
        if execution.execution is None:
            raise GoalManagerDevelopmentError("development execution report is absent")
        metadata = policy.selection_metadata()
        selected_probability = _metadata_probability(
            metadata.get("selected_probability"),
            subject="selected behavior probability",
            positive=True,
        )
        base_probability = _metadata_probability(
            metadata.get("base_selected_probability"),
            subject="selected base probability",
            positive=False,
        )
        after = _observation(observe())
        after_budget = budget_meter.checkpoint()
        actions = after_budget.controller_actions - last_budget.controller_actions
        frames = after_budget.emulator_frames - last_budget.emulator_frames
        if actions < 0 or frames < 0:
            raise GoalManagerDevelopmentError("development budget counters regressed")
        if (
            actions != execution.execution.actions_executed
            or frames != execution.execution.frames_executed
        ):
            raise GoalManagerDevelopmentError(
                "development report differs from independent budget accounting"
            )
        require_living_collection_transition(
            current.collection,
            after.collection,
            selected_kind=execution.selected_kind,
            require_selected_goal_progress=execution.passed,
        )
        changed = after.semantic_state_sha256 != current.semantic_state_sha256
        if execution.passed and not changed:
            raise GoalManagerDevelopmentError(
                "successful development skill did not change semantic state"
            )
        steps.append(
            GoalManagerDevelopmentStep(
                decision_ordinal=decision_index + 1,
                selected_kind=execution.selected_kind,
                status=execution.verification.status,
                behavior_probability=selected_probability,
                base_probability=base_probability,
                available_goal_count=len(question.available_indices),
                actions_executed=actions,
                frames_executed=frames,
                semantic_state_changed=changed,
                policy_context_sha256=question.policy_context_sha256,
                available_menu_sha256=question.available_menu_sha256,
                collection_before=current.collection,
                collection_after=after.collection,
            )
        )
        contexts.append(question.policy_context_sha256)
        menus.append(question.available_menu_sha256)
        current = after
        last_budget = after_budget
        if not execution.passed:
            stopped_reason = "verified_failure"
            break

    trajectory.require_settled()
    if not steps:
        raise GoalManagerDevelopmentError("development episode produced no outcome")
    return GoalManagerDevelopmentResult(
        model_sha256=policy.model_sha256,
        seed=policy.seed,
        steps=tuple(steps),
        policy_context_changes=sum(
            left != right for left, right in zip(contexts, contexts[1:], strict=False)
        ),
        available_menu_changes=sum(
            left != right for left, right in zip(menus, menus[1:], strict=False)
        ),
        stopped_reason=stopped_reason,
    )


def load_repeatable_goal_manager_development_episode(
    reader: GoalEpisodeReader,
    *,
    expected_campaign_id: str,
    expected_trial_claim_sha256: str,
    expected_episode_id: str,
    expected_root_lineage_id: str,
    expected_seed: int,
    expected_execution_identity_sha256: str,
    expected_context_catalog_sha256: str,
    expected_context_id: str,
    expected_binding_manifest_sha256: str,
    expected_state_sha256: str,
    expected_envelope_sha256: str,
    expected_first_question_sha256: str,
    expected_first_policy_context_sha256: str,
    expected_first_available_menu_sha256: str,
    expected_model: GoalManagerScorer,
    expected_source_commit: str,
) -> AdmittedGoalManagerDevelopmentEpisode:
    """Admit one complete episode without turning failures into teacher labels.

    The objective is frozen before collection: settled success reinforces the sampled
    semantic choice, settled failure penalizes it, and interrupted choices are retained
    but do not become update targets.  The selected-action loss is inverse-propensity
    weighted with a fixed cap; candidate probabilities remain in the durable decision.
    """

    try:
        dataset = load_goal_manager_episode(reader)
    except GoalManagerTrajectoryError as error:
        raise GoalManagerDevelopmentError(str(error)) from error
    if (
        dataset.partition != "development"
        or dataset.actor != "exploratory_goal_manager"
        or dataset.policy_id != "red-goal-manager-outcome-development-v1"
        or dataset.environment_id != RED_COLLECTION_GAME_ID
        or dataset.collection_id != expected_campaign_id
        or dataset.assignment_id != expected_trial_claim_sha256
        or dataset.episode_id != expected_episode_id
        or dataset.root_lineage_id != expected_root_lineage_id
        or dataset.context_catalog_sha256 != expected_context_catalog_sha256
        or dataset.context_id != expected_context_id
        or dataset.binding_manifest_sha256 != expected_binding_manifest_sha256
        or dataset.capture_state_sha256 != expected_state_sha256
        or dataset.capture_envelope_sha256 != expected_envelope_sha256
        or dataset.source_commit != expected_source_commit
        or not 1 <= len(dataset.examples) <= DEVELOPMENT_MAX_DECISIONS
    ):
        raise GoalManagerDevelopmentError("development episode provenance differs")
    first_question = dataset.examples[0].question
    if (
        first_question.ordered_policy_input_sha256 != expected_first_question_sha256
        or first_question.policy_context_sha256
        != expected_first_policy_context_sha256
        or first_question.available_menu_sha256
        != expected_first_available_menu_sha256
    ):
        raise GoalManagerDevelopmentError("development frozen first question differs")
    expected_model_sha256 = canonical_goal_manager_model_record_sha256(
        expected_model.to_dict()
    )
    if any(
        example.behavior_policy_id != DEVELOPMENT_BEHAVIOR_POLICY_ID
        or example.behavior_probability is None
        or example.behavior_exploration_mix != DEVELOPMENT_EXPLORATION_MIX
        or example.behavior_temperature != DEVELOPMENT_TEMPERATURE
        for example in dataset.examples
    ):
        raise GoalManagerDevelopmentError(
            "development episode lacks authenticated behavior propensities"
        )
    if any(
        example.decision_id
        != f"{expected_episode_id}:goal-manager:{example.decision_index}"
        for example in dataset.examples
    ):
        raise GoalManagerDevelopmentError("development decision identity differs")
    if any(
        example.selected_kind is GoalKind.EVOLVE_SPECIES
        for example in dataset.examples
    ):
        raise GoalManagerDevelopmentError(
            "development episode selected an unsupported evolution goal"
        )
    replay = ExploratoryGoalManagerPolicy(expected_model, seed=expected_seed)
    for example in dataset.examples:
        replayed = replay.select(example.question)
        replay_metadata = replay.selection_metadata()
        if (
            replayed.selected_index != example.selected_candidate_index
            or replay_metadata.get("behavior_policy_id")
            != example.behavior_policy_id
            or replay_metadata.get("selected_probability")
            != example.behavior_probability
            or tuple(cast(list[float], replay_metadata.get("candidate_probabilities")))
            != example.behavior_candidate_probabilities
            or replay_metadata.get("base_selected_probability")
            != example.behavior_base_probability
            or replay_metadata.get("exploration_mix")
            != example.behavior_exploration_mix
            or replay_metadata.get("temperature") != example.behavior_temperature
        ):
            raise GoalManagerDevelopmentError(
                "development behavior policy does not replay exactly"
            )

    header = _mapping(reader.read_header(), subject="development episode header")
    metadata = _mapping(header.get("metadata"), subject="development episode metadata")
    goal_metadata = _mapping(
        metadata.get("goal_manager"),
        subject="development goal-manager metadata",
    )
    if (
        goal_metadata.get("execution_identity_sha256")
        != expected_execution_identity_sha256
    ):
        raise GoalManagerDevelopmentError(
            "development execution identity differs"
        )
    development = _mapping(
        metadata.get("development"),
        subject="development episode contract",
    )
    if development != goal_manager_development_contract():
        raise GoalManagerDevelopmentError("development episode contract differs")

    terminals = [
        _mapping(row, subject="development terminal")
        for row in reader.iter_stream("events")
        if row.get("kind") == "terminal"
    ]
    if len(terminals) != 1:
        raise GoalManagerDevelopmentError(
            "development episode needs exactly one durable terminal"
        )
    terminal = terminals[0]
    terminal_step_index = terminal.get("step_index")
    if (
        terminal.get("event_id") != f"{expected_episode_id}:terminal"
        or terminal.get("episode_id") != expected_episode_id
        or type(terminal_step_index) is not int
        or terminal_step_index < 0
    ):
        raise GoalManagerDevelopmentError("development terminal identity differs")
    terminal_payload = _mapping(
        terminal.get("payload"),
        subject="development terminal payload",
    )
    if terminal_payload.get("status") != "complete":
        raise GoalManagerDevelopmentError("development terminal is not complete")
    result = _mapping(
        terminal_payload.get("development"),
        subject="development terminal result",
    )
    selected_kinds = [example.selected_kind.value for example in dataset.examples]
    if (
        result.get("schema")
        != "pokemon.red.repeatable-goal-manager-development-result.v1"
        or result.get("status") != "durable_terminal"
        or result.get("model_sha256") != expected_model_sha256
        or result.get("decisions") != len(dataset.examples)
        or result.get("verified_outcomes") != len(dataset.examples)
        or result.get("selected_goal_kinds") != selected_kinds
        or result.get("teacher_queries") != 0
        or result.get("teacher_fallbacks") != 0
        or result.get("fixed_dispatches") != 0
        or result.get("seed") != expected_seed
    ):
        raise GoalManagerDevelopmentError("development terminal result differs")
    steps = result.get("steps")
    if not isinstance(steps, list) or len(steps) != len(dataset.examples):
        raise GoalManagerDevelopmentError("development terminal steps differ")
    collection_transitions: list[
        tuple[LivingCollectionCheckpoint, LivingCollectionCheckpoint]
    ] = []
    for example, raw_step in zip(dataset.examples, steps, strict=True):
        step = _mapping(raw_step, subject="development terminal step")
        if (
            step.get("decision_ordinal") != example.decision_index + 1
            or step.get("selected_kind") != example.selected_kind.value
            or step.get("status") != example.outcome_status.value
            or step.get("behavior_probability") != example.behavior_probability
            or step.get("base_probability") != example.behavior_base_probability
        ):
            raise GoalManagerDevelopmentError("development terminal step differs")
        before_collection = _collection_checkpoint(
            step.get("collection_before"),
            subject="development collection before",
        )
        after_collection = _collection_checkpoint(
            step.get("collection_after"),
            subject="development collection after",
        )
        try:
            require_living_collection_transition(
                before_collection,
                after_collection,
                selected_kind=example.selected_kind,
                require_selected_goal_progress=(
                    example.outcome_status is GoalDecisionOutcome.SUCCEEDED
                ),
            )
        except GoalManagerCompositionError as error:
            raise GoalManagerDevelopmentError(
                "development collection transition differs"
            ) from error
        if (
            collection_transitions
            and collection_transitions[-1][1] != before_collection
        ):
            raise GoalManagerDevelopmentError(
                "development collection continuity differs"
            )
        collection_transitions.append((before_collection, after_collection))

    execution_rows = [
        _mapping(row, subject="development execution")
        for row in reader.iter_stream("executions")
    ]
    execution_frames = [
        _integer_field(row, "frames", subject="development execution")
        for row in execution_rows
    ]
    if any(
        row.get("episode_id") != dataset.episode_id
        or row.get("status") != "success"
        for row in execution_rows
    ):
        raise GoalManagerDevelopmentError("development execution stream differs")
    step_actions = [
        _integer_field(step, "actions_executed", subject="development terminal step")
        for step in steps
    ]
    step_frames = [
        _integer_field(step, "frames_executed", subject="development terminal step")
        for step in steps
    ]
    if (
        any(value > FRESH_COMPOSITION_ACTIONS_PER_DECISION for value in step_actions)
        or any(value > FRESH_COMPOSITION_FRAMES_PER_DECISION for value in step_frames)
        or sum(step_actions) > FRESH_COMPOSITION_MAX_ACTIONS
        or sum(step_frames) > FRESH_COMPOSITION_MAX_FRAMES
        or sum(step_actions) != len(execution_rows)
        or sum(step_frames) != sum(execution_frames)
        or terminal_step_index != len(execution_rows)
    ):
        raise GoalManagerDevelopmentError("development budget evidence differs")

    policy_contexts = [
        example.question.policy_context_sha256 for example in dataset.examples
    ]
    expected_composition = len(dataset.examples) >= 2 and any(
        left != right
        for left, right in zip(policy_contexts, policy_contexts[1:], strict=False)
    )
    if result.get("composition") is not expected_composition:
        raise GoalManagerDevelopmentError("development composition claim differs")
    collection_relevant = sum(
        kind
        in {
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.EVOLVE_SPECIES.value,
            GoalKind.MANAGE_STORAGE.value,
        }
        for kind in selected_kinds
    )
    if result.get("collection_relevant_outcomes") != collection_relevant:
        raise GoalManagerDevelopmentError(
            "development collection-outcome count differs"
        )
    if result.get("collection_relevant_selections") != collection_relevant:
        raise GoalManagerDevelopmentError(
            "development collection-selection count differs"
        )
    successful_retained_acquisitions = sum(
        example.outcome_status is GoalDecisionOutcome.SUCCEEDED
        and example.selected_kind is GoalKind.ACQUIRE_SPECIES
        for example in dataset.examples
    )
    successful_storage = 0
    for example, transition in zip(dataset.examples, collection_transitions, strict=True):
        if (
            example.outcome_status is GoalDecisionOutcome.SUCCEEDED
            and example.selected_kind is GoalKind.MANAGE_STORAGE
        ):
            before_collection, after_collection = transition
            if after_collection.storage_headroom > before_collection.storage_headroom:
                successful_storage += 1
    if (
        result.get("successful_retained_acquisitions")
        != successful_retained_acquisitions
        or result.get("successful_specimen_preserving_storage")
        != successful_storage
    ):
        raise GoalManagerDevelopmentError(
            "development successful collection evidence differs"
        )
    stopped_reason = result.get("stopped_reason")
    if stopped_reason not in {
        "decision_limit",
        "menu_became_singleton",
        "verified_failure",
    }:
        raise GoalManagerDevelopmentError("development stop reason differs")
    expected_stop_reason = (
        "verified_failure"
        if dataset.examples[-1].outcome_status is not GoalDecisionOutcome.SUCCEEDED
        else "decision_limit"
        if len(dataset.examples) == DEVELOPMENT_MAX_DECISIONS
        else "menu_became_singleton"
    )
    if stopped_reason != expected_stop_reason:
        raise GoalManagerDevelopmentError("development stop reason is not derived")

    targets: list[GoalManagerDevelopmentTarget] = []
    for example in dataset.examples:
        if example.outcome_status is GoalDecisionOutcome.INTERRUPTED:
            continue
        raw_probability = example.behavior_probability
        if raw_probability is None:  # Proven above; retain a local type-safe guard.
            raise GoalManagerDevelopmentError(
                "development behavior probability disappeared"
            )
        probability = float(raw_probability)
        targets.append(
            GoalManagerDevelopmentTarget(
                decision_id=example.decision_id,
                selected_candidate_index=example.selected_candidate_index,
                reward=(
                    1.0
                    if example.outcome_status is GoalDecisionOutcome.SUCCEEDED
                    else -1.0
                ),
                behavior_probability=probability,
                importance_weight=min(
                    DEVELOPMENT_MAX_IMPORTANCE_WEIGHT,
                    1.0 / probability,
                ),
            )
        )
    return AdmittedGoalManagerDevelopmentEpisode(
        dataset=dataset,
        stopped_reason=stopped_reason,
        composition=expected_composition,
        collection_relevant_outcomes=collection_relevant,
        successful_retained_acquisitions=successful_retained_acquisitions,
        successful_specimen_preserving_storage=successful_storage,
        targets=tuple(targets),
    )


def _observation(value: object) -> GoalManagerCompositionObservation:
    if not isinstance(value, GoalManagerCompositionObservation):
        raise GoalManagerDevelopmentError(
            "development observer returned an invalid observation"
        )
    return value


def _metadata_probability(value: object, *, subject: str, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalManagerDevelopmentError(f"development {subject} is invalid")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0 or (
        positive and result == 0.0
    ):
        raise GoalManagerDevelopmentError(f"development {subject} is invalid")
    return result


def _collection_evidence_dict(
    checkpoint: LivingCollectionCheckpoint,
) -> dict[str, object]:
    result = checkpoint.public_dict()
    result["specimen_counts"] = [list(item) for item in checkpoint.specimen_counts]
    return result


def _collection_checkpoint(
    value: object,
    *,
    subject: str,
) -> LivingCollectionCheckpoint:
    raw = _mapping(value, subject=subject)
    expected_keys = {
        "completion_contract_sha256",
        "living_species",
        "registered_species",
        "required_specimens_remaining",
        "required_specimens_sha256",
        "retained_captures",
        "specimen_counts",
        "specimen_ledger_sha256",
        "storage_headroom",
        "total_living_specimens",
        "undeclared_specimen_losses",
    }
    counts = raw.get("specimen_counts")
    if set(raw) != expected_keys or not isinstance(counts, list):
        raise GoalManagerDevelopmentError(f"{subject} is invalid")
    parsed_counts: list[tuple[str, int]] = []
    for item in counts:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or type(item[1]) is not int  # noqa: E721
        ):
            raise GoalManagerDevelopmentError(f"{subject} specimen counts are invalid")
        parsed_counts.append((item[0], item[1]))
    digest_fields: dict[str, str] = {}
    for key in (
        "completion_contract_sha256",
        "specimen_ledger_sha256",
        "required_specimens_sha256",
    ):
        digest = raw.get(key)
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise GoalManagerDevelopmentError(f"{subject} {key} is invalid")
        digest_fields[key] = digest
    try:
        checkpoint = LivingCollectionCheckpoint(
            registered_species=_integer_field(
                raw,
                "registered_species",
                subject=subject,
            ),
            living_species=_integer_field(raw, "living_species", subject=subject),
            required_specimens_remaining=_integer_field(
                raw,
                "required_specimens_remaining",
                subject=subject,
            ),
            retained_captures=_integer_field(
                raw,
                "retained_captures",
                subject=subject,
            ),
            storage_headroom=_integer_field(
                raw,
                "storage_headroom",
                subject=subject,
            ),
            undeclared_specimen_losses=_integer_field(
                raw,
                "undeclared_specimen_losses",
                subject=subject,
            ),
            completion_contract_sha256=digest_fields[
                "completion_contract_sha256"
            ],
            specimen_ledger_sha256=digest_fields["specimen_ledger_sha256"],
            required_specimens_sha256=digest_fields[
                "required_specimens_sha256"
            ],
            specimen_counts=tuple(parsed_counts),
        )
    except GoalManagerCompositionError as error:
        raise GoalManagerDevelopmentError(f"{subject} is invalid") from error
    specimens = dict(checkpoint.specimen_counts)
    required = RED_ACQUISITION_CATALOG.required_root_acquisitions()
    remaining = {
        species: required_count - specimens.get(species, 0)
        for species, required_count in required.items()
        if required_count > specimens.get(species, 0)
    }
    retained = sum(
        min(required_count, specimens.get(species, 0))
        for species, required_count in required.items()
    )
    expected_contract = canonical_sha256(
        {
            "schema": "pokemon.core.living-collection-contract.v1",
            "game_id": RED_COLLECTION_GAME_ID,
            "registered_target": sorted(RED_SOLO_COLLECTION_CONTRACT.target_species),
            "living_target": sorted(
                RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
            ),
            "required_root_acquisitions": dict(sorted(required.items())),
        }
    )
    expected_ledger = canonical_sha256(
        {
            "schema": "pokemon.core.living-specimen-ledger.v1",
            "specimens": dict(sorted(specimens.items())),
        }
    )
    expected_required = canonical_sha256(
        {
            "schema": "pokemon.core.remaining-required-specimens.v1",
            "remaining": dict(sorted(remaining.items())),
        }
    )
    expected_living_species = sum(
        species in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
        for species in specimens
    )
    if (
        _integer_field(raw, "total_living_specimens", subject=subject)
        != sum(specimens.values())
        or checkpoint.specimen_ledger_sha256 != expected_ledger
        or checkpoint.required_specimens_sha256 != expected_required
        or checkpoint.required_specimens_remaining != sum(remaining.values())
        or checkpoint.retained_captures != retained
        or checkpoint.completion_contract_sha256 != expected_contract
        or checkpoint.living_species != expected_living_species
    ):
        raise GoalManagerDevelopmentError(f"{subject} derived evidence differs")
    return checkpoint


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoalManagerDevelopmentError(f"{subject} is invalid")
    return value


def _integer_field(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise GoalManagerDevelopmentError(f"{subject} {key} is invalid")
    return value


__all__ = [
    "DEVELOPMENT_BEHAVIOR_POLICY_ID",
    "DEVELOPMENT_CAMPAIGN_TRIALS",
    "DEVELOPMENT_EXPLORATION_MIX",
    "DEVELOPMENT_MAX_DECISIONS",
    "DEVELOPMENT_MAX_IMPORTANCE_WEIGHT",
    "DEVELOPMENT_OUTCOME_OBJECTIVE_ID",
    "DEVELOPMENT_TEMPERATURE",
    "ExploratoryGoalManagerPolicy",
    "AdmittedGoalManagerDevelopmentEpisode",
    "GoalManagerDevelopmentError",
    "GoalManagerDevelopmentResult",
    "GoalManagerDevelopmentStep",
    "GoalManagerDevelopmentTarget",
    "goal_manager_development_contract",
    "goal_manager_development_outcome_objective",
    "load_repeatable_goal_manager_development_episode",
    "repeatable_goal_manager_trial_execution_identity",
    "run_repeatable_goal_manager_development_episode",
]
