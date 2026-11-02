"""Opt-in story combat: declared boundaries, learned decisions, no teacher fallback.

This adapter grants no global gym/League override. Chapters supply a cartridge-
derived trainer contract and keep navigation, gifts and badge dialogue separate.
The first contract is zero-item; combat items need their own explicit controller.
"""

from dataclasses import dataclass

from .battle_runtime import BattleRuntimeTiming, advance_battle_to_policy_boundary
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import static_trainer_sight_zones, trainer_headers
from .gen1_traversal import map_object_events
from .observation import event_flag_is_set
from .red_eventless_trainer import eventless_battle_ready
from .red_learned_trainer import FrozenTrainerBattler
from .red_trainer_battle_lifecycle import continue_learned_trainer_battle


@dataclass(frozen=True)
class StoryTrainerContract:
    objective_id: str
    battle_plan_id: str
    map_id: int
    trainer_identity: tuple[int, int, int]
    defeated_event: int | None
    victory_money: int
    victory_items: tuple[tuple[int, int], ...] = ()
    victory_badge_bits: int = 0

    def __post_init__(self):
        if (
            not isinstance(self.objective_id, str)
            or not self.objective_id
            or not isinstance(self.battle_plan_id, str)
            or not self.battle_plan_id
            or type(self.map_id) is not int
            or not 0 <= self.map_id <= 255
            or (
                self.defeated_event is not None
                and (type(self.defeated_event) is not int or self.defeated_event < 0)
            )
            or (
                self.defeated_event is None
                and (
                    not (
                        (
                            self.objective_id == "obtain_cut"
                            and self.battle_plan_id == "ss-anne-rival-gate"
                            and self.map_id == 96
                            and self.trainer_identity in {(242, 42, 1), (242, 42, 2), (242, 42, 3)}
                        )
                        or (
                            self.objective_id == "clear_rocket_hideout"
                            and self.battle_plan_id == "game-corner-poster-guard"
                            and self.map_id == 135
                            and self.trainer_identity == (230, 30, 7)
                        )
                    )
                    or self.victory_items
                    or self.victory_badge_bits
                )
            )
            or type(self.victory_money) is not int
            or not 0 < self.victory_money <= 999999
            or not isinstance(self.trainer_identity, tuple)
            or len(self.trainer_identity) != 3
            or any(type(v) is not int or not 0 <= v <= 255 for v in self.trainer_identity)
            or not 201 <= self.trainer_identity[0] <= 247
            or self.trainer_identity[1] != self.trainer_identity[0] - 200
            or self.trainer_identity[2] == 0
        ):
            raise ValueError("invalid story trainer contract")

    @classmethod
    def from_cartridge(
        cls,
        rom,
        raw,
        *,
        objective_id,
        battle_plan_id,
        map_id,
        defeated_event,
        allow_final_class=False,
    ):
        zones = static_trainer_sight_zones(
            trainer_headers(rom, {map_id}, full_event_offsets=True),
            map_object_events(rom, {map_id}),
            raw.event_flags,
        )
        matches = [z for z in zones if z.event_flag == defeated_event and not z.defeated]
        if len(matches) != 1:
            raise ValueError("story trainer must be uniquely quoted and undefeated")
        trainer = matches[0]
        # Keep the cartridge adapter's explicit exact-Red final-class opt-in.
        quote = trainer_party_quote(
            rom, trainer.trainer_class, trainer.trainer_set, allow_final_class=allow_final_class
        )
        return cls(
            objective_id,
            battle_plan_id,
            map_id,
            (trainer.trainer_class, trainer.trainer_class - 200, trainer.trainer_set),
            defeated_event,
            quote.expected_victory_money,
        )


@dataclass
class FrozenStoryBattleController:
    battler: FrozenTrainerBattler
    contracts: tuple[StoryTrainerContract, ...]
    maximum_decisions: int = 80
    preparation_review: object = None
    evolution_rom: bytes | None = None

    def __post_init__(self):
        self.require_identity()
        if self.evolution_rom is not None and (
            not isinstance(self.evolution_rom, bytes) or not self.evolution_rom
        ):
            raise ValueError("story evolution requires an immutable cartridge")
        if self.preparation_review is not None and not callable(self.preparation_review):
            raise ValueError("story preparation review must be callable")
        if (
            not isinstance(self.contracts, tuple)
            or not self.contracts
            or any(not isinstance(c, StoryTrainerContract) for c in self.contracts)
            or len({(c.objective_id, c.battle_plan_id) for c in self.contracts})
            != len(self.contracts)
            or type(self.maximum_decisions) is not int
            or not 1 <= self.maximum_decisions <= 80
        ):
            raise ValueError("invalid story battle scope or decision budget")
        for contract in self.contracts:
            self.battler.require_story_contract(contract)

    def require_identity(self):
        if not isinstance(self.battler, FrozenTrainerBattler) or not self.battler.story_limit():
            raise ValueError("story combat requires an exact receipt-bound story model")
        self.battler.require_story_identity()

    def run(self, reader, actions, *, objective_id, battle_plan_id, expected_map, timing=None):
        self.require_identity()
        timing = timing or BattleRuntimeTiming()
        matches = [
            c
            for c in self.contracts
            if (c.objective_id, c.battle_plan_id, c.map_id)
            == (objective_id, battle_plan_id, expected_map)
        ]
        if len(matches) != 1:
            raise ValueError("undeclared story battle boundary")
        contract = matches[0]
        self.battler.require_story_contract(contract)
        before = reader.read()
        from .red_trainer_evolution import RedTrainerEvolutionGuard

        evolution_guard = (
            None
            if self.evolution_rom is None
            else RedTrainerEvolutionGuard.from_rom(self.evolution_rom, self.battler.session)
        )
        if (
            before.battle_state != 2
            or before.map_id != contract.map_id
            or reader.read_active_trainer_identity() != contract.trainer_identity
            or before.event_flags is None
            or (
                contract.defeated_event is not None
                and (
                    contract.defeated_event >= len(before.event_flags) * 8
                    or event_flag_is_set(before.event_flags, contract.defeated_event)
                )
            )
            or (
                contract.defeated_event is None
                and not eventless_battle_ready(reader, contract.trainer_identity)
            )
        ):
            raise ValueError("story battle identity or event is stale")
        # A retained faint/switch prompt is already a model decision boundary.
        # Do not acknowledge it as introduction text or wait for MAIN forever.
        index = before.active_party_index
        forced = (
            before.battler_hp == 0
            and type(index) is int
            and before.party_hp is not None
            and len(before.party_hp) == before.party_count
            and 0 <= index < len(before.party_hp)
            and before.party_hp[index] == 0
            and any(hp > 0 for hp in before.party_hp)
            and (before.enemy_hp or 0) > 0
        )
        prompt_reader = getattr(reader, "trainer_switch_prompt_visible", None)
        prompt = callable(prompt_reader) and prompt_reader(before)
        if not forced and not prompt:
            # Advance text/intro only. No move policy or healing callback is supplied.
            advance_battle_to_policy_boundary(
                reader,
                actions,
                expected_map=expected_map,
                expected_battle_state=2,
                timing=timing,
                label="learned story entry",
            )
        after = reader.read()
        for key in (
            "party_count",
            "party_species_ids",
            "party_hp",
            "party_moves",
            "party_pp",
            "bag_items",
            "player_money",
            "badge_bits",
            "event_flags",
        ):
            if getattr(before, key) != getattr(after, key):
                raise ValueError("story introduction changed protected resources")
        result = continue_learned_trainer_battle(
            self.battler,
            reader,
            actions,
            trainer_identity=contract.trainer_identity,
            defeated_event=contract.defeated_event,
            ordinary_victory_money=contract.victory_money,
            timing=timing,
            remaining_decisions=self.maximum_decisions,
            story_authority=True,
            victory_items=contract.victory_items,
            victory_badge_bits=contract.victory_badge_bits,
            **({"evolution_guard": evolution_guard} if evolution_guard is not None else {}),
        )
        if self.preparation_review is not None:
            self.preparation_review(result)
        return result
