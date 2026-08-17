"""Title-neutral projection into completion-aware party candidate menus.

Concrete game adapters are responsible for reading memory and deriving each
member's evolution, collection, role, and venue-survival facts.  This module
does the reusable part: validate that those private facts align with one
coherent party snapshot, derive the party-wide context, preserve the frozen v1
candidate prefix, attach only pre-existing venue evidence, and return private
execution bindings beside identity-free learner candidates.

No controller, teacher, ROM, map, species name, or button sequence appears at
this boundary.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pokemon_red_completion.party import (
    MAX_LEVEL,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
    PartyDevelopmentUnavailableReason,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (
    CandidateCompletionSemantics,
    EvolutionSemantics,
    PartyDevelopmentCandidateSet,
    PartyDevelopmentContext,
    PartyDevelopmentGoal,
    VenueOperationalPrior,
    VenuePriorFeatureMode,
    augment_training_candidate_set,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    member_needs_training,
)
from pokemon_red_completion.training_candidate_rank import (
    TrainingChoiceKind,
    project_trainee_choice_set,
    project_venue_choice_set,
)

_BindingT = TypeVar("_BindingT", PartyMemberObservation, GrindingArea)
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class PartyDevelopmentAdapterError(ValueError):
    """Raised when a semantic snapshot cannot support an honest menu."""


class PartyDevelopmentCapabilityState(StrEnum):
    """Prospective status of one title adapter's execution capability."""

    READY = "ready"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PartyDevelopmentExecutionCapability:
    """Title-neutral readiness of one trainee/venue pair before selection.

    A title adapter may use any private facts required to derive these three
    statuses.  The shared learner sees only the resulting availability mask and
    portable reason.  Keeping the axes separate prevents a later title from
    treating a static map edge, one usable move, or a nearby healer as proof
    that the complete action can actually finish.
    """

    transition: PartyDevelopmentCapabilityState
    battle: PartyDevelopmentCapabilityState
    recovery: PartyDevelopmentCapabilityState

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, PartyDevelopmentCapabilityState)
            for value in (self.transition, self.battle, self.recovery)
        ):
            raise PartyDevelopmentAdapterError(
                "party-development execution capability states are invalid"
            )

    @classmethod
    def ready(cls) -> PartyDevelopmentExecutionCapability:
        return cls(
            PartyDevelopmentCapabilityState.READY,
            PartyDevelopmentCapabilityState.READY,
            PartyDevelopmentCapabilityState.READY,
        )

    @property
    def available(self) -> bool:
        return all(
            value is PartyDevelopmentCapabilityState.READY
            for value in (self.transition, self.battle, self.recovery)
        )

    @property
    def unavailable_reason(self) -> PartyDevelopmentUnavailableReason | None:
        states_and_reasons = (
            (
                self.transition,
                PartyDevelopmentUnavailableReason.TRANSITION_UNAVAILABLE,
            ),
            (
                self.battle,
                PartyDevelopmentUnavailableReason.BATTLE_POLICY_INCOMPATIBLE,
            ),
            (
                self.recovery,
                PartyDevelopmentUnavailableReason.INSUFFICIENT_RECOVERY_CAPACITY,
            ),
        )
        for state, blocked_reason in states_and_reasons:
            if state is PartyDevelopmentCapabilityState.BLOCKED:
                return blocked_reason
        if any(
            state is PartyDevelopmentCapabilityState.UNKNOWN
            for state, _reason in states_and_reasons
        ):
            return PartyDevelopmentUnavailableReason.WORLD_STATE_UNKNOWN
        return None


@dataclass(frozen=True, slots=True)
class PartyDevelopmentMemberProfile:
    """Private completion facts for one exact observed party member."""

    member: PartyMemberObservation
    evolution: EvolutionSemantics
    execution_capabilities_by_venue: tuple[PartyDevelopmentExecutionCapability, ...]
    registration_needed: bool = False
    living_target_needed: bool = False
    living_retention_risk: bool = False
    role_needed: bool = False
    role_complete: bool = False
    emergency_escort_required: bool = False
    projected_survival_by_venue: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.member, PartyMemberObservation):
            raise PartyDevelopmentAdapterError(
                "party-development profile needs an observed member binding"
            )
        if not isinstance(self.evolution, EvolutionSemantics):
            raise PartyDevelopmentAdapterError(
                "party-development profile evolution semantics are invalid"
            )
        for name in (
            "registration_needed",
            "living_target_needed",
            "living_retention_risk",
            "role_needed",
            "role_complete",
            "emergency_escort_required",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PartyDevelopmentAdapterError(
                    f"party-development profile {name.replace('_', ' ')} must be boolean"
                )
        if self.role_needed and self.role_complete:
            raise PartyDevelopmentAdapterError(
                "a party-development profile role cannot be missing and complete"
            )
        margins = self.projected_survival_by_venue
        if not isinstance(margins, tuple) or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not -1.0 <= float(value) <= 1.0
            for value in margins
        ):
            raise PartyDevelopmentAdapterError(
                "projected venue survival margins must be finite signed unit values"
            )
        capabilities = self.execution_capabilities_by_venue
        if not isinstance(capabilities, tuple) or any(
            not isinstance(value, PartyDevelopmentExecutionCapability) for value in capabilities
        ):
            raise PartyDevelopmentAdapterError(
                "party-development execution capabilities must be typed"
            )

    def semantics_for_venue(self, venue_index: int) -> CandidateCompletionSemantics:
        if type(venue_index) is not int or venue_index not in range(  # noqa: E721
            len(self.projected_survival_by_venue)
        ):
            raise PartyDevelopmentAdapterError("projected survival venue index is invalid")
        return CandidateCompletionSemantics(
            evolution=self.evolution,
            registration_needed=self.registration_needed,
            living_target_needed=self.living_target_needed,
            living_retention_risk=self.living_retention_risk,
            role_needed=self.role_needed,
            role_complete=self.role_complete,
            emergency_escort_required=self.emergency_escort_required,
            projected_survival_margin=float(self.projected_survival_by_venue[venue_index]),
        )

    def execution_capability_for_venue(
        self,
        venue_index: int,
    ) -> PartyDevelopmentExecutionCapability:
        if type(venue_index) is not int or venue_index not in range(  # noqa: E721
            len(self.execution_capabilities_by_venue)
        ):
            raise PartyDevelopmentAdapterError("execution capability venue index is invalid")
        return self.execution_capabilities_by_venue[venue_index]


@dataclass(frozen=True, slots=True)
class BoundPartyDevelopmentMenu(Generic[_BindingT]):
    """Identity-free candidates plus bindings that never enter learner data."""

    candidate_set: PartyDevelopmentCandidateSet
    semantic_snapshot_sha256: str
    bindings: tuple[_BindingT, ...]
    candidate_available: tuple[bool, ...]
    candidate_unavailable_reasons: tuple[PartyDevelopmentUnavailableReason | None, ...]
    venue_priors: tuple[VenueOperationalPrior, ...]
    shared_venue: GrindingArea | None = None
    shared_venue_prior: VenueOperationalPrior | None = None
    venue_prior_feature_mode: VenuePriorFeatureMode = VenuePriorFeatureMode.CALIBRATED

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_set, PartyDevelopmentCandidateSet):
            raise PartyDevelopmentAdapterError(
                "bound party-development menu needs typed candidates"
            )
        if (
            not isinstance(self.semantic_snapshot_sha256, str)
            or _SHA256.fullmatch(self.semantic_snapshot_sha256) is None
        ):
            raise PartyDevelopmentAdapterError(
                "bound party-development menu semantic snapshot is invalid"
            )
        count = len(self.candidate_set.candidates)
        if (
            not isinstance(self.bindings, tuple)
            or len(self.bindings) != count
            or not isinstance(self.candidate_available, tuple)
            or len(self.candidate_available) != count
            or any(not isinstance(value, bool) for value in self.candidate_available)
            or not isinstance(self.candidate_unavailable_reasons, tuple)
            or len(self.candidate_unavailable_reasons) != count
            or any(
                reason is not None and not isinstance(reason, PartyDevelopmentUnavailableReason)
                for reason in self.candidate_unavailable_reasons
            )
            or not isinstance(self.venue_priors, tuple)
            or len(self.venue_priors) != count
            or any(not isinstance(value, VenueOperationalPrior) for value in self.venue_priors)
        ):
            raise PartyDevelopmentAdapterError(
                "private bindings, availability, and priors must align with candidates"
            )
        if any(
            available != (reason is None)
            for available, reason in zip(
                self.candidate_available,
                self.candidate_unavailable_reasons,
                strict=True,
            )
        ):
            raise PartyDevelopmentAdapterError(
                "candidate availability and unavailable reasons must agree"
            )
        if not isinstance(self.venue_prior_feature_mode, VenuePriorFeatureMode):
            raise PartyDevelopmentAdapterError(
                "venue-prior feature mode must be typed"
            )
        if self.venue_prior_feature_mode is VenuePriorFeatureMode.MASKED_UNCALIBRATED:
            if (
                any(prior.available for prior in self.venue_priors)
                or self.shared_venue_prior is not None
                or any(
                    reason is PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE
                    for reason in self.candidate_unavailable_reasons
                )
                or (
                    self.candidate_set.kind is TrainingChoiceKind.TRAINEE
                    and (
                        not isinstance(self.shared_venue, GrindingArea)
                        or any(
                            not isinstance(value, PartyMemberObservation)
                            for value in self.bindings
                        )
                    )
                )
                or (
                    self.candidate_set.kind is TrainingChoiceKind.VENUE
                    and (
                        self.shared_venue is not None
                        or any(
                            not isinstance(value, GrindingArea)
                            for value in self.bindings
                        )
                    )
                )
            ):
                raise PartyDevelopmentAdapterError(
                    "masked venue priors must be absent and cannot gate execution"
                )
        elif self.candidate_set.kind is TrainingChoiceKind.TRAINEE:
            if (
                any(not isinstance(value, PartyMemberObservation) for value in self.bindings)
                or not isinstance(self.shared_venue, GrindingArea)
                or not isinstance(self.shared_venue_prior, VenueOperationalPrior)
                or not self.shared_venue_prior.available
                or any(prior != self.shared_venue_prior for prior in self.venue_priors)
                or any(
                    reason is PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE
                    for reason in self.candidate_unavailable_reasons
                )
            ):
                raise PartyDevelopmentAdapterError(
                    "trainee menus need one frozen shared venue and only member bindings"
                )
        elif (
            any(not isinstance(value, GrindingArea) for value in self.bindings)
            or self.shared_venue is not None
            or self.shared_venue_prior is not None
            or any(
                available and not prior.available
                for available, prior in zip(
                    self.candidate_available,
                    self.venue_priors,
                    strict=True,
                )
            )
            or any(
                (not prior.available)
                != (reason is PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE)
                for prior, reason in zip(
                    self.venue_priors,
                    self.candidate_unavailable_reasons,
                    strict=True,
                )
            )
        ):
            raise PartyDevelopmentAdapterError(
                "venue menus must preserve prior and execution availability causality"
            )


@dataclass(frozen=True, slots=True)
class PartyDevelopmentSemanticSnapshot:
    """One coherent title-neutral state from which menus may be projected."""

    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    source_commit: str
    source_bundle_sha256: str
    party: PartyObservation
    policy: BalancedTeamPolicy
    areas: tuple[GrindingArea, ...]
    goal: PartyDevelopmentGoal
    member_profiles: tuple[PartyDevelopmentMemberProfile, ...]
    venue_prior_registry: PartyDevelopmentVenuePriorRegistry
    venue_operational_contract_sha256: tuple[str, ...]
    registration_owned_count: int
    registration_target_count: int
    living_unique_count: int
    living_target_count: int
    role_coverage_count: int
    role_target_count: int
    active_conditions: tuple[str, ...] = ()
    venue_prior_feature_mode: VenuePriorFeatureMode = VenuePriorFeatureMode.CALIBRATED
    execution_protocol_id: str = "legacy-adaptive-v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.root_lineage_id, str)
            or _SAFE_ID.fullmatch(self.root_lineage_id) is None
        ):
            raise PartyDevelopmentAdapterError("party-development snapshot root lineage is invalid")
        if (
            not isinstance(self.initial_state_sha256, str)
            or _SHA256.fullmatch(self.initial_state_sha256) is None
        ):
            raise PartyDevelopmentAdapterError(
                "party-development snapshot initial state is invalid"
            )
        if not isinstance(self.partition, ScenarioPartition):
            raise PartyDevelopmentAdapterError("party-development snapshot partition is invalid")
        if (
            not isinstance(self.source_commit, str)
            or _GIT_OID.fullmatch(self.source_commit) is None
        ):
            raise PartyDevelopmentAdapterError(
                "party-development snapshot source commit is invalid"
            )
        if (
            not isinstance(self.source_bundle_sha256, str)
            or _SHA256.fullmatch(self.source_bundle_sha256) is None
        ):
            raise PartyDevelopmentAdapterError(
                "party-development snapshot source bundle is invalid"
            )
        if not isinstance(self.party, PartyObservation) or not self.party.members:
            raise PartyDevelopmentAdapterError("party-development snapshot needs a non-empty party")
        if not isinstance(self.policy, BalancedTeamPolicy):
            raise PartyDevelopmentAdapterError("party-development snapshot policy is invalid")
        if (
            not isinstance(self.areas, tuple)
            or not self.areas
            or any(not isinstance(item, GrindingArea) for item in self.areas)
            or len({item.identity for item in self.areas}) != len(self.areas)
        ):
            raise PartyDevelopmentAdapterError(
                "party-development venues must be unique typed areas"
            )
        if not isinstance(self.goal, PartyDevelopmentGoal):
            raise PartyDevelopmentAdapterError("party-development snapshot goal is invalid")
        if (
            not isinstance(self.member_profiles, tuple)
            or tuple(item.member for item in self.member_profiles) != self.party.members
            or any(
                len(item.projected_survival_by_venue) != len(self.areas)
                or len(item.execution_capabilities_by_venue) != len(self.areas)
                for item in self.member_profiles
            )
        ):
            raise PartyDevelopmentAdapterError(
                "member profiles must align exactly with party and venue order"
            )
        if not isinstance(self.venue_prior_registry, PartyDevelopmentVenuePriorRegistry):
            raise PartyDevelopmentAdapterError(
                "party-development snapshot venue registry is invalid"
            )
        contracts = self.venue_operational_contract_sha256
        if (
            not isinstance(contracts, tuple)
            or len(contracts) != len(self.areas)
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in contracts
            )
        ):
            raise PartyDevelopmentAdapterError(
                "venue operational contracts must align with the venue order"
            )
        for observed, target, subject in (
            (
                self.registration_owned_count,
                self.registration_target_count,
                "registration",
            ),
            (self.living_unique_count, self.living_target_count, "living collection"),
            (self.role_coverage_count, self.role_target_count, "role coverage"),
        ):
            if (
                type(observed) is not int  # noqa: E721
                or type(target) is not int  # noqa: E721
                or target <= 0
                or not 0 <= observed <= target
            ):
                raise PartyDevelopmentAdapterError(
                    f"party-development {subject} counts are invalid"
                )
        conditions = self.active_conditions
        if (
            not isinstance(conditions, tuple)
            or any(not isinstance(item, str) or not item.strip() for item in conditions)
            or conditions != tuple(sorted(set(conditions)))
        ):
            raise PartyDevelopmentAdapterError(
                "party-development active conditions must be sorted and unique"
            )
        if not isinstance(self.venue_prior_feature_mode, VenuePriorFeatureMode):
            raise PartyDevelopmentAdapterError(
                "party-development venue-prior feature mode is invalid"
            )
        if (
            not isinstance(self.execution_protocol_id, str)
            or _SAFE_ID.fullmatch(self.execution_protocol_id) is None
        ):
            raise PartyDevelopmentAdapterError(
                "party-development execution protocol identity is invalid"
            )
        self._require_declared_goal_has_pressure()

    @property
    def semantic_snapshot_sha256(self) -> str:
        """Digest every private fact allowed to influence candidate projection."""

        return canonical_sha256(
            {
                "schema": "pokemon.core.party-development-semantic-snapshot.v1",
                "root_lineage_id": self.root_lineage_id,
                "initial_state_sha256": self.initial_state_sha256,
                "partition": self.partition.value,
                "source_commit": self.source_commit,
                "source_bundle_sha256": self.source_bundle_sha256,
                "party": asdict(self.party),
                "policy": asdict(self.policy),
                "areas": [asdict(item) for item in self.areas],
                "goal": self.goal.value,
                "member_profiles": [asdict(item) for item in self.member_profiles],
                "venue_prior_registry_sha256": (self.venue_prior_registry.registry_sha256),
                "venue_operational_contract_sha256": list(self.venue_operational_contract_sha256),
                "registration_owned_count": self.registration_owned_count,
                "registration_target_count": self.registration_target_count,
                "living_unique_count": self.living_unique_count,
                "living_target_count": self.living_target_count,
                "role_coverage_count": self.role_coverage_count,
                "role_target_count": self.role_target_count,
                "active_conditions": list(self.active_conditions),
                "venue_prior_feature_mode": self.venue_prior_feature_mode.value,
                "execution_protocol_id": self.execution_protocol_id,
            }
        )

    @property
    def context(self) -> PartyDevelopmentContext:
        profiles = self.member_profiles
        party = self.party
        return PartyDevelopmentContext(
            goal=self.goal,
            party_size=party.size,
            below_floor_count=sum(
                member_needs_training(item.member, self.policy) for item in profiles
            ),
            evolution_needed_count=sum(item.evolution.required for item in profiles),
            registration_needed_count=sum(item.registration_needed for item in profiles),
            living_needed_count=sum(item.living_target_needed for item in profiles),
            role_gap_count=min(party.size, self.role_target_count - self.role_coverage_count),
            registration_completion_ratio=(
                self.registration_owned_count / self.registration_target_count
            ),
            living_completion_ratio=(self.living_unique_count / self.living_target_count),
            role_coverage_ratio=self.role_coverage_count / self.role_target_count,
            healthy_trainable_count=sum(
                item.member.is_trainable and item.member.status is StatusCondition.HEALTHY
                for item in profiles
            ),
            exhausted_count=sum(
                not item.member.is_fainted
                and item.member.level < MAX_LEVEL
                and not item.member.usable_moves
                for item in profiles
            ),
            fainted_count=party.fainted_count,
        )

    def trainee_menu(
        self, shared_venue: GrindingArea
    ) -> BoundPartyDevelopmentMenu[PartyMemberObservation] | None:
        """Project trainees under one fixed venue and explicit prior mode."""

        venue_index = self._venue_index(shared_venue)
        if not shared_venue.conditions_match(self.active_conditions):
            raise PartyDevelopmentAdapterError(
                "shared trainee venue is inactive in the observed conditions"
            )
        calibrated_prior = self.venue_prior_registry.prior_for(
            shared_venue,
            operational_contract_sha256=self.venue_operational_contract_sha256[venue_index],
        )
        if (
            self.venue_prior_feature_mode is VenuePriorFeatureMode.CALIBRATED
            and not calibrated_prior.available
        ):
            raise PartyDevelopmentAdapterError(
                "shared trainee venue lacks frozen independent evidence"
            )
        projected = project_trainee_choice_set(
            self.party,
            self.policy,
            (shared_venue,),
            active_conditions=self.active_conditions,
        )
        if projected is None:
            return None
        bindings, base = projected
        profiles = tuple(self._profile_for_member(item) for item in bindings)
        self._require_candidates_can_serve_goal(profiles)
        semantics = tuple(item.semantics_for_venue(venue_index) for item in profiles)
        capabilities = tuple(item.execution_capability_for_venue(venue_index) for item in profiles)
        shared_prior = (
            calibrated_prior
            if self.venue_prior_feature_mode is VenuePriorFeatureMode.CALIBRATED
            else None
        )
        feature_prior = shared_prior or VenueOperationalPrior()
        repeated_prior = tuple(feature_prior for _ in bindings)
        candidate_set = augment_training_candidate_set(
            base,
            self.context,
            semantics,
            venue_priors=repeated_prior,
        )
        if sum(item.available for item in capabilities) < 2:
            return None
        return BoundPartyDevelopmentMenu(
            candidate_set=candidate_set,
            semantic_snapshot_sha256=self.semantic_snapshot_sha256,
            bindings=bindings,
            candidate_available=tuple(item.available for item in capabilities),
            candidate_unavailable_reasons=tuple(item.unavailable_reason for item in capabilities),
            venue_priors=repeated_prior,
            shared_venue=shared_venue,
            shared_venue_prior=shared_prior,
            venue_prior_feature_mode=self.venue_prior_feature_mode,
        )

    def venue_menu(
        self,
        trainee: PartyMemberObservation,
        *,
        require_healer: bool = True,
    ) -> BoundPartyDevelopmentMenu[GrindingArea] | None:
        """Project viable venues for one exact private trainee binding."""

        profile = self._profile_for_member(trainee)
        self._require_candidates_can_serve_goal((profile,))
        projected = project_venue_choice_set(
            self.party,
            trainee,
            self.policy,
            self.areas,
            require_healer=require_healer,
            active_conditions=self.active_conditions,
        )
        if projected is None:
            return None
        bindings, base = projected
        indexes = tuple(self._venue_index(item) for item in bindings)
        priors = (
            tuple(
                self.venue_prior_registry.prior_for(
                    item,
                    operational_contract_sha256=(
                        self.venue_operational_contract_sha256[index]
                    ),
                )
                for item, index in zip(bindings, indexes, strict=True)
            )
            if self.venue_prior_feature_mode is VenuePriorFeatureMode.CALIBRATED
            else tuple(VenueOperationalPrior() for _ in bindings)
        )
        semantics = tuple(profile.semantics_for_venue(index) for index in indexes)
        capabilities = tuple(profile.execution_capability_for_venue(index) for index in indexes)
        candidate_set = augment_training_candidate_set(
            base,
            self.context,
            semantics,
            venue_priors=priors,
        )
        availability = tuple(
            capability.available
            and (
                prior.available
                or self.venue_prior_feature_mode
                is VenuePriorFeatureMode.MASKED_UNCALIBRATED
            )
            for prior, capability in zip(priors, capabilities, strict=True)
        )
        reasons = tuple(
            (
                PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE
                if (
                    not prior.available
                    and self.venue_prior_feature_mode is VenuePriorFeatureMode.CALIBRATED
                )
                else capability.unavailable_reason
            )
            for prior, capability in zip(priors, capabilities, strict=True)
        )
        if sum(availability) < 2:
            return None
        return BoundPartyDevelopmentMenu(
            candidate_set=candidate_set,
            semantic_snapshot_sha256=self.semantic_snapshot_sha256,
            bindings=bindings,
            candidate_available=availability,
            candidate_unavailable_reasons=reasons,
            venue_priors=priors,
            venue_prior_feature_mode=self.venue_prior_feature_mode,
        )

    def unique_weakest_goal_relevant_venue_trainee(
        self,
    ) -> PartyMemberObservation:
        """Choose a venue-question context without teaching the venue answer.

        A venue question needs one fixed trainee before its candidate venues can
        be compared.  The context rule uses only portable semantics: the member
        must still need training, must reduce the declared completion pressure,
        and must have at least two viable venue candidates.  The weakest such
        member is selected.  A level tie fails closed because breaking it by
        party slot or species would smuggle private title identity into
        curriculum construction.
        """

        eligible: list[PartyMemberObservation] = []
        for profile in self.member_profiles:
            if (
                not member_needs_training(profile.member, self.policy)
                or not profile.member.is_trainable
                or not self._profile_can_serve_goal(profile)
            ):
                continue
            menu = self.venue_menu(profile.member)
            if menu is not None and sum(menu.candidate_available) >= 2:
                eligible.append(profile.member)
        if not eligible:
            raise PartyDevelopmentAdapterError(
                "venue context has no goal-relevant trainee with two viable venues"
            )
        weakest_level = min(member.level for member in eligible)
        weakest = tuple(member for member in eligible if member.level == weakest_level)
        if len(weakest) != 1:
            raise PartyDevelopmentAdapterError(
                "venue context weakest goal-relevant trainee is not semantically unique"
            )
        return weakest[0]

    def freeze_binding(
        self,
        menu: (
            BoundPartyDevelopmentMenu[PartyMemberObservation]
            | BoundPartyDevelopmentMenu[GrindingArea]
        ),
        *,
        scenario_id: str,
    ) -> PartyDevelopmentProspectiveBinding:
        """Bind one adapter menu after proving prior/candidate independence."""

        if not isinstance(menu, BoundPartyDevelopmentMenu):
            raise TypeError("menu must be a BoundPartyDevelopmentMenu")
        if menu.semantic_snapshot_sha256 != self.semantic_snapshot_sha256:
            raise PartyDevelopmentAdapterError("menu belongs to a different semantic snapshot")
        self.venue_prior_registry.require_scenario_is_independent(
            root_lineage_id=self.root_lineage_id,
            initial_state_sha256=self.initial_state_sha256,
        )
        return PartyDevelopmentProspectiveBinding.build(
            scenario_id=scenario_id,
            root_lineage_id=self.root_lineage_id,
            initial_state_sha256=self.initial_state_sha256,
            partition=self.partition,
            source_commit=self.source_commit,
            source_bundle_sha256=self.source_bundle_sha256,
            semantic_snapshot_sha256=self.semantic_snapshot_sha256,
            candidate_set=menu.candidate_set,
            venue_priors=menu.venue_priors,
            shared_venue_prior=menu.shared_venue_prior,
            venue_prior_feature_mode=menu.venue_prior_feature_mode,
            venue_prior_registry_sha256=self.venue_prior_registry.registry_sha256,
            outcome_objective_sha256=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256),
            candidate_available=menu.candidate_available,
            candidate_unavailable_reasons=menu.candidate_unavailable_reasons,
        )

    def _profile_for_member(self, member: PartyMemberObservation) -> PartyDevelopmentMemberProfile:
        if not isinstance(member, PartyMemberObservation):
            raise TypeError("member must be a PartyMemberObservation")
        match = next(
            (
                item
                for item in self.member_profiles
                if item.member.slot == member.slot and item.member == member
            ),
            None,
        )
        if match is None:
            raise PartyDevelopmentAdapterError("member does not match the semantic snapshot")
        return match

    def _venue_index(self, venue: GrindingArea) -> int:
        if not isinstance(venue, GrindingArea):
            raise TypeError("venue must be a GrindingArea")
        matches = tuple(index for index, item in enumerate(self.areas) if item == venue)
        if len(matches) != 1:
            raise PartyDevelopmentAdapterError("venue does not match exactly one snapshot binding")
        return matches[0]

    def _require_declared_goal_has_pressure(self) -> None:
        context = self.context
        pressure = {
            PartyDevelopmentGoal.BALANCE: (
                context.below_floor_count > 0
                or self.party.size < self.policy.required_size
                or (self.party.level_spread or 0) > self.policy.maximum_level_spread
            ),
            PartyDevelopmentGoal.EVOLUTION: context.evolution_needed_count > 0,
            PartyDevelopmentGoal.COLLECTION: (
                context.registration_completion_ratio < 1.0 or context.living_completion_ratio < 1.0
            ),
            PartyDevelopmentGoal.ROLE_COVERAGE: context.role_gap_count > 0,
        }[self.goal]
        if not pressure:
            raise PartyDevelopmentAdapterError(
                "declared party-development goal has no observed pressure"
            )

    def _require_candidates_can_serve_goal(
        self, profiles: tuple[PartyDevelopmentMemberProfile, ...]
    ) -> None:
        if not profiles:
            raise PartyDevelopmentAdapterError("party-development menu has no candidate profiles")
        if not any(self._profile_can_serve_goal(item) for item in profiles):
            raise PartyDevelopmentAdapterError(
                "candidate menu cannot reduce its declared completion pressure"
            )

    def _profile_can_serve_goal(self, profile: PartyDevelopmentMemberProfile) -> bool:
        useful = {
            PartyDevelopmentGoal.BALANCE: lambda item: member_needs_training(
                item.member, self.policy
            ),
            PartyDevelopmentGoal.EVOLUTION: lambda item: item.evolution.required,
            PartyDevelopmentGoal.COLLECTION: lambda item: (
                item.registration_needed or item.living_target_needed
            ),
            PartyDevelopmentGoal.ROLE_COVERAGE: lambda item: item.role_needed,
        }[self.goal]
        return useful(profile)


__all__ = [
    "BoundPartyDevelopmentMenu",
    "PartyDevelopmentAdapterError",
    "PartyDevelopmentCapabilityState",
    "PartyDevelopmentExecutionCapability",
    "PartyDevelopmentMemberProfile",
    "PartyDevelopmentSemanticSnapshot",
]
