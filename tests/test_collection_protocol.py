from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion import collection_protocol as collection_protocol_module
from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.collection_protocol import (
    BATTLE_START_SCHEDULE_SCHEMA,
    COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH,
    COLLECTION_REGISTRY_RELATIVE_PATH,
    SCHEDULE_DRY_RUN_SEED,
    CollectionProtocolError,
    collection_document_sha256,
    committed_source_bundle_sha256,
    load_committed_collection_registry,
    parse_collection_registry,
    working_source_bundle_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / COLLECTION_REGISTRY_RELATIVE_PATH
DIGEST_PATH = PROJECT_ROOT / COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH


def _document() -> dict[str, object]:
    value = json.loads(REGISTRY_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def _canonical(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _runs(document: dict[str, object]) -> list[dict[str, object]]:
    runs = document["runs"]
    assert isinstance(runs, list)
    assert all(isinstance(run, dict) for run in runs)
    return runs


def _schedule(document: dict[str, object]) -> dict[str, object]:
    schedule = document["schedule"]
    assert isinstance(schedule, dict)
    return schedule


def _commit(repository: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Collection Test",
            "-c",
            "user.email=collection@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            message,
        ],
        cwd=repository,
        check=True,
    )


def _committed_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", repository / "pyproject.toml")
    shutil.copytree(
        PROJECT_ROOT / "src",
        repository / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for relative_path in (
        COLLECTION_REGISTRY_RELATIVE_PATH,
        COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH,
    ):
        target = repository / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, target)
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    _commit(repository, "freeze collection")
    return repository


def test_tracked_registry_is_canonical_frozen_and_preassigned() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_collection_registry(payload)

    assert payload == _canonical(_document())
    assert registry.registry_sha256 == hashlib.sha256(payload).hexdigest()
    assert registry.partition_counts == {"test": 5, "train": 5, "validation": 2}
    assert len(registry.runs) == 12
    sidecar = json.loads(DIGEST_PATH.read_text(encoding="ascii"))
    assert sidecar["bytes"] == len(payload)
    assert sidecar["sha256"] == hashlib.sha256(payload).hexdigest()
    assert registry.schedule.battle_plan_ids == RED_BATTLE_PLAN_IDS
    assert len(registry.schedule.battle_plan_ids) == 74
    assert len({run.harness_seed for run in registry.runs}) == 12
    assert len({run.schedule_sha256 for run in registry.runs}) == 12
    assert registry.schedule_dry_run.harness_seed not in {run.harness_seed for run in registry.runs}
    assert registry.schedule_dry_run.schedule_sha256 not in {
        run.schedule_sha256 for run in registry.runs
    }
    assert (
        registry.schedule.battle_roster_sha256
        == "21f14864555f34e5eb45cdcb6b3c1019a7b4518e719d48e2253f396d6b16effc"
    )
    assert (
        registry.schedule_dry_run.schedule_sha256
        == "8f74fcc50610702ace7f44b3ed3b44409f38cba96d6fe195ef2ae2c497adbf67"
    )


def test_final_campaign_identity_has_public_golden_values() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_collection_registry(payload)
    first = registry.assignment("red-battle-v95-01-train")

    assert len(payload) == 7000
    assert (
        registry.registry_sha256
        == "9386a1fcd7bfcd8e1d787f41ecd6ebdbb25f2b224730572dcfef5fe85a551142"
    )
    assert (
        registry.execution.source_bundle_sha256
        == "671be589d60cffb382a74897da5c39630d2e361cccf07226e2ae8455e9d7065b"
    )
    assert (
        registry.execution.behavior_configuration_sha256
        == "bdca346b2cbb97cf43d79a8cf7f0d8eab90dacfb6610bb5c2f97028435f985b8"
    )
    assert (
        registry.execution.objective_graph_sha256
        == "d86fd746901dae2806de025b6ccc721794750c7bffa1c761b0e2a79dabdca3de"
    )
    assert (
        registry.execution.teacher_execution_sha256
        == "9debc4eb942d32559f20cac9bc2ab6f769a372aef9cca1eceb7681521d21f2b8"
    )
    assert first.assignment_id == "3bc2597d578a5e1e4417421fd24d299cb95b3ddc83b0c3d2943303cadbc987b5"


def test_canonical_newline_hash_has_an_independent_golden_vector() -> None:
    assert (
        collection_document_sha256({"b": 2, "a": 1})
        == "e8d38819d39f705646bfb643368eca78f7db476c16471dbc33b941b27326410d"
    )


def test_schedule_expansion_is_deterministic_bounded_and_content_addressed() -> None:
    registry = parse_collection_registry(REGISTRY_PATH.read_bytes())
    run = registry.run("red-battle-v95-01-train")

    first = registry.schedule.offsets(run.harness_seed)
    second = registry.schedule.offsets(run.harness_seed)

    assert first == second
    assert len(first) == 74
    assert first[0].battle_plan_id == RED_BATTLE_PLAN_IDS[0]
    assert first[0].frames == 40
    assert first[-1].battle_plan_id == RED_BATTLE_PLAN_IDS[-1]
    assert first[-1].frames == 190
    assert all(0 <= offset.frames <= 255 for offset in first)
    assert run.schedule_sha256 == "6e37dcb8a759c7dc3b76ee643b97b368359d51807f875231124c4bfc84ff8ec6"
    assert registry.schedule.schedule_sha256(run.harness_seed) == run.schedule_sha256
    assert registry.schedule.schedule_sha256(registry.runs[1].harness_seed) != run.schedule_sha256


def test_assignment_ids_are_stable_collision_safe_and_path_free() -> None:
    registry = parse_collection_registry(REGISTRY_PATH.read_bytes())
    first = registry.assignment("red-battle-v95-01-train")
    repeated = registry.assignment("red-battle-v95-01-train")

    assert first == repeated
    assert first.assignment_id == collection_document_sha256(
        {
            "collection_id": registry.collection_id,
            "harness_seed": first.harness_seed,
            "partition": first.partition,
            "registry_sha256": registry.registry_sha256,
            "run_id": first.run_id,
            "schedule_sha256": first.schedule_sha256,
            "schema": "pokemon-red-collection-assignment-v1",
            "teacher_execution_sha256": (registry.execution.teacher_execution_sha256),
        }
    )
    assert first.root_lineage_id == f"red-root-{first.assignment_id}"
    assert first.episode_id == f"red-teacher-{first.assignment_id}"
    assert len(first.episode_id) == 76
    assert first.collection_slot_ordinal == 1
    assert first.declared_collection_slots == 12
    assert first.partition_slot_ordinal == 1
    assert first.declared_partition_slots == 5
    assert len({registry.assignment(run.run_id).assignment_id for run in registry.runs}) == 12
    assert len({registry.assignment(run.run_id).episode_id for run in registry.runs}) == 12

    metadata = first.metadata_dict()
    assert metadata["harness_seed"] == 1590001
    assert metadata["run_id"] == "red-battle-v95-01-train"
    assert metadata["attempt"] == {"attempts_per_slot": 1, "counted": True}
    assert metadata["collection_slot"] == {
        "collection_ordinal": 1,
        "collection_total": 12,
        "partition_ordinal": 1,
        "partition_total": 5,
    }
    assert metadata["split"] == {
        "partition": "train",
        "regime": "within_game",
        "root_lineage_id": first.root_lineage_id,
    }
    assert "offsets" not in metadata
    assert "/" not in json.dumps(metadata, sort_keys=True)

    first_test = registry.assignment("red-battle-v95-08-test")
    assert first_test.collection_slot_ordinal == 8
    assert first_test.partition_slot_ordinal == 1
    assert first_test.declared_partition_slots == 5


def test_parser_requires_bytes_and_exact_canonical_json() -> None:
    payload = REGISTRY_PATH.read_bytes()
    with pytest.raises(TypeError, match="must be bytes"):
        parse_collection_registry(payload.decode("ascii"))  # type: ignore[arg-type]

    document = _document()
    pretty = json.dumps(document, indent=2, sort_keys=True).encode("ascii")
    with pytest.raises(CollectionProtocolError, match="not canonical"):
        parse_collection_registry(pretty)

    with pytest.raises(CollectionProtocolError, match="duplicate JSON keys"):
        parse_collection_registry(b'{"schema":"one","schema":"two"}\n')

    with pytest.raises(CollectionProtocolError, match="canonical ASCII"):
        parse_collection_registry(b'{"schema":"\xff"}\n')


@pytest.mark.parametrize(
    ("battle_plan_id", "frames"),
    (
        ("unsafe/plan", 1),
        ("battle-001-test", -1),
        ("battle-001-test", 256),
        ("battle-001-test", True),
    ),
)
def test_battle_start_offsets_reject_unsafe_or_out_of_range_values(
    battle_plan_id: str,
    frames: object,
) -> None:
    from pokemon_red_completion.collection_protocol import BattleStartOffset

    with pytest.raises(CollectionProtocolError):
        BattleStartOffset(battle_plan_id, frames)  # type: ignore[arg-type]


def test_parser_sanitizes_excessively_nested_json() -> None:
    payload = (b'{"a":' * 100_000) + b"0" + (b"}" * 100_000) + b"\n"

    with pytest.raises(
        CollectionProtocolError,
        match="not valid JSON|cannot be encoded",
    ):
        parse_collection_registry(payload)


def test_parser_rejects_extra_or_missing_schema_keys() -> None:
    extra = _document()
    extra["outcomes"] = []
    with pytest.raises(CollectionProtocolError, match="keys do not match"):
        parse_collection_registry(_canonical(extra))

    missing = _document()
    del missing["policy"]
    with pytest.raises(CollectionProtocolError, match="keys do not match"):
        parse_collection_registry(_canonical(missing))

    nested = _document()
    _schedule(nested)["offset_source"] = "mutable"
    with pytest.raises(CollectionProtocolError, match="keys do not match"):
        parse_collection_registry(_canonical(nested))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("harness_seed", True, "unsigned 64-bit"),
        ("harness_seed", -1, "unsigned 64-bit"),
        ("harness_seed", 1 << 64, "unsigned 64-bit"),
        ("partition", "holdout", "partition is unsupported"),
        ("schedule_sha256", "A" * 64, "lowercase SHA-256"),
    ],
)
def test_parser_rejects_invalid_run_field_types_and_values(
    field: str,
    value: object,
    message: str,
) -> None:
    document = _document()
    _runs(document)[0][field] = value

    with pytest.raises(CollectionProtocolError, match=message):
        parse_collection_registry(_canonical(document))


def test_parser_rejects_unsafe_ids_without_echoing_them() -> None:
    document = _document()
    sensitive = "/Users/example/private/run"
    _runs(document)[0]["run_id"] = sensitive

    with pytest.raises(CollectionProtocolError) as error:
        parse_collection_registry(_canonical(document))

    assert sensitive not in str(error.value)
    assert "/Users/" not in str(error.value)

    registry = parse_collection_registry(REGISTRY_PATH.read_bytes())
    with pytest.raises(CollectionProtocolError) as lookup_error:
        registry.assignment(sensitive)
    assert sensitive not in str(lookup_error.value)


def test_parser_rejects_roster_size_order_duplicates_and_digest_mismatch() -> None:
    too_short = _document()
    roster = _schedule(too_short)["battle_plan_ids"]
    assert isinstance(roster, list)
    roster.pop()
    with pytest.raises(CollectionProtocolError, match="qualified route plan"):
        parse_collection_registry(_canonical(too_short))

    duplicate = _document()
    duplicate_roster = _schedule(duplicate)["battle_plan_ids"]
    assert isinstance(duplicate_roster, list)
    duplicate_roster[-1] = duplicate_roster[-2]
    with pytest.raises(CollectionProtocolError, match="qualified route plan"):
        parse_collection_registry(_canonical(duplicate))

    unsorted = _document()
    unsorted_roster = _schedule(unsorted)["battle_plan_ids"]
    assert isinstance(unsorted_roster, list)
    unsorted_roster[0], unsorted_roster[1] = unsorted_roster[1], unsorted_roster[0]
    with pytest.raises(CollectionProtocolError, match="qualified route plan"):
        parse_collection_registry(_canonical(unsorted))

    mismatched = _document()
    _schedule(mismatched)["battle_roster_sha256"] = "0" * 64
    with pytest.raises(CollectionProtocolError, match="does not match"):
        parse_collection_registry(_canonical(mismatched))


def test_parser_rejects_schedule_schema_limits_and_seed_checksum_mismatch() -> None:
    schema = _document()
    _schedule(schema)["schema"] = "pokemon-red-battle-start-offset-v2"
    with pytest.raises(CollectionProtocolError, match="schema is unsupported"):
        parse_collection_registry(_canonical(schema))

    maximum = _document()
    _schedule(maximum)["max_offset_frames"] = 256
    with pytest.raises(CollectionProtocolError, match="maximum offset is unsupported"):
        parse_collection_registry(_canonical(maximum))

    mismatch = _document()
    _runs(mismatch)[0]["harness_seed"] = 9999
    with pytest.raises(CollectionProtocolError, match="does not match its harness seed"):
        parse_collection_registry(_canonical(mismatch))


def test_parser_rejects_duplicate_run_seed_schedule_and_partition_counts() -> None:
    duplicate_id = _document()
    duplicate_id_runs = _runs(duplicate_id)
    duplicate_id_runs[1]["run_id"] = duplicate_id_runs[0]["run_id"]
    with pytest.raises(CollectionProtocolError, match="identities must be unique"):
        parse_collection_registry(_canonical(duplicate_id))

    duplicate_seed = _document()
    duplicate_seed_runs = _runs(duplicate_seed)
    duplicate_seed_runs[1]["harness_seed"] = duplicate_seed_runs[0]["harness_seed"]
    duplicate_seed_runs[1]["schedule_sha256"] = duplicate_seed_runs[0]["schedule_sha256"]
    with pytest.raises(CollectionProtocolError, match="harness seeds must be unique"):
        parse_collection_registry(_canonical(duplicate_seed))

    wrong_counts = _document()
    wrong_count_runs = _runs(wrong_counts)
    wrong_count_runs[4]["partition"] = "validation"
    with pytest.raises(CollectionProtocolError, match="partition counts"):
        parse_collection_registry(_canonical(wrong_counts))


def test_every_partition_has_disjoint_seeds_and_schedule_hashes() -> None:
    registry = parse_collection_registry(REGISTRY_PATH.read_bytes())
    for left in ("train", "validation", "test"):
        for right in ("train", "validation", "test"):
            if left >= right:
                continue
            left_runs = [run for run in registry.runs if run.partition == left]
            right_runs = [run for run in registry.runs if run.partition == right]
            assert {run.harness_seed for run in left_runs}.isdisjoint(
                run.harness_seed for run in right_runs
            )
            assert {run.schedule_sha256 for run in left_runs}.isdisjoint(
                run.schedule_sha256 for run in right_runs
            )


def test_parser_requires_the_fixed_disjoint_dry_run_seed() -> None:
    document = _document()
    dry_run = document["schedule_dry_run"]
    assert isinstance(dry_run, dict)
    registry = parse_collection_registry(REGISTRY_PATH.read_bytes())
    alternate_seed = SCHEDULE_DRY_RUN_SEED + 1
    dry_run["harness_seed"] = alternate_seed
    dry_run["schedule_sha256"] = registry.schedule.schedule_sha256(alternate_seed)

    with pytest.raises(CollectionProtocolError, match="harness seed is unsupported"):
        parse_collection_registry(_canonical(document))


def test_committed_loader_reads_head_not_a_modified_working_file(tmp_path: Path) -> None:
    repository = _committed_repository(tmp_path)
    target = repository / COLLECTION_REGISTRY_RELATIVE_PATH

    target.write_bytes(b"working tree tampering")
    registry = load_committed_collection_registry(repository)

    assert registry.registry_sha256 == hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    assert registry.partition_counts == {"test": 5, "train": 5, "validation": 2}
    assert committed_source_bundle_sha256(repository) == working_source_bundle_sha256(PROJECT_ROOT)


def test_committed_loader_rejects_a_valid_but_different_registry_digest(
    tmp_path: Path,
) -> None:
    repository = _committed_repository(tmp_path)
    changed = _document()
    _runs(changed)[0]["run_id"] = "red-battle-v95-00-train"
    payload = _canonical(changed)
    assert (
        parse_collection_registry(payload).registry_sha256
        != hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    )
    (repository / COLLECTION_REGISTRY_RELATIVE_PATH).write_bytes(payload)
    _commit(repository, "tamper registry without sidecar")

    with pytest.raises(CollectionProtocolError, match="digest is not frozen"):
        load_committed_collection_registry(repository)


def test_committed_loader_authenticates_bytes_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _committed_repository(tmp_path)
    payload = (b"[" * 2_000) + b"0" + (b"]" * 2_000) + b"\n"
    (repository / COLLECTION_REGISTRY_RELATIVE_PATH).write_bytes(payload)
    _commit(repository, "commit unauthenticated bytes")
    monkeypatch.setattr(
        collection_protocol_module,
        "parse_collection_registry",
        lambda _payload: pytest.fail("unauthenticated registry bytes were parsed"),
    )

    with pytest.raises(CollectionProtocolError, match="digest is not frozen"):
        load_committed_collection_registry(repository)


def test_committed_loader_rejects_executable_changes_but_accepts_docs_only_commit(
    tmp_path: Path,
) -> None:
    repository = _committed_repository(tmp_path)
    (repository / "README.md").write_text("documentation only\n", encoding="utf-8")
    _commit(repository, "docs only")
    assert load_committed_collection_registry(repository).partition_counts == {
        "test": 5,
        "train": 5,
        "validation": 2,
    }

    source = repository / "src" / "pokemon_red_completion" / "__init__.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    _commit(repository, "change executable")
    with pytest.raises(CollectionProtocolError, match="executable source"):
        load_committed_collection_registry(repository)


def test_committed_loader_errors_are_path_free(tmp_path: Path) -> None:
    private_location = tmp_path / "private" / "repository"

    with pytest.raises(CollectionProtocolError) as error:
        load_committed_collection_registry(private_location)

    assert str(private_location) not in str(error.value)
    assert "unavailable" in str(error.value)


def test_collection_git_reads_ignore_repository_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _committed_repository(tmp_path)
    trusted_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=other, check=True)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(other))

    payload = collection_protocol_module._run_git(
        repository,
        ["rev-parse", "HEAD"],
        subject="test source identity",
        maximum_output_bytes=4096,
    )

    assert payload.decode("ascii").strip() == trusted_commit


def test_committed_loader_rejects_source_mode_changes(tmp_path: Path) -> None:
    repository = _committed_repository(tmp_path)
    source = repository / "src" / "pokemon_red_completion" / "__init__.py"
    source.chmod(0o755)
    subprocess.run(
        ["git", "update-index", "--chmod=+x", str(source.relative_to(repository))],
        cwd=repository,
        check=True,
    )
    _commit(repository, "change executable mode")

    with pytest.raises(CollectionProtocolError, match="executable source"):
        load_committed_collection_registry(repository)


def test_working_source_bundle_rejects_ignored_executable_content(
    tmp_path: Path,
) -> None:
    repository = _committed_repository(tmp_path)
    ignored = repository / "src" / "pokemon_red_completion" / "ignored_override.py"
    (repository / ".gitignore").write_text("ignored_override.py\n", encoding="ascii")
    ignored.write_text("raise RuntimeError('must not execute')\n", encoding="ascii")

    with pytest.raises(CollectionProtocolError, match="ignored content"):
        working_source_bundle_sha256(repository)


def test_committed_loader_bounds_the_sidecar_before_materializing_it(
    tmp_path: Path,
) -> None:
    repository = _committed_repository(tmp_path)
    (repository / COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH).write_bytes(b"x" * 5000)
    _commit(repository, "oversized sidecar")

    with pytest.raises(CollectionProtocolError, match="size limit"):
        load_committed_collection_registry(repository)


def test_registry_generator_check_mode_rebuilds_the_exact_tracked_bytes() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/regenerate_collection_registry.py",
            "--check",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_metadata_names_seed_as_harness_seed_not_a_cartridge_seed() -> None:
    assignment = parse_collection_registry(REGISTRY_PATH.read_bytes()).assignment(
        "red-battle-v95-08-test"
    )
    metadata = deepcopy(assignment.metadata_dict())
    serialized = json.dumps(metadata, sort_keys=True)

    assert metadata["harness_seed"] == 1610001
    assert '"seed"' not in serialized
    assert BATTLE_START_SCHEDULE_SCHEMA in serialized
    assert "outcome" not in serialized
    assert "executed" not in serialized
