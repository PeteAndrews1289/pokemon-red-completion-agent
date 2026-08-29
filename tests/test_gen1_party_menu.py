from __future__ import annotations

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_party_menu import (
    promote_sole_living_party_member,
    promote_species_to_lead,
    sole_living_party_index,
)
from pokemon_red_completion.observation import InputReadiness, MapId, RamAddress, RawGameState


class _PartyMenuSimulation:
    def __init__(self, *, hp: tuple[int, int] = (0, 13)) -> None:
        self.stage = "field"
        self.cursor = 0
        self.source = 0
        self.species = [0xB3, 0x6B]
        self.hp = list(hp)
        self.moves = [(33, 39, 5, 55), (141, 48, 0, 0)]

    def read(self) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.MT_MOON_B2F,
            player_x=13,
            player_y=7,
            party_count=2,
            battle_state=0,
            party_species_ids=tuple(self.species),
            party_hp=tuple(self.hp),
            party_moves=tuple(self.moves),
            first_party_hp=self.hp[0],
        )

    def read_input_readiness(self) -> InputReadiness:
        # Red's movement flags can read as ready while a field menu remains
        # open. The implementation must close both menu layers structurally.
        return InputReadiness(0, 0, 0, 0, 0)

    def read_u8(self, address: int) -> int:
        if address == RamAddress.CURRENT_MENU_ITEM:
            return self.cursor
        raise AssertionError(f"unexpected address {address:#x}")

    def execute(self, action: MacroAction) -> object:
        if action.kind is MacroActionKind.OPEN_MENU:
            self.stage = "start"
            self.cursor = 0
        elif action.kind is MacroActionKind.MOVE:
            self.cursor += 1 if action.value == "down" else -1
        elif action.kind is MacroActionKind.CONFIRM:
            if self.stage == "start" and self.cursor == 1:
                self.stage = "party"
                self.cursor = 0
            elif self.stage == "party":
                self.source = self.cursor
                self.stage = "submenu"
                self.cursor = 0
            elif self.stage == "submenu" and self.cursor == 1:
                self.stage = "destination"
                self.cursor = self.source
            elif self.stage == "destination":
                destination = self.cursor
                self.species[self.source], self.species[destination] = (
                    self.species[destination],
                    self.species[self.source],
                )
                self.hp[self.source], self.hp[destination] = (
                    self.hp[destination],
                    self.hp[self.source],
                )
                self.moves[self.source], self.moves[destination] = (
                    self.moves[destination],
                    self.moves[self.source],
                )
                self.stage = "party_after_switch"
        elif action.kind is MacroActionKind.CANCEL:
            if self.stage == "party_after_switch":
                self.stage = "start"
            elif self.stage == "start":
                self.stage = "field"
        return object()


def test_sole_living_party_index_refuses_a_hidden_choice() -> None:
    assert sole_living_party_index((0, 13)) == 1
    assert sole_living_party_index((12, 13)) is None
    assert sole_living_party_index((0, 0)) is None


def test_promote_sole_living_party_member_restores_a_field_lead() -> None:
    simulation = _PartyMenuSimulation()

    after = promote_sole_living_party_member(
        simulation,
        simulation,
        simulation,  # type: ignore[arg-type]
        label="Mt. Moon survival lead",
    )

    assert after.party_species_ids == (0x6B, 0xB3)
    assert after.party_hp == (13, 0)
    assert after.party_moves == ((141, 48, 0, 0), (33, 39, 5, 55))
    assert simulation.stage == "field"


def test_promote_species_to_lead_normalizes_roles_after_healing() -> None:
    simulation = _PartyMenuSimulation(hp=(32, 46))
    simulation.species = [0x6B, 0xB3]
    simulation.moves = [(141, 48, 0, 0), (33, 39, 5, 55)]

    after = promote_species_to_lead(
        simulation,
        simulation,
        simulation,  # type: ignore[arg-type]
        0xB3,
        label="Cerulean role normalization",
    )

    assert after.party_species_ids == (0xB3, 0x6B)
    assert after.party_hp == (46, 32)
