"""Source-only qualification of Red venue evidence for party development.

The portable learner sees only unit measurements and digests.  This adapter
owns the Red-specific work needed to justify those measurements: it checks the
published prospective plan against its immutable outcome receipt, binds the
observation to the current Route 11 execution contract, and refuses to reuse
the simultaneously measured Cave outcome after that venue's traversal changed.

No ROM, emulator, controller, teacher, or outcome runner is used here.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import re
import textwrap
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

import pokemon_red_completion.battle_runtime as battle_runtime_module
import pokemon_red_completion.blaine as blaine_module
import pokemon_red_completion.celadon as celadon_module
import pokemon_red_completion.party as party_module
import pokemon_red_completion.red_team_training as red_team_training_module
import pokemon_red_completion.team_training as team_training_module
import pokemon_red_completion.training_candidate_rank as training_candidate_rank_module
import pokemon_red_completion.training_venue as training_venue_module
from pokemon_red_completion.battle_runtime import run_adaptive_wild_battle
from pokemon_red_completion.blaine import (
    DIGLETT_SPECIES_ID,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TEAM_POLICY,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_VOLATILE_ENEMY_SPECIES,
    ROUTE_11_TRAINING_VENUE,
    VERMILION_CENTER_TO_ROUTE_11,
    VERMILION_NURSE_TO_EXIT,
    VERMILION_ROUTE_11_TO_CENTER_EXTERIOR,
    _flee,
    _heal,
    _move,
    _pulse,
    _route_11_heal_and_return,
    _route_11_training_venue,
    _route_11_walk_to_grass,
    _team_training_move_guard,
    _team_training_move_slot,
    _training_dig_to_vermilion,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import (
    committed_executable_source_blob,
    committed_source_bundle_sha256,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.party import (
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorMeasurementContract,
    VenuePriorObservation,
    VenuePriorOperationalContract,
    VenuePriorSourceCompatibilityAttestation,
    compose_venue_prior_evidence,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
)
from pokemon_red_completion.red_team_training import (
    TRAINING_ATTACK_PP_RESERVE,
    TRAINING_MOVE_IDS,
    TeamTrainingExecutionSummary,
    run_red_team_balancing,
    trainee_should_fight_directly,
    training_attack_pp,
    training_attack_pp_reserve,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
    member_can_train_at,
    member_needs_training,
    training_safety_ceiling,
)
from pokemon_red_completion.training_candidate_rank import (
    TrainingCandidate,
    TrainingCandidateDecision,
    TrainingCandidateRankError,
    TrainingCandidateSet,
    TrainingChoiceKind,
    _candidate_features,
    _eligible_trainees,
    _eligible_venues,
    _ratio,
    _ratio_float,
    _signed_ratio,
    bind_trainee_candidate,
    bind_venue_candidate,
    project_trainee_candidates,
    project_trainee_choice_set,
    project_venue_candidates,
    project_venue_choice_set,
)
from pokemon_red_completion.training_venue import TrainingVenue

RED_ROUTE_11_VENUE_PRIOR_COMPOSITION_SCHEMA = (
    "pokemon.red.party-development-route-11-venue-prior-composition.v1"
)
RED_PARTY_DEVELOPMENT_OUTCOME_SCENARIO_ID = (
    "red-party-development-evolution-venue-v2"
)
RED_ROUTE_11_VENUE_PRIOR_EVIDENCE_ID = "red-route-11-evolution-prior-v1"
RED_ROUTE_11_VENUE_OPERATIONAL_CONTRACT_ID = (
    "red-route-11-bounded-evolution-runtime-v1"
)
RED_ROUTE_11_SUPPORT_CHECKPOINT_ID = "red-goal-v1-029-evolve_species-train-02"
RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT = (
    "00499bc68b099ffcd0125a6777bc3b836a84ff0b"
)
RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256 = (
    "969f6ae2f60282848d26d4097fcefe6e9881f3739d78b560bdf0f186482f6294"
)
RED_PARTY_DEVELOPMENT_OUTCOME_PLAN_SHA256 = (
    "24bc09099260e7dea14c8e759fcc2ed3a97c19486379c06bcf728ad168e46493"
)
RED_PARTY_DEVELOPMENT_OUTCOME_RESULT_SHA256 = (
    "a182025184383d7e2d8d1bdaa4d1c4477dca7136b5005cc78667e5c7d0132036"
)
RED_ROUTE_11_SOURCE_COMPATIBILITY_ATTESTATION_ID = (
    "red-route-11-00499bc-runtime-compatibility-v1"
)
RED_ROUTE_11_STATELESS_WALKER_AST_SHA256 = (
    "8ae1a58bc11bd7801ba229fae4afbcb292d9e34c484d42b97e32694116b45522"
)

RED_PARTY_DEVELOPMENT_OUTCOME_POLICY = replace(
    MANSION_TEAM_POLICY,
    retreat_hp_ratio=0.45,
    reserve_total_pp=2,
    max_battles=200,
    max_steps=20_000,
    max_healing_trips=50,
    max_faints=0,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


@dataclass(frozen=True, slots=True)
class _SourceElement:
    element_id: str
    relative_path: str
    qualname: str
    current_object: Callable[..., object] | type[object] | ModuleType
    kind: Literal["definition", "module_assignments"] = "definition"


@dataclass(frozen=True, slots=True)
class _SourceCompatibilityWaiver:
    element_id: str
    observed_ast_sha256: str | None
    current_ast_sha256: str
    justification_id: str

    def public_dict(self) -> dict[str, object]:
        return {
            "element_id": self.element_id,
            "observed_ast_sha256": self.observed_ast_sha256,
            "current_ast_sha256": self.current_ast_sha256,
            "justification_id": self.justification_id,
        }


_ROUTE_11_SOURCE_ELEMENTS = (
    _SourceElement(
        "training-venue.contract",
        "src/pokemon_red_completion/training_venue.py",
        "TrainingVenue",
        TrainingVenue,
    ),
    _SourceElement(
        "core.grinding-area",
        "src/pokemon_red_completion/team_training.py",
        "GrindingArea",
        GrindingArea,
    ),
    _SourceElement(
        "core.balanced-team-policy",
        "src/pokemon_red_completion/team_training.py",
        "BalancedTeamPolicy",
        BalancedTeamPolicy,
    ),
    _SourceElement(
        "core.party-member-observation",
        "src/pokemon_red_completion/party.py",
        "PartyMemberObservation",
        PartyMemberObservation,
    ),
    _SourceElement(
        "core.party-observation",
        "src/pokemon_red_completion/party.py",
        "PartyObservation",
        PartyObservation,
    ),
    _SourceElement(
        "core.status-condition",
        "src/pokemon_red_completion/party.py",
        "StatusCondition",
        StatusCondition,
    ),
    _SourceElement(
        "core.training-candidate-error",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "TrainingCandidateRankError",
        TrainingCandidateRankError,
    ),
    _SourceElement(
        "core.training-candidate",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "TrainingCandidate",
        TrainingCandidate,
    ),
    _SourceElement(
        "core.training-candidate-set",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "TrainingCandidateSet",
        TrainingCandidateSet,
    ),
    _SourceElement(
        "core.training-candidate-decision",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "TrainingCandidateDecision",
        TrainingCandidateDecision,
    ),
    _SourceElement(
        "core.training-choice-kind",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "TrainingChoiceKind",
        TrainingChoiceKind,
    ),
    _SourceElement(
        "core.project-trainee-candidates",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "project_trainee_candidates",
        project_trainee_candidates,
    ),
    _SourceElement(
        "core.project-trainee-choice-set",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "project_trainee_choice_set",
        project_trainee_choice_set,
    ),
    _SourceElement(
        "core.project-venue-candidates",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "project_venue_candidates",
        project_venue_candidates,
    ),
    _SourceElement(
        "core.project-venue-choice-set",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "project_venue_choice_set",
        project_venue_choice_set,
    ),
    _SourceElement(
        "core.bind-trainee-candidate",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "bind_trainee_candidate",
        bind_trainee_candidate,
    ),
    _SourceElement(
        "core.bind-venue-candidate",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "bind_venue_candidate",
        bind_venue_candidate,
    ),
    _SourceElement(
        "core.eligible-trainees",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "_eligible_trainees",
        _eligible_trainees,
    ),
    _SourceElement(
        "core.eligible-venues",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "_eligible_venues",
        _eligible_venues,
    ),
    _SourceElement(
        "core.candidate-features",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "_candidate_features",
        _candidate_features,
    ),
    _SourceElement(
        "core.candidate-ratio",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "_ratio",
        _ratio,
    ),
    _SourceElement(
        "core.candidate-ratio-float",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "_ratio_float",
        _ratio_float,
    ),
    _SourceElement(
        "core.candidate-signed-ratio",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "_signed_ratio",
        _signed_ratio,
    ),
    _SourceElement(
        "core.member-can-train-at",
        "src/pokemon_red_completion/team_training.py",
        "member_can_train_at",
        member_can_train_at,
    ),
    _SourceElement(
        "core.member-needs-training",
        "src/pokemon_red_completion/team_training.py",
        "member_needs_training",
        member_needs_training,
    ),
    _SourceElement(
        "core.training-safety-ceiling",
        "src/pokemon_red_completion/team_training.py",
        "training_safety_ceiling",
        training_safety_ceiling,
    ),
    _SourceElement(
        "red.route-11-training-venue",
        "src/pokemon_red_completion/blaine.py",
        "_route_11_training_venue",
        _route_11_training_venue,
    ),
    _SourceElement(
        "red.route-11-walk-to-grass",
        "src/pokemon_red_completion/blaine.py",
        "_route_11_walk_to_grass",
        _route_11_walk_to_grass,
    ),
    _SourceElement(
        "red.run-team-balancing",
        "src/pokemon_red_completion/red_team_training.py",
        "run_red_team_balancing",
        run_red_team_balancing,
    ),
    _SourceElement(
        "red.route-11-heal-and-return",
        "src/pokemon_red_completion/blaine.py",
        "_route_11_heal_and_return",
        _route_11_heal_and_return,
    ),
    _SourceElement(
        "red.training-dig-to-vermilion",
        "src/pokemon_red_completion/blaine.py",
        "_training_dig_to_vermilion",
        _training_dig_to_vermilion,
    ),
    _SourceElement(
        "red.move",
        "src/pokemon_red_completion/blaine.py",
        "_move",
        _move,
    ),
    _SourceElement(
        "red.pulse",
        "src/pokemon_red_completion/blaine.py",
        "_pulse",
        _pulse,
    ),
    _SourceElement(
        "red.heal",
        "src/pokemon_red_completion/blaine.py",
        "_heal",
        _heal,
    ),
    _SourceElement(
        "red.flee",
        "src/pokemon_red_completion/celadon.py",
        "_flee",
        _flee,
    ),
    _SourceElement(
        "red.adaptive-wild-battle",
        "src/pokemon_red_completion/battle_runtime.py",
        "run_adaptive_wild_battle",
        run_adaptive_wild_battle,
    ),
    _SourceElement(
        "red.team-training-move-slot",
        "src/pokemon_red_completion/blaine.py",
        "_team_training_move_slot",
        _team_training_move_slot,
    ),
    _SourceElement(
        "red.team-training-move-guard",
        "src/pokemon_red_completion/blaine.py",
        "_team_training_move_guard",
        _team_training_move_guard,
    ),
    _SourceElement(
        "red.trainee-fights-directly",
        "src/pokemon_red_completion/red_team_training.py",
        "trainee_should_fight_directly",
        trainee_should_fight_directly,
    ),
    _SourceElement(
        "red.training-attack-pp",
        "src/pokemon_red_completion/red_team_training.py",
        "training_attack_pp",
        training_attack_pp,
    ),
    _SourceElement(
        "red.training-attack-pp-reserve",
        "src/pokemon_red_completion/red_team_training.py",
        "training_attack_pp_reserve",
        training_attack_pp_reserve,
    ),
    _SourceElement(
        "red.team-training-execution-summary",
        "src/pokemon_red_completion/red_team_training.py",
        "TeamTrainingExecutionSummary",
        TeamTrainingExecutionSummary,
    ),
    _SourceElement(
        "core.team-training-progress",
        "src/pokemon_red_completion/team_training.py",
        "TeamTrainingProgress",
        TeamTrainingProgress,
    ),
    _SourceElement(
        "module-assignments.battle-runtime",
        "src/pokemon_red_completion/battle_runtime.py",
        "<module assignments>",
        battle_runtime_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.blaine",
        "src/pokemon_red_completion/blaine.py",
        "<module assignments>",
        blaine_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.celadon",
        "src/pokemon_red_completion/celadon.py",
        "<module assignments>",
        celadon_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.party",
        "src/pokemon_red_completion/party.py",
        "<module assignments>",
        party_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.red-team-training",
        "src/pokemon_red_completion/red_team_training.py",
        "<module assignments>",
        red_team_training_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.team-training",
        "src/pokemon_red_completion/team_training.py",
        "<module assignments>",
        team_training_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.training-candidate-rank",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "<module assignments>",
        training_candidate_rank_module,
        "module_assignments",
    ),
    _SourceElement(
        "module-assignments.training-venue",
        "src/pokemon_red_completion/training_venue.py",
        "<module assignments>",
        training_venue_module,
        "module_assignments",
    ),
)

_ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS = (
    _SourceCompatibilityWaiver(
        element_id="training-venue.contract",
        observed_ast_sha256=(
            "4fbbbd2b289fd575811b85b1d10968a9dd09c33a7abbb67547b649b9a3332747"
        ),
        current_ast_sha256=(
            "748f27949b60ae4137a2b70df849a9def707b04947fc30e59ebf1061e2614c1d"
        ),
        justification_id="run-local-walker-preserves-route-11-venue-contract",
    ),
    _SourceCompatibilityWaiver(
        element_id="core.project-trainee-candidates",
        observed_ast_sha256=(
            "a5a52755b578c8536ecaba3f914b2466bc43000484b6e98b9735d9e3badf854d"
        ),
        current_ast_sha256=(
            "cbfae3d5858f961267b07e425216e5fb33d7fd8097ce02d55bf5388a68e8b62d"
        ),
        justification_id="extract-choice-set-preserves-teacher-trainee-selection",
    ),
    _SourceCompatibilityWaiver(
        element_id="core.project-trainee-choice-set",
        observed_ast_sha256=None,
        current_ast_sha256=(
            "221d1a8d1a9b64f8aa052345b55b70942dc698786f38cb5226765edc85472275"
        ),
        justification_id="added-unlabeled-trainee-menu-preserves-teacher-selection",
    ),
    _SourceCompatibilityWaiver(
        element_id="core.project-venue-candidates",
        observed_ast_sha256=(
            "359da3498012160695e59fbccf3ce4b1f93b1c2dae59d350e414d93d5a205ae4"
        ),
        current_ast_sha256=(
            "4b731e174dcb3ec0412111dbcb7c687f0552405f1a4bd0325ff854728b06bfe7"
        ),
        justification_id="extract-choice-set-preserves-teacher-venue-selection",
    ),
    _SourceCompatibilityWaiver(
        element_id="core.project-venue-choice-set",
        observed_ast_sha256=None,
        current_ast_sha256=(
            "4a4ac69e4e2675fc92e3b3c4d8507c97844d6659dcaaf4c26419d44978926dbb"
        ),
        justification_id="added-unlabeled-venue-menu-preserves-teacher-selection",
    ),
    _SourceCompatibilityWaiver(
        element_id="red.run-team-balancing",
        observed_ast_sha256=(
            "495627fc69c0bcf27872ae53f0e9f26f599f5e1d3873215e7ec115b07fcdd3db"
        ),
        current_ast_sha256=(
            "c419c28563c8f5640e464d4c2ee4fcbc3c360e54da5d4af3e5a3bfc53d2964e6"
        ),
        justification_id=(
            "run-local-walker-zero-telemetry-and-eligible-cardinality-menu-"
            "suppression-plus-opt-in-fixed-dose-preserve-historical-route-11-"
            "default-and-unused-live-guard-fallback-plus-ten-of-fifty-heals-"
            "preserve-measured-path-plus-opt-in-targeted-development-remains-"
            "disabled-on-historical-route-11"
        ),
    ),
    _SourceCompatibilityWaiver(
        element_id="red.route-11-heal-and-return",
        observed_ast_sha256=(
            "5f96285852f9ed925330be02c109b0a8f57d0c9756962df1c84963c7df586299"
        ),
        current_ast_sha256=(
            "ef05d302d3d38aa43ae8949bf78ba882d130c40ae8271ea9a3fe002416e834c5"
        ),
        justification_id=(
            "optional-ground-transition-is-unset-on-historical-route-11-path"
        ),
    ),
    _SourceCompatibilityWaiver(
        element_id="red.training-dig-to-vermilion",
        observed_ast_sha256=(
            "cb1bc40d3a08fce7f511936b5d017dfe3ab244d3ecffdc9cc59f69e84c08bc47"
        ),
        current_ast_sha256=(
            "cc56ace445c78eb815661afadf1fe9ac19d034d6fcb7b1a6c8cc0f95b63f4552"
        ),
        justification_id=(
            "additional-fly-boundary-normalization-preserves-historical-route-"
            "11-and-cinnabar-nurse-paths-and-celadon-only-branch-is-unreached"
        ),
    ),
    _SourceCompatibilityWaiver(
        element_id="red.team-training-execution-summary",
        observed_ast_sha256=(
            "307da86ffe4ac2a7baa7c6ce6873c53db731a128f5c852a28368fa8d9079ca58"
        ),
        current_ast_sha256=(
            "60cffd1eef84b93634b484349ee23900ff36a1a467d1cdc8a52d2034ec6c2e3c"
        ),
        justification_id="default-zero-traversal-counters-preserve-historical-summary",
    ),
    _SourceCompatibilityWaiver(
        element_id="module-assignments.blaine",
        observed_ast_sha256=(
            "94b42d7891d670ee5a2f834c2dc77c6aa27976eba19884123c49be0206866753"
        ),
        current_ast_sha256=(
            "5e40386a31d3b213abe997da1e652ed4f7b6f5ee1843b3a6eedef4ca6d7a9e32"
        ),
        justification_id="cave-only-pacing-and-exit-constants-do-not-affect-route-11",
    ),
    _SourceCompatibilityWaiver(
        element_id="module-assignments.training-venue",
        observed_ast_sha256=(
            "21d3c856685f92c828a195e8963a23a991e307d9a4c5ad7ae3ffbccf70e2f399"
        ),
        current_ast_sha256=(
            "cfaa9dddb67d10cb39a06c41a003216d8b378f4a1c65ba13cd5af8ed011b13d2"
        ),
        justification_id="walker-type-and-direction-constants-preserve-route-11",
    ),
)

_ROUTE_11_CANDIDATE_DIRECT_ROOTS = (
    project_trainee_candidates,
    project_venue_candidates,
    bind_trainee_candidate,
    bind_venue_candidate,
)
_ROUTE_11_CANDIDATE_DIRECT_DEPENDENCIES = (
    *_ROUTE_11_CANDIDATE_DIRECT_ROOTS,
    TrainingCandidateDecision,
)
_ROUTE_11_CANDIDATE_CLOSURE_ROOTS = (
    *_ROUTE_11_CANDIDATE_DIRECT_ROOTS,
    project_trainee_choice_set,
    project_venue_choice_set,
)
_ROUTE_11_ATTRIBUTE_SEMANTICS = (
    TrainingVenue,
    GrindingArea,
    BalancedTeamPolicy,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
    TrainingChoiceKind,
)


class RedPartyDevelopmentVenuePriorError(ValueError):
    """Raised when public Red evidence cannot support the current venue."""


@dataclass(frozen=True, slots=True)
class RedRoute11VenuePriorComposition:
    """One private registry plus its path-free qualification projection."""

    registry: PartyDevelopmentVenuePriorRegistry
    evidence: VenuePriorEvidence
    measurement_contract: VenuePriorMeasurementContract
    operational_contract: VenuePriorOperationalContract
    source_compatibility: VenuePriorSourceCompatibilityAttestation
    rejected_stale_sibling_venue_count: int
    public_plan_sha256: str
    public_result_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.registry, PartyDevelopmentVenuePriorRegistry):
            raise TypeError("registry must be a PartyDevelopmentVenuePriorRegistry")
        if not isinstance(self.evidence, VenuePriorEvidence):
            raise TypeError("evidence must be VenuePriorEvidence")
        if self.registry.entries != (self.evidence,):
            raise RedPartyDevelopmentVenuePriorError(
                "Route 11 composition must freeze exactly its composed evidence"
            )
        if not isinstance(self.measurement_contract, VenuePriorMeasurementContract):
            raise TypeError("measurement contract is invalid")
        if not isinstance(self.operational_contract, VenuePriorOperationalContract):
            raise TypeError("operational contract is invalid")
        if not isinstance(
            self.source_compatibility,
            VenuePriorSourceCompatibilityAttestation,
        ):
            raise TypeError("source compatibility is invalid")
        if (
            self.operational_contract.source_compatibility_sha256
            != self.source_compatibility.source_compatibility_sha256
            or self.evidence.source_compatibility_sha256
            != self.source_compatibility.source_compatibility_sha256
        ):
            raise RedPartyDevelopmentVenuePriorError(
                "Route 11 source compatibility is not bound through the evidence"
            )
        if self.rejected_stale_sibling_venue_count != 1:
            raise RedPartyDevelopmentVenuePriorError(
                "Route 11 composition must reject exactly one measured stale sibling"
            )
        _require_digest(self.public_plan_sha256, subject="public plan")
        _require_digest(self.public_result_sha256, subject="public result")

    def public_dict(self) -> dict[str, object]:
        """Describe the qualification without exposing venue or support identities."""

        return {
            "schema": RED_ROUTE_11_VENUE_PRIOR_COMPOSITION_SCHEMA,
            "status": "source_only_prior_composed",
            "registry": self.registry.public_dict(),
            "evidence": self.evidence.public_dict(),
            "measurement_contract": self.measurement_contract.public_dict(),
            "operational_contract": self.operational_contract.public_dict(),
            "source_compatibility": self.source_compatibility.public_dict(),
            "source_receipt_sha256": [
                self.public_plan_sha256,
                self.public_result_sha256,
            ],
            "accepted_venue_evidence_count": 1,
            "rejected_stale_sibling_venue_count": (
                self.rejected_stale_sibling_venue_count
            ),
            "private_venue_identity_public": False,
            "support_identity_public": False,
            "rom_reads": 0,
            "emulator_starts": 0,
            "controller_actions": 0,
            "outcomes_executed": 0,
            "teacher_queries": 0,
            "sealed_test_cases_opened": 0,
            "crystal_contexts_opened": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }


def attest_red_route_11_source_compatibility(
    repository_root: str | Path,
    *,
    current_commit: str,
    current_source_bundle_sha256: str,
) -> VenuePriorSourceCompatibilityAttestation:
    """Prove every runtime element is unchanged or one exact reviewed waiver."""

    root = Path(repository_root)
    _require_route_11_source_closure()
    if _GIT_OID.fullmatch(current_commit) is None:
        raise RedPartyDevelopmentVenuePriorError(
            "current compatibility source commit is invalid"
        )
    _require_digest(
        current_source_bundle_sha256,
        subject="current compatibility source bundle",
    )
    observed_bundle = committed_source_bundle_sha256(
        root,
        revision=RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT,
    )
    if observed_bundle != RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256:
        raise RedPartyDevelopmentVenuePriorError(
            "historical Route 11 source bundle differs from its receipt"
        )
    current_bundle = committed_source_bundle_sha256(
        root,
        revision=current_commit,
    )
    if current_bundle != current_source_bundle_sha256:
        raise RedPartyDevelopmentVenuePriorError(
            "current Route 11 source bundle differs from its registry"
        )

    observed_rows = _committed_source_element_rows(
        root,
        revision=RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT,
    )
    current_rows = _committed_source_element_rows(root, revision=current_commit)
    loaded_rows = _loaded_source_element_rows()
    if current_rows != loaded_rows:
        raise RedPartyDevelopmentVenuePriorError(
            "loaded Route 11 runtime differs from the attested current commit"
        )

    observed_by_id = {
        str(row["element_id"]): row["ast_sha256"] for row in observed_rows
    }
    current_by_id = {
        str(row["element_id"]): row["ast_sha256"] for row in current_rows
    }
    waivers = {
        waiver.element_id: waiver
        for waiver in _ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS
    }
    if len(waivers) != len(_ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 source waiver allowlist repeats an element"
        )

    unchanged: list[dict[str, object]] = []
    fired_waivers: list[str] = []
    for spec, current_row in zip(
        _ROUTE_11_SOURCE_ELEMENTS,
        current_rows,
        strict=True,
    ):
        observed = observed_by_id[spec.element_id]
        current = current_by_id[spec.element_id]
        if observed is not None and observed == current:
            unchanged.append(current_row)
            continue
        waiver = waivers.get(spec.element_id)
        if (
            waiver is None
            or observed != waiver.observed_ast_sha256
            or current != waiver.current_ast_sha256
        ):
            raise RedPartyDevelopmentVenuePriorError(
                f"unreviewed Route 11 source drift: {spec.element_id}"
            )
        fired_waivers.append(spec.element_id)
    expected_waivers = tuple(sorted(waivers))
    if tuple(sorted(fired_waivers)) != expected_waivers:
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 source waiver allowlist contains a stale exception"
        )

    return VenuePriorSourceCompatibilityAttestation(
        attestation_id=RED_ROUTE_11_SOURCE_COMPATIBILITY_ATTESTATION_ID,
        observed_commit=RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT,
        observed_source_bundle_sha256=observed_bundle,
        current_commit=current_commit,
        current_source_bundle_sha256=current_bundle,
        unchanged_elements_sha256=_source_element_rows_sha256(
            tuple(unchanged),
            scope="unchanged",
        ),
        current_elements_sha256=_source_element_rows_sha256(
            current_rows,
            scope="current",
        ),
        waived_elements=expected_waivers,
        waiver_allowlist_sha256=_source_waiver_allowlist_sha256(waivers),
    )


def red_route_11_operational_contract(
    *,
    source_compatibility: VenuePriorSourceCompatibilityAttestation,
    venue: TrainingVenue = ROUTE_11_TRAINING_VENUE,
    policy: BalancedTeamPolicy = RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
) -> VenuePriorOperationalContract:
    """Digest the current Red layers whose drift invalidates the observation."""

    _require_current_route_11_venue(venue)
    _require_route_11_source_closure()
    if not isinstance(
        source_compatibility,
        VenuePriorSourceCompatibilityAttestation,
    ):
        raise TypeError("source compatibility is invalid")
    current_rows = _loaded_source_element_rows()
    expected_waivers = tuple(
        sorted(
            waiver.element_id
            for waiver in _ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS
        )
    )
    waived_ids = frozenset(expected_waivers)
    expected_unchanged_rows = tuple(
        row
        for row in current_rows
        if str(row["element_id"]) not in waived_ids
    )
    waiver_by_id = {
        waiver.element_id: waiver
        for waiver in _ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS
    }
    if len(waiver_by_id) != len(_ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 source waiver allowlist repeats an element"
        )
    if (
        source_compatibility.observed_commit
        != RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT
        or source_compatibility.observed_source_bundle_sha256
        != RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256
        or source_compatibility.current_elements_sha256
        != _source_element_rows_sha256(
            current_rows,
            scope="current",
        )
        or source_compatibility.unchanged_elements_sha256
        != _source_element_rows_sha256(
            expected_unchanged_rows,
            scope="unchanged",
        )
        or source_compatibility.waived_elements != expected_waivers
        or source_compatibility.waiver_allowlist_sha256
        != _source_waiver_allowlist_sha256(waiver_by_id)
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 operational runtime differs from its source attestation"
        )
    if not isinstance(policy, BalancedTeamPolicy):
        raise TypeError("policy must be a BalancedTeamPolicy")

    policy_document = {
        "schema": "pokemon.red.party-development-venue-policy.v1",
        "balanced_team_policy": asdict(policy),
        "intent": _jsonable(asdict(MANSION_BALANCED_TEAM_TRAINING_INTENT)),
        "volatile_enemy_species": list(MANSION_VOLATILE_ENEMY_SPECIES),
        "escort_enemy_species": list(MANSION_ESCORT_ENEMY_SPECIES),
        "maximum_consecutive_flees": MANSION_MAX_CONSECUTIVE_FLEES,
        "training_move_table_sha256": canonical_sha256(
            {str(key): list(value) for key, value in sorted(TRAINING_MOVE_IDS.items())}
        ),
        "training_pp_reserve_sha256": canonical_sha256(
            dict(sorted(TRAINING_ATTACK_PP_RESERVE.items()))
        ),
        "evolution_objective": {
            "stop": "first_verified_level_triggered_evolution",
            "binding_sha256": canonical_sha256(
                {
                    "precursor_species_id": DIGLETT_SPECIES_ID,
                    "final_species_id": DUGTRIO_SPECIES_ID,
                }
            ),
        },
    }
    encounter_document = {
        "schema": "pokemon.red.party-development-venue-encounter-execution.v1",
        "private_venue_binding_sha256": canonical_sha256(
            {
                "area": asdict(venue.band),
                "map_id": venue.map_id,
            }
        ),
        "stateless_walker_ast_sha256": (
            _require_positive_route_11_stateless_walker()
        ),
        "execution_source_sha256": _source_set_sha256(
            (
                TrainingVenue.fresh_walk_to_grass,
                TrainingVenue.is_in_map,
                _route_11_training_venue,
                _route_11_walk_to_grass,
                run_red_team_balancing,
            )
        ),
        "module_source_sha256": _module_set_sha256(
            (red_team_training_module, training_venue_module)
        ),
    }
    recovery_document = {
        "schema": "pokemon.red.party-development-venue-recovery-execution.v1",
        "route_sha256": canonical_sha256(
            {
                "route_to_center": list(VERMILION_ROUTE_11_TO_CENTER_EXTERIOR),
                "nurse_to_exit": list(VERMILION_NURSE_TO_EXIT),
                "center_to_venue": list(VERMILION_CENTER_TO_ROUTE_11),
            }
        ),
        "execution_source_sha256": _source_set_sha256(
            (
                _route_11_heal_and_return,
                _training_dig_to_vermilion,
                _move,
                _pulse,
                _heal,
                _flee,
            )
        ),
        "module_source_sha256": _module_set_sha256(
            (blaine_module, celadon_module)
        ),
    }
    battle_document = {
        "schema": "pokemon.red.party-development-venue-battle-timing.v1",
        "venue_battle_timing": asdict(venue.battle_timing),
        "flee_timing": asdict(MANSION_TRAINING_FLEE_TIMING),
        "field_menu_timing": asdict(DEFAULT_HIDEOUT_TIMING),
        "controller_timing": asdict(DEFAULT_NEW_GAME_TIMING.controller_timing()),
        "level_up_move_cancel_interval": MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
        "execution_source_sha256": _source_set_sha256(
            (
                run_adaptive_wild_battle,
                _team_training_move_slot,
                _team_training_move_guard,
                trainee_should_fight_directly,
                training_attack_pp,
                training_attack_pp_reserve,
            )
        ),
        "module_source_sha256": _module_set_sha256(
            (battle_runtime_module, red_team_training_module)
        ),
    }
    accounting_document = {
        "schema": "pokemon.red.party-development-venue-accounting.v1",
        "budgeted_center_phases": [
            "venue_transition",
            "required_recovery",
            "optional_recovery",
        ],
        "cleanup_counted_but_outside_recurring_cost": True,
        "execution_source_sha256": _source_set_sha256(
            (
                TeamTrainingExecutionSummary,
                TeamTrainingProgress,
                run_red_team_balancing,
            )
        ),
        "module_source_sha256": _module_set_sha256(
            (red_team_training_module, team_training_module)
        ),
    }
    return VenuePriorOperationalContract(
        contract_id=RED_ROUTE_11_VENUE_OPERATIONAL_CONTRACT_ID,
        policy_sha256=canonical_sha256(policy_document),
        encounter_execution_sha256=canonical_sha256(encounter_document),
        recovery_execution_sha256=canonical_sha256(recovery_document),
        battle_timing_sha256=canonical_sha256(battle_document),
        accounting_sha256=canonical_sha256(accounting_document),
        source_compatibility_sha256=(
            source_compatibility.source_compatibility_sha256
        ),
    )


def compose_red_route_11_venue_prior(
    *,
    plan: Mapping[str, object],
    result: Mapping[str, object],
    public_plan_sha256: str,
    public_result_sha256: str,
    registry_source_commit: str,
    registry_source_bundle_sha256: str,
    source_compatibility: VenuePriorSourceCompatibilityAttestation,
) -> RedRoute11VenuePriorComposition:
    """Qualify the immutable lower-band outcome for the current Route 11 code."""

    _require_digest(public_plan_sha256, subject="public plan")
    _require_digest(public_result_sha256, subject="public result")
    if _GIT_OID.fullmatch(registry_source_commit) is None:
        raise RedPartyDevelopmentVenuePriorError(
            "registry source commit is invalid"
        )
    _require_digest(registry_source_bundle_sha256, subject="registry source bundle")
    if not isinstance(
        source_compatibility,
        VenuePriorSourceCompatibilityAttestation,
    ):
        raise TypeError("source compatibility is invalid")
    if (
        registry_source_commit != source_compatibility.current_commit
        or registry_source_bundle_sha256
        != source_compatibility.current_source_bundle_sha256
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "registry source differs from its compatibility attestation"
        )
    _require_public_evidence_identity(
        plan,
        result,
        public_plan_sha256,
        public_result_sha256,
    )

    authenticated_plan = _mapping(plan, "authenticated_root")
    authenticated_result = _mapping(result, "authenticated_root")
    construction = _mapping(plan, "candidate_construction")
    objective = _mapping(plan, "bounded_objective")
    training_policy = _mapping(plan, "training_policy")
    source = _mapping(result, "source")
    collection = _mapping(result, "outcome_collection")
    decision = _mapping(result, "decision")
    accounting = _mapping(result, "center_call_accounting")

    state_sha256 = authenticated_plan.get("state_sha256")
    if (
        state_sha256 != authenticated_result.get("state_sha256")
        or authenticated_plan.get("checkpoint_id")
        != RED_ROUTE_11_SUPPORT_CHECKPOINT_ID
        or authenticated_plan.get("partition") != "train"
        or authenticated_result.get("partition") != "train"
        or authenticated_plan.get("sealed_test") is not False
        or authenticated_result.get("sealed_test") is not False
        or authenticated_plan.get("crystal") is not False
        or authenticated_result.get("crystal") is not False
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 support root is not one open independent Red train state"
        )
    _require_digest(state_sha256, subject="support state")
    if not isinstance(state_sha256, str):  # pragma: no cover - digest guard narrows at runtime
        raise AssertionError("support digest disappeared")

    _require_policy_matches_plan(training_policy)
    venue = ROUTE_11_TRAINING_VENUE
    _require_current_route_11_venue(venue)
    if (
        construction.get("candidate_count") != 2
        or construction.get("ordered_minimum_encounter_levels") != [
            venue.band.minimum_encounter_level,
            15,
        ]
        or construction.get("ordered_maximum_encounter_levels") != [
            venue.band.maximum_encounter_level,
            21,
        ]
        or construction.get("same_start_required") is not True
        or construction.get("same_trainee_required") is not True
        or construction.get("same_stop_condition_required") is not True
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "published candidate order does not bind Route 11 as candidate zero"
        )

    trials = collection.get("trials")
    if (
        not isinstance(trials, list)
        or len(trials) != 2
        or [item.get("candidate_index") if isinstance(item, Mapping) else None for item in trials]
        != [0, 1]
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "published outcome does not retain two canonical candidate trials"
        )
    route_trial = trials[0]
    if not isinstance(route_trial, Mapping):  # pragma: no cover - guarded above
        raise AssertionError("canonical trial disappeared")
    rejected_stale_sibling_venue_count = _rejected_stale_sibling_count(
        trials,
        objective=objective,
    )

    initial_level = _integer(route_trial, "initial_target_level")
    final_level = _integer(route_trial, "final_target_level")
    expected_level = _integer(objective, "expected_evolution_level")
    if (
        route_trial.get("candidate_kind") != "lower_encounter_band_9_15"
        or route_trial.get("evolution_completed") is not True
        or initial_level != objective.get("initial_target_level")
        or final_level != expected_level
        or final_level <= initial_level
        or _integer(route_trial, "faints") != 0
        or collection.get("fully_measured") is not True
        or collection.get("learner_update_eligible") is not True
        or decision.get("training_target_accepted") is not True
        or decision.get("model_fit") is not False
        or decision.get("authority_promoted") is not False
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 trial is not the accepted bounded evolution observation"
        )

    transitions = _integer(route_trial, "venue_transition_trips")
    required_recovery = _integer(route_trial, "required_recovery_trips")
    optional_recovery = _integer(route_trial, "optional_recovery_trips")
    cleanup = _integer(route_trial, "cleanup_trips")
    total_center = _integer(route_trial, "total_counted_center_routes")
    budgeted_center = _integer(route_trial, "budgeted_center_calls")
    if (
        transitions + required_recovery + optional_recovery != budgeted_center
        or budgeted_center + cleanup != total_center
        or accounting.get("phase_sum_equals_total_for_every_trial") is not True
        or accounting.get("budget_conformance_proven") is not True
        or accounting.get("exactly_one_cleanup_per_trial") is not True
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 Center accounting does not reconcile exactly"
        )

    source_commit = source.get("git_commit")
    source_bundle = source.get("source_bundle_sha256")
    if (
        source_commit != RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT
        or source_bundle
        != RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256
        or source.get("exact_commit_ci_conclusion") != "success"
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 outcome lacks one successful published source"
        )
    _require_digest(source_bundle, subject="outcome source bundle")
    if not isinstance(source_bundle, str):  # pragma: no cover - digest guard narrows at runtime
        raise AssertionError("source bundle digest disappeared")

    if (
        source_commit != source_compatibility.observed_commit
        or source_bundle
        != source_compatibility.observed_source_bundle_sha256
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 outcome source lacks the required compatibility proof"
        )

    measurement_contract = VenuePriorMeasurementContract()
    operational_contract = red_route_11_operational_contract(
        source_compatibility=source_compatibility,
    )
    observation = VenuePriorObservation(
        root_lineage_id=RED_ROUTE_11_SUPPORT_CHECKPOINT_ID,
        initial_state_sha256=state_sha256,
        outcome_receipt_sha256=tuple(
            sorted((public_plan_sha256, public_result_sha256))
        ),
        objective_completed=True,
        progress_units_gained=final_level - initial_level,
        progress_units_required=expected_level - initial_level,
        battles_completed=_integer(route_trial, "battles_completed"),
        faints=_integer(route_trial, "faints"),
        venue_transition_trips=transitions,
        required_recovery_trips=required_recovery,
        optional_recovery_trips=optional_recovery,
        cleanup_trips=cleanup,
        total_counted_center_routes=total_center,
    )
    evidence = compose_venue_prior_evidence(
        evidence_id=RED_ROUTE_11_VENUE_PRIOR_EVIDENCE_ID,
        venue=venue.band,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle,
        measurement_contract=measurement_contract,
        operational_contract=operational_contract,
        source_compatibility=source_compatibility,
        observations=(observation,),
    )
    registry = PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit=registry_source_commit,
        source_bundle_sha256=registry_source_bundle_sha256,
        entries=(evidence,),
    )
    return RedRoute11VenuePriorComposition(
        registry=registry,
        evidence=evidence,
        measurement_contract=measurement_contract,
        operational_contract=operational_contract,
        source_compatibility=source_compatibility,
        rejected_stale_sibling_venue_count=(
            rejected_stale_sibling_venue_count
        ),
        public_plan_sha256=public_plan_sha256,
        public_result_sha256=public_result_sha256,
    )


def _require_public_evidence_identity(
    plan: Mapping[str, object],
    result: Mapping[str, object],
    public_plan_sha256: str,
    public_result_sha256: str,
) -> None:
    if (
        public_plan_sha256 != RED_PARTY_DEVELOPMENT_OUTCOME_PLAN_SHA256
        or public_result_sha256 != RED_PARTY_DEVELOPMENT_OUTCOME_RESULT_SHA256
        or plan.get("schema") != "pokemon-red-party-development-outcome-plan-v2"
        or plan.get("status") != "prospective_unexecuted"
        or plan.get("experiment_id") != RED_PARTY_DEVELOPMENT_OUTCOME_SCENARIO_ID
        or result.get("schema")
        != "pokemon-red-party-development-outcome-evidence-v2"
        or result.get("status") != "complete_learner_target_accepted"
        or result.get("experiment_id") != RED_PARTY_DEVELOPMENT_OUTCOME_SCENARIO_ID
        or _mapping(result, "prospective_bindings").get("public_plan_sha256")
        != public_plan_sha256
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 plan and result identity do not form one accepted experiment"
        )


def _rejected_stale_sibling_count(
    trials: list[object],
    *,
    objective: Mapping[str, object],
) -> int:
    """Validate and count the measured Cave sibling excluded from this prior."""

    siblings = trials[1:]
    if len(siblings) != 1 or not isinstance(siblings[0], Mapping):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 outcome lacks one auditable stale sibling"
        )
    sibling = siblings[0]
    transitions = _integer(sibling, "venue_transition_trips")
    required_recovery = _integer(sibling, "required_recovery_trips")
    optional_recovery = _integer(sibling, "optional_recovery_trips")
    cleanup = _integer(sibling, "cleanup_trips")
    budgeted = _integer(sibling, "budgeted_center_calls")
    total = _integer(sibling, "total_counted_center_routes")
    if (
        sibling.get("candidate_index") != 1
        or sibling.get("candidate_kind") != "higher_encounter_band_15_21"
        or sibling.get("evolution_completed") is not True
        or _integer(sibling, "initial_target_level")
        != objective.get("initial_target_level")
        or _integer(sibling, "final_target_level")
        != objective.get("expected_evolution_level")
        or _integer(sibling, "battles_completed") <= 0
        or _integer(sibling, "faints") != 0
        or transitions <= 0
        or transitions + required_recovery + optional_recovery != budgeted
        or budgeted + cleanup != total
        or cleanup != 1
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "measured sibling does not prove one rejected stale Cave outcome"
        )
    return len(siblings)


def _require_policy_matches_plan(plan_policy: Mapping[str, object]) -> None:
    policy = RED_PARTY_DEVELOPMENT_OUTCOME_POLICY
    expected = {
        "retreat_hp_ratio": policy.retreat_hp_ratio,
        "reserve_total_pp": policy.reserve_total_pp,
        "species_specific_escort_pp_reserve": TRAINING_ATTACK_PP_RESERVE[
            BLASTOISE_SPECIES_ID
        ],
        "minimum_direct_level_advantage": policy.minimum_direct_level_advantage,
        "safe_escort_level": policy.safe_lead_level,
        "maximum_battles": policy.max_battles,
        "maximum_steps": policy.max_steps,
        "max_healing_trips_runtime_value": policy.max_healing_trips,
        "maximum_budgeted_center_calls": policy.max_healing_trips,
        "budgeted_center_call_phases": [
            "venue_transition",
            "required_recovery",
            "optional_recovery",
        ],
        "final_cleanup_outside_budget_but_counted": True,
        "required_final_cleanup_calls": 1,
        "maximum_faints": policy.max_faints,
        "optional_heal_selected_by_executor": False,
        "mandatory_heal_only_when_health_status_or_pp_is_unsafe": True,
    }
    if any(plan_policy.get(key) != value for key, value in expected.items()):
        raise RedPartyDevelopmentVenuePriorError(
            "published training policy differs from the current bounded policy"
        )


def _require_positive_route_11_stateless_walker() -> str:
    """Positively bind the one reviewed stateless Route 11 walker body."""

    if _route_11_walk_to_grass.__closure__ not in (None, ()):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 walker unexpectedly closes over mutable state"
        )
    digest = _loaded_element_ast_sha256(
        _route_11_walk_to_grass,
        qualname="_route_11_walk_to_grass",
    )
    if digest != RED_ROUTE_11_STATELESS_WALKER_AST_SHA256:
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 walker differs from its positive statelessness proof"
        )
    return digest


def _require_current_route_11_venue(venue: TrainingVenue) -> None:
    expected = ROUTE_11_TRAINING_VENUE
    if (
        not isinstance(venue, TrainingVenue)
        or venue.band != expected.band
        or venue.map_id != expected.map_id
        or venue.walk_to_grass is not _route_11_walk_to_grass
        or venue.heal_and_return is not _route_11_heal_and_return
        or venue.move_slot is not _team_training_move_slot
        or venue.move_guard is not _team_training_move_guard
        or venue.walk_to_grass_factory is not None
        or venue.band.minimum_encounter_level != 9
        or venue.band.maximum_encounter_level != 15
        or venue.band.rare_maximum_encounter_level != 17
        or venue.band.measured_samples != 81
        or not venue.band.has_nearby_healer
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "current Route 11 venue differs from its qualified operating seam"
        )


def _committed_source_element_rows(
    repository_root: Path,
    *,
    revision: str,
) -> tuple[dict[str, object], ...]:
    blobs: dict[str, bytes] = {}
    rows: list[dict[str, object]] = []
    for spec in _ROUTE_11_SOURCE_ELEMENTS:
        blob = blobs.get(spec.relative_path)
        if blob is None:
            blob = committed_executable_source_blob(
                repository_root,
                revision=revision,
                relative_path=spec.relative_path,
            )
            blobs[spec.relative_path] = blob
        rows.append(
            _source_element_row(
                spec,
                _committed_element_ast_sha256(
                    blob,
                    qualname=spec.qualname,
                    kind=spec.kind,
                ),
            )
        )
    return tuple(rows)


def _loaded_source_element_rows() -> tuple[dict[str, object], ...]:
    return tuple(
        _source_element_row(
            spec,
            _loaded_element_ast_sha256(
                spec.current_object,
                qualname=spec.qualname,
                kind=spec.kind,
            ),
        )
        for spec in _ROUTE_11_SOURCE_ELEMENTS
    )


def _require_route_11_source_closure() -> None:
    """Fail closed when the candidate seam reaches untracked project code.

    The historical observation ran through the four candidate projection and
    binding entry points in ``run_red_team_balancing``.  Tracking only those
    wrappers is insufficient: a wrapper can keep the same source while a
    helper beneath it changes.  Resolve the loaded same-project call graph and
    require every discovered function or class to have its own semantic source
    element.  Attribute-driven domain semantics are declared separately and
    covered as whole classes because Python's AST does not carry receiver
    types.
    """

    element_ids = tuple(spec.element_id for spec in _ROUTE_11_SOURCE_ELEMENTS)
    if len(element_ids) != len(set(element_ids)):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 source elements repeat an identity"
        )
    tracked = frozenset(spec.current_object for spec in _ROUTE_11_SOURCE_ELEMENTS)
    required_attribute_semantics = frozenset(_ROUTE_11_ATTRIBUTE_SEMANTICS)
    if not required_attribute_semantics.issubset(tracked):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 attribute semantics are not source-covered"
        )

    direct_dependencies = frozenset(
        dependency
        for dependency in _resolved_project_call_dependencies(
            run_red_team_balancing
        )
        if getattr(dependency, "__module__", None)
        == training_candidate_rank_module.__name__
    )
    if direct_dependencies != frozenset(
        _ROUTE_11_CANDIDATE_DIRECT_DEPENDENCIES
    ):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 candidate entry-point closure changed"
        )

    pending: list[Callable[..., object]] = [
        cast(Callable[..., object], root)
        for root in _ROUTE_11_CANDIDATE_CLOSURE_ROOTS
    ]
    visited: set[Callable[..., object]] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current not in tracked:
            raise RedPartyDevelopmentVenuePriorError(
                "Route 11 candidate closure contains an untracked root"
            )
        for dependency in _resolved_project_call_dependencies(current):
            module_name = getattr(dependency, "__module__", "")
            if not module_name.startswith("pokemon_red_completion"):
                continue
            if dependency not in tracked:
                qualname = getattr(dependency, "__qualname__", repr(dependency))
                raise RedPartyDevelopmentVenuePriorError(
                    "Route 11 candidate closure contains untracked project "
                    f"code: {module_name}.{qualname}"
                )
            if (
                module_name == training_candidate_rank_module.__name__
                and inspect.isfunction(dependency)
            ):
                pending.append(cast(Callable[..., object], dependency))


def _resolved_project_call_dependencies(
    value: Callable[..., object],
) -> tuple[Callable[..., object] | type[object], ...]:
    """Resolve direct named calls made by one loaded Python function."""

    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(value)))
    except (OSError, TypeError, SyntaxError) as error:
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 closure source is unavailable"
        ) from error
    namespace = getattr(value, "__globals__", None)
    if not isinstance(namespace, dict):
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 closure root has no Python globals"
        )
    dependencies: set[Callable[..., object] | type[object]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        dependency = namespace.get(node.func.id)
        if inspect.isfunction(dependency) or inspect.isclass(dependency):
            dependencies.add(dependency)
    return tuple(
        sorted(
            dependencies,
            key=lambda item: (
                getattr(item, "__module__", ""),
                getattr(item, "__qualname__", ""),
            ),
        )
    )


def _source_waiver_allowlist_sha256(
    waivers: Mapping[str, _SourceCompatibilityWaiver],
) -> str:
    expected_ids = tuple(sorted(waivers))
    return canonical_sha256(
        {
            "schema": "pokemon.red.route-11-source-waiver-allowlist.v1",
            "waivers": [
                waivers[element_id].public_dict()
                for element_id in expected_ids
            ],
        }
    )


def _source_element_row(
    spec: _SourceElement,
    ast_sha256: str | None,
) -> dict[str, object]:
    return {
        "element_id": spec.element_id,
        "relative_path": spec.relative_path,
        "qualname": spec.qualname,
        "ast_sha256": ast_sha256,
    }


def _committed_element_ast_sha256(
    source: bytes,
    *,
    qualname: str,
    kind: Literal["definition", "module_assignments"] = "definition",
) -> str | None:
    if kind == "module_assignments":
        return _module_assignments_ast_sha256(source)
    if kind != "definition":
        raise RedPartyDevelopmentVenuePriorError(
            "committed operational source kind is invalid"
        )
    try:
        document = source.decode("utf-8")
        tree = ast.parse(document)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise RedPartyDevelopmentVenuePriorError(
            "committed operational source is not parseable Python"
        ) from error
    body: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in qualname.split("."):
        matches = [
            item
            for item in body
            if isinstance(
                item,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and item.name == part
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise RedPartyDevelopmentVenuePriorError(
                "committed operational source repeats a qualified element"
            )
        node = matches[0]
        body = list(getattr(node, "body", ()))
    if node is None:  # pragma: no cover - every declared qualname is non-empty
        raise AssertionError("source element qualname disappeared")
    return _ast_node_sha256(node, qualname=qualname)


def _loaded_element_ast_sha256(
    value: Callable[..., object] | type[object] | ModuleType,
    *,
    qualname: str,
    kind: Literal["definition", "module_assignments"] = "definition",
) -> str:
    if kind == "module_assignments":
        if not isinstance(value, ModuleType):
            raise RedPartyDevelopmentVenuePriorError(
                "loaded module-assignment source is invalid"
            )
        try:
            module_source = inspect.getsource(value).encode("utf-8")
        except (OSError, TypeError) as error:
            raise RedPartyDevelopmentVenuePriorError(
                "loaded module-assignment source is unavailable"
            ) from error
        return _module_assignments_ast_sha256(module_source)
    if kind != "definition":
        raise RedPartyDevelopmentVenuePriorError(
            "loaded operational source kind is invalid"
        )
    try:
        source = textwrap.dedent(inspect.getsource(value))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError) as error:
        raise RedPartyDevelopmentVenuePriorError(
            "loaded operational source is unavailable"
        ) from error
    leaf = qualname.rsplit(".", 1)[-1]
    matches = [
        item
        for item in tree.body
        if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == leaf
    ]
    if len(matches) != 1:
        raise RedPartyDevelopmentVenuePriorError(
            "loaded operational source element differs"
        )
    return _ast_node_sha256(matches[0], qualname=qualname)


def _module_assignments_ast_sha256(source: bytes) -> str:
    """Bind every top-level assignment in one execution-bearing module."""

    try:
        document = source.decode("utf-8")
        tree = ast.parse(document)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise RedPartyDevelopmentVenuePriorError(
            "module-assignment source is not parseable Python"
        ) from error
    assignments = [
        node
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    if not assignments:
        raise RedPartyDevelopmentVenuePriorError(
            "execution-bearing module has no assignments"
        )
    return canonical_sha256(
        {
            "schema": "pokemon.red.semantic-python-module-assignments.v1",
            "assignments": [
                _canonical_ast_value(node) for node in assignments
            ],
        }
    )


def _ast_node_sha256(node: ast.AST, *, qualname: str) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.red.semantic-python-ast.v1",
            "qualname": qualname,
            "ast": _canonical_ast_value(node),
        }
    )


def _canonical_ast_value(value: object) -> object:
    """Encode semantic AST fields independently of ``ast.dump`` versions."""

    if isinstance(value, ast.AST):
        fields: list[dict[str, object]] = []
        for name, child in ast.iter_fields(value):
            # ``type_params`` was added in Python 3.12. Empty values carry no
            # source semantics and must not make identical Python 3.11 source
            # hash differently on a newer interpreter.
            if name == "type_params" and child == []:
                continue
            fields.append(
                {
                    "name": name,
                    "value": _canonical_ast_value(child),
                }
            )
        return {
            "node": type(value).__name__,
            "fields": fields,
        }
    if isinstance(value, list):
        return {
            "sequence": [_canonical_ast_value(item) for item in value],
        }
    if isinstance(value, tuple):
        return {
            "tuple": [_canonical_ast_value(item) for item in value],
        }
    if value is None:
        return {"scalar": "none"}
    if isinstance(value, bool):
        return {"scalar": "bool", "value": value}
    if isinstance(value, int):
        return {"scalar": "int", "value": str(value)}
    if isinstance(value, float):
        return {"scalar": "float", "value": value.hex()}
    if isinstance(value, complex):
        return {
            "scalar": "complex",
            "real": value.real.hex(),
            "imag": value.imag.hex(),
        }
    if isinstance(value, str):
        return {"scalar": "str", "value": value}
    if isinstance(value, bytes):
        return {"scalar": "bytes", "value": value.hex()}
    if value is Ellipsis:
        return {"scalar": "ellipsis"}
    raise RedPartyDevelopmentVenuePriorError(
        "operational AST contains an unsupported semantic value"
    )


def _source_element_rows_sha256(
    rows: tuple[dict[str, object], ...],
    *,
    scope: str,
) -> str:
    if not rows:
        raise RedPartyDevelopmentVenuePriorError(
            "Route 11 source compatibility has no elements"
        )
    return canonical_sha256(
        {
            "schema": "pokemon.red.route-11-source-elements.v1",
            "scope": scope,
            "elements": list(rows),
        }
    )


def _source_set_sha256(callables: tuple[Callable[..., object], ...]) -> str:
    rows: list[tuple[str, str, str]] = []
    for value in callables:
        try:
            source = inspect.getsource(value).encode("utf-8")
        except (OSError, TypeError) as error:
            raise RedPartyDevelopmentVenuePriorError(
                "operational callable source is unavailable"
            ) from error
        rows.append(
            (
                value.__module__,
                value.__qualname__,
                hashlib.sha256(source).hexdigest(),
            )
        )
    return canonical_sha256(
        {
            "schema": "pokemon.core.operational-callable-source-set.v1",
            "callables": [
                {
                    "module": module,
                    "qualname": qualname,
                    "source_sha256": source_sha256,
                }
                for module, qualname, source_sha256 in sorted(rows)
            ],
        }
    )


def _module_set_sha256(modules: tuple[ModuleType, ...]) -> str:
    rows: list[tuple[str, str]] = []
    for module in modules:
        try:
            source = inspect.getsource(module).encode("utf-8")
        except (OSError, TypeError) as error:
            raise RedPartyDevelopmentVenuePriorError(
                "operational module source is unavailable"
            ) from error
        rows.append((module.__name__, hashlib.sha256(source).hexdigest()))
    return canonical_sha256(
        {
            "schema": "pokemon.core.operational-module-source-set.v1",
            "modules": [
                {"module": module, "source_sha256": source_sha256}
                for module, source_sha256 in sorted(rows)
            ],
        }
    )


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=repr)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise RedPartyDevelopmentVenuePriorError(
        "operational contract contains a non-canonical value"
    )


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise RedPartyDevelopmentVenuePriorError(
            f"published Route 11 evidence {key} is invalid"
        )
    return value


def _integer(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedPartyDevelopmentVenuePriorError(
            f"published Route 11 evidence {key} is invalid"
        )
    return value


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedPartyDevelopmentVenuePriorError(
            f"Route 11 {subject} digest is invalid"
        )


__all__ = [
    "RED_PARTY_DEVELOPMENT_OUTCOME_POLICY",
    "RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_BUNDLE_SHA256",
    "RED_PARTY_DEVELOPMENT_OUTCOME_SOURCE_COMMIT",
    "RED_ROUTE_11_VENUE_PRIOR_COMPOSITION_SCHEMA",
    "RedPartyDevelopmentVenuePriorError",
    "RedRoute11VenuePriorComposition",
    "attest_red_route_11_source_compatibility",
    "compose_red_route_11_venue_prior",
    "red_route_11_operational_contract",
]
