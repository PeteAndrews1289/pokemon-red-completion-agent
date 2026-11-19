"""Cache hints cannot weaken or interrupt sealed native-record publication."""
import os,json
from pathlib import Path
import pytest
from pokemon_red_completion import private_artifacts as private
from test_compact_native_inputs import store_at,publish

def test_advice_follows_durable_publication_and_validation(tmp_path,monkeypatch):
    root,store,_=store_at(tmp_path,'flat');events=[];sync=private._fsync_directory;opened=private._open_flat_native_record
    def synced(path):sync(path);events.append('synced')
    def validated(*args,**kwargs):record=opened(*args,**kwargs);events.append('validated');return record
    def advised(fd,offset,length,advice):
        assert events[-1]=='validated'and'synced'in events
        assert offset==length==0 and advice==os.POSIX_FADV_DONTNEED
        assert os.fstat(fd).st_size>0
        events.append('advised')
    monkeypatch.setattr(private,'_fsync_directory',synced);monkeypatch.setattr(private,'_open_flat_native_record',validated);monkeypatch.setattr(os,'posix_fadvise',advised)
    identifier,record=publish(store);assert events[-1]=='advised'
    assert record.read()==dict(ordinal=0,before_frame=0,action='wait',value=None,repeat=1)
    assert store.find_sealed_record(identifier).summary==record.summary

def test_failed_advice_preserves_readable_record(tmp_path,monkeypatch):
    root,store,_=store_at(tmp_path,'flat')
    def fail(*args):raise OSError('unsupported hint')
    monkeypatch.setattr(os,'posix_fadvise',fail)
    identifier,record=publish(store);assert store.find_sealed_record(identifier).read_bytes()==record.read_bytes()

def test_absent_platform_advice_preserves_readable_record(tmp_path,monkeypatch):
    root,store,_=store_at(tmp_path,'flat');monkeypatch.delattr(os,'posix_fadvise')
    identifier,record=publish(store);assert store.find_sealed_record(identifier).summary==record.summary

def test_non_native_evidence_keeps_existing_representation(tmp_path,monkeypatch):
    root,store,_=store_at(tmp_path,'flat');calls=[];monkeypatch.setattr(os,'posix_fadvise',lambda *args:calls.append(args))
    record=store.publish_sealed_record('native-claim',kind='red_native_player_execution',record={'version':1})
    assert record.read()=={'version':1}and not calls and(root/'native-claim/record.json').exists()

def test_cache_hint_does_not_follow_symlink(tmp_path,monkeypatch):
    target=tmp_path/'real';target.write_bytes(b'keep');link=tmp_path/'link';link.symlink_to(target);calls=[]
    monkeypatch.setattr(os,'posix_fadvise',lambda *args:calls.append(args));private._release_flat_record_cache(link)
    assert not calls and target.read_bytes()==b'keep'

def test_failed_durability_does_not_advise(tmp_path,monkeypatch):
    root,store,_=store_at(tmp_path,'flat');calls=[]
    def fail(*args):raise OSError('fsync failure')
    monkeypatch.setattr(private,'_fsync_directory',fail);monkeypatch.setattr(os,'posix_fadvise',lambda *args:calls.append(args))
    with pytest.raises(private.PrivateArtifactError):publish(store)
    assert not calls

def test_corrupted_existing_record_still_fails_closed(tmp_path,monkeypatch):
    root,store,_=store_at(tmp_path,'flat');identifier,record=publish(store);path=root/(identifier+'.sealed.jsonl');path.write_bytes(path.read_bytes()+b'bad');calls=[]
    monkeypatch.setattr(os,'posix_fadvise',lambda *args:calls.append(args))
    with pytest.raises(private.PrivateArtifactError):publish(store)
    assert not calls
