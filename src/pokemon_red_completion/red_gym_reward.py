"""Cartridge-bound leader contract and native reward settlement, not battle policy."""

from dataclasses import dataclass

from . import silph
from .gen1_trainer_parties import trainer_party_quote
from .gen1_traversal import map_object_events
from .observation import MAX_BAG_ITEMS, Badge, EventFlag, ItemId, MapId, event_flag_is_set
from .red_story_battle import StoryTrainerContract
from .rom import verify_rom_bytes


@dataclass(frozen=True)
class GymReward:
    objective_id: str
    map_id: int
    trainer_class: int
    trainer_set: int
    defeated_event: int
    reward_event: int
    badge: int
    item: int

    def capacity_available(self, raw):
        if raw.bag_items is None:
            return False
        bag = dict(raw.bag_items)
        return bag[self.item] < 99 if self.item in bag else len(bag) < MAX_BAG_ITEMS

    def pending(self, raw):
        """An already earned local badge with its one-off TM still undelivered."""
        return bool(
            raw.map_id == self.map_id
            and raw.battle_state == 0
            and raw.event_flags is not None
            and raw.badge_bits is not None
            and event_flag_is_set(raw.event_flags, self.defeated_event)
            and raw.badge_bits & self.badge
            and not event_flag_is_set(raw.event_flags, self.reward_event)
        )

    def received(self, raw):
        """Permanent reward proof; using or depositing the TM does not undo victory."""
        return bool(
            raw.event_flags is not None
            and raw.badge_bits is not None
            and event_flag_is_set(raw.event_flags, self.defeated_event)
            and event_flag_is_set(raw.event_flags, self.reward_event)
            and raw.badge_bits & self.badge
        )

    def contract(self, rom, raw):
        verify_rom_bytes(rom)
        if (
            raw.event_flags is None
            or event_flag_is_set(raw.event_flags, self.defeated_event)
            or raw.badge_bits & self.badge
        ):
            raise ValueError("leader is consumed or unreadable")
        objects = [o for o in map_object_events(rom, {self.map_id}) if o.object_index == 1]
        if len(objects) != 1 or (objects[0].trainer_class, objects[0].trainer_set) != (
            self.trainer_class,
            self.trainer_set,
        ):
            raise ValueError("leader identity differs from cartridge")
        quote = trainer_party_quote(rom, self.trainer_class, self.trainer_set)
        return StoryTrainerContract(
            self.objective_id,
            "sabrina" if self == SABRINA_REWARD else self.objective_id,
            self.map_id,
            (self.trainer_class, self.trainer_class - 200, self.trainer_set),
            self.defeated_event,
            quote.expected_victory_money,
            ((self.item, 1),),
            self.badge,
        )

    def settle(self, reader, actions, *, before, victory_money):
        raw = reader.read()
        if (
            raw.battle_state
            or raw.map_id != self.map_id
            or not event_flag_is_set(raw.event_flags, self.defeated_event)
            or raw.player_money != before.player_money + victory_money
        ):
            raise ValueError("reward settlement requires native victory and exact payout")
        expected = dict(before.bag_items)
        if not self.capacity_available(before):
            raise RuntimeError("gym reward requires a free bag slot or available TM stack")
        expected[self.item] = expected.get(self.item, 0) + 1
        for _ in range(64):
            raw = reader.read()
            if (
                event_flag_is_set(raw.event_flags, self.reward_event)
                and raw.badge_bits & self.badge
                and dict(raw.bag_items) == expected
                and reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()
            ):
                break
            silph._interact(actions, silph.DEFAULT_SILPH_TIMING.dialogue_frames)
        else:
            raise RuntimeError("gym reward did not settle within dialogue bound")
        if (
            raw.battle_state
            or raw.map_id != self.map_id
            or raw.player_money != before.player_money + victory_money
            or raw.badge_bits != before.badge_bits | self.badge
        ):
            raise RuntimeError("gym reward reconciliation failed")
        return {
            "badge": self.badge,
            "item": self.item,
            "money_delta": victory_money,
            "native_defeat_event": self.defeated_event,
            "native_reward_event": self.reward_event,
        }


ERIKA_REWARD = GymReward(
    "defeat_erika",
    int(MapId.CELADON_GYM),
    237,
    1,
    int(EventFlag.BEAT_ERIKA),
    int(EventFlag.GOT_TM21),
    int(Badge.RAINBOW),
    int(ItemId.TM21_MEGA_DRAIN),
)


SURGE_REWARD = GymReward(
    "defeat_surge",
    int(MapId.VERMILION_GYM),
    236,
    1,
    int(EventFlag.BEAT_LT_SURGE),
    int(EventFlag.GOT_TM24),
    int(Badge.THUNDER),
    int(ItemId.TM24_THUNDERBOLT),
)


BROCK_REWARD = GymReward(
    "defeat_brock",
    int(MapId.PEWTER_GYM),
    234,
    1,
    int(EventFlag.BEAT_BROCK),
    int(EventFlag.GOT_TM34),
    int(Badge.BOULDER),
    int(ItemId.TM34_BIDE),
)


MISTY_REWARD = GymReward(
    "defeat_misty",
    int(MapId.CERULEAN_GYM),
    235,
    1,
    int(EventFlag.BEAT_MISTY),
    int(EventFlag.GOT_TM11),
    int(Badge.CASCADE),
    int(ItemId.TM11_BUBBLEBEAM),
)


SABRINA_REWARD = GymReward(
    "defeat_sabrina",
    int(MapId.SAFFRON_GYM),
    240,
    1,
    int(EventFlag.BEAT_SABRINA),
    int(EventFlag.GOT_TM46),
    int(Badge.MARSH),
    int(ItemId.TM46_PSYWAVE),
)


KOGA_REWARD = GymReward(
    "defeat_koga",
    int(MapId.FUCHSIA_GYM),
    238,
    1,
    int(EventFlag.BEAT_KOGA),
    int(EventFlag.GOT_TM06),
    int(Badge.SOUL),
    int(ItemId.TM06_TOXIC),
)

BLAINE_REWARD = GymReward(
    "defeat_blaine",
    int(MapId.CINNABAR_GYM),
    239,
    1,
    int(EventFlag.BEAT_BLAINE),
    int(EventFlag.GOT_TM38),
    int(Badge.VOLCANO),
    int(ItemId.TM38_FIRE_BLAST),
)

GIOVANNI_REWARD = GymReward(
    "defeat_giovanni",
    int(MapId.VIRIDIAN_GYM),
    229,
    3,
    int(EventFlag.BEAT_VIRIDIAN_GYM_GIOVANNI),
    int(EventFlag.GOT_TM27),
    int(Badge.EARTH),
    int(ItemId.TM27_FISSURE),
)
