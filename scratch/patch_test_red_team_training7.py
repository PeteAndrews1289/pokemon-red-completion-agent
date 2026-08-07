import re
from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

old_1 = """    with pytest.raises(RuntimeError, match="where their own level lives"):
        run(memory, reader)"""
new_1 = """    with pytest.raises(RuntimeError, match="where their own level lives"):
        run(memory, reader, venues=[])"""

if old_1 in content:
    content = content.replace(old_1, new_1)
else:
    print("WARNING: Could not find old_1")

old_2 = """                **balancing_kwargs(  # type: ignore[arg-type]
                    policy=policy,
                    venue_band=MANSION_BAND,
                    measured_venues=(
                        GrindingArea(
                            area_id="digletts_cave",
                            minimum_encounter_level=15,
                            maximum_encounter_level=21,
                            rare_maximum_encounter_level=31,
                            measured_samples=29,
                        ),
                    ),
                ),"""
new_2 = """                **balancing_kwargs(  # type: ignore[arg-type]
                    policy=policy,
                    venues=[
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
                            move_slot=lambda _raw: 1,
                        ),
                    ],
                ),"""

if old_2 in content:
    content = content.replace(old_2, new_2)
else:
    print("WARNING: Could not find old_2")

Path("tests/test_red_team_training.py").write_text(content)
