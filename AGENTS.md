# Repository instructions

Work only in the active Current/Code checkout. Do not resume a legacy checkout or a
dated experiment merely because it contains a handoff.

## Read before development

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md),
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) and [HANDOFF.md](HANDOFF.md).
These answer, respectively: the product, operating rules, current status and next work.
Consult [the roadmap](docs/model-first-roadmap.md) for the remaining delivery sequence.
Latest explicit user direction takes precedence over repository documents.

Only HANDOFF.md contains the current executable work order. Dated reports, archived
plans, review prompts and closed experiment declarations are evidence, not dispatch
instructions. Do not read the entire archive at every session.

## Development contract

Before implementation, record the six-part mission check from NORTH_STAR.md:
reusable capability, learned authority, transfer check, cheapest falsifier, time
box and stopping condition. Anchor repairs to a player outcome, not an expanding
list of infrastructure tasks. Reuse the existing player and battler first.

Default work blocks are up to 3 hours unless Pete specifies otherwise.
Triage a local issue after 10 minutes; after 15 minutes or two equivalent failures,
reassess the whole approach and pivot within scope. These are not automatic stops.
Ordinary recovery, scoped repairs, useful TRAIN lessons, fits, diagnostics and
reversible DEVELOPMENT integration do not require repeated approval.
Explain a new subsystem, substantial architecture change or different product
outcome before implementing it. Do not manufacture work to fill a time allowance.

Use targeted tests for changed behavior. Preserve legality, provenance, save
recovery and truthful accounting checks. A targeted pass is not full-suite or CI
success. Do not replay Red or repeat a teacher factory to diagnose a local defect.
Do not repeatedly refit identical uninformative failures.

## Authority and safety

- Use semantic observations above the observation adapter; raw memory addresses stay below it.
- Only the executor translates actions into controller inputs.
- The referee verifies outcomes; it must not secretly choose a replacement action.
- Disclosed teachers may manipulate isolated TRAIN fixtures. The final player has no cheat action.
- Never fit DEVELOPMENT, benchmark or sealed data. Related snapshots are not independent origins.
- Preserve original losses, costs, exact terminals and model-versus-support attribution.
- Do not merge save progress or copy diagnostic wins, XP, money or specimens into another run.
- Do not claim final completion without the same-run criteria in
  [the completion contract](docs/completion-contract.md).
- Add ROM-free tests for changed behavior; private-ROM tests use the integration marker.
- Never commit ROMs, saves, datasets, model artifacts, credentials or personal filesystem paths.

## Documentation and closeout

Keep one concise current handoff and one dated work-session record. Update the
active-state JSON and its generated page when the decision changes. Counters must
cite evidence; gameplay XP, engineering work and tests are not parameter learning.
Historical learning totals are not a target to repeat in every session.

Keep README under 100 lines and 650 words; keep current entry points under 200 lines.
Replace current sections instead of stacking status paragraphs. Preserve unique
history in the chronicle or a clearly labeled archive. Back up a substantial
narrative rewrite. Update the roadmap, narrative and review log for a material
milestone or Pete's request, not automatically after every small fix.
Keep roadmap stage IDs and final exit criteria stable. Record strategy changes in
[roadmap decisions](docs/roadmap-decisions.md). Do not build another logging system.

Run scripts/check_product_focus.py and the documentation checks for changed
surfaces. Do not weaken tests to accommodate an unreadable status dump.

The final chat response must state the verified outcome, learning/registration
delta, running or stopped status, limitations and the next decision. Include an
ordered next-session plan directly in chat: player outcome, blocker, components
to reuse, work, acceptance/failure, time allowance, reassessment and exclusions.
Recommend a model, effort and whether Fast is useful without claiming to change
the user's setting.

## Ownership and publication

Codex implements and verifies. [AGENT_COORDINATION.md](AGENT_COORDINATION.md)
contains current ownership. Flash, Claude and subagents are optional, not standing
review gates; do not dispatch or check their quotas without a current assignment.
Do not overlap source writers. Report actual external contributions if used.

Pete alone authorizes GitHub publication. Passing tests, finishing a session or
“continue” does not authorize a push, release or pull request. Preserve unrelated
dirty work; local recoverable checkpoints are allowed.

Before an explicitly authorized executable-source publication, regenerate the
existing collection registry with scripts/regenerate_collection_registry.py,
run its --check mode and include its generated metadata. This does not authorize
gameplay. Do not manually rerun unchanged failing hosted CI.
