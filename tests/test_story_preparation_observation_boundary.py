"""Keep the actual composite battle order without relaxing ambiguous-batch guards."""
import pytest
import test_red_player_battle_history as fixtures
from test_retained_story_preparation import story
from test_story_preparation_composite_victories import won
from pokemon_red_completion.red_player_preparation_history import StoryPreparationHistory,connect_story_preparation_observation

def test_observed_composite_wins_then_loss_keep_only_actual_latest_loss(tmp_path,monkeypatch):
    holder={"scoped_actors":{}}
    memory=StoryPreparationHistory()
    holder["observe_history"]=lambda *args,**kw: "observed"
    connect_story_preparation_observation(holder,memory)
    for name in ["first","second","lost"]:
        p=tmp_path/name;p.mkdir();b,h=story(p);holder["scoped_actors"][name]=(b,h)
        if name!="lost":
            # Replace the fixture's first loss before it is observed.
            import shutil
            shutil.rmtree(b.output/"battle-0001");b.calls=0
            won(b,monkeypatch)
        assert holder["observe_history"](checkpoint_error_type=None)=="observed"
    assert memory.retained.directory==b.output/"battle-0001"
    old=memory.private_dict();holder["observe_history"]();assert memory.private_dict()==old

def test_unordered_batch_still_rejected_without_partial_commit(tmp_path):
    holder={"scoped_actors":{},"observe_history":lambda:None};memory=StoryPreparationHistory()
    connect_story_preparation_observation(holder,memory)
    for name in ["a","b"]:
        p=tmp_path/name;p.mkdir();holder["scoped_actors"][name]=story(p)
    with pytest.raises(ValueError,match="ambiguous story preparation history order"):holder["observe_history"]()
    assert memory.private_dict()is None and memory._seen=={}

def test_failed_native_reader_cannot_advance_preparation(tmp_path):
    def fail():raise FileNotFoundError("incomplete battle")
    holder={"scoped_actors":{},"observe_history":fail};memory=StoryPreparationHistory();connect_story_preparation_observation(holder,memory)
    with pytest.raises(FileNotFoundError):holder["observe_history"]()
    assert memory.private_dict()is None and memory._seen=={}
