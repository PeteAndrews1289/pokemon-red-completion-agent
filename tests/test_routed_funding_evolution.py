from collections import Counter
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_routed_trainer_funding as funding
from pokemon_red_completion.collection import CollectionLocation

PARTY, BOX = CollectionLocation.PARTY, CollectionLocation.BOX


def _observation(species, specimens):
    return SimpleNamespace(
        raw=SimpleNamespace(party_species_ids=tuple(species)),
        collection_observation=SimpleNamespace(
            specimens=tuple(SimpleNamespace(species_ref=r, location=loc) for r, loc in specimens)
        ),
    )


class _Guard:
    def __init__(self, result=True):
        self.result, self.calls = result, []

    def matches(self, initial, current):
        self.calls.append((initial, current))
        return self.result


@pytest.fixture(autouse=True)
def _ledger(monkeypatch):
    monkeypatch.setattr(
        funding,
        "dependency_specimen_ledger",
        lambda observation: tuple(sorted(Counter(s.species_ref for s in observation.specimens).items())),
    )


def _ledger_of(observation):
    return funding.dependency_specimen_ledger(observation.collection_observation)


START = _observation((177, 113), [("squirtle", PARTY), ("oddish", PARTY), ("rattata", BOX)])
EVOLVED = _observation((177, 114), [("squirtle", PARTY), ("gloom", PARTY), ("rattata", BOX)])


def test_unchanged_party_keeps_the_exact_original_ledger():
    ledger = _ledger_of(START)
    assert funding._funding_evolution_ledger(None, None, START, (177, 113), ledger) == ledger
    assert funding._funding_evolution_ledger(None, None, START, (177, 113), ()) is None


def test_verified_level_evolution_rebases_party_species_and_ledger():
    guard = _Guard()
    ledger = _ledger_of(START)
    result = funding._funding_evolution_ledger(guard, START, EVOLVED, (177, 113), ledger)
    assert result == _ledger_of(EVOLVED) != ledger
    assert guard.calls == [(START.raw, EVOLVED.raw)]


@pytest.mark.parametrize(
    "guard, start, won, why",
    [
        (None, START, EVOLVED, "strict funding has no evolution guard"),
        (_Guard(False), START, EVOLVED, "cartridge guard rejected the change"),
        (_Guard(), None, EVOLVED, "no battle-start observation"),
        (_Guard(), START,
         _observation((177, 114), [("squirtle", PARTY), ("gloom", PARTY), ("raticate", BOX)]),
         "a specimen outside the party changed"),
        (_Guard(), START,
         _observation((177, 114), [("squirtle", PARTY), ("gloom", PARTY), ("gloom", PARTY),
                                   ("rattata", BOX)]),
         "party census does not match the party"),
        (_Guard(), START, _observation((177,), [("squirtle", PARTY), ("rattata", BOX)]),
         "party size changed"),
        (_Guard(), _observation((177, 114), [("squirtle", PARTY), ("gloom", PARTY), ("rattata", BOX)]),
         EVOLVED, "battle start differs from the prepared party"),
    ],
)
def test_unverified_party_change_fails_closed(guard, start, won, why):
    assert funding._funding_evolution_ledger(
        guard, start, won, (177, 113), _ledger_of(START)
    ) is None, why
