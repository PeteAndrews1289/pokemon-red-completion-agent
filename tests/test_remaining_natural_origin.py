from types import SimpleNamespace
import pytest
from prepare_red_remaining_natural_origin import BoundaryReached, boundary


def test_existing_progress_seam_stops_before_optional_tm_detours():
    boundary(SimpleNamespace(checkpoint_id="route_4_reached"))
    with pytest.raises(BoundaryReached):
        boundary(SimpleNamespace(checkpoint_id="mt_moon_entered"))
