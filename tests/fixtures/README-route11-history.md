# Historical venue test evidence

[The fixture](route11-historical-source.json) preserves the observed Route 11
source elements from commit `00499bc68b099ffcd0125a6777bc3b836a84ff0b`, the exact
reviewed `run_red_team_balancing` function from commit
`ba9d32c9b84a1eefedce438023e9637b6d77f868`, and measured Cave runtime digests.
These development commits are absent from public snapshot ancestry.

The complete fixture is independently hash-pinned in
[the test adapter](../route11_historical_fixture.py). It records original source
paths, blob identities, byte counts and SHA-256 hashes. Eight source projections
retain every declared historical definition and top-level assignment; unrelated
code is omitted. Production AST parsing must reproduce all 55 original observed
rows. The reviewed balancer retains its exact function bytes and unchanged
production predecessor AST pin. The original full source-bundle identity remains
receipt evidence; the selected projections are not a complete source bundle.

Only historical reads in the attestation tests use this adapter. Current
committed source, loaded-code identities, closure and waiver checks remain real.
Historical blob-mutation tests still pass through the production parser and
reject drift. The Cave digest fixture preserves the assertion that current
runtime cannot inherit historical measurement authority.

These are public test fixtures, never runtime authorization, gameplay inputs,
training outcomes, a replay or proof of new native success.
