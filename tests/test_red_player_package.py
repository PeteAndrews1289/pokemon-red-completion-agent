import ast
import importlib.machinery
import json
import os
import py_compile
import sys
from hashlib import sha256

import pytest

from pokemon_red_completion.red_player_package import (
    bind_player_package,
    freeze_player_package,
    make_package_read_guard,
    relocate_helper,
    resolve_packaged_history_path,
)


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def test_literal_relocation_preserves_python_logic_and_unrelated_strings(tmp_path):
    before = (b"from pathlib import Path\nROOT=Path('/source/data')\nLABEL='not /source/data'\n"
              b"def f():\n return ROOT/'model.json'\n")
    after = relocate_helper(before, (("/source", "/frozen"),))
    assert b"/frozen/data" in after and b"not /source/data" in after
    original, frozen = ast.parse(before), ast.parse(after)
    for node in ast.walk(frozen):
        if isinstance(node, ast.Constant) and node.value == "/frozen/data":
            node.value = "/source/data"
    assert ast.dump(original) == ast.dump(frozen)


def test_unicode_before_literal_and_multiline_offsets_are_exact():
    before = "label='é'; root='/source/a'\nother=\"\"\"/source/b\"\"\"\n".encode()
    after = relocate_helper(before, (("/source", "/frozen"),))
    result = ast.parse(after)
    assert result.body[1].value.value == "/frozen/a"
    assert result.body[2].value.value == "/frozen/b"


@pytest.fixture
def package(tmp_path):
    repo, helpers, data = (tmp_path / x for x in ("repo", "helpers", "data"))
    (repo / "src/pokemon_red_completion").mkdir(parents=True)
    (repo / "scripts").mkdir()
    helpers.mkdir()
    data.mkdir()
    source = repo / "src/pokemon_red_completion/unit.py"
    source.write_text("value=1\n")
    (repo / "scripts/worker.py").write_text("pass\n")
    helper, evidence = helpers / "backend.py", data / "evidence.json"
    helper.write_text(f"from pathlib import Path\nROOT=Path({str(data)!r})\n")
    evidence.write_text(json.dumps(dict(historical_path=str(data / "old.state"))))
    manifest, identity = freeze_player_package(repository=repo, helpers_root=helpers,
        helper_pins={str(helper): pin(helper)}, data_pins={str(evidence): pin(evidence)},
        environment_pins={}, output=tmp_path / "frozen", scripts=("worker.py",),
        data_root=data, source_commit="a"*40, dirty_status=" M unit.py\n",
        declaration=dict(checkout_data=[]))
    return manifest, identity, evidence, source


def test_package_binds_exact_data_and_relocated_history_without_live_checkout(package):
    path, identity, original, source = package
    manifest = bind_player_package(path, identity)
    copied = path.parent / "data/evidence.json"
    assert copied.read_bytes() == original.read_bytes()
    assert resolve_packaged_history_path(original) == copied
    source.write_text("value=2\n")
    assert bind_player_package(path, identity) == manifest
    assert manifest["relocations"] and manifest["source_commit"] == "a"*40


def test_changed_package_or_manifest_is_rejected(package):
    path, identity, _, _ = package
    with pytest.raises(ValueError, match="manifest changed"):
        bind_player_package(path, "b"*64)
    (path.parent / "data/evidence.json").write_text("{}")
    with pytest.raises(ValueError, match="input hash changed"):
        bind_player_package(path, identity)


def test_new_owned_output_history_is_not_remapped_to_frozen_old_data(package):
    path, identity, original, _ = package
    output = original.parent / "fresh-attempt"
    bind_player_package(path, identity, history_output=output)
    terminal = output / "initial/terminal.state"
    assert resolve_packaged_history_path(terminal) == terminal
    assert resolve_packaged_history_path(original) == path.parent / "data/evidence.json"
    # Neighboring data is not given a passthrough by a new attempt's output.
    assert resolve_packaged_history_path(original.parent / "other-run/state") == (
        path.parent / "data/other-run/state")


def test_data_symlink_is_rejected_before_freeze(package):
    path, identity, _, _ = package
    copied = path.parent / "data/evidence.json"
    payload = copied.read_bytes()
    copied.unlink()
    outside = path.parent.parent / "outside.json"
    outside.write_bytes(payload)
    copied.symlink_to(outside)
    with pytest.raises(ValueError, match="escaped"):
        bind_player_package(path, identity)


def test_guard_distinguishes_absent_probes_from_existing_unlisted_dependencies(package, tmp_path):
    path, identity, original, _ = package
    manifest = bind_player_package(path, identity)
    output=tmp_path/"result"
    output.mkdir()
    guard, reads, writes = make_package_read_guard(manifest,manifest_path=path,output=output)
    guard("open",(str(path.parent/"checkout/__pycache__/optional.pyc"),"r",0))
    guard("open",(str(original.parent/"optional-direct_url.json"),"r",0))
    guard("open",(str(path.parent/"data/evidence.json"),"r",0))
    with pytest.raises(ValueError,match="mutable"):
        guard("open",(str(original),"r",0))
    unexpected=path.parent/"data/unlisted.json"
    unexpected.write_text("{}")
    with pytest.raises(ValueError,match="undeclared package"):
        guard("open",(str(unexpected),"r",0))
    assert len(reads)==1 and not writes


def test_guard_keeps_frozen_files_read_only_and_blocks_subprocesses(package, tmp_path):
    path, identity, original, _ = package
    output=tmp_path/"result"
    output.mkdir()
    guard, _, writes=make_package_read_guard(bind_player_package(path,identity),
        manifest_path=path,output=output)
    for target in (original,path.parent/"data/evidence.json"):
        with pytest.raises(ValueError,match="write outside"):
            guard("open",(str(target),"w",os.O_WRONLY|os.O_CREAT))
    with pytest.raises(ValueError,match="subprocess"):
        guard("subprocess.Popen",("git",["git","status"],None,{}))
    guard("open",(str(output/"receipt.json"),"w",os.O_WRONLY|os.O_CREAT))
    assert writes=={str(output/"receipt.json")}


def test_unpinned_cache_is_denied_and_pinned_source_executes(package, tmp_path, monkeypatch):
    path, identity, _, _ = package
    source = path.parent / "checkout/src/pokemon_red_completion/unit.py"
    original_stat = source.stat()
    # A valid cache with the same source timestamp/size must not replace source.
    source.write_text("value=2\n")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    cache = py_compile.compile(str(source), doraise=True)
    source.write_text("value=1\n")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    ordinary = importlib.machinery.SourceFileLoader("ordinary_unit", str(source))
    unsafe_namespace = {}
    exec(ordinary.get_code("ordinary_unit"), unsafe_namespace)
    assert unsafe_namespace["value"] == 2  # Regression fixture really can win.
    guard, reads, writes = make_package_read_guard(
        bind_player_package(path, identity), manifest_path=path, output=tmp_path / "result"
    )

    class GuardedLoader(importlib.machinery.SourceFileLoader):
        def get_data(self, name):
            guard("open", (name, "r", 0))
            return super().get_data(name)

    with pytest.raises(FileNotFoundError, match="optional Python cache"):
        guard("open", (cache, "r", 0))
    loader = GuardedLoader("guarded_unit", str(source))
    namespace = {}
    exec(loader.get_code("guarded_unit"), namespace)
    assert namespace["value"] == 1
    assert reads == {str(source.resolve())}
    assert not writes


@pytest.mark.parametrize("location", ["data/__pycache__/unlisted.pyc", "checkout/unlisted.pyc",
                                      "checkout/__pycache__/unlisted.json"])
def test_cache_fallback_does_not_allow_other_undeclared_files(package, tmp_path, location):
    path, identity, _, _ = package
    unexpected = path.parent / location
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_bytes(b"undeclared bytes")
    guard, reads, writes = make_package_read_guard(
        bind_player_package(path, identity), manifest_path=path, output=tmp_path / "result"
    )
    with pytest.raises(ValueError, match="undeclared package"):
        guard("open", (str(unexpected), "r", 0))
    assert not reads and not writes


def test_mutable_cache_and_cache_writes_stay_forbidden(package, tmp_path):
    path, identity, _, original_source = package
    mutable = original_source.parent / "__pycache__/unit.pyc"
    mutable.parent.mkdir()
    mutable.write_bytes(b"mutable bytecode")
    frozen = path.parent / "checkout/__pycache__/unit.pyc"
    guard, reads, writes = make_package_read_guard(
        bind_player_package(path, identity), manifest_path=path, output=tmp_path / "result"
    )
    with pytest.raises(ValueError, match="mutable"):
        guard("open", (str(mutable), "r", 0))
    with pytest.raises(ValueError, match="write outside"):
        guard("open", (str(frozen), "w", os.O_WRONLY | os.O_CREAT))
    assert not reads and not writes


def test_unpinned_cache_cannot_execute_without_pinned_source(package, tmp_path):
    path, identity, _, _ = package
    cache = path.parent / "helpers/__pycache__/unlisted.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"cache-only code")
    guard, reads, writes = make_package_read_guard(
        bind_player_package(path, identity), manifest_path=path, output=tmp_path / "result"
    )

    class GuardedLoader(importlib.machinery.SourcelessFileLoader):
        def get_data(self, name):
            guard("open", (name, "r", 0))
            return super().get_data(name)

    with pytest.raises(FileNotFoundError, match="optional Python cache"):
        GuardedLoader("cache_only", str(cache)).get_code("cache_only")
    assert not reads and not writes


def test_bound_paths_avoid_duplicate_resolution_but_reads_still_resolve(package, tmp_path, monkeypatch):
    from pathlib import Path
    path, identity, _, _ = package
    names = set(json.loads(path.read_text())["pins"])
    original_resolve = Path.resolve
    calls = []
    def resolve(self, *args, **kwargs):
        if str(self) in names:
            calls.append(str(self))
        return original_resolve(self, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    bound = bind_player_package(path, identity)
    assert sorted(calls) == sorted(names)
    calls.clear()
    guard, reads, _ = make_package_read_guard(bound, manifest_path=path, output=tmp_path/"out")
    assert calls == []
    target = path.parent/"data/evidence.json"
    guard("open", (str(target), "r", 0))
    assert calls == [str(target)] and reads == {str(target)}
    with pytest.raises(AttributeError, match="immutable"):
        bound._binding = None


@pytest.mark.parametrize("copy_kind", ["dict", "json", "forged"])
def test_serialized_or_copied_manifests_never_carry_path_proof(package, tmp_path, monkeypatch, copy_kind):
    from pathlib import Path
    path, identity, _, _ = package
    bound = bind_player_package(path, identity)
    plain = dict(bound) if copy_kind == "dict" else json.loads(json.dumps(bound))
    assert plain == bound and "_binding" not in plain
    if copy_kind == "forged":
        plain["_binding"] = [str(path), [], []]
    names = set(plain["pins"])
    original_resolve = Path.resolve
    calls = []
    def resolve(self, *args, **kwargs):
        if str(self) in names:
            calls.append(str(self))
        return original_resolve(self, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    make_package_read_guard(plain, manifest_path=path, output=tmp_path/"out")
    assert sorted(calls) == sorted(names)


@pytest.mark.parametrize("mutation", ["digest", "name", "manifest_path"])
def test_bound_declaration_change_fails_closed(package, tmp_path, mutation):
    path, identity, _, _ = package
    bound = bind_player_package(path, identity)
    if mutation == "digest":
        bound["pins"][next(iter(bound["pins"]))] = "0"*64
    elif mutation == "name":
        bound["pins"][str(tmp_path/"extra")] = "0"*64
    else:
        path = tmp_path/"other-manifest.json"
    with pytest.raises(ValueError, match="bound package declaration changed"):
        make_package_read_guard(bound, manifest_path=path, output=tmp_path/"out")


def test_parent_symlink_after_binding_does_not_enroll_external_target(package, tmp_path):
    path, identity, _, _ = package
    bound = bind_player_package(path, identity)
    data = path.parent/"data"
    retained = path.parent/"retained-data"
    data.rename(retained)
    outside = tmp_path/"outside"
    outside.mkdir()
    (outside/"evidence.json").write_bytes((retained/"evidence.json").read_bytes())
    data.symlink_to(outside, target_is_directory=True)
    guard, reads, _ = make_package_read_guard(bound, manifest_path=path, output=tmp_path/"out")
    with pytest.raises(ValueError, match="undeclared external"):
        guard("open", (str(data/"evidence.json"), "r", 0))
    assert not reads


def test_leaf_symlink_after_guard_construction_still_fails(package, tmp_path):
    path, identity, _, _ = package
    bound = bind_player_package(path, identity)
    guard, reads, _ = make_package_read_guard(bound, manifest_path=path, output=tmp_path/"out")
    copied = path.parent/"data/evidence.json"
    outside = tmp_path/"external.json"
    outside.write_bytes(copied.read_bytes())
    copied.unlink()
    copied.symlink_to(outside)
    with pytest.raises(ValueError, match="undeclared external"):
        guard("open", (str(copied), "r", 0))
    assert not reads
