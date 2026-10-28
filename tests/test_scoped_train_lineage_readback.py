"""Opt-in retained native evidence; no emulator, originals remain untouched."""
import json
import os
from pathlib import Path
import pytest
from pokemon_red_completion import red_scoped_training_battlers as scoped
from pokemon_red_completion import red_challenge_consequence as consequence
from pokemon_red_completion.battle_scenario_capture import (
    BattleScenarioCaptureManifest, parse_battle_scenario_capture_manifest,
)
from pokemon_red_completion.provenance import canonical_sha256
from test_scoped_train_consequence_readback import _arguments


def fixture():
    raw = os.environ.get("POKEMON_TRAIN_CONSEQUENCE_FIXTURES")
    if raw is None:
        pytest.skip("retained private TRAIN fixtures not explicitly supplied")
    return Path(json.loads(raw)["direct"])


def test_real_capture_and_reader_share_exact_canonical_source(monkeypatch):
    case = fixture(); store, kwargs = _arguments(case)
    source = json.loads((case / "native/consequence-plan.json").read_bytes())["source"]
    declaration = json.loads((case / "scoped-battles/declaration.json").read_bytes())
    canonical = scoped.scoped_train_root_lineage_id(source["origin_sha256"])
    original = scoped.scoped_train_root_lineage_id
    calls = []
    def observed(origin):
        calls.append(origin)
        return original(origin)
    monkeypatch.setattr(scoped, "scoped_train_root_lineage_id", observed)
    loaded = consequence.load_scoped_train_challenge_consequence(store, **kwargs)
    assert calls == [source["origin_sha256"]]
    assert declaration["root_lineage_id"] == canonical
    actor = next(a for a in declaration["actors"] if a["scope"] == "story"
                 and a["contract"]["defeated_event"] == kwargs["expected_story_contract"].defeated_event)
    payload = (case / "scoped-battles" / ("actor-%03d" % actor["index"])
               / "battle-0001/initial.state.json").read_bytes()
    manifest = parse_battle_scenario_capture_manifest(payload)
    assert type(manifest) is BattleScenarioCaptureManifest
    assert manifest.root_lineage_id == canonical
    assert manifest.source_state_sha256 == source["state_sha256"]
    assert manifest.source_commit == source["source_commit"]
    recorded = json.loads((case / "native/consequence-result.json").read_bytes())
    assert canonical_sha256(loaded.row.document()) == canonical_sha256(recorded["row"])
    assert not loaded.row.outcome.completed
    assert json.loads((case / "RESULT.json").read_bytes())["passed"] is False
    assert json.loads((case / "TERMINAL-AUTHENTICATION.json").read_bytes())["passed"] is False


def test_human_alias_not_accepted_even_with_fresh_declaration_digest(monkeypatch):
    case = fixture(); store, kwargs = _arguments(case)
    target = case / "scoped-battles/declaration.json"
    original = Path.read_bytes
    changed = json.loads(original(target)); changed["root_lineage_id"] = "human-training-origin"
    kwargs["expected_scoped_declaration_sha256"] = canonical_sha256(changed)
    def read(path):
        return json.dumps(changed).encode() if path == target else original(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="declaration authority differs"):
        consequence.load_scoped_train_challenge_consequence(store, **kwargs)
