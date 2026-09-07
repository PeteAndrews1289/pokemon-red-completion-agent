# Shared-experience compatibility repair — September7

Maintenance within the [varied-collection session](../work-sessions/2026-09-07-varied-collection-plan.md),
not new learning. CI runs34132340835 and34134485750 both failed on
`unreviewed Route 11 source drift: red.run-team-balancing`. The latter reported
1249passed and2skipped before its first-failure stop. The preceding two runs were
green. No gameplay failure or lost checkpoint is established by these CI logs.

## Reviewed semantic boundary

Compared executable9406200 against343fe7a. Exactly two attested elements changed:
the training routine and its module assignments. The new collection mode defaults
toFalse and requires an evolution target plus bounded quantum when enabled.
Every change to recipient/helper selection, venue selection, PP checks, cap
bypass, core ordering, XP checks and repeated-recovery handling is conditional
on that mode. WithFalse, the old branches remain: Blastoise is required, its cap
still applies, old PP/type guards and core ordering remain, and the new XP
verification returns without observing game state. New local bookkeeping and
boolean argument validation do not change historical calls.

The sole added module assignment is a move-effect exclusion set consumed only
by the new collection helpers. Existing assignments are unchanged. These helpers
are not part of the historical execution path. This does **not** attest that
shared-experience mode has the old curriculum's outcomes or costs.

Update the exact routine waiver and add an exact module-assignment waiver, with
specific reasons. Keep historical receipts immutable and unreviewed-drift,
loaded-versus-committed, false-bundle, stale-exception and module-constant mutation
rejections intact. No wildcard, ignored check, disabled workflow or rerun was added.

The legacy training test module now runs with all three new collection-only
helpers replaced by immediate failures and asserts the new mode defaultsFalse.
This executes the existing varied training paths while demonstrating they do not
depend on the new helpers. The separate collection tests still execute the new
mode, including actual-loop XP and recovery failures.

## Prevention and scope

Validation: full local ROM-free suite **7581passed,1skipped,1expected failure**
in1030.36seconds. The initial targeted run passed153 and exposed one additional
stale operational fingerprint; the full run passed after its reviewed update.
Legacy runtime tests execute with the new helpers unavailable; collection-mode
tests remain separate. Lint, changed-module typing, docs/focus and public-artifact
checks also passed. GitHub CI run34137137746 subsequently passed on exact repair
commitcde8f13d44920a33f658e1d4da4a5177bfac65fb. Later storage commits exposed a
separate observer-test expectation; see the varied-collection audit, not this
historical repair result, for the latest branch status.
The repair itself was bounded; the broader local verification took17minutes.

Include `test_red_party_development_venue_priors.py` whenever changing training
execution or module constants. Update reviewed fingerprints locally before a
push; a new hash is an identity assertion, not a semantic proof. The omitted
compatibility tests—not a GitHub outage—caused these two repeat notifications.
Retain CI and run broader regression once locally before publication.

S/model59,23living species and25specimens are unchanged by this repair. It
unblocks continued resource-aware collection; no sealed evaluation, teacher
campaign, full replay, new training row or advancement of stage exits is implied.
