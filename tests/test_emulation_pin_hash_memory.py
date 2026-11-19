from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from pokemon_red_completion.emulation_batch import file_digest, verify_pins


@pytest.mark.parametrize("size",[0,1,1024*1024-1,1024*1024,1024*1024+1,3*1024*1024+7])
def test_pinned_digest_is_identical_without_unbounded_reads(size):
    unit=b"native-pinned-journal"
    payload=(unit*((size+len(unit)-1)//len(unit)))[:size]
    assert len(payload)==size
    reads=[]
    class BoundedReader(BytesIO):
        def read(self,n=-1):
            assert 0 < n <= 1024*1024
            reads.append(n)
            return super().read(n)
    class Input:
        def open(self,mode):
            assert mode=="rb"
            return BoundedReader(payload)
        def read_bytes(self):
            raise AssertionError("whole-file allocation must not occur")
    assert file_digest(Input())==sha256(payload).hexdigest()
    assert reads


def test_streaming_verification_still_rejects_changed_input(tmp_path):
    source=tmp_path/"journal";source.write_bytes(b"old")
    pins={str(source):sha256(b"old").hexdigest()}
    verify_pins(pins)
    source.write_bytes(b"new")
    with pytest.raises(ValueError,match="input hash changed"):
        verify_pins(pins)
