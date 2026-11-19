# Solo development player source, November 19

The solo campaign entered from power-on on `f4488e2d661e` and continued from its own blackout on `b75589bc4d74`. The default source checkout includes ongoing development. The [manifest](runtime-source.json) identifies the exact Python source observed during the repaired fresh import check, both compiled drivers and the declared overrides. The [source patch](frozen-player.patch) reconstructs the differing files from this publication. Every resulting SHA-256 was checked in an independent directory.

From a disposable copy of this version, run the following commands at the repository root.

```sh
git apply --check docs/releases/red-solo-2026-11-19/frozen-player.patch
git apply docs/releases/red-solo-2026-11-19/frozen-player.patch
```

Private ROM, model, save and environment inputs remain on the private installation. The source reconstruction does not launch a game. [Native evidence](../../work-sessions/solo-field-blackout-2026-11-19.md) · [Timing comparison](../../work-sessions/four-run-splits-2026-11-19.md)

[Full development tree](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/codex/red-development-20261119) · [Exact frozen player source](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/bc5b05a0463ebbcb3c2139211b99ea2baa147b22/docs/releases/red-solo-2026-11-19)

The development branch includes all 495 Python files changed since the previous public revision. Two operator helpers use installation-relative paths. The interview branch carries a small fishing-test correction. The public checks cover the documentation, configuration, artifact boundaries, registry and focused tests. The broader development tree retains 5529 lint findings in the accumulated changes. [Verification scope](development-coverage.json) · [Redacted review decisions](../../agent-review-log.md)
