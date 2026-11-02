"""Frozen files and filesystem binding for the existing native player.

This packages an actor; it does not choose goals, migrate a backend, or provide
a security sandbox for untrusted Python. Historical JSON bytes remain exact.
Only declared filesystem string literals in private helper sources relocate.
"""

import ast
import json
import os
import sys
from hashlib import sha256
from pathlib import Path, PosixPath

from .emulation_batch import freeze_runtime, verify_pins
from .provenance import canonical_sha256

SCHEMA = "pokemon.red.frozen-player-package.v1"
_history_roots = ()
_history_output = None


class _BoundPlayerPackage(dict):
    """In-process path proof; JSON/copies retain only the ordinary manifest."""

    __slots__ = ("_binding",)

    def __init__(self, manifest, manifest_path, canonical_paths):
        super().__init__(manifest)
        object.__setattr__(self, "_binding", (
            manifest_path, tuple(manifest["pins"].items()), frozenset(canonical_paths)))

    def __setattr__(self, name, value):
        raise AttributeError("bound package path proof is immutable")

    def paths_for_guard(self, manifest_path):
        path, pins, canonical_paths = self._binding
        if path != manifest_path or pins != tuple(self["pins"].items()):
            raise ValueError("bound package declaration changed before guard construction")
        return canonical_paths


def resolve_packaged_history_path(path):
    """Resolve an old evidence location without rewriting its authenticated bytes."""
    path = Path(path)
    if _history_output is not None and path.is_relative_to(_history_output):
        return path
    for original, frozen in _history_roots:
        if path.is_relative_to(original):
            return frozen / path.relative_to(original)
    return path


def relocate_helper(payload, roots):
    """Relocate literal paths only; verify all other Python syntax is identical."""
    text = payload.decode("utf-8")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line.encode("utf-8"))
    encoded = payload
    replacements = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        for original, frozen in roots:
            original, frozen = str(original), str(frozen)
            if value == original or value.startswith(original + "/"):
                replacement = frozen + value[len(original):]
                replacements.append((offsets[node.lineno - 1] + node.col_offset,
                    offsets[node.end_lineno - 1] + node.end_col_offset,
                    repr(replacement).encode("utf-8")))
                node.value = replacement
                break
    for start, end, replacement in sorted(replacements, reverse=True):
        encoded = encoded[:start] + replacement + encoded[end:]
    if ast.dump(ast.parse(encoded)) != ast.dump(tree):
        raise ValueError("helper relocation changed executable syntax")
    return encoded


def freeze_player_package(*, repository, helpers_root, helper_pins, data_pins,
                          environment_pins, output, scripts, data_root,
                          source_commit, dirty_status, declaration):
    """Extend the existing source freezer with exact helper/data dependencies."""
    repository, helpers_root, data_root, output = map(Path,
        (repository, helpers_root, data_root, output))
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit):
        raise ValueError("package needs the actual source revision")
    verify_pins({**helper_pins, **data_pins, **environment_pins})
    output.mkdir(mode=0o700, exist_ok=False)
    checkout, helpers, data = output / "checkout", output / "helpers", output / "data"
    roots = ((repository.resolve(), checkout.resolve()),
             (helpers_root.resolve(), helpers.resolve()),
             (data_root.resolve(), data.resolve()))
    pins = freeze_runtime(repository, checkout, scripts)
    originals, relocations = {}, {}
    for collection, base, target_base, relocate in (
        (helper_pins, helpers_root, helpers, True),
        (data_pins, data_root, data, False),
    ):
        for name, expected in sorted(collection.items()):
            path = Path(name)
            if path.is_symlink() or not path.is_relative_to(base):
                raise ValueError("package input is not a declared regular root member")
            payload = path.read_bytes()
            if sha256(payload).hexdigest() != expected:
                raise ValueError("package input changed during freeze")
            target = target_base / path.relative_to(base)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            copied = relocate_helper(payload, roots) if relocate else payload
            with target.open("xb") as stream:
                stream.write(copied)
            pins[str(target.resolve())] = sha256(copied).hexdigest()
            originals[str(target.relative_to(output))] = expected
            if copied != payload:
                relocations[str(target.relative_to(output))] = dict(
                    original_sha256=expected, frozen_sha256=sha256(copied).hexdigest(),
                    change="filesystem_literals_only_ast_verified")
    for name in declaration.get("checkout_data", ()):
        path = repository / name
        if path.is_symlink() or not path.resolve().is_relative_to(repository.resolve()):
            raise ValueError("checkout data escaped its declared root")
        payload = path.read_bytes()
        target = checkout / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(payload)
        pins[str(target.resolve())] = sha256(payload).hexdigest()
    manifest = dict(schema=SCHEMA, pins=pins, environment_pins=environment_pins,
        source_commit=source_commit, dirty_status=dirty_status,
        roots=[(str(a), str(b)) for a, b in roots], original_pins=originals,
        relocations=relocations, declaration=declaration,
        limitations=("Local frozen player files; verified shared Python/native environment, "
                     "not an OS sandbox."))
    manifest_path = output / "PLAYER-PACKAGE.json"
    with manifest_path.open("x") as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write("\n")
    verify_pins(pins)
    return manifest_path, sha256(manifest_path.read_bytes()).hexdigest()


def _bind_path_is_relative_to(path, root):
    """Keep native semantics; avoid ancestry allocation for absolute POSIX roots."""
    if type(path) is PosixPath and type(root) is PosixPath and root.is_absolute():
        prefix = root.parts
        return path.parts[:len(prefix)] == prefix
    return path.is_relative_to(root)


def _verify_with_data_cache_release(manifest, root):
    """Hash every pin; relinquish clean data cache after its exact hash matches."""
    if not hasattr(os, "posix_fadvise") or not hasattr(os, "POSIX_FADV_DONTNEED"):
        raise ValueError("verified data cache release is unavailable")
    data = {name: digest for name, digest in manifest["pins"].items()
            if _bind_path_is_relative_to(Path(name), root / "data")}
    verify_pins({**{name: digest for name, digest in manifest["pins"].items()
                   if name not in data}, **manifest["environment_pins"]})
    checked_bytes = 0
    for name, expected in data.items():
        with Path(name).open("rb") as source:
            digest = sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
                checked_bytes += len(block)
            if digest.hexdigest() != expected:
                raise ValueError(f"frozen package pin changed: {name}")
            try:
                os.posix_fadvise(source.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
            except OSError as error:
                raise ValueError("verified data cache release failed") from error
    return dict(data_files=len(data), checked_bytes=checked_bytes,
                every_pin_authenticated=True, file_contents_changed=False)


def bind_player_package(manifest_path, expected_sha256, *, history_output=None):
    """Authenticate all declared files before importing any private backend."""
    global _history_roots, _history_output
    manifest_path = Path(manifest_path).resolve()
    payload = manifest_path.read_bytes()
    if sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("player package manifest changed")
    manifest = json.loads(payload)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unknown player package")
    canonical_paths = []
    for name in manifest["pins"]:
        path = Path(name)
        canonical = path.resolve()
        if path.is_symlink() or not _bind_path_is_relative_to(canonical, manifest_path.parent):
            raise ValueError("frozen package file escaped its directory")
        canonical_paths.append(canonical)
    cache_policy = manifest.get("declaration", {}).get("verified_data_cache_release")
    if cache_policy is None:
        verify_pins({**manifest["pins"], **manifest["environment_pins"]})
    elif cache_policy == "posix_fadvise_dontneed_v1":
        manifest["_verified_data_cache_release"] = _verify_with_data_cache_release(
            manifest, manifest_path.parent)
    else:
        raise ValueError("unknown verified data cache release policy")
    _history_roots = tuple((Path(a), Path(b)) for a, b in manifest["roots"])
    _history_output = None if history_output is None else Path(history_output).resolve()
    return _BoundPlayerPackage(manifest, manifest_path, canonical_paths)


def make_package_read_guard(manifest, *, manifest_path, output, extra_inputs=()):
    """Fail closed on undeclared project reads/writes in a trusted runtime.

    Python/native-library and system roots are explicit trusted environment
    boundaries, not arbitrary project-data permissions or a sandbox claim.
    """
    output = Path(output).resolve()
    originals = tuple(Path(a) for a, _ in manifest["roots"])
    manifest_path = Path(manifest_path).resolve()
    frozen = manifest_path.parent
    if type(manifest) is _BoundPlayerPackage:
        package_paths = manifest.paths_for_guard(manifest_path)
    else:
        package_paths = {Path(name).resolve() for name in manifest["pins"]}
    allowed = set(package_paths)
    allowed.update(Path(name).resolve() for name in
        (*manifest["environment_pins"], str(manifest_path), *extra_inputs))
    reads, writes = set(), set()

    def guard(event, args):
        if event == "subprocess.Popen":
            raise ValueError("frozen player must not spawn a metadata or gameplay subprocess")
        if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        flags = args[2]
        writing = isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR))
        if writing:
            if not path.is_relative_to(output):
                raise ValueError("frozen player attempted a write outside its retained output")
            writes.add(str(path))
            return
        if path.is_relative_to(output) or path in allowed:
            reads.add(str(path))
            return
        # Python/importlib probe optional caches and metadata. No absent file
        # yields dependency bytes; the real open still raises FileNotFoundError.
        # Required inputs already passed the complete pre-launch pin check.
        if not path.exists():
            return
        if path.is_relative_to(frozen):
            if (
                path.parent.name == "__pycache__"
                and path.suffix == ".pyc"
                and any(path.is_relative_to(frozen / root) for root in ("checkout", "helpers"))
            ):
                # Deny unpinned bytes, but let importlib fall back to pinned
                # source. dont_write_bytecode alone still reads old caches.
                raise FileNotFoundError(f"unverified optional Python cache: {path.name}")
            raise ValueError("frozen player attempted an undeclared package read")
        if any(path.is_relative_to(root) for root in originals):
            raise ValueError(
                f"frozen player attempted a mutable project dependency read: {path.name}")
        if any(path.is_relative_to(Path(p).resolve()) for p in
               (sys.base_prefix, "/System/Library", "/usr/share/zoneinfo")):
            return
        if str(path) in {"/dev/null", "/dev/urandom", "/dev/random"}:
            return
        raise ValueError("frozen player attempted an undeclared external dependency read")

    return guard, reads, writes


def package_read_guard(manifest, **kwargs):
    guard, reads, writes = make_package_read_guard(manifest, **kwargs)
    sys.addaudithook(guard)
    return reads, writes


def packaged_backend_identity(manifest):
    return canonical_sha256({name: pin for name, pin in manifest["pins"].items()
        if Path(name).parent.name == "helpers" and name.endswith(".py")})
