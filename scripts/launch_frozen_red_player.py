"""Verify the frozen actor before importing it; run from any working directory."""

import argparse
import gzip
import importlib.machinery
import io
import json
import os
import runpy
import sys
from hashlib import sha256
from pathlib import Path


class PinnedSourceLoader(importlib.machinery.SourceFileLoader):
    """Compile authenticated source directly; never consult Python bytecode."""

    def __init__(self, fullname, path, expected):
        super().__init__(fullname, path)
        self.expected = expected

    def get_code(self, fullname):
        payload = self.get_data(self.path)
        if sha256(payload).hexdigest() != self.expected:
            raise ValueError("frozen source changed before module import")
        return self.source_to_code(payload, self.path)


class FrozenSourceFinder:
    """Apply source pinning before bootstrap imports as well as after the guard."""

    def __init__(self, root, pins, environment_pins=None):
        self.root, self.pins = Path(root).resolve(), pins
        self.environment_pins = environment_pins or {}

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin in (None, "built-in", "frozen"):
            return None
        source = Path(spec.origin).absolute()
        if not source.is_relative_to(self.root):
            expected = self.environment_pins.get(str(source.resolve()))
            if expected is None or not isinstance(spec.loader, importlib.machinery.SourceFileLoader):
                return None
            if source.is_symlink():
                raise ValueError("pinned environment import requires regular Python source")
            spec.loader = PinnedSourceLoader(fullname, str(source), expected)
            return spec
        expected = self.pins.get(str(source.resolve()))
        if (source.is_symlink() or not source.resolve().is_relative_to(self.root)
                or expected is None
                or not isinstance(spec.loader, importlib.machinery.SourceFileLoader)):
            raise ValueError("frozen import requires declared regular Python source")
        spec.loader = PinnedSourceLoader(fullname, str(source), expected)
        return spec


def isolated_io_report_path(output, *, compressed=False):
    """Retain each inspection/continuation report instead of overwriting one."""
    output = Path(output)
    ordinal = 1
    while True:
        name = "ISOLATED-IO.json" if ordinal == 1 else f"ISOLATED-IO-{ordinal:04d}.json"
        path = output / name
        if not path.exists() and not path.with_suffix(".json.gz").exists():
            return path.with_suffix(".json.gz") if compressed else path
        ordinal += 1


def declared_compressed_io_report(plan):
    """Compression is a prospective explicit representation, never a sampled report."""
    spec = plan.get("input_recording")
    if spec is None:
        return False
    if not isinstance(spec, dict):
        raise ValueError("input recording requires an explicit dictionary")
    if "isolation_report" not in spec:
        return False
    if spec["isolation_report"] != "gzip_json_v1" or plan.get("partition") != "development":
        raise ValueError("compressed isolation report requires explicit DEVELOPMENT gzip_json_v1")
    return True


def write_isolated_io_report(output, report, *, compressed=False):
    """Keep the complete original JSON bytes, optionally gzip-compressed losslessly."""
    path = isolated_io_report_path(output, compressed=compressed)
    if not compressed:
        with path.open("x", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(report, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    else:
        with path.open("xb") as raw:
            os.fchmod(raw.fileno(), 0o600)
            with (
                gzip.GzipFile(
                    fileobj=raw, filename="", mtime=0, mode="wb", compresslevel=1,
                ) as zipped,
                io.TextIOWrapper(zipped, encoding="utf-8") as stream,
            ):
                json.dump(report, stream, sort_keys=True, indent=2)
                stream.write("\n")
            raw.flush()
            os.fsync(raw.fileno())
    return path


def loaded_player_modules(manifest, root):
    """Reject cached mutable modules as well as later filesystem imports."""
    original_roots = tuple(Path(a).resolve() for a, _ in manifest["roots"])
    environment = {Path(name).resolve() for name in manifest["environment_pins"]}
    root = Path(root).resolve()
    loaded = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str):
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(root):
            loaded[name] = str(path)
        elif name == "pokemon_red_completion" or name.startswith("pokemon_red_completion."):
            raise ValueError("frozen player package was already imported from outside the package")
        elif path not in environment and any(path.is_relative_to(base) for base in original_roots):
            raise ValueError(f"frozen player has a cached mutable project module: {name}")
    return loaded


def run_selected_driver(script, *, plan, check_imports=False):
    """Import the actual fresh entry without calling its gameplay main block."""
    if check_imports and Path(script).name != "run_fresh_red_player.py":
        raise ValueError("import-only check requires the fresh entry")
    driver = runpy.run_path(
        str(script), run_name="frozen_driver_import_check" if check_imports else "__main__"
    )
    if check_imports:
        driver["validate_fresh_plan"](plan, import_only=True)


def validate_diagnostic_timing(plan, *, now=None):
    """Validate prospective serial-copy timing without importing an emulator."""
    from datetime import datetime, timezone
    from math import isfinite

    try:
        native = plan['native_limits']['seconds']
        worker = plan['worker_wall_seconds']
        outer = plan['caps']['outer_seconds']
        hold = plan['full_hold_seconds']
        cutoff = datetime.fromisoformat(plan['cutoff_utc'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('diagnostic timing declaration is incomplete') from error
    if (any(type(v) not in (int, float) or not isfinite(v) or v <= 0
            for v in (native, worker, outer, hold))
            or type(native) is not int
            or not native < worker < outer or outer != hold
            or cutoff.utcoffset() is None):
        raise ValueError('diagnostic timing requires native < worker < outer == hold and aware cutoff')
    if now is None:
        now = datetime.now(timezone.utc)
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError('diagnostic timing requires an aware current time')
    remaining = (cutoff - now).total_seconds()
    if remaining <= 0:
        raise ValueError('diagnostic cutoff has expired')
    return min(worker, remaining)


def validate_retained_train_custody(plan, custody, catalog_row):
    """Require explicit preserved TRAIN ancestry; do not default missing flags.

    Exact parent terminal authentication and failed-tail policy remain with the
    existing scenario preflight. This shared check does not require a parent win.
    """
    def digest(value):
        return (type(value) is str and len(value) == 64
                and all(c in '0123456789abcdef' for c in value))

    if any(type(v) is not dict for v in (plan, custody, catalog_row)):
        raise ValueError('retained TRAIN custody requires explicit documents')
    source = plan.get('source_sha256')
    original = plan.get('original_TRAIN_state_sha256')
    if (not digest(source) or not digest(original)
            or custody.get('retained_state_sha256') != source
            or custody.get('original_TRAIN_state_sha256') != original
            or catalog_row.get('state_sha256') != original
            or catalog_row.get('source_partition') != 'train'
            or custody.get('development_relabel') is not False
            or custody.get('same_related_TRAIN_ancestry') is not True
            or type(custody.get('save_writes')) is not int
            or custody['save_writes'] != 0):
        raise ValueError('retained TRAIN custody flags or source identities differ')


def validate_diagnostic_startup(plan, custody, catalog_row, *, now=None):
    """Common preflight/worker gate before package binding or native allocation."""
    allowance = validate_diagnostic_timing(plan, now=now)
    validate_retained_train_custody(plan, custody, catalog_row)
    return allowance




def verify_initial_dependencies(manifest, root):
    """Authenticate every dependency before imports, honoring declared data-cache release.

    Source/environment checks retain their existing behavior. Data is streamed
    only for the existing opt-in policy, and released only after its complete
    digest matches. No pin is skipped and no file contents are changed.
    """
    policy = manifest.get("declaration", {}).get("verified_data_cache_release")
    if policy not in (None, "posix_fadvise_dontneed_v1"):
        raise ValueError("unknown verified data cache release policy")
    if policy is not None and (not hasattr(os, "posix_fadvise")
            or not hasattr(os, "POSIX_FADV_DONTNEED")):
        raise ValueError("verified data cache release is unavailable")
    pins = {**manifest["pins"], **manifest["environment_pins"]}
    data_files = data_bytes = 0
    for name, expected in pins.items():
        path = Path(name)
        if path.is_symlink():
            raise ValueError("frozen runtime dependency changed before import")
        release = policy is not None and path.is_relative_to(Path(root) / "data")
        if not release:
            if sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("frozen runtime dependency changed before import")
            continue
        if not path.resolve().is_relative_to(Path(root).resolve() / "data"):
            raise ValueError("frozen runtime data dependency escaped its directory")
        with path.open("rb") as source:
            digest = sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
                data_bytes += len(block)
            if digest.hexdigest() != expected:
                raise ValueError("frozen runtime dependency changed before import")
            try:
                os.posix_fadvise(source.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
            except OSError as error:
                raise ValueError("verified data cache release failed") from error
            data_files += 1
    return dict(policy=policy,authenticated_files=len(pins),released_data_files=data_files,
        streamed_data_bytes=data_bytes,every_pin_authenticated=True,file_contents_changed=False)


def preload_verified_native_dependencies(manifest):
    """Resolve pinned native libraries before read-only runtime enforcement.

    Importing SDL/PyBoy can perform loader discovery. This constructs no adapter
    or emulator and grants no additional runtime reads or writes.
    """
    modules = {name: importlib.import_module(name) for name in ("sdl2", "pyboy")}
    paths = {
        "sdl2": Path(modules["sdl2"].__file__).resolve(),
        "pyboy": Path(modules["pyboy"].__file__).resolve(),
        "sdl2_library": Path(modules["sdl2"].get_dll_file()).resolve(),
    }
    verified = {}
    for name, path in paths.items():
        expected = manifest["environment_pins"].get(str(path))
        if expected is None or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("native import bootstrap differs from the pinned environment")
        verified[name] = dict(path=str(path), sha256=expected)
    return dict(scope="verified_import_only_no_emulator", dependencies=verified)


def declared_protected_inputs(plan):
    """Authenticate explicit input leaves before granting their read paths."""
    protected = plan.get("protected", {})
    if not isinstance(protected, dict):
        raise ValueError("protected inputs require an exact path-to-SHA256 mapping")
    inputs = {}
    for name, expected in protected.items():
        if (type(name) is not str or not name.strip() or not Path(name).is_absolute()
                or type(expected) is not str or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)):
            raise ValueError("protected inputs require absolute file paths and SHA256 digests")
        path = Path(name).resolve()
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("protected input bytes changed before player import")
        key = str(path)
        if key in inputs and inputs[key] != expected:
            raise ValueError("protected input aliases have conflicting digests")
        inputs[key] = expected
    return tuple(sorted(inputs))


def launch():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--check-imports", action="store_true",
        help="Import and validate the fresh driver without an emulator or gameplay dispatch")
    args, remaining = parser.parse_known_args()
    if args.check_imports and (not args.fresh or remaining):
        parser.error("--check-imports requires --fresh and accepts no gameplay arguments")
    manifest_path, plan_path = Path(args.manifest).resolve(), Path(args.plan).resolve()
    payload, plan_bytes = manifest_path.read_bytes(), plan_path.read_bytes()
    if (
        sha256(payload).hexdigest() != args.manifest_sha256
        or sha256(plan_bytes).hexdigest() != args.plan_sha256
    ):
        raise ValueError("frozen launch declaration changed before import")
    manifest, plan = json.loads(payload), json.loads(plan_bytes)
    compressed_io_report = declared_compressed_io_report(plan)
    root = manifest_path.parent
    if manifest.get("schema") != "pokemon.red.frozen-player-package.v1":
        raise ValueError("unknown player package")
    if plan.get("runtime_package") != dict(path=str(manifest_path), sha256=args.manifest_sha256):
        raise ValueError("plan and runtime package identity differ")
    sources = plan.get("backend_sources")
    if "backend_sources" in plan and (
        not isinstance(sources, dict)
        or any(not isinstance(name, str) or not isinstance(expected, str)
               or manifest["pins"].get(name) != expected
               for name, expected in sources.items())
    ):
        raise ValueError("frozen backend declaration differs from package")
    protected_inputs = declared_protected_inputs(plan)
    initial_dependency_verification = verify_initial_dependencies(manifest, root)
    loaded_player_modules(manifest, root)
    sys.dont_write_bytecode = True
    sys.path[:0] = [
        str(root / "checkout/src"),
        str(root / "checkout/scripts"),
        str(root / "helpers"),
    ]
    sys.meta_path.insert(0, FrozenSourceFinder(
        root, manifest["pins"], manifest["environment_pins"]
    ))
    from pokemon_red_completion.red_player_package import bind_player_package, package_read_guard

    bound = bind_player_package(
        manifest_path, args.manifest_sha256, history_output=plan_path.parent
    )
    native_dependency_imports = preload_verified_native_dependencies(bound)
    reads, writes = package_read_guard(
        bound, manifest_path=manifest_path, output=plan_path.parent,
        extra_inputs=(str(plan_path), *protected_inputs),
    )
    script = "run_fresh_red_player.py" if args.fresh else "run_configured_red_player.py"
    sys.argv = [script, "--plan", str(plan_path), *remaining]
    try:
        run_selected_driver(root / "checkout/scripts" / script,
            plan=plan, check_imports=args.check_imports)
    finally:
        import_failure = None
        try:
            modules = loaded_player_modules(manifest, root)
        except ValueError as error:
            modules, import_failure = {}, str(error)
        report = dict(
            schema="pokemon.red.frozen-launch-io.v1",
            manifest_sha256=args.manifest_sha256,
            plan_sha256=args.plan_sha256,
            reads=sorted(reads),
            writes=sorted(writes),
            fresh=args.fresh,
            import_check_only=args.check_imports,
            loaded_project_modules=modules,
            module_isolation_error=import_failure,
            initial_dependency_verification=initial_dependency_verification,
            native_dependency_imports=native_dependency_imports,
        )
        write_isolated_io_report(plan_path.parent, report, compressed=compressed_io_report)
        if import_failure is not None and sys.exception() is None:
            raise ValueError(import_failure)


if __name__ == "__main__":
    launch()
