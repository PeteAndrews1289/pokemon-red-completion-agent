"""Join existing prospective records with independently read native channels.

Not a dataset admission API: ancestry, safety/executor authority and complete
battle-loss coverage still require their own verified experiment-bound checks.
"""

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .living_dex_option_value import LivingDexOptionValueModel
from .player_sequence_policy import SequencePolicy
from .player_sequence_reconstruction import ReconstructedSequence, reconstruct_sequence_candidates
from .player_sequence_targets import SequenceTargets, sequence_targets, RESOURCE_TASK_TARGET_CONTRACT
from .player_short_sequence import SequenceMeasurement, measure_sequence
from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256
from .red_scoped_training_battlers import ScopedTrainingBattlers
from .red_sequence_battle_audit import audit_scoped_sequence_losses
from .red_sequence_native_audit import audit_native_sequence_trace
from .red_sequence_state_audit import CeruleanSequenceStateReader, audit_sequence_state_channels


@dataclass(frozen=True)
class NativeSequenceTargets:
    original: ReconstructedSequence
    measurement: SequenceMeasurement
    targets: SequenceTargets
    native_channel_audit_sha256: str
    training_eligible: bool = False


def verify_sequence_target_channels(
    root: Path,
    *,
    reader: CeruleanSequenceStateReader,
    store: PrivateArtifactRoot,
    model: LivingDexOptionValueModel,
    source_sha256: str,
    partition: str,
    expected_native_plan_sha256: str,
    expected_actor_plan_sha256: str,
    expected_actor_result_sha256: str,
    expected_declaration_sha256: str,
    expected_catalog_sha256: str,
    expected_task_sha256: str | None = None,
    scoped_battlers: ScopedTrainingBattlers | None = None,
    expected_scope_sha256: str | None = None,
    sequence_policy: SequencePolicy | None = None,
    actor_work_order: Path | None = None,
) -> tuple[NativeSequenceTargets, ...]:
    """Verify six channels; leave incomplete horizons and battle losses masked.

    All expected hashes must be pinned externally; calling this with hashes computed
    from historical data does not grant prospective authority or create TRAIN data.
    Original collector measurements remain retained beside native-corrected counts.
    """
    trace = audit_native_sequence_trace(
        root,
        store=store,
        model=model,
        expected_native_plan_sha256=expected_native_plan_sha256,
        expected_actor_result_sha256=expected_actor_result_sha256,
        source_sha256=source_sha256,
        sequence_policy=sequence_policy,
        actor_work_order=actor_work_order,
    )
    if trace.partition != partition:
        raise ValueError("sequence target source partition differs")
    candidates = reconstruct_sequence_candidates(
        root / "episode",
        source_sha256=source_sha256,
        partition=partition,
        expected_plan_sha256=expected_actor_plan_sha256,
        expected_result_sha256=expected_actor_result_sha256,
        expected_declaration_sha256=expected_declaration_sha256,
        expected_task_sha256=expected_task_sha256,
    )
    state = audit_sequence_state_channels(
        root / "episode",
        reader=reader,
        source_sha256=source_sha256,
        expected_plan_sha256=expected_actor_plan_sha256,
        expected_result_sha256=expected_actor_result_sha256,
        expected_catalog_sha256=expected_catalog_sha256,
    )
    from .player_sequence_targets import TASK_TARGET_CONTRACTS
    from .player_short_sequence import SequenceEnd

    if any(c.target_contract in TASK_TARGET_CONTRACTS for c in candidates):
        if (
            expected_task_sha256 is None
            or getattr(reader, "task_sha256", None) != expected_task_sha256
        ):
            raise ValueError("native task reader differs from prospective task")
    if (scoped_battlers is None) != (expected_scope_sha256 is None):
        raise ValueError("sequence scoped loss audit identity is incomplete")
    losses = None
    if scoped_battlers is not None:
        assert expected_scope_sha256 is not None
        losses = audit_scoped_sequence_losses(
            root,
            pool=scoped_battlers,
            expected_native_plan_sha256=expected_native_plan_sha256,
            expected_scope_sha256=expected_scope_sha256,
            expected_actor_plan_sha256=expected_actor_plan_sha256,
            expected_actor_result_sha256=expected_actor_result_sha256,
            source_sha256=source_sha256,
        )
        state = replace(
            state,
            steps=tuple(
                replace(step, blackouts=loss)
                for step, loss in zip(
                    state.steps,
                    losses.model_losses,
                    strict=True,
                )
            ),
        )
    digest = canonical_sha256(
        dict(
            trace=asdict(trace),
            state=asdict(state),
            scoped_losses=None if losses is None else asdict(losses),
        )
    )
    covered_choices: set[int] = set()
    result = []
    for index, candidate in enumerate(candidates):
        original = candidate.measurement
        # Reconstruction has already authenticated this recorded start. Bind the
        # reread to that exact window before slicing overlapping native choices.
        window = json.loads(
            (root / "episode" / "sequence" / f"window-{index:03d}.json").read_bytes()
        )
        if canonical_sha256(window) != candidate.window_sha256:
            raise ValueError("recorded native sequence window differs")
        start = window.get("first_model_choice")
        if type(start) is not int or start < 0 or original.observed_steps <= 0:
            raise ValueError("native sequence window start or size is invalid")
        end = start + original.observed_steps
        if end > len(state.steps):
            raise ValueError("native sequence window exceeds audited boundaries")
        if original.end is SequenceEnd.TASK_TERMINAL:
            # A later success cannot supply this window's terminal predicate.
            required = set(getattr(reader, "task_progress", ()))
            initial = state.initial_progress if start == 0 else state.steps[start - 1].progress
            terminal = state.steps[end - 1].progress
            predicate = getattr(reader, "task_completed", None)
            completed = (
                predicate(initial, terminal) if predicate is not None else
                bool(required and not required & set(initial) and required <= set(terminal))
            )
            if completed is not True:
                raise ValueError("native task-terminal predicate was not newly completed")
        measured = measure_sequence(
            state.steps[start:end],
            horizon=original.horizon,
            end=original.end,
            initial_progress=(
                state.initial_progress if start == 0 else state.steps[start - 1].progress
            ),
            initial_quests=state.initial_quests if start == 0 else state.steps[start - 1].quests,
        )
        if (
            replace(
                measured,
                new_progress=original.new_progress,
                completed_quests=original.completed_quests,
                blackouts=original.blackouts,
            )
            != original
        ):
            raise ValueError("native sequence window differs beyond audited progress channels")
        medicine = None
        if candidate.target_contract == RESOURCE_TASK_TARGET_CONTRACT:
            valuator = getattr(reader, "priced_medicine_depletion", None)
            if not callable(valuator):
                raise ValueError("resource task requires an independent native medicine reader")
            medicine = valuator(state.steps[start].before_sha256, state.steps[end - 1].after_sha256)
        result.append(
            NativeSequenceTargets(
                candidate,
                measured,
                sequence_targets(
                    measured,
                    target_contract=candidate.target_contract,
                    priced_medicine_depletion=medicine,
                    covered=getattr(
                        reader,
                        "target_channels",
                        frozenset(
                            {
                                "native_progress",
                                "completed_quests",
                                "actions",
                                "frames",
                                "observed_cash_debits",
                                "observed_cash_credits",
                            }
                        ),
                    ),
                ),
                digest,
            )
        )
        covered_choices.update(range(start, end))
    if covered_choices != set(range(len(state.steps))):
        raise ValueError("native sequence target census differs")
    return tuple(result)
