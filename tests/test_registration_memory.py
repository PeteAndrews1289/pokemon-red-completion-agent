import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.pokedex import declare_target
from pokemon_red_completion.registered_collection import (
    new_registration_credit,
    summarize_registered_collection,
)
from pokemon_red_completion.registration_memory import (
    RegistrationMemory,
    RegistrationObservation,
    RegistrationSnapshot,
    observation_from_collection,
)


def observed(*, run="red", sequence=0, owned=(1,), seen=None, counts=None):
    return RegistrationObservation(
        run, "game:" + run, "adapter:" + run, "a" * 64, "b" * 64,
        sequence, frozenset(owned if seen is None else seen), frozenset(owned),
        {s: 1 for s in owned} if counts is None else counts,
    )


def test_seen_is_not_credit_and_evolution_keeps_all_registration_without_base_stock(tmp_path):
    path = tmp_path / "dex.sqlite"
    memory = RegistrationMemory(path)
    first = observed(owned=(1,), seen=(1, 2, 3), counts={1: 1})
    assert memory.record(first).new_global_species == {1}
    before = memory.snapshot()
    assert before.registered == {1}
    second = observed(sequence=1, owned=(1, 2), counts={2: 1})
    assert memory.record(second).new_global_species == {2}
    third = memory.record(observed(sequence=2, owned=(1, 2, 3), counts={3: 1}))
    assert third.inserted is True and third.new_global_species == {3}
    after = RegistrationMemory(path).snapshot()
    assert after.registered == {1, 2, 3}
    assert after.latest("red").physical_counts == {3: 1}
    assert before.registered == {1}  # Frozen evaluation baseline cannot change.
    report = summarize_registered_collection(declare_target(3, {}), after, run_id="red")
    assert report.passed and report.physical_species == {3}
    assert new_registration_credit(before, after, target=declare_target(3, {})) == {2, 3}


def test_duplicate_import_and_duplicate_capture_have_no_novelty_or_penalty(tmp_path):
    memory = RegistrationMemory(tmp_path / "dex.sqlite")
    row = observed()
    memory.record(row)
    before = memory.snapshot()
    result = memory.record(row)
    assert result.inserted is False and not result.new_global_species
    assert memory.snapshot().sha256 == before.sha256
    duplicate = memory.record(observed(sequence=1, counts={1: 2}))
    assert duplicate.inserted is True and duplicate.new_global_species == set()
    after = memory.snapshot()
    assert len(after.observations) == 2
    assert after.latest("red").physical_counts == {1: 2}
    assert new_registration_credit(before, after, target=declare_target(3, {})) == set()


def test_red_blue_union_never_invents_blue_flags_or_physical_stock(tmp_path):
    memory = RegistrationMemory(tmp_path / "dex.sqlite")
    memory.record(observed(owned=(1, 2, 3), counts={3: 1}))
    assert memory.record(observed(run="blue", owned=(2, 4))).new_global_species == {4}
    report = summarize_registered_collection(declare_target(5, {}), memory.snapshot(),
                                            run_id="blue")
    assert report.globally_registered == {1, 2, 3, 4}
    assert report.locally_registered == {2, 4}
    assert report.physical_species == {2, 4}
    assert report.globally_credited_but_not_local == {1, 3}
    assert report.missing == {5}
    absent = summarize_registered_collection(declare_target(5, {}), memory.snapshot(),
                                            run_id="unstarted")
    assert absent.locally_registered == absent.physical_species == set()


def test_late_import_and_restore_keep_local_latest_separate_from_ever_registered(tmp_path):
    memory = RegistrationMemory(tmp_path / "dex.sqlite")
    memory.record(observed(sequence=10, owned=(1,), counts={}))
    memory.record(observed(sequence=2, owned=(1, 2)))
    result = memory.snapshot()
    assert result.registered == {1, 2}
    assert result.latest("red").owned == {1}
    assert result.latest("red").physical_counts == {}


@pytest.mark.parametrize("change", [
    {"game_id": "other"}, {"adapter_id": "other"}, {"cartridge_sha256": "c" * 64},
    {"owned": frozenset(), "physical_counts": {}}, {"snapshot_sha256": "d" * 64},
])
def test_conflicting_run_or_sequence_fails_without_mutation(tmp_path, change):
    memory = RegistrationMemory(tmp_path / "dex.sqlite")
    row = observed()
    memory.record(row)
    before = memory.snapshot().sha256
    with pytest.raises(ValueError, match="changed|conflicting"):
        memory.record(replace(row, **change))
    assert memory.snapshot().sha256 == before


@pytest.mark.parametrize("change", [
    {"owned": frozenset({2})}, {"seen": frozenset()}, {"physical_counts": {2: 1}},
    {"physical_counts": {1: True}}, {"sequence": True}, {"sequence": 2**63},
    {"seen": (1, 1)}, {"run_id": "private/path"}, {"snapshot_sha256": "bad"},
    {"owned": frozenset({True})},
])
def test_invalid_observations_are_rejected(change):
    with pytest.raises(ValueError):
        replace(observed(), **change)


def test_bridge_uses_explicit_mapping_and_rejects_aliases_or_unknown_species():
    collection = CollectionObservation(
        frozenset({"internal:28"}),
        (LivingSpecimen("internal:28", 36, CollectionLocation.PARTY),),
        1, 6, (0,), 0, 20,
    )
    kwargs = dict(seen_species=frozenset({"internal:28", "internal:1"}),
                  run_id="red", game_id="red", adapter_id="fixture",
                  cartridge_sha256="a" * 64, snapshot_sha256="b" * 64, sequence=0)
    row = observation_from_collection(collection,
                                     national_ids={"internal:28": 9, "internal:1": 112},
                                     **kwargs)
    assert row.owned == {9} and row.seen == {9, 112} and row.physical_counts == {9: 1}
    for mapping in ({"internal:28": 9}, {"internal:28": 9, "internal:1": 9},
                    {"internal:28": True, "internal:1": 112}):
        with pytest.raises(ValueError):
            observation_from_collection(collection, national_ids=mapping, **kwargs)


def test_defensive_copies_and_path_free_export():
    counts = {1: 1}
    row = observed(counts=counts)
    counts[1] = 99
    rows = [row]
    snapshot = RegistrationSnapshot(rows)
    rows.clear()
    assert snapshot.latest("red").physical_counts == {1: 1}
    with pytest.raises(TypeError):
        row.physical_counts[1] = 50
    data = json.loads(snapshot.export_json())
    assert data["registered"] == [1]
    assert data["observations"][0]["physical_counts"] == [[1, 1]]
    assert "path" not in snapshot.export_json()


def test_concurrent_duplicates_and_overlap_credit_once(tmp_path):
    path = tmp_path / "dex.sqlite"
    def record(i):
        return RegistrationMemory(path).record(observed(run=f"run-{i % 4}", owned=(1, i % 4 + 2)))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(record, range(16)))
    assert sum(result.inserted for result in results) == 4
    assert sum(len(result.new_global_species) for result in results) == 5
    assert RegistrationMemory(path).snapshot().registered == {1, 2, 3, 4, 5}


def test_abrupt_process_exit_during_write_rolls_back_and_can_resume(tmp_path):
    path = tmp_path / "dex.sqlite"
    memory = RegistrationMemory(path)
    memory.record(observed())
    before = memory.snapshot().sha256
    child = subprocess.run([sys.executable, "-c", """
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute('BEGIN IMMEDIATE')
c.execute("INSERT INTO registrations VALUES ('interrupted', 0, 'invalid', 'invalid')")
os._exit(7)
""", str(path)], timeout=15, check=False)
    assert child.returncode == 7
    assert RegistrationMemory(path).snapshot().sha256 == before
    assert memory.record(observed(sequence=1, owned=(1, 2))).new_global_species == {2}


@pytest.mark.parametrize("statement", [
    "UPDATE registrations SET payload='{}'",
    "UPDATE registrations SET digest='bad'",
    "UPDATE registrations SET sequence=44",
])
def test_corrupt_evidence_is_rejected_on_read_and_before_write(tmp_path, statement):
    path = tmp_path / "dex.sqlite"
    memory = RegistrationMemory(path)
    memory.record(observed())
    with sqlite3.connect(path) as connection:
        connection.execute(statement)
    with pytest.raises(ValueError):
        memory.snapshot()
    with pytest.raises(ValueError):
        memory.record(observed(sequence=1))
    with pytest.raises(ValueError):
        RegistrationMemory(path)


def test_foreign_database_and_rewritten_history_are_rejected(tmp_path):
    path = tmp_path / "other.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (value)")
    with pytest.raises(ValueError, match="supported registration database"):
        RegistrationMemory(path)
    with pytest.raises(ValueError, match="removed or rewritten"):
        new_registration_credit(RegistrationSnapshot((observed(),)), RegistrationSnapshot(()),
                                target=declare_target(3, {}))
