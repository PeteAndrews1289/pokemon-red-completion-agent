from __future__ import annotations

import pytest

import pokemon_red_completion.ss_anne as ss_anne
from pokemon_red_completion.battle_runtime import BattleResourcePolicy, BattleRuntimeError
from pokemon_red_completion.observation import MapId, RawGameState


def test_ss_anne_rival_can_use_multiple_retained_potions_with_one_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quantity = 3
    calls = 0
    intents = []
    terminal = RawGameState(
        True,
        MapId.SS_ANNE_2F,
        2,
        4,
        1,
        0,
        first_party_hp=45,
        first_party_max_hp=71,
    )

    monkeypatch.setattr(ss_anne, "_bag_quantity", lambda *_args: quantity)

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        nonlocal calls
        calls += 1
        intents.append(kwargs["intent"])
        if calls <= 2:
            policy = args[2]
            try:
                policy(
                    RawGameState(
                        True,
                        MapId.SS_ANNE_2F,
                        2,
                        4,
                        1,
                        2,
                        enemy_species_id=ss_anne.IVYSAUR_SPECIES_ID,
                        enemy_hp=38,
                        first_party_hp=40,
                        first_party_max_hp=71,
                    )
                )
            except ss_anne._PauseForSSAnneRivalPotion as pause:
                raise BattleRuntimeError("paused for S.S. Anne recovery") from pause
        return terminal

    def fake_use(*_args: object) -> None:
        nonlocal quantity
        quantity -= 1

    monkeypatch.setattr(ss_anne, "run_adaptive_trainer_battle", fake_runtime)
    monkeypatch.setattr(ss_anne, "_use_cerulean_rival_potion", fake_use)

    observed = ss_anne._run_ss_anne_rival_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ss_anne.DEFAULT_SS_ANNE_TIMING,
    )

    assert observed is terminal
    assert quantity == 1
    assert calls == 3
    assert intents[0] is intents[1] is intents[2]
    assert intents[0].resource_policy is BattleResourcePolicy.BOUNDED_RECOVERY


def test_ss_anne_rival_accepts_seven_potions_when_none_are_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = RawGameState(
        True,
        MapId.SS_ANNE_2F,
        2,
        4,
        1,
        0,
        first_party_hp=71,
        first_party_max_hp=71,
    )
    monkeypatch.setattr(ss_anne, "_bag_quantity", lambda *_args: 7)
    monkeypatch.setattr(
        ss_anne,
        "run_adaptive_trainer_battle",
        lambda *_args, **_kwargs: terminal,
    )

    observed = ss_anne._run_ss_anne_rival_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ss_anne.DEFAULT_SS_ANNE_TIMING,
    )

    assert observed is terminal
