# Model113 frozen restore learning and supplemental-only continuation

## Outcome

Model112's exact frozen restore choice succeeded in **87 controller actions / 3,996 emulator
frames**. The executor reconstructed the exact five-option menu, selected the already-recorded
index directly and made zero policy queries during execution. Registrations remained **83**, with
**63 living species** and **67 specimens**. The outcome was admitted once without a teacher label,
advancing the training-only learner from 112 to **113 settled examples** and 77 successful examples.

Model113 was published in checkpoint
`1365ed6e8ae8ee9c79cc17b9c0b55cad1f8fbebaba1cb7fb174636f2dff2f8ae` and reopened byte-for-byte.
The next action-free menu initially exposed a real planner gap: after healing, no ordinary goal was
available, so four valid automatic fishing destinations were discarded. The reusable menu now
permits two or more authenticated supplemental choices without requiring an ordinary goal, while
retaining storage-pressure masking and keeping control recovery outside learned authority.

With that repair, Model113 saw four anonymous acquisition choices and selected candidate0 by
exploration with probability `0.19050388143341396`. That acquisition is frozen but unexecuted.

## Audit and validation

Gemini3.8 Flash High returned **GO** twice: first for the no-resampling restore executor, then for
the supplemental-only menu change. The second review found no P0/P1 issue and five optional P2
defense-in-depth tests. Focused measured-choice and menu suites passed; Ruff and mypy passed. The
exact-head GitHub run `34748536613` passed in full. The frozen acquisition remains unexecuted; its
source dependency is now green.

One full local run was stopped after 7,674 passes because source changed under it during this
session. Its sole failure was the known machine-specific PyBoy metadata fingerprint, not the new
planner or receipt code. Exact-head CI is the clean full-suite authority.

## Mission check

| Question | Answer |
| --- | --- |
| Reusable capability | Persist a model choice across runtimes without resampling, learn from its actual result and keep a supplemental-only acquisition menu productive. |
| Learned authority | Model113 selected the next acquisition destination; deterministic code still owns routing, fishing, capture, battles and menus. |
| Product relevance | A long collection run can now heal, learn from that decision and continue toward missing registrations instead of stalling because no unrelated ordinary goal exists. |
| Limitation | This remains one same-lineage Red development continuation, not fresh-game autonomy, complete Red registration or transfer evidence. |
| Next falsifier | The exact frozen Model113 acquisition cannot bind its required capture support, execute within declared bounds and retain its actual success or failure. |
| Stop condition | No second policy query, no retry of prior fishing attempts, no post-hoc species target, no teacher label and no Blue/Crystal execution. |

## Next session

After exact-head CI is green, bind the exact Model113 menu and selected acquisition once, attach
capability-based capture support without resampling, execute within the existing route and casting
bounds, retain success or failure, fit only that measured outcome, publish the terminal and rebuild
the next menu action-free.

[Evidence](../evidence/red-model113-frozen-restore-learning-2026-09-13.json)
