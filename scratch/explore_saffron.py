import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path("src").resolve()))

from pokemon_red_completion.cartridge import Cartridge
from pokemon_red_completion.emulator import Emulator
from pokemon_red_completion.state import PokemonRedStateReader
from pokemon_red_completion.actions import _directions, _move
from pokemon_red_completion.fuchsia import _CountingExecutor
import json

class DummyChapterExecutor:
    def execute(self, action):
        self.emulator.step(action)
        self.emulator.step(None)

def main():
    cart = Cartridge(Path("/Users/peterandrews/Downloads/Pokemon - Red Version (UE)[!]/Pokemon Red.gb").read_bytes())
    emu = Emulator(cart)
    reader = PokemonRedStateReader(emu)
    # We don't have a save state at Saffron center right now easily?
    # Wait, test_saffron.py might load a state.
    pass

if __name__ == "__main__":
    main()
