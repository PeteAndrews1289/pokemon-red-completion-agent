"""ROM-free victory custody regressions derived from the bounded Claude review."""
import json, shutil
import pytest
import test_red_player_battle_history as fixtures
from test_story_preparation_atomic_refresh import actor
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_player_preparation_history import StoryPreparationHistory
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog


def won_publish(b, monkeypatch, **kw):
    original = fixtures.episode
    def episode():
        ep = original(); ep.update(battle_won=True, stop_reason="battle_won")
        row = ep["decisions"][0]; row["state_after"]["party_hp"] = [90]
        row["observation"]["features"]["battle"].update(opponent_party_count=1, opponent_remaining_count=1)
        row["outcome"]["opponent_fainted"] = True; ep["metrics"]["opponent_faints"] = 1
        return ep
    with monkeypatch.context() as p:
        p.setattr(fixtures, "episode", episode)
        d = fixtures.publish(b, **kw)
    e = json.loads((d / "endpoint.json").read_bytes()); e["actor_returned_win"] = True
    (d / "endpoint.json").write_text(json.dumps(e))
    ident = json.loads((d / "events/event-00001.json").read_bytes())["payload"]["identity"]
    shutil.rmtree(d / "events"); TrainerPracticeEventLog(d / "events", run_identity=ident).finish(e)
    return d


def test_wild_win_by_story_actor_cannot_clear_its_defeat(tmp_path, monkeypatch):
    b, h = actor(tmp_path / "s"); fixtures.publish(b)
    m = StoryPreparationHistory(); holder = dict(scoped_actors={"s": (b, h)}); m.refresh(holder)
    before, seen = m.private_dict(), dict(m._seen)
    won_publish(b, monkeypatch, wild=True)
    h()  # native validator itself accepts the wild win for this TRAIN story actor
    assert h.outcomes[-1].result.value == "won"
    for _ in range(2):
        with pytest.raises(ValueError, match="registered story battle"):
            m.refresh(holder)
        assert m.private_dict() == before and m._seen == seen


def test_foreign_owner_win_refused_without_retained_record(tmp_path, monkeypatch):
    b, h = actor(tmp_path / "s"); won_publish(b, monkeypatch)
    owner, _ = actor(tmp_path / "o", root="other-root")
    m = StoryPreparationHistory()
    for _ in range(2):
        with pytest.raises(ValueError, match="lineage or partition"):
            m.refresh(dict(actor=owner, scoped_actors={"s": (b, h)}))
        assert m._seen == {}


