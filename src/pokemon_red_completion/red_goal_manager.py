"""Live Pokémon Red adapter for portable high-level goal arbitration.

This module composes story, party, Pokédex, all-box, inventory and control
evidence at one stable boundary.  It also turns registered bounded Red skills
into a complete semantic candidate menu: missing or blocked skills remain
visible but hard-masked, while available candidates retain private bindings
only on the executor side of the policy boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    GoalStateEvidence,
    headroom_satisfaction,
    party_readiness_satisfaction,
    party_safety_satisfaction,
)
from pokemon_red_completion.objective_skills import ObjectiveSkillRegistry
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    RawGameState,
    RedBoxCollectionState,
    RedPokedexState,
)
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.quest import QuestGraph, Specialist
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAcquisitionKind,
)
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    RedCollectionProgress,
    red_collection_observation,
    summarize_red_collection,
)
from pokemon_red_completion.red_party import party_observation_from_raw


class RedGoalManagerError(RuntimeError):
    """Raised when live Red evidence cannot support a truthful goal menu."""


class RedGoalStateReader(Protocol):
    def read(self) -> RawGameState: ...

    def read_pokedex_state(self) -> RedPokedexState: ...

    def read_all_box_states(self) -> RedBoxCollectionState: ...

    def read_input_readiness(self) -> InputReadiness: ...


class RedSemanticObserver(Protocol):
    def observe(self) -> GameState: ...

    def observe_raw(self, raw: RawGameState) -> GameState: ...


@dataclass(frozen=True, slots=True)
class RedGoalManagerConfig:
    """Declared Red challenge and reserve targets used only for normalization."""

    required_party_size: int = 6
    required_team_level: int = 60
    desired_capture_items: int = 10
    desired_recovery_items: int = 8
    desired_storage_headroom: int = 8

    def __post_init__(self) -> None:
        if type(self.required_party_size) is not int or not 1 <= self.required_party_size <= 6:
            raise ValueError("required_party_size must be between one and six")
        if type(self.required_team_level) is not int or not 1 <= self.required_team_level <= 100:
            raise ValueError("required_team_level must be between one and one hundred")
        for name in (
            "desired_capture_items",
            "desired_recovery_items",
            "desired_storage_headroom",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class RedGoalObservation:
    """One coherent adapter observation; raw identity never enters the model."""

    raw: RawGameState
    game_state: GameState
    party: PartyObservation
    collection: RedCollectionProgress
    collection_observation: CollectionObservation
    evidence: GoalStateEvidence
    input_ready: bool
    capture_item_count: int
    recovery_item_count: int
    free_storage_slots: int
    immediate_capture_slots: int

    @property
    def situation(self) -> GoalSituation:
        return self.evidence.situation()

    def public_dict(self) -> dict[str, object]:
        """Return counts and normalized evidence without raw Red identities."""

        return {
            "schema": "pokemon.red.goal-observation.v1",
            "story": {
                "completed": self.evidence.story.completed,
                "target": self.evidence.story.target,
            },
            "collection": {
                "registered": self.evidence.registered_collection.completed,
                "registered_target": self.evidence.registered_collection.target,
                "living": self.evidence.living_collection.completed,
                "living_target": self.evidence.living_collection.target,
                "level_cap": self.evidence.level_collection.completed,
                "level_cap_target": self.evidence.level_collection.target,
            },
            "party_size": self.party.size,
            "input_ready": self.input_ready,
            "capture_item_count": self.capture_item_count,
            "recovery_item_count": self.recovery_item_count,
            "free_storage_slots": self.free_storage_slots,
            "immediate_capture_slots": self.immediate_capture_slots,
            "situation": self.situation.policy_dict(),
            "private_path_fields": 0,
            "raw_address_fields": 0,
        }


@dataclass(slots=True)
class PokemonRedGoalStateAdapter:
    """Compose every manager pressure from authenticated live Red readers."""

    reader: RedGoalStateReader
    semantic_observer: RedSemanticObserver
    graph: QuestGraph
    config: RedGoalManagerConfig = RedGoalManagerConfig()
    acquisition_catalog: RedAcquisitionCatalog = RED_ACQUISITION_CATALOG

    def observe(self) -> RedGoalObservation:
        raw = self.reader.read()
        game_state = self.semantic_observer.observe_raw(raw)
        party = party_observation_from_raw(raw)
        pokedex = self.reader.read_pokedex_state()
        boxes = self.reader.read_all_box_states()
        collection_observation = red_collection_observation(pokedex, party, boxes)
        collection = summarize_red_collection(pokedex, party, boxes)
        input_ready = self.reader.read_input_readiness().ready

        inventory = dict(raw.bag_items or ())
        capture_items = _quantity(
            inventory,
            ItemId.POKE_BALL,
            ItemId.GREAT_BALL,
            ItemId.ULTRA_BALL,
            ItemId.MASTER_BALL,
        )
        recovery_items = _quantity(
            inventory,
            ItemId.POTION,
            ItemId.SUPER_POTION,
            ItemId.HYPER_POTION,
            ItemId.FULL_RESTORE,
            ItemId.ANTIDOTE,
            ItemId.AWAKENING,
            ItemId.PARLYZ_HEAL,
            ItemId.FULL_HEAL,
            ItemId.REVIVE,
        )
        free_storage = sum(20 - count for count in boxes.counts)
        immediate_capture_slots = (6 - party.size) + (
            20 - boxes.counts[boxes.current_box_index]
        )
        evolution_targets = tuple(
            method.species_ref
            for method in self.acquisition_catalog.methods
            if method.kind is RedAcquisitionKind.EVOLUTION
        )
        owned_refs = collection_observation.owned_species
        completed_objectives = self.graph.completed_ids(game_state)
        report = collection.collection
        resources = min(
            headroom_satisfaction(
                capture_items,
                self.config.desired_capture_items,
                subject="capture item",
            ),
            headroom_satisfaction(
                recovery_items,
                self.config.desired_recovery_items,
                subject="recovery item",
            ),
        )
        evidence = GoalStateEvidence(
            story=CompletionProgress(len(completed_objectives), len(self.graph)),
            registered_collection=CompletionProgress(
                report.pokedex_owned_count,
                report.target_count,
            ),
            living_collection=CompletionProgress(
                report.living_count,
                report.living_target_count,
            ),
            level_collection=CompletionProgress(
                report.level_cap_count,
                report.living_target_count,
            ),
            team_readiness=party_readiness_satisfaction(
                party,
                required_size=self.config.required_party_size,
                required_level=self.config.required_team_level,
            ),
            evolution=CompletionProgress(
                sum(species_ref in owned_refs for species_ref in evolution_targets),
                len(evolution_targets),
            ),
            safety=party_safety_satisfaction(party),
            resources=resources,
            storage=headroom_satisfaction(
                immediate_capture_slots,
                self.config.desired_storage_headroom,
                subject="immediate capture storage",
            ),
            control=float(raw.game_started and input_ready),
            world_knowledge=CompletionProgress(
                len(collection.pokedex.seen_target_numbers),
                len(RED_SOLO_COLLECTION_CONTRACT.target_species),
            ),
        )
        return RedGoalObservation(
            raw=raw,
            game_state=game_state,
            party=party,
            collection=collection,
            collection_observation=collection_observation,
            evidence=evidence,
            input_ready=input_ready,
            capture_item_count=capture_items,
            recovery_item_count=recovery_items,
            free_storage_slots=free_storage,
            immediate_capture_slots=immediate_capture_slots,
        )


@dataclass(frozen=True, slots=True)
class RedGoalBindingOffer:
    """Available private binding or one portable reason it is masked."""

    kind: GoalKind
    binding: ExecutableGoalBinding | None = None
    unavailable_reason: GoalUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind):
            raise RedGoalManagerError("Red goal offer kind is invalid")
        if self.binding is not None:
            if self.binding.kind is not self.kind:
                raise RedGoalManagerError("Red goal offer and binding kinds differ")
            if self.unavailable_reason is not None:
                raise RedGoalManagerError("an available Red goal cannot be unavailable")
        elif not isinstance(self.unavailable_reason, GoalUnavailableReason):
            raise RedGoalManagerError("a masked Red goal needs an unavailable reason")

    @classmethod
    def available(cls, binding: ExecutableGoalBinding) -> RedGoalBindingOffer:
        return cls(kind=binding.kind, binding=binding)

    @classmethod
    def unavailable(
        cls,
        kind: GoalKind,
        reason: GoalUnavailableReason,
    ) -> RedGoalBindingOffer:
        return cls(kind=kind, unavailable_reason=reason)


class RedGoalBindingProvider(Protocol):
    @property
    def kind(self) -> GoalKind: ...

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer: ...


@dataclass(frozen=True, slots=True)
class CallableRedGoalBindingProvider:
    """Small adapter for existing bounded specialists and captured contexts."""

    kind: GoalKind
    resolver: Callable[[RedGoalObservation], RedGoalBindingOffer]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind):
            raise RedGoalManagerError("callable Red goal provider kind is invalid")
        if not callable(self.resolver):
            raise RedGoalManagerError("callable Red goal provider needs a resolver")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        result = self.resolver(observation)
        if not isinstance(result, RedGoalBindingOffer) or result.kind is not self.kind:
            raise RedGoalManagerError("callable Red goal provider returned a different kind")
        return result


@dataclass(frozen=True, slots=True)
class RedStoryGoalBindingProvider:
    """Bind one dependency-legal story objective below the goal manager."""

    graph: QuestGraph
    skills: ObjectiveSkillRegistry
    observer: RedSemanticObserver
    kind: GoalKind = GoalKind.ADVANCE_STORY

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if not isinstance(observation, RedGoalObservation):
            raise TypeError("observation must be a RedGoalObservation")
        dependency_legal = self.graph.available_objectives(observation.game_state)
        if not dependency_legal:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        executable = []
        registered = 0
        for objective in dependency_legal:
            skill = self.skills.get(objective.id)
            if skill is None:
                continue
            registered += 1
            # require_for rejects a registry whose declared authority drifted.
            self.skills.require_for(objective)
            if skill.availability(observation.game_state).executable:
                executable.append((objective, skill))
        if not executable:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                (
                    GoalUnavailableReason.MISSING_CAPABILITY
                    if registered == 0
                    else GoalUnavailableReason.TEMPORARILY_BLOCKED
                ),
            )
        objective, skill = executable[0]
        completed_before = self.graph.completed_ids(observation.game_state)

        def execute() -> GoalExecutionReport:
            result = self.skills.execute_bounded(skill)
            return GoalExecutionReport(
                actions_executed=result.actions_executed,
                frames_executed=result.frames_executed,
                evidence={
                    "bounded": True,
                    "declared_effect_count": (
                        len(skill.expected_facts) + len(skill.additional_effect_facts)
                    ),
                },
            )

        def verify(_execution: GoalExecutionReport) -> GoalVerification:
            after = self.observer.observe()
            completed_after = self.graph.completed_ids(after)
            if completed_before.difference(completed_after):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            expected = objective.completion_facts.union(skill.additional_effect_facts)
            if not expected.issubset(after.facts):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=f"pokemon.red:story:{objective.id}",
                kind=self.kind,
                estimated_effort=_objective_effort(skill.max_actions, skill.max_frames),
                estimated_risk=_specialist_risk(objective.specialist),
                execute=execute,
                verify=verify,
            )
        )


@dataclass(frozen=True, slots=True)
class RedGoalOpportunityEnumerator:
    """Produce all nine kinds while granting authority only to live bindings."""

    providers: tuple[RedGoalBindingProvider, ...]

    def __post_init__(self) -> None:
        kinds = tuple(provider.kind for provider in self.providers)
        if any(not isinstance(kind, GoalKind) for kind in kinds):
            raise RedGoalManagerError("Red goal provider has an invalid kind")
        if len(kinds) != len(set(kinds)):
            raise RedGoalManagerError("Red goal providers must not duplicate a kind")

    def enumerate(self, observation: RedGoalObservation) -> GoalBindingSet:
        if not isinstance(observation, RedGoalObservation):
            raise TypeError("observation must be a RedGoalObservation")
        providers = {provider.kind: provider for provider in self.providers}
        opportunities: list[GoalOpportunity] = []
        bindings: list[ExecutableGoalBinding] = []
        for kind in GoalKind:
            provider = providers.get(kind)
            offer = (
                RedGoalBindingOffer.unavailable(
                    kind,
                    GoalUnavailableReason.MISSING_CAPABILITY,
                )
                if provider is None
                else provider.offer(observation)
            )
            if offer.kind is not kind:
                raise RedGoalManagerError("Red goal provider returned a different kind")
            if offer.binding is not None:
                opportunities.append(offer.binding.opportunity)
                bindings.append(offer.binding)
            else:
                assert offer.unavailable_reason is not None
                opportunities.append(
                    GoalOpportunity(
                        binding_ref=f"pokemon.red:goal:{kind.value}:unavailable",
                        kind=kind,
                        availability=GoalAvailability.UNAVAILABLE,
                        unavailable_reason=offer.unavailable_reason,
                    )
                )
        return GoalBindingSet(tuple(opportunities), tuple(bindings))


def _quantity(inventory: dict[int, int], *item_ids: ItemId) -> int:
    return sum(inventory.get(int(item_id), 0) for item_id in item_ids)


def _objective_effort(max_actions: int, max_frames: int) -> float:
    return min(1.0, max(max_actions / 5_000, max_frames / 5_000_000))


def _specialist_risk(specialist: Specialist) -> float:
    return {
        Specialist.BOOTSTRAP: 0.05,
        Specialist.NAVIGATION: 0.20,
        Specialist.INTERACTION: 0.10,
        Specialist.MENU: 0.05,
        Specialist.BATTLE: 0.35,
        Specialist.RECOVERY: 0.05,
        Specialist.VERIFICATION: 0.01,
    }[specialist]
