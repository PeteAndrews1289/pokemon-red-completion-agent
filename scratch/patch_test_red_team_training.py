import re
from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

# 1. Add TrainingVenue import
content = content.replace("from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea", "from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea\nfrom pokemon_red_completion.training_venue import TrainingVenue")

# 2. Update balancing_kwargs definition to accept `venues` parameter instead of the individual map/healing callbacks
# Let's find balancing_kwargs definition:
kwargs_def_start = content.find("    def balancing_kwargs(**overrides: object) -> dict[str, object]:")
kwargs_dict_start = content.find("        kwargs: dict[str, object] = {", kwargs_def_start)
kwargs_dict_end = content.find("        }", kwargs_dict_start) + 9

old_kwargs = content[kwargs_dict_start:kwargs_dict_end]
new_kwargs = """        kwargs: dict[str, object] = {
            "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
            "intent": BattleIntent("team_training", "wild_training"),
            "flee_timing": object(),
            "hideout_timing": object(),
            "flee_func": lambda *_args: None,
            "report_label": "harness training",
            "checkpoint_count": 9,
            "venues": overrides.pop("venues", [TrainingVenue(
                band=overrides.pop("venue_band", None),
                map_id=overrides.pop("expected_map", TRAINING_MAP),
                walk_to_grass=overrides.pop("walk_to_grass", lambda *_args: 1),
                heal_and_return=overrides.pop("heal_and_return", lambda *_args: None),
                is_in_center=overrides.pop("is_in_center", lambda raw: raw.map_id == CENTER_MAP),
                move_slot=overrides.pop("move_slot", lambda _raw: 1),
            )]),
        }"""
content = content.replace(old_kwargs, new_kwargs)

# 3. Update tests to use `venues` where they previously passed `measured_venues` or `venue_band`
# Let's replace usages of measured_venues in tests.
content = content.replace("measured_venues=venues", "venues=[TrainingVenue(band=venues[0], map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1)]")

content = content.replace(
    "measured_venues=(\n                        MANSION_BAND,\n                        GrindingArea(\n                            area_id=\"digletts_cave\",\n                            minimum_encounter_level=15,\n                            maximum_encounter_level=21,\n                            rare_maximum_encounter_level=31,\n                            measured_samples=29,\n                        ),\n                    )",
    'venues=[\n                        TrainingVenue(band=MANSION_BAND, map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1),\n                        TrainingVenue(band=GrindingArea(area_id="digletts_cave", minimum_encounter_level=15, maximum_encounter_level=21, rare_maximum_encounter_level=31, measured_samples=29), map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1)\n                    ]'
)

Path("tests/test_red_team_training.py").write_text(content)
