from pathlib import Path
import pytest

from pokemon_red_completion.red_sequence_state_audit import NativeSequenceBoundary, ScopedStorySequenceStateReader
from pokemon_red_completion.red_task_sequence_audit import TaskSequenceStateReader


def base(*, quests=(), guards=True):
    reader = object.__new__(ScopedStorySequenceStateReader)
    reader.objectives = ("defeat_erika", "liberate_silph", "rescue_fuji")
    reader.quest_scope = frozenset(reader.objectives) | {"reach_saffron"}
    reader.catalog_sha256 = "a" * 64
    reader.task_sha256 = "b" * 64
    progress = ("event:82", "owned-dex:007") + (("story:saffron_guards_open",) if guards else ())
    reader.read = lambda path, digest: NativeSequenceBoundary(digest, 123, progress, quests)
    return reader


def rows(before, after):
    return [{"before": {"completed_objectives": before}, "after": {"completed_objectives": after}}]


def test_only_native_task_quests_and_costs_are_covered():
    wrapped = TaskSequenceStateReader(base(quests=("reach_saffron", "defeat_erika")), masked_source_quests=frozenset({"reach_saffron"}))
    result = wrapped.read(Path("unused"), "c" * 64)
    assert result == NativeSequenceBoundary("c" * 64, 123, ("quest:defeat_erika",), ("defeat_erika",))
    assert wrapped.target_channels == {"completed_quests", "actions", "frames"}
    assert wrapped.task_sha256 == wrapped.reader.task_sha256
    assert wrapped.catalog_sha256 != wrapped.reader.catalog_sha256
    assert wrapped.task_completed((), result.progress)
    assert not wrapped.task_completed((), ("quest:reach_saffron",))


@pytest.mark.parametrize("before,after", [([], ["reach_saffron"]), (["reach_saffron"], []), ([], [])])
def test_source_mask_cannot_supply_new_or_disappearing_credit(before, after):
    wrapped = TaskSequenceStateReader(base(), masked_source_quests=frozenset({"reach_saffron"}))
    with pytest.raises(ValueError, match="remain present"):
        wrapped.validate_source_claims(rows(before, after))


def test_all_boundaries_are_checked():
    wrapped = TaskSequenceStateReader(base(), masked_source_quests=frozenset({"reach_saffron"}))
    wrapped.validate_source_claims(rows(["reach_saffron"], ["reach_saffron", "defeat_erika"]))
    with pytest.raises(ValueError):
        wrapped.validate_source_claims(rows(["reach_saffron"], ["reach_saffron"]) + rows([], []))


@pytest.mark.parametrize("mask", [frozenset({"defeat_erika"}), frozenset({"rescue_fuji"}), frozenset({"unknown"}), {"reach_saffron"}])
def test_target_or_unknown_or_untyped_masks_are_refused(mask):
    with pytest.raises(ValueError):
        TaskSequenceStateReader(base(), masked_source_quests=mask)


def test_current_guard_truth_is_still_required():
    wrapped = TaskSequenceStateReader(base(guards=False), masked_source_quests=frozenset({"reach_saffron"}))
    with pytest.raises(ValueError, match="native guard access"):
        wrapped.read(Path("unused"), "c" * 64)


def test_default_does_not_invent_saffron_credit():
    wrapped = TaskSequenceStateReader(base(quests=("reach_saffron",)))
    assert wrapped.read(Path("unused"), "c" * 64).quests == ()
    assert wrapped.masked_source_quests == frozenset()


def test_arbitrary_readers_and_missing_chains_are_refused():
    with pytest.raises(ValueError):
        TaskSequenceStateReader(object())
    wrapped = TaskSequenceStateReader(base())
    with pytest.raises(ValueError):
        wrapped.validate_source_claims([])
