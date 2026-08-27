from __future__ import annotations

import pytest

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
    RedStoryTarget,
    red_living_dex_provider_family_target,
)
from pokemon_red_completion.red_living_dex_provider_recipe import (
    RedLivingDexProviderRecipeError,
    build_red_living_dex_provider_recipe_seed,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupProviderRecipe,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedRoutedSemanticBoundary,
)

_STORY_MAP = {
    "defeat_giovanni": MapId.CINNABAR_POKECENTER,
    "defeat_erika": MapId.CELADON_POKECENTER,
    "defeat_blaine": MapId.CINNABAR_POKECENTER,
    "cross_victory_road": MapId.VIRIDIAN_POKECENTER,
    "obtain_strength": MapId.FUCHSIA_POKECENTER,
}

_STORY_AT = {
    "defeat_giovanni": (3, 3),
    "defeat_erika": (3, 3),
    "defeat_blaine": (3, 3),
    "cross_victory_road": (3, 3),
    "obtain_strength": (3, 3),
}


def _inputs(slot: object, option_kind: LivingDexOptionKind) -> dict[str, object]:
    target = red_living_dex_provider_family_target(slot, option_kind)  # type: ignore[arg-type]
    if isinstance(target, RedEncounterSourceTarget):
        from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
            map_id_for_wild_source,
        )

        return {
            "corridor": RedLivingDexWildCorridor(
                target.source_id,
                int(map_id_for_wild_source(target.source_id)),
                (2, 1),
                (1, 1),
            )
        }
    if isinstance(target, RedStoryTarget):
        return {
            "story_boundary": RedRoutedSemanticBoundary(
                int(_STORY_MAP[target.objective_id]),
                _STORY_AT[target.objective_id],
                "land",
            )
        }
    return {}


def test_builds_all_forty_five_real_provider_seeds_and_exact_family_capacity() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    seeds = tuple(
        build_red_living_dex_provider_recipe_seed(
            slot,
            option_kind,
            **_inputs(slot, option_kind),  # type: ignore[arg-type]
        )
        for slot in plan.slots
        for option_kind in slot.available_option_kinds
    )

    assert len(seeds) == 45
    assert len({seed.family.family_sha256 for seed in seeds}) == 33
    assert all(len(seed.profile.providers) == 3 for seed in seeds)
    assert all(seed.terminal_boundary.mode == "land" for seed in seeds)
    assert {
        seed.option_kind for seed in seeds
    } == set(LivingDexOptionKind).difference({LivingDexOptionKind.TRADE})


def test_seed_is_accepted_by_the_same_root_recipe_with_an_explicit_land_mode() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    seed = build_red_living_dex_provider_recipe_seed(
        slot,
        LivingDexOptionKind.ACQUIRE,
        **_inputs(slot, LivingDexOptionKind.ACQUIRE),  # type: ignore[arg-type]
    )

    recipe = RedLivingDexSetupProviderRecipe(
        option_kind=seed.option_kind,
        provider_type=seed.provider_type,
        profile=seed.profile,
        family=seed.family,
        route=None,
    )

    assert recipe.provider_contract_id.endswith("RedAreaSurveyGoalProvider")


def test_seed_rejects_missing_or_cross_kind_terminal_inputs() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    encounter_slot = plan.slots[0]

    with pytest.raises(RedLivingDexProviderRecipeError, match="lacks its cartridge"):
        build_red_living_dex_provider_recipe_seed(
            encounter_slot,
            LivingDexOptionKind.ACQUIRE,
        )
    with pytest.raises(RedLivingDexProviderRecipeError, match="cannot carry a story"):
        build_red_living_dex_provider_recipe_seed(
            encounter_slot,
            LivingDexOptionKind.ACQUIRE,
            **_inputs(encounter_slot, LivingDexOptionKind.ACQUIRE),  # type: ignore[arg-type]
            story_boundary=RedRoutedSemanticBoundary(
                int(MapId.VIRIDIAN_POKECENTER),
                (3, 3),
                "land",
            ),
        )


def test_story_seed_rejects_a_real_boundary_for_the_wrong_objective() -> None:
    story_slot = build_red_living_dex_prospective_capture_plan().slots[2]

    with pytest.raises(RedLivingDexProviderRecipeError, match="cross-binds"):
        build_red_living_dex_provider_recipe_seed(
            story_slot,
            LivingDexOptionKind.UNLOCK_ACCESS,
            story_boundary=RedRoutedSemanticBoundary(
                int(MapId.INDIGO_PLATEAU_LOBBY),
                (5, 2),
                "land",
            ),
        )
    with pytest.raises(RedLivingDexProviderRecipeError, match="lacks its authentic"):
        build_red_living_dex_provider_recipe_seed(
            story_slot,
            LivingDexOptionKind.UNLOCK_ACCESS,
        )
