"""Teacher-only contrast declarations preserve old and held-out boundaries."""
import pytest
from pokemon_red_completion.red_teacher_venue import workload_trainee_species

CASES = [('geodude30_to31',169,39,30,True),('geodude40_to41',169,39,40,True),('machop30_to31', 106, 41, 30, True), ('machop40_to41', 106, 41, 40, True), ('machop35_to36', 106, 41, 35, False), ('sandshrew30_to31', 96, 97, 30, True), ('sandshrew40_to41', 96, 97, 40, True), ('poliwag30_to31', 71, 110, 30, True), ('poliwag40_to41', 71, 110, 40, True), ('poliwag35_to36', 71, 110, 35, False)]

@pytest.mark.parametrize("profile,source,target,level,train_allowed", CASES)
def test_exact_fixture_scope(profile,source,target,level,train_allowed):
    item=dict(trainee_profile=profile,fixture_level=level)
    assert workload_trainee_species(item,validation=True)==(source,target)
    if train_allowed:
        assert workload_trainee_species(item,validation=False)==(source,target)
    else:
        with pytest.raises(ValueError):workload_trainee_species(item,validation=False)
    for wrong in (True,str(level),level-1,level+1,None):
        with pytest.raises(ValueError):workload_trainee_species(dict(item,fixture_level=wrong),validation=True)


def test_existing_teacher_profiles_and_defaults_are_unchanged():
    assert workload_trainee_species({},validation=False)==(59,118)
    assert workload_trainee_species(dict(trainee_profile="drowzee30_to31",fixture_level=30),validation=False)==(48,129)
    with pytest.raises(ValueError):workload_trainee_species(dict(trainee_profile="dragonair54_to55",fixture_level=54),validation=False)
    assert workload_trainee_species(dict(trainee_profile="dragonair54_to55",fixture_level=54),validation=True)==(89,66)
    with pytest.raises(ValueError):workload_trainee_species(dict(trainee_profile="unknown",fixture_level=30),validation=True)


def test_diversity_target_uses_exact_declared_source_census_without_old_species_assumption():
    from dataclasses import asdict, replace
    from pokemon_red_completion.party import PartyObservation, PartyMemberObservation
    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_teacher_venue import workload_fixture_target
    party = PartyObservation((PartyMemberObservation(slot=1,species_id=118,level=55,hp=80,max_hp=118),))
    item=dict(trainee_profile="machop30_to31",fixture_level=30,fixture_source_slot=1,
              fixture_source_party_sha256=canonical_sha256(asdict(party)))
    assert workload_fixture_target(party,item,high_level=True) is party.members[0]
    for fault in [dict(fixture_source_slot=True),dict(fixture_source_slot=2),dict(fixture_source_party_sha256="0"*64),dict(fixture_source_party_sha256=None)]:
        with pytest.raises(ValueError):workload_fixture_target(party,dict(item,**fault),high_level=True)
    with pytest.raises(ValueError):workload_fixture_target(party,item,high_level=False)
    with pytest.raises(ValueError):workload_fixture_target(replace(party,members=(replace(party.members[0],hp=79),)),item,high_level=True)
    legacy=PartyObservation((PartyMemberObservation(slot=1,species_id=59,level=22,hp=37,max_hp=37),))
    assert workload_fixture_target(legacy,{},high_level=True)==legacy.members[0]
    with pytest.raises(AssertionError):workload_fixture_target(party,{},high_level=True)


def test_teacher_rejects_version_ineligible_target_using_cartridge_identity():
    from types import SimpleNamespace as NS
    from pokemon_red_completion.red_teacher_venue import require_workload_collection_target
    cartridge=NS(species=lambda internal: NS(national_number={97:28,41:67,110:61}[internal]))
    with pytest.raises(ValueError,match="outside the Red completion contract"):
        require_workload_collection_target(cartridge,97)
    require_workload_collection_target(cartridge,41)
    require_workload_collection_target(cartridge,110)
