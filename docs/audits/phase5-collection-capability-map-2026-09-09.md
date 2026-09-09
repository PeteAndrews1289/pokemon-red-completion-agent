# Phase 5 collection-planning capability map

Baseline: `774805e243299cb7c8caebe5fe691fa26f8fcd6a`.
Flash authored the isolated draft; Claude Opus 4.8 High reviewed its frozen first
revision `f451da63`; Codex adjudicated, corrected and tested the result.

This is **ROM-free engineering preparation**, not a new gameplay capability.
No save, ROM, controller, model fit or evaluation was used in this package.

## Existing components to reuse

| Component | Implemented support | Boundary still to verify |
| --- | --- | --- |
| [Physical collection](../../src/pokemon_red_completion/red_collection.py) | Party and box specimen accounting; declared living contract | Current post-game census and safe continuation were not reopened here |
| [Acquisition demand](../../src/pokemon_red_completion/collection_acquisition_demand.py) | Surplus specimens matched to missing reachable forms; alternatives are non-additive | Mathematical transformation reachability is not live action feasibility |
| [Level edges](../../src/pokemon_red_completion/red_acquisition_alternatives.py) | Cartridge-derived level-evolution edges scoped to the Red contract | No implied stone, trade or event executor |
| [Cartridge decoding](../../src/pokemon_red_completion/gen1_cartridge.py) | Encounter, fishing, trade and evolution tables | A decoded source does not prove current access or a working controller skill |
| [Registration](../../src/pokemon_red_completion/red_pokedex.py) | Seen/owned flags and explicit run-choice exclusions | Registration is historical ownership, not a retained specimen |
| [Regional acquisition](../../src/pokemon_red_completion/red_regional_acquisition.py) | Existing corridor enumeration and real executable goal bindings | Verify useful sources and supplies from the post-game state |
| [Native boxed evolution](../../src/pokemon_red_completion/red_native_boxed_evolution.py) | Existing native binding for the boxed level-evolution skill | Qualify a useful current precursor; do not rebuild the skill |
| [Resource router](../../src/pokemon_red_completion/red_resource_goal_router.py) | Existing semantic resource and route support | Verify legitimate post-game supply and its actual costs |
| [New pure catalog](../../src/pokemon_red_completion/collection_planning_catalog.py) | Tested prerequisite explanations, retained-precursor checks and acquisition accounting | **Not wired to runtime**; no new executable bindings |

Fishing, static encounters, stones, in-game trades and external trade/event
requirements remain explicit capability questions. This inventory does not prove
that no implementation exists anywhere in the repository; it does not qualify
those methods at the current checkpoint.

The legacy `pokedex.LivingDex` tracks registration, despite its name. Use the
physical collection ledger, not that object, for coexisting-specimen accounting.

## Catalog contract

Three questions must stay separate:

1. Is an acquisition method declared?
2. Are its observed resources, precursor and source prerequisites satisfied?
3. Does the runtime supply a qualified executable binding?

The pure catalog checks **caller-supplied declarations**. Its `READY` means those
declarations are internally consistent, not independent proof of reachability
or executor safety. Unknown reachability/resources block. Version/trade/event
flags and qualification enums need trustworthy adapters; their values are not
authenticated by this module.

Transformation edges must be declared, contradictory stock or consumption inputs
are rejected, and observation/report mappings are defensive read-only copies.
Registration appears as `registered_but_not_living` diagnostics but never fills a
living target. Each transformation preserves the last required precursor.

Capture demand and evolution readiness are different. A held precursor can cover
a future form mathematically, making further captures unnecessary, while its
evolution is still needed. Codex corrected this by checking replacement utility
after removing the consumed specimen. The calculation creates no training label
or predicted gameplay reward. All alternatives must be recomputed after an action.

`unsupported_targets` means no direct option was declared for a missing target;
it does not establish biological impossibility or rule out indirect preparation.

## Review and verification

- First Flash draft: 56 targeted tests passed, but independent probes exposed
  stock divergence, undeclared transformations, mutable observations and silently
  ignored contradictory consumption. Lint also failed.
- Claude independently identified stock divergence and dead registration
  diagnostics. Its suggestion that validation needed no further work was rejected
  based on the reproduced defects. Its non-target-only caveat about capture
  demand was too narrow: the new all-target A→B→C test also failed.
- Flash made one correction pass. Codex retained its useful changes, restored
  dropped tests, repaired transformation utility and remaining mapping/key/lint
  issues, and corrected unsupported documentation claims.
- Final local scope: **69 targeted ROM-free tests passed** across the new catalog,
  acquisition-demand and Red edge-projection tests. New-module typing and
  source/test lint passed. This is not a full-repository test result.
- Claude reviewed the first draft, not the final integrated correction. Final
  acceptance and residual limitations are Codex's responsibility.

## Next gameplay-facing step

Stop expanding the catalog. Reuse the existing native acquisition/evolution
bindings to establish two useful, genuinely executable collection alternatives.
First inspect the retained Hall-of-Fame continuation and legitimate supply:
the prior closeout reported 30 specimens, 28 unique living species, 33
registrations, 120 required coexisting species, 30,418 money and no capture items.
These figures are prior evidence, not observations made by this ROM-free task.

Then run a bounded model-selected collection lesson with a fresh physical ledger
and retained resource costs. No new boss replay, broad executor rewrite, or
mandatory outside-review gate is warranted.
