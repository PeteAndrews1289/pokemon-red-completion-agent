from pathlib import Path
import re

content = Path("tests/test_red_team_training.py").read_text()

# Remove the first duplicate 'venues' key.
# It is at line 272: "venues": [TrainingVenue(band=GrindingArea(area_id="pallet", ...
content = re.sub(
    r'        "venues": \[TrainingVenue\(band=GrindingArea\(area_id="pallet".*?\],\n',
    '',
    content,
    flags=re.DOTALL
)

# And in the second 'venues', add Diglett's Cave as a second venue.
old_venues = '''        "venues": [TrainingVenue(
            band=MANSION_BAND,
            map_id=TRAINING_MAP,
            walk_to_grass=lambda *_args: 1,
            heal_and_return=lambda *_args: None,
            is_in_center=lambda raw: raw.map_id == CENTER_MAP,
            move_slot=lambda _raw: 1,
        )],'''

new_venues = '''        "venues": [
            TrainingVenue(
                band=MANSION_BAND,
                map_id=TRAINING_MAP,
                walk_to_grass=lambda *_args: 1,
                heal_and_return=lambda *_args: None,
                is_in_center=lambda raw: raw.map_id == CENTER_MAP,
                move_slot=lambda _raw: 1,
            ),
            TrainingVenue(
                band=GrindingArea(
                    area_id="digletts_cave",
                    minimum_encounter_level=15,
                    maximum_encounter_level=21,
                    rare_maximum_encounter_level=31,
                    measured_samples=29,
                ),
                map_id=TRAINING_MAP,
                walk_to_grass=lambda *_args: 1,
                heal_and_return=lambda *_args: None,
                is_in_center=lambda raw: raw.map_id == CENTER_MAP,
                move_slot=lambda _raw: 1
            )
        ],'''

content = content.replace(old_venues, new_venues)

Path("tests/test_red_team_training.py").write_text(content)
