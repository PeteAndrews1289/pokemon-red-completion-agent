from dataclasses import dataclass

import pytest

from pokemon_red_completion.fishing import (
    FishingCastOutcome,
    FishingCastResult,
)
from pokemon_red_completion.gen1_cartridge import FishingSlot, RodKind
from pokemon_red_completion.red_fishing_acquisition import RedFishingDestinationOffer
from pokemon_red_completion.red_fishing_capture import (
    RedFishingCaptureError,
    run_red_fishing_capture,
)


def _result(
    outcome: FishingCastOutcome, rod: RodKind = RodKind.SUPER
) -> FishingCastResult:
    return FishingCastResult(outcome, rod, 2, 180)


def _offer() -> RedFishingDestinationOffer:
    return RedFishingDestinationOffer(
        "fishing-map-private-23",
        23,
        (
            FishingSlot(15, 72, RodKind.SUPER),
            FishingSlot(15, 98, RodKind.SUPER),
            FishingSlot(15, 129, RodKind.SUPER),
        ),
        (72, 98),
    )


@dataclass
class _Port:
    registered: frozenset[int]
    outcomes: list[tuple[FishingCastOutcome, int | None]]
    capture_succeeds: bool = True
    dishonest_capture: bool = False
    registration_drift: bool = False
    active: int | None = None
    map_id: int = 23
    rod: RodKind = RodKind.SUPER

    def registered_species_numbers(self) -> frozenset[int]:
        return self.registered

    def current_map_id(self) -> int:
        return self.map_id

    def cast(self) -> FishingCastResult:
        outcome, self.active = self.outcomes.pop(0)
        if self.registration_drift:
            self.registered |= {150}
        return _result(outcome, self.rod)

    def encountered_species_number(self) -> int | None:
        return self.active

    def capture_encounter(self, species_number: int) -> bool:
        self.active = None
        if self.capture_succeeds and not self.dishonest_capture:
            self.registered |= {species_number}
        return self.capture_succeeds

    def flee_encounter(self) -> None:
        self.active = None


def test_fishing_capture_skips_no_bite_and_registered_encounter_then_catches():
    port = _Port(
        frozenset({129}),
        [
            (FishingCastOutcome.NO_BITE, None),
            (FishingCastOutcome.WILD_ENCOUNTER, 129),
            (FishingCastOutcome.WILD_ENCOUNTER, 72),
        ],
    )

    report = run_red_fishing_capture(_offer(), port, maximum_casts=5)

    assert report.passed
    assert (report.casts, report.encounters, report.no_bites) == (3, 2, 1)
    assert (report.captures, report.flees, report.new_registrations) == (1, 1, 1)
    assert port.registered == frozenset({72, 129})
    assert "72" not in str(report.public_dict())


def test_fishing_capture_returns_honest_bounded_exhaustion():
    port = _Port(
        frozenset({129}),
        [
            (FishingCastOutcome.NO_BITE, None),
            (FishingCastOutcome.WILD_ENCOUNTER, 98),
        ],
        capture_succeeds=False,
    )

    report = run_red_fishing_capture(_offer(), port, maximum_casts=2)

    assert not report.passed
    assert report.search_exhausted
    assert report.failed_captures == 1
    assert report.new_registrations == 0


def test_fishing_capture_rejects_stale_offer_and_existing_battle():
    with pytest.raises(RedFishingCaptureError, match="stale"):
        run_red_fishing_capture(
            _offer(),
            _Port(frozenset({72, 129}), []),
            maximum_casts=1,
        )
    with pytest.raises(RedFishingCaptureError, match="outside battle"):
        run_red_fishing_capture(
            _offer(),
            _Port(frozenset({129}), [], active=72),
            maximum_casts=1,
        )


def test_fishing_capture_rejects_wrong_selected_map():
    with pytest.raises(RedFishingCaptureError, match="selected map"):
        run_red_fishing_capture(
            _offer(),
            _Port(frozenset({129}), [], map_id=24),
            maximum_casts=1,
        )
@pytest.mark.parametrize(
    ("port", "message"),
    [
        (
            _Port(
                frozenset({129}),
                [(FishingCastOutcome.WILD_ENCOUNTER, 118)],
            ),
            "cartridge slots",
        ),
        (
            _Port(
                frozenset({129}),
                [(FishingCastOutcome.WILD_ENCOUNTER, 72)],
                dishonest_capture=True,
            ),
            "exactly its registration",
        ),
        (
            _Port(
                frozenset({129}),
                [(FishingCastOutcome.NO_BITE, None)],
                registration_drift=True,
            ),
            "no-bite",
        ),
        (
            _Port(
                frozenset({129}),
                [(FishingCastOutcome.NO_BITE, None)],
                rod=RodKind.OLD,
            ),
            "another rod",
        ),
    ],
)
def test_fishing_capture_fails_closed_on_semantic_mismatch(port, message):
    with pytest.raises(RedFishingCaptureError, match=message):
        run_red_fishing_capture(_offer(), port, maximum_casts=1)


def test_fishing_capture_validates_bounds():
    with pytest.raises(ValueError, match="positive"):
        run_red_fishing_capture(
            _offer(),
            _Port(frozenset({129}), []),
            maximum_casts=0,
        )
