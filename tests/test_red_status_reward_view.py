import json

import build_red_status_reward_view as view
import pytest


@pytest.mark.parametrize("key", ["schema", "inputs_sha256", "groups", "branches"])
def test_rescore_view_rejects_changed_source_or_labels(tmp_path, monkeypatch, key):
    expected = {"schema": view.SCHEMA, "inputs_sha256": "digest", "groups": [], "branches": []}
    monkeypatch.setattr(view, "build", lambda root: expected)
    path = tmp_path / "view.json"
    path.write_text(json.dumps(expected))
    assert view.validate_view(path, tmp_path) == expected
    path.write_text(json.dumps({**expected, key: "tampered"}))
    with pytest.raises(ValueError, match="authenticated measured branches"):
        view.validate_view(path, tmp_path)
