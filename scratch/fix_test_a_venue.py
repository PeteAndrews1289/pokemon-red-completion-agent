from pathlib import Path
import re

content = Path("tests/test_red_team_training.py").read_text()

# I will replace the whole function using regex to be safe.
old_func = re.search(r'def test_a_venue_that_can_train_nobody_says_so_at_once\(\) -> None:.*?assert executor\.actions_executed == 0, "and should not walk a single step first"\n', content, re.DOTALL)

if old_func:
    new_func = """def test_a_venue_that_can_train_nobody_says_so_at_once() -> None:
    \"\"\"Eight flees to learn what the band already says is eight too many.\"\"\"

    memory = FakeMemory()
    memory.set_party(
        [
            (DIGLETT_SPECIES_ID, 20),
            (BLASTOISE_SPECIES_ID, ESCORT_LEVEL_CAP + 5),
            (DUX_SPECIES_ID, 22),
            (DUGTRIO_SPECIES_ID, 22),
            (SNORLAX_SPECIES_ID, 22),
            (HITMONLEE_SPECIES_ID, 22),
        ]
    )
    reader = FakeReader([state()])
    policy = BalancedTeamPolicy(
        minimum_level=55, maximum_level_spread=40, required_size=6, max_enemy_level_delta=2
    )
    executor = FakeExecutor(memory)

    with pytest.raises(RuntimeError) as failure:
        run_red_team_balancing(
            executor,  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            memory,  # type: ignore[arg-type]
            **balancing_kwargs(  # type: ignore[arg-type]
                policy=policy,
                venues=[
                    TrainingVenue(band=MANSION_BAND, map_id=TRAINING_MAP, walk_to_grass=lambda *_args: 1, heal_and_return=lambda *_args: None, is_in_center=lambda raw: raw.map_id == CENTER_MAP, move_slot=lambda _raw: 1),
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
                ]
            )
        )

    message = str(failure.value)
    assert "No party member can train here" in message
    assert "28-34" in message, "the stop should state what this venue fields"
    assert "digletts_cave" in message, "and where the party should go instead"
    assert executor.actions_executed == 0, "and should not walk a single step first"
"""
    content = content[:old_func.start()] + new_func + content[old_func.end():]
    Path("tests/test_red_team_training.py").write_text(content)
else:
    print("Could not find function")

