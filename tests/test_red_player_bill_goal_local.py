"""Bill quoting must not construct an unrelated Misty battle before filtering."""
from dataclasses import dataclass
from types import SimpleNamespace as NS

import pokemon_red_completion.red_player_cerulean_branches as cerulean
import pokemon_red_completion.red_player_early_story_options as early
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.player_option_challenge import OptionChallenge


@dataclass(frozen=True)
class Binding:
    name: str
    story_objective_ref: str | None = None


def gym_quote_fixture(monkeypatch):
    before = NS(raw=NS(map_id=int(MapId.CERULEAN_GYM), event_flags=bytes(512)), game_state=object())
    runtime = NS(adapter=NS(observe=lambda: before, graph=NS(
        available_objectives=lambda _: (NS(id="defeat_misty"), NS(id="help_bill")))))
    contract = NS(trainer_identity=(235, 35, 1))
    monkeypatch.setattr(early, "_legal", lambda *args: True)
    monkeypatch.setattr(cerulean, "_field_ready", lambda *args: True)
    monkeypatch.setattr(cerulean, "MISTY_REWARD", NS(contract=lambda *args: contract))
    monkeypatch.setattr(cerulean, "story_travel_binding",
        lambda *args, **kwargs: Binding("travel:" + kwargs["objective_id"]))
    return runtime, NS(rom=b"unit-quote-no-emulator")


def test_bill_only_quote_never_constructs_misty_with_train_wild_actor(monkeypatch):
    runtime, route = gym_quote_fixture(monkeypatch)
    wild = object()  # A nonstory actor must never be asked to admit Misty here.

    def unrelated_misty_quote(*args, **kwargs):
        raise AssertionError("Bill quote constructed an unrelated Misty battle")

    monkeypatch.setattr(cerulean, "story_battle_binding", unrelated_misty_quote)
    binding, challenge = early.bill_story_option(runtime, object(), route=route,
        battler=wild, combat_levels=(17, 19, 18, 7))
    assert binding.name == "travel:help_bill"
    assert binding.story_objective_ref == "help_bill"
    assert challenge == OptionChallenge(False, False, 0.0, 0.0, 0.0)


def test_cerulean_bundle_keeps_both_goals_lazy_actor_and_exact_challenges(monkeypatch):
    runtime, route = gym_quote_fixture(monkeypatch)
    misty, wild, dispatches, quote_actors = object(), object(), [], []

    def actor(objective):
        dispatches.append(objective)
        return misty if objective == "defeat_misty" else wild

    def leader_quote(*args, **kwargs):
        quote_actors.append(kwargs["battler"])
        return Binding("misty-battle")

    monkeypatch.setattr(cerulean, "story_battle_binding", leader_quote)
    monkeypatch.setattr(cerulean, "trainer_party_quote",
        lambda *args, **kwargs: NS(party=(NS(level=18), NS(level=21))))
    rows = cerulean.cerulean_story_options(runtime, object(), route=route,
        battler=wild, combat_levels=(17, 19, 18, 7), battler_for_objective=actor)
    assert [row.objective_id for row in rows] == ["defeat_misty", "help_bill"]
    assert dispatches == ["defeat_misty"] and quote_actors == [misty]
    assert rows[0].challenge == OptionChallenge.from_levels(
        combat_levels=(17, 19, 18, 7), opponent_levels=(18, 21))
    assert rows[1].challenge == OptionChallenge(False, False, 0.0, 0.0, 0.0)
