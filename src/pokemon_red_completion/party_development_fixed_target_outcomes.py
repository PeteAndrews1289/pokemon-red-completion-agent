"""Fixed-level, fully-restored comparison using existing records.

No new serialized binding/campaign schema, runtime, evaluator or fitter. Existing
v2/v3 objectives and adapters are untouched. The trusted native materializer must
authenticate endpoint receipt hashes and retained specimen/home bindings before
constructing ReadyEndpointEvidence; this pure adapter cannot inspect a cartridge
or prove private native identity from a PartyObservation.

Initial scope is completed, non-evolving BALANCE/VENUE tasks only. Ordinary
partial/error native receipts stay retained elsewhere; they are not assigned a
cheap completed-task cost by this adapter.
"""
from dataclasses import asdict, dataclass
from math import isclose
import re

from pokemon_red_completion.party import PartyObservation, StatusCondition
from pokemon_red_completion.party_development_catalog import PartyDevelopmentProspectiveBinding
from pokemon_red_completion.party_development_rank import (
    PartyDevelopmentCandidateSet, PartyDevelopmentGoal,
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID,
)
from pokemon_red_completion.party_development_outcomes import (
    PartyDevelopmentOutcomeTrialV2, _require_shared_start, _criterion_values,
    _trial_evidence,
)
from pokemon_red_completion.player_option_level_workload import (
    OptionLevelWorkload, level_workload_feature_names,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome, OutcomeCandidate, OutcomeCriterion, OutcomeDirection,
    OutcomeEvidenceStatus, OutcomeObjective, ScenarioOutcomeExample, ScenarioOutcomeError,
)
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

FIXED_LEVEL_READY_OBJECTIVE = OutcomeObjective(
    "party-development.fixed-level-ready-task-cost.v1",
    ScenarioFamily.PARTY_DEVELOPMENT,
    (
        OutcomeCriterion("party.no-blackout", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.completion-no-regression", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.fixed-level-ready-completed", OutcomeDirection.MAXIMIZE, 0),
        OutcomeCriterion("party.completed-task-frames", OutcomeDirection.MINIMIZE, 0),
        OutcomeCriterion("party.faints", OutcomeDirection.MINIMIZE, 0),
        OutcomeCriterion("party.useful-target-xp", OutcomeDirection.MAXIMIZE, 0),
    ),
)

def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ScenarioOutcomeError("fixed-level contract needs an exact SHA256")

def observed_party_sha256(party):
    if not isinstance(party, PartyObservation):
        raise TypeError("fixed-level evidence requires a typed party")
    return canonical_sha256(asdict(party))

@dataclass(frozen=True, slots=True)
class FixedLevelReadyContract:
    """Private semantic binding, never candidate features or a learned label."""
    workload: OptionLevelWorkload
    source_party_sha256: str
    target_slot: int
    recipient_binding_sha256: str
    home_binding_sha256_by_candidate: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.workload, OptionLevelWorkload):
            raise TypeError("fixed-level contract needs a typed target workload")
        if type(self.target_slot) is not int or self.target_slot < 1:
            raise ScenarioOutcomeError("fixed-level target slot differs")
        _digest(self.source_party_sha256)
        _digest(self.recipient_binding_sha256)
        if (not isinstance(self.home_binding_sha256_by_candidate, tuple)
                or len(self.home_binding_sha256_by_candidate) < 2):
            raise ScenarioOutcomeError("fixed-level venue homes must align with a paired menu")
        for value in self.home_binding_sha256_by_candidate:
            _digest(value)

    def semantic_snapshot_sha256(self, original_semantic_snapshot_sha256):
        _digest(original_semantic_snapshot_sha256)
        return canonical_sha256(dict(
            base_semantic_snapshot_sha256=original_semantic_snapshot_sha256,
            fixed_level_ready_contract=asdict(self),
            endpoint="declared-home-field-return-with-full-party-hp-status-and-pp",
        ))

@dataclass(frozen=True, slots=True)
class ReadyEndpointEvidence:
    """Trusted materializer output bound to independently authenticated native evidence.

    field_return_verified means exact candidate home, settled field control and
    released buttons were checked against native receipts. Party readiness is
    independently recomputed here. Private recipient continuity is authenticated
    by the materializer, not guessed from species or party position.
    """
    candidate_index: int
    source_state_sha256: str
    terminal_state_sha256: str
    terminal_party_sha256: str
    recipient_binding_sha256: str
    home_binding_sha256: str
    native_receipt_sha256: str
    field_return_verified: bool
    controller_actions: int
    frames_executed: int

    def __post_init__(self):
        if type(self.candidate_index) is not int or self.candidate_index < 0:
            raise ScenarioOutcomeError("endpoint candidate differs")
        for name in ("source_state_sha256", "terminal_state_sha256", "terminal_party_sha256",
                     "recipient_binding_sha256", "home_binding_sha256", "native_receipt_sha256"):
            _digest(getattr(self, name))
        if type(self.field_return_verified) is not bool:
            raise ScenarioOutcomeError("endpoint field proof must be explicit")
        for name in ("controller_actions", "frames_executed"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ScenarioOutcomeError("completed endpoint needs positive physical cost")

def _require_menu(candidate_set, contract):
    if not isinstance(candidate_set, PartyDevelopmentCandidateSet):
        raise TypeError("fixed-level task requires typed candidates")
    if not isinstance(contract, FixedLevelReadyContract):
        raise TypeError("fixed-level task requires its prospective contract")
    if (candidate_set.goal is not PartyDevelopmentGoal.BALANCE
            or candidate_set.kind is not TrainingChoiceKind.VENUE
            or candidate_set.feature_schema_id != PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID
            or len(candidate_set.candidates) != len(contract.home_binding_sha256_by_candidate)):
        raise ScenarioOutcomeError("fixed-level ready task needs one BALANCE venue workload")
    names = candidate_set.feature_names
    indexes = tuple(names.index(name) for name in level_workload_feature_names())
    for candidate in candidate_set.candidates:
        if any(not isclose(candidate.features[i], expected, rel_tol=0, abs_tol=1e-12)
               for i, expected in zip(indexes, contract.workload.vector(), strict=True)):
            raise ScenarioOutcomeError("candidate workload differs from fixed target contract")
        if not isclose(candidate.features[names.index("candidate.level")],
                       contract.workload.current_level / 100, rel_tol=0, abs_tol=1e-12):
            raise ScenarioOutcomeError("candidate starting level differs from fixed target")

def freeze_fixed_level_ready_binding(candidate_set, contract, *,
                                     original_semantic_snapshot_sha256, **binding_fields):
    """Call before native input; return the existing prospective binding type."""
    _require_menu(candidate_set, contract)
    if {"candidate_set", "semantic_snapshot_sha256", "outcome_objective_sha256"} & binding_fields.keys():
        raise ScenarioOutcomeError("caller cannot replace fixed task binding semantics")
    return PartyDevelopmentProspectiveBinding.build(
        candidate_set=candidate_set,
        semantic_snapshot_sha256=contract.semantic_snapshot_sha256(original_semantic_snapshot_sha256),
        outcome_objective_sha256=FIXED_LEVEL_READY_OBJECTIVE.objective_sha256,
        **binding_fields,
    )

def _fully_restored(party):
    if not party.members:
        return False
    for member in party.members:
        known = tuple(move for move in member.moves if move.is_known)
        if (member.hp != member.max_hp or member.status is not StatusCondition.HEALTHY
                or not known
                or any(move.max_pp is None or move.current_pp != move.max_pp for move in known)):
            return False
    return True

def adapt_fixed_level_ready_outcomes(candidate_set, trials, endpoints, *,
                                    contract, prospective_binding,
                                    original_semantic_snapshot_sha256,
                                    measurement_partition=ScenarioPartition.TRAIN):
    """Admit completed ready measurements in an explicitly permitted partition.

    Existing calls remain TRAIN-only. DEVELOPMENT is an opt-in measurement,
    not permission to fit or to relabel a source; the trusted materializer must
    authenticate the source role before constructing its prospective binding.
    """
    if (not isinstance(measurement_partition, ScenarioPartition)
            or measurement_partition not in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT)):
        raise ScenarioOutcomeError("fixed-level measurement partition must be TRAIN or DEVELOPMENT")
    _require_menu(candidate_set, contract)
    if not isinstance(prospective_binding, PartyDevelopmentProspectiveBinding):
        raise TypeError("fixed-level task requires its existing prospective binding")
    prospective_binding.require_candidate_set(candidate_set)
    if prospective_binding.partition is not measurement_partition:
        raise ScenarioOutcomeError("fixed-level measurement partition differs from prospective binding")
    if (prospective_binding.outcome_objective_sha256 != FIXED_LEVEL_READY_OBJECTIVE.objective_sha256
            or prospective_binding.semantic_snapshot_sha256
            != contract.semantic_snapshot_sha256(original_semantic_snapshot_sha256)):
        raise ScenarioOutcomeError("fixed-level prospective objective or target was substituted")
    if (not isinstance(trials, tuple) or not isinstance(endpoints, tuple)
            or len(trials) != len(candidate_set.candidates) or len(endpoints) != len(trials)
            or any(not isinstance(t, PartyDevelopmentOutcomeTrialV2) for t in trials)
            or any(not isinstance(e, ReadyEndpointEvidence) for e in endpoints)):
        raise ScenarioOutcomeError("fixed-level comparison requires every typed paired endpoint")
    _require_shared_start(candidate_set, trials)
    ordered = sorted(zip(trials, endpoints, strict=True), key=lambda pair: pair[0].candidate_index)
    if tuple(t.candidate_index for t, _ in ordered) != tuple(range(len(trials))):
        raise ScenarioOutcomeError("fixed-level paired candidates repeat or are absent")
    outcomes = []
    for trial, endpoint in ordered:
        index = trial.candidate_index
        if (trial.candidate != candidate_set.candidates[index]
                or not prospective_binding.candidate_available[index]
                or trial.censored
                or trial.target_slot != contract.target_slot
                or observed_party_sha256(trial.before_party) != contract.source_party_sha256
                or endpoint.candidate_index != index
                or endpoint.source_state_sha256 != prospective_binding.initial_state_sha256
                or endpoint.terminal_party_sha256 != observed_party_sha256(trial.after_party)
                or endpoint.recipient_binding_sha256 != contract.recipient_binding_sha256
                or endpoint.home_binding_sha256 != contract.home_binding_sha256_by_candidate[index]
                or endpoint.frames_executed != trial.frames_executed
                or not endpoint.field_return_verified):
            raise ScenarioOutcomeError("fixed-level endpoint does not match source/recipient/home/cost")
        before = trial.before_party.member_in_slot(trial.target_slot)
        after = trial.after_party.member_in_slot(trial.resolved_after_target_slot)
        if before is None or after is None or before.experience is None or after.experience is None:
            raise ScenarioOutcomeError("fixed-level recipient XP is unknown")
        if before.level != contract.workload.current_level:
            raise ScenarioOutcomeError("fixed-level recipient initial level differs")
        gained = after.experience - before.experience
        if (after.level < contract.workload.target_level or gained < contract.workload.remaining_xp
                or not _fully_restored(trial.after_party)):
            raise ScenarioOutcomeError("full ready endpoint unobserved; retain raw partial evidence")
        # Scope deliberately excludes natural evolution; do not counterfeit or
        # erase it to enter this first fixed-level cost comparison.
        if (trial.evolution_completed or before.species_id != after.species_id
                or trial.completion_before.evolution_steps_remaining
                != trial.completion_after.evolution_steps_remaining):
            raise ScenarioOutcomeError("natural evolution requires a separately qualified fixed-task adapter")
        legacy = _criterion_values(candidate_set.goal, trial)
        if legacy[0] != 1.0 or legacy[1] != 1.0:
            raise ScenarioOutcomeError("fixed-level ready task regressed completion or blacked out")
        useful_xp = min(gained, contract.workload.remaining_xp)
        evidence = dict(trial=_trial_evidence(trial), endpoint=asdict(endpoint),
                        contract=asdict(contract), useful_target_xp=useful_xp)
        outcomes.append(CandidateOutcome(
            status=OutcomeEvidenceStatus.MEASURED,
            criterion_values=(1.0, 1.0, 1.0, float(trial.frames_executed),
                              float(legacy[13]), float(useful_xp)),
            actions_executed=endpoint.controller_actions, frames_executed=trial.frames_executed,
            evidence_sha256=canonical_sha256(evidence)))
    example = ScenarioOutcomeExample(
        scenario_id=prospective_binding.scenario_id,
        root_lineage_id=prospective_binding.root_lineage_id,
        initial_state_sha256=prospective_binding.initial_state_sha256,
        partition=prospective_binding.partition, objective=FIXED_LEVEL_READY_OBJECTIVE,
        feature_schema_id=candidate_set.feature_schema_id, feature_names=candidate_set.feature_names,
        candidates=tuple(OutcomeCandidate(c.candidate_index, c.features,
                         prospective_binding.candidate_available[c.candidate_index])
                         for c in candidate_set.candidates),
        outcomes=tuple(outcomes), prospective_binding_sha256=prospective_binding.binding_sha256)
    prospective_binding.require_matches(example)
    return example
