import re
from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

old_block = """    venue_band = overrides.pop("venue_band", None)
    default_venues = [TrainingVenue(
        band=venue_band,
        map_id=overrides.pop("expected_map", TRAINING_MAP),
        walk_to_grass=overrides.pop("walk_to_grass", lambda *_args: 1),
        heal_and_return=overrides.pop("heal_and_return", lambda *_args: None),
        is_in_center=overrides.pop("is_in_center", lambda raw: raw.map_id == CENTER_MAP),
        move_slot=overrides.pop("move_slot", lambda _raw: 1),
    )] if venue_band is not None else []"""

new_block = """    venue_band = overrides.pop("venue_band", GrindingArea("test_area", 1, 100, 100, 100))
    default_venues = [TrainingVenue(
        band=venue_band,
        map_id=overrides.pop("expected_map", TRAINING_MAP),
        walk_to_grass=overrides.pop("walk_to_grass", lambda *_args: 1),
        heal_and_return=overrides.pop("heal_and_return", lambda *_args: None),
        is_in_center=overrides.pop("is_in_center", lambda raw: raw.map_id == CENTER_MAP),
        move_slot=overrides.pop("move_slot", lambda _raw: 1),
    )]"""

if old_block in content:
    content = content.replace(old_block, new_block)
else:
    print("WARNING: Could not find old block to replace!")

Path("tests/test_red_team_training.py").write_text(content)
