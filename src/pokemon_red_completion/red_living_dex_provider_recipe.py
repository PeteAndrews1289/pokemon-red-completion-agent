"""Translate the frozen Red curriculum into genuine provider recipe seeds.

This is the last title-specific layer before route planning.  It binds each
portable option kind to an existing Red provider, a finite authenticated
profile, a mechanics-derived transformation family, and one semantic terminal.
It does not select a root, plan or execute a route, invoke a provider, inspect
an outcome, query a teacher, or create a learner target.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedStoryGoalBindingProvider
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedMartResupplyGoalProvider,
    RedObservedGoalSkillProvider,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
    RedLevelEvolutionTarget,
    RedPartyDevelopmentTarget,
    RedProviderFamilyTarget,
    RedResupplyTarget,
    RedStorageTarget,
    RedStoryTarget,
    red_living_dex_provider_family_target,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexTransformationFamily,
    build_red_living_dex_transformation_family,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedRoutedSemanticBoundary,
)


class RedLivingDexProviderRecipeError(ValueError):
    """A scheduled family cannot bind one existing Red provider contract."""


_GOAL_KIND_BY_OPTION = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}

_MECHANIC_BY_OPTION = {
    LivingDexOptionKind.ACQUIRE: RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
    LivingDexOptionKind.EVOLVE: RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
    LivingDexOptionKind.DEVELOP: RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
    LivingDexOptionKind.MANAGE_STORAGE: RedGoalMechanic.BOX_SWITCH,
    LivingDexOptionKind.RESUPPLY: RedGoalMechanic.MART_RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: RedGoalMechanic.MIDGAME_STORY,
    LivingDexOptionKind.EXPLORE: RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
}

_PROVIDER_TYPE_BY_OPTION = {
    LivingDexOptionKind.ACQUIRE: RedAreaSurveyGoalProvider,
    LivingDexOptionKind.EVOLVE: RedObservedGoalSkillProvider,
    LivingDexOptionKind.DEVELOP: RedObservedGoalSkillProvider,
    LivingDexOptionKind.MANAGE_STORAGE: RedBoxSwitchGoalProvider,
    LivingDexOptionKind.RESUPPLY: RedMartResupplyGoalProvider,
    LivingDexOptionKind.UNLOCK_ACCESS: RedStoryGoalBindingProvider,
    LivingDexOptionKind.EXPLORE: RedEncounterDiscoveryGoalProvider,
}

_STORY_BOUNDARY_BY_OBJECTIVE = {
    "defeat_giovanni": RedRoutedSemanticBoundary(
        int(MapId.CINNABAR_POKECENTER),
        (3, 3),
        "land",
    ),
    "defeat_erika": RedRoutedSemanticBoundary(
        int(MapId.CELADON_POKECENTER),
        (3, 3),
        "land",
    ),
    "defeat_blaine": RedRoutedSemanticBoundary(
        int(MapId.CINNABAR_POKECENTER),
        (3, 3),
        "land",
    ),
    "cross_victory_road": RedRoutedSemanticBoundary(
        int(MapId.VIRIDIAN_POKECENTER),
        (3, 3),
        "land",
    ),
    "obtain_strength": RedRoutedSemanticBoundary(
        int(MapId.FUCHSIA_POKECENTER),
        (3, 3),
        "land",
    ),
}


@dataclass(frozen=True, slots=True)
class RedLivingDexProviderRecipeSeed:
    """A real profile/family/terminal join awaiting only an origin route."""

    option_kind: LivingDexOptionKind
    provider_type: type[object]
    profile: RedGoalContextProfile
    family: RedLivingDexTransformationFamily
    terminal_boundary: RedRoutedSemanticBoundary

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, LivingDexOptionKind):
            raise RedLivingDexProviderRecipeError("provider seed option kind differs")
        if self.provider_type is not _PROVIDER_TYPE_BY_OPTION.get(self.option_kind):
            raise RedLivingDexProviderRecipeError("provider seed contract differs")
        if not isinstance(self.profile, RedGoalContextProfile):
            raise TypeError("provider seed needs a Red profile")
        self.profile.__post_init__()
        if not isinstance(self.family, RedLivingDexTransformationFamily):
            raise TypeError("provider seed needs a transformation family")
        self.family.__post_init__()
        if not isinstance(self.terminal_boundary, RedRoutedSemanticBoundary):
            raise TypeError("provider seed needs a semantic terminal")
        self.terminal_boundary.__post_init__()
        goal_kind = _GOAL_KIND_BY_OPTION[self.option_kind]
        spec = tuple(item for item in self.profile.providers if item.kind is goal_kind)
        if (
            len(spec) != 1
            or spec[0].mechanic is not _MECHANIC_BY_OPTION[self.option_kind]
            or self.family.option_kind is not self.option_kind
            or self.family.goal_kind is not goal_kind
            or self.family.mechanic is not spec[0].mechanic
        ):
            raise RedLivingDexProviderRecipeError(
                "provider seed profile and family do not describe one mechanic"
            )


def build_red_living_dex_provider_recipe_seed(
    slot: LivingDexProspectiveCaptureSlot,
    option_kind: LivingDexOptionKind,
    *,
    corridor: RedLivingDexWildCorridor | None = None,
    story_boundary: RedRoutedSemanticBoundary | None = None,
) -> RedLivingDexProviderRecipeSeed:
    """Build one finite real-provider seed without touching title state."""

    target = red_living_dex_provider_family_target(slot, option_kind)
    parameters, terminal = _parameters_and_terminal(
        target,
        corridor=corridor,
        story_boundary=story_boundary,
    )
    goal_kind = _GOAL_KIND_BY_OPTION[option_kind]
    mechanic = _MECHANIC_BY_OPTION[option_kind]
    provider_rows = [
        (goal_kind, mechanic, parameters),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
    ]
    provider_rows.sort(key=lambda row: tuple(GoalKind).index(row[0]))
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=f"{slot.slot_id}-{option_kind.value}",
            providers=tuple(provider_rows),
        )
    )
    story_objective_id = (
        target.objective_id if isinstance(target, RedStoryTarget) else None
    )
    family = build_red_living_dex_transformation_family(
        option_kind=option_kind,
        profile=profile,
        story_objective_id=story_objective_id,
    )
    return RedLivingDexProviderRecipeSeed(
        option_kind=option_kind,
        provider_type=_PROVIDER_TYPE_BY_OPTION[option_kind],
        profile=profile,
        family=family,
        terminal_boundary=terminal,
    )


def red_living_dex_story_boundary(
    target: RedStoryTarget,
) -> RedRoutedSemanticBoundary:
    """Return the sole authentic setup boundary for one scheduled objective."""

    if not isinstance(target, RedStoryTarget):
        raise TypeError("story boundary needs a Red story target")
    target.__post_init__()
    boundary = _STORY_BOUNDARY_BY_OBJECTIVE.get(target.objective_id)
    if boundary is None:
        raise RedLivingDexProviderRecipeError(
            "story objective has no authentic setup boundary"
        )
    return boundary


def _parameters_and_terminal(
    target: RedProviderFamilyTarget,
    *,
    corridor: RedLivingDexWildCorridor | None,
    story_boundary: RedRoutedSemanticBoundary | None,
) -> tuple[dict[str, object], RedRoutedSemanticBoundary]:
    if isinstance(target, RedEncounterSourceTarget):
        if corridor is None or corridor.source_id != target.source_id:
            raise RedLivingDexProviderRecipeError(
                "encounter provider seed lacks its cartridge-derived corridor"
            )
        if story_boundary is not None:
            raise RedLivingDexProviderRecipeError(
                "encounter provider seed cannot carry a story boundary"
            )
        return corridor.profile_parameters(), RedRoutedSemanticBoundary(
            corridor.map_id,
            corridor.origin_at,
            "land",
        )
    if corridor is not None:
        raise RedLivingDexProviderRecipeError(
            "non-encounter provider seed cannot carry a wild corridor"
        )
    if isinstance(target, RedStoryTarget):
        if story_boundary is None:
            raise RedLivingDexProviderRecipeError(
                "story provider seed lacks its authentic objective boundary"
            )
        expected = red_living_dex_story_boundary(target)
        if story_boundary != expected:
            raise RedLivingDexProviderRecipeError(
                "story provider seed cross-binds another objective boundary"
            )
        return target.parameters(), story_boundary
    if story_boundary is not None:
        raise RedLivingDexProviderRecipeError(
            "non-story provider seed cannot carry a story boundary"
        )
    if isinstance(target, (RedLevelEvolutionTarget, RedPartyDevelopmentTarget)):
        return target.parameters(), RedRoutedSemanticBoundary(
            int(MapId.CINNABAR_POKECENTER),
            (3, 3),
            "land",
        )
    if isinstance(target, RedStorageTarget):
        parameters = target.parameters()
        return parameters, RedRoutedSemanticBoundary(
            int(MapId.CINNABAR_POKECENTER),
            (4, 13),
            "land",
        )
    if isinstance(target, RedResupplyTarget):
        parameters = target.parameters()
        return parameters, RedRoutedSemanticBoundary(
            int(MapId.CINNABAR_MART),
            (5, 2),
            "land",
        )
    raise RedLivingDexProviderRecipeError("provider family target is unsupported")


__all__ = [
    "RedLivingDexProviderRecipeError",
    "RedLivingDexProviderRecipeSeed",
    "build_red_living_dex_provider_recipe_seed",
    "red_living_dex_story_boundary",
]
