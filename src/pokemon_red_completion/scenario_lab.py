"""Small authenticated laboratory for transferable skill experiments.

The laboratory runs one bounded scenario at a time.  It deliberately does not
own emulator construction, save-state paths, parallel workers, a dashboard, or
game-specific actions.  A title adapter supplies a private environment while
the learner receives only a semantic observation and a finite semantic action
menu.  The first supported families are exactly navigation, battle, and party
development.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from pokemon_red_completion.provenance import canonical_sha256

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_FORBIDDEN_POLICY_KEYS = frozenset(
    {
        "binding_ref",
        "expected_action",
        "game_id",
        "map_id",
        "move_id",
        "private_path",
        "rom_sha256",
        "species_id",
        "teacher_choice",
        "title_id",
    }
)


class ScenarioLabError(ValueError):
    """Raised when a scenario crosses an authority or evidence boundary."""


class ScenarioFamily(StrEnum):
    NAVIGATION = "navigation"
    BATTLE = "battle"
    PARTY_DEVELOPMENT = "party_development"


class ScenarioPartition(StrEnum):
    TRAIN = "train"
    DEVELOPMENT = "development"
    TEST = "test"


class ScenarioAuthority(StrEnum):
    SHADOW = "shadow"
    INTERVENTION_BACKED = "intervention_backed"
    TEACHER_FREE = "teacher_free"


class ScenarioVerdictStatus(StrEnum):
    ONGOING = "ongoing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ScenarioTerminalStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ScenarioFailureKind(StrEnum):
    ACTION_BUDGET_EXHAUSTED = "action_budget_exhausted"
    FRAME_BUDGET_EXHAUSTED = "frame_budget_exhausted"
    INVALID_POLICY_ACTION = "invalid_policy_action"
    MISSING_INTERVENTION = "missing_intervention"
    VERIFICATION_FAILED = "verification_failed"
    POLICY_ERROR = "policy_error"
    VERIFIER_ERROR = "verifier_error"
    ENVIRONMENT_ERROR = "environment_error"
    EXTERNAL_INTERRUPTION = "external_interruption"


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """Path-free public declaration for one private starting-state family."""

    scenario_id: str
    family: ScenarioFamily
    partition: ScenarioPartition
    environment_id: str
    observation_schema_id: str
    source_commit: str
    root_lineage_id: str
    initial_state_sha256: str
    allowed_action_kinds: tuple[str, ...]
    randomization_dimensions: tuple[str, ...]
    verifier_id: str
    maximum_actions: int
    maximum_frames: int
    authority: ScenarioAuthority

    def __post_init__(self) -> None:
        for name in (
            "scenario_id",
            "environment_id",
            "observation_schema_id",
            "root_lineage_id",
            "verifier_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise ScenarioLabError(f"{name.replace('_', ' ')} is invalid")
        if not isinstance(self.family, ScenarioFamily):
            raise ScenarioLabError("scenario family is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise ScenarioLabError("scenario partition is invalid")
        if not isinstance(self.authority, ScenarioAuthority):
            raise ScenarioLabError("scenario authority is invalid")
        if _SHA256.fullmatch(self.initial_state_sha256) is None:
            raise ScenarioLabError("scenario initial-state digest is invalid")
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise ScenarioLabError("scenario source commit is invalid")
        _safe_unique_vocabulary(self.allowed_action_kinds, subject="allowed action")
        _safe_unique_vocabulary(
            self.randomization_dimensions,
            subject="randomization dimension",
            allow_empty=True,
        )
        for name in ("maximum_actions", "maximum_frames"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ScenarioLabError(f"{name.replace('_', ' ')} must be positive")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.scenario-spec.v1",
            "scenario_id": self.scenario_id,
            "family": self.family.value,
            "partition": self.partition.value,
            "environment_id": self.environment_id,
            "observation_schema_id": self.observation_schema_id,
            "source_commit": self.source_commit,
            "root_lineage_id": self.root_lineage_id,
            "initial_state_sha256": self.initial_state_sha256,
            "allowed_action_kinds": list(self.allowed_action_kinds),
            "randomization_dimensions": list(self.randomization_dimensions),
            "verifier_id": self.verifier_id,
            "maximum_actions": self.maximum_actions,
            "maximum_frames": self.maximum_frames,
            "authority": self.authority.value,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class ScenarioCatalog:
    """Leakage-audited collection of train/development/test declarations."""

    specs: tuple[ScenarioSpec, ...]

    def __post_init__(self) -> None:
        if not self.specs or any(not isinstance(item, ScenarioSpec) for item in self.specs):
            raise ScenarioLabError("scenario catalog must contain typed specs")
        ids = tuple(item.scenario_id for item in self.specs)
        if len(ids) != len(set(ids)):
            raise ScenarioLabError("scenario identities must be unique")
        lineages: dict[str, ScenarioPartition] = {}
        states: dict[str, ScenarioPartition] = {}
        for item in self.specs:
            prior = lineages.setdefault(item.root_lineage_id, item.partition)
            if prior is not item.partition:
                raise ScenarioLabError("root lineage crosses scenario partitions")
            prior_state = states.setdefault(item.initial_state_sha256, item.partition)
            if prior_state is not item.partition:
                raise ScenarioLabError("initial state crosses scenario partitions")

    @property
    def catalog_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        counts = Counter((item.partition.value, item.family.value) for item in self.specs)
        return {
            "schema": "pokemon.core.scenario-catalog.v1",
            "specs": [item.public_dict() for item in self.specs],
            "partition_family_counts": {
                f"{partition}:{family}": count
                for (partition, family), count in sorted(counts.items())
            },
            "lineage_partition_overlap": _partition_overlap_count(
                self.specs,
                attribute="root_lineage_id",
            ),
            "initial_state_partition_overlap": _partition_overlap_count(
                self.specs,
                attribute="initial_state_sha256",
            ),
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class ScenarioObservation:
    """Identity-free state visible to a shared skill policy."""

    semantic_state: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_state, Mapping) or any(
            not isinstance(key, str) for key in self.semantic_state
        ):
            raise ScenarioLabError("scenario semantic state must be an object")
        document = _json_document(dict(self.semantic_state), subject="semantic state")
        forbidden = _forbidden_keys(document)
        if forbidden:
            raise ScenarioLabError(
                f"scenario policy state contains forbidden key {sorted(forbidden)[0]}"
            )
        encoded = json.dumps(document, sort_keys=True)
        if any(token in encoded for token in ("/Users/", "/Volumes/", "file://")):
            raise ScenarioLabError("scenario policy state contains a private path")
        object.__setattr__(self, "semantic_state", MappingProxyType(document))

    @property
    def state_sha256(self) -> str:
        return canonical_sha256(dict(self.semantic_state))


@dataclass(frozen=True, slots=True)
class ScenarioPolicyDecision:
    action_kind: str | None
    confidence: float | None = None
    requests_intervention: bool = False

    def __post_init__(self) -> None:
        if self.action_kind is not None and (
            not isinstance(self.action_kind, str)
            or _SAFE_ID.fullmatch(self.action_kind) is None
        ):
            raise ScenarioLabError("scenario action kind is invalid")
        if self.confidence is not None and (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not math.isfinite(float(self.confidence))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ScenarioLabError("scenario confidence is invalid")
        if not isinstance(self.requests_intervention, bool):
            raise ScenarioLabError("intervention request must be boolean")
        if self.requests_intervention and self.action_kind is not None:
            raise ScenarioLabError("an intervention request cannot also choose an action")
        if not self.requests_intervention and self.action_kind is None:
            raise ScenarioLabError("a policy decision needs an action or intervention")


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    observation: ScenarioObservation
    frames_executed: int

    def __post_init__(self) -> None:
        if not isinstance(self.observation, ScenarioObservation):
            raise ScenarioLabError("scenario step observation is invalid")
        if type(self.frames_executed) is not int or self.frames_executed <= 0:  # noqa: E721
            raise ScenarioLabError("scenario step frame count must be positive")


@dataclass(frozen=True, slots=True)
class ScenarioVerdict:
    status: ScenarioVerdictStatus
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ScenarioVerdictStatus):
            raise ScenarioLabError("scenario verdict status is invalid")
        if self.status is ScenarioVerdictStatus.FAILED:
            if not isinstance(self.reason, str) or _SAFE_ID.fullmatch(self.reason) is None:
                raise ScenarioLabError("failed scenario verdict needs a safe reason")
        elif self.reason is not None:
            raise ScenarioLabError("non-failed scenario verdict cannot carry a reason")


class ScenarioEnvironment(Protocol):
    def reset(self, seed: int) -> ScenarioObservation: ...

    def step(self, action_kind: str) -> ScenarioStep: ...


class ScenarioPolicy(Protocol):
    @property
    def policy_id(self) -> str: ...

    def choose(
        self,
        family: ScenarioFamily,
        observation: ScenarioObservation,
        allowed_action_kinds: tuple[str, ...],
    ) -> ScenarioPolicyDecision: ...


class ScenarioVerifier(Protocol):
    @property
    def verifier_id(self) -> str: ...

    def evaluate(self, observation: ScenarioObservation) -> ScenarioVerdict: ...


@dataclass(frozen=True, slots=True)
class ScenarioEpisodeResult:
    scenario_id: str
    family: ScenarioFamily
    partition: ScenarioPartition
    assignment_sha256: str
    policy_id: str
    intervention_policy_id: str | None
    status: ScenarioTerminalStatus
    failure_kind: ScenarioFailureKind | None
    failure_reason: str | None
    failure_message_sha256: str | None
    actions_executed: int
    frames_executed: int
    teacher_interventions: int
    final_state_sha256: str
    learner_update_eligible: bool

    @property
    def passed(self) -> bool:
        return self.status is ScenarioTerminalStatus.SUCCEEDED

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.scenario-episode-result.v1",
            "scenario_id": self.scenario_id,
            "family": self.family.value,
            "partition": self.partition.value,
            "assignment_sha256": self.assignment_sha256,
            "policy_id": self.policy_id,
            "intervention_policy_id": self.intervention_policy_id,
            "status": self.status.value,
            "failure_kind": (
                None if self.failure_kind is None else self.failure_kind.value
            ),
            "failure_reason": self.failure_reason,
            "failure_message_sha256": self.failure_message_sha256,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "teacher_interventions": self.teacher_interventions,
            "final_state_sha256": self.final_state_sha256,
            "learner_update_eligible": self.learner_update_eligible,
            "exact_exception_text_public": False,
            "private_path_fields": 0,
        }


def run_scenario_episode(
    spec: ScenarioSpec,
    *,
    seed: int,
    environment: ScenarioEnvironment,
    policy: ScenarioPolicy,
    verifier: ScenarioVerifier,
    intervention_policy: ScenarioPolicy | None = None,
) -> ScenarioEpisodeResult:
    """Run one bounded episode and retain every terminal classification."""

    if not isinstance(spec, ScenarioSpec):
        raise TypeError("spec must be ScenarioSpec")
    if type(seed) is not int or not 0 <= seed < 2**63:  # noqa: E721
        raise ScenarioLabError("scenario seed is invalid")
    policy_id = _safe_protocol_id(policy.policy_id, subject="policy identity")
    verifier_id = _safe_protocol_id(verifier.verifier_id, subject="verifier identity")
    if verifier_id != spec.verifier_id:
        raise ScenarioLabError("scenario verifier identity differs from its spec")
    intervention_policy_id = None
    if intervention_policy is not None:
        intervention_policy_id = _safe_protocol_id(
            intervention_policy.policy_id,
            subject="intervention policy identity",
        )
    if spec.authority is not ScenarioAuthority.INTERVENTION_BACKED and (
        intervention_policy is not None
    ):
        raise ScenarioLabError("scenario authority does not permit intervention")

    assignment_sha256 = canonical_sha256(
        {
            "catalog_spec": spec.public_dict(),
            "policy_id": policy_id,
            "intervention_policy_id": intervention_policy_id,
            "seed": seed,
            "schema": "pokemon.core.scenario-assignment.v1",
        }
    )
    actions = frames = interventions = 0
    observation = ScenarioObservation({"phase": "not_started"})
    try:
        observation = environment.reset(seed)
        if not isinstance(observation, ScenarioObservation):
            raise ScenarioLabError("scenario environment reset returned invalid state")
        while True:
            try:
                verdict = verifier.evaluate(observation)
            except Exception as error:
                return _exception_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.VERIFIER_ERROR,
                    reason="verifier_error",
                    error=error,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if not isinstance(verdict, ScenarioVerdict):
                return _exception_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.VERIFIER_ERROR,
                    reason="invalid_verifier_result",
                    error=ScenarioLabError(
                        "scenario verifier returned an invalid verdict"
                    ),
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if verdict.status is ScenarioVerdictStatus.SUCCEEDED:
                return _result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    status=ScenarioTerminalStatus.SUCCEEDED,
                    failure_kind=None,
                    failure_reason=None,
                    failure_message_sha256=None,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if verdict.status is ScenarioVerdictStatus.FAILED:
                return _result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    status=ScenarioTerminalStatus.FAILED,
                    failure_kind=ScenarioFailureKind.VERIFICATION_FAILED,
                    failure_reason=verdict.reason,
                    failure_message_sha256=None,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if actions >= spec.maximum_actions:
                return _budget_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.ACTION_BUDGET_EXHAUSTED,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            try:
                decision = policy.choose(
                    spec.family,
                    observation,
                    spec.allowed_action_kinds,
                )
            except Exception as error:
                return _exception_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.POLICY_ERROR,
                    reason="policy_error",
                    error=error,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if not isinstance(decision, ScenarioPolicyDecision):
                return _exception_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.POLICY_ERROR,
                    reason="invalid_policy_result",
                    error=ScenarioLabError(
                        "scenario policy returned an invalid decision"
                    ),
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if decision.requests_intervention:
                if (
                    spec.authority is not ScenarioAuthority.INTERVENTION_BACKED
                    or intervention_policy is None
                ):
                    return _failure_result(
                        spec,
                        assignment_sha256=assignment_sha256,
                        policy_id=policy_id,
                        intervention_policy_id=intervention_policy_id,
                        kind=ScenarioFailureKind.MISSING_INTERVENTION,
                        reason="intervention_unavailable",
                        actions=actions,
                        frames=frames,
                        interventions=interventions,
                        observation=observation,
                    )
                try:
                    decision = intervention_policy.choose(
                        spec.family,
                        observation,
                        spec.allowed_action_kinds,
                    )
                except Exception as error:
                    return _exception_result(
                        spec,
                        assignment_sha256=assignment_sha256,
                        policy_id=policy_id,
                        intervention_policy_id=intervention_policy_id,
                        kind=ScenarioFailureKind.POLICY_ERROR,
                        reason="intervention_policy_error",
                        error=error,
                        actions=actions,
                        frames=frames,
                        interventions=interventions,
                        observation=observation,
                    )
                if not isinstance(decision, ScenarioPolicyDecision) or (
                    decision.requests_intervention
                ):
                    return _exception_result(
                        spec,
                        assignment_sha256=assignment_sha256,
                        policy_id=policy_id,
                        intervention_policy_id=intervention_policy_id,
                        kind=ScenarioFailureKind.POLICY_ERROR,
                        reason="invalid_intervention_policy_result",
                        error=ScenarioLabError(
                            "intervention policy did not return a direct action"
                        ),
                        actions=actions,
                        frames=frames,
                        interventions=interventions,
                        observation=observation,
                    )
                interventions += 1
            action = decision.action_kind
            if action not in spec.allowed_action_kinds:
                return _failure_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.INVALID_POLICY_ACTION,
                    reason="action_outside_declared_menu",
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            assert action is not None
            try:
                step = environment.step(action)
            except Exception as error:
                return _exception_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.ENVIRONMENT_ERROR,
                    reason="environment_step_error",
                    error=error,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
            if not isinstance(step, ScenarioStep):
                raise ScenarioLabError("scenario environment returned an invalid step")
            actions += 1
            frames += step.frames_executed
            observation = step.observation
            if frames > spec.maximum_frames:
                return _budget_result(
                    spec,
                    assignment_sha256=assignment_sha256,
                    policy_id=policy_id,
                    intervention_policy_id=intervention_policy_id,
                    kind=ScenarioFailureKind.FRAME_BUDGET_EXHAUSTED,
                    actions=actions,
                    frames=frames,
                    interventions=interventions,
                    observation=observation,
                )
    except (KeyboardInterrupt, SystemExit) as error:
        return _result(
            spec,
            assignment_sha256=assignment_sha256,
            policy_id=policy_id,
            intervention_policy_id=intervention_policy_id,
            status=ScenarioTerminalStatus.INTERRUPTED,
            failure_kind=ScenarioFailureKind.EXTERNAL_INTERRUPTION,
            failure_reason="external_interruption",
            failure_message_sha256=_exception_digest(error),
            actions=actions,
            frames=frames,
            interventions=interventions,
            observation=observation,
        )
    except Exception as error:
        return _result(
            spec,
            assignment_sha256=assignment_sha256,
            policy_id=policy_id,
            intervention_policy_id=intervention_policy_id,
            status=ScenarioTerminalStatus.FAILED,
            failure_kind=ScenarioFailureKind.ENVIRONMENT_ERROR,
            failure_reason="environment_or_contract_error",
            failure_message_sha256=_exception_digest(error),
            actions=actions,
            frames=frames,
            interventions=interventions,
            observation=observation,
        )


def _budget_result(
    spec: ScenarioSpec,
    *,
    assignment_sha256: str,
    policy_id: str,
    intervention_policy_id: str | None,
    kind: ScenarioFailureKind,
    actions: int,
    frames: int,
    interventions: int,
    observation: ScenarioObservation,
) -> ScenarioEpisodeResult:
    return _failure_result(
        spec,
        assignment_sha256=assignment_sha256,
        policy_id=policy_id,
        intervention_policy_id=intervention_policy_id,
        kind=kind,
        reason=kind.value,
        actions=actions,
        frames=frames,
        interventions=interventions,
        observation=observation,
    )


def _failure_result(
    spec: ScenarioSpec,
    *,
    assignment_sha256: str,
    policy_id: str,
    intervention_policy_id: str | None,
    kind: ScenarioFailureKind,
    reason: str,
    actions: int,
    frames: int,
    interventions: int,
    observation: ScenarioObservation,
) -> ScenarioEpisodeResult:
    return _result(
        spec,
        assignment_sha256=assignment_sha256,
        policy_id=policy_id,
        intervention_policy_id=intervention_policy_id,
        status=ScenarioTerminalStatus.FAILED,
        failure_kind=kind,
        failure_reason=reason,
        failure_message_sha256=None,
        actions=actions,
        frames=frames,
        interventions=interventions,
        observation=observation,
    )


def _result(
    spec: ScenarioSpec,
    *,
    assignment_sha256: str,
    policy_id: str,
    intervention_policy_id: str | None,
    status: ScenarioTerminalStatus,
    failure_kind: ScenarioFailureKind | None,
    failure_reason: str | None,
    failure_message_sha256: str | None,
    actions: int,
    frames: int,
    interventions: int,
    observation: ScenarioObservation,
) -> ScenarioEpisodeResult:
    learner_update_eligible = (
        spec.partition is not ScenarioPartition.TEST
        and status is not ScenarioTerminalStatus.INTERRUPTED
        and failure_kind
        not in {
            ScenarioFailureKind.ENVIRONMENT_ERROR,
            ScenarioFailureKind.POLICY_ERROR,
            ScenarioFailureKind.VERIFIER_ERROR,
            ScenarioFailureKind.MISSING_INTERVENTION,
        }
    )
    return ScenarioEpisodeResult(
        scenario_id=spec.scenario_id,
        family=spec.family,
        partition=spec.partition,
        assignment_sha256=assignment_sha256,
        policy_id=policy_id,
        intervention_policy_id=intervention_policy_id,
        status=status,
        failure_kind=failure_kind,
        failure_reason=failure_reason,
        failure_message_sha256=failure_message_sha256,
        actions_executed=actions,
        frames_executed=frames,
        teacher_interventions=interventions,
        final_state_sha256=observation.state_sha256,
        learner_update_eligible=learner_update_eligible,
    )


def _exception_result(
    spec: ScenarioSpec,
    *,
    assignment_sha256: str,
    policy_id: str,
    intervention_policy_id: str | None,
    kind: ScenarioFailureKind,
    reason: str,
    error: BaseException,
    actions: int,
    frames: int,
    interventions: int,
    observation: ScenarioObservation,
) -> ScenarioEpisodeResult:
    return _result(
        spec,
        assignment_sha256=assignment_sha256,
        policy_id=policy_id,
        intervention_policy_id=intervention_policy_id,
        status=ScenarioTerminalStatus.FAILED,
        failure_kind=kind,
        failure_reason=reason,
        failure_message_sha256=_exception_digest(error),
        actions=actions,
        frames=frames,
        interventions=interventions,
        observation=observation,
    )


def _exception_digest(error: BaseException) -> str:
    return hashlib.sha256(
        f"{type(error).__name__}:{error}".encode("utf-8", errors="replace")
    ).hexdigest()


def _safe_protocol_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ScenarioLabError(f"{subject} is invalid")
    return value


def _safe_unique_vocabulary(
    values: object,
    *,
    subject: str,
    allow_empty: bool = False,
) -> None:
    if (
        not isinstance(values, tuple)
        or (not values and not allow_empty)
        or any(not isinstance(item, str) or _SAFE_ID.fullmatch(item) is None for item in values)
        or len(values) != len(set(values))
    ):
        raise ScenarioLabError(f"{subject} vocabulary is invalid")


def _json_document(value: object, *, subject: str) -> dict[str, object]:
    try:
        encoded = json.dumps(value, allow_nan=False, sort_keys=True)
        decoded = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ScenarioLabError(f"scenario {subject} is not finite JSON") from error
    if not isinstance(decoded, dict):
        raise ScenarioLabError(f"scenario {subject} must be an object")
    return decoded


def _forbidden_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_POLICY_KEYS:
                result.add(key)
            result.update(_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_forbidden_keys(child))
    return result


def _partition_overlap_count(
    specs: tuple[ScenarioSpec, ...],
    *,
    attribute: str,
) -> int:
    partitions: dict[str, set[ScenarioPartition]] = {}
    for spec in specs:
        value = getattr(spec, attribute)
        partitions.setdefault(value, set()).add(spec.partition)
    return sum(len(items) > 1 for items in partitions.values())


__all__ = [
    "ScenarioAuthority",
    "ScenarioCatalog",
    "ScenarioEnvironment",
    "ScenarioEpisodeResult",
    "ScenarioFailureKind",
    "ScenarioFamily",
    "ScenarioLabError",
    "ScenarioObservation",
    "ScenarioPartition",
    "ScenarioPolicy",
    "ScenarioPolicyDecision",
    "ScenarioSpec",
    "ScenarioStep",
    "ScenarioTerminalStatus",
    "ScenarioVerdict",
    "ScenarioVerdictStatus",
    "ScenarioVerifier",
    "run_scenario_episode",
]
