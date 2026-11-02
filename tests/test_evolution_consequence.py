"""ROM-free prospective V2 boundaries; never relabel a real failed attempt."""

import copy
from collections import Counter
from dataclasses import replace

import pytest
from test_challenge_consequence import documents

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_challenge_consequence import (
    ChallengeConsequenceSpec,
    project_consequence,
)
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.red_player_evolution_lesson import (
    _known_edges,
    evolution_lesson_contract,
    validate_evolution_lesson_contract,
)
from pokemon_red_completion.red_safari_training_setup import RED_ROM_SHA256
from pokemon_red_completion.registered_checkpoint import RegisteredCollectionCheckpoint


def contract():
    return dict(
        schema="pokemon.red.evolution-lesson.v1",
        cartridge_sha256=RED_ROM_SHA256,
        level_edges=[list(e) for e in sorted(_known_edges())],
    )


def bind_registration(document, snapshot, *, inherited=(), protected=()):
    # Build the complete immutable checkpoint at once; no temporarily invalid object.
    old = RegisteredCollectionCheckpoint.from_public(document["registration"])
    counts = tuple(
        sorted(
            Counter(
                red_species_ref(red_internal_species_number(m["species_id"]))
                for m in snapshot["party"]
            ).items()
        )
    )
    local = tuple(sorted(set(dict(counts)) | set(inherited)))
    missing = tuple(sorted(set(old.target_species) - set(local)))
    ledger = {
        "schema": "pokemon.core.registered-physical-ledger.v1",
        "counts": counts,
        "local": local,
        "global": local,
    }
    cp = replace(
        old,
        specimen_counts=counts,
        global_species=local,
        local_species=local,
        protected_counts=protected,
        registered_species=len(set(local) & set(old.target_species)),
        living_species=len(counts),
        retained_captures=sum(n for _, n in counts),
        required_specimens_remaining=len(missing),
        required_specimens_sha256=canonical_sha256(
            dict(schema="pokemon.core.missing-registrations.v1", missing=missing)
        ),
        specimen_ledger_sha256=canonical_sha256(ledger),
    )
    result = copy.deepcopy(document)
    result["registration"] = cp.public_dict()
    return result


def evolving_documents(tmp_path, monkeypatch):
    plan, phases, _ = documents(tmp_path, monkeypatch)
    plan["schema"] = "pokemon.red.challenge-consequence-plan.v2"
    plan["spec"] = replace(
        ChallengeConsequenceSpec.from_document(plan["spec"]), evolution_contract=contract()
    ).document()
    before = plan["before"]
    before["lesson"]["party"][0]["species_id"] = 165
    before["observation"] = bind_registration(before["observation"], before["lesson"])
    inherited = before["observation"]["registration"]["local_species"]
    phases[0]["before"] = copy.deepcopy(before)
    after = phases[0]["after"]
    after["lesson"]["party"][0]["species_id"] = 166
    after["observation"] = bind_registration(
        after["observation"], after["lesson"], inherited=inherited
    )
    phases[1]["before"] = copy.deepcopy(after)
    terminal = phases[1]["after"]
    terminal["lesson"]["party"][0]["species_id"] = 166
    terminal["observation"] = bind_registration(
        terminal["observation"], terminal["lesson"], inherited=inherited
    )
    return plan, phases


def test_v2_legal_evolution_and_legacy_v1_rejection(tmp_path, monkeypatch):
    plan, phases = evolving_documents(tmp_path, monkeypatch)
    row = project_consequence(plan, phases)
    assert row.outcome.attempted and not row.outcome.completed
    assert row.outcome.actions == 120
    old = copy.deepcopy(plan)
    old["schema"] = "pokemon.red.challenge-consequence-plan.v1"
    old["spec"].pop("evolution_contract")
    old["spec"]["schema"] = "pokemon.red.challenge-consequence-spec.v1"
    with pytest.raises(ValueError, match="lost or substituted"):
        project_consequence(old, phases)


@pytest.mark.parametrize(
    "fault",
    [
        "substitute",
        "identity",
        "lost",
        "xp",
        "level",
        "early",
        "fake_flag",
        "lost_flag",
        "physical",
        "reserve",
        "binding",
        "restore_evolution",
        "table",
        "version",
        "hm",
        "coherent_extra_flag",
    ],
)
def test_v2_rejects_unearned_or_unretained_evolution(tmp_path, monkeypatch, fault):
    plan, phases = evolving_documents(tmp_path, monkeypatch)
    after = phases[0]["after"]
    member = after["lesson"]["party"][0]
    if fault == "substitute":
        member["species_id"] = 150
    elif fault == "identity":
        member["specimen_ref"] = "red-preparation:" + "f" * 64
    elif fault == "lost":
        after["lesson"]["party"].pop()
    elif fault == "xp":
        member["experience"] = 0
    elif fault == "level":
        member["level"] = 19
    elif fault == "early":
        plan["before"]["lesson"]["party"][0]["species_id"] = 177
        member["species_id"] = 28  # Squirtle cannot jump straight to Blastoise.
    elif fault == "fake_flag":
        after["observation"]["registration"]["local_species"].append("red-species-151")
    elif fault == "lost_flag":
        after["observation"]["registration"]["local_species"].pop()
    elif fault == "physical":
        after["observation"]["registration"]["specimen_counts"] = []
    elif fault == "reserve":
        after["observation"]["registration"]["protected_counts"] = [[red_species_ref(19), 1]]
    elif fault == "binding":
        after["observation"]["registration"]["binding_sha256"] = "e" * 64
    elif fault == "restore_evolution":
        phases[0]["kind"] = "restore_team"
    elif fault == "table":
        plan["spec"]["evolution_contract"]["level_edges"].append([165, 150, 1])
    elif fault == "version":
        plan["schema"] = "pokemon.red.challenge-consequence-plan.v1"
    elif fault == "hm":
        plan["before"]["lesson"]["party"][0]["moves"][0][0] = 15
        phases[0]["before"] = copy.deepcopy(plan["before"])
    elif fault == "coherent_extra_flag":
        after["observation"] = bind_registration(
            after["observation"],
            after["lesson"],
            inherited=(
                *plan["before"]["observation"]["registration"]["local_species"],
                red_species_ref(151),
            ),
        )
    phases[1]["before"] = copy.deepcopy(after)
    with pytest.raises(ValueError):
        project_consequence(plan, phases)


def test_cartridge_contract_rejects_wrong_rom_and_forged_edges():
    with pytest.raises(ValueError):
        evolution_lesson_contract(b"not a cartridge")
    assert validate_evolution_lesson_contract(contract()) == _known_edges()
    forged = contract()
    forged["cartridge_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        validate_evolution_lesson_contract(forged)


def test_true_species_reserve_cannot_be_removed_for_evolution(tmp_path, monkeypatch):
    plan, phases = evolving_documents(tmp_path, monkeypatch)
    before = plan["before"]
    before["observation"] = bind_registration(
        before["observation"], before["lesson"], protected=((red_species_ref(19), 1),)
    )
    phases[0]["before"] = copy.deepcopy(before)
    with pytest.raises(ValueError, match="reserves"):
        project_consequence(plan, phases)
    with pytest.raises(ValueError, match="protected physical stock"):
        bind_registration(
            phases[0]["after"]["observation"],
            phases[0]["after"]["lesson"],
            inherited=before["observation"]["registration"]["local_species"],
            protected=((red_species_ref(19), 1),),
        )


def test_native_recorder_v2_roundtrip(tmp_path, monkeypatch):
    from test_native_challenge_consequence import harness, session

    import pokemon_red_completion.red_challenge_consequence as consequence
    import pokemon_red_completion.red_native_player as native
    import pokemon_red_completion.red_player_lesson_runtime as lesson

    args, state = harness(tmp_path, monkeypatch, fault="win")
    original = consequence.capture_player_lesson_snapshot
    inherited = []

    def capture(rt):
        observation, snapshot = original(rt)
        snapshot["party"][0]["species_id"] = 166 if state["trained"] else 165
        document = bind_registration(observation.public_dict(), snapshot, inherited=inherited)
        if not inherited:
            inherited.extend(document["registration"]["local_species"])
        observation.public_dict = lambda: copy.deepcopy(document)
        return observation, snapshot

    for module in (consequence, native, lesson):
        monkeypatch.setattr(module, "capture_player_lesson_snapshot", capture)
    args["consequence_spec"] = replace(args["consequence_spec"], evolution_contract=contract())
    s = session(args)
    for ordinal, kind in enumerate((GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY)):
        options = s.observe(ordinal)
        binding = next(b for b in options.bindings if b.kind is kind)
        binding.verify(binding.execute())
    recorded = s.consequence.finish()
    assert recorded["error"] is None
    row = consequence.load_challenge_consequence(
        args["store"],
        declaration_sha256=recorded["declaration_sha256"],
        result_sha256=canonical_sha256(recorded),
    )
    assert row.outcome.completed and row.outcome.actions == 3 and row.outcome.restorations == 1
