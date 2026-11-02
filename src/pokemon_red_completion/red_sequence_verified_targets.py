"""Join existing prospective records with independently read native channels.

Not a dataset admission API: ancestry, safety/executor authority and complete
battle-loss coverage still require their own verified experiment-bound checks.
"""

from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .living_dex_option_value import LivingDexOptionValueModel
from .player_sequence_policy import SequencePolicy
from .player_sequence_reconstruction import ReconstructedSequence, reconstruct_sequence_candidates
from .player_sequence_targets import SequenceTargets, sequence_targets
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
    root: Path, *, reader: CeruleanSequenceStateReader, store: PrivateArtifactRoot,
    model: LivingDexOptionValueModel, source_sha256: str, partition: str,
    expected_native_plan_sha256: str, expected_actor_plan_sha256: str,
    expected_actor_result_sha256: str, expected_declaration_sha256: str,
    expected_catalog_sha256: str,
    scoped_battlers: ScopedTrainingBattlers | None = None,
    expected_scope_sha256: str | None = None,
    sequence_policy: SequencePolicy | None = None,
) -> tuple[NativeSequenceTargets, ...]:
    """Verify six channels; leave incomplete horizons and battle losses masked.

All expected hashes must be pinned externally; calling this with hashes computed
from historical data does not grant prospective authority or create TRAIN data.
Original collector measurements remain retained beside native-corrected counts.
"""
    trace = audit_native_sequence_trace(
        root, store=store, model=model, expected_native_plan_sha256=expected_native_plan_sha256,
        expected_actor_result_sha256=expected_actor_result_sha256, source_sha256=source_sha256,
        sequence_policy=sequence_policy,
    )
    if trace.partition != partition:
        raise ValueError("sequence target source partition differs")
    candidates = reconstruct_sequence_candidates(
        root / "episode", source_sha256=source_sha256, partition=partition,
        expected_plan_sha256=expected_actor_plan_sha256,
        expected_result_sha256=expected_actor_result_sha256,
        expected_declaration_sha256=expected_declaration_sha256,
    )
    state = audit_sequence_state_channels(
        root / "episode", reader=reader, source_sha256=source_sha256,
        expected_plan_sha256=expected_actor_plan_sha256,
        expected_result_sha256=expected_actor_result_sha256,
        expected_catalog_sha256=expected_catalog_sha256,
    )
    if (scoped_battlers is None) != (expected_scope_sha256 is None):
        raise ValueError("sequence scoped loss audit identity is incomplete")
    losses = None
    if scoped_battlers is not None:
        assert expected_scope_sha256 is not None
        losses = audit_scoped_sequence_losses(
            root, pool=scoped_battlers, expected_native_plan_sha256=expected_native_plan_sha256,
            expected_scope_sha256=expected_scope_sha256,
            expected_actor_plan_sha256=expected_actor_plan_sha256,
            expected_actor_result_sha256=expected_actor_result_sha256,
            source_sha256=source_sha256,
        )
        state = replace(state, steps=tuple(
            replace(step, blackouts=loss) for step, loss in zip(
                state.steps, losses.model_losses, strict=True,
            )
        ))
    digest = canonical_sha256(dict(trace=asdict(trace), state=asdict(state),
                                   scoped_losses=None if losses is None else asdict(losses)))
    offset = 0
    result = []
    for candidate in candidates:
        original = candidate.measurement
        end = offset + original.observed_steps
        measured = measure_sequence(
            state.steps[offset:end], horizon=original.horizon, end=original.end,
            initial_progress=(state.initial_progress if offset == 0
                              else state.steps[offset - 1].progress),
            initial_quests=state.initial_quests if offset == 0 else state.steps[offset - 1].quests,
        )
        if replace(measured, new_progress=original.new_progress,
                   completed_quests=original.completed_quests,
                   blackouts=original.blackouts) != original:
            raise ValueError("native sequence window differs beyond audited progress channels")
        result.append(NativeSequenceTargets(
            candidate, measured, sequence_targets(measured, covered=frozenset({
                "native_progress", "completed_quests", "actions", "frames",
                "observed_cash_debits", "observed_cash_credits",
            })), digest,
        ))
        offset = end
    if offset != len(state.steps):
        raise ValueError("native sequence target census differs")
    return tuple(result)
