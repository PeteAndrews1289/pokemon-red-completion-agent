import re
from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

# 1. Update balancing_kwargs definition to handle `venue_band` safely or drop `TrainingVenue` if None.
old_kwargs = """    kwargs: dict[str, object] = {
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
new_kwargs = """    venue_band = overrides.pop("venue_band", None)
    default_venues = [TrainingVenue(
        band=venue_band,
        map_id=overrides.pop("expected_map", TRAINING_MAP),
        walk_to_grass=overrides.pop("walk_to_grass", lambda *_args: 1),
        heal_and_return=overrides.pop("heal_and_return", lambda *_args: None),
        is_in_center=overrides.pop("is_in_center", lambda raw: raw.map_id == CENTER_MAP),
        move_slot=overrides.pop("move_slot", lambda _raw: 1),
    )] if venue_band is not None else []

    kwargs: dict[str, object] = {
        "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
        "intent": BattleIntent("team_training", "wild_training"),
        "flee_timing": object(),
        "hideout_timing": object(),
        "flee_func": lambda *_args: None,
        "report_label": "harness training",
        "checkpoint_count": 9,
        "venues": overrides.pop("venues", default_venues),
    }
"""

if old_kwargs in content:
    content = content.replace(old_kwargs, new_kwargs)

# 2. Fix test_a_venue_that_can_train_nobody_says_so_at_once
# It is still passing venue_band and measured_venues to balancing_kwargs, let's fix it.
old_test_block = """                **balancing_kwargs(  # type: ignore[arg-type]
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
new_test_block = """                **balancing_kwargs(  # type: ignore[arg-type]
                    policy=policy,
                    venues=[
                        TrainingVenue(band=MANSION_BAND, map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1),
                        TrainingVenue(band=GrindingArea(area_id="digletts_cave", minimum_encounter_level=15, maximum_encounter_level=21, rare_maximum_encounter_level=31, measured_samples=29), map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1)
                    ]
                ),"""
if old_test_block in content:
    content = content.replace(old_test_block, new_test_block)


Path("tests/test_red_team_training.py").write_text(content)
