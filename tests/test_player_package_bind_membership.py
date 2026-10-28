"""ROM-free containment parity and real package-boundary regressions."""
import hashlib
import json
import os
from pathlib import Path, PosixPath, PurePosixPath, PureWindowsPath

import pytest

from pokemon_red_completion import red_player_package as package_module
from test_verified_data_cache_release import package as make_package


@pytest.mark.skipif(os.name != "posix", reason="concrete POSIX fast path")
@pytest.mark.parametrize("name,root", [
    ("/a/b", "/a"), ("/a", "/a"), ("/ab", "/a"), ("/A/b", "/a"),
    ("/a/b", "/"), ("/", "/"), ("//a/b", "/a"), ("/a/b", "//a"),
    ("//a/b", "//a"), ("//a", "//"), ("/a/../b", "/a"),
    ("/a/b", "/a/.."), ("/a/../b", "/a/.."), ("/a/./b", "/a"),
    ("a/b", "/a"), ("a/b", "a"), ("a/b", "."), ("a/b", ""),
    ("../a", ".."), ("/a", "."), (".", "."), ("", ""),
])
def test_bind_membership_preserves_posix_lexical_semantics(name, root):
    path, base = PosixPath(name), PosixPath(root)
    assert package_module._bind_path_is_relative_to(path, base) == path.is_relative_to(base)


@pytest.mark.parametrize("name,root", [
    ("c:/A/b", "C:/a"), ("C:/ab", "c:/a"), ("D:/a", "C:/"),
    ("C:a/b", "C:a"), ("C:a", "C:/"), ("C:/a", "C:"),
    ("//SERVER/SHARE/A/b", "//server/share/a"),
    ("//server/other/a", "//server/share"), ("/a/b", "/a"), ("a/b", "."),
])
def test_bind_membership_keeps_windows_case_drive_and_unc_rules(name, root):
    path, base = PureWindowsPath(name), PureWindowsPath(root)
    assert package_module._bind_path_is_relative_to(path, base) == path.is_relative_to(base)


@pytest.mark.parametrize("path,root", [
    (PurePosixPath("/a/b"), PurePosixPath("/a")),
    (PurePosixPath("/a/b"), PureWindowsPath("/a")),
    (PureWindowsPath("C:/a/b"), PurePosixPath("C:/a")),
    (PureWindowsPath("c:/A/b"), "C:/a"),
])
def test_bind_membership_keeps_pure_mixed_flavour_and_string_root_fallback(path, root):
    assert package_module._bind_path_is_relative_to(path, root) == path.is_relative_to(root)


def test_bind_membership_preserves_subclass_override():
    seen = []

    class CustomPath(type(Path())):
        def is_relative_to(self, root):
            seen.append(root)
            return False

    path, base = CustomPath("/a/b"), Path("/a")
    assert package_module._bind_path_is_relative_to(path, base) is False
    assert seen == [base]


@pytest.mark.skipif(os.name != "nt", reason="concrete Windows path available only on Windows")
def test_bind_membership_concrete_windows_fallback():
    path, base = Path("c:/A/b"), Path("C:/a")
    assert package_module._bind_path_is_relative_to(path, base) == path.is_relative_to(base)


def rewrite_manifest(path, document):
    path.write_text(json.dumps(document))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_data_partition_does_not_release_a_similarly_named_directory(tmp_path, monkeypatch):
    manifest, _, _ = make_package(tmp_path)
    neighbor = manifest.parent / "data-neighbor/evidence.json"
    neighbor.parent.mkdir()
    neighbor.write_bytes(b"ordinary pinned dependency")
    document = json.loads(manifest.read_text())
    document["pins"][str(neighbor)] = hashlib.sha256(neighbor.read_bytes()).hexdigest()
    identity = rewrite_manifest(manifest, document)
    released = []
    monkeypatch.setattr(package_module.os, "posix_fadvise", lambda fd, *_:
                        released.append(package_module.os.fstat(fd).st_ino))
    bound = package_module.bind_player_package(manifest, identity)
    data = manifest.parent / "data/weights.json"
    assert released == [data.stat().st_ino]
    assert bound["_verified_data_cache_release"]["data_files"] == 1
    assert bound["_verified_data_cache_release"]["checked_bytes"] == data.stat().st_size
    assert bound["_verified_data_cache_release"]["every_pin_authenticated"]


@pytest.mark.parametrize("escape", ["sibling_prefix", "dotdot", "parent_symlink"])
def test_canonical_package_containment_still_rejects_escapes_before_cache_advice(
    tmp_path, monkeypatch, escape
):
    manifest, _, _ = make_package(tmp_path)
    root = manifest.parent
    outside = tmp_path / "package-neighbor"
    outside.mkdir()
    target = outside / "payload.json"
    target.write_bytes(b"outside the frozen package")
    if escape == "sibling_prefix":
        declared = target
    elif escape == "dotdot":
        declared = root / "data/../../package-neighbor/payload.json"
    else:
        link = root / "data/linked-parent"
        link.symlink_to(outside, target_is_directory=True)
        declared = link / target.name
    document = json.loads(manifest.read_text())
    document["pins"][str(declared)] = hashlib.sha256(target.read_bytes()).hexdigest()
    identity = rewrite_manifest(manifest, document)
    releases = []
    monkeypatch.setattr(package_module.os, "posix_fadvise", lambda *a: releases.append(a))
    with pytest.raises(ValueError, match="escaped"):
        package_module.bind_player_package(manifest, identity)
    assert not releases
