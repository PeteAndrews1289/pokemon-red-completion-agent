from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

# We need to remove the default `band=MANSION_BAND` from balancing_kwargs, 
# and instead pass `band=None` to allow tests to run with unmeasured venues.
# Then we can explicitly pass `band=MANSION_BAND` in the tests that need it.

old_kwargs = """        kwargs: dict[str, object] = {
            "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
            "intent": BattleIntent("team_training", "wild_training"),
            "flee_timing": object(),
            "hideout_timing": object(),
            "flee_func": lambda *_args: None,
            "report_label": "harness training",
            "checkpoint_count": 9,
            "venues": [TrainingVenue(
                band=MANSION_BAND,
                map_id=TRAINING_MAP,
                walk_to_grass=lambda *_args: 1,
                heal_and_return=lambda *_args: None,
                is_in_center=lambda raw: raw.map_id == CENTER_MAP,
                move_slot=lambda _raw: 1,
            )],
        }"""

new_kwargs = """        kwargs: dict[str, object] = {
            "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
            "intent": BattleIntent("team_training", "wild_training"),
            "flee_timing": object(),
            "hideout_timing": object(),
            "flee_func": lambda *_args: None,
            "report_label": "harness training",
            "checkpoint_count": 9,
            "venues": [TrainingVenue(
                band=None,
                map_id=TRAINING_MAP,
                walk_to_grass=lambda *_args: 1,
                heal_and_return=lambda *_args: None,
                is_in_center=lambda raw: raw.map_id == CENTER_MAP,
                move_slot=lambda _raw: 1,
            )],
        }"""

content = content.replace(old_kwargs, new_kwargs)

Path("tests/test_red_team_training.py").write_text(content)
