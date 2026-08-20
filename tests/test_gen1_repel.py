from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_repel import (
    ENCOUNTER_SUPPRESSION,
    Gen1RepelRenewalManager,
    gen1_repel_resource,
)
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def raw(
    *,
    remaining: int | None,
    bag: tuple[tuple[int, int], ...] | None,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=108,
        player_x=7,
        player_y=23,
        party_count=6,
        battle_state=0,
        bag_items=bag,
        repel_remaining_steps=remaining,
    )


@dataclass
class FakeReader:
    raw: RawGameState
    ready: bool = True

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0 if self.ready else 1, 0, 0, 0, 0)


@dataclass
class FakeActions:
    reader: FakeReader
    actions: list[MacroAction] = field(default_factory=list)

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        if action.kind is MacroActionKind.CONFIRM:
            self.reader.ready = True
        return action


def as_reader(fake: FakeReader) -> PokemonRedStateReader:
    return cast(PokemonRedStateReader, fake)


def snapshot(fake: FakeReader) -> TraversalSnapshot:
    return TraversalSnapshot(
        map_id=108,
        at=(23, 7),
        ready=fake.ready,
        resources=(gen1_repel_resource(fake.raw),),
    )


def test_repel_observation_keeps_unknown_distinct_from_zero() -> None:
    unknown = gen1_repel_resource(raw(remaining=None, bag=None))
    depleted = gen1_repel_resource(raw(remaining=0, bag=()))

    assert unknown.remaining is None
    assert unknown.carried_units is None
    assert depleted.remaining == 0
    assert depleted.carried_units == 0


def test_max_repel_renews_only_after_the_expiry_prompt_settles() -> None:
    fake = FakeReader(
        raw(remaining=0, bag=((ItemId.MAX_REPEL, 2),)),
        ready=False,
    )
    actions = FakeActions(fake)

    def use_item(item_id: int) -> None:
        assert item_id == ItemId.MAX_REPEL
        fake.raw = replace(
            fake.raw,
            bag_items=((ItemId.MAX_REPEL, 1),),
            repel_remaining_steps=250,
        )

    manager = Gen1RepelRenewalManager(actions, as_reader(fake), use_item)

    receipt = manager.renew_if_needed(snapshot(fake))

    assert receipt is not None
    assert receipt.kind == ENCOUNTER_SUPPRESSION
    assert receipt.before_remaining == 0
    assert receipt.after_remaining == 250
    assert receipt.units_consumed == 1
    assert receipt.details == {
        "item_id": ItemId.MAX_REPEL,
        "prompt_confirmations": 1,
        "carried_before": 2,
        "carried_after": 1,
    }
    assert actions.actions == [
        MacroAction(MacroActionKind.CONFIRM),
        MacroAction(MacroActionKind.WAIT, repeat=240),
    ]


def test_an_active_repel_needs_no_menu_action() -> None:
    fake = FakeReader(raw(remaining=17, bag=((ItemId.REPEL, 1),)))
    actions = FakeActions(fake)
    used: list[int] = []

    receipt = Gen1RepelRenewalManager(
        actions,
        as_reader(fake),
        used.append,
    ).renew_if_needed(snapshot(fake))

    assert receipt is None
    assert actions.actions == []
    assert used == []


def test_unknown_or_empty_repel_state_fails_closed_before_using_a_menu() -> None:
    unknown = FakeReader(raw(remaining=None, bag=None))
    empty = FakeReader(raw(remaining=0, bag=()))

    with pytest.raises(RouteExecutionError, match="state is unavailable"):
        Gen1RepelRenewalManager(
            FakeActions(unknown),
            as_reader(unknown),
            lambda _item: None,
        ).renew_if_needed(snapshot(unknown))
    with pytest.raises(RouteExecutionError, match="without a carried renewal"):
        Gen1RepelRenewalManager(
            FakeActions(empty),
            as_reader(empty),
            lambda _item: None,
        ).renew_if_needed(snapshot(empty))
