import hashlib

from pokemon_red_completion.living_dex_paired_development import private_failure_diagnostic


def test_nested_policy_failure_retains_actual_cause_without_private_paths():
    try:
        try:
            raise ValueError("unfit active member cannot safely take another turn")
        except ValueError as cause:
            raise RuntimeError("trainer policy rejected") from cause
    except RuntimeError as error:
        report = private_failure_diagnostic(error)
    assert report["message"] == "trainer policy rejected"
    assert report["causes"][0]["exception_type"] == "ValueError"
    assert report["causes"][0]["message"] == "unfit active member cannot safely take another turn"
    assert report["cause_chain_truncated"] is False
    assert all("/" not in f["module_file"] for f in report["causes"][0]["frames"])
    secret = "file:/private/task-specific-fixture"
    inner = ValueError(secret)
    outer = RuntimeError("wrapped")
    outer.__cause__ = inner
    nested = private_failure_diagnostic(outer)["causes"][0]
    assert secret not in nested["message"]
    assert nested["message_sha256"] == hashlib.sha256(secret.encode()).hexdigest()


def test_cause_collection_is_bounded_and_cycle_safe():
    root = RuntimeError("root")
    previous = root
    for i in range(12):
        previous.__cause__ = ValueError(str(i))
        previous = previous.__cause__
    report = private_failure_diagnostic(root)
    assert len(report["causes"]) == 6 and report["cause_chain_truncated"] is True
    root.__cause__ = root
    assert "causes" not in private_failure_diagnostic(root)
