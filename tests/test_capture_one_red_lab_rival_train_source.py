import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_one_red_lab_rival_train_source as source  # noqa: E402


def test_source_request_requires_clean_code_pinned_rom_and_new_output(tmp_path, monkeypatch):
    rom = tmp_path / "red.gb"
    rom.write_bytes(b"private test cartridge")
    output = tmp_path / "new-source"
    monkeypatch.setattr(source, "ROM_SHA256", hashlib.sha256(rom.read_bytes()).hexdigest())
    monkeypatch.setattr(source.subprocess, "check_output", lambda *_args, **_kwargs: b"")
    assert source._validate_request(rom, output) == rom.read_bytes()
    output.mkdir()
    with pytest.raises(ValueError, match="must be new"):
        source._validate_request(rom, output)
    output.rmdir()
    monkeypatch.setattr(source.subprocess, "check_output", lambda *_args, **_kwargs: b"dirty")
    with pytest.raises(ValueError, match="commit"):
        source._validate_request(rom, output)
    monkeypatch.setattr(source.subprocess, "check_output", lambda *_args, **_kwargs: b"")
    rom.write_bytes(b"different")
    with pytest.raises(ValueError, match="pinned Red"):
        source._validate_request(rom, output)
