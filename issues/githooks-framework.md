---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# Global git hooks framework — design

gitflower provides the machine-wide git hooks framework with `.d` dispatch: a gitflower-owned hooks script directory that `core.hooksPath` points at, where a dispatcher runs pluggable checks and actions, then chains to the repository's own `hooks/<hook>`. The framework currently lives as static files in the cute-devops `git_hooks` Ansible role; gitflower becomes its deployment-independent implementation, and deployments (Ansible or otherwise) install gitflower and invoke it. This issue records the decisions taken so far and the questions still open, ahead of writing the spec.

## Current state

**cute-devops `feature/global-git-hooks`** deploys `/etc/git/hooks` via `git config --system core.hooksPath`. One POSIX-sh dispatcher script is installed under every managed hook name; it derives the hook from its own basename, replays stdin payloads, runs `<hook>.d/*` lexicographically (fail fast), then chains to the repo-local `hooks/<hook>` that `core.hooksPath` would otherwise shadow. On top: `reference-transaction.d/50-autopush` (pushes ref updates to every remote with `remote.<name>.autopush=true`, no-op elsewhere) and `check-tree` + `check-tree.d/50-reuse` + `pre-receive.d/50-check-tree` for pluggable tree validation.

**gitflower** (`src/gitflower/hooks.py`) installs per-repo hooks in the old single-owner model: it writes `.git/hooks/pre-push` as a shim calling `gitflower hook pre-push`, refuses if a foreign hook exists, and overwrites with `--force`. The `.d` layout dissolves this ownership conflict: gitflower's workflow policy becomes one dispatched entry among others instead of owning the hook file.

## Decisions

**The dispatcher is gitflower.** Hook dispatch runs in Python: the hook entry points call into gitflower, and the framework's central commands (autopush, check-tree, the pre-receive gate) are gitflower code — tested in the package's suite, not static sh copies.

**A central gitflower githooks directory.** gitflower owns a global githooks script directory shipped with the package; the hook names in it are the dispatch entry points. Installation never copies files into place.

**`gitflower githooks install` sets config, nothing else.** The install command points `core.hooksPath` at the central directory, scopable as `--system`, `--global`, or `--repo`. Uninstall unsets it. Because no files are written, there is no ownership or double-writer problem with deployment tooling — the Ansible role reduces to installing the package and running the command (or setting the config itself).

**All four framework scripts move into gitflower.** Autopush, the check-tree driver, the REUSE check, and the pre-receive check-tree gate become gitflower-bundled central commands.

**Checks are configurable per repository.** A bundled check is not globally on or off: it is enabled per repo — for example the REUSE check only for public repos — so a machine-wide install stays a no-op wherever a check isn't wanted, the way autopush already gates on per-remote config.

## Open questions

**Q1 — hot-path cost.** With a Python dispatcher, every dispatched hook invocation pays interpreter startup, and `reference-transaction` fires on every ref update of every repo on the machine (several times per ordinary git command). Options: only ship entry points for hook names the framework actually uses; a minimal sh shim that fast-paths to exit before Python when nothing is configured; accept the cost. Needs a measurement before the spec fixes an answer.

**Q2 — site extension points.** The central directory is package-owned, so admins no longer drop scripts next to the dispatcher. Where do site-local `.d` extensions live — `/etc/gitflower/githooks.d/<hook>/`, a git-config key naming extra directories, per-repo `.gitflower/` config, some combination? And does the lexicographic `50-` ordering convention carry over there?

**Q3 — repo-local chaining.** `core.hooksPath` shadows the repository's own `hooks/` directory; the current dispatcher replays `hooks/<hook>` after the `.d` scripts so per-repo hooks keep firing. Confirm the Python dispatcher keeps this chaining, and whether scope layering beyond it (system → user → repo) is wanted or out of scope.

**Q4 — check configuration mechanism.** Where a check's enablement lives: git config keys in the repo (`gitflower.check.reuse=true`, the autopush precedent), the repo's `.gitflower/` config (but that is in-tree, so pushers control their own gates), or the hosting config, which already knows repo classes and could enable checks by group or pattern ("public repos"). Possibly layered — hosting config sets policy, git config overrides per repo.

**Q5 — command naming.** What the central commands are called under the CLI (`gitflower githooks run <hook>`? `gitflower hook <name>` extending the existing group?) and how a hook entry point maps to them.

**Q6 — spec home.** The dispatch semantics and directory contract need a normative home. Presumably `docs/spec/` here, with the cute-devops pattern page referencing it — confirm the split.

# References

- cute-devops branch `feature/global-git-hooks`: `roles/git_hooks/` (dispatcher, autopush, check-tree, role tasks).
- [Pure Git Project Workflows](https://cute-devops.patterns.how/patterns/workflows/pure-git-project-workflows) — the repo as the platform; gitflower as a view/enforcement layer over git conventions.
- gitflower `src/gitflower/hooks.py`, `src/gitflower/workflows.py` — current per-repo hook install and branch workflows.

# Considerations

## Prior art

No maintained tool occupies this niche. husky, lefthook, and pre-commit all own the repo-local hook file and dispatch from their own config — per-repo, language-ecosystem-bound, and exactly the single-owner model whose conflicts dispatched entries dissolve. The `.d` convention follows Debian's run-parts lineage. git upstream discussed native multi-hook support (config-based hooks, Emily Shaffer's series, ~2020–21) but it never landed; the framework should stay simple enough to map onto such a mechanism if git ever ships one.

## Why deployment-independent

The Ansible role manages plain file copies: untested, only reachable through a deployment run, and duplicated wherever the pattern is wanted without Ansible. In gitflower the framework sits in a tested package (`test_hooks_e2e.py` already exercises hook flows), ships via apt, and one idempotent config-setting command replaces the role's file management.

## Pure-sh runtime, rejected

A first framing kept the hook runtime pure sh with gitflower only installing static scripts, to keep Python off the hook path. Rejected in favour of the Python dispatcher: central commands in one tested implementation outweigh the startup cost, which Q1 addresses directly instead of designing around.
