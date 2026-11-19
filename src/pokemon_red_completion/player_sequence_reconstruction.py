"""Recompute collector candidates from original receipts, without native admission.

This is a recorded-consistency auditor. No ROM access, controller or fitting.
All target coverage remains unknown until independent native channel checks.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_sequence_targets import (
    SEQUENCE_TARGET_CONTRACT,
    TASK_TERMINAL_TARGET_CONTRACT,
    TASK_TARGET_CONTRACTS,
    SequenceTargets,
    unverified_sequence_targets,
    validate_sequence_target_contract,
)
from .player_sequence_value import sequence_feature_contract
from .player_short_sequence import SequenceEnd, SequenceMeasurement, measure_sequence
from .provenance import canonical_sha256
from .recorded_branch_history import recorded_option_history, STORY_HISTORY, validate_history_contract
from .red_sequence_receipts import read_sequence_prefix, read_sequence_receipts


@dataclass(frozen=True)
class ReconstructedSequence:
    anchor_sha256: str
    window_sha256: str
    features: tuple[float, ...]
    behavior_probability: float
    measurement: SequenceMeasurement
    targets: SequenceTargets
    target_contract: str = SEQUENCE_TARGET_CONTRACT

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
    root: Path,
    *,
    source_sha256: str,
    partition: str,
    expected_plan_sha256: str,
    expected_result_sha256: str,
    expected_declaration_sha256: str,
    expected_task_sha256: str | None = None,
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
    stride = declaration.get("window_stride", horizon)
    overlapping = type(stride) is int and type(horizon) is int and 1 <= stride < horizon
    version = declaration.get("feature_version", 6)
    history_contract = declaration.get("history_contract", STORY_HISTORY)
    selection_history = declaration.get("selection_history_contract", history_contract)
    validate_history_contract(selection_history)
    if "sequence_policy" in plan:
        from .player_sequence_policy import SequencePolicy
        policy = SequencePolicy.from_document(plan["sequence_policy"],expected_sha256=plan["model_sha256"])
        if selection_history != policy.head.history_contract:
            raise ValueError("sequence selection history differs from the frozen policy")
    contract = sequence_feature_contract(version, history_contract)
    target_contract = declaration.get("target_contract", SEQUENCE_TARGET_CONTRACT)
    validate_sequence_target_contract(target_contract)
    task = declaration.get("task_sha256")
    if target_contract in TASK_TARGET_CONTRACTS:
        import re

        if (
            type(task) is not str
            or re.fullmatch(r"[0-9a-f]{64}", task) is None
            or task != expected_task_sha256
        ):
            raise ValueError("sequence task identity differs from prospective audit scope")
    elif task is not None or expected_task_sha256 is not None:
        raise ValueError("legacy sequence cannot acquire task-terminal authority")
    if (
        partition not in {"train", "development"}
        or type(horizon) is not int
        or not 1 <= horizon <= 4
        or type(stride) is not int or not 1 <= stride <= horizon
        or canonical_sha256(declaration) != expected_declaration_sha256
        or not _matches(
            declaration,
            dict(
                schema=(
                    "pokemon.player.sequence-collection.v4"
                    if overlapping
                    else "pokemon.player.sequence-collection.v3"
                    if task is not None
                    else "pokemon.player.sequence-collection.v1"
                    if version == 6
                    else "pokemon.player.sequence-collection.v2"
                ),
                **({"feature_version": version} if version != 6 else {}),
                **(
                    {"target_contract": target_contract, "task_sha256": task}
                    if task is not None
                    else {}
                ),
                source_sha256=source_sha256,
                partition=partition,
                behavior_plan_sha256=expected_plan_sha256,
                behavior_model_sha256=plan["model_sha256"],
                horizon=horizon,
                **({"window_stride": stride} if overlapping else {}),
                windows=("overlapping-model-choices-with-attached-support" if overlapping
                         else "nonoverlapping-model-choices-with-attached-support"),
                feature_contract=contract,
                **({"history_contract": history_contract} if history_contract != STORY_HISTORY else {}),
                **({"selection_history_contract": declaration["selection_history_contract"]}
                   if "selection_history_contract" in declaration else {}),
                training_eligible=False,
                scoring_changed="sequence_policy" in plan,
            ),
        )
    ):
        raise ValueError("sequence prospective declaration differs")
    projection = read_sequence_receipts(
        root,
        expected_plan_sha256=expected_plan_sha256,
        expected_result_sha256=expected_result_sha256,
        source_sha256=source_sha256,
    )
    outcomes = _read(root / "result.json")["outcomes"]
    digests = tuple(canonical_sha256(row) for row in outcomes)
    expected_files = {"declaration.json", "result.json"}
    terminal_claim = None
    if task is not None and (sequence / "task-terminal.json").exists():
        terminal_claim = _read(sequence / "task-terminal.json")
        expected_files.add("task-terminal.json")
        last = outcomes[-1]
        expected_claim = dict(
            schema="pokemon.player.task-terminal-claim.v1",
            task_sha256=task,
            source_sha256=source_sha256,
            behavior_plan_sha256=expected_plan_sha256,
            terminal_sha256=last["terminal_state_sha256"],
            last_outcome_sha256=digests[-1],
            native_verification_required=True,
            training_eligible=False,
        )
        if (
            not _matches(terminal_claim, expected_claim)
            or _read(root / "result.json").get("stop_reason") != "declared_consequence_complete"
            or last.get("safe_terminal") is not True
            or last.get("error_type") is not None
            or last.get("verification") != "succeeded"
        ):
            raise ValueError("sequence task terminal claim differs")
    anchors: list[dict[str, Any]] = []
    ordinals = []
    for ordinal, outcome in enumerate(outcomes):
        receipt = f"receipt-{ordinal:03d}.json"
        expected_files.add(receipt)
        if not _matches(
            _read(sequence / receipt),
            dict(
                schema="pokemon.player.sequence-prefix.v1",
                ordinal=ordinal,
                outcome_sha256=digests[ordinal],
                prefix_sha256=canonical_sha256(list(digests[: ordinal + 1])),
                observed_cost=outcome["observed_cost"],
                training_eligible=False,
            ),
        ):
            raise ValueError("sequence sealed receipt differs")
        if outcome["learning_eligible"] is not True:
            continue
        prefix = read_sequence_prefix(
            root,
            expected_plan_sha256=expected_plan_sha256,
            source_sha256=source_sha256,
            outcome_sha256=digests[:ordinal],
            boundary_sha256=outcome["before_state_sha256"],
        )
        intent = _read(root / f"step-{ordinal:03d}" / "intent.json")
        decision = _read(root / f"step-{ordinal:03d}" / "decision.json")
        menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
        selected = decision["selected_candidate_index"]
        context = projection.story_contexts[len(anchors)]
        history = recorded_option_history(prefix, kind=outcome["selected_kind"],
            objective_ref=context, history_contract=history_contract,
            boundary_sha256=outcome["before_state_sha256"],
            expected_source_sha256=source_sha256, expected_plan_sha256=expected_plan_sha256)
        expected_anchor = dict(
            schema="pokemon.player.sequence-anchor.v1",
            ordinal=ordinal,
            model_choice_index=len(anchors),
            before_sha256=outcome["before_state_sha256"],
            decision_sha256=canonical_sha256(dict(intent=intent, decision=decision)),
            previous_outcome_sha256=list(digests[:ordinal]),
            selected_candidate_index=selected,
            behavior_probability=decision["probabilities"][selected],
            features=list(
                menu.candidates[selected].vector(menu.context, feature_version=version)
                + history.vector()
            ),
            private_identity_feature_count=0,
            training_eligible=False,
        )
        name = f"anchor-{len(anchors):03d}.json"
        expected_files.add(name)
        if not _matches(_read(sequence / name), expected_anchor):
            raise ValueError("sequence pre-input anchor differs")
        anchors.append(expected_anchor)
        ordinals.append(ordinal)
    windows: list[ReconstructedSequence] = []
    for start in range(0, len(anchors), stride):
        stop = min(start + horizon, len(anchors))
        prefix_stop = ordinals[stop] if stop < len(ordinals) else len(outcomes)
        steps = projection.choices[start:stop]
        measurement = measure_sequence(
            steps,
            horizon=horizon,
            end=(
                SequenceEnd.TASK_TERMINAL
                if terminal_claim is not None and stop == len(anchors)
                else SequenceEnd.HORIZON
                if stop - start == horizon
                else SequenceEnd.INTERRUPTED
            ),
            initial_quests=projection.initial_quests
            if start == 0
            else projection.choices[start - 1].quests,
        )
        expected_window = dict(
            schema="pokemon.player.sequence-window-candidate.v2"
            if task is not None
            else "pokemon.player.sequence-window-candidate.v1",
            **(
                {
                    "target_contract": target_contract,
                    "task_terminal": measurement.end is SequenceEnd.TASK_TERMINAL,
                }
                if task is not None
                else {}
            ),
            anchor_sha256=canonical_sha256(anchors[start]),
            first_model_choice=start,
            prefix_outcome_sha256=list(digests[:prefix_stop]),
            measurement=asdict(measurement),
            complete_window=measurement.complete_window,
            cash_accounting_basis=measurement.cash_accounting_basis,
            native_verification_required=True,
            loss_accounting_complete=False,
            training_eligible=False,
        )
        name = f"window-{len(windows):03d}.json"
        expected_files.add(name)
        if not _matches(_read(sequence / name), expected_window):
            raise ValueError("sequence measured window differs")
        windows.append(
            ReconstructedSequence(
                canonical_sha256(anchors[start]),
                canonical_sha256(expected_window),
                tuple(anchors[start]["features"]),
                anchors[start]["behavior_probability"],
                measurement,
                unverified_sequence_targets(measurement, target_contract=target_contract),
                target_contract,
            )
        )
    if not _matches(
        _read(sequence / "result.json"),
        dict(
            schema="pokemon.player.sequence-collection-result.v3"
            if overlapping
            else "pokemon.player.sequence-collection-result.v2"
            if task is not None
            else "pokemon.player.sequence-collection-result.v1",
            **(
                {
                    "target_contract": target_contract,
                    "task_terminal_claim_sha256": None
                    if terminal_claim is None
                    else canonical_sha256(terminal_claim),
                }
                if task is not None
                else {}
            ),
            horizon=horizon,
            **({"window_stride": stride} if overlapping else {}),
            anchors=len(anchors),
            windows=len(windows),
            outcome_sha256=list(digests),
            projection_error=None,
            unprojected_observed_costs=[],
            training_eligible=False,
            fit_calls=0,
            promotions=0,
        ),
    ):
        raise ValueError("sequence collector result differs")
    if {path.name for path in sequence.iterdir()} != expected_files:
        raise ValueError("sequence artifact census differs")
    return tuple(windows)
