"""Generation I adapter for observed, renewable encounter suppression."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import ItemId, PokemonRedStateReader, RawGameState
from pokemon_red_completion.route_executor import (
    ResourceRenewalReceipt,
    RouteActionPort,
    RouteExecutionError,
    TraversalResource,
    TraversalSnapshot,
)

ENCOUNTER_SUPPRESSION = "encounter_suppression"
REPEL_STEPS = {
    ItemId.MAX_REPEL: 250,
    ItemId.SUPER_REPEL: 200,
    ItemId.REPEL: 100,
}
REPEL_PRIORITY = tuple(REPEL_STEPS)


def gen1_repel_resource(raw: RawGameState) -> TraversalResource:
    """Project remaining effect and carried renewals without assuming either exists."""

    carried = (
        None
        if raw.bag_items is None
        else sum(
            quantity
            for item_id, quantity in raw.bag_items
            if item_id in REPEL_STEPS
        )
    )
    return TraversalResource(
        ENCOUNTER_SUPPRESSION,
        raw.repel_remaining_steps,
        carried,
    )


@dataclass(slots=True)
class Gen1RepelRenewalManager:
    """Dismiss an expiry boundary and consume exactly one observed Repel item."""

    actions: RouteActionPort
    reader: PokemonRedStateReader
    use_item: Callable[[int], None]
    prompt_confirmation_limit: int = 8
    prompt_wait_frames: int = 240

    def __post_init__(self) -> None:
        if type(self.prompt_confirmation_limit) is not int or self.prompt_confirmation_limit <= 0:  # noqa: E721
            raise ValueError("prompt_confirmation_limit must be a positive integer")
        if type(self.prompt_wait_frames) is not int or self.prompt_wait_frames <= 0:  # noqa: E721
            raise ValueError("prompt_wait_frames must be a positive integer")

    def renew_if_needed(
        self,
        current: TraversalSnapshot,
    ) -> ResourceRenewalReceipt | None:
        resource = next(
            (item for item in current.resources if item.kind == ENCOUNTER_SUPPRESSION),
            None,
        )
        if resource is None or resource.remaining is None or resource.carried_units is None:
            raise RouteExecutionError("Gen I Repel state is unavailable")
        raw = self.reader.read()
        self._require_same_overworld(raw, current, "Repel observation")
        if raw.repel_remaining_steps != resource.remaining:
            raise RouteExecutionError("Repel snapshot disagrees with live remaining steps")
        if resource.remaining > 0:
            return None

        before_bag = dict(raw.bag_items or ())
        selected = next(
            (item for item in REPEL_PRIORITY if before_bag.get(item, 0) > 0),
            None,
        )
        if selected is None:
            raise RouteExecutionError("Repel expired without a carried renewal")

        confirmations = 0
        for _ in range(self.prompt_confirmation_limit):
            if self.reader.read_input_readiness().ready:
                break
            self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
            self.actions.execute(
                MacroAction(MacroActionKind.WAIT, repeat=self.prompt_wait_frames)
            )
            confirmations += 1
            self._require_same_overworld(
                self.reader.read(),
                current,
                "Repel expiry prompt",
            )
            if self.reader.read_input_readiness().ready:
                break
        else:
            raise RouteExecutionError("Repel expiry prompt did not restore input")
        if not self.reader.read_input_readiness().ready:
            raise RouteExecutionError("Repel expiry prompt remained active")

        self.use_item(int(selected))
        after = self.reader.read()
        self._require_same_overworld(after, current, "Repel renewal")
        after_bag = dict(after.bag_items or ())
        expected_bag = dict(before_bag)
        expected_bag[selected] -= 1
        if expected_bag[selected] == 0:
            del expected_bag[selected]
        expected_steps = REPEL_STEPS[selected]
        if (
            after_bag != expected_bag
            or after.repel_remaining_steps != expected_steps
            or not self.reader.read_input_readiness().ready
        ):
            raise RouteExecutionError("Repel renewal did not settle its exact resource boundary")
        return ResourceRenewalReceipt(
            kind=ENCOUNTER_SUPPRESSION,
            map_id=current.map_id,
            at=current.at,
            before_remaining=0,
            after_remaining=expected_steps,
            units_consumed=1,
            details={
                "item_id": int(selected),
                "prompt_confirmations": confirmations,
                "carried_before": resource.carried_units,
                "carried_after": resource.carried_units - 1,
            },
        )

    @staticmethod
    def _require_same_overworld(
        raw: RawGameState,
        current: TraversalSnapshot,
        label: str,
    ) -> None:
        if (
            raw.map_id != current.map_id
            or (raw.player_y, raw.player_x) != current.at
            or raw.battle_state != 0
        ):
            raise RouteExecutionError(f"{label} changed the protected overworld boundary")
