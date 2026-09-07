from dataclasses import replace

import pytest
from test_red_native_boxed_evolution import runtime_fixture

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    living_collection_checkpoint,
    living_completion_checkpoint,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    GoalManagerCompositionError,
    require_living_collection_transition,
)
from pokemon_red_completion.red_collection import RedCurrentBoxState, red_internal_species_id


@pytest.mark.parametrize(
    "mode", ["evolve", "release", "wrong_species", "last_precursor", "two_losses", "unverified"]
)
def test_living_completion_preserves_real_evolution_but_rejects_loss(tmp_path, mode):
    runtime, reader, _ = runtime_fixture(tmp_path)
    source, target = red_internal_species_id(77), red_internal_species_id(78)
    reader.raw = replace(
        reader.raw,
        party_species_ids=(*reader.raw.party_species_ids[:5], source),
    )
    reader.boxes = replace(
        reader.boxes,
        boxes=(
            RedCurrentBoxState(
                0,
                () if mode == "last_precursor" else (source,),
                () if mode == "last_precursor" else (30,),
            ),
            *reader.boxes.boxes[1:],
        ),
    )
    before_observation = runtime.adapter.observe()
    before = living_completion_checkpoint(before_observation)
    legacy = living_collection_checkpoint(before_observation)
    assert legacy.completion_contract_sha256 != before.completion_contract_sha256
    assert legacy.allowed_evolutions == ()
    if mode == "release":
        reader.boxes = replace(
            reader.boxes,
            boxes=(RedCurrentBoxState(0, (), ()), *reader.boxes.boxes[1:]),
        )
    else:
        reader.raw = replace(
            reader.raw,
            party_species_ids=(
                *reader.raw.party_species_ids[:5],
                red_internal_species_id(21) if mode == "wrong_species" else target,
            ),
        )
        if mode == "two_losses":
            reader.boxes = replace(
                reader.boxes,
                boxes=(RedCurrentBoxState(0, (), ()), *reader.boxes.boxes[1:]),
            )
    after = living_completion_checkpoint(runtime.adapter.observe())
    if mode == "evolve":
        require_living_collection_transition(before, after, selected_kind=GoalKind.EVOLVE_SPECIES)
        assert after.required_specimens_remaining == before.required_specimens_remaining - 1
        assert after.retained_captures == before.retained_captures + 1
        assert sum(n for _, n in before.specimen_counts) == sum(n for _, n in after.specimen_counts)
        # The same change must never be permitted under storage/capture authority.
        for kind in (GoalKind.MANAGE_STORAGE, GoalKind.ACQUIRE_SPECIES):
            with pytest.raises(GoalManagerCompositionError, match="regressed"):
                require_living_collection_transition(before, after, selected_kind=kind)
    else:
        with pytest.raises(GoalManagerCompositionError, match="regressed"):
            require_living_collection_transition(
                before,
                after,
                selected_kind=GoalKind.EVOLVE_SPECIES,
                require_selected_goal_progress=mode != "unverified",
            )


def test_duplicate_capture_is_preparation_not_a_new_living_species(tmp_path):
    runtime, reader, _ = runtime_fixture(tmp_path, count=1)
    before = living_completion_checkpoint(runtime.adapter.observe())
    source = red_internal_species_id(77)
    reader.boxes = replace(
        reader.boxes,
        boxes=(RedCurrentBoxState(0, (source, source), (32, 30)), *reader.boxes.boxes[1:]),
    )
    after = living_completion_checkpoint(runtime.adapter.observe())
    require_living_collection_transition(before, after, selected_kind=GoalKind.ACQUIRE_SPECIES)
    assert after.living_species == before.living_species
    assert after.required_specimens_remaining == before.required_specimens_remaining
    assert after.specimen_ledger_sha256 != before.specimen_ledger_sha256
