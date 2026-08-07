from pathlib import Path
import re

content = Path("src/pokemon_red_completion/red_team_training.py").read_text()

old_logic = r'''        if evolution_target is None:
            decision = plan_team_training\(party, policy, progress\)
            trainee = party.weakest_trainable_member
            if trainee is None:
                pass # decision will be STOP
            else:
                target_band = choose_grinding_area\(\[v.band for v in venues\], trainee, policy\)
                if target_band is None:
                    raise RuntimeError\(
                        f"No provided venue suits \{trainee.species_id\} at level \{trainee.level\}."
                    \)'''

new_logic = '''        if evolution_target is None:
            decision = plan_team_training(party, policy, progress)
            trainee = None
            target_band = None
            bands = [v.band for v in venues]
            trainable_members = [m for m in party.members if m.can_train_in_party_battle(policy)]
            for member in sorted(trainable_members, key=lambda m: (m.level, m.slot)):
                band = choose_grinding_area(bands, member, policy)
                if band is not None:
                    trainee = member
                    target_band = band
                    break
            
            if not trainable_members:
                pass # decision will be STOP
            elif trainee is None:
                raise RuntimeError(
                    f"No provided venue suits {party.weakest_trainable_member.species_id} at level {party.weakest_trainable_member.level}."
                )'''

# Using regex replace
content = re.sub(old_logic, new_logic, content)

Path("src/pokemon_red_completion/red_team_training.py").write_text(content)
