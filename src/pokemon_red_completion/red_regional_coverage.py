"""Direct new registrations that different grass surveys could cover on this cartridge."""
from .gen1_cartridge import wild_tables
from .red_collection import red_internal_species_number, red_species_ref


def missing_grass_targets(rom, missing):
    """Encounter-table membership is separate from live route, stock and capture checks."""
    return {
        map_id: frozenset(red_species_ref(red_internal_species_number(species)) for _, species in slots) & missing
        for map_id, slots in wild_tables(rom, medium="grass").items()
    }


def diversify_regional_sources(ranked, missing_by_map, eligible_maps):
    """Keep the closest useful grass survey and examine one complementary survey early."""
    useful = [(index, row, missing_by_map.get(row[1], frozenset())) for index, row in enumerate(ranked)
              if row[1] in eligible_maps and missing_by_map.get(row[1])]
    if len(useful) < 2:
        return ranked, None
    first, first_row, covered = useful[0]
    index, alternate, species = max(useful[1:], key=lambda row: (len(row[2] - covered), -row[0]))
    marginal = species - covered
    if not marginal:
        return ranked, None
    original = tuple(ranked)
    kept = list(original)
    kept.insert(first+1, kept.pop(index))
    return tuple(kept), dict(nearest_source=first_row[0], alternate_source=alternate[0],
        original_rank=index+1, comparison_rank=first+2, distinct_at_nearest=len(covered),
        distinct_at_alternate=len(species), additional_species=sorted(marginal))
