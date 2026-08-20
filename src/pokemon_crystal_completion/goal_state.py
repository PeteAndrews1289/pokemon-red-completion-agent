"""Semantic Pokemon Crystal state for the portable goal manager.

Revision-specific memory decoding stops at :class:`CrystalCampaignSnapshot`.
The shared model receives only the normalized :class:`GoalSituation`; species,
maps, coordinates, item identities, raw addresses, and private skill bindings
remain on the adapter side of the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pokemon_red_completion.goal_manager import GoalSituation
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    GoalStateEvidence,
    headroom_satisfaction,
    party_readiness_satisfaction,
    party_safety_satisfaction,
)
from pokemon_red_completion.party import PartyObservation


class CrystalGoalStateError(ValueError):
    """Raised when Crystal evidence cannot support a truthful projection."""


class CrystalCapability(StrEnum):
    """Adapter-private mechanics needed by completion and living-dex work.

    The model does not receive this set.  Providers use it to decide whether a
    semantic goal has a real executable binding; the policy sees only the
    resulting availability mask and a portable unavailable reason.
    """

    OVERWORLD_MOVEMENT = "overworld_movement"
    INTERACTION = "interaction"
    BATTLE = "battle"
    CAPTURE = "capture"
    PARTY_TRAINING = "party_training"
    CENTER_HEALING = "center_healing"
    SHOPPING = "shopping"
    PC_STORAGE = "pc_storage"
    LEVEL_EVOLUTION = "level_evolution"
    ITEM_EVOLUTION = "item_evolution"
    HAPPINESS_EVOLUTION = "happiness_evolution"
    TIME_EVOLUTION = "time_evolution"
    TRADE = "trade"
    TRADE_EVOLUTION = "trade_evolution"
    BREEDING = "breeding"
    TIME_OF_DAY_WAIT = "time_of_day_wait"
    CUT = "cut"
    FLY = "fly"
    SURF = "surf"
    STRENGTH = "strength"
    FLASH = "flash"
    WHIRLPOOL = "whirlpool"
    WATERFALL = "waterfall"
    HEADBUTT = "headbutt"
    ROCK_SMASH = "rock_smash"
    STATIC_ENCOUNTER = "static_encounter"
    ROAMING_ENCOUNTER = "roaming_encounter"
    PUZZLE_INTERACTION = "puzzle_interaction"


@dataclass(frozen=True, slots=True)
class CrystalCapabilityState:
    """Known available and unknown mechanics at one observed boundary."""

    available: frozenset[CrystalCapability] = frozenset()
    unknown: frozenset[CrystalCapability] = frozenset(CrystalCapability)

    def __post_init__(self) -> None:
        for name in ("available", "unknown"):
            value = getattr(self, name)
            if not isinstance(value, frozenset) or any(
                not isinstance(item, CrystalCapability) for item in value
            ):
                raise CrystalGoalStateError(f"{name} capabilities must be a typed frozenset")
        if self.available & self.unknown:
            raise CrystalGoalStateError("a Crystal capability cannot be available and unknown")

    @property
    def unavailable(self) -> frozenset[CrystalCapability]:
        return frozenset(CrystalCapability) - self.available - self.unknown


@dataclass(frozen=True, slots=True)
class CrystalGoalManagerConfig:
    """Declared challenge and reserve targets used only for normalization."""

    required_party_size: int = 6
    required_team_level: int = 50
    desired_capture_items: int = 10
    desired_recovery_items: int = 8
    desired_storage_headroom: int = 8

    def __post_init__(self) -> None:
        if type(self.required_party_size) is not int or not 1 <= self.required_party_size <= 6:
            raise CrystalGoalStateError("required party size must be between one and six")
        if type(self.required_team_level) is not int or not 1 <= self.required_team_level <= 100:
            raise CrystalGoalStateError("required team level must be between one and one hundred")
        for name in (
            "desired_capture_items",
            "desired_recovery_items",
            "desired_storage_headroom",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise CrystalGoalStateError(f"{name} must be a non-negative integer")


DEFAULT_CRYSTAL_GOAL_MANAGER_CONFIG = CrystalGoalManagerConfig()


@dataclass(frozen=True, slots=True)
class CrystalCampaignSnapshot:
    """One coherent semantic read from a revision-specific Crystal reader."""

    story: CompletionProgress
    registered_collection: CompletionProgress
    living_collection: CompletionProgress
    level_collection: CompletionProgress
    evolution: CompletionProgress
    world_knowledge: CompletionProgress
    party: PartyObservation
    game_started: bool
    input_ready: bool
    capture_item_count: int
    recovery_item_count: int
    free_storage_slots: int
    immediate_capture_slots: int
    capabilities: CrystalCapabilityState = CrystalCapabilityState()

    def __post_init__(self) -> None:
        for name in (
            "story",
            "registered_collection",
            "living_collection",
            "level_collection",
            "evolution",
            "world_knowledge",
        ):
            if not isinstance(getattr(self, name), CompletionProgress):
                raise CrystalGoalStateError(f"{name} must be CompletionProgress")
        if not isinstance(self.party, PartyObservation):
            raise CrystalGoalStateError("party must be PartyObservation")
        if not isinstance(self.capabilities, CrystalCapabilityState):
            raise CrystalGoalStateError("capabilities must be CrystalCapabilityState")
        for name in ("game_started", "input_ready"):
            if not isinstance(getattr(self, name), bool):
                raise CrystalGoalStateError(f"{name} must be boolean")
        for name in (
            "capture_item_count",
            "recovery_item_count",
            "free_storage_slots",
            "immediate_capture_slots",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise CrystalGoalStateError(f"{name} must be a non-negative integer")
        if self.living_collection.completed > self.registered_collection.completed:
            raise CrystalGoalStateError("living collection cannot exceed registered collection")
        if self.level_collection.completed > self.living_collection.completed:
            raise CrystalGoalStateError("level-cap collection cannot exceed living collection")
        if self.immediate_capture_slots > self.party.open_slots + self.free_storage_slots:
            raise CrystalGoalStateError(
                "immediate capture slots cannot exceed party and storage headroom"
            )


class CrystalGoalStateReader(Protocol):
    """Revision-pinned reader that owns every raw address and title identity."""

    def read_goal_state(self, raw: object) -> CrystalCampaignSnapshot: ...


@dataclass(frozen=True, slots=True)
class CrystalGoalObservation:
    """Adapter result with a deliberately smaller model-facing projection."""

    snapshot: CrystalCampaignSnapshot
    evidence: GoalStateEvidence

    @property
    def situation(self) -> GoalSituation:
        return self.evidence.situation()

    def policy_dict(self) -> dict[str, object]:
        """Return exactly the identity-free state supplied to candidate scoring."""

        return self.situation.policy_dict()

    def public_dict(self) -> dict[str, object]:
        """Return auditable counts without title, species, map, path, or RAM identity."""

        snapshot = self.snapshot
        return {
            "schema": "pokemon.core.goal-state-observation.v1",
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
            "evolution": {
                "completed": self.evidence.evolution.completed,
                "target": self.evidence.evolution.target,
            },
            "world_knowledge": {
                "completed": self.evidence.world_knowledge.completed,
                "target": self.evidence.world_knowledge.target,
            },
            "party_size": snapshot.party.size,
            "game_started": snapshot.game_started,
            "input_ready": snapshot.input_ready,
            "capture_item_count": snapshot.capture_item_count,
            "recovery_item_count": snapshot.recovery_item_count,
            "free_storage_slots": snapshot.free_storage_slots,
            "immediate_capture_slots": snapshot.immediate_capture_slots,
            "situation": self.policy_dict(),
            "capability_identity_in_model_input": False,
            "private_path_fields": 0,
            "raw_address_fields": 0,
        }


@dataclass(slots=True)
class PokemonCrystalGoalStateAdapter:
    """Project a raw Crystal boundary into the shared nine-pressure ontology."""

    reader: CrystalGoalStateReader
    config: CrystalGoalManagerConfig = DEFAULT_CRYSTAL_GOAL_MANAGER_CONFIG

    def observe(self, raw: object) -> CrystalGoalObservation:
        snapshot = self.reader.read_goal_state(raw)
        if not isinstance(snapshot, CrystalCampaignSnapshot):
            raise CrystalGoalStateError("Crystal reader returned an invalid campaign snapshot")
        return project_crystal_goal_state(snapshot, config=self.config)


def project_crystal_goal_state(
    snapshot: CrystalCampaignSnapshot,
    *,
    config: CrystalGoalManagerConfig = DEFAULT_CRYSTAL_GOAL_MANAGER_CONFIG,
) -> CrystalGoalObservation:
    """Normalize semantic Crystal evidence without consulting raw memory."""

    if not isinstance(snapshot, CrystalCampaignSnapshot):
        raise TypeError("snapshot must be CrystalCampaignSnapshot")
    if not isinstance(config, CrystalGoalManagerConfig):
        raise TypeError("config must be CrystalGoalManagerConfig")
    resources = min(
        headroom_satisfaction(
            snapshot.capture_item_count,
            config.desired_capture_items,
            subject="capture item",
        ),
        headroom_satisfaction(
            snapshot.recovery_item_count,
            config.desired_recovery_items,
            subject="recovery item",
        ),
    )
    evidence = GoalStateEvidence(
        story=snapshot.story,
        registered_collection=snapshot.registered_collection,
        living_collection=snapshot.living_collection,
        level_collection=snapshot.level_collection,
        team_readiness=party_readiness_satisfaction(
            snapshot.party,
            required_size=config.required_party_size,
            required_level=config.required_team_level,
        ),
        evolution=snapshot.evolution,
        safety=party_safety_satisfaction(snapshot.party),
        resources=resources,
        storage=headroom_satisfaction(
            snapshot.immediate_capture_slots,
            config.desired_storage_headroom,
            subject="immediate capture storage",
        ),
        control=float(snapshot.game_started and snapshot.input_ready),
        world_knowledge=snapshot.world_knowledge,
    )
    return CrystalGoalObservation(snapshot=snapshot, evidence=evidence)


__all__ = [
    "CrystalCampaignSnapshot",
    "CrystalCapability",
    "CrystalCapabilityState",
    "CrystalGoalManagerConfig",
    "CrystalGoalObservation",
    "CrystalGoalStateError",
    "CrystalGoalStateReader",
    "DEFAULT_CRYSTAL_GOAL_MANAGER_CONFIG",
    "PokemonCrystalGoalStateAdapter",
    "project_crystal_goal_state",
]
