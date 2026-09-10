"""The corridor consumes an authenticated encounter mask, never relaxes walk edges."""

from dataclasses import replace

import pytest
from test_red_living_dex_wild_corridor import _graph, _terrain

from pokemon_red_completion import gen1_cartridge
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridorError,
    derive_red_living_dex_wild_corridor,
)


@pytest.mark.parametrize("one_way,blocked,allowed", [
    (False, (), True), (True, (), False), (False, ((3, 1), (3, 4)), False),
])
def test_indoor_mask_requires_reversible_unblocked_plain_edges(
    monkeypatch, one_way, blocked, allowed,
):
    from pokemon_red_completion import gen1_indoor_encounters
    original = _terrain()
    terrain = replace(original, map_id=int(MapId.MT_MOON_1F), tileset=17,
                      grass=tuple(tuple(False for _ in row) for row in original.grass))
    monkeypatch.setattr(gen1_cartridge, "wild_tables", lambda rom, *, medium: {
        terrain.map_id: [(8, 1)],
    })
    observed = []

    def mask(rom, actual):
        assert rom == b"fixture" and actual is terrain
        observed.append(actual)
        return original.grass

    monkeypatch.setattr(gen1_indoor_encounters, "indoor_land_encounter_mask", mask)
    target = RedEncounterSourceTarget("wild:MtMoon1F:grass")
    if allowed:
        corridor = derive_red_living_dex_wild_corridor(
            target, terrain, _graph(), cartridge=b"fixture", excluded=blocked,
        )
        assert corridor.origin_at in {(3, 1), (3, 4)}
    else:
        with pytest.raises(RedLivingDexWildCorridorError, match="reversible"):
            derive_red_living_dex_wild_corridor(
                target, terrain, _graph(one_way=one_way), cartridge=b"fixture", excluded=blocked,
            )
    assert observed == [terrain]
    assert not any(any(row) for row in terrain.grass)
    # The new projection never modifies old no-cartridge behavior.
    with pytest.raises(RedLivingDexWildCorridorError):
        derive_red_living_dex_wild_corridor(target, terrain, _graph())
