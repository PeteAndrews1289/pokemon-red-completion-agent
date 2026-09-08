# Collection resource recovery repair

Mission: unblock sustained model-directed Red collection without replacing goal
choice or losing earned progress after an executor failure. The Phase 3 exit and
prospective chain requirements remain in the [work plan](../work-sessions/2026-09-08-phase3-completion-plan.md).

## Implemented; live recovery not yet demonstrated

- The native collection trainer supplies cartridge encounter rows. Every next
  encounter search checks current per-opponent HP, status, level, type and usable
  PP coverage; different opponents may use different helpers. Structural support
  remains a separate question used to determine whether healing could help.
- A no-finisher wild battle has a PP-independent defensive escape path. It retains
  health/status/type/level qualification, finite existing menu limits and the
  outer action/frame budgets. Every escape action checks for faints before/after.
  No qualified escort means no controller input, not blind fleeing or attacking.
- A separately logged support recovery can load only the last authenticated
  failed-state capture, escape, heal and publish a safe continuation. The failed
  episode remains immutable. A distinct terminal/checkpoint type retains failed
  prefix costs and actual recovery costs, zero decisions and zero training rows.
  The subsequent restore keeps the inherited quest envelope and search memory.

The original evolution remains failed, model67 remains unchanged, and Arbok has
not been obtained. This engineering work is not a new fitted outcome or Phase 3
completion. Successful recovery must precede new model-directed gameplay.

## Checks

The first live support operation on source269417ae successfully escaped the
retained Drowzee battle with no faint. It then selected an available FIELD_RESTORE
binding rather than the intended Center mechanic: HP/status improved using items,
but empty PP remained. The strict final check rejected admission after128actions/
11,076frames. Exact statebd01a806 and failed manifestc54a6a63 remain retained;
no model label or safe checkpoint was published. The next support operation starts
from that state, explicitly requires Center recovery and authenticates both failed
prefixes. Default model/legacy restore behavior remains unchanged.

The next operation reached Vermilion Center(3,7) in55actions/1,632frames without
a faint, but the leaf Center provider still rejected PP-only recovery at safety1.
State8d174e04 and failed manifest4ff59eee preserve that exact endpoint. The explicit
PP mode now reaches the nurse provider and verifies actual HP/status/PP changes,
not an invented safety-score increase.118 related tests pass, including the full
route/leaf PP-only healing path. The next operation continues from the Center;
neither the battle nor the trip is repeated.

Read-only rehearsal also caught canonical profile serialization before any input;
the real proposal round-trip now has a regression test. Broader testing caught
the generated source registry and historical Route11 AST attestation becoming
stale. Regeneration updates only prospective source bindings; the exact trainer
waiver is justified by unchanged default mode plus legacy tests that forbid calls
to collection-only helpers. No old campaign receipt or test partition is changed.

331 targeted tests passed across collection/legacy trainers, native evolution,
Center/box access, private artifacts, checkpoint provenance, incremental fitting
and the bounded player runner. Added cases distinguish the actual Primeape versus
Drowzee resource gap, split helper coverage, ineffective healing, PP-independent
escape, post-action faint stopping, fabricated labels/costs and silent rewinds.
Lint, public-artifact and documentation/focus checks passed. This is targeted
coverage, not a claim that every repository test or a ROM execution passed.

## External review adjudication

Claude Opus 4.8, requested High: approved repair direction with conditions. Accepted
per-species current-resource checks, a separate escape path, preserved legacy mode
and recovery that does not rerun the evolution. Rejected blind fleeing without a
qualified defensive helper: finite retries alone do not establish safe control.
The final review raised three speculative blockers, rejected against the complete
implementation and executable tests: capture already emits both original-parent
hashes; the recovery result supplies the entire surface actually used by capture;
and verification/observation must remain action-free. The real recovery round-trip
test captures, completes, publishes and opens the checkpoint successfully. Moving
the meter before verification would hide illicit inputs, so costs remain checked
after it. Preserve this fail-closed accounting check during the live rehearsal.

Antigravity Gemini 3.8 Flash High: accepted its split-helper, resource-degradation
and ineffective-recovery adversarial cases. Rejected the follow-up's three source
claims after checking actual interfaces: recording a FLEE decision is not issuing
controller input; `switch_active_battler` returns true when the escort is already
active; and the field finisher already receives the venue's maximum level, not
`None`. Do not change correct code to satisfy a hypothetical substitute interface.

Observed service usage after the initial Claude review: current session 5% used
(reset September 8, 03:49 America/New_York), weekly 8% used (September 11, 09:59).
After two Flash reviews: Gemini five-hour remaining 98.835%, weekly remaining
94.976%; resets September 8 07:51:43 UTC and September 11 23:22:45 UTC respectively.
These are provider quota readings, not token-cost estimates. The later Claude
review receives a separate post-session reading in the operator handoff.
