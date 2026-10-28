import hashlib
import json

import pytest

from pokemon_red_completion import red_player_package as s


def package(tmp_path, policy="posix_fadvise_dontneed_v1"):
    root = tmp_path / "package"
    files = {root / "data/weights.json": b"unchanged model bytes",
             root / "checkout/source.py": b"value = 1\n"}
    environment = tmp_path / "environment.py"
    files[environment] = b"trusted environment"
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    pins = {str(p): hashlib.sha256(b).hexdigest() for p, b in files.items() if p != environment}
    declaration = {} if policy is None else {"verified_data_cache_release": policy}
    doc = dict(schema=s.SCHEMA, pins=pins,
        environment_pins={str(environment): hashlib.sha256(files[environment]).hexdigest()},
        roots=[], declaration=declaration)
    manifest = root / "PLAYER-PACKAGE.json"
    manifest.write_text(json.dumps(doc))
    return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), files


def test_advice_follows_complete_hash_check_and_only_targets_data(monkeypatch, tmp_path):
    manifest, digest, files = package(tmp_path)
    calls = []
    monkeypatch.setattr(s.os, "posix_fadvise", lambda fd, offset, length, advice:
        calls.append((s.os.fstat(fd).st_ino, offset, length, advice)))
    result = s.bind_player_package(manifest, digest)
    data = manifest.parent / "data/weights.json"
    assert calls == [(data.stat().st_ino, 0, 0, s.os.POSIX_FADV_DONTNEED)]
    assert result["_verified_data_cache_release"]["every_pin_authenticated"]
    assert all(p.read_bytes() == content for p, content in files.items())


@pytest.mark.parametrize("which", ["data", "source", "environment"])
def test_changed_pins_still_fail_before_advice_or_private_import(monkeypatch, tmp_path, which):
    manifest, digest, files = package(tmp_path)
    path = (manifest.parent / "data/weights.json" if which == "data" else
            manifest.parent / "checkout/source.py" if which == "source" else
            tmp_path / "environment.py")
    path.write_bytes(b"tampered")
    calls = []
    monkeypatch.setattr(s.os, "posix_fadvise", lambda *args: calls.append(args))
    with pytest.raises(ValueError):
        s.bind_player_package(manifest, digest)
    assert not calls


def test_default_packages_preserve_existing_verification_without_advice(monkeypatch, tmp_path):
    manifest, digest, _ = package(tmp_path, None)
    monkeypatch.setattr(s.os, "posix_fadvise", lambda *_: pytest.fail("policy not enabled"))
    assert "_verified_data_cache_release" not in s.bind_player_package(manifest, digest)


@pytest.mark.parametrize("fault", ["unknown", "missing_api", "advice_error"])
def test_explicit_unavailable_policy_fails_closed(monkeypatch, tmp_path, fault):
    manifest, digest, _ = package(tmp_path, "unknown" if fault == "unknown" else "posix_fadvise_dontneed_v1")
    if fault == "missing_api":
        monkeypatch.delattr(s.os, "posix_fadvise")
    elif fault == "advice_error":
        def fail(*_):
            raise OSError("unsupported")
        monkeypatch.setattr(s.os, "posix_fadvise", fail)
    with pytest.raises(ValueError, match="cache release"):
        s.bind_player_package(manifest, digest)
