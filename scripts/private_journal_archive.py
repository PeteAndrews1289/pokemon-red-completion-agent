"""Lossless offline packing only; the live sealed-store reader is unchanged.

Archives contain an authenticated inventory and ordinary relative tar members.
Restoration is exclusive, staged and never extracts over an existing journal.
Incomplete outputs remain visibly partial. There is deliberately no delete API.
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import uuid
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

from pokemon_red_completion import private_artifacts as private

SCHEMA = "pokemon.closed-journal-archive.v1"
INVENTORY_NAME = "JOURNAL-INVENTORY.json"
MAX_ENTRIES = 100_000
MAX_BYTES = 2 * 1024**3
MAX_FILE_BYTES = 128 * 1024**2
MAX_INVENTORY_BYTES = 32 * 1024**2
_ATOM = re.compile(r"[a-zA-Z0-9._-]{1,100}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
if sys.platform == "darwin":
    _darwin_listxattr = ctypes.CDLL(None, use_errno=True).listxattr
    _darwin_listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    _darwin_listxattr.restype = ctypes.c_ssize_t


class JournalArchiveError(RuntimeError):
    """A closed journal or archive could not be preserved safely."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _relative(name):
    if not isinstance(name, str) or len(name) > 240:
        raise JournalArchiveError("archive relative name is invalid")
    if name == "":
        return
    parts = name.split("/")
    if len(parts) > 8 or any(p in {"", ".", ".."} or not _ATOM.fullmatch(p) for p in parts):
        raise JournalArchiveError("archive relative name is unsafe")
    if str(PurePosixPath(name)) != name:
        raise JournalArchiveError("archive name is not canonical")


def _fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _has_xattrs(path):
    if sys.platform == "darwin":
        # Darwin's installed listxattr(2): XATTR_NOFOLLOW=1; a NULL buffer probes size.
        count = _darwin_listxattr(os.fsencode(path), None, 0, 1)
        if count < 0:
            raise JournalArchiveError("unable to inspect journal extended attributes")
        return count > 0
    if not hasattr(os, "listxattr"):
        raise JournalArchiveError("extended attribute inspection is unavailable")
    return bool(os.listxattr(path, follow_symlinks=False))


def _read_file(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        initial = os.fstat(stream.fileno())
        if _fingerprint(initial) != _fingerprint(expected):
            raise JournalArchiveError("source file changed before reading")
        payload = stream.read(MAX_FILE_BYTES + 1)
        if len(payload) > MAX_FILE_BYTES or _fingerprint(os.fstat(stream.fileno())) != _fingerprint(
            initial
        ):
            raise JournalArchiveError("source file exceeds bounds or changed during reading")
    if _fingerprint(path.lstat()) != _fingerprint(expected):
        raise JournalArchiveError("source file changed after reading")
    return payload


def census_journal(root):
    """Hash every entry without following links; include private modes and nanosecond mtime."""
    root = Path(root)
    entries, states, total = [], {}, 0
    pending = [root]
    while pending:
        path = pending.pop()
        name = path.relative_to(root).as_posix() if path != root else ""
        _relative(name)
        before = path.lstat()
        if stat.S_ISDIR(before.st_mode):
            kind, mode = "directory", 0o700
            pending.extend(sorted((Path(e.path) for e in os.scandir(path)), reverse=True))
            payload = None
        elif stat.S_ISREG(before.st_mode):
            kind, mode = "file", 0o600
            if before.st_size > MAX_FILE_BYTES:
                raise JournalArchiveError("journal file exceeds the pilot bound")
            payload = _read_file(path, before)
            total += len(payload)
        else:
            raise JournalArchiveError("journal contains a link or special file")
        if stat.S_IMODE(before.st_mode) != mode:
            raise JournalArchiveError("journal permissions are not private")
        if _has_xattrs(path):
            # This pilot promises no silent loss of attributes it cannot restore.
            raise JournalArchiveError("journal extended attributes require a broader archive")
        if _fingerprint(path.lstat()) != _fingerprint(before):
            raise JournalArchiveError("journal entry changed during inventory")
        item = dict(name=name, kind=kind, mode=mode, mtime_ns=str(before.st_mtime_ns))
        if payload is not None:
            item.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        entries.append(item)
        states[name] = before
        if len(entries) > MAX_ENTRIES or total > MAX_BYTES:
            raise JournalArchiveError("journal exceeds the closed-pilot bound")
    entries.sort(key=lambda row: row["name"])
    inventory = dict(
        schema=SCHEMA,
        entries=entries,
        files=sum(e["kind"] == "file" for e in entries),
        file_bytes=total,
    )
    encoded = _canonical(inventory)
    if len(encoded) > MAX_INVENTORY_BYTES:
        raise JournalArchiveError("journal inventory exceeds its bound")
    return inventory, states


def _private_parent(path, repository_root):
    path = Path(path)
    if not path.is_absolute() or path.name in {"", ".", ".."} or ".." in path.parts:
        raise JournalArchiveError("output must be an explicit new leaf")
    private._validate_root_location(
        path.parent,
        repository_root=repository_root,
        allow_same_device=False,
        device_id=private._default_device_id,
        git_worktree_probe=private._default_git_worktree_probe,
    )
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise JournalArchiveError("output parent permissions are not private")
    return path


def _tar_entry(name, mode, *, directory=False, size=0):
    member = tarfile.TarInfo(name)
    member.mode, member.size = mode, size
    member.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    member.mtime = 0  # exact mtime lives in the authenticated inventory, not a float header
    return member


def pack_closed_journal(root, archive, *, repository_root):
    root = Path(root)
    store = private.open_private_root(root, repository_root=repository_root)
    root = store._root
    archive = _private_parent(archive, repository_root)
    if archive.is_relative_to(root) or root.is_relative_to(archive.parent):
        raise JournalArchiveError("archive output overlaps its source")
    if os.path.lexists(archive):
        raise JournalArchiveError("archive output already exists")
    partial = archive.with_name(f".{archive.name}.{uuid.uuid4().hex}.partial")
    with ExitStack() as stack:
        # Hold all existing collection locks. A new unrelated writer is additionally
        # detected by the final complete census; no lock files are created or edited.
        for lock in sorted(root.glob(".collection-*.lock")):
            descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
            stack.callback(os.close, descriptor)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise JournalArchiveError("journal has an active collection") from None
        for attempt in sorted(root.glob("*.partial")):
            if stat.S_ISDIR(attempt.lstat().st_mode):
                try:
                    descriptor = private._lock_private_artifact_directory(attempt, nonblocking=True)
                except private.PrivateArtifactError:
                    raise JournalArchiveError("journal has an active partial artifact") from None
                stack.callback(os.close, descriptor)
        before, states = census_journal(root)
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as raw:
            with (
                gzip.GzipFile(
                    fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=6
                ) as zipped,
                tarfile.open(fileobj=zipped, mode="w|", format=tarfile.USTAR_FORMAT) as bundle,
            ):
                payload = _canonical(before)
                bundle.addfile(
                    _tar_entry(INVENTORY_NAME, 0o600, size=len(payload)), io.BytesIO(payload)
                )
                for item in before["entries"]:
                    name = "data" + ("/" + item["name"] if item["name"] else "")
                    directory = item["kind"] == "directory"
                    payload = (
                        None if directory else _read_file(root / item["name"], states[item["name"]])
                    )
                    if (
                        payload is not None
                        and hashlib.sha256(payload).hexdigest() != item["sha256"]
                    ):
                        raise JournalArchiveError("journal bytes changed during packing")
                    bundle.addfile(
                        _tar_entry(
                            name,
                            item["mode"],
                            directory=directory,
                            size=0 if directory else len(payload),
                        ),
                        None if directory else io.BytesIO(payload),
                    )
            raw.flush()
            os.fsync(raw.fileno())
        store._revalidate()
        after, final_states = census_journal(root)
        if before != after or any(
            _fingerprint(states[k]) != _fingerprint(final_states[k]) for k in states
        ):
            raise JournalArchiveError("closed journal changed during packing")
        private._rename_no_replace(partial, archive)
        private._fsync_directory(archive.parent)
    return dict(
        schema=SCHEMA,
        archive_sha256=_digest_file(archive),
        inventory_sha256=hashlib.sha256(_canonical(before)).hexdigest(),
        entries=len(before["entries"]),
        files=before["files"],
        file_bytes=before["file_bytes"],
        source_allocated_file_bytes=sum(
            s.st_blocks * 512 for s in states.values() if stat.S_ISREG(s.st_mode)
        ),
        source_shared_link_files=sum(
            s.st_nlink > 1 for s in states.values() if stat.S_ISREG(s.st_mode)
        ),
        archive_bytes=archive.stat().st_size,
        archive_allocated_bytes=archive.stat().st_blocks * 512,
    )


def _inventory(payload):
    document = json.loads(payload)
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "entries",
        "files",
        "file_bytes",
    }:
        raise JournalArchiveError("archive inventory fields differ")
    if document["schema"] != SCHEMA or not isinstance(document["entries"], list):
        raise JournalArchiveError("archive inventory schema differs")
    rows = document["entries"]
    if not rows or len(rows) > MAX_ENTRIES or _canonical(document) != payload:
        raise JournalArchiveError("archive inventory is unbounded or noncanonical")
    names, directories, total, files = set(), set(), 0, 0
    for row in rows:
        if not isinstance(row, dict):
            raise JournalArchiveError("archive entry is not an object")
        name = row.get("name")
        _relative(name)
        expected = {"name", "kind", "mode", "mtime_ns"}
        if row.get("kind") == "file":
            expected |= {"bytes", "sha256"}
            size = row.get("bytes")
            if (
                type(size) is not int
                or not 0 <= size <= MAX_FILE_BYTES
                or not _SHA.fullmatch(str(row.get("sha256")))
            ):
                raise JournalArchiveError("archive file bounds differ")
            files, total = files + 1, total + size
        elif row.get("kind") != "directory":
            raise JournalArchiveError("archive contains an unsupported entry kind")
        mode = 0o600 if row["kind"] == "file" else 0o700
        timestamp = row.get("mtime_ns")
        if (
            set(row) != expected
            or type(row.get("mode")) is not int
            or row["mode"] != mode
            or not isinstance(timestamp, str)
            or not re.fullmatch(r"[0-9]{1,20}", timestamp)
            or name in names
        ):
            raise JournalArchiveError("archive metadata differs")
        if name:
            parent = str(PurePosixPath(name).parent)
            if ("" if parent == "." else parent) not in directories:
                raise JournalArchiveError("archive parent is missing or not a directory")
        elif row["kind"] != "directory":
            raise JournalArchiveError("archive root is not a directory")
        names.add(name)
        if row["kind"] == "directory":
            directories.add(name)
    if (
        rows != sorted(rows, key=lambda r: r["name"])
        or rows[0]["name"] != ""
        or type(document["files"]) is not int
        or document["files"] != files
        or type(document["file_bytes"]) is not int
        or document["file_bytes"] != total
        or total > MAX_BYTES
    ):
        raise JournalArchiveError("archive inventory totals differ")
    return document


def _tar_content_bytes(inventory):
    sizes = [len(_canonical(inventory)), *(row.get("bytes", 0) for row in inventory["entries"])]
    return sum(512 + ((size + 511) // 512) * 512 for size in sizes)


def restore_closed_journal(archive, destination, *, expected_sha256, repository_root):
    archive = Path(archive)
    destination = _private_parent(destination, repository_root)
    if not _SHA.fullmatch(str(expected_sha256)) or os.path.lexists(destination):
        raise JournalArchiveError("restore identity is invalid or destination exists")
    private._ensure_no_symlink_components(archive)
    fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW)
    partial = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
    with os.fdopen(fd, "rb") as raw:
        initial = os.fstat(raw.fileno())
        if not stat.S_ISREG(initial.st_mode) or stat.S_IMODE(initial.st_mode) != 0o600:
            raise JournalArchiveError("archive is not a private regular file")
        digest = hashlib.sha256()
        while block := raw.read(1024 * 1024):
            digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise JournalArchiveError("archive digest differs")
        raw.seek(0)
        with (
            gzip.GzipFile(fileobj=raw, mode="rb") as zipped,
            tarfile.open(fileobj=zipped, mode="r|") as bundle,
        ):
            first = bundle.next()
            if (
                first is None
                or first.name != INVENTORY_NAME
                or not first.isreg()
                or first.size > MAX_INVENTORY_BYTES
                or first.mode != 0o600
            ):
                raise JournalArchiveError("archive inventory member differs")
            source = bundle.extractfile(first)
            assert source is not None
            inventory = _inventory(source.read(MAX_INVENTORY_BYTES + 1))
            os.mkdir(partial, 0o700)
            for row in inventory["entries"]:
                member = bundle.next()
                name = "data" + ("/" + row["name"] if row["name"] else "")
                directory = row["kind"] == "directory"
                if (
                    member is None
                    or member.name != name
                    or member.mode != row["mode"]
                    or (not member.isdir() if directory else not member.isreg())
                    or member.size != (0 if directory else row["bytes"])
                    or member.linkname
                    or member.pax_headers
                    or member.sparse is not None
                ):
                    raise JournalArchiveError("archive member differs from its inventory")
                target = partial / row["name"]
                if directory:
                    if row["name"]:
                        os.mkdir(target, 0o700)
                else:
                    source = bundle.extractfile(member)
                    assert source is not None
                    payload = source.read(MAX_FILE_BYTES + 1)
                    if (
                        len(payload) != row["bytes"]
                        or hashlib.sha256(payload).hexdigest() != row["sha256"]
                    ):
                        raise JournalArchiveError("restored payload digest differs")
                    output_fd = os.open(
                        target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    with os.fdopen(output_fd, "wb") as output:
                        output.write(payload)
                        output.flush()
                        os.fsync(output.fileno())
                    os.utime(target, ns=(int(row["mtime_ns"]), int(row["mtime_ns"])))
            if bundle.next() is not None:
                raise JournalArchiveError("archive contains undeclared members")
            # Read through tar's buffered stream, not directly from gzip: the
            # tar buffer can already hold undeclared bytes behind the end marker.
            content_bytes = _tar_content_bytes(inventory)
            padded_bytes = ((content_bytes + 1024 + 10239) // 10240) * 10240
            consumed = bundle.fileobj.tell()
            if consumed != content_bytes + 512:
                raise JournalArchiveError("archive has unexpected trailing layout")
            remaining = padded_bytes - consumed
            tail = bundle.fileobj.read(remaining + 1)
            if len(tail) != remaining or any(tail):
                raise JournalArchiveError("archive has unexpected trailing content")
        if _fingerprint(os.fstat(raw.fileno())) != _fingerprint(initial):
            raise JournalArchiveError("archive changed while restoring")
    for row in reversed(inventory["entries"]):
        if row["kind"] == "directory":
            os.utime(partial / row["name"], ns=(int(row["mtime_ns"]), int(row["mtime_ns"])))
            private._fsync_directory(partial / row["name"])
    restored, _ = census_journal(partial)
    if restored != inventory:
        raise JournalArchiveError("restored journal differs from the inventory")
    private.open_private_root(partial, repository_root=repository_root)
    private._rename_no_replace(partial, destination)
    private._fsync_directory(destination.parent)
    return dict(
        schema=SCHEMA,
        archive_sha256=expected_sha256,
        files=inventory["files"],
        entries=len(inventory["entries"]),
        file_bytes=inventory["file_bytes"],
        inventory_sha256=hashlib.sha256(_canonical(inventory)).hexdigest(),
        restored=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pack", "restore"))
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.mode == "pack":
        if args.journal is None:
            parser.error("pack requires --journal")
        result = pack_closed_journal(args.journal, args.archive, repository_root=args.repository)
    else:
        if args.destination is None or args.sha256 is None:
            parser.error("restore requires --destination and --sha256")
        result = restore_closed_journal(
            args.archive,
            args.destination,
            expected_sha256=args.sha256,
            repository_root=args.repository,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
