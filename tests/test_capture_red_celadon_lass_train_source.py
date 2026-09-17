import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_red_celadon_lass_train_source as source  # noqa: E402


def test_request_requires_pinned_identity_bytes_clean_code_and_new_result(tmp_path, monkeypatch):
    source_id = next(iter(source.SOURCE_SHA256))
    rom = tmp_path / "red.gb"
    state = tmp_path / f"{source_id}.state"
    rom.write_bytes(b"test rom")
    state.write_bytes(b"test state")
    monkeypatch.setattr(source, "ROM_SHA256", hashlib.sha256(rom.read_bytes()).hexdigest())
    monkeypatch.setattr(
        source, "SOURCE_SHA256", {source_id: hashlib.sha256(state.read_bytes()).hexdigest()}
    )
    monkeypatch.setattr(source.subprocess, "check_output", lambda *_args, **_kwargs: b"")
    assert source._validate_request(rom, state, source_id, tmp_path)[1] == b"test state"
    with pytest.raises(ValueError, match="identity"):
        source._validate_request(rom, state, "other", tmp_path)
    (tmp_path / source_id).mkdir()
    with pytest.raises(ValueError, match="retained result"):
        source._validate_request(rom, state, source_id, tmp_path)
    (tmp_path / source_id).rmdir()
    monkeypatch.setattr(source.subprocess, "check_output", lambda *_args, **_kwargs: b"dirty")
    with pytest.raises(ValueError, match="commit"):
        source._validate_request(rom, state, source_id, tmp_path)
    monkeypatch.setattr(source.subprocess, "check_output", lambda *_args, **_kwargs: b"")
    state.write_bytes(b"different")
    with pytest.raises(ValueError, match="pinned root"):
        source._validate_request(rom, state, source_id, tmp_path)


def test_route_budget_is_finite():
    assert 0 < source.MAX_ACTIONS <= 600
    assert 0 < source.MAX_FRAMES <= 180_000
