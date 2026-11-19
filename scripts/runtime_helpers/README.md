# Maintained native helper overrides

These two files mirror the exact F92 runtime helpers. The supported-departure
quote repair is maintained here because this checkout is the editable source.
The frozen package builder copies them into its declared helpers directory and
pins their exact bytes. Other legacy helpers retain their separate frozen
provenance; this does not establish whole-Code parity.

The repair changes read-only transport quoting. It does not execute a route,
choose a goal, add a priority, change a model, or bypass native route guards.
ROM-free quote regressions load these exact source functions. The normal frozen
runner imports the packaged helpers and verifies their hashes.
