"""Collection locations must not vanish at the name-to-cartridge adapter boundary."""

import pytest

from pokemon_red_completion.red_living_dex_multifamily_curriculum import map_id_for_wild_source
from pokemon_red_completion.red_regional_acquisition import cartridge_grass_sources

# Independently recorded map IDs from pret/pokered constants/map_constants.asm.
# Values are not generated from the enum under test.
MISSING_LAND_MAPS = (
    ("Route17", 0x1C), ("Route18", 0x1D), ("PowerPlant", 0x53),
    ("SeafoamIslandsB1F", 0x9F), ("SeafoamIslandsB2F", 0xA0),
    ("SeafoamIslandsB3F", 0xA1), ("SeafoamIslandsB4F", 0xA2),
    ("SeafoamIslands1F", 0xC0), ("CeruleanCave2F", 0xE2),
    ("CeruleanCaveB1F", 0xE3), ("CeruleanCave1F", 0xE4),
)


@pytest.mark.parametrize("name,number", MISSING_LAND_MAPS)
def test_wild_collection_name_resolves_to_cartridge_id(name, number):
    assert int(map_id_for_wild_source(f"wild:{name}:grass")) == number


def test_cartridge_inventory_does_not_drop_later_collection_maps(monkeypatch):
    import pokemon_red_completion.gen1_cartridge as cartridge

    # An occupied slot is enough for enumeration; fixture IDs do not use MapId.
    tables = {number: (object(),) for _, number in MISSING_LAND_MAPS}
    tables.update({0x0C: (object(),), 0xD9: (object(),), 0x0D: ()})
    def tables_for(rom, *, medium):
        assert rom == b"map-coverage-fixture" and medium == "grass"
        return tables
    monkeypatch.setattr(cartridge, "wild_tables", tables_for)
    assert set(cartridge_grass_sources(b"map-coverage-fixture")) == {
        f"wild:{name}:grass" for name, _ in MISSING_LAND_MAPS
    } | {"wild:Route1:grass"}


def test_every_declared_ordinary_grass_source_has_a_named_map():
    from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind

    sources = {m.source_id for m in RED_ACQUISITION_CATALOG.methods
               if m.kind is RedAcquisitionKind.WILD and m.source_id.endswith(":grass")}
    assert len(sources) > 20
    for source in sources:
        map_id_for_wild_source(source)
