# Frozen strategic navigation registry fixture

These two files preserve the originally pinned public collection registry and
its digest byte-for-byte from commit `867f5ad468b5d071dea9c990f59fba87f19cccb9`.
They are historical identity fixtures, not current collection authorization.
The original registry SHA-256 is
`6af88b103febed5d9168efda2b5caf73baeea362cb5b57d13cdbd1a012cb83ec`.

The current prospective registry has a separate source-bound identity. Tests
retain these original pins and verify that current regeneration changes only
the executable source digest and the teacher digest derived from it. Neither
fixture access nor regeneration opens a sealed test root.
