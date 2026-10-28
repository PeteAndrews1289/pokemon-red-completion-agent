"""Exact protected leaf admission in the shared frozen launcher; no native entry."""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace as N

import launch_frozen_red_player as launcher
import pytest
from pokemon_red_completion.red_player_package import make_package_read_guard


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def test_default_without_extra_inputs_is_unchanged():
    assert launcher.declared_protected_inputs({}) == ()
    assert launcher.declared_protected_inputs({"protected": {}}) == ()


def test_actual_guard_allows_only_authenticated_leaf_not_sibling_or_directory(tmp_path):
    frozen, output, inputs = tmp_path / "frozen", tmp_path / "output", tmp_path / "input"
    for p in (frozen, output, inputs): p.mkdir()
    manifest = frozen / "PLAYER-PACKAGE.json"
    manifest.write_text("{}")
    listed, sibling = inputs / "declared.json", inputs / "unlisted.json"
    listed.write_text("declared")
    sibling.write_text("not declared")
    extra = launcher.declared_protected_inputs({"protected": {str(listed): pin(listed)}})
    guard, reads, writes = make_package_read_guard(
        dict(pins={}, environment_pins={}, roots=[]), manifest_path=manifest,
        output=output, extra_inputs=extra,
    )
    guard("open", (str(listed), "r", 0))
    assert str(listed) in reads
    for path in (sibling, inputs):
        with pytest.raises(ValueError, match="undeclared external"):
            guard("open", (str(path), "r", 0))
    assert writes == set()


@pytest.mark.parametrize("fault", ["changed", "missing", "directory"])
def test_unverified_input_never_granted(tmp_path, fault):
    path = tmp_path / "input"
    path.write_text("original")
    expected = pin(path)
    if fault == "changed": path.write_text("changed")
    if fault == "missing": path.unlink()
    if fault == "directory": path.unlink(); path.mkdir()
    with pytest.raises(ValueError, match="bytes changed"):
        launcher.declared_protected_inputs({"protected": {str(path): expected}})


@pytest.mark.parametrize("protected", [[], True, {"relative": "a" * 64},
    {"": "a" * 64}, {"/absolute": True}, {"/absolute": "G" * 64},
    {"/absolute": "a" * 63}, {1: "a" * 64}])
def test_protected_input_mapping_rejects_ambiguous_declarations(protected):
    with pytest.raises(ValueError, match="protected input"):
        launcher.declared_protected_inputs({"protected": protected})


def test_shared_launch_authenticates_and_passes_exact_inputs_before_driver(tmp_path, monkeypatch):
    import pokemon_red_completion.red_player_package as package
    root, inputs = tmp_path / "frozen", tmp_path / "inputs"
    root.mkdir(); inputs.mkdir()
    source = inputs / "source-context.json"; source.write_text("{}")
    manifest = root / "PLAYER-PACKAGE.json"
    manifest.write_text(json.dumps(dict(schema="pokemon.red.frozen-player-package.v1",
        pins={}, environment_pins={}, roots=[])))
    plan = tmp_path / "PLAN.json"
    plan.write_text(json.dumps(dict(runtime_package=dict(path=str(manifest), sha256=pin(manifest)),
        protected={str(source): pin(source)})))
    events = []
    real = launcher.declared_protected_inputs
    def protected(value):
        events.append("authenticate")
        return real(value)
    monkeypatch.setattr(launcher, "declared_protected_inputs", protected)
    monkeypatch.setattr(launcher, "verify_initial_dependencies", lambda *a: events.append("dependencies") or {})
    monkeypatch.setattr(launcher, "loaded_player_modules", lambda *a: {})
    monkeypatch.setattr(launcher.sys, "meta_path", list(launcher.sys.meta_path))
    monkeypatch.setattr(launcher.sys, "path", list(launcher.sys.path))
    monkeypatch.setattr(package, "bind_player_package", lambda *a, **kw: {})
    def guard(*args, **kwargs):
        events.append("guard")
        assert set(kwargs["extra_inputs"]) == {str(plan), str(source)}
        return set(), set()
    monkeypatch.setattr(package, "package_read_guard", guard)
    monkeypatch.setattr(launcher, "preload_verified_native_dependencies", lambda *_: events.append("bootstrap") or {})
    monkeypatch.setattr(launcher, "run_selected_driver", lambda script, **kw: events.append("driver"))
    monkeypatch.setattr(launcher.sys, "argv", ["launch", "--manifest", str(manifest),
        "--manifest-sha256", pin(manifest), "--plan", str(plan), "--plan-sha256", pin(plan)])
    launcher.launch()
    assert events[:5] == ["authenticate", "dependencies", "bootstrap", "guard", "driver"]



@pytest.mark.parametrize("fault", [None, "module_unpinned", "module_changed", "library_unpinned"])
def test_native_import_bootstrap_uses_only_verified_environment_without_constructing_guest(tmp_path, monkeypatch, fault):
    files = {name: tmp_path / name for name in ("sdl2", "pyboy", "sdl2_library")}
    for name, path in files.items(): path.write_text(name)
    environment = {str(path): pin(path) for path in files.values()}
    modules = {"sdl2": N(__file__=str(files["sdl2"]), get_dll_file=lambda: str(files["sdl2_library"])),
        "pyboy": N(__file__=str(files["pyboy"]))}
    # Actual constructors are absent: this function must only import/verify modules.
    imported = []
    monkeypatch.setattr(launcher.importlib, "import_module", lambda name: imported.append(name) or modules[name])
    if fault == "module_unpinned": environment.pop(str(files["pyboy"]))
    if fault == "module_changed": files["pyboy"].write_text("changed")
    if fault == "library_unpinned": environment.pop(str(files["sdl2_library"]))
    if fault:
        with pytest.raises(ValueError, match="pinned environment"):
            launcher.preload_verified_native_dependencies(dict(environment_pins=environment))
    else:
        report = launcher.preload_verified_native_dependencies(dict(environment_pins=environment))
        assert report["scope"] == "verified_import_only_no_emulator"
        assert report["dependencies"]["sdl2_library"]["sha256"] == pin(files["sdl2_library"])
    assert imported == ["sdl2", "pyboy"]
