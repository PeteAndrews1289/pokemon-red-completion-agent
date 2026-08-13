# External audit handoff: directional-warp repair and hard live qualification

This is a pre-authorization audit. Do not open, enumerate, hash, preflight, materialize or score a
sealed test capture. Do not create an owner authorization receipt. The sealed counter is **0/12**.

## Why schema v8 exists

Schema v7 was published at commit `b640ecb1c140eff120196b0ad6f7702f2068d0e9`. Its first explicit
non-test qualification passed a Celadon-to-Saffron relocation with no teacher action and zero test
access. The authorization-level audit then compared the public sealed cases and found that cases
011 and 012 require the materially harder Saffron-to-Cinnabar relocation through Surf.

An explicit train capture for scenario 046 was used to exercise that path. The attempt failed before
the water crossing at Route 2's south-facing warp into the Viridian Forest north gate. The planner
expected map 47 at `(0, 5)`; live RAM observed map 47 at `(1, 5)`. The capture remained unchanged,
no ROM-adjacent artifact appeared, no teacher action ran and no sealed case was opened. The failure
is retained externally as evidence SHA-256
`e00954d20e19b68acb828daf6a16a34d534df5b463238ae2754a5d6859df2e5f` and typed failed-receipt
SHA-256 `7fa9829427b30c6d81320d1eddabe13671560fa8c68f16680b8da4ad40ab22fc`.

## Exact public identities to verify

- plan schema: `pokemon-strategic-navigation-sealed-evaluation-plan-v8`
- plan bytes: `13664`
- plan SHA-256: `fe208ac5cf628bcd7301ae500622ae59e39bea271f60d817e2f70f3001fcc5d9`
- executable source bundle SHA-256:
  `d1faf6f33dc609bae475d854053cc9e2a271c56114459511ee7816d06cef4b60`
- teacher execution SHA-256:
  `827446bfe2f7c5b39da5311912b41872169804228010e211616d33dc79edd507`
- scenario registry SHA-256:
  `d06ecc9c1bc9d4103b966c83df0ee6e49c2329ed7785c63751ada1e74c11cd71`
- case-order SHA-256:
  `8c913e7101efdfe33c21c849d46da6076653066869077e5043bcf60928a4f2ba`
- frozen model canonical SHA-256:
  `753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1`
- sealed test access: `0/12`

Bind any verdict to the exact published HEAD commit in addition to those identities. A favorable
review of an earlier commit cannot authorize this revision.

## What changed

1. `route_plan._warp_transition` now applies the measured one-tile southward doorway settlement to
   directional ordinary warps as well as return warps. The regression uses the exact public Route 2
   to map-47 transition that failed live.
2. A non-test qualification catches measured route execution/planning failures only after its input
   has been authenticated. It rechecks capture bytes and ROM-adjacent artifacts, emits no exception
   text or private path, records `teacher_executed: false` and `sealed_test_cases_opened: 0`, and
   returns a v2 observation with an allowlisted portable failure reason.
3. The command builds and parses a typed receipt whose verdict matches `passed` or `failed`, writes
   both evidence and receipt as new external files, prints the path-free result and exits nonzero on
   failure. A failed receipt remains valid evidence but cannot satisfy authorization.
4. Schema v8 records this seventh pre-access amendment and supersedes v7 without changing the model,
   cases, case order, endpoint, attempt policy or scoring policy.

## Attack targets

- Revert the ordinary-warp correction while leaving the return correction intact; the Route 2 live
  witness and its regression must fail.
- Change the correction to affect `up`, `left` or `right`; existing directional passage tests must
  distinguish those semantics.
- Force a route failure to claim `passed`, return zero, omit either durable output, include the
  exception message/private path, claim candidate planning completed, run the teacher or report
  nonzero sealed access. Each mutation should be killed without using only the whole-plan digest.
- Try to authorize with the historical failed receipt, a v7 receipt, a receipt bound to another
  source bundle/commit, or a valid failure observation paired with a forged `passed` verdict.
- Verify that the v8 amendment chain ends at the exact v7 digest and that all twelve public case
  identities and the frozen model remain unchanged.

## Evidence required before an authorization verdict

First require clean exact-commit CI. Then inspect a fresh path-free, typed `passed` qualification on
the same scenario-046 Saffron-to-Cinnabar route. It must bind the exact published commit, v8 plan and
source bundle; plan all candidates; execute no teacher; leave the capture and ROM-adjacent artifacts
unchanged; and report zero sealed test cases opened. A Celadon-to-Saffron pass alone is no longer
sufficient. If any binding or the hard live route fails, return `changes_required`.
