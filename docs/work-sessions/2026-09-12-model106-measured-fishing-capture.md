# Model106 measured fishing capture

## Mission check

The North Star remains a transferable hierarchical Pokémon player that completes stories and adds
legitimate registrations to one shared Pokédex. This session advanced the Red collection loop with a
generic fishing decision and made the earned state reusable. It did not execute Crystal, replay the
full game, add a named-species route or claim fresh-game autonomy.

## Live result

From the 80-registration model105 state, cartridge data identified 33 productive fishing maps. Nine
were physically reachable with current field capabilities; the nearest eight became identity-free
feature rows. Model105 sampled candidate5. That choice, rather than an operator-selected fallback,
controlled the played attempt.

Generic routing executed 336 steps and handled three wild interruptions. The fishing controller made
11 Super Rod casts: nine no-bites and two encounters. It fled one already-covered encounter and
captured one missing species. The Pokédex verifier observed **80→81 registrations**.

- Controller actions: **802**
- Emulator frames: **54,384**
- Captures: **1**
- Living species: **60**
- Physical specimens: **65**
- Teacher labels: **0**

## Learning and restart result

A read-only observer reconstructed the exact before/after registration states and replayed the
model105 sample without pressing controls or advancing a frame. The measured-choice admission bound
the declaration, claim, result, menu, model, state endpoints and costs. The fitter retained all 105
prior examples and added exactly one training row, producing **model106 with 106 examples**.

The terminal was then published as
`red-model106-fishing-measured-terminal-v2-20260912`, checkpoint record SHA-256
`2571f6c85fd2bfdbddec7945bbed386c62018f9326de54454f34b97216286595`. It reopened with
the exact terminal bytes and collection using zero publication actions and zero publication frames.

## Engineering result

The existing measured-choice contract was Safari-specific. It now validates the frozen fishing
declaration while preserving the same lower-trust restrictions. A second issue appeared during
restart publication: the lineage contract supported measured→support but rejected the next
support→measured transition. The contract now permits an alternating measured/support chain only
after recursively authenticating every preceding join. Support-on-support and measured-on-measured
chains remain rejected. A full integration test constructs and reopens this alternating sequence.

## Trust and review

The fishing harness retained exact states and aggregate costs but no standard per-action journal.
The new row is therefore training-only, action-trace unavailable, independent-evaluation false and
authority-promotion ineligible.

Claude correctly identified the weak destination ranking: the model assigned little probability to
a nearby candidate with more productive slots and selected a long one-target route. That is evidence
for more varied outcomes, not a reason to discard the observed success. Claude's menu-geometry
concern and Flash's recommendation to revert the bounds were rejected because direct exact-save
measurements and the successful live cast validate the current geometry. Flash correctly endorsed
the composition and the need for multiple future outcomes.

## Verification and reorientation

The measured-choice gate passed 23 focused tests. The alternating restart contract passed 13 direct
tests and 111 broader checkpoint/support tests. The product-state and dashboard consolidation passed
135 focused tests. Repository-wide documentation, public-artifact, registry, Ruff and mypy checks
passed. GitHub CI run `34714403115` completed successfully. A local non-integration run passed
11,405 tests with one expected xfail after excluding one unrelated Mac-only runtime-identity test:
the installed PyBoy `RECORD` metadata no longer matches that old preflight's frozen local hash. The
hash was not silently reauthorized as part of this learning change.

The next falsifier is simple: if model106 cannot reopen the 81-registration state and expose at least
two useful remaining executable fishing alternatives, this lane stops. Otherwise, collect one more
bounded model-selected destination outcome and preserve success or failure. Several varied outcomes
are required before the fishing ranking can be called useful; Blue, modified Red and Crystal remain
later stages.

[Sanitized evidence](../evidence/red-model106-measured-fishing-capture-2026-09-12.json)

Recommended next-session model: **GPT-5.6 Sol High**, Fast enabled when available. This is bounded
implementation and live-result inspection; reserve Astra High/Max for a later promotion or transfer
architecture review.
