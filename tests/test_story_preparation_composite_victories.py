"""ROM-free authenticated fixture histories at a composite-skill boundary."""
import json
import shutil
import pytest
import test_red_player_battle_history as fixtures
from test_retained_story_preparation import story
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_player_preparation_history import StoryPreparationHistory
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog


def won(b, monkeypatch):
    original = fixtures.episode
    def episode():
        ep = original()
        ep.update(battle_won=True, stop_reason="battle_won")
        row = ep["decisions"][0]
        row["state_after"]["party_hp"] = [90]
        row["observation"]["features"]["battle"].update(
            opponent_party_count=1, opponent_remaining_count=1)
        row["outcome"]["opponent_fainted"] = True
        ep["metrics"]["opponent_faints"] = 1
        return ep
    with monkeypatch.context() as patch:
        patch.setattr(fixtures, "episode", episode)
        directory = fixtures.publish(b)
    endpoint = json.loads((directory / "endpoint.json").read_bytes())
    endpoint["actor_returned_win"] = True
    (directory / "endpoint.json").write_text(json.dumps(endpoint))
    identity = json.loads((directory / "events/event-00001.json").read_bytes())["payload"]["identity"]
    shutil.rmtree(directory / "events")
    TrainerPracticeEventLog(directory / "events", run_identity=identity).finish(endpoint)
    return directory


@pytest.mark.parametrize("count", [2, 5])
@pytest.mark.parametrize("reverse", [False, True])
def test_composite_victories_clear_only_their_contracts(tmp_path, monkeypatch, count, reverse):
    pairs = []
    memory = StoryPreparationHistory()
    holder = {"scoped_actors": {}}
    for n in range(count + 1):
        directory = tmp_path / str(n)
        directory.mkdir()
        b = fixtures.battler(directory)
        # Borrow an existing valid contract fixture, then bind distinct actors
        # before publishing evidence (never alter an authenticated identity).
        from pokemon_red_completion.red_story_battle import StoryTrainerContract
        from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256
        from pokemon_red_completion.scenario_lab import ScenarioPartition
        b.source_partition = ScenarioPartition.TRAIN
        b.model_sha256, b.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
        b.train_story_contract = StoryTrainerContract("defeat_misty", "story-"+str(n), 65, (235,35,1),191,2079)
        h = NativeBattlerHistory(b)
        fixtures.publish(b)
        holder["scoped_actors"][str(n)] = (b,h)
        memory.refresh(holder)
        pairs.append((b,h))
    survivor = pairs[-1][0].train_story_contract
    for b,h in pairs[:-1]:
        won(b, monkeypatch)
    if reverse:
        holder["scoped_actors"] = dict(reversed(list(holder["scoped_actors"].items())))
    memory.refresh(holder)
    assert memory.retained.contract == survivor
    assert len(memory.private_dict()["defeats"]) == 1
    before = memory.private_dict()
    memory.refresh(holder)
    assert memory.private_dict() == before


def test_ambiguous_loss_is_rejected_on_every_refresh(tmp_path, monkeypatch):
    actors = {}
    for name in ["a", "b"]:
        path = tmp_path / name
        path.mkdir()
        actors[name] = story(path)
    memory = StoryPreparationHistory()
    holder = {"scoped_actors": actors}
    for _ in range(2):
        with pytest.raises(ValueError, match="ambiguous story preparation history order"):
            memory.refresh(holder)
        assert memory.private_dict() is None
        assert memory._seen == {}


def test_tampered_composite_win_is_not_acknowledged(tmp_path, monkeypatch):
    actors = {}
    memory = StoryPreparationHistory()
    holder = {"scoped_actors": actors}
    for name in ["a", "b"]:
        path = tmp_path / name
        path.mkdir()
        actors[name] = story(path)
        memory.refresh(holder)
    old_seen = dict(memory._seen)
    for b,h in actors.values():
        last = won(b, monkeypatch)
    (last / "outcome.json").write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        memory.refresh(holder)
    assert memory._seen == old_seen
