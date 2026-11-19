"""Adversarial, authenticated history batches; no emulator or model fitting."""
from types import SimpleNamespace as N
import pytest
import test_red_player_battle_history as fixtures
from test_story_preparation_composite_victories import won
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_player_preparation_history import RetainedStoryDefeat, StoryPreparationHistory
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256,K_QUALIFICATION_SHA256
from pokemon_red_completion.scenario_lab import ScenarioPartition

def actor(path, *, root='live-root', partition=ScenarioPartition.TRAIN, suffix=1):
    path.mkdir()
    b=fixtures.battler(path)
    b.root_lineage_id=root;b.source_partition=partition
    b.model_sha256,b.qualification_sha256=FROZEN_K_SHA256,K_QUALIFICATION_SHA256
    b.train_story_contract=StoryTrainerContract('defeat_misty','observed-'+str(suffix),65,(235,35,suffix),191+suffix,2079)
    return b,NativeBattlerHistory(b)

def group_for(pairs, *, intervals=None, no_call=False):
    pools={}
    for i,(b,h)in enumerate(pairs):
        before,after=intervals[i]if intervals else(2*i,2*i+1)
        entries=[dict(actor=0,calls_before=0,calls_after=1,before_frame=before,after_frame=after)]
        if no_call:entries.append(dict(actor=0,calls_before=1,calls_after=1,before_frame=after,after_frame=None))
        pools[i]=N(_histories=[h],_entries=entries)
    def observe():
        for b,h in pairs:h()
    return dict(scoped_native_train_group=N(pools=pools,history=observe))

@pytest.mark.parametrize('ordered',[False,True])
def test_failed_apply_keeps_seen_and_losses_on_every_retry(tmp_path,monkeypatch,ordered):
    b,h=actor(tmp_path/'story');fixtures.publish(b)
    m=StoryPreparationHistory(expected_lineage='foreign-root',expected_partition='train')
    holder=group_for([(b,h)])if ordered else dict(scoped_actors={'s':(b,h)})
    for _ in range(2):
        with pytest.raises(ValueError,match='lineage or partition'):m.refresh(holder)
        assert m._seen=={} and m.private_dict()is None

@pytest.mark.parametrize('foreign',['root','partition'])
def test_foreign_win_cannot_erase_a_local_defeat(tmp_path,monkeypatch,foreign):
    b,h=actor(tmp_path/'local');fixtures.publish(b)
    m=StoryPreparationHistory(expected_lineage='live-root',expected_partition='train');m.refresh(dict(scoped_actors={'s':(b,h)}))
    if foreign=='partition':m=StoryPreparationHistory(expected_lineage='live-root',expected_partition='development')
    before=m.private_dict();seen=dict(m._seen)
    fb,fh=actor(tmp_path/'foreign',root='foreign-root'if foreign=='root'else'live-root')
    won(fb,monkeypatch)
    for _ in range(2):
        with pytest.raises(ValueError,match='lineage or partition'):m.refresh(dict(scoped_actors={'s':(fb,fh)}))
        assert m.private_dict()==before and m._seen==seen

@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('unresolved',[False,True])
def test_mixed_win_and_nonwin_batch_is_always_ambiguous(tmp_path,monkeypatch,reverse,unresolved):
    a,ah=actor(tmp_path/'a',suffix=1);b,bh=actor(tmp_path/'b',suffix=2)
    won(a,monkeypatch);fixtures.publish(b,unresolved=unresolved)
    pairs={'a':(a,ah),'b':(b,bh)}
    if reverse:pairs=dict(reversed(list(pairs.items())))
    m=StoryPreparationHistory()
    for _ in range(2):
        with pytest.raises(ValueError,match='ambiguous'):m.refresh(dict(scoped_actors=pairs))
        assert m._seen=={} and m.private_dict()is None

def test_late_apply_error_cannot_partially_clear_loss(tmp_path,monkeypatch):
    b,h=actor(tmp_path/'story');fixtures.publish(b);m=StoryPreparationHistory();holder=dict(scoped_actors={'s':(b,h)});m.refresh(holder)
    before=m.private_dict();seen=dict(m._seen);won(b,monkeypatch);fixtures.publish(b)
    def unavailable(*a,**k):raise ValueError('late retained evidence failure')
    monkeypatch.setattr(RetainedStoryDefeat,'from_history',unavailable)
    for _ in range(2):
        with pytest.raises(ValueError,match='late retained evidence failure'):m.refresh(holder)
        assert m.private_dict()==before and m._seen==seen

@pytest.mark.parametrize('mismatch',[False,True])
def test_duplicate_or_mismatched_registered_histories_refuse_without_acknowledgement(tmp_path,mismatch):
    b,h=actor(tmp_path/'story');fixtures.publish(b)
    if mismatch:
        other=fixtures.battler(tmp_path/'other');pairs={'s':(other,h)}
    else:pairs={'s':(b,h),'alias':(b,h)}
    m=StoryPreparationHistory()
    for _ in range(2):
        with pytest.raises(ValueError,match='registered|duplicate'):m.refresh(dict(scoped_actors=pairs))
        assert m._seen=={} and m.private_dict()is None

@pytest.mark.parametrize('intervals',[[[0,3],[2,4]],[[0,1],[0,1]],[[0,None],[2,3]]])
def test_ordered_history_rejects_missing_or_overlapping_frames(tmp_path,intervals):
    pairs=[actor(tmp_path/str(i),suffix=i+1)for i in range(2)]
    for b,h in pairs:fixtures.publish(b)
    m=StoryPreparationHistory();holder=group_for(pairs,intervals=intervals)
    for _ in range(2):
        with pytest.raises(ValueError,match='frame|overlap'):m.refresh(holder)
        assert m._seen=={} and m.private_dict()is None

def test_ordered_zero_call_receipt_does_not_repeat_a_battle(tmp_path):
    b,h=actor(tmp_path/'story');fixtures.publish(b);m=StoryPreparationHistory();holder=group_for([(b,h)],no_call=True)
    m.refresh(holder);before=m.private_dict();m.refresh(holder)
    assert m.private_dict()==before and m._seen=={id(h):1}
