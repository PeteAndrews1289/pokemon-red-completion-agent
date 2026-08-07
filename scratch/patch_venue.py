from pathlib import Path
content = Path("src/pokemon_red_completion/red_team_training.py").read_text()

# Find the block where `trainee` is resolved and we can set `current_venue`.
# Specifically, we want to replace `current_venue = next(v for v in venues if v.band == target_band)`
# with `if target_band is not None: current_venue = next(v for v in venues if v.band == target_band)`
# and then add the fallback.

if "current_venue = venues[0]" not in content:
    content = content.replace(
        "            if decision.directive is TeamTrainingDirective.RESTORE_TEAM or escort_unsafe:",
        "            if current_venue is None:\n                current_venue = venues[0]\n\n            if decision.directive is TeamTrainingDirective.RESTORE_TEAM or escort_unsafe:"
    )

Path("src/pokemon_red_completion/red_team_training.py").write_text(content)
