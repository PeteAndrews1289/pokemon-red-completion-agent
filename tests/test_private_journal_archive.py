from __future__ import annotations

import gzip
import hashlib
import io
import json
import stat
import tarfile

import private_journal_archive as archive
import pytest

from pokemon_red_completion import private_artifacts as private


@pytest.fixture
def journal(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    root, output = tmp_path / "journal", tmp_path / "archives"
    for path in (repository, root, output):
        path.mkdir(mode=0o700)
    # Test-only separate-device simulation, as in existing sealed-store tests.
    monkeypatch.setattr(private, "_default_device_id", lambda p: 1 if p == repository else 2)
    monkeypatch.setattr(private, "_default_git_worktree_probe", lambda p: False)
    store = private.initialize_private_root(root, repository_root=repository)
    for identifier, success in (("success", True), ("loss", False)):
        store.publish_sealed_record(
            identifier,
            kind="collection_seal",
            record={
                "partition": "train",
                "succeeded": success,
                "actions": 13 if success else 19,
            },
        )
    return root, output, repository, store


def pack(journal):
    root, output, repository, _ = journal
    path = output / "journal.tar.gz"
    result = archive.pack_closed_journal(root, path, repository_root=repository)
    return path, result


def restore(journal, path, sha=None, name="restored"):
    _, output, repository, _ = journal
    target = output / name
    result = archive.restore_closed_journal(
        path,
        target,
        expected_sha256=sha or hashlib.sha256(path.read_bytes()).hexdigest(),
        repository_root=repository,
    )
    return target, result


def rewrite(path, *, mutate_inventory=None, mutate_member=None):
    with tarfile.open(path, "r:gz") as source:
        members = []
        for item in source:
            stream = source.extractfile(item) if item.isreg() else None
            members.append((item, stream.read() if stream is not None else None))
    if mutate_inventory:
        item, payload = members[0]
        value = json.loads(payload)
        mutate_inventory(value)
        payload = archive._canonical(value)
        item.size = len(payload)
        members[0] = item, payload
    if mutate_member:
        mutate_member(members)
    target = path.parent / "bad.tar.gz"
    with tarfile.open(target, "x:gz", format=tarfile.USTAR_FORMAT) as destination:
        for item, payload in members:
            destination.addfile(item, io.BytesIO(payload) if payload is not None else None)
    target.chmod(0o600)
    return target


def test_roundtrip_keeps_originals_modes_times_and_reader_outcomes(journal):
    root, _, repository, original = journal
    before, _ = archive.census_journal(root)
    path, result = pack(journal)
    target, restored = restore(journal, path)
    assert result["inventory_sha256"] == restored["inventory_sha256"]
    assert archive.census_journal(root)[0] == before == archive.census_journal(target)[0]
    reader = private.open_private_root(target, repository_root=repository)
    for name in ("success", "loss"):
        a, b = original.find_sealed_record(name), reader.find_sealed_record(name)
        assert a.read_bytes() == b.read_bytes()
        assert a.summary == b.summary
    assert reader.find_sealed_record("loss").read()["succeeded"] is False


def test_partial_attempt_stays_partial_not_completed(journal):
    root, _, repository, original = journal
    original.begin_episode("interrupted")
    path, _ = pack(journal)
    target, _ = restore(journal, path)
    reader = private.open_private_root(target, repository_root=repository)
    assert original.inspect_episode_state("interrupted").status == "partial"
    assert reader.inspect_episode_state("interrupted").status == "partial"
    with pytest.raises(private.PrivateArtifactError):
        reader.open_episode("interrupted")
    assert (root / "interrupted.partial").is_dir()


def test_failed_attempt_reader_reason_and_streams_are_identical(journal):
    _, _, repository, original = journal
    writer = original.begin_artifact("failed", kind="failure_probe")
    writer.append("header", {"partition": "train"})
    writer.append("trace", {"ordinal": 0, "succeeded": False})
    writer.abort("planned_failure")
    path, _ = pack(journal)
    target, _ = restore(journal, path)
    reader = private.open_private_root(target, repository_root=repository)
    a = original.open_failed_artifact("failed", expected_kind="failure_probe")
    b = reader.open_failed_artifact("failed", expected_kind="failure_probe")
    assert a.summary == b.summary
    assert a.reason_code == b.reason_code == "planned_failure"
    for stream in a.stream_names:
        assert tuple(a.iter_stream(stream)) == tuple(b.iter_stream(stream))


def test_pack_rejects_active_collection(journal):
    _, output, repository, store = journal
    with (
        store.collection_session("active"),
        pytest.raises(archive.JournalArchiveError, match="active collection"),
    ):
        archive.pack_closed_journal(
            journal[0], output / "active.tar.gz", repository_root=repository
        )


def test_pack_rejects_active_typed_writer_even_when_idle(journal):
    _, output, repository, store = journal
    writer = store.begin_artifact("active-writer", kind="failure_probe")
    try:
        with pytest.raises(archive.JournalArchiveError, match="active partial"):
            archive.pack_closed_journal(
                journal[0], output / "active.tar.gz", repository_root=repository
            )
    finally:
        writer.abort("planned_failure")


def test_extended_attributes_are_not_silently_discarded(journal, monkeypatch):
    monkeypatch.setattr(archive, "_has_xattrs", lambda path: True)
    with pytest.raises(archive.JournalArchiveError, match="extended attributes"):
        archive.pack_closed_journal(
            journal[0], journal[1] / "attributes.gz", repository_root=journal[2]
        )


def test_existing_archive_or_restore_destination_is_never_overwritten(journal):
    root, output, repository, _ = journal
    path, _ = pack(journal)
    before = path.read_bytes()
    with pytest.raises(archive.JournalArchiveError):
        archive.pack_closed_journal(root, path, repository_root=repository)
    target = output / "restored"
    target.mkdir(mode=0o700)
    marker = target / "must-remain"
    marker.write_bytes(b"original")
    with pytest.raises(archive.JournalArchiveError):
        restore(journal, path)
    assert path.read_bytes() == before and marker.read_bytes() == b"original"


@pytest.mark.parametrize("target", ("../escape", "/escape", "a/../escape", "a//b", "a\\b"))
def test_unsafe_inventory_path_cannot_escape(journal, target):
    path, _ = pack(journal)
    bad = rewrite(path, mutate_inventory=lambda value: value["entries"][1].update(name=target))
    with pytest.raises(archive.JournalArchiveError):
        restore(journal, bad)
    assert not (journal[1] / "restored").exists()


@pytest.mark.parametrize("type_", (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE))
def test_links_and_special_members_refused(journal, type_):
    path, _ = pack(journal)

    def corrupt(rows):
        item, _ = rows[-1]
        item.type, item.linkname, item.size = type_, "../escape", 0
        rows[-1] = item, None

    bad = rewrite(path, mutate_member=corrupt)
    with pytest.raises(archive.JournalArchiveError):
        restore(journal, bad)
    assert not (journal[1] / "restored").exists()


def test_wrong_digest_refused_before_restoration(journal):
    path, _ = pack(journal)
    with pytest.raises(archive.JournalArchiveError, match="digest differs"):
        restore(journal, path, "0" * 64)
    assert not list(journal[1].glob(".restored.*.partial"))


def test_known_hash_does_not_hide_payload_tampering(journal):
    path, _ = pack(journal)

    def corrupt(rows):
        item, payload = rows[-1]
        rows[-1] = item, b"X" + payload[1:]

    bad = rewrite(path, mutate_member=corrupt)
    with pytest.raises(archive.JournalArchiveError, match="payload digest"):
        restore(journal, bad)
    assert not (journal[1] / "restored").exists()


@pytest.mark.parametrize("cut", (8, 40, 150))
def test_truncated_archive_never_publishes_a_restore(journal, cut):
    path, _ = pack(journal)
    bad = path.parent / "truncated.gz"
    bad.write_bytes(path.read_bytes()[:-cut])
    bad.chmod(0o600)
    with pytest.raises((archive.JournalArchiveError, EOFError, tarfile.TarError, gzip.BadGzipFile)):
        restore(journal, bad)
    assert not (journal[1] / "restored").exists()


def test_mutation_during_pack_retains_partial_and_originals(journal, monkeypatch):
    root, output, repository, _ = journal
    original_read = archive._read_file
    calls = 0

    def changing(path, expected):
        nonlocal calls
        payload = original_read(path, expected)
        calls += 1
        if calls == 6:
            (root / "loss" / "record.json").write_bytes(b"changed\n")
        return payload

    monkeypatch.setattr(archive, "_read_file", changing)
    with pytest.raises(archive.JournalArchiveError):
        archive.pack_closed_journal(root, output / "changing.tar.gz", repository_root=repository)
    assert not (output / "changing.tar.gz").exists()
    assert list(output.glob(".changing.*.partial"))
    assert (root / "loss" / "record.json").read_bytes() == b"changed\n"


def test_unsafe_permissions_and_source_links_fail_closed(journal):
    root, output, repository, _ = journal
    payload = root / "loss" / "record.json"
    payload.chmod(0o644)
    with pytest.raises(archive.JournalArchiveError, match="permissions"):
        archive.pack_closed_journal(root, output / "bad-mode.gz", repository_root=repository)
    payload.chmod(0o600)
    (root / "link").symlink_to(payload)
    with pytest.raises(archive.JournalArchiveError, match="link or special"):
        archive.pack_closed_journal(root, output / "bad-link.gz", repository_root=repository)


def test_overlapping_output_is_refused(journal):
    root, _, repository, _ = journal
    with pytest.raises(archive.JournalArchiveError, match="overlaps"):
        archive.pack_closed_journal(root, root / "journal.gz", repository_root=repository)


def test_private_archive_permissions_and_size_bound(journal, monkeypatch):
    path, _ = pack(journal)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    monkeypatch.setattr(archive, "MAX_ENTRIES", 1)
    with pytest.raises(archive.JournalArchiveError, match="bound"):
        restore(journal, path)


def test_missing_or_duplicate_declared_members_are_rejected(journal):
    path, _ = pack(journal)
    bad = rewrite(
        path, mutate_inventory=lambda value: value["entries"].append(value["entries"][-1])
    )
    with pytest.raises(archive.JournalArchiveError):
        restore(journal, bad)


def test_nonzero_content_in_tar_end_padding_is_not_ignored(journal):
    path, _ = pack(journal)
    with tarfile.open(path, "r:gz") as stream:
        end = sum(512 + ((member.size + 511) // 512) * 512 for member in stream)
    data = bytearray(gzip.decompress(path.read_bytes()))
    data[end + 1024 : end + 1028] = b"junk"
    bad = path.parent / "bad-padding.gz"
    bad.write_bytes(gzip.compress(data, mtime=0))
    bad.chmod(0o600)
    with pytest.raises(archive.JournalArchiveError, match="trailing"):
        restore(journal, bad)
    assert not (journal[1] / "restored").exists()


def test_invalid_sealed_record_is_preserved_as_invalid(journal):
    root, _, repository, original = journal
    payload = root / "loss" / "record.json"
    payload.write_bytes(b'{"actions":20,"partition":"train","succeeded":false}\n')
    path, _ = pack(journal)
    target, _ = restore(journal, path)
    reader = private.open_private_root(target, repository_root=repository)
    errors = []
    for store in (original, reader):
        with pytest.raises(private.PrivateArtifactError) as caught:
            store.find_sealed_record("loss")
        errors.append(str(caught.value))
    assert errors[0] == errors[1]
    assert (target / "loss/record.json").read_bytes() == payload.read_bytes()


def test_restore_publication_race_keeps_existing_target_and_partial(journal, monkeypatch):
    path, _ = pack(journal)
    old_rename = private._rename_no_replace
    target = journal[1] / "restored"

    def collide(source, destination):
        if destination == target:
            target.mkdir(mode=0o700)
            (target / "keep").write_bytes(b"existing")
        return old_rename(source, destination)

    monkeypatch.setattr(private, "_rename_no_replace", collide)
    with pytest.raises((FileExistsError, private.PrivateArtifactError)):
        restore(journal, path)
    assert (target / "keep").read_bytes() == b"existing"
    assert list(journal[1].glob(".restored.*.partial"))
