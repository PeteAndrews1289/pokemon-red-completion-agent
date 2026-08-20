"""No-optimizer postmortem for the consumed protocol-party representation.

This module diagnoses the frozen train representation without fitting weights, selecting a
candidate, computing evaluation metrics, opening development examples, or proposing replacement
features.  Reproducing the consumed audit requires the historical prior's frozen hidden and score
forward pass.  It is intentionally separate from the learner so the consumed v2 result cannot be
turned into another architecture sweep by changing its gate.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import protocol_consistent_party_learning as protocol
from numpy.typing import NDArray

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeModel,
)
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeExample
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

_COLLISION_RTOL = 1e-9
_COLLISION_ATOL = protocol.PROTOCOL_OPTIMIZER_TOLERANCE


@dataclass(frozen=True, slots=True)
class _DiagnosticRow:
    action: str
    goal: str
    menu_ordinal: int
    pair_ordinal: int
    root_ordinal: int
    projected: NDArray[np.float64]
    raw_semantics: NDArray[np.float64]
    target: float
    menu_normalized_weight: float


@dataclass(frozen=True, slots=True)
class ProtocolPartyCollisionPostmortem:
    """Path-free aggregate explaining why the frozen representation was rejected."""

    train_questions: int
    pairwise_rows_by_action: Mapping[str, int]
    contradictory_pairwise_relationships: int
    collision_clusters: tuple[Mapping[str, object], ...]
    classification_counts: Mapping[str, int]
    spectra_by_action: Mapping[str, Mapping[str, object]]
    venue_menu_ranges: tuple[Mapping[str, object], ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "architecture_or_hyperparameter_sweep": False,
            "classification_counts": dict(sorted(self.classification_counts.items())),
            "collision_cluster_count": len(self.collision_clusters),
            "collision_clusters": list(self.collision_clusters),
            "contradictory_pairwise_relationships": (self.contradictory_pairwise_relationships),
            "development_examples_opened": 0,
            "development_metrics_computed": 0,
            "fitted_model_predictions": 0,
            "frozen_prior_forward_scores_used": True,
            "model_fits": 0,
            "optimizer_steps": 0,
            "pairwise_rows_by_action": dict(sorted(self.pairwise_rows_by_action.items())),
            "private_path_fields": 0,
            "preference_predictions_committed": 0,
            "schema": "pokemon.red.protocol-party-collision-postmortem.v1",
            "spectra_by_action": {
                key: dict(value) for key, value in sorted(self.spectra_by_action.items())
            },
            "status": "complete_no_optimizer",
            "train_questions": self.train_questions,
            "venue_menu_ranges": list(self.venue_menu_ranges),
        }


def audit_protocol_party_collisions(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> ProtocolPartyCollisionPostmortem:
    """Explain frozen collisions without fitting, ranking, or emitting predictions.

    The frozen prior's forward scores are intentionally recomputed because they are part of the
    consumed representation being diagnosed.  They never become probabilities, rankings, or
    candidate choices here.
    """

    ordered = tuple(sorted(examples, key=lambda item: item.scenario_id))
    protocol._require_base_model(base_model)
    protocol._require_training_examples(base_model, ordered)
    rows = _diagnostic_rows(base_model, ordered)
    clusters = _collision_clusters(rows)
    relationship_count = 0
    for cluster in clusters:
        conflicting = cluster.get("conflicting_relationships")
        if type(conflicting) is not int:  # noqa: E721
            raise protocol.ProtocolPartyLearningError(
                "postmortem collision relationship count is invalid"
            )
        relationship_count += conflicting
    consumed_audit = protocol.audit_protocol_party_representation(base_model, ordered)
    if relationship_count != consumed_audit.contradictory_pairwise_rows:
        raise protocol.ProtocolPartyLearningError(
            "postmortem contradiction count diverges from the consumed representation audit"
        )
    classifications = Counter(str(cluster["classification"]) for cluster in clusters)
    rows_by_action = Counter(row.action for row in rows)
    return ProtocolPartyCollisionPostmortem(
        train_questions=len(ordered),
        pairwise_rows_by_action=dict(sorted(rows_by_action.items())),
        contradictory_pairwise_relationships=relationship_count,
        collision_clusters=clusters,
        classification_counts=dict(sorted(classifications.items())),
        spectra_by_action=_spectra_by_action(rows),
        venue_menu_ranges=_venue_menu_ranges(base_model, ordered),
    )


def _diagnostic_rows(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Sequence[ScenarioOutcomeExample],
) -> tuple[_DiagnosticRow, ...]:
    result: list[_DiagnosticRow] = []
    root_ordinals = {
        root: ordinal
        for ordinal, root in enumerate(
            sorted(item.root_lineage_id for item in examples),
            start=1,
        )
    }
    for action_kind in TrainingChoiceKind:
        action_examples = tuple(
            item for item in examples if protocol._choice_kind(item) is action_kind
        )
        menu_weight = 1.0 / len(action_examples)
        for menu_ordinal, example in enumerate(action_examples, start=1):
            base_scores, representation = protocol._representation(base_model, example)
            raw = np.asarray(
                [candidate.features for candidate in example.candidates],
                dtype=np.float64,
            )
            pairs = tuple(
                (left, right)
                for position, left in enumerate(example.available_candidate_indices)
                for right in example.available_candidate_indices[position + 1 :]
            )
            pair_weight = menu_weight / len(pairs)
            for pair_ordinal, (left, right) in enumerate(pairs, start=1):
                left_outcome = example.outcomes[left]
                right_outcome = example.outcomes[right]
                if left_outcome is None or right_outcome is None:
                    raise protocol.ProtocolPartyLearningError(
                        "postmortem pairwise target is incomplete"
                    )
                left_key = example.objective.preference_key(left_outcome.criterion_values)
                right_key = example.objective.preference_key(right_outcome.criterion_values)
                target = 0.5 if left_key == right_key else float(left_key > right_key)
                augmented = np.concatenate(
                    (
                        np.asarray([base_scores[left] - base_scores[right]], dtype=np.float64),
                        representation[left] - representation[right],
                    )
                )
                nonzero = np.flatnonzero(np.abs(augmented) > _COLLISION_ATOL)
                reverse = bool(nonzero.size and augmented[int(nonzero[0])] < 0)
                direction = -1.0 if reverse else 1.0
                result.append(
                    _DiagnosticRow(
                        action=action_kind.value,
                        goal=protocol._goal(example).value,
                        menu_ordinal=menu_ordinal,
                        pair_ordinal=pair_ordinal,
                        root_ordinal=root_ordinals[example.root_lineage_id],
                        projected=direction * augmented,
                        raw_semantics=direction * (raw[left] - raw[right]),
                        target=1.0 - target if reverse else target,
                        menu_normalized_weight=pair_weight,
                    )
                )
    return tuple(result)


def _collision_clusters(
    rows: Sequence[_DiagnosticRow],
) -> tuple[Mapping[str, object], ...]:
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    near_pairs: list[tuple[int, int]] = []
    for left, left_row in enumerate(rows):
        for right in range(left + 1, len(rows)):
            right_row = rows[right]
            if left_row.action == right_row.action and np.allclose(
                left_row.projected,
                right_row.projected,
                rtol=_COLLISION_RTOL,
                atol=_COLLISION_ATOL,
            ):
                near_pairs.append((left, right))
                union(left, right)

    members: dict[int, list[int]] = {}
    for index in range(len(rows)):
        members.setdefault(find(index), []).append(index)
    result: list[dict[str, object]] = []
    for indices in members.values():
        conflicting = [
            (left, right)
            for left, right in near_pairs
            if left in indices
            and right in indices
            and abs(rows[left].target - rows[right].target) > protocol.PROTOCOL_TOLERANCE
        ]
        if not conflicting:
            continue
        involved = sorted({index for pair in conflicting for index in pair})
        categories = Counter(
            _classify_relationship(rows[left], rows[right]) for left, right in conflicting
        )
        classifications = tuple(sorted(categories))
        classification = classifications[0] if len(classifications) == 1 else "mixed"
        goals = Counter(rows[index].goal for index in involved)
        targets = Counter(_target_name(rows[index].target) for index in involved)
        projected_distances = [
            float(np.max(np.abs(rows[left].projected - rows[right].projected)))
            for left, right in conflicting
        ]
        raw_distances = [
            float(np.max(np.abs(rows[left].raw_semantics - rows[right].raw_semantics)))
            for left, right in conflicting
        ]
        document: dict[str, object] = {
            "action": rows[involved[0]].action,
            "classification": classification,
            "classification_relationship_counts": dict(sorted(categories.items())),
            "conflicting_relationships": len(conflicting),
            "distinct_roots": len({rows[index].root_ordinal for index in involved}),
            "exact_conflicting_relationships": sum(
                np.array_equal(rows[left].projected, rows[right].projected)
                for left, right in conflicting
            ),
            "goal_row_counts": dict(sorted(goals.items())),
            "maximum_projected_distance": max(projected_distances),
            "maximum_raw_semantic_distance": max(raw_distances),
            "menus_affected": len({rows[index].menu_ordinal for index in involved}),
            "row_count": len(involved),
            "target_row_counts": dict(sorted(targets.items())),
            "unique_menu_normalized_weight_affected": float(
                sum(rows[index].menu_normalized_weight for index in involved)
            ),
        }
        identity = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
        document["cluster_sha256"] = hashlib.sha256(identity).hexdigest()
        result.append(document)
    result.sort(key=lambda item: str(item["cluster_sha256"]))
    return tuple(
        {"cluster_ordinal": ordinal, **document} for ordinal, document in enumerate(result, start=1)
    )


def _classify_relationship(left: _DiagnosticRow, right: _DiagnosticRow) -> str:
    if not np.array_equal(left.projected, right.projected):
        return "tolerance_only_projected_near_collision"
    if left.goal == right.goal and np.array_equal(left.raw_semantics, right.raw_semantics):
        return "raw_semantics_aliased_or_outcome_instability"
    return "frozen_projection_compression"


def _target_name(target: float) -> str:
    if target == 0.0:
        return "loss"
    if target == 0.5:
        return "tie"
    if target == 1.0:
        return "win"
    raise protocol.ProtocolPartyLearningError("postmortem target is invalid")


def _spectra_by_action(
    rows: Sequence[_DiagnosticRow],
) -> dict[str, Mapping[str, object]]:
    names = ("frozen_prior.offset", *_representation_names_from_width(rows))
    result: dict[str, Mapping[str, object]] = {}
    for action in sorted({row.action for row in rows}):
        action_rows = tuple(row for row in rows if row.action == action)
        full = _spectrum(np.asarray([row.projected for row in action_rows]), names)
        folds: list[dict[str, object]] = []
        menus = sorted({row.menu_ordinal for row in action_rows})
        for fold_ordinal, menu in enumerate(menus, start=1):
            retained = tuple(row for row in action_rows if row.menu_ordinal != menu)
            fold = _spectrum(np.asarray([row.projected for row in retained]), names)
            held_goal = next(row.goal for row in action_rows if row.menu_ordinal == menu)
            folds.append(
                {
                    "fold_ordinal": fold_ordinal,
                    "held_goal": held_goal,
                    **fold,
                }
            )
        result[action] = {"full": full, "leave_one_root_out": folds}
    return result


def _spectrum(
    matrix: NDArray[np.float64],
    names: Sequence[str],
) -> dict[str, object]:
    if matrix.ndim != 2 or matrix.shape[1] != len(names):
        raise protocol.ProtocolPartyLearningError("postmortem spectrum matrix is invalid")
    norms = np.linalg.norm(matrix, axis=0)
    nonzero = norms > _COLLISION_ATOL
    normalized = np.zeros_like(matrix)
    normalized[:, nonzero] = matrix[:, nonzero] / norms[nonzero]
    singular = np.linalg.svd(normalized, compute_uv=False)
    return {
        "column_normalized_rank": int(np.linalg.matrix_rank(normalized, tol=_COLLISION_ATOL)),
        "row_count": matrix.shape[0],
        "singular_values": [float(value) for value in singular],
        "zero_columns": [name for name, present in zip(names, nonzero, strict=True) if not present],
    }


def _venue_menu_ranges(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Sequence[ScenarioOutcomeExample],
) -> tuple[Mapping[str, object], ...]:
    names = protocol._representation_names(base_model)
    venue_examples = tuple(
        item for item in examples if protocol._choice_kind(item) is TrainingChoiceKind.VENUE
    )
    result: list[Mapping[str, object]] = []
    for ordinal, example in enumerate(venue_examples, start=1):
        goal = protocol._goal(example).value
        representation = protocol._representation(base_model, example)[1]
        indices = list(example.available_candidate_indices)
        ranges = {
            component: float(
                np.ptp(
                    representation[
                        indices,
                        names.index(f"portable.goal_{goal}.venue_{component}"),
                    ]
                )
            )
            for component in protocol._VENUE_INTERACTION_COMPONENTS
        }
        result.append(
            {
                "candidate_count": len(indices),
                "goal": goal,
                "menu_ordinal": ordinal,
                "ranges": ranges,
            }
        )
    return tuple(result)


def _representation_names_from_width(
    rows: Sequence[_DiagnosticRow],
) -> tuple[str, ...]:
    if not rows:
        raise protocol.ProtocolPartyLearningError("postmortem has no pairwise rows")
    width = rows[0].projected.shape[0] - 1
    if width < len(protocol.PORTABLE_GROUP_NAMES) + 1:
        raise protocol.ProtocolPartyLearningError("postmortem representation width is invalid")
    hidden = width - len(protocol.PORTABLE_GROUP_NAMES) - 1
    return (
        "frozen_prior.score_adjustment",
        *(f"frozen_hidden.{index}" for index in range(hidden)),
        *protocol.PORTABLE_GROUP_NAMES,
    )
