---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# Global git hooks framework — design

gitflower provides the machine-wide git hooks framework with `.d` dispatch: a gitflower-owned hooks script directory that `core.hooksPath` points at, where a dispatcher runs pluggable checks and actions and can chain to the repository's own `hooks/<hook>`. The framework currently lives as static files in the cute-devops `git_hooks` Ansible role; gitflower becomes its deployment-independent implementation, and deployments (Ansible or otherwise) install gitflower and invoke it. This issue records the design decisions; the contract is specified in [`../docs/spec/githooks-framework.md`](../docs/spec/githooks-framework.md).

## Current state

**cute-devops `feature/global-git-hooks`** deploys `/etc/git/hooks` via `git config --system core.hooksPath`. One POSIX-sh dispatcher script is installed under every managed hook name; it derives the hook from its own basename, replays stdin payloads, runs `<hook>.d/*` lexicographically (fail fast), then chains to the repo-local `hooks/<hook>` that `core.hooksPath` would otherwise shadow. On top: `reference-transaction.d/50-autopush` (pushes ref updates to every remote with `remote.<name>.autopush=true`, no-op elsewhere) and `check-tree` + `check-tree.d/50-reuse` + `pre-receive.d/50-check-tree` for pluggable tree validation.

**gitflower** (`src/gitflower/hooks.py`) installs per-repo hooks in the old single-owner model: it writes `.git/hooks/pre-push` as a shim calling `gitflower hook pre-push`, refuses if a foreign hook exists, and overwrites with `--force`. The `.d` layout dissolves this ownership conflict: gitflower's workflow policy becomes one dispatched entry among others instead of owning the hook file.

## Decisions

**The dispatcher is gitflower.** Hook dispatch runs in Python: the hook entry points call into gitflower, and the framework's central commands (autopush, check-tree, the pre-receive gate) are gitflower code — tested in the package's suite, not static sh copies.

**A central gitflower githooks directory.** gitflower owns a global githooks script directory shipped with the package; the hook names in it are the dispatch entry points. Installation never copies files into place.

**`gitflower githooks install` sets config, nothing else.** The install command points `core.hooksPath` at the central directory, scopable as `--system`, `--global`, or `--repo`. Uninstall unsets it. Because no files are written, there is no ownership or double-writer problem with deployment tooling — the Ansible role reduces to installing the package and running the command (or setting the config itself).

**All four framework scripts move into gitflower.** Autopush, the check-tree driver, the REUSE check, and the pre-receive check-tree gate become gitflower-bundled central commands.

**Checks are configurable per repository.** A bundled check is not globally on or off: it is enabled per repo — for example the REUSE check only for public repos — so a machine-wide install stays a no-op wherever a check isn't wanted, the way autopush already gates on per-remote config.

**Only needed hook names exist in the central directory.** The directory contains entry points only for the hooks the framework actually dispatches (`reference-transaction`, `pre-receive`, `pre-push`, …); git skips absent hook names for free, so repos never pay interpreter startup for hooks the framework doesn't use. Startup cost on the dispatched hooks is measured before the spec is fixed; a sh fast-path shim remains the fallback if it hurts.

**Site extensions: `/etc` directory plus a config key.** The dispatcher always runs `/etc/gitflower/githooks.d/<hook>/*` when present, and a git-config key can name additional extension directories at any scope (system, global, repo) — machine-wide policy and per-repo extras through one mechanism.

**Repo-local hooks chain only if configured.** The dispatcher runs the repository's own `hooks/<hook>` only where config enables it. Since `core.hooksPath` shadows repo-local hooks, installing the framework silently disables existing repo hooks (such as pod.git's `post-receive` deploy trigger) until chaining is switched on for that repo — deployments must set the config wherever repo-local hooks are load-bearing. In return, nothing runs that isn't declared.

**Check enablement is git config; hosting writes it.** The runtime truth a hook reads is git config in the repository (e.g. `gitflower.check.reuse=true`), following the `remote.<name>.autopush` precedent — hooks depend only on local state. The hosting configuration declares policy (which repo classes get which checks) and writes those keys, the way `repos[].remotes[].auto_push` becomes per-remote config today.

**Hook entry points are the CLI.** The entries in the central directory are symlinks to the gitflower executable, named after the hook; gitflower detects from `argv[0]` which hook it is acting as. The same dispatch is equally reachable as `gitflower hook <name>`, extending the existing hook group — one implementation, two spellings.

**The spec lives in `docs/spec/`, the workflow on the pattern site.** [`docs/spec/githooks-framework.md`](../docs/spec/githooks-framework.md) holds the normative contract — directory layout, dispatch order, config keys — alongside the existing specs; the cute-devops pattern page describes the workflow and references it.

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

A first framing kept the hook runtime pure sh with gitflower only installing static scripts, to keep Python off the hook path. Rejected in favour of the Python dispatcher: central commands in one tested implementation outweigh the startup cost, which the needed-hooks-only decision addresses directly instead of designing around.
