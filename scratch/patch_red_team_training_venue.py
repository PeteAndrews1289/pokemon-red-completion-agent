from pathlib import Path

content = Path("src/pokemon_red_completion/red_team_training.py").read_text()

old_logic = """        if evolution_target is None:
            decision = plan_team_training(party, policy, progress)
            trainee = None
            target_band = None
            bands = [v.band for v in venues]
            trainable_members = [m for m in party.members if m.level < policy.minimum_level]
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
                )
            else:
                current_venue = next(v for v in venues if v.band == target_band)"""

new_logic = """        if evolution_target is None:
            decision = plan_team_training(party, policy, progress)
            trainee = None
            target_band = None
            bands = [v.band for v in venues]
            trainable_members = [m for m in party.members if m.level < policy.minimum_level]
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
                )
            
            if target_band is not None:
                current_venue = next(v for v in venues if v.band == target_band)
        
        if current_venue is None:
            # Fallback for evolution_target or when just starting with an unsafe team
            current_venue = venues[0]
"""

content = content.replace(old_logic, new_logic)

# In test_a_wrong_venue_stops_early_and_names_the_band, the failure is "Team training stopped before readiness: healing budget exhausted".
# This happens because the initial team is unsafe (hp=30 is below retreat ratio), so it tries to heal.
# It goes to `heal_and_return`, which is a no-op in the mock, and then tests loops again, but since it's a mock, hp doesn't change, so it heals 40 times and exhausts the budget.
# Wait, why did the old code fail with "Training venue does not match"?
# Because the old code didn't check `escort_unsafe` before entering battle?
# Ah! The old code HAD `escort_unsafe` check inside the battle entry loop!
# Yes! `if escort_unsafe` was checked AFTER finding a battle!
# Let me look at where `escort_unsafe` is defined.

Path("src/pokemon_red_completion/red_team_training.py").write_text(content)
