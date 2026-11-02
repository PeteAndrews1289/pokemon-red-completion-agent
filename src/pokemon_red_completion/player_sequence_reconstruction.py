"""Recompute collector candidates from original receipts, without native admission.

This is a recorded-consistency auditor. No ROM access, controller or fitting.
All target coverage remains unknown until independent native channel checks.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_sequence_targets import SequenceTargets, sequence_targets
from .player_short_sequence import SequenceEnd, SequenceMeasurement, measure_sequence
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory, recorded_branch_history
from .red_sequence_receipts import read_sequence_prefix, read_sequence_receipts


@dataclass(frozen=True)
class ReconstructedSequence:
    anchor_sha256: str
    window_sha256: str
    features: tuple[float, ...]
    behavior_probability: float
    measurement: SequenceMeasurement
    targets: SequenceTargets

    @property
    def training_eligible(self) -> bool:
        return False


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("sequence record is not an object")
    return value


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    # Python equality aliases false/0 and true/1; record schemas must not.
    return canonical_sha256(actual) == canonical_sha256(expected)


def reconstruct_sequence_candidates(
    root: Path, *, source_sha256: str, partition: str, expected_plan_sha256: str,
    expected_result_sha256: str, expected_declaration_sha256: str,
) -> tuple[ReconstructedSequence, ...]:
    """Reject changed/missing/extra records; never silently skip a bad window.

    The expected declaration hash must be retained before input by the eventual
    experiment protocol. A retrospective self-hash is only a diagnostic check.
    Failed projections leave all original evidence intact and return no dataset.
    """
    sequence = root / "sequence"
    declaration = _read(sequence / "declaration.json")
    plan = _read(root / "plan.json")
    horizon = declaration.get("horizon")
    if (
        partition not in {"train", "development"}
        or type(horizon) is not int or not 1 <= horizon <= 4
        or canonical_sha256(declaration) != expected_declaration_sha256
        or not _matches(declaration, dict(
            schema="pokemon.player.sequence-collection.v1", source_sha256=source_sha256,
            partition=partition, behavior_plan_sha256=expected_plan_sha256,
            behavior_model_sha256=plan["model_sha256"], horizon=horizon,
            windows="nonoverlapping-model-choices-with-attached-support",
            feature_contract="v6-candidate-plus-eight-observed-branch-history-values-v1",
            training_eligible=False, scoring_changed="sequence_policy" in plan,
        ))
    ):
        raise ValueError("sequence prospective declaration differs")
    projection = read_sequence_receipts(
        root, expected_plan_sha256=expected_plan_sha256,
        expected_result_sha256=expected_result_sha256, source_sha256=source_sha256,
    )
    outcomes = _read(root / "result.json")["outcomes"]
    digests = tuple(canonical_sha256(row) for row in outcomes)
    expected_files = {"declaration.json", "result.json"}
    anchors: list[dict[str, Any]] = []
    ordinals = []
    for ordinal, outcome in enumerate(outcomes):
        receipt = f"receipt-{ordinal:03d}.json"
        expected_files.add(receipt)
        if not _matches(_read(sequence / receipt), dict(
            schema="pokemon.player.sequence-prefix.v1", ordinal=ordinal,
            outcome_sha256=digests[ordinal],
            prefix_sha256=canonical_sha256(list(digests[:ordinal + 1])),
            observed_cost=outcome["observed_cost"], training_eligible=False,
        )):
            raise ValueError("sequence sealed receipt differs")
        if outcome["learning_eligible"] is not True:
            continue
        prefix = read_sequence_prefix(
            root, expected_plan_sha256=expected_plan_sha256, source_sha256=source_sha256,
            outcome_sha256=digests[:ordinal], boundary_sha256=outcome["before_state_sha256"],
        )
        intent = _read(root / f"step-{ordinal:03d}" / "intent.json")
        decision = _read(root / f"step-{ordinal:03d}" / "decision.json")
        menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
        selected = decision["selected_candidate_index"]
        context = projection.story_contexts[len(anchors)]
        history = RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)
        if context is not None and prefix.choices:
            history = recorded_branch_history(
                prefix, objective_ref=context, boundary_sha256=outcome["before_state_sha256"],
                expected_source_sha256=source_sha256, expected_plan_sha256=expected_plan_sha256,
            )
        expected_anchor = dict(
            schema="pokemon.player.sequence-anchor.v1", ordinal=ordinal,
            model_choice_index=len(anchors), before_sha256=outcome["before_state_sha256"],
            decision_sha256=canonical_sha256(dict(intent=intent, decision=decision)),
            previous_outcome_sha256=list(digests[:ordinal]), selected_candidate_index=selected,
            behavior_probability=decision["probabilities"][selected],
            features=list(menu.candidates[selected].vector(menu.context, feature_version=6)
                          + history.vector()),
            private_identity_feature_count=0, training_eligible=False,
        )
        name = f"anchor-{len(anchors):03d}.json"
        expected_files.add(name)
        if not _matches(_read(sequence / name), expected_anchor):
            raise ValueError("sequence pre-input anchor differs")
        anchors.append(expected_anchor)
        ordinals.append(ordinal)
    windows: list[ReconstructedSequence] = []
    for start in range(0, len(anchors), horizon):
        stop = min(start + horizon, len(anchors))
        prefix_stop = ordinals[stop] if stop < len(ordinals) else len(outcomes)
        steps = projection.choices[start:stop]
        measurement = measure_sequence(
            steps, horizon=horizon,
            end=SequenceEnd.HORIZON if stop - start == horizon else SequenceEnd.INTERRUPTED,
            initial_quests=projection.initial_quests if start == 0
            else projection.choices[start - 1].quests,
        )
        expected_window = dict(
            schema="pokemon.player.sequence-window-candidate.v1",
            anchor_sha256=canonical_sha256(anchors[start]), first_model_choice=start,
            prefix_outcome_sha256=list(digests[:prefix_stop]), measurement=asdict(measurement),
            complete_window=measurement.complete_window,
            cash_accounting_basis=measurement.cash_accounting_basis,
            native_verification_required=True, loss_accounting_complete=False,
            training_eligible=False,
        )
        name = f"window-{len(windows):03d}.json"
        expected_files.add(name)
        if not _matches(_read(sequence / name), expected_window):
            raise ValueError("sequence measured window differs")
        windows.append(ReconstructedSequence(
            canonical_sha256(anchors[start]), canonical_sha256(expected_window),
            tuple(anchors[start]["features"]), anchors[start]["behavior_probability"],
            measurement, sequence_targets(measurement),
        ))
    if not _matches(_read(sequence / "result.json"), dict(
        schema="pokemon.player.sequence-collection-result.v1", horizon=horizon,
        anchors=len(anchors), windows=len(windows), outcome_sha256=list(digests),
        projection_error=None, unprojected_observed_costs=[], training_eligible=False,
        fit_calls=0, promotions=0,
    )):
        raise ValueError("sequence collector result differs")
    if {path.name for path in sequence.iterdir()} != expected_files:
        raise ValueError("sequence artifact census differs")
    return tuple(windows)
