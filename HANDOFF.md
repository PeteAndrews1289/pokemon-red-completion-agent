# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 14, 2026.

## Direct catalog source consumed before preflight

The exact source frozen in `full-local-source-20260914-v1` was claimed once under published commit
`424695ca` after exact-head CI 34889466446 passed. The first preparation failed before payload
access because the command parser produced a null regional-transition list. One same-claim recovery
opened and authenticated only that source, then failed before preflight while Model121's v4 feature
selected the economy behavior for a base plan without economy schema/supply fields.

Both failures are retained. No action-free preflight completed; controller actions, advanced
frames, model queries, registration sessions/observations, outcomes, examples and fits are all
zero. Read-only checks confirmed that the intended registration session/run do not exist. The
source is consumed: never reopen, reclaim, retry or replace it in this session.

The generic repair normalizes the empty parser value while preserving legacy `wild_source`, and
maps supported feature version 4 to optional-recovery behavior until a separately valid economy
promotion. Future unsupported versions still fail closed. Existing economy and continuation
contracts remain strict.

## Next bounded implementation

Publish the generic repairs and require exact-head CI. In a separate session, freeze one distinct
unused source prospectively, claim only it and run the action-free two-family gate. Only if that
passes may one exploratory Model121 choice execute once and contribute its measured outcome. The
next attempt is bounded to one source and two hours, with no fallback source.

## Learning and completion status

Model121 remains 121 examples, 83 successes and 86 local registrations. This session consumed one
claim and opened one selected payload, but issued no input/query and added no registration session,
outcome or fit. Gameplay is stopped; the anti-drift alarm remains active.

The Model121 terminal itself remains ineligible for the standard collector because its original
state is not in the frozen catalog. Never relabel it, replay consumed trials or weaken provenance.
Full fresh-start model-directed Red story plus all 151 local flags still precedes any ROM hack,
then Crystal and at least Emerald. Version, trade, supporting-save and event requirements remain.

## Verification and reviewers

Flash3.8 High found that the first repair could admit feature versions above4 and could discard a
legacy wild-source field; both findings were accepted and fixed. Its metadata-skew claim was
rejected because the base plan stores no feature-version field. Claude's evidence review is
recorded in the current session report. Neither reviewer accessed private artifacts.

Next-session recommendation: **GPT-5.6 Sol / High / Fast off**. The next work is another tightly
bounded source freeze/claim gate using the repaired path; reserve Astra for a new authority or
provenance design dispute.

[Session](docs/work-sessions/2026-09-14-direct-full-local-preflight-failure.md) ·
[Evidence](docs/evidence/red-direct-full-local-preflight-failure-2026-09-14.json)
