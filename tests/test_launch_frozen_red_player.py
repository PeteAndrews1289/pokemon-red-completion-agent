import gzip
import importlib.machinery
import json
import os
import py_compile
from hashlib import sha256
from types import SimpleNamespace as N

import launch_frozen_red_player as launcher
import pytest


def test_separate_inspections_and_continuations_retain_each_isolation_report(tmp_path):
    first = launcher.isolated_io_report_path(tmp_path)
    assert first.name == "ISOLATED-IO.json"
    first.write_text("first-launch-proof")
    second = launcher.isolated_io_report_path(tmp_path)
    assert second.name == "ISOLATED-IO-0002.json"
    second.write_text("second-launch-proof")
    assert launcher.isolated_io_report_path(tmp_path).name == "ISOLATED-IO-0003.json"
    assert first.read_text() == "first-launch-proof"


def test_compressed_report_retains_every_original_json_byte_and_shared_ordinals(tmp_path):
    report = dict(
        reads=[f"private/read-{i:05d}" for i in range(1000)],
        writes=[f"private/write-{i:05d}" for i in range(1000)], error="native failure retained",
    )
    plain = launcher.write_isolated_io_report(tmp_path, report)
    compressed = launcher.write_isolated_io_report(tmp_path, report, compressed=True)
    assert compressed.name == 'ISOLATED-IO-0002.json.gz'
    assert gzip.decompress(compressed.read_bytes()) == plain.read_bytes()
    assert json.loads(gzip.decompress(compressed.read_bytes())) == report
    assert compressed.stat().st_size < plain.stat().st_size / 5
    assert launcher.isolated_io_report_path(tmp_path).name == 'ISOLATED-IO-0003.json'
    assert launcher.isolated_io_report_path(
        tmp_path, compressed=True,
    ).name == 'ISOLATED-IO-0003.json.gz'


@pytest.mark.parametrize('spec,partition', [({'isolation_report': 'sample'}, 'development'),
    ({'isolation_report': 'gzip_json_v1'}, 'train'), ([], 'development')])
def test_compressed_report_rejects_undeclared_or_lossy_modes(spec, partition):
    with pytest.raises(ValueError):
        launcher.declared_compressed_io_report(dict(input_recording=spec, partition=partition))


@pytest.mark.parametrize("fault", ["manifest", "plan", "changed", "missing", "symlink"])
@pytest.mark.parametrize("import_check", [False, True])
def test_frozen_wrapper_rejects_changed_or_missing_inputs_before_player_import(
    tmp_path, monkeypatch, fault, import_check
):
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    dependency = frozen / "actor.py"
    dependency.write_bytes(b"actor = 1\n")
    manifest = frozen / "PLAYER-PACKAGE.json"
    manifest.write_text(
        json.dumps(
            dict(
                schema="pokemon.red.frozen-player-package.v1",
                pins={str(dependency): sha256(dependency.read_bytes()).hexdigest()},
                environment_pins={},
                roots=[(str(tmp_path / "live"), str(frozen))],
            )
        )
    )
    manifest_pin = sha256(manifest.read_bytes()).hexdigest()
    plan = tmp_path / "PLAN.json"
    plan.write_text(json.dumps(dict(runtime_package=dict(path=str(manifest), sha256=manifest_pin))))
    plan_pin = sha256(plan.read_bytes()).hexdigest()
    if fault == "manifest":
        manifest.write_text("{}")
    elif fault == "plan":
        plan.write_text("{}")
    elif fault == "changed":
        dependency.write_bytes(b"actor = 2\n")
    elif fault == "missing":
        dependency.unlink()
    elif fault == "symlink":
        target = tmp_path / "mutable-actor.py"
        target.write_bytes(dependency.read_bytes())
        dependency.unlink()
        dependency.symlink_to(target)
    monkeypatch.setattr(
        launcher.sys,
        "argv",
        [
            "launch",
            "--manifest",
            str(manifest),
            "--manifest-sha256",
            manifest_pin,
            "--plan",
            str(plan),
            "--plan-sha256",
            plan_pin,
        ] + (["--fresh", "--check-imports"] if import_check else []),
    )
    monkeypatch.setattr(
        launcher.runpy, "run_path", lambda *a, **k: pytest.fail("must not reach player")
    )
    with pytest.raises((ValueError, FileNotFoundError)):
        launcher.launch()


def test_cached_mutable_modules_are_not_accepted_as_frozen_imports(tmp_path, monkeypatch):
    root, mutable = tmp_path / "frozen", tmp_path / "live"
    manifest = dict(roots=[(str(mutable), str(root))], environment_pins={})
    monkeypatch.setattr(
        launcher.sys,
        "modules",
        {
            "private_player_alias": N(__file__=str(mutable / "actor.py")),
        },
    )
    with pytest.raises(ValueError, match="cached mutable"):
        launcher.loaded_player_modules(manifest, root)
    monkeypatch.delitem(launcher.sys.modules, "private_player_alias")
    monkeypatch.setitem(
        launcher.sys.modules,
        "pokemon_red_completion.existing",
        N(__file__=str(tmp_path / "different-root/module.py")),
    )
    with pytest.raises(ValueError, match="outside the package"):
        launcher.loaded_player_modules(manifest, root)


def test_pinned_environment_is_not_confused_with_mutable_project_modules(tmp_path, monkeypatch):
    root, live = tmp_path / "frozen", tmp_path / "live"
    native = live / "venv/numpy/module.py"
    manifest = dict(roots=[(str(live), str(root))], environment_pins={str(native): "a" * 64})
    monkeypatch.setattr(launcher.sys, "modules", {"numpy": N(__file__=str(native))})
    assert launcher.loaded_player_modules(manifest, root) == {}


def test_import_only_check_uses_actual_fresh_entry_without_calling_gameplay(tmp_path):
    script = tmp_path / "run_fresh_red_player.py"
    script.write_text(
        "def validate_fresh_plan(plan, *, import_only=False):\n"
        " assert import_only is True\n"
        " assert plan == {'declared': True}\n"
        "def run():\n"
        " raise AssertionError('gameplay must not start')\n"
        "if __name__ == '__main__':\n"
        " run()\n"
    )
    launcher.run_selected_driver(script, plan={"declared": True}, check_imports=True)
    with pytest.raises(AssertionError, match="gameplay must not start"):
        launcher.run_selected_driver(script, plan={"declared": True})


def test_import_only_check_validates_fresh_plan_and_rejects_other_entries(tmp_path):
    script = tmp_path / "run_fresh_red_player.py"
    script.write_text(
        "def validate_fresh_plan(plan, *, import_only=False):\n"
        " assert import_only is True\n"
        " raise ValueError('invalid declaration')\n"
    )
    with pytest.raises(ValueError, match="invalid declaration"):
        launcher.run_selected_driver(script, plan={}, check_imports=True)
    with pytest.raises(ValueError, match="requires the fresh entry"):
        launcher.run_selected_driver(tmp_path / "run_configured_red_player.py",
            plan={}, check_imports=True)


def test_pinned_source_loader_ignores_valid_wrong_bytecode_before_guard_bootstrap(tmp_path):
    source = tmp_path / "bootstrap.py"
    source.write_text("value=1\n")
    expected, stamp = sha256(source.read_bytes()).hexdigest(), source.stat()
    source.write_text("value=2\n")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    py_compile.compile(str(source), doraise=True)
    source.write_text("value=1\n")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    unsafe = importlib.machinery.SourceFileLoader("unsafe", str(source))
    namespace = {}
    exec(unsafe.get_code("unsafe"), namespace)
    assert namespace["value"] == 2
    loader = launcher.PinnedSourceLoader("verified", str(source), expected)
    namespace = {}
    exec(loader.get_code("verified"), namespace)
    assert namespace["value"] == 1
    source.write_text("value=3\n")
    with pytest.raises(ValueError, match="source changed"):
        loader.get_code("verified")


def test_source_finder_rejects_unlisted_symlink_and_sourceless_modules(tmp_path):
    source = tmp_path / "unit.py"
    source.write_text("value=1\n")
    finder = launcher.FrozenSourceFinder(
        tmp_path, {str(source): sha256(source.read_bytes()).hexdigest()})
    assert isinstance(finder.find_spec("unit", [str(tmp_path)]).loader, launcher.PinnedSourceLoader)
    unlisted = tmp_path / "unlisted.py"
    unlisted.write_text("value=2\n")
    with pytest.raises(ValueError, match="declared regular Python source"):
        finder.find_spec("unlisted", [str(tmp_path)])
    linked = tmp_path / "linked.py"
    linked.symlink_to(source)
    with pytest.raises(ValueError, match="declared regular Python source"):
        finder.find_spec("linked", [str(tmp_path)])
    escaped = tmp_path / "escaped.py"
    escaped.symlink_to(__file__)
    with pytest.raises(ValueError, match="declared regular Python source"):
        finder.find_spec("escaped", [str(tmp_path)])
    bytecode = tmp_path / "cache_only.pyc"
    py_compile.compile(str(source), cfile=str(bytecode), doraise=True)
    finder.pins[str(bytecode)] = sha256(bytecode.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="declared regular Python source"):
        finder.find_spec("cache_only", [str(tmp_path)])


def test_source_finder_does_not_replace_environment_loaders(tmp_path):
    root, environment = tmp_path / "frozen", tmp_path / "environment"
    root.mkdir()
    environment.mkdir()
    (environment / "unit.py").write_text("value=1\n")
    assert launcher.FrozenSourceFinder(root, {}).find_spec("unit", [str(environment)]) is None


@pytest.mark.parametrize("import_check", [False, True])
@pytest.mark.parametrize("fault", ["stale_hash", "unknown_source", "not_mapping", "null_sources", "null_hash", "runtime_identity"])
def test_conflicting_plan_is_rejected_before_dependency_payload_reads(tmp_path, monkeypatch, fault, import_check):
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    dependency = frozen / "helper.py"
    dependency.write_bytes(b"native-helper")
    digest = sha256(dependency.read_bytes()).hexdigest()
    manifest = frozen / "PLAYER-PACKAGE.json"
    manifest.write_text(json.dumps(dict(schema="pokemon.red.frozen-player-package.v1",
        pins={str(dependency): digest}, environment_pins={}, roots=[])))
    manifest_sha = sha256(manifest.read_bytes()).hexdigest()
    spec = dict(runtime_package=dict(path=str(manifest), sha256=manifest_sha),
        backend_sources={str(dependency): digest})
    if fault == "stale_hash":
        spec["backend_sources"][str(dependency)] = "a" * 64
    elif fault == "unknown_source":
        spec["backend_sources"] = {str(tmp_path / "outside.py"): digest}
    elif fault == "not_mapping":
        spec["backend_sources"] = [[str(dependency), digest]]
    elif fault == "null_sources":
        spec["backend_sources"] = None
    elif fault == "null_hash":
        spec["backend_sources"][str(dependency)] = None
    elif fault == "runtime_identity":
        spec["runtime_package"]["sha256"] = "b" * 64
    plan = tmp_path / "PLAN.json"
    plan.write_text(json.dumps(spec))
    plan_sha = sha256(plan.read_bytes()).hexdigest()
    before = manifest.read_bytes(), plan.read_bytes(), dependency.read_bytes()
    original_read = type(manifest).read_bytes
    reads = []

    def restricted_read(path):
        if path not in (manifest, plan):
            pytest.fail("conflicting declaration reached expensive dependency payload binding")
        reads.append(path)
        return original_read(path)

    monkeypatch.setattr(type(manifest), "read_bytes", restricted_read)
    monkeypatch.setattr(launcher.sys, "argv", ["launch", "--manifest", str(manifest),
        "--manifest-sha256", manifest_sha, "--plan", str(plan), "--plan-sha256", plan_sha]
        + (["--fresh", "--check-imports"] if import_check else []))
    monkeypatch.setattr(launcher.runpy, "run_path", lambda *a, **k:pytest.fail("no player import allowed"))
    with pytest.raises(ValueError, match="declaration differs|runtime package identity"):
        launcher.launch()
    assert reads == [manifest, plan]
    assert tuple(original_read(p) for p in (manifest, plan, dependency)) == before


@pytest.mark.parametrize("import_check", [False, True])
def test_matching_backend_declaration_keeps_full_dependency_integrity(tmp_path, monkeypatch, import_check):
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    dependency = frozen / "helper.py"
    dependency.write_bytes(b"old-native-helper")
    digest = sha256(dependency.read_bytes()).hexdigest()
    manifest = frozen / "PLAYER-PACKAGE.json"
    manifest.write_text(json.dumps(dict(schema="pokemon.red.frozen-player-package.v1",
        pins={str(dependency): digest}, environment_pins={}, roots=[])))
    manifest_sha = sha256(manifest.read_bytes()).hexdigest()
    plan = tmp_path / "PLAN.json"
    plan.write_text(json.dumps(dict(runtime_package=dict(path=str(manifest), sha256=manifest_sha),
        backend_sources={str(dependency): digest})))
    dependency.write_bytes(b"changed-native-helper")
    monkeypatch.setattr(launcher.sys, "argv", ["launch", "--manifest", str(manifest),
        "--manifest-sha256", manifest_sha, "--plan", str(plan), "--plan-sha256", sha256(plan.read_bytes()).hexdigest()]
        + (["--fresh", "--check-imports"] if import_check else []))
    monkeypatch.setattr(launcher.runpy, "run_path", lambda *a, **k:pytest.fail("no player import allowed"))
    with pytest.raises(ValueError, match="runtime dependency changed"):
        launcher.launch()


def test_explicit_pinned_environment_source_ignores_valid_wrong_bytecode(tmp_path):
    root, environment = tmp_path / "frozen", tmp_path / "environment"
    root.mkdir()
    environment.mkdir()
    source = environment / "environment_unit.py"
    source.write_text("value=1\n")
    expected, stamp = sha256(source.read_bytes()).hexdigest(), source.stat()
    source.write_text("value=2\n")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    py_compile.compile(str(source), doraise=True)
    source.write_text("value=1\n")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    unsafe = importlib.machinery.SourceFileLoader("unsafe", str(source))
    namespace = {}
    exec(unsafe.get_code("unsafe"), namespace)
    assert namespace["value"] == 2
    finder = launcher.FrozenSourceFinder(root, {}, {str(source): expected})
    spec = finder.find_spec("environment_unit", [str(environment)])
    namespace = {}
    exec(spec.loader.get_code("environment_unit"), namespace)
    assert namespace["value"] == 1
    source.write_text("value=3\n")
    with pytest.raises(ValueError, match="source changed"):
        spec.loader.get_code("environment_unit")


def test_environment_pinning_does_not_grant_unlisted_cache_or_symlink(tmp_path):
    root, environment = tmp_path / "frozen", tmp_path / "environment"
    root.mkdir()
    environment.mkdir()
    source = environment / "environment_unit.py"
    source.write_text("value=1\n")
    expected = sha256(source.read_bytes()).hexdigest()
    finder = launcher.FrozenSourceFinder(root, {}, {str(source): expected})
    unlisted = environment / "unlisted.py"
    unlisted.write_text("value=2\n")
    assert finder.find_spec("unlisted", [str(environment)]) is None
    linked = environment / "linked.py"
    linked.symlink_to(source)
    with pytest.raises(ValueError, match="regular Python source"):
        finder.find_spec("linked", [str(environment)])
    bytecode = environment / "cache_only.pyc"
    py_compile.compile(str(source), cfile=str(bytecode), doraise=True)
    finder.environment_pins[str(bytecode)] = sha256(bytecode.read_bytes()).hexdigest()
    assert finder.find_spec("cache_only", [str(environment)]) is None


def startup_documents():
    from datetime import datetime,timezone
    plan=dict(native_limits=dict(seconds=480),worker_wall_seconds=570,
        caps=dict(outer_seconds=600),full_hold_seconds=600,
        cutoff_utc='2026-10-23T04:32:30+00:00',source_sha256='a'*64,
        original_TRAIN_state_sha256='b'*64)
    custody=dict(retained_state_sha256='a'*64,original_TRAIN_state_sha256='b'*64,
        development_relabel=False,same_related_TRAIN_ancestry=True,save_writes=0)
    row=dict(state_sha256='b'*64,source_partition='train')
    return plan,custody,row,datetime(2026,10,23,2,tzinfo=timezone.utc)


@pytest.mark.parametrize('native,worker,outer',[(240,330,360),(480,570,600)])
def test_shared_diagnostic_startup_admits_both_declared_profiles(native,worker,outer):
    p,c,r,now=startup_documents();p.update(native_limits=dict(seconds=native),
        worker_wall_seconds=worker,caps=dict(outer_seconds=outer),full_hold_seconds=outer)
    assert launcher.validate_diagnostic_startup(p,c,r,now=now)==worker
    from datetime import timedelta
    assert launcher.validate_diagnostic_startup(p,c,r,now=now+timedelta(hours=2,minutes=31))==90


@pytest.mark.parametrize('fault',['equal','inverted','hold','bool','string','nan','infinity','expired','naive','fractional_native','missing'])
def test_shared_diagnostic_timing_rejects_invalid_or_stale_limits(fault):
    p,c,r,now=startup_documents()
    if fault=='equal':p['native_limits']['seconds']=570
    elif fault=='inverted':p['worker_wall_seconds']=700
    elif fault=='hold':p['full_hold_seconds']=601
    elif fault=='bool':p['native_limits']['seconds']=True
    elif fault=='string':p['native_limits']['seconds']='480'
    elif fault=='nan':p['worker_wall_seconds']=float('nan')
    elif fault=='infinity':p['caps']['outer_seconds']=float('inf')
    elif fault=='expired':p['cutoff_utc']='2026-10-23T01:00:00+00:00'
    elif fault=='naive':p['cutoff_utc']='2026-10-23T04:32:30'
    elif fault=='fractional_native':p['native_limits']['seconds']=480.5
    else:del p['worker_wall_seconds']
    with pytest.raises(ValueError):launcher.validate_diagnostic_startup(p,c,r,now=now)


@pytest.mark.parametrize('fault',['missing_flag','relabel','integer_flag','ancestry','writes','bool_writes','retained_hash','original_hash','catalog_hash','partition'])
def test_shared_custody_gate_rejects_before_emulator_construction(fault):
    p,c,r,now=startup_documents();construction=[]
    if fault=='missing_flag':del c['development_relabel']
    elif fault=='relabel':c['development_relabel']=True
    elif fault=='integer_flag':c['development_relabel']=0
    elif fault=='ancestry':c['same_related_TRAIN_ancestry']=False
    elif fault=='writes':c['save_writes']=1
    elif fault=='bool_writes':c['save_writes']=False
    elif fault=='retained_hash':c['retained_state_sha256']='c'*64
    elif fault=='original_hash':p['original_TRAIN_state_sha256']='c'*64
    elif fault=='catalog_hash':r['state_sha256']='c'*64
    else:r['source_partition']='development'
    with pytest.raises(ValueError):
        launcher.validate_diagnostic_startup(p,c,r,now=now)
        construction.append('forbidden emulator construction')
    assert not construction


def test_custody_gate_does_not_require_a_winning_parent():
    p,c,r,now=startup_documents();c.update(parent_passed=False,parent_outcome='ordinary_loss')
    assert launcher.validate_diagnostic_startup(p,c,r,now=now)==570
