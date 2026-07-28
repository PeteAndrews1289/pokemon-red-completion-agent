# Optional Continual Harness baseline

The core project does not import or vendor Continual Harness. If a comparison is added, it will run
as an explicit external baseline.

## Pinned source

- Repository: `https://github.com/sethkarten/continual-harness`
- Audited commit: `bbab97ad73e460b7cd7c08527d10ced30cc03fbe`
- License: MIT, copyright retained by the upstream authors

The upstream code and its runtime environment remain outside this repository. No upstream ROM,
save state, bootstrap archive, prompt asset, or private runtime artifact may be copied here.

## Why it is isolated

The upstream harness has a broader research and operational contract than this project. Its default
runtime may use save-state loading, externally reachable services, permissive CLI-agent execution,
and completion or termination signals that are not equivalent to the clean-run Hall-of-Fame
contract.

That does not make the upstream project invalid. It means its output cannot be relabeled as this
project's result without an adapter and independent verification.

## Required adapter boundary

An eventual `continual-harness` baseline must:

1. be requested explicitly and remain absent from default installation;
2. verify the exact upstream commit and a clean worktree;
3. run from a disposable private checkout or constrained container;
4. disable implicit state loading and require verified clean power-on;
5. bind any local service to loopback only;
6. restrict the exposed game tools and subprocess permissions;
7. record every live model call and controller action;
8. return only sanitized `baseline-run-v1` metadata; and
9. let this project's independent referee decide completion.

If an overlay or upstream source is ever committed, the complete upstream MIT notice and a
modification statement must be added to `THIRD_PARTY_NOTICES.md`.
