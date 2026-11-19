"""No future arrival credit or implicit expansion of TRAIN authority."""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_sequence_state_audit import events
from test_scoped_story_sequence import reader
from test_scoped_train_composition import case

from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.red_sequence_state_audit import (
    NativeSequenceBoundary,
    _retain_observed_saffron_arrival,
)


def boundary(quests=(), progress=(), digest="a" * 64):
    return NativeSequenceBoundary(digest, 100, tuple(sorted(progress)), tuple(sorted(quests)))


def test_native_arrival_survives_later_departure_only_with_explicit_scope():
    old = boundary(("reach_saffron",), ("quest:reach_saffron", "story:saffron_guards_open"))
    new = boundary((), ("story:saffron_guards_open",), "b" * 64)
    assert _retain_observed_saffron_arrival(old, new) is new
    carried = _retain_observed_saffron_arrival(old, new, enabled=True)
    assert carried.quests == ("reach_saffron",)
    assert carried.state_sha256 == new.state_sha256 and carried.cash == new.cash
    assert "quest:reach_saffron" in carried.progress


def test_guard_access_and_future_arrival_cannot_earn_previous_credit():
    before = boundary((), ("story:saffron_guards_open",))
    departed = boundary((), ("story:saffron_guards_open",), "b" * 64)
    later_arrival = boundary(
        ("reach_saffron",), ("quest:reach_saffron", "story:saffron_guards_open"), "c" * 64
    )
    assert _retain_observed_saffron_arrival(before, departed, enabled=True).quests == ()
    assert _retain_observed_saffron_arrival(departed, later_arrival, enabled=True).quests == (
        "reach_saffron",
    )
    assert departed.quests == ()


def test_arrival_retention_rejects_lost_native_guard_evidence():
    with pytest.raises(ValueError, match="guards"):
        _retain_observed_saffron_arrival(boundary(("reach_saffron",)), boundary(), enabled=True)
    with pytest.raises(ValueError, match="boolean"):
        _retain_observed_saffron_arrival(boundary(), boundary(), enabled=1)


@pytest.mark.parametrize(
    "flags,expected",
    [
        ((), ()),
        ((EventFlag.BEAT_SILPH_CO_GIOVANNI,), ()),
        ((EventFlag.GOT_MASTER_BALL,), ()),
        ((EventFlag.BEAT_SILPH_CO_GIOVANNI, EventFlag.GOT_MASTER_BALL), ("liberate_silph",)),
    ],
)
def test_silph_completion_needs_both_native_victory_and_gift(
    tmp_path, monkeypatch, flags, expected
):
    raw = NS(
        map_id=133,
        battle_state=0,
        player_money=100,
        event_flags=events(*flags),
        badge_bits=0,
        status_flags_1=0,
    )
    audit = reader(monkeypatch, raw, include_silph=True, objectives=("liberate_silph",))
    p = tmp_path / "state"
    p.write_bytes(b"state")
    result = audit.read(p, sha256(b"state").hexdigest())
    assert result.quests == expected
    assert audit.task_completed((), result.progress) is bool(expected)
    # Gift history remains valid if the earned ball was later used.
    assert audit.emulator.frame_count == 0


def test_extended_reader_flags_change_identity_and_default_is_unchanged(monkeypatch):
    raw = NS()
    legacy = reader(monkeypatch, raw)
    explicit = reader(monkeypatch, raw, include_silph=False, retain_saffron_arrival=False)
    extended = reader(monkeypatch, raw, include_silph=True, retain_saffron_arrival=True)
    assert legacy.task_sha256 == explicit.task_sha256
    assert legacy.catalog_sha256 == explicit.catalog_sha256
    assert extended.task_sha256 != legacy.task_sha256
    assert extended.catalog_sha256 != legacy.catalog_sha256
    with pytest.raises(ValueError, match="booleans"):
        reader(monkeypatch, raw, include_silph=1)


def test_fourth_scoped_train_objective_requires_exact_opt_in(tmp_path):
    spec, *_ = case(tmp_path)
    contracts = tuple(
        replace(spec.contracts[0], objective_id=x)
        for x in ("defeat_erika", "rescue_fuji", "reach_saffron", "liberate_silph")
    )
    with pytest.raises(ValueError, match="finite pool scope"):
        replace(spec, contracts=contracts)
    extended = replace(spec, contracts=contracts, include_silph=True)
    assert extended.contracts == contracts
    with pytest.raises(ValueError, match="undeclared objective"):
        replace(
            extended,
            contracts=(*contracts[:-1], replace(contracts[-1], objective_id="defeat_sabrina")),
        )
    with pytest.raises(ValueError, match="boolean"):
        replace(spec, include_silph=1)
