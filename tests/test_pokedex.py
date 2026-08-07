from __future__ import annotations

import pytest

from pokemon_red_completion.observation import RamAddress
from pokemon_red_completion.pokedex import (
    ExclusionReason,
    PokedexObservation,
    PokedexTarget,
    declare_target,
    registration_from_flags,
    summarize,
)
from pokemon_red_completion.red_pokedex import (
    NICKNAME_LENGTH,
    PARTY_NICKNAME_COUNT,
    PARTY_NICKNAMES_BASE,
    POKEDEX_FLAG_BYTES,
    POKEDEX_OWNED,
    POKEDEX_SEEN,
    RED_POKEDEX_TARGET,
    RED_TOTAL_SPECIES,
    PokemonRedPokedexReader,
)


class Memory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values

    def read_u8(self, address: int) -> int:
        return self.values.get(int(address), 0)


def flags_for(species: set[int]) -> list[int]:
    payload = [0] * POKEDEX_FLAG_BYTES
    for entry in species:
        payload[(entry - 1) // 8] |= 1 << ((entry - 1) % 8)
    return payload


def memory_with(owned: set[int], seen: set[int] | None = None) -> Memory:
    seen = owned if seen is None else seen
    values: dict[int, int] = {}
    for offset, byte in enumerate(flags_for(owned)):
        values[POKEDEX_OWNED + offset] = byte
    for offset, byte in enumerate(flags_for(seen)):
        values[POKEDEX_SEEN + offset] = byte
    return Memory(values)


# --- address derivation ------------------------------------------------------


def test_nickname_block_anchors_the_pokedex_addresses() -> None:
    """Both offsets derive from committed symbols, so neither can drift alone."""

    assert int(RamAddress.PARTY_MON_3_NICKNAME) - int(
        RamAddress.PARTY_MON_2_NICKNAME
    ) == NICKNAME_LENGTH
    assert int(RamAddress.PARTY_MON_2_NICKNAME) - NICKNAME_LENGTH == PARTY_NICKNAMES_BASE
    assert POKEDEX_OWNED == PARTY_NICKNAMES_BASE + PARTY_NICKNAME_COUNT * NICKNAME_LENGTH
    assert POKEDEX_SEEN == POKEDEX_OWNED + POKEDEX_FLAG_BYTES
    assert POKEDEX_FLAG_BYTES * 8 >= RED_TOTAL_SPECIES


# --- bitfield decoding -------------------------------------------------------


def test_bitfield_decoding_maps_ordinals_to_the_right_bit() -> None:
    assert registration_from_flags([0b0000_0001], 8) == frozenset({1})
    assert registration_from_flags([0b1000_0000], 8) == frozenset({8})
    assert registration_from_flags([0x00, 0b0000_0001], 16) == frozenset({9})
    assert registration_from_flags([0xFF], 8) == frozenset(range(1, 9))
    assert registration_from_flags([], 8) == frozenset()


def test_bitfield_decoding_rejects_values_that_are_not_bytes() -> None:
    with pytest.raises(ValueError, match="unsigned bytes"):
        registration_from_flags([256], 8)


# --- target declaration ------------------------------------------------------


def test_every_species_must_be_accounted_for() -> None:
    """An unstated denominator is how a percentage stops meaning anything."""

    with pytest.raises(ValueError, match="neither obtainable nor excluded"):
        PokedexTarget(total_species=10, obtainable=frozenset({1, 2, 3}))


def test_a_species_cannot_be_both_obtainable_and_excluded() -> None:
    with pytest.raises(ValueError, match="both obtainable and excluded"):
        PokedexTarget(
            total_species=3,
            obtainable=frozenset({1, 2, 3}),
            exclusions={2: ExclusionReason.REQUIRES_TRADE},
        )


def test_declare_target_derives_the_obtainable_set_from_exclusions() -> None:
    target = declare_target(5, {3: ExclusionReason.VERSION_EXCLUSIVE})
    assert target.obtainable == frozenset({1, 2, 4, 5})
    assert target.obtainable_count == 4
    assert target.excluded_for(ExclusionReason.VERSION_EXCLUSIVE) == frozenset({3})
    assert target.excluded_for(ExclusionReason.REQUIRES_TRADE) == frozenset()


# --- Red's declared target ---------------------------------------------------


def test_red_target_is_not_the_full_national_count() -> None:
    """151 is not a coherent goal for one cartridge; the real number is stated."""

    assert RED_POKEDEX_TARGET.total_species == 151
    assert RED_POKEDEX_TARGET.obtainable_count == 125
    assert len(RED_POKEDEX_TARGET.exclusions) == 26


@pytest.mark.parametrize(
    ("reason", "count"),
    (
        (ExclusionReason.VERSION_EXCLUSIVE, 10),
        (ExclusionReason.REQUIRES_TRADE, 4),
        (ExclusionReason.EVENT_DISTRIBUTION, 1),
        (ExclusionReason.MUTUALLY_EXCLUSIVE_CHOICE, 11),
    ),
)
def test_red_exclusions_are_grouped_by_stated_reason(
    reason: ExclusionReason, count: int
) -> None:
    assert len(RED_POKEDEX_TARGET.excluded_for(reason)) == count


def test_red_excludes_the_lines_a_single_cartridge_cannot_reach() -> None:
    excluded = frozenset(RED_POKEDEX_TARGET.exclusions)
    # Blue-exclusive.
    assert {27, 28, 37, 38, 52, 53, 69, 70, 71, 126} <= excluded
    # Trade evolutions.
    assert {65, 68, 76, 94} <= excluded
    # Forfeited by this route's own choices.
    assert {1, 4, 107, 134, 140} <= excluded
    # Squirtle's line, the Helix fossil, Hitmonlee and Jolteon stay reachable.
    assert {7, 8, 9, 138, 139, 106, 135} <= RED_POKEDEX_TARGET.obtainable


# --- progress ----------------------------------------------------------------


def test_progress_measures_against_the_declared_set_only() -> None:
    target = declare_target(5, {3: ExclusionReason.VERSION_EXCLUSIVE})
    progress = summarize(target, PokedexObservation(seen={1, 2, 4}, owned={1, 2}))
    assert progress.registered == frozenset({1, 2})
    assert progress.missing == frozenset({4, 5})
    assert progress.completion == pytest.approx(0.5)
    assert not progress.is_complete


def test_progress_reports_a_complete_dex_for_the_obtainable_set() -> None:
    target = declare_target(5, {3: ExclusionReason.VERSION_EXCLUSIVE})
    progress = summarize(target, PokedexObservation(seen={1, 2, 4, 5}, owned={1, 2, 4, 5}))
    assert progress.is_complete
    assert progress.completion == pytest.approx(1.0)


def test_owning_an_excluded_species_flags_the_declaration_not_the_run() -> None:
    target = declare_target(5, {3: ExclusionReason.VERSION_EXCLUSIVE})
    progress = summarize(target, PokedexObservation(seen={1, 3}, owned={1, 3}))
    assert progress.unexpected == frozenset({3})
    # The excluded species never inflates completion.
    assert progress.completion == pytest.approx(0.25)


def test_owned_must_be_a_subset_of_seen() -> None:
    with pytest.raises(ValueError, match="also have been seen"):
        PokedexObservation(seen={1}, owned={1, 2})


# --- Red reader --------------------------------------------------------------


def test_reader_projects_both_registers() -> None:
    observed = PokemonRedPokedexReader(memory_with(owned={9, 135}, seen={9, 135, 16})).read()
    assert observed.owned == frozenset({9, 135})
    assert observed.seen == frozenset({9, 16, 135})
    assert observed.owned_count == 2
    assert observed.seen_count == 3


def test_reader_reads_an_empty_dex_before_the_starter() -> None:
    observed = PokemonRedPokedexReader(Memory({})).read()
    assert observed.owned == frozenset()
    assert observed.seen == frozenset()


def test_reader_tolerates_an_owned_species_missing_from_seen() -> None:
    """A partially written save can produce this; it must not raise."""

    observed = PokemonRedPokedexReader(memory_with(owned={9}, seen=set())).read()
    assert observed.owned == frozenset({9})
    assert observed.seen == frozenset({9})


def test_reader_covers_the_whole_species_range() -> None:
    observed = PokemonRedPokedexReader(memory_with(owned={1, 151})).read()
    assert observed.owned == frozenset({1, 151})


# --- multi-run living dex ----------------------------------------------------


def test_run_choices_change_which_species_are_reachable() -> None:
    """A second run exists to take the branch the first one forfeited."""

    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    a = red_target()
    b = red_target(RedRunChoices("charmander", "dome", "hitmonchan", "flareon"))

    assert a.obtainable_count == b.obtainable_count == 125
    # Squirtle's line and the Helix fossil belong to A, not B.
    assert {7, 8, 9, 138, 139, 106, 135} <= a.obtainable
    assert not {7, 8, 9} & b.obtainable
    # Charmander's line, the Dome fossil, Hitmonchan and Flareon belong to B.
    assert {4, 5, 6, 140, 141, 107, 136} <= b.obtainable


def test_two_opposed_red_runs_still_cannot_finish_the_dex() -> None:
    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    a = red_target()
    b = red_target(RedRunChoices("charmander", "dome", "hitmonchan", "flareon"))
    union = a.obtainable | b.obtainable

    assert len(union) == 132
    # What two Red runs leave open: Blue exclusives, trade evolutions, Mew, plus
    # the third starter line and the third Eevee stone no pair of runs reaches.
    remaining = frozenset(range(1, 152)) - union
    assert {27, 37, 52, 69, 126} <= remaining  # Blue-exclusive
    assert {65, 68, 76, 94} <= remaining  # trade evolutions
    assert 151 in remaining  # Mew, deferred to a later title
    assert {1, 2, 3} <= remaining  # the untaken starter line
    assert 134 in remaining  # the untaken Eevee stone


def test_run_choices_reject_a_branch_that_does_not_exist() -> None:
    from pokemon_red_completion.red_pokedex import RedRunChoices

    with pytest.raises(ValueError, match="starter must be one of"):
        RedRunChoices(starter="pikachu")
    with pytest.raises(ValueError, match="fossil must be one of"):
        RedRunChoices(fossil="amber")


def test_living_dex_accumulates_across_runs() -> None:
    from pokemon_red_completion.pokedex import LivingDex
    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    a = red_target()
    b = red_target(RedRunChoices("charmander", "dome", "hitmonchan", "flareon"))

    living = LivingDex()
    assert living.coverage(a) == pytest.approx(0.0)

    living = living.with_run(PokedexObservation(seen=a.obtainable, owned=a.obtainable))
    assert living.coverage(a) == pytest.approx(1.0)
    assert living.remaining(a) == frozenset()
    # A run of the same game with opposite choices still adds seven species.
    assert len(living.remaining(b)) == 7


def test_coverage_planner_picks_the_run_that_adds_the_most() -> None:
    from pokemon_red_completion.pokedex import LivingDex, plan_next_run
    from pokemon_red_completion.red_pokedex import RedRunChoices, red_target

    a = red_target()
    b = red_target(RedRunChoices("charmander", "dome", "hitmonchan", "flareon"))
    living = LivingDex().with_run(PokedexObservation(seen=a.obtainable, owned=a.obtainable))

    chosen = plan_next_run(living, {"red-a": a, "red-b": b})
    assert len(chosen) > 0
    name, gain = chosen[0]
    assert name == "red-b"
    assert len(gain) == 7

    # Once nothing is left to add, the planner says so rather than picking one.
    complete = living.with_run(PokedexObservation(seen=b.obtainable, owned=b.obtainable))
    assert plan_next_run(complete, {"red-a": a, "red-b": b}) == []
