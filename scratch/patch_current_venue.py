from pathlib import Path
content = Path("src/pokemon_red_completion/red_team_training.py").read_text()

old_logic = """            elif trainee is None:
                raise RuntimeError(
                    f"No provided venue suits {party.weakest_trainable_member.species_id} at level {party.weakest_trainable_member.level}."
                )
                current_venue = next(v for v in venues if v.band == target_band)"""

new_logic = """            elif trainee is None:
                raise RuntimeError(
                    f"No provided venue suits {party.weakest_trainable_member.species_id} at level {party.weakest_trainable_member.level}."
                )
            else:
                current_venue = next(v for v in venues if v.band == target_band)
"""
content = content.replace(old_logic, new_logic)

if "if current_venue is None:" not in content:
    content = content.replace(
        "            if decision.directive is TeamTrainingDirective.RESTORE_TEAM or escort_unsafe:",
        "            if current_venue is None:\n                current_venue = venues[0]\n            if decision.directive is TeamTrainingDirective.RESTORE_TEAM or escort_unsafe:"
    )

Path("src/pokemon_red_completion/red_team_training.py").write_text(content)
