"""Prospective strategic situations for short authenticated collection.

The whole-game strategic campaign repeats three policy inputs.  This module
defines the stricter replacement contract: preregister *quest situations*,
keep related situations in one partition, and require a later live replay to
prove the actual identity-free policy context.  A registry row is a collection
assignment, not evidence that the emulator reached it and not a training row.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.collection_protocol import collection_document_sha256
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.quest import QuestGraph
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_SCENARIO_COLLECTION_ID,
    STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_ASSIGNMENT_SCHEMA,
    STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_EPISODE_PREFIX,
    StrategicNavigationExecution,
    StrategicNavigationScenarioRehearsalAssignment,
)

STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH = (
    "configs/red-strategic-navigation-scenarios-v2.json"
)
STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH = (
    "configs/red-strategic-navigation-scenarios-v2.digest.json"
)
STRATEGIC_SCENARIO_REGISTRY_SCHEMA = (
    "pokemon-strategic-navigation-scenario-registry-v2"
)
STRATEGIC_SCENARIO_REGISTRY_DIGEST_SCHEMA = (
    "pokemon-strategic-navigation-scenario-registry-digest-v2"
)
STRATEGIC_SCENARIO_SCHEMA = "pokemon-strategic-navigation-scenario-v2"
STRATEGIC_SCENARIO_COLLECTION_ID = STRATEGIC_NAVIGATION_SCENARIO_COLLECTION_ID
STRATEGIC_SCENARIO_REGIME = "within_game_authenticated_scenario"
STRATEGIC_SCENARIO_MINIMUM_CANDIDATES = 2
STRATEGIC_SCENARIO_MAXIMUM_CANDIDATES = 5
STRATEGIC_SCENARIO_MINIMUM_VALIDATION_CHALLENGES = 6
STRATEGIC_SCENARIO_MINIMUM_MULTIWAY_CONTEXTS = 24
STRATEGIC_SCENARIO_MINIMUM_TEACHER_OBJECTIVES = 12
STRATEGIC_SCENARIO_PARTITION_COUNTS = {
    "test": 12,
    "train": 24,
    "validation": 12,
}

_MAX_REGISTRY_BYTES = 1024 * 1024
_MAX_DIGEST_BYTES = 4096
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

# These implications come from bounded-skill effects, not from graph edges.
# A scenario that violates one cannot exist in the current teacher execution.
STRATEGIC_SCENARIO_AUTOMATIC_COMPLETIONS: Mapping[str, frozenset[str]] = {
    "clear_rocket_hideout": frozenset({"obtain_silph_scope"}),
    "defeat_champion": frozenset({"enter_hall_of_fame"}),
}


class StrategicScenarioProtocolError(RuntimeError):
    """Raised when a scenario registry overstates a prospective experiment."""


@dataclass(frozen=True, slots=True)
class StrategicNavigationScenario:
    """One preregistered semantic frontier awaiting live authentication."""

    scenario_id: str
    partition: str
    completed_objective_ids: tuple[str, ...]
    candidate_objective_ids: tuple[str, ...]
    teacher_objective_id: str
    origin_region: str
    cost_baseline_challenge_hypothesis: bool
    context_family_sha256: str
    scenario_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_objective_ids": list(self.candidate_objective_ids),
            "completed_objective_ids": list(self.completed_objective_ids),
            "context_family_sha256": self.context_family_sha256,
            "cost_baseline_challenge_hypothesis": (
                self.cost_baseline_challenge_hypothesis
            ),
            "origin_region": self.origin_region,
            "partition": self.partition,
            "scenario_id": self.scenario_id,
            "scenario_sha256": self.scenario_sha256,
            "schema": STRATEGIC_SCENARIO_SCHEMA,
            "teacher_objective_id": self.teacher_objective_id,
        }

    def commitment_payload(self) -> dict[str, object]:
        """Return the scenario fields covered by ``scenario_sha256``."""

        payload = self.public_dict()
        payload.pop("scenario_sha256")
        return payload


@dataclass(frozen=True, slots=True)
class StrategicNavigationScenarioRegistry:
    """Canonical scenario assignments with sealed test access."""

    registry_sha256: str
    objective_graph_sha256: str
    teacher_order_sha256: str
    scenarios: tuple[StrategicNavigationScenario, ...]

    @property
    def partition_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.partition for item in self.scenarios).items()))

    @property
    def candidate_count_counts(self) -> dict[int, int]:
        return dict(
            sorted(Counter(len(item.candidate_objective_ids) for item in self.scenarios).items())
        )

    @property
    def teacher_objective_counts(self) -> dict[str, int]:
        return dict(
            sorted(Counter(item.teacher_objective_id for item in self.scenarios).items())
        )

    @property
    def validation_challenge_hypotheses(self) -> int:
        return sum(
            item.partition == "validation"
            and item.cost_baseline_challenge_hypothesis
            for item in self.scenarios
        )

    @property
    def multiway_scenarios(self) -> int:
        return sum(len(item.candidate_objective_ids) >= 3 for item in self.scenarios)

    def learning_scenarios(self) -> tuple[StrategicNavigationScenario, ...]:
        """Expose train/validation assignments while test remains unopened."""

        return tuple(item for item in self.scenarios if item.partition != "test")

    def scenario(self, scenario_id: str) -> StrategicNavigationScenario:
        """Return a non-test assignment by ID and fail closed on sealed test."""

        for item in self.scenarios:
            if item.scenario_id != scenario_id:
                continue
            if item.partition == "test":
                raise StrategicScenarioProtocolError(
                    "test scenario must remain unopened until final evaluation"
                )
            return item
        raise StrategicScenarioProtocolError("unknown strategic scenario")

    def rehearsal_assignment(
        self,
        scenario_id: str,
        *,
        capture: CapturedProgressEnvelope,
        execution: StrategicNavigationExecution,
    ) -> StrategicNavigationScenarioRehearsalAssignment:
        """Bind one uncounted rehearsal to exact scenario, state and source.

        Test scenarios remain inaccessible through :meth:`scenario`.  Exact
        equality is intentional: a checkpoint with additional completed
        objectives is a different decision frontier, not this scenario.
        """

        if not isinstance(capture, CapturedProgressEnvelope):
            raise TypeError("capture must be a CapturedProgressEnvelope")
        if not isinstance(execution, StrategicNavigationExecution):
            raise TypeError("execution must be a StrategicNavigationExecution")
        if execution.source_commit is None:
            raise StrategicScenarioProtocolError(
                "scenario rehearsal requires committed source identity"
            )
        scenario = self.scenario(scenario_id)
        if frozenset(capture.verified_objective_ids) != frozenset(
            scenario.completed_objective_ids
        ):
            raise StrategicScenarioProtocolError(
                "capture objective frontier differs from strategic scenario"
            )
        envelope_sha256 = canonical_sha256(capture.to_dict())
        assignment_payload = {
            "capture_envelope_sha256": envelope_sha256,
            "capture_state_sha256": capture.state_sha256,
            "checkpoint_id": capture.checkpoint_id,
            "collection_id": STRATEGIC_SCENARIO_COLLECTION_ID,
            "registry_sha256": self.registry_sha256,
            "scenario_id": scenario.scenario_id,
            "scenario_partition": scenario.partition,
            "scenario_sha256": scenario.scenario_sha256,
            "schema": STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_ASSIGNMENT_SCHEMA,
            "source_bundle_sha256": execution.source_bundle_sha256,
            "source_commit": execution.source_commit,
            "teacher_execution_sha256": execution.teacher_execution_sha256,
        }
        assignment_id = collection_document_sha256(assignment_payload)
        return StrategicNavigationScenarioRehearsalAssignment(
            collection_id=STRATEGIC_SCENARIO_COLLECTION_ID,
            registry_sha256=self.registry_sha256,
            scenario_id=scenario.scenario_id,
            scenario_sha256=scenario.scenario_sha256,
            scenario_partition=scenario.partition,
            capture_envelope_sha256=envelope_sha256,
            capture_state_sha256=capture.state_sha256,
            checkpoint_id=capture.checkpoint_id,
            assignment_id=assignment_id,
            root_lineage_id=f"red-scenario-rehearsal-root-{assignment_id}",
            episode_id=(
                f"{STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_EPISODE_PREFIX}"
                f"{assignment_id}"
            ),
            source_bundle_sha256=execution.source_bundle_sha256,
            teacher_execution_sha256=execution.teacher_execution_sha256,
            source_commit=execution.source_commit,
        )

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": STRATEGIC_SCENARIO_REGISTRY_SCHEMA,
            "registry_sha256": self.registry_sha256,
            "objective_graph_sha256": self.objective_graph_sha256,
            "teacher_order_sha256": self.teacher_order_sha256,
            "scenario_count": len(self.scenarios),
            "partition_counts": self.partition_counts,
            "candidate_count_counts": {
                str(key): value for key, value in self.candidate_count_counts.items()
            },
            "teacher_objective_counts": self.teacher_objective_counts,
            "validation_challenge_hypotheses": self.validation_challenge_hypotheses,
            "multiway_scenarios": self.multiway_scenarios,
            "live_policy_contexts_authenticated": 0,
            "collection_open": False,
            "test_scenarios_sealed": self.partition_counts.get("test", 0),
        }


def scenario_context_family_sha256(
    completed_objective_ids: Sequence[str],
    candidate_objective_ids: Sequence[str],
) -> str:
    """Group order variants before any route metrics or outcomes are observed."""

    return canonical_sha256(
        {
            "candidate_objective_ids": sorted(candidate_objective_ids),
            "completed_objective_ids": sorted(completed_objective_ids),
            "schema": "pokemon-strategic-navigation-context-family-v1",
        }
    )


def strategic_scenario_objective_graph_sha256(graph: QuestGraph) -> str:
    """Bind scenario assignments to objective semantics and ordering inputs."""

    if not isinstance(graph, QuestGraph):
        raise TypeError("graph must be a QuestGraph")
    return canonical_sha256(
        {
            "objectives": [
                {
                    "completion_facts": sorted(item.completion_facts),
                    "id": item.id,
                    "prerequisites": sorted(item.prerequisites),
                    "priority": item.priority,
                    "specialist": item.specialist.value,
                    "target_region": item.target_region,
                }
                for item in graph.topological_order()
            ],
            "schema": "pokemon-strategic-scenario-objective-graph-v1",
        }
    )


def strategic_scenario_teacher_order_sha256(
    teacher_order: Sequence[str],
) -> str:
    """Bind scenario labels to the prospective teacher order."""

    return canonical_sha256(
        {
            "objective_ids": list(teacher_order),
            "schema": "pokemon-strategic-scenario-teacher-order-v1",
        }
    )


def reachable_objective_sets(
    graph: QuestGraph,
    *,
    maximum: int = 20_000,
) -> tuple[frozenset[str], ...]:
    """Enumerate graph-legal completion sets without consulting an outcome."""

    if not isinstance(graph, QuestGraph):
        raise TypeError("graph must be a QuestGraph")
    if type(maximum) is not int or maximum <= 0:  # noqa: E721
        raise ValueError("maximum must be a positive integer")
    initial: frozenset[str] = frozenset()
    queue = deque((initial,))
    seen = {initial}
    while queue:
        completed = queue.popleft()
        available = tuple(
            objective
            for objective in graph
            if objective.id not in completed
            and objective.prerequisites.issubset(completed)
        )
        for objective in available:
            successor = completed.union((objective.id,))
            if successor in seen:
                continue
            if len(seen) >= maximum:
                raise StrategicScenarioProtocolError(
                    "scenario reachability audit exceeded its declared bound"
                )
            seen.add(successor)
            queue.append(successor)
    return tuple(sorted(seen, key=lambda value: (len(value), tuple(sorted(value)))))


def parse_strategic_navigation_scenario_registry(
    payload: bytes,
    *,
    graph: QuestGraph | None = None,
    teacher_order: Sequence[str] | None = None,
) -> StrategicNavigationScenarioRegistry:
    """Parse, canonicalize and semantically authenticate a public registry."""

    if not isinstance(payload, bytes):
        raise TypeError("strategic scenario registry must be bytes")
    if not payload or len(payload) > _MAX_REGISTRY_BYTES:
        raise StrategicScenarioProtocolError("strategic scenario registry size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, StrategicScenarioProtocolError) as error:
        raise StrategicScenarioProtocolError(
            "strategic scenario registry is not canonical ASCII JSON"
        ) from error
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise StrategicScenarioProtocolError(
            "strategic scenario registry is not canonical ASCII JSON"
        )
    if set(value) != {
        "collection_id",
        "objective_graph_sha256",
        "regime",
        "scenarios",
        "schema",
        "teacher_order_sha256",
    }:
        raise StrategicScenarioProtocolError("strategic scenario registry fields differ")
    if graph is None or teacher_order is None:
        from pokemon_red_completion.play import QUALIFIED_OBJECTIVE_SEQUENCE
        from pokemon_red_completion.route import COMPLETION_QUEST

        graph = COMPLETION_QUEST if graph is None else graph
        teacher_order = (
            QUALIFIED_OBJECTIVE_SEQUENCE if teacher_order is None else teacher_order
        )
    assert graph is not None
    assert teacher_order is not None
    if value.get("schema") != STRATEGIC_SCENARIO_REGISTRY_SCHEMA:
        raise StrategicScenarioProtocolError("strategic scenario registry schema differs")
    if value.get("collection_id") != STRATEGIC_SCENARIO_COLLECTION_ID:
        raise StrategicScenarioProtocolError("strategic scenario collection differs")
    if value.get("regime") != STRATEGIC_SCENARIO_REGIME:
        raise StrategicScenarioProtocolError("strategic scenario regime differs")
    graph_sha256 = _digest(
        value.get("objective_graph_sha256"),
        subject="scenario objective graph digest",
    )
    expected_graph_sha256 = strategic_scenario_objective_graph_sha256(graph)
    if graph_sha256 != expected_graph_sha256:
        raise StrategicScenarioProtocolError("scenario objective graph differs")
    teacher_sha256 = _digest(
        value.get("teacher_order_sha256"),
        subject="scenario teacher order digest",
    )
    teacher_ids = tuple(teacher_order)
    if teacher_sha256 != strategic_scenario_teacher_order_sha256(teacher_ids):
        raise StrategicScenarioProtocolError("scenario teacher order differs")
    if len(teacher_ids) != len(set(teacher_ids)) or set(teacher_ids) != {
        item.id for item in graph
    }:
        raise StrategicScenarioProtocolError("scenario teacher order is not a graph order")

    raw_scenarios = value.get("scenarios")
    if not isinstance(raw_scenarios, list):
        raise StrategicScenarioProtocolError("strategic scenarios must be a list")
    scenarios = tuple(
        _parse_scenario(
            item,
            graph=graph,
            teacher_order=teacher_ids,
            ordinal=ordinal,
        )
        for ordinal, item in enumerate(raw_scenarios, start=1)
    )
    _validate_registry_scenarios(scenarios)
    return StrategicNavigationScenarioRegistry(
        registry_sha256=hashlib.sha256(payload).hexdigest(),
        objective_graph_sha256=graph_sha256,
        teacher_order_sha256=teacher_sha256,
        scenarios=scenarios,
    )


def load_strategic_navigation_scenario_registry(
    repository: Path,
) -> StrategicNavigationScenarioRegistry:
    """Load the committed public registry and verify its sidecar digest."""

    registry_path = repository / STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH
    digest_path = repository / STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH
    registry_payload = registry_path.read_bytes()
    if not digest_path.is_file() or digest_path.stat().st_size > _MAX_DIGEST_BYTES:
        raise StrategicScenarioProtocolError("strategic scenario digest sidecar is invalid")
    try:
        digest = json.loads(digest_path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StrategicScenarioProtocolError(
            "strategic scenario digest sidecar is invalid"
        ) from error
    actual = hashlib.sha256(registry_payload).hexdigest()
    if digest != {
        "bytes": len(registry_payload),
        "schema": STRATEGIC_SCENARIO_REGISTRY_DIGEST_SCHEMA,
        "sha256": actual,
    }:
        raise StrategicScenarioProtocolError("strategic scenario digest sidecar differs")
    return parse_strategic_navigation_scenario_registry(registry_payload)


def _parse_scenario(
    value: object,
    *,
    graph: QuestGraph,
    teacher_order: tuple[str, ...],
    ordinal: int,
) -> StrategicNavigationScenario:
    row = _mapping(value, subject="strategic scenario")
    if set(row) != {
        "candidate_objective_ids",
        "completed_objective_ids",
        "context_family_sha256",
        "cost_baseline_challenge_hypothesis",
        "origin_region",
        "partition",
        "scenario_id",
        "scenario_sha256",
        "schema",
        "teacher_objective_id",
    }:
        raise StrategicScenarioProtocolError("strategic scenario fields differ")
    if row.get("schema") != STRATEGIC_SCENARIO_SCHEMA:
        raise StrategicScenarioProtocolError("strategic scenario schema differs")
    scenario = StrategicNavigationScenario(
        scenario_id=_safe_id(row.get("scenario_id"), "strategic scenario identity"),
        partition=_string(row.get("partition"), "strategic scenario partition"),
        completed_objective_ids=_strings(
            row.get("completed_objective_ids"),
            "completed objective identities",
        ),
        candidate_objective_ids=_strings(
            row.get("candidate_objective_ids"),
            "candidate objective identities",
        ),
        teacher_objective_id=_string(
            row.get("teacher_objective_id"),
            "teacher objective identity",
        ),
        origin_region=_safe_id(row.get("origin_region"), "scenario origin region"),
        cost_baseline_challenge_hypothesis=_boolean(
            row.get("cost_baseline_challenge_hypothesis"),
            "cost-baseline challenge hypothesis",
        ),
        context_family_sha256=_digest(
            row.get("context_family_sha256"),
            subject="scenario context-family digest",
        ),
        scenario_sha256=_digest(
            row.get("scenario_sha256"),
            subject="strategic scenario digest",
        ),
    )
    if scenario.partition not in STRATEGIC_SCENARIO_PARTITION_COUNTS:
        raise StrategicScenarioProtocolError("strategic scenario partition differs")
    if scenario.scenario_id != (
        f"red-strategic-scenario-v2-{ordinal:03d}-{scenario.partition}"
    ):
        raise StrategicScenarioProtocolError("strategic scenario order differs")
    if not (
        STRATEGIC_SCENARIO_MINIMUM_CANDIDATES
        <= len(scenario.candidate_objective_ids)
        <= STRATEGIC_SCENARIO_MAXIMUM_CANDIDATES
    ):
        raise StrategicScenarioProtocolError("strategic scenario candidate count differs")
    known = {item.id for item in graph}
    completed = frozenset(scenario.completed_objective_ids)
    if (
        len(completed) != len(scenario.completed_objective_ids)
        or scenario.completed_objective_ids
        != tuple(sorted(scenario.completed_objective_ids))
        or len(set(scenario.candidate_objective_ids))
        != len(scenario.candidate_objective_ids)
        or completed.difference(known)
        or set(scenario.candidate_objective_ids).difference(known)
    ):
        raise StrategicScenarioProtocolError("strategic scenario objective identity differs")
    for objective_id in completed:
        if not graph.objective(objective_id).prerequisites.issubset(completed):
            raise StrategicScenarioProtocolError(
                "strategic scenario completed objectives violate prerequisites"
            )
        automatic = STRATEGIC_SCENARIO_AUTOMATIC_COMPLETIONS.get(
            objective_id,
            frozenset(),
        )
        if not automatic.issubset(completed):
            raise StrategicScenarioProtocolError(
                "strategic scenario omits an automatic objective completion"
            )
    facts = frozenset(
        fact
        for objective_id in completed
        for fact in graph.objective(objective_id).completion_facts
    )
    available = graph.available_objectives(
        GameState(mode=GameMode.OVERWORLD, facts=facts)
    )
    available_ids = tuple(item.id for item in available)
    if scenario.candidate_objective_ids != available_ids:
        raise StrategicScenarioProtocolError(
            "strategic scenario candidates differ from the quest frontier"
        )
    teacher_rank = {objective_id: index for index, objective_id in enumerate(teacher_order)}
    expected_teacher = min(available_ids, key=teacher_rank.__getitem__)
    if scenario.teacher_objective_id != expected_teacher:
        raise StrategicScenarioProtocolError("strategic scenario teacher choice differs")
    completed_regions = {
        graph.objective(objective_id).target_region for objective_id in completed
    }
    if scenario.origin_region not in completed_regions:
        raise StrategicScenarioProtocolError(
            "strategic scenario origin region lacks completed progress evidence"
        )
    if scenario.cost_baseline_challenge_hypothesis:
        local_non_teacher = {
            graph.objective(objective_id).target_region
            for objective_id in available_ids
            if objective_id != scenario.teacher_objective_id
        }
        if scenario.origin_region not in local_non_teacher:
            raise StrategicScenarioProtocolError(
                "cost-baseline challenge lacks a local non-teacher candidate"
            )
    expected_family = scenario_context_family_sha256(
        scenario.completed_objective_ids,
        scenario.candidate_objective_ids,
    )
    if scenario.context_family_sha256 != expected_family:
        raise StrategicScenarioProtocolError("scenario context-family digest differs")
    if scenario.scenario_sha256 != canonical_sha256(scenario.commitment_payload()):
        raise StrategicScenarioProtocolError("strategic scenario digest differs")
    return scenario


def _validate_registry_scenarios(
    scenarios: tuple[StrategicNavigationScenario, ...],
) -> None:
    if len(scenarios) != sum(STRATEGIC_SCENARIO_PARTITION_COUNTS.values()):
        raise StrategicScenarioProtocolError("strategic scenario count differs")
    if len({item.scenario_id for item in scenarios}) != len(scenarios):
        raise StrategicScenarioProtocolError("strategic scenario identity is duplicated")
    if len({item.scenario_sha256 for item in scenarios}) != len(scenarios):
        raise StrategicScenarioProtocolError("strategic scenario digest is duplicated")
    counts = Counter(item.partition for item in scenarios)
    if dict(counts) != STRATEGIC_SCENARIO_PARTITION_COUNTS:
        raise StrategicScenarioProtocolError("strategic scenario partition counts differ")
    family_partitions: dict[str, set[str]] = {}
    for item in scenarios:
        family_partitions.setdefault(item.context_family_sha256, set()).add(item.partition)
    if any(len(partitions) != 1 for partitions in family_partitions.values()):
        raise StrategicScenarioProtocolError(
            "strategic context family crosses data partitions"
        )
    validation_challenges = sum(
        item.partition == "validation"
        and item.cost_baseline_challenge_hypothesis
        for item in scenarios
    )
    if validation_challenges < STRATEGIC_SCENARIO_MINIMUM_VALIDATION_CHALLENGES:
        raise StrategicScenarioProtocolError(
            "strategic validation lacks baseline-challenge hypotheses"
        )
    if (
        sum(len(item.candidate_objective_ids) >= 3 for item in scenarios)
        < STRATEGIC_SCENARIO_MINIMUM_MULTIWAY_CONTEXTS
    ):
        raise StrategicScenarioProtocolError(
            "strategic scenario registry lacks genuine multiway density"
        )
    if (
        len({item.teacher_objective_id for item in scenarios})
        < STRATEGIC_SCENARIO_MINIMUM_TEACHER_OBJECTIVES
    ):
        raise StrategicScenarioProtocolError(
            "strategic scenario registry lacks teacher-objective breadth"
        )


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrategicScenarioProtocolError("JSON object key is duplicated")
        result[key] = value
    return result


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise StrategicScenarioProtocolError(f"{subject} must be an object")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategicScenarioProtocolError(f"{subject} must be a non-empty string")
    return value


def _safe_id(value: object, subject: str) -> str:
    item = _string(value, subject)
    if _SAFE_ID.fullmatch(item) is None:
        raise StrategicScenarioProtocolError(f"{subject} is unsafe")
    return item


def _strings(value: object, subject: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise StrategicScenarioProtocolError(f"{subject} must be a list")
    return tuple(_safe_id(item, subject) for item in value)


def _boolean(value: object, subject: str) -> bool:
    if not isinstance(value, bool):
        raise StrategicScenarioProtocolError(f"{subject} must be boolean")
    return value


def _digest(value: object, *, subject: str) -> str:
    digest = _string(value, subject)
    if _SHA256.fullmatch(digest) is None:
        raise StrategicScenarioProtocolError(f"{subject} must be a SHA-256 digest")
    return digest
