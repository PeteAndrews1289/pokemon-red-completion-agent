import re
from pathlib import Path

content = Path("src/pokemon_red_completion/blaine.py").read_text()

old_block = """def _digletts_cave_training_venue() -> TrainingVenue:
    band = next(
        a
        for a in MANSION_TRAINING_POLICY.grinding_areas
        if a.area_id == "Diglett's Cave"
    )
    return TrainingVenue("""

new_block = """def _digletts_cave_training_venue() -> TrainingVenue:
    from pokemon_red_completion.team_training import GrindingArea
    band = GrindingArea(
        area_id="Diglett's Cave",
        minimum_encounter_level=15,
        maximum_encounter_level=21,
        rare_maximum_encounter_level=31,
        measured_samples=29,
    )
    return TrainingVenue("""

if old_block in content:
    content = content.replace(old_block, new_block)
else:
    print("WARNING: Could not find old_block to replace!")

Path("src/pokemon_red_completion/blaine.py").write_text(content)
