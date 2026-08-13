"""Normalize semantic campaign evidence for the portable goal manager.

Title adapters provide counts and shared party/collection observations.  This
module converts them to zero-to-one satisfaction values before
``GoalSituation`` turns satisfaction into pressure.  Different Pokédex sizes,
badge totals, party species, and level curves therefore remain adapter data,
not model identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.collection import CollectionReport
from pokemon_red_completion.goal_manager import GoalManagerError, GoalSituation
from pokemon_red_completion.party import PartyObservation, StatusCondition


@dataclass(frozen=True, slots=True)
class CompletionProgress:
    """A bounded completed/target measurement from any title adapter."""

    completed: int
    target: int

    def __post_init__(self) -> None:
        if type(self.target) is not int or self.target < 0:  # noqa: E721
            raise GoalManagerError("completion target must be a non-negative integer")
        if (  # noqa: E721
            type(self.completed) is not int or self.completed < 0 or self.completed > self.target
        ):
            raise GoalManagerError("completed progress must fit its target")

    @property
    def satisfaction(self) -> float:
        return 1.0 if self.target == 0 else self.completed / self.target


@dataclass(frozen=True, slots=True)
class GoalStateEvidence:
    """Identity-free satisfaction evidence immediately before arbitration."""

    story: CompletionProgress
    registered_collection: CompletionProgress
    living_collection: CompletionProgress
    team_readiness: float
    evolution: CompletionProgress
    safety: float
    resources: float
    storage: float
    control: float
    world_knowledge: CompletionProgress

    def __post_init__(self) -> None:
        for name in (
            "story",
            "registered_collection",
            "living_collection",
            "evolution",
            "world_knowledge",
        ):
            if not isinstance(getattr(self, name), CompletionProgress):
                raise GoalManagerError(f"{name} must be CompletionProgress")
        for name in ("team_readiness", "safety", "resources", "storage", "control"):
            object.__setattr__(self, name, _unit(getattr(self, name), subject=name))

    def situation(self) -> GoalSituation:
        """Compose strict collection/team/safety satisfaction into need pressure."""

        return GoalSituation.from_satisfaction(
            story=self.story.satisfaction,
            collection=min(
                self.registered_collection.satisfaction,
                self.living_collection.satisfaction,
            ),
            team=self.team_readiness,
            evolution=self.evolution.satisfaction,
            safety=self.safety,
            resources=self.resources,
            storage=self.storage,
            control=self.control,
            world_knowledge=self.world_knowledge.satisfaction,
        )


def goal_state_evidence(
    *,
    story: CompletionProgress,
    collection: CollectionReport,
    party: PartyObservation,
    required_party_size: int,
    required_team_level: int,
    evolution: CompletionProgress,
    available_resources: int,
    desired_resources: int,
    free_storage_slots: int,
    desired_storage_headroom: int,
    control_stable: bool,
    world_knowledge: CompletionProgress,
) -> GoalStateEvidence:
    """Compose existing semantic reports without reading a title's raw state."""

    if not isinstance(collection, CollectionReport):
        raise TypeError("collection must be a CollectionReport")
    if not isinstance(party, PartyObservation):
        raise TypeError("party must be a PartyObservation")
    if not isinstance(control_stable, bool):
        raise TypeError("control_stable must be a boolean")
    return GoalStateEvidence(
        story=story,
        registered_collection=CompletionProgress(
            completed=collection.pokedex_owned_count,
            target=collection.target_count,
        ),
        living_collection=CompletionProgress(
            completed=collection.living_count,
            target=collection.living_target_count,
        ),
        team_readiness=party_readiness_satisfaction(
            party,
            required_size=required_party_size,
            required_level=required_team_level,
        ),
        evolution=evolution,
        safety=party_safety_satisfaction(party),
        resources=headroom_satisfaction(
            available_resources,
            desired_resources,
            subject="resource",
        ),
        storage=headroom_satisfaction(
            free_storage_slots,
            desired_storage_headroom,
            subject="storage",
        ),
        control=float(control_stable),
        world_knowledge=world_knowledge,
    )


def party_readiness_satisfaction(
    party: PartyObservation,
    *,
    required_size: int,
    required_level: int,
) -> float:
    """Average roster-and-level readiness, counting missing members as zero."""

    if not isinstance(party, PartyObservation):
        raise TypeError("party must be a PartyObservation")
    if type(required_size) is not int or not 1 <= required_size <= party.capacity:  # noqa: E721
        raise GoalManagerError("required party size must fit the party capacity")
    if type(required_level) is not int or not 1 <= required_level <= 100:  # noqa: E721
        raise GoalManagerError("required team level must be between one and one hundred")
    member_readiness = [
        min(member.level / required_level, 1.0) for member in party.members[:required_size]
    ]
    member_readiness.extend(0.0 for _ in range(required_size - len(member_readiness)))
    return sum(member_readiness) / required_size


def party_safety_satisfaction(party: PartyObservation) -> float:
    """Conservatively combine health, status, and ability to take a turn."""

    if not isinstance(party, PartyObservation):
        raise TypeError("party must be a PartyObservation")
    if not party.members:
        return 1.0
    total_hp = sum(member.hp for member in party.members)
    total_max_hp = sum(member.max_hp for member in party.members)
    health = total_hp / total_max_hp
    healthy = sum(member.status is StatusCondition.HEALTHY for member in party.members) / party.size
    battle_ready = party.battle_ready_count / party.size
    return min(health, healthy, battle_ready)


def headroom_satisfaction(
    available: int,
    desired: int,
    *,
    subject: str,
) -> float:
    """Return one once a declared resource/storage reserve is satisfied."""

    if type(available) is not int or available < 0:  # noqa: E721
        raise GoalManagerError(f"available {subject} headroom must be non-negative")
    if type(desired) is not int or desired < 0:  # noqa: E721
        raise GoalManagerError(f"desired {subject} headroom must be non-negative")
    return 1.0 if desired == 0 else min(available / desired, 1.0)


def _unit(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalManagerError(f"{subject} satisfaction must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise GoalManagerError(f"{subject} satisfaction must be between zero and one")
    return result
