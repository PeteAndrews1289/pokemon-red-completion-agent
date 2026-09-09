from types import SimpleNamespace

import pytest
import run_paired_red_bounded_player as runner

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.referee import CHAMPION_DEFEATED_FACT
from pokemon_red_completion.route import HALL_OF_FAME_FACT


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "profile",
        "champion",
        "hall_fact",
        "mode",
        "map",
        "scene_map",
        "stage2",
        "held",
        "battle",
        "input",
    ],
)
def test_terminal_scene_exception_is_explicit_concurrent_and_action_free(fault):
    facts = {CHAMPION_DEFEATED_FACT, HALL_OF_FAME_FACT}
    if fault == "champion":
        facts.remove(CHAMPION_DEFEATED_FACT)
    if fault == "hall_fact":
        facts.remove(HALL_OF_FAME_FACT)
    count = [0]

    def observe():
        count[0] += int(fault == "input")
        return SimpleNamespace(
            input_ready=False,
            raw=SimpleNamespace(
                map_id=120 if fault == "map" else 118, battle_state=2 if fault == "battle" else 0
            ),
            game_state=GameState(
                GameMode.OVERWORLD if fault == "mode" else GameMode.HALL_OF_FAME,
                frozenset(facts),
                "final",
            ),
        )

    runtime = SimpleNamespace(
        adapter=SimpleNamespace(observe=observe),
        profile=SimpleNamespace(
            providers=(
                SimpleNamespace(
                    parameters={
                        "trainer_objective": "defeat_lance"
                        if fault == "profile"
                        else "defeat_champion"
                    }
                ),
            )
        ),
        emulator=SimpleNamespace(
            pressed_buttons=frozenset({"a"}) if fault == "held" else frozenset()
        ),
        reader=SimpleNamespace(
            read_final_league_scene=lambda: SimpleNamespace(
                map_id=120 if fault == "scene_map" else 118,
                script_stage=2 if fault == "stage2" else 1,
            )
        ),
    )
    meter = SimpleNamespace(checkpoint=lambda: count[0])
    if fault is None:
        runner._require_safe_checkpoint_boundary(runtime, meter)
    else:
        with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="unsafe_boundary"):
            runner._require_safe_checkpoint_boundary(runtime, meter)
