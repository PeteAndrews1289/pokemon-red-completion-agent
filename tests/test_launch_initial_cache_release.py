from hashlib import sha256
from pathlib import Path
import os
import pytest
import launch_frozen_red_player as launcher


def fixture(tmp_path,policy='posix_fadvise_dontneed_v1'):
    root=tmp_path/'frozen';(root/'data').mkdir(parents=True)
    data=root/'data/payload.bin';data.write_bytes(b'x'*(1024*1024+17)+b'last-byte')
    code=root/'source.py';code.write_bytes(b'value=1\n')
    env=tmp_path/'environment.py';env.write_bytes(b'environment=1\n')
    pins={str(p):sha256(p.read_bytes()).hexdigest()for p in [data,code]}
    mf=dict(pins=pins,environment_pins={str(env):sha256(env.read_bytes()).hexdigest()})
    if policy is not None:mf['declaration']=dict(verified_data_cache_release=policy)
    return root,mf,data,code,env


def advice(monkeypatch):
    calls=[]
    monkeypatch.setattr(launcher.os,'POSIX_FADV_DONTNEED',4,raising=False)
    def release(fd,offset,length,mode):
        calls.append((os.fstat(fd).st_size,offset,length,mode))
    monkeypatch.setattr(launcher.os,'posix_fadvise',release,raising=False)
    return calls


def test_opt_in_streams_entire_data_before_release_and_authenticates_other_pins(tmp_path,monkeypatch):
    root,mf,data,code,env=fixture(tmp_path);before={p:p.read_bytes()for p in [data,code,env]};calls=advice(monkeypatch)
    original=Path.read_bytes;seen=[]
    def read(p):
        assert p!=data,'opt-in data must not be read eagerly'
        seen.append(p);return original(p)
    monkeypatch.setattr(Path,'read_bytes',read)
    got=launcher.verify_initial_dependencies(mf,root)
    assert got['authenticated_files']==3 and got['released_data_files']==1
    assert got['streamed_data_bytes']==len(before[data]) and got['every_pin_authenticated']
    assert calls==[(len(before[data]),0,0,4)] and seen==[code,env]
    assert all(original(p)==v for p,v in before.items())


@pytest.mark.parametrize('target',['data','source','environment'])
def test_tampered_dependency_fails_and_tampered_data_is_never_released(tmp_path,monkeypatch,target):
    root,mf,data,code,env=fixture(tmp_path);calls=advice(monkeypatch)
    selected={'data':data,'source':code,'environment':env}[target]
    payload=selected.read_bytes();selected.write_bytes(payload[:-1]+b'!')
    with pytest.raises(ValueError,match='dependency changed'):
        launcher.verify_initial_dependencies(mf,root)
    if target=='data':assert calls==[]


@pytest.mark.parametrize('fault',['symlink','missing'])
def test_missing_or_symlink_data_never_reaches_release(tmp_path,monkeypatch,fault):
    root,mf,data,code,env=fixture(tmp_path);calls=advice(monkeypatch)
    content=data.read_bytes();data.unlink()
    if fault=='symlink':
        target=tmp_path/'mutable.bin';target.write_bytes(content);data.symlink_to(target)
    with pytest.raises((ValueError,FileNotFoundError)):
        launcher.verify_initial_dependencies(mf,root)
    assert not calls


def test_parent_directory_symlink_escape_rejected_before_stream(tmp_path,monkeypatch):
    root,mf,data,code,env=fixture(tmp_path);calls=advice(monkeypatch)
    outside=tmp_path/'outside';outside.mkdir();other=outside/'external.bin';other.write_bytes(b'other')
    link=root/'data/link';link.symlink_to(outside,target_is_directory=True)
    mf['pins']={str(link/'external.bin'):sha256(b'other').hexdigest()}
    with pytest.raises(ValueError,match='escaped'):
        launcher.verify_initial_dependencies(mf,root)
    assert not calls


def test_legacy_package_retains_eager_verification_and_no_advice(tmp_path,monkeypatch):
    root,mf,data,code,env=fixture(tmp_path,None);calls=advice(monkeypatch)
    original=Path.read_bytes;seen=[]
    def read(p):seen.append(p);return original(p)
    monkeypatch.setattr(Path,'read_bytes',read)
    got=launcher.verify_initial_dependencies(mf,root)
    assert seen==[data,code,env] and not calls and got['policy']is None
    assert got['authenticated_files']==3 and got['released_data_files']==got['streamed_data_bytes']==0


@pytest.mark.parametrize('fault',['unknown','unavailable','advice_error'])
def test_opt_in_failures_are_explicit_and_never_fall_back(tmp_path,monkeypatch,fault):
    root,mf,data,code,env=fixture(tmp_path);advice(monkeypatch)
    if fault=='unknown':mf['declaration']['verified_data_cache_release']='unverified-fast-mode'
    elif fault=='unavailable':monkeypatch.delattr(launcher.os,'posix_fadvise')
    else:
        def broken(*a):raise OSError('injected advice failure')
        monkeypatch.setattr(launcher.os,'posix_fadvise',broken)
    with pytest.raises(ValueError,match='unknown|unavailable|failed'):
        launcher.verify_initial_dependencies(mf,root)
