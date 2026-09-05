# Coding-model comparison log

Purpose: assess whether GPT-6 improves useful project progress enough to justify its usage
relative to GPT-5.6 Sol. These are observations from development, not a controlled benchmark.
The coding assistant and the trained Pokemon policy are different models.

## 2026-09-05: Sol final-preflight storage diagnosis

Starting point: GPT-5.6 Sol inherited the merged interpreter-diagnostic successor. Exact-main CI
`33943983942/1` passed in 19 minutes 1 second. Its one canonical-locale launch then rejected with
all protected effects at zero. Sol isolated the cause through file metadata and one read-only
development import: the clean execution checkout and private artifact root were both on the T7,
which violates the repository's deliberate separate-device boundary.

The quick diagnosis is positive evidence for Sol on bounded operational debugging. The failed
launch is still operator/infrastructure rework and counts against session efficiency; it is not a
model, data or ROM failure. Codex closed the strict-bootstrap lane rather than spend another CI
cycle on a wrapper and reoriented toward repeatable model-behavior development from the internal
checkout. That path passed five real inputs in 3.22 seconds, three synthetic resolver tests in 45.38
seconds, 37 focused source tests in 65.11 seconds, and the complete 6,742-test gate in 17m43s. Exact
assistant token counts and weekly quota debit remain unavailable.

## What to record each session

- Task and starting revision; whether the diagnosis/design was inherited.
- Verified deliverable and connection to learned gameplay or living-Pokedex progress.
- Measured local test time, hosted CI time and private-run time separately.
- Corrections after failed commands, failed tests, review or production use.
- Input/output/reasoning tokens and account usage only if actually available; otherwise unknown.
- Reasoning setting and Fast mode only when confirmed for that session.

Compare cost per verified deliverable over several similar sessions, accounting for task size,
inherited work, machine/runtime differences and CI waits. Faster generated text, more tests or
more documentation alone do not establish better value. API prices do not establish subscription
usage debits. No account quota or billing data is inferred from elapsed time.

## 2026-09-05: Sol strict-bootstrap invocation correction

Starting point: GPT-5.6 Sol inherited its own published V1 runtime-staging defect, replaced the
command with the mature strict bootstrap, passed 50 focused tests and the full local gate, merged
through PR 215, and passed exact-main CI `33939561868/1` in 26 minutes 4 seconds. The exact
1,477-file production dependency closure reproduced its reviewed digest. Claude and Antigravity
3.8 Flash High independently returned GO with no P0 or blocking P1.

The first strict invocation was rejected before source authentication because Codex launched the
pinned interpreter under `LANG=C` and `LC_ALL=C`, yielding `utf8_mode=1` instead of the required
zero. This is operator rework attributable to the Sol session, not a model/root/runtime failure.
The source's generic early failure label also obscured the cause. V2 is retained without retry; the
minimal final successor adds a distinct interpreter-authentication stage and a canonical reproduced
locale. No learner counter, prediction, gameplay action or authority changed.

Current judgment: Sol remains appropriate for this bounded correction, but this session is negative
evidence against claiming superior efficiency. It delivered a substantial trust-boundary repair,
then lost another hosted cycle to an avoidable launch-contract mistake. Exact assistant tokens and
weekly account debit remain unavailable, so no token-use ratio can be claimed.

## 2026-09-04: focused external audit and budgeting guidance

Claude completed a High-effort read-only source review; Antigravity completed compact architecture
reviews using explicit Gemini 3.8 Flash High. Codex checked their material claims against source
and [recorded accepted/rejected findings](development-supplement-focused-audit.md). Review agreement
is not proof of correctness: Claude's failed-plan-fixture description was inaccurate, and
Antigravity retracted unsupported claims after receiving actual feature/journal excerpts.

The adapter suite was independently rerun: 24 passed in 55.74 seconds. The initial command omitted
the source import path and failed during collection. This repeats an earlier command-setup error
and counts as rework, not evidence of a coding-model advantage. No live experiment or fit ran.
Assistant token counts and the user's actual account debit remain unknown.

Official documentation checked on this date supplies a budgeting reference, not a task-token ratio:

- [ChatGPT credit rates](https://learn.chatgpt.com/docs/pricing): Astra input/cached/output rates
  are 250/25/1,250 credits per million tokens; Sol rates are 100/10/500. Equal token mixes at
  standard speed therefore cost 2.5 times as many credits on Astra.
- [Fast mode](https://learn.chatgpt.com/docs/agent-configuration/speed) adds a 2.5 multiplier for
  both Astra and GPT-5.6 where supported. Astra Fast is therefore 6.25 times Sol Standard for an
  equal token mix; Sol Fast and Astra Standard have equal published per-token credit rates.
- These ratios do not establish how many tokens either model uses to finish the same task, or
  an exact weekly allowance ratio. Context, reasoning, retries, tools and caching affect usage.

Budget recommendation (judgment, not measured superiority): Sol High with Fast off for normal
integration sessions; Astra High for bounded difficult diagnoses and milestone audits; avoid
Max/Ultra as the default for long sessions. Antigravity High handles compact independent design
challenges, with Claude reserved for source/evidence audits at meaningful boundaries. Do not
request large duplicated audits after every maintenance edit.

## 2026-09-04: supplement-consumer implementation session

Starting revision: `52cb0dcc`. The preceding GPT-6 session had already identified this adapter
gap, so this session is implementation rather than an independently discovered diagnosis.

The new explicit supplement binding and strict reader share development admission and journals
with the historical held-suffix path. The real stored three-row plan authenticates without
opening state files, a ROM, predictions or outcomes. A ROM-free positive-path test reaches the
actual scorer and selected-outcome journal and recovers without reopening a runtime. The concrete
five-root production command remains unfinished; no real learning progress is claimed.

Corrections: the initial module import used an incorrect guessed filename; several exploratory
file lookups also missed. One test confused a coordination lock with a claim. The positive-path
fixture needed correction for authentic root/recipe pairing, occupied storage and scarce supplies;
otherwise actual providers correctly rejected its offers. A temporary diagnostic initially used
a symlinked system temporary path and was corrected to its resolved path. The real-record check
also corrected the inherited conflation of shared-plan and complete Red-plan digests.

The first focused batch passed 36 tests and failed one lock assertion in 151.03 seconds.
The successful full positive-path test passed in 30.00 seconds after fixture corrections.
Whole-source typing passed across 365 modules and repository lint passed at this checkpoint.
The final regression batch passed 212 tests in 272.94 seconds; a strengthened positive-path
test separately passed in 30.08 seconds. One additional test correction compared a stored JSON
record with the JSON-normalized fixture rather than expecting in-memory tuples to survive as
tuples. A guessed registry-loader function name also failed before being replaced with the
existing parser. No hosted failure is inferred from these local iterations.
These timings are not matched GPT-5.6 comparisons. Exact assistant tokens, account debit,
reasoning setting and Fast-mode state remain unknown.

Judgment: do not yet claim GPT-6 is better value. This session demonstrates useful integration
work but also rework and remaining production assembly. Use a focused two-lane independent audit
before consuming the five development cases, not a large whole-repository review. Official
[model comparison documentation](https://developers.openai.com/api/docs/models/compare) is product
reference material, not evidence of this project's subscription cost or measured speed.

## 2026-09-04: GPT-5.6 Sol handoff to GPT-6

**Inherited evidence:** PR 211 fixed the mixed-partition binding defect, passed 6,688 local tests,
merged at `32dcb064`, and passed CI `33904380404/1`. The following census was interrupted after
65+ minutes in binding diagnosis with zero protected effects. The repeated-validation diagnosis
and proposed index refactor were already present before the model switch; credit for finding
that defect must not be assigned to GPT-6.

**GPT-6 delivered:** implements a per-call validated capability index and exact shared join,
while retaining full private-plan validation in the freezer. Six added regression cases cover
bounded projection work, parity across context faults and projection substitution. The focused
slice passes 25 tests in 62.72 seconds. Lint, typing across 364 modules, documentation/privacy/focus
checks and four registry reproductions pass. PR 212 merged as `7d654cdf`; both hosted runs passed
6,691 tests, with four skips and one expected failure. No hosted CI run failed in this session.

**Production outcome:** all 429 feasible supplements bound with zero failures. Completion was
observed within 834 seconds of launch (an upper bound; exact process duration was not measured).
The preceding attempt had been stopped after 65+ minutes. The following one-shot freeze completed
in a measured 788.71 seconds and stored/reopened three new development roots. Both commands had
zero gameplay, prediction, fit, outcome, teacher and claim effects. Supply preparation succeeded;
the Pokemon model did not learn or gain authority in this session.

**Audit finding:** the existing held runner parses historical mixed schedules and cannot consume
the new zero-train supplement. GPT-6 identified and documented the missing reader/admission and
executable preflight instead of treating the freeze as gameplay readiness.

**Infrastructure timing:** PR pytest took 1,498.24 seconds; main pytest took 982.70 seconds for the
same source and test counts. That variation is a warning against attributing session wall-clock
differences to the coding model. Total pytest waiting alone was about 41 minutes. The subsequent
census and freeze also spent substantial time in unchanged input checking and capability discovery;
their individual stage timings were not instrumented, so the split is unknown.

**Corrections so far:** the first test invocation and registry-generation batch omitted the
worktree import path and failed before executing tests; both were corrected. An additional
protocol-golden test failure followed registry regeneration: one expected assignment digest was
missed while updating the other source-derived golden values. The 140 other protocol/focus tests
passed in that run (65.54 seconds); the stale digest was corrected and the failed test rerun.

**Usage:** exact assistant token totals, weekly subscription debit, actual reasoning setting and
Fast-mode state are unavailable in this log. The recommendation to use High is not evidence
that High was selected. No cost or speed superiority is established yet.

**Current judgment:** a verified engineering success, but insufficient evidence that GPT-6 earns
its additional usage cost over Sol. Sol had already supplied the diagnosis and refactor direction.
Credit GPT-6 for implementation, regression coverage, completing the gate and the downstream
integration audit; do not claim a controlled model advantage. Compare several similarly scoped
sessions and their observed usage before changing the default solely on this result.

Evidence: [binding result](evidence/red-living-dex-development-supplement-binding-result-v1-2026-09-04.json),
[freeze result](evidence/red-living-dex-development-supplement-freeze-result-v1-2026-09-04.json).

## 2026-09-04: GPT-5.6 Sol production-integration session

**Inherited state:** GPT-6 had implemented and locally rehearsed the supplement reader/admission
adapter, then a focused Claude/Antigravity audit found no blocking defect in that scope. The
concrete command, exact model-record join, five-root batch and production bootstrap were still
unfinished.

**Sol delivered so far:** adds a production development wrapper that authenticates a freshly
reopened sealed plan, current-source consumer, staged producer runtime, selected root and immutable
model record before constructing the cold ROM resolver. It extracts one train-corpus/model loader,
freezes the case set to historical ordinals 10 and 11 plus supplement ordinals 0 through 2. An
initial attempt to extend the already-qualified train command was rejected because it changed the
script digest bound by historical evidence. Sol restored that command byte-for-byte and added a
separate source-authenticated, ROM-free five-root development preflight. All five actual private
state/envelope pairs join after correcting their overly broad file permissions.

The combined focused slice passes **72 tests in 234.16 seconds**; the new command adds **7 focused
boundary tests**, and lint plus typing pass for the changed source. The exact private model
record reauthenticated against all 18 train-only examples. No gameplay, prediction, claim, outcome,
fit, controller action or emulator frame occurred.

**Corrections:** an initial large patch needed inspection before follow-up edits; import ordering
was corrected mechanically. A new model-loader test initially used dataclass equality on NumPy
arrays and was changed to compare canonical model documents. Synthetic batch fixtures initially
overlapped roots across old and supplement plans, so the test moved to independent fixture roots.
The first real file join failed closed on `0644` capture permissions; only the ten selected files
were changed to owner-only and the join then passed.
The full gate also caught that extending the historical train CLI invalidated its qualified script
identity. That extension was removed, its evidence test passes unchanged, and development now has
its own command rather than rewriting historical evidence.

**Current judgment:** this is a strong Sol implementation result on a well-bounded seam, but it is
not a controlled comparison with GPT-6. The task inherited mature architecture, exact bindings and
review findings. Token usage and weekly account debit remain unavailable, so no cost ratio can be
measured from the repository. Continue using Sol High for ordinary implementation and reserve the
more expensive model for genuinely ambiguous architecture or promotion audits unless later sessions
show a repeatable quality difference.

Evidence: [local five-root command qualification](evidence/red-development-five-root-command-local-qualification-v1-2026-09-04.json).

### Sol correction after publication

PR 214 and exact-main CI passed, but the first action-free five-root invocation failed at the
production batch boundary with every protected counter at zero. Read-only diagnosis found that
the new lightweight command had not staged the authenticated third-party dependency closure that
the production runtime checker requires. The unit suite verified argument and effect boundaries
but did not execute the real command bootstrap, so this was a genuine coverage gap.

Sol did not retry the executable or blame the roots/model. It retained the failure as evidence and
replaced the command bootstrap with the proven strict pattern already used by the historical train
consumer, while leaving that historical script byte-for-byte unchanged. This is useful negative
evidence in the comparison: Sol found and repaired its own architectural shortcut only after the
real boundary falsified it. No claim about model quality or gameplay follows.

Evidence: [V1 five-root preflight failure](evidence/red-development-five-root-preflight-failure-v1-2026-09-05.json).
