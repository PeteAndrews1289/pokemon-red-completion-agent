"""The survey must inspect received stock, not assign a transformed appearance."""
from collections import Counter

import pytest
from test_red_acquisition import _RouteOneSurveySimulation

from pokemon_red_completion.red_acquisition import (
    RedAreaExecutionError,
    RedAreaExecutionPolicy,
    run_red_area_survey,
)
from pokemon_red_completion.red_collection import red_species_ref


@pytest.mark.parametrize('received', [97, 132])
def test_nonmatching_received_species_is_not_credited_to_original_target(received):
    class ChangedCapture(_RouteOneSurveySimulation):
        def capture_encounter(self, species_ref):
            super().capture_encounter(species_ref)
            _, box = self.captured[-1]
            self.captured[-1] = (received, box)
            return True

    world = ChangedCapture((16,))
    with pytest.raises(RedAreaExecutionError) as caught:
        run_red_area_survey('wild:Route1:grass', world)
    assert caught.value.reason_code == 'capture_retention_postcondition_failed'
    counts = Counter(item.species_ref for item in world.read_collection().specimens)
    assert counts[red_species_ref(16)] == 0
    assert counts[red_species_ref(received)] == 1
    assert world.current_encounter is None


def test_received_ditto_is_retained_and_credited_as_ditto_not_hypno():
    world = _RouteOneSurveySimulation((132,))
    report = run_red_area_survey(
        'wild:Route14:grass', world,
        policy=RedAreaExecutionPolicy(capture_quota=1),
    )
    assert report.captures == 1
    counts = Counter(item.species_ref for item in world.read_collection().specimens)
    assert counts[red_species_ref(132)] == 1
    assert counts[red_species_ref(97)] == 0
    assert red_species_ref(132) in world.read_collection().owned_species
