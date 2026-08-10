"""The declared version exclusives, checked against the cartridges.

Sampling encounters can show what a place offers; it can never show what it does
not. So the version-exclusive claim -- eleven species each way -- was settled by
reading the wild tables out of both ROMs, and the extraction is recorded in
``docs/evidence/wild-table-extraction-2026-08-09.json``.

This file holds the declared table against that record. It needs no ROM: the
extraction is the measurement, and this is the accounting that says the
measurement and the declaration agree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.generation_one import (
    UNAVAILABLE_IN_BLUE,
    UNAVAILABLE_IN_RED,
)

EXTRACTION = Path("docs/evidence/wild-table-extraction-2026-08-09.json")

#: Species that never appear in a wild table because you evolve into them.
#: Each inherits its pre-evolution's availability, and each pre-evolution is
#: itself confirmed by the extraction.
EVOLVED_FROM = {45: 44, 57: 56, 59: 58, 38: 37, 53: 52, 71: 70}

#: Differences the wild tables show that the declared table does not claim.
#:
#: Red's water tables hold Horsea and Seadra where Blue's hold Krabby and
#: Kingler. Neither pair is declared version-exclusive, and this extraction
#: cannot say whether that is wrong: fishing is a separate table it does not
#: read, and fishing plausibly supplies each pair in the other version. Recorded
#: so the discrepancy is visible rather than quietly dropped.
UNRESOLVED_WATER_DIFFERENCES = {98, 99, 116, 117}


@pytest.fixture(scope="module")
def extraction() -> dict[str, list[int]]:
    if not EXTRACTION.exists():  # pragma: no cover - the record is committed
        pytest.skip(f"{EXTRACTION} has not been produced")
    return json.loads(EXTRACTION.read_text(encoding="utf-8"))


def test_every_declared_exclusive_is_accounted_for(extraction: dict) -> None:
    """Each of the twenty-two is either seen in one cartridge, or an evolution."""

    red_only = set(extraction["red_wild_tables_only"])
    blue_only = set(extraction["blue_wild_tables_only"])

    for species in UNAVAILABLE_IN_BLUE:
        seen = species in red_only
        inherits = EVOLVED_FROM.get(species) in red_only
        assert seen or inherits, f"{species} is declared Red-only and neither seen nor inherited"

    for species in UNAVAILABLE_IN_RED:
        seen = species in blue_only
        inherits = EVOLVED_FROM.get(species) in blue_only
        assert seen or inherits, f"{species} is declared Blue-only and neither seen nor inherited"


def test_the_game_corner_pair_is_measured_not_assumed(extraction: dict) -> None:
    """Scyther and Pinsir are the correction this extraction exists to check.

    They were missing from an earlier table, which made every Red-only figure
    one too high. They are now read from the cartridges rather than reasoned
    about.
    """

    assert 123 in set(extraction["red_wild_tables_only"]), "Scyther in Red"
    assert 127 in set(extraction["blue_wild_tables_only"]), "Pinsir in Blue"
    assert 123 in UNAVAILABLE_IN_BLUE
    assert 127 in UNAVAILABLE_IN_RED


def test_an_evolution_is_never_expected_in_a_wild_table(extraction: dict) -> None:
    """Guards the accounting above from excusing anything it likes."""

    every_wild = set(extraction["red_wild_tables_only"]) | set(extraction["blue_wild_tables_only"])

    for evolved, precursor in EVOLVED_FROM.items():
        assert evolved not in every_wild, f"{evolved} should not appear wild"
        assert precursor in every_wild, f"{precursor} must be confirmed for {evolved} to inherit"


def test_unexplained_differences_stay_visible(extraction: dict) -> None:
    """The extraction sees water differences the declared table does not claim.

    If this set ever shrinks or grows, either fishing was parsed or the declared
    table changed, and both deserve a look rather than a silent pass.
    """

    red_only = set(extraction["red_wild_tables_only"])
    blue_only = set(extraction["blue_wild_tables_only"])
    undeclared = (red_only - UNAVAILABLE_IN_BLUE) | (blue_only - UNAVAILABLE_IN_RED)

    assert undeclared == UNRESOLVED_WATER_DIFFERENCES


def test_the_two_cartridges_field_the_same_number_of_wild_species(
    extraction: dict,
) -> None:
    """A lopsided count would mean the extraction lost a table on one side."""

    counts = extraction["wild_species_count"]
    assert counts["red"] == counts["blue"] == 78
