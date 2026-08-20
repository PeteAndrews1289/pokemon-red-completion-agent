"""Crystal-private capability masks and executable goal bindings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pokemon_crystal_completion.goal_state import (
    CrystalCapability,
    CrystalGoalObservation,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
)


class CrystalGoalBindingError(ValueError):
    """Raised when Crystal exposes authority without an exact live binding."""


@dataclass(frozen=True, slots=True)
class CrystalGoalBindingOffer:
    """One available private binding or one portable reason it is masked."""

    kind: GoalKind
    binding: ExecutableGoalBinding | None = None
    unavailable_reason: GoalUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind):
            raise CrystalGoalBindingError("Crystal goal offer kind is invalid")
        if self.binding is not None:
            if self.binding.kind is not self.kind:
                raise CrystalGoalBindingError("Crystal offer and binding kinds differ")
            if self.unavailable_reason is not None:
                raise CrystalGoalBindingError("available Crystal goal cannot be unavailable")
        elif not isinstance(self.unavailable_reason, GoalUnavailableReason):
            raise CrystalGoalBindingError("masked Crystal goal needs an unavailable reason")

    @classmethod
    def available(cls, binding: ExecutableGoalBinding) -> CrystalGoalBindingOffer:
        return cls(kind=binding.kind, binding=binding)

    @classmethod
    def unavailable(
        cls,
        kind: GoalKind,
        reason: GoalUnavailableReason,
    ) -> CrystalGoalBindingOffer:
        return cls(kind=kind, unavailable_reason=reason)


class CrystalGoalBindingProvider(Protocol):
    @property
    def kind(self) -> GoalKind: ...

    def offer(self, observation: CrystalGoalObservation) -> CrystalGoalBindingOffer: ...


CrystalBindingResolver = Callable[
    [CrystalGoalObservation],
    ExecutableGoalBinding | GoalUnavailableReason,
]


@dataclass(frozen=True, slots=True)
class CapabilityBoundCrystalGoalProvider:
    """Mask a provider before its resolver can advertise executable authority."""

    kind: GoalKind
    required_capabilities: frozenset[CrystalCapability]
    resolver: CrystalBindingResolver

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind):
            raise CrystalGoalBindingError("Crystal provider kind is invalid")
        if not isinstance(self.required_capabilities, frozenset) or any(
            not isinstance(item, CrystalCapability) for item in self.required_capabilities
        ):
            raise CrystalGoalBindingError("Crystal provider capabilities are invalid")
        if not callable(self.resolver):
            raise CrystalGoalBindingError("Crystal provider resolver is not callable")

    def offer(self, observation: CrystalGoalObservation) -> CrystalGoalBindingOffer:
        if not isinstance(observation, CrystalGoalObservation):
            raise TypeError("observation must be CrystalGoalObservation")
        capabilities = observation.snapshot.capabilities
        if self.required_capabilities & capabilities.unknown:
            return CrystalGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.WORLD_STATE_UNKNOWN,
            )
        if not self.required_capabilities <= capabilities.available:
            return CrystalGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.MISSING_CAPABILITY,
            )
        result = self.resolver(observation)
        if isinstance(result, GoalUnavailableReason):
            return CrystalGoalBindingOffer.unavailable(self.kind, result)
        if not isinstance(result, ExecutableGoalBinding) or result.kind is not self.kind:
            raise CrystalGoalBindingError("Crystal provider returned a different binding kind")
        return CrystalGoalBindingOffer.available(result)


@dataclass(frozen=True, slots=True)
class CrystalGoalOpportunityEnumerator:
    """Expose all nine kinds while retaining only exact bindings as authority."""

    providers: tuple[CrystalGoalBindingProvider, ...]

    def __post_init__(self) -> None:
        kinds = tuple(provider.kind for provider in self.providers)
        if any(not isinstance(kind, GoalKind) for kind in kinds):
            raise CrystalGoalBindingError("Crystal goal provider has an invalid kind")
        if len(kinds) != len(set(kinds)):
            raise CrystalGoalBindingError("Crystal goal providers must not duplicate a kind")

    def enumerate(
        self,
        observation: CrystalGoalObservation,
        *,
        candidate_order: tuple[GoalKind, ...] = tuple(GoalKind),
    ) -> GoalBindingSet:
        if not isinstance(observation, CrystalGoalObservation):
            raise TypeError("observation must be CrystalGoalObservation")
        if (
            not isinstance(candidate_order, tuple)
            or len(candidate_order) != len(GoalKind)
            or set(candidate_order) != set(GoalKind)
        ):
            raise CrystalGoalBindingError("Crystal candidate order must contain every goal kind")
        providers = {provider.kind: provider for provider in self.providers}
        opportunities: list[GoalOpportunity] = []
        bindings: list[ExecutableGoalBinding] = []
        for kind in candidate_order:
            provider = providers.get(kind)
            offer = (
                CrystalGoalBindingOffer.unavailable(
                    kind,
                    GoalUnavailableReason.MISSING_CAPABILITY,
                )
                if provider is None
                else provider.offer(observation)
            )
            if offer.kind is not kind:
                raise CrystalGoalBindingError("Crystal provider returned a different kind")
            if offer.binding is not None:
                opportunities.append(offer.binding.opportunity)
                bindings.append(offer.binding)
            else:
                assert offer.unavailable_reason is not None
                opportunities.append(
                    GoalOpportunity(
                        binding_ref=f"pokemon.crystal:goal:{kind.value}:unavailable",
                        kind=kind,
                        availability=GoalAvailability.UNAVAILABLE,
                        unavailable_reason=offer.unavailable_reason,
                    )
                )
        return GoalBindingSet(tuple(opportunities), tuple(bindings))


__all__ = [
    "CapabilityBoundCrystalGoalProvider",
    "CrystalBindingResolver",
    "CrystalGoalBindingError",
    "CrystalGoalBindingOffer",
    "CrystalGoalBindingProvider",
    "CrystalGoalOpportunityEnumerator",
]
