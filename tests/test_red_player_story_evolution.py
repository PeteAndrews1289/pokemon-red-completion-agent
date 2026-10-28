from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_trainer_battle_lifecycle import fixture

from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_trainer_battle_lifecycle import (
    TrainerBattleLifecycleError,
    continue_learned_trainer_battle,
)
from pokemon_red_completion.red_trainer_evolution import RedTrainerEvolutionGuard


@pytest.mark.parametrize(
    "fault", [None, "identity", "species", "threshold", "default_scope", "no_guard"]
)
def test_story_evolution_retains_all_native_outcome_checks(fault):
    state, reader, battler, executor = fixture("won")
    from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256

    battler.model_sha256, battler.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
    initial = replace(state.raw, party_levels=(10, 10))
    state.raw = initial
    before = PartyObservation(
        tuple(
            PartyMemberObservation(i + 1, s, 10, 20, 30, experience=1000)
            for i, s in enumerate((107, 179))
        )
    )
    after = PartyObservation(
        (replace(before.members[0], species_id=108, level=11, experience=1331), before.members[1])
    )
    guard = RedTrainerEvolutionGuard(
        N(
            read=lambda: after,
            preparation_specimen_refs=lambda: (
                ("changed", "b") if fault == "identity" else ("a", "b")
            ),
        ),
        before,
        ("a", "b"),
        frozenset({(107, 109 if fault == "species" else 108, 12 if fault == "threshold" else 11)}),
    )
    original = battler.continue_battle

    def play(*a, **k):
        episode = original(*a, **k)
        state.raw = replace(
            state.raw, party_species_ids=after.species_ids(), party_levels=after.levels
        )
        return episode

    battler.continue_battle = play
    kwargs = dict(
        trainer_identity=(230, 30, 4),
        defeated_event=8,
        ordinary_victory_money=480,
        timing=BattleRuntimeTiming(),
        story_authority=fault != "default_scope",
    )
    if fault != "no_guard":
        kwargs["evolution_guard"] = guard
    if fault:
        with pytest.raises((ValueError, TrainerBattleLifecycleError)):
            continue_learned_trainer_battle(battler, reader, executor, **kwargs)
    else:
        assert continue_learned_trainer_battle(battler, reader, executor, **kwargs).outcome == "won"
