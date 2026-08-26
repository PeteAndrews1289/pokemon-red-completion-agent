# Purpose-built living-Pokédex capture contract

Status: ROM-free shared contract under qualification on 2026-08-26. This document is subordinate
to [MISSION.md](../MISSION.md), [NORTH_STAR.md](../NORTH_STAR.md), and the generated
[active product state](../ACTIVE_PRODUCT_STATE.md).

## Why this exists

The exhaustive Red V3 census reconciled all 81 legacy contexts and found only eight complete
three-or-more-option menus: five train and three development. They covered three offered option
kinds and one location per partition. The unchanged observed-arm calibration gate needs at least
eight train examples across four selected kinds and three selected transformation families plus
four development examples across four selected families and four locations, with no train/
development family or location overlap. The old bank cannot supply that curriculum and every
inventory identity is retired without retry.

The replacement is prospective data engineering. We declare the semantic decision states the
learner needs before a title adapter opens a cartridge. A deterministic setup policy may create
those states later, but its route, buttons, and choices are provenance only. They are never
teacher labels. The learner still receives only one system-random selected semantic arm and its
independently observed consequence.

The implementation is
[`living_dex_capture_curriculum.py`](../src/pokemon_red_completion/living_dex_capture_curriculum.py).
It is title-neutral. Red and Crystal must bind different private setup plans, state bytes,
families, locations, roots, menus, and observers to this same schema.

## Frozen campaign shape

The evidence minimum remains **8 train + 4 development**. The prospective campaign is larger:

- at least 10 train setup slots, tolerating at most 2 failed or interrupted setups;
- at least 5 development setup slots, tolerating at most 1 failed or interrupted setup;
- every slot declared before setup begins and every slot executed or terminally accounted;
- no adaptive replacement, outcome-dependent omission, retry of a claimed slot, or early stop
  when a convenient selected-kind mix appears;
- each complete capture exposes at least three distinct portable option kinds with one planned row
  per kind; mixed menu widths are supported;
- train slots must retain at least a 98% exact prospective probability of selecting four or more
  distinct kinds after any allowed pair of train setup censors.

The probability is a campaign-coverage guard, not a policy-quality claim. The existing system-
random rank permutation assigns each row every rank symmetrically; averaging the logged
nonuniform rank-weighted propensity over the not-yet-issued commitment therefore gives each
distinct row a uniform marginal. The contract calculates the exact rational probability over
those marginals for every allowed surviving train subset and takes the worst case. Once a
commitment exists, the collector still logs and fits with its actual nonuniform propensity.

## Selected-arm diversity, not offered-menu decoration

Earlier gates could count kinds or families that appeared somewhere in a menu even when the
randomly selected arms might all collapse to one kind or family. The purpose-built contract
separates those claims:

- train offered-kind union must meet four, and the exact worst-case-after-censor selected-kind
  probability must meet 98%;
- logical train family scopes must still provide at least three distinct surviving scopes after
  any allowed two censors;
- logical development family scopes must still provide at least four distinct surviving scopes
  after the allowed one censor;
- each development location scope is distinct, and every development scope is disjoint from all
  train location scopes;
- actual title-adapter family hashes belonging to different logical scopes must be pairwise
  disjoint; actual locations must map one-to-one to logical location scopes.

That makes family and location coverage true for whichever arm is selected. It cannot be satisfied
by offering diverse alternatives and then learning from a homogeneous realized batch.

## Setup versus learner authority

Every setup slot freezes three private digests before execution: the deterministic setup plan, its
terminal predicate, and the independent capture-observer contract. It also freezes action and
frame budgets. The durable setup runner must claim the slot before controller input. After input,
complete, failed, and power-loss-interrupted terminals are all non-retryable.

Setup terminals may truthfully report setup controller actions and frames. They must report all
learner effects as zero:

- no behavior draw;
- no learner controller authority or action;
- no learner label;
- no selected-arm outcome observation;
- no learner root claim;
- no teacher query;
- no model fit.

A complete attestation additionally proves that the state is repeatable, nonsealed, and not
one-shot; the full distinct-kind menu and all executors are present; the capture occurred before
the behavior draw; and the root, state, envelope, observer, family, and location bindings are
cryptographically joined. A failed or interrupted setup remains a censored slot in the frozen
denominator and has no capture attestation.

## Public/private boundary

Private records retain slot, root, setup, state, envelope, menu, observer, family, and location
digests. Public plan and qualification receipts expose only:

- partition, menu-width, kind, family-scope, location-scope, and terminal counts;
- exact probability numerator and denominator;
- aggregate setup actions and frames;
- zero learner-effect counters;
- plan and qualification digests;
- explicit identity-field and private-path counts of zero.

No species, map, coordinate, route, item, title, private root, filesystem path, or raw exception
may enter the learner projection or public receipt.

## Cross-game boundary

The shared contract owns curriculum arithmetic, selected-arm coverage risk, nonadaptive slot
accounting, censor reserve, and public/private invariants. A title adapter owns only:

- how to reach a requested semantic decision state;
- how to prove its terminal predicate without selecting an arm;
- how to enumerate the complete portable menu and authenticate each executor;
- how to bind private transformation-family and location identities;
- how to save and independently reopen a repeatable capture.

Red remains the first adapter and Crystal the first frozen-weight transfer test. Crystal does not
inherit Red routes or button sequences. It must satisfy the same capture, feature, outcome, and
model schemas with its own observation and execution bindings.

## Claim boundary and next gates

This ROM-free contract is infrastructure, not a learned player. It creates no training example,
does not authorize a setup run, and does not prove that Red can supply the requested states. Its
focused tests must still pass mutation, full-suite, source-registry, documentation, lint, and type
checks before publication.

After publication and reorientation, the separate next gates are:

1. freeze a concrete private Red 10+5 setup plan whose logical menus and scopes satisfy this
   contract, including any missing reusable Red semantic skills;
2. qualify a durable setup runner without opening a protected input;
3. run the frozen Red setup campaign once, account every terminal, and stop before a behavior draw;
4. freeze the resulting exact capture inventory only if its private attestations satisfy this
   contract;
5. separately collect every preregistered selected-arm outcome, fit once on train, and report
   development calibration;
6. use observed variance to power paired Red evaluation before any frozen-weight Crystal run.

The 8+4 settled minimum remains an integration and variance pilot. It cannot support coefficient
interpretation, policy superiority, autonomous-play authority, living-Pokédex completion, or
cross-title transfer claims. Curating prospective states also leaves context-sampling propensity
uncorrected; every later report must retain that limitation.
