import re
from pathlib import Path

content = Path("tests/test_red_team_training.py").read_text()

if "from pokemon_red_completion.training_venue import TrainingVenue" not in content:
    content = content.replace("from pokemon_red_completion.red_team_training import run_red_team_balancing", "from pokemon_red_completion.training_venue import TrainingVenue\nfrom pokemon_red_completion.red_team_training import run_red_team_balancing")

Path("tests/test_red_team_training.py").write_text(content)
