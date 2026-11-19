"""ROM-free continuation closure checks using existing authenticated fixtures."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from test_retained_story_preparation import story
from pokemon_red_completion.red_player_preparation_history import (
    RetainedStoryDefeat, retained_story_preparation_inputs,
)
from pokemon_red_completion.red_player_package import (
    make_package_read_guard, retained_metadata_closure, validate_retained_metadata_inputs,
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def retained(tmp_path):
    witness = tmp_path / "witness"
    witness.mkdir()
    actor, history = story(witness)
    record = RetainedStoryDefeat.from_history(history, 1).private_dict()
    return record, witness / "battle-0001", actor


def manifest():
    return dict(roots=[], pins={}, environment_pins={})


def node(path, context, parent=None):
    path.mkdir()
    save(path / "PLAN.json", {} if parent is None else dict(actual_parent=str(parent)))
    save(path / "CONTEXT.json", context)
    return path


def test_typed_inputs_are_exact_and_leave_all_context_fields_untouched(retained, tmp_path):
    record, directory, _ = retained
    noise = directory / "unrelated.json"
    noise.write_text("{}")
    (directory / "events/other.json").write_text("{}")
    before = deepcopy(record)
    expected = {directory / name for name in (
        "outcome.json", "initial.state", "initial.state.json", "endpoint.json", "final.state",
    )} | set((directory / "events").glob("event-*.json"))
    assert set(retained_story_preparation_inputs(record)) == expected
    assert retained_story_preparation_inputs(None) == []
    assert record == before and noise not in expected
    context = dict(
        preparation_story_loss=dict(schema="pokemon.red.story-preparation-history.v1", defeats=[record]),
        search_memory={"retained": "exact"}, field_carrier={"retained": "exact"},
        story_kind_commitment={"retained": "exact"}, spent={"seconds": 123.25},
        grants_new_budget=False, fit_allowed=False,
    )
    source = node(tmp_path / "source", context)
    original = (source / "CONTEXT.json").read_bytes()
    files, nodes = retained_metadata_closure(source, manifest(), tmp_path / "new-output")
    assert set(nodes[0]["retained_story_preparation_inputs"]) == {str(x) for x in expected}
    assert expected <= set(files) and noise not in files
    assert (source / "CONTEXT.json").read_bytes() == original


@pytest.mark.parametrize("name", [
    "outcome.json", "initial.state", "initial.state.json", "endpoint.json",
    "final.state", "events/event-00001.json",
])
@pytest.mark.parametrize("missing", [False, True])
def test_missing_or_tampered_typed_witness_fails_before_pin_emission(retained, name, missing):
    record, directory, _ = retained
    path = directory / name
    if missing:
        path.unlink()
    else:
        path.write_bytes(b"tampered")
    with pytest.raises((ValueError, OSError, KeyError, TypeError)):
        retained_story_preparation_inputs(record)


def test_current_source_typed_closure_does_not_admit_obsolete_ancestor_defeats(retained, tmp_path):
    record, directory, _ = retained
    ancestor = node(tmp_path / "ancestor", dict(preparation_story_loss={"schema": "obsolete"}))
    source = node(tmp_path / "source", dict(preparation_story_loss=record), ancestor)
    files, nodes = retained_metadata_closure(source, manifest(), tmp_path / "new-output")
    assert len(nodes) == 2 and nodes[1]["retained_story_preparation_inputs"] == []
    assert directory / "outcome.json" in files and ancestor / "CONTEXT.json" in files


def test_preflight_requires_every_exact_pin_and_does_not_expand_guard(retained, tmp_path):
    record, directory, _ = retained
    source = node(tmp_path / "source", dict(preparation_story_loss=record))
    package = manifest()
    files, _ = retained_metadata_closure(source, package, tmp_path / "output")
    protected = {str(path): digest(path) for path in files}
    omitted = directory / "outcome.json"
    with pytest.raises(ValueError, match="omitted"):
        validate_retained_metadata_inputs(source, package, tmp_path / "output",
                                         {k: v for k, v in protected.items() if k != str(omitted)})
    assert validate_retained_metadata_inputs(source, package, tmp_path / "output", protected)[0] == files
    protected[str(omitted)] = "f" * 64
    with pytest.raises(ValueError, match="input hash changed"):
        validate_retained_metadata_inputs(source, package, tmp_path / "output", protected)
    protected[str(omitted)] = digest(omitted)
    unlisted = directory / "unlisted.json"
    unlisted.write_text("{}")
    guard, reads, writes = make_package_read_guard(
        package, manifest_path=tmp_path / "package.json", output=tmp_path / "output",
        extra_inputs=protected,
    )
    for path in files:
        guard("open", (str(path), "r", 0))
    with pytest.raises(ValueError, match="undeclared"):
        guard("open", (str(unlisted), "r", 0))
    assert reads == set(protected) and not writes


def test_preflight_rejects_conflicting_package_and_protected_pin(retained, tmp_path):
    record, _, _ = retained
    source = node(tmp_path / "source", dict(preparation_story_loss=record))
    package = manifest()
    files, _ = retained_metadata_closure(source, package, tmp_path / "output")
    protected = {str(path): digest(path) for path in files}
    package["pins"][str(files[0])] = "f" * 64
    with pytest.raises(ValueError, match="conflicting"):
        validate_retained_metadata_inputs(source, package, tmp_path / "output", protected)


def test_existing_ordered_relocation_and_new_output_passthrough_are_unchanged(tmp_path):
    original = tmp_path / "original"
    frozen = tmp_path / "frozen"
    original.mkdir()
    frozen.mkdir()
    old = node(frozen / "old", {})
    source = node(original / "new", {}, original / "old")
    package = dict(roots=[(str(original), str(frozen))], pins={}, environment_pins={})
    files, nodes = retained_metadata_closure(source, package, source)
    assert [row["path"] for row in nodes] == [str(source), str(old)]
    assert old / "PLAN.json" in files


def test_cycles_are_not_silently_truncated(tmp_path):
    source = node(tmp_path / "source", {})
    save(source / "PLAN.json", dict(actual_parent=str(source)))
    with pytest.raises(ValueError, match="cyclic"):
        retained_metadata_closure(source, manifest(), tmp_path / "output")


def test_typed_scope_authentication_is_still_used(retained):
    record, _, actor = retained
    assert retained_story_preparation_inputs(record, expected_lineage=actor.root_lineage_id,
                                             expected_partition="train")
    with pytest.raises(ValueError, match="lineage or partition"):
        retained_story_preparation_inputs(record, expected_lineage="foreign", expected_partition="train")


def test_initial_without_plan_is_pinned_and_checked_by_existing_guard(tmp_path):
    initial = tmp_path / "initial"
    initial.mkdir()
    (initial / "terminal.state").write_bytes(b"initial bytes")
    save(initial / "CONTEXT.json", {})
    source = node(tmp_path / "source", {}, initial)
    package = manifest()
    files, nodes = retained_metadata_closure(source, package, tmp_path / "output")
    assert initial / "terminal.state" in files
    assert [x["path"] for x in nodes] == [str(source), str(initial)]
    protected = {str(p): digest(p) for p in files}
    with pytest.raises(ValueError, match="omitted"):
        validate_retained_metadata_inputs(source, package, tmp_path / "output",
            {k: v for k, v in protected.items() if k != str(initial / "terminal.state")})
    guard, reads, writes = make_package_read_guard(package,
        manifest_path=tmp_path / "package.json", output=tmp_path / "output", extra_inputs=protected)
    guard("open", (str(initial / "terminal.state"), "r", 0))
    assert str(initial / "terminal.state") in reads and not writes


@pytest.mark.parametrize("name", ["terminal.state", "CONTEXT.json"])
def test_source_alias_mismatch_fails_before_admission(tmp_path, name):
    original, frozen = tmp_path / "original", tmp_path / "frozen"
    original.mkdir(); frozen.mkdir()
    source = node(original / "source", {})
    alias = node(frozen / "source", {})
    (source / "terminal.state").write_bytes(b"same")
    (alias / "terminal.state").write_bytes(b"same")
    (alias / name).write_bytes(b"different")
    package = dict(roots=[(str(original), str(frozen))], pins={}, environment_pins={})
    with pytest.raises(ValueError, match="relocation bytes differ"):
        retained_metadata_closure(source, package, tmp_path / "output")


def test_next_outer_chunk_can_read_exact_source_alias_without_broadening_guard(tmp_path):
    original, frozen = tmp_path / "original", tmp_path / "frozen"
    original.mkdir(); frozen.mkdir()
    source = node(original / "source", {})
    alias = node(frozen / "source", {})
    for p in (source, alias):
        (p / "terminal.state").write_bytes(b"same source")
    noise = alias / "unrelated.bin"; noise.write_bytes(b"not a dependency")
    package = dict(roots=[(str(original), str(frozen))], pins={}, environment_pins={})
    files, nodes = retained_metadata_closure(source, package, tmp_path / "output")
    assert source / "terminal.state" in files and alias / "terminal.state" in files
    assert noise not in files and len(nodes) == 2
    protected = {str(p): digest(p) for p in files}
    guard, _, _ = make_package_read_guard(package,
        manifest_path=tmp_path / "package.json", output=tmp_path / "output", extra_inputs=protected)
    guard("open", (str(alias / "terminal.state"), "r", 0))
    with pytest.raises(ValueError, match="undeclared"):
        guard("open", (str(noise), "r", 0))
