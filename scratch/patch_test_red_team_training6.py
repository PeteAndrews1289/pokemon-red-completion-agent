import re
from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

old_block = """    venue_band = overrides.pop("venue_band", GrindingArea(area_id="test_area", minimum_encounter_level=1, maximum_encounter_level=100, rare_maximum_encounter_level=100, measured_samples=100))"""
new_block = """    venue_band = overrides.pop("venue_band", GrindingArea(area_id="test_area", minimum_encounter_level=1, maximum_encounter_level=10, rare_maximum_encounter_level=10, measured_samples=100))"""

if old_block in content:
    content = content.replace(old_block, new_block)
else:
    print("WARNING: Could not find old block to replace!")

Path("tests/test_red_team_training.py").write_text(content)
