import json
from dataclasses import asdict, replace
from types import SimpleNamespace as N

import pytest
from test_party_preparation import enemies, team
from test_red_post_battle_strategy import episode

from pokemon_red_completion import red_player_continuation as c
from pokemon_red_completion.party_preparation import PreparationPurpose, build_preparation_plan
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_post_battle_strategy import red_battle_aftermath


def test_earned_income_does_not_refund_prior_debits():
    before = dict(decisions=9, actions=1500, frames=99924, seconds=90.1, heals=2, cash_debits=1400)
    after = c.accumulate_player_costs(
        before,
        decisions=3,
        actions=20,
        frames=100,
        seconds=2.0,
        heals=1,
        cash_deltas=(800, -1386, 300),
    )
    assert after == dict(
        decisions=12, actions=1520, frames=100024, seconds=92.1, heals=3, cash_debits=2500
    )
    assert before["cash_debits"] == 1400


def test_optional_above_reference_plan_roundtrip_preserves_actual_quote_and_cap():
    from pokemon_red_completion.party_preparation import build_optional_preview_preparation_plan

    plan = build_optional_preview_preparation_plan(
        team(70, 32),
        (54, 53, 54, 56, 56),
        forecast_ref="authenticated-cartridge",
        maximum_level_gain=1,
        reference_mode="strongest",
        allow_above_reference=True,
    )
    restored = c._plan(json.loads(json.dumps(asdict(plan))))
    assert restored == plan
    assert restored.opposition_level == 56 and restored.above_reference_level_gain == 1
    assert dict(restored.targets)["specimen-1"] == 71


def test_legacy_preparation_document_without_optional_cap_preserves_default():
    plan = build_preparation_plan(team(5), enemies(10))
    document = asdict(plan)
    document.pop("above_reference_level_gain")
    restored = c._plan(json.loads(json.dumps(document)))
    assert restored == plan and restored.above_reference_level_gain == 0


@pytest.mark.parametrize("fault", [None, "unknown_species", "no_xp", "too_early", "no_authority"])
def test_evolution_retains_original_roles_and_targets(fault):
    old = team(15)[0]
    old = replace(old, observation=replace(old.observation, species_id=177, experience=3000))
    plan = build_preparation_plan((old,), enemies(20))
    current = replace(
        old,
        observation=replace(
            old.observation,
            species_id=1 if fault == "unknown_species" else 178,
            level=15 if fault == "too_early" else 16,
            experience=3000 if fault == "no_xp" else 3500,
        ),
    )
    edges = frozenset() if fault == "no_authority" else frozenset({(177, 178, 16)})
    if fault:
        with pytest.raises(ValueError):
            c.extend_preparation_roster(plan, (current,), evolution_edges=edges)
    else:
        after = c.extend_preparation_roster(plan, (current,), evolution_edges=edges)
        assert after == plan and after.roster[0].observation.species_id == 177


@pytest.mark.parametrize(
    "fault", [None, "missing_edge", "too_early", "no_xp", "regression", "unrelated", "cycle"]
)
def test_continuation_accepts_two_earned_level_evolutions_without_retargeting(fault):
    old = team(6)[0]
    old = replace(old, observation=replace(old.observation, species_id=177, experience=202))
    plan = build_preparation_plan((old,), enemies(14))
    current = replace(
        old,
        observation=replace(
            old.observation,
            species_id=1 if fault == "unrelated" else 28,
            level=35 if fault == "too_early" else (5 if fault == "regression" else 36),
            experience=202 if fault == "no_xp" else 40150,
        ),
    )
    edges = frozenset({(177, 179, 16), (179, 28, 36)})
    if fault == "missing_edge":
        edges = frozenset({(177, 179, 16)})
    elif fault == "cycle":
        edges = frozenset({(177, 179, 16), (179, 177, 36)})
    if fault:
        with pytest.raises(ValueError, match="regressed"):
            c.extend_preparation_roster(plan, (current,), evolution_edges=edges)
    else:
        assert c.extend_preparation_roster(plan, (current,), evolution_edges=edges) == plan
        assert plan.roster[0].observation.level == 6
        assert plan.roster[0].observation.species_id == 177
        assert plan.roster[0].observation.experience == 202
        assert plan.targets == (("specimen-1", 11),)


def fixture(monkeypatch):
    original = team(5)
    plan = replace(build_preparation_plan(original, enemies(10)), targets=(("specimen-1", 7),))
    current = team(7, 2)
    native = N(state=b"terminal", save_state_bytes=lambda: native.state)
    raw = N(player_money=1600, bag_items=((4, 5),))
    snapshot = dict(completed_objectives=["story"], party=[{"level": 7}])
    latched = []
    runtime = N(
        emulator=native,
        adapter=N(graph=N(objective=lambda _: N(completion_facts={"verified"}))),
        observer=N(latch_verified_facts=lambda facts: latched.append(facts)),
    )
    monkeypatch.setattr(c, "capture_player_lesson_snapshot", lambda _: (N(raw=raw), snapshot))
    monkeypatch.setattr(
        c,
        "PokemonRedPartyReader",
        lambda _: N(
            preparation_specimen_refs=lambda: tuple(m.specimen_ref for m in current),
            read=lambda: N(members=tuple(m.observation for m in current)),
        ),
    )
    costs = dict(decisions=9, actions=1500, frames=99924, seconds=90.1, heals=2, cash_debits=1400)
    payload = json.dumps(episode()).encode()
    from hashlib import sha256

    battle = red_battle_aftermath(payload, expected_sha256=sha256(payload).hexdigest())
    document = c.capture_player_continuation(runtime, preparation=plan, battle=battle, spent=costs)
    return runtime, plan, battle, document, raw, snapshot, latched


def test_json_roundtrip_preserves_original_target_history_cost_and_new_catch_role(monkeypatch):
    rt, plan, battle, doc, raw, snapshot, latched = fixture(monkeypatch)
    restored = c.restore_player_continuation(
        rt, json.loads(json.dumps(doc)), expected_sha256=canonical_sha256(doc)
    )
    assert restored.preparation.targets == plan.targets == (("specimen-1", 7),)
    assert restored.preparation.roster[0].observation.level == 5
    assert restored.preparation.roster[1].purpose is PreparationPurpose.UNDECIDED
    assert restored.battle == battle and restored.spent == doc["spent"]
    assert rt.emulator.save_state_bytes() == b"terminal" and raw.player_money == 1600
    assert latched == [frozenset({"verified"})]
    assert restored.search_memory is None  # Legacy context means untracked, not invented history.


def test_measured_search_memory_is_hash_bound_and_roundtrips(monkeypatch):
    from pokemon_red_completion.goal_search_memory import GoalSearchMemory

    rt, plan, battle, original, *_ = fixture(monkeypatch)
    memory = GoalSearchMemory()
    memory.record("paid-source", "a" * 64, exhausted=True, actions=30, frames=600)
    doc = c.capture_player_continuation(
        rt, preparation=plan, battle=battle, spent=original["spent"], search_memory=memory)
    restored = c.restore_player_continuation(
        rt, json.loads(json.dumps(doc)), expected_sha256=canonical_sha256(doc))
    assert restored.search_memory is not memory
    assert restored.search_memory.private_dict() == memory.private_dict()
    digest = canonical_sha256(doc)
    entry = next(iter(doc["search_memory"]["entries"].values()))
    entry["attempts"] += 1
    with pytest.raises(ValueError, match="identity"):
        c.restore_player_continuation(rt, doc, expected_sha256=digest)


def test_malformed_search_memory_fails_before_semantic_restoration(monkeypatch):
    rt, _plan, _battle, doc, _raw, _snapshot, latched = fixture(monkeypatch)
    doc["search_memory"] = {"schema": "unknown", "entries": {}}
    with pytest.raises(ValueError, match="memory schema"):
        c.restore_player_continuation(rt, doc, expected_sha256=canonical_sha256(doc))
    assert latched == [] and rt.emulator.save_state_bytes() == b"terminal"


@pytest.mark.parametrize("fault", [
    None, "undeclared", "missing", "duplicate", "regression", "species",
])
def test_resume_accepts_only_the_explicit_unique_native_boxed_loan(monkeypatch, fault):
    rt, plan, battle, document, _, _, _ = fixture(monkeypatch)
    old = plan.roster[0]
    guest = replace(old, specimen_ref="temporary-guest")
    monkeypatch.setattr(c, "PokemonRedPartyReader", lambda _: N(
        preparation_specimen_refs=lambda: (guest.specimen_ref,),
        read=lambda: N(members=(guest.observation,))))
    boxed = N(preparation_ref=old.specimen_ref, species_id=old.observation.species_id,
              level=old.observation.level, experience=1000)
    if fault == "regression":
        boxed.level -= 1
    if fault == "species":
        boxed.species_id += 1
    rt.reader = N(read_box_specimen_identities=lambda:
        () if fault == "missing" else (boxed, boxed) if fault == "duplicate" else (boxed,))
    allowed = frozenset() if fault == "undeclared" else frozenset({old.specimen_ref})
    if fault:
        with pytest.raises(ValueError, match="loan|undeclared"):
            c.restore_player_continuation(rt, document,
                expected_sha256=canonical_sha256(document), loanable_refs=allowed)
    else:
        restored = c.restore_player_continuation(rt, document,
            expected_sha256=canonical_sha256(document), loanable_refs=allowed)
        assert restored.preparation == plan
        assert restored.spent == document["spent"] and restored.battle == battle


@pytest.mark.parametrize("loan_index", range(6))
@pytest.mark.parametrize("reordered", (False, True))
def test_pending_loan_uses_logical_slots_without_adopting_guest_or_refreshing_roles(
    monkeypatch, loan_index, reordered
):
    rt, _, battle, old_document, *_ = fixture(monkeypatch)
    originals = team(5, 6, 7, 8, 9, 10)
    plan = build_preparation_plan(originals, enemies(20))
    document = c.capture_player_continuation(
        rt, preparation=plan, battle=battle, spent=old_document["spent"]
    )
    loaned = plan.roster[loan_index]
    retained = [m for m in originals if m.specimen_ref != loaned.specimen_ref]
    if reordered:
        retained.reverse()
    guest = replace(originals[0], specimen_ref="temporary-guest")
    live = tuple(
        replace(m, observation=replace(m.observation, slot=index))
        for index, m in enumerate((guest, *retained), 1)
    )
    monkeypatch.setattr(c, "PokemonRedPartyReader", lambda _: N(
        preparation_specimen_refs=lambda: tuple(m.specimen_ref for m in live),
        read=lambda: N(members=tuple(m.observation for m in live)),
    ))
    boxed = N(preparation_ref=loaned.specimen_ref, species_id=loaned.observation.species_id,
        level=loaned.observation.level, experience=loaned.observation.experience)
    rt.reader = N(read_box_specimen_identities=lambda: (boxed,))
    restored = c.restore_player_continuation(
        rt, document, expected_sha256=canonical_sha256(document),
        loanable_refs=frozenset({loaned.specimen_ref}),
    )
    assert restored.preparation.targets == plan.targets
    assert restored.preparation.budget == plan.budget
    by_ref = {m.specimen_ref: m for m in restored.preparation.roster}
    assert set(by_ref) == {m.specimen_ref for m in plan.roster}
    assert "temporary-guest" not in by_ref
    assert [m.observation.slot for m in restored.preparation.roster] == list(range(1, 7))
    for original in plan.roster:
        result = by_ref[original.specimen_ref]
        assert replace(result.observation, slot=original.observation.slot) == original.observation
        assert result.purpose == original.purpose
        assert result.milestone_level == original.milestone_level
    assert restored.spent == document["spent"] and restored.battle == battle
    assert rt.emulator.save_state_bytes() == b"terminal"


@pytest.mark.parametrize("fault", ["digest", "state", "cash", "bag", "lesson", "budget", "fit"])
def test_changed_continuation_refuses_without_inputs(monkeypatch, fault):
    rt, plan, battle, doc, raw, snapshot, _ = fixture(monkeypatch)
    digest = canonical_sha256(doc)
    if fault == "digest":
        digest = "0" * 64
    elif fault == "state":
        rt.emulator.state = b"other"
    elif fault == "cash":
        raw.player_money += 1
    elif fault == "bag":
        raw.bag_items = ((4, 6),)
    elif fault == "lesson":
        doc = json.loads(json.dumps(doc))
        snapshot["party"][0]["level"] += 1
    elif fault == "budget":
        doc["grants_new_budget"] = True
        digest = canonical_sha256(doc)
    else:
        doc["fit_allowed"] = True
        digest = canonical_sha256(doc)
    with pytest.raises(ValueError):
        c.restore_player_continuation(rt, doc, expected_sha256=digest)


@pytest.mark.parametrize("bad", [-1, True, float("nan")])
def test_invalid_spent_cost_cannot_reset_budget(monkeypatch, bad):
    rt, plan, battle, doc, *_ = fixture(monkeypatch)
    doc["spent"]["actions"] = bad
    with pytest.raises(ValueError):
        c.capture_player_continuation(rt, preparation=plan, battle=battle, spent=doc["spent"])


def test_removed_regressed_or_duplicate_roster_rejected():
    plan = build_preparation_plan(team(5), enemies(10))
    for current in ((), team(4), (team(7)[0], team(7)[0])):
        with pytest.raises(ValueError):
            c.extend_preparation_roster(plan, current)


def test_reordering_preserves_identity_roles_and_frozen_evidence():
    plan = build_preparation_plan(team(5, 6), enemies(10))
    current = tuple(
        replace(m, observation=replace(m.observation, slot=i))
        for i, m in enumerate(reversed(team(7, 8)), 1)
    )
    new = c.extend_preparation_roster(plan, current)
    assert new.targets == plan.targets
    assert [(m.specimen_ref, m.observation.slot, m.observation.level) for m in new.roster] == [
        ("specimen-2", 1, 6),
        ("specimen-1", 2, 5),
    ]


def test_live_menu_refresh_reuses_capture_extension_without_retargeting(monkeypatch):
    rt, plan, battle, doc, *_ = fixture(monkeypatch)
    refreshed = c.refresh_preparation_roster(rt.emulator, plan)
    assert refreshed.targets == plan.targets
    assert refreshed.budget == plan.budget
    assert refreshed.roster[0] == plan.roster[0]
    assert refreshed.roster[1].purpose is PreparationPurpose.UNDECIDED
    assert len(plan.roster) == 1
    after = c.capture_player_continuation(
        rt,
        preparation=refreshed,
        battle=battle,
        spent=doc["spent"],
    )
    assert after["spent"] == doc["spent"]
    assert after["battle"] == doc["battle"]
    assert after["state_sha256"] == doc["state_sha256"]


@pytest.mark.parametrize("current", [(), team(4), (team(7)[0], team(7)[0])])
def test_live_menu_refresh_rejects_missing_regressed_or_duplicate_members(monkeypatch, current):
    rt, plan, *_ = fixture(monkeypatch)
    monkeypatch.setattr(
        c,
        "PokemonRedPartyReader",
        lambda _: N(
            preparation_specimen_refs=lambda: tuple(m.specimen_ref for m in current),
            read=lambda: N(members=tuple(m.observation for m in current)),
        ),
    )
    with pytest.raises(ValueError):
        c.refresh_preparation_roster(rt.emulator, plan)
