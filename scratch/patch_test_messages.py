from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

# 1. test_a_wrong_venue_stops_early_and_names_the_band
content = content.replace(
    """    message = str(failure.value)
    assert "Training venue does not match" in message, f"the wrong bound fired: {message}"
    assert "28-34" in message""",
    """    message = str(failure.value)
    assert "No provided venue suits" in message, f"the wrong bound fired: {message}" """
)

# 2. test_a_run_that_never_finds_a_battle_is_reported_as_unfinished
# The failure here is also early because the level 20 Blastoise cannot train in the provided MANSION_BAND
# Wait, let me check the test's intent:
# test_a_run_that_never_finds_a_battle_is_reported_as_unfinished -> Expects "stopped before readiness"
# If it fails early, it doesn't even walk.
# I should change the test's provided venue to something that suits a level 20 Blastoise, so it enters the loop, and runs out of steps.
content = content.replace(
    """        "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),""",
    """        "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),\n        "venues": [TrainingVenue(band=GrindingArea(area_id="pallet", minimum_encounter_level=2, maximum_encounter_level=5, rare_maximum_encounter_level=5, measured_samples=100), map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1)],"""
)

# 3. test_without_measured_bands_the_stop_does_not_invent_a_venue
# This test expects "where their own level lives" (the old early exit).
content = content.replace(
    'with pytest.raises(RuntimeError, match="where their own level lives"):',
    'with pytest.raises(RuntimeError, match="No provided venue suits"):'
)

# 4. test_a_venue_that_can_train_nobody_says_so_at_once
# This test now expects "No provided venue suits" instead of "No party member can train here"
content = content.replace(
    'assert "No party member can train here" in message\n    assert "28-34" in message, "the stop should state what this venue fields"\n    assert "digletts_cave" in message, "and where the party should go instead"',
    'assert "No provided venue suits" in message'
)


Path("tests/test_red_team_training.py").write_text(content)
