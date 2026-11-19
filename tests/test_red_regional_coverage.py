from pokemon_red_completion.red_regional_coverage import diversify_regional_sources


def test_survey_comparison_uses_distinct_missing_species_and_retains_every_source():
    ranked = (("near",1), ("duplicate",2), ("guarded",3), ("different",4), ("tied",5))
    missing = {1:{"a","b"},2:{"a","b"},3:{"c","d","e","f"},4:{"b","c","d"},5:{"e","f"}}
    changed, choice = diversify_regional_sources(ranked, missing, {1,2,4,5})
    assert [name for name,_ in changed] == ["near","different","duplicate","guarded","tied"]
    assert sorted(changed) == sorted(ranked)
    assert choice["additional_species"] == ["c","d"]
    assert choice["distinct_at_alternate"] == 3
    assert (choice["original_rank"],choice["comparison_rank"]) == (4,2)


def test_exhausted_overlap_and_unknown_access_do_not_invent_complementary_survey():
    ranked = (("empty",0),("near",1),("overlap",2),("blocked",3))
    missing = {1:{"a","b"},2:{"b"},3:{"c"}}
    assert diversify_regional_sources(ranked, missing, {0,1,2}) == (ranked,None)
    assert diversify_regional_sources(ranked, {}, {0,1,2,3}) == (ranked,None)
