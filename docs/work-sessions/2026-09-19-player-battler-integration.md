# September19: frozen battler integration checkpoint

## Outcome

Frozen J is explicitly connected to ordinary trainer funding in the main-player runtime.
The first direct prepared-entry probe exercised four learned choices, then FAILED after
Wartortle fainted. The unchanged no-faints funding guard stopped the unfinished battle
before replacement. Wiring and failure retention are verified; successful funding is not.

[Machine-readable evidence](../evidence/red-player-battler-integration-2026-09-19.json).

## Implemented

- Authenticated per-run frozen J model binding; no global override or teacher fallback.
- Shared player action/frame budgets and decision-time preservation checks.
- Durable initial/final battle saves and hash-linked choice/timing logs, including failures.
- One-to-three own-party scope; larger learned funding offers fail closed before travel.
- Ordinary Potion/Super Potion recovery amounts in the shared field-item executor.
- Primitive controller forwarding remains inside the executor module.

The default player, wild captures and Elite Four controllers are unchanged. The test invoked
the same main-player prepared trainer entry directly; it did not execute Model137's high-level
selector or claim that its conservative funding eligibility admitted this early-game party.

## Single consumed live goal

Source commit:e676847010a61953372a4200dbe5d7aa07380cb2.
Private run:red-player-battler-checkpoint-20260919-v1.
The earned boot3100 endpoint was the source, not the main96-registration collection save.

| Measure | Result |
| --- | --- |
| Normal preparation |3owned Potions; HP12/12→28/51 |
| Route |78same-map cartridge-derived steps |
| New opponent |One level16 trainer Pokémon; quoted480cash |
| Model decisions |4:1voluntary switch,3attacks |
| Mean policy time |1.160094ms |
| Total cost |247controller actions,19,284frames |
| Terminal |Funding goal failed; battle unfinished;1party faint |
| Actual resources |HP28/0,enemyHP18,1706cash;0payout |
| Retention |19hash-chained events,4complete decisions; both final saves match |
| Read-only reopening |Fresh ledger matches;0actions,0frames |
| Resets / memory edits / fits |0 / 0 / 0 |

No success, completed-battle loss, new independent origin, fit or collection gain is claimed.
The no-faints guard ran before a replacement decision, so this did not test J's ability to
finish from the reserve. The consumed source must not be replayed or fitted as TRAIN.

## Verification and publication

The first broad run passed12,524tests with13failures and1expected failure. Seven failures
were the pre-existing dashboard receipt-format mismatch; one was the live bridge's controller
forwarding location; three registry checks raced ongoing source edits; one was a stale battle
module golden digest; one was an older exact-Mac-runtime fingerprint qualification.

The relevant controller boundary and dashboard projection were corrected without weakening
their assertions. The historical dashboard receipt remains135examples, not the current137:
its measured-fit projection does not invent a native action trace or policy replay.
The timing golden was refreshed for the already-tested faint/sleep/move-learning changes.
The old exact-runtime qualification remains unchanged and unavailable in this relocated setup.
Final stable-source verification is recorded below.

Pete explicitly authorized this integration/documentation GitHub checkpoint. Current README,
handoffs, architecture, roadmap, narratives, portfolio/interview material and setup guidance
were refreshed. Historical reports and training evidence were not rewritten. No ROM, state,
model, dataset or private machine path is published. Future pushes remain user-controlled.

### Final stable-source verification

On commit eee30ee1, the ROM-free suite completed with **12,562 passed,1expected failure**
in19minutes38seconds. The only explicit test-name exclusion was
test_exact_local_mac_runtime_identity_qualification; its obsolete local environment
fingerprint still fails in this installation, and its assertion was not changed.
The private-ROM integration marker was excluded as usual. One SDL2 library warning
was emitted. This is a passing scoped suite, not a claim that the excluded qualification passes.

Ruff passed; mypy passed across542source files. Documentation, product-focus, public-artifact
and generated-registry checks passed. The86-test targeted documentation/registry/integration
run also passed. Unpublished Git history was scanned for private artifact suffixes, home paths
and recognized secret patterns with no findings; this is not a universal secret-detection claim.

Registry SHA256:ec01c9ecf9a178f169c55d38dcbb26ca372d97f4c058ca0a47d6d3c5d8f2069d.
Executable source bundle:8c7847db6f9801f7461950392eb2eba64617a8a126c6a7d7f56737d6eef308f5.
The subsequent closeout change is documentation only. Publication target is the existing
codex/model115-frozen-resupply-20260913 branch and its open pull request244, not a merge or release.
Local results do not claim that the newly triggered hosted CI has completed.

## Next step, not another trainer review

Separate general learned-battle completion/recovery from strict no-faint funding acceptance.
A new prospective continuation may begin at the exact failed endpoint while retaining prior
costs and the original failed-goal verdict. Do not reset the encounter, silently relax payout
or specimen checks, or relabel development data as training.

Model137 remains137examples/92successes/58economy-qualified; main Red save96/124,74specimens,
198cash. Frozen J still has318TRAIN contexts. Fresh-run acceptance remains0/5.
Gameplay stopped. No Flash or Claude was used; no external review is pending.
Next:Astra High, Fast off;45–60minutes for lifecycle judgment and bounded validation.
