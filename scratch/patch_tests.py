from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

if "from pokemon_red_completion.training_venue import TrainingVenue" not in content:
    content = content.replace("from pokemon_red_completion.red_team_training import run_red_team_balancing", "from pokemon_red_completion.training_venue import TrainingVenue\nfrom pokemon_red_completion.red_team_training import run_red_team_balancing")

old_kwargs = """    kwargs: dict[str, object] = {
        "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
        "expected_map": TRAINING_MAP,
        "intent": BattleIntent("team_training", "wild_training"),
        "flee_timing": object(),
        "hideout_timing": object(),
        "flee_func": lambda *_args: None,
        "heal_and_return": lambda *_args: None,
        "is_in_center": lambda raw: raw.map_id == CENTER_MAP,
        "is_in_map": lambda raw: raw.map_id == TRAINING_MAP,
        "walk_to_grass": lambda *_args: 1,
        "move_slot": lambda _raw: 1,
        "report_label": "harness training",
        "checkpoint_count": 9,
    }"""

new_kwargs = """    kwargs: dict[str, object] = {
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

content = content.replace(old_kwargs, new_kwargs)

# test_the_venue_mismatch_stop_names_where_the_trainee_belongs
content = content.replace("measured_venues=venues", "venues=[TrainingVenue(band=venues[0], map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1)]")

# test_a_venue_trains_whoever_it_can_rather_than_the_weakest_outright
# and test_a_venue_that_can_train_nobody_says_so_at_once
content = content.replace("venue_band=MANSION_BAND", "")
content = content.replace("measured_venues=(", "venues=[TrainingVenue(band=MANSION_BAND, map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1), TrainingVenue(band=")
content = content.replace("),\n            ),", "), map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1)],")

Path("tests/test_red_team_training.py").write_text(content)
