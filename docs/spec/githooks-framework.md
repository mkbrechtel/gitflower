---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# githooks framework — machine-wide git hooks with pluggable dispatch

gitflower provides a global git hooks directory that `core.hooksPath` points at. Every entry in it is the gitflower executable acting as that hook: gitflower dispatches its bundled, config-gated central commands, site extension scripts, and — where enabled — the repository's own hooks. Installation is a config edit; no hook files are ever written into repositories.

This file specifies the directory contract, dispatch order, and configuration keys. The design decisions behind it are recorded in [`../../issues/githooks-framework.md`](../../issues/githooks-framework.md); the surrounding workflow is described by the [Pure Git Project Workflows](https://cute-devops.patterns.how/patterns/workflows/pure-git-project-workflows) pattern family.

## The central directory

The githooks directory ships with the gitflower package at `/usr/lib/gitflower/githooks`. Its entries are symlinks to the gitflower executable, named after git hooks; gitflower recognizes from `argv[0]` which hook it is acting as. The same dispatch is reachable as `gitflower hook <name>` — one implementation, two spellings. `gitflower githooks path` prints the directory.

The directory contains only the hook names the framework dispatches:

- `pre-push`
- `pre-receive`
- `update`
- `post-receive`
- `post-update`
- `reference-transaction`

git skips hook names that don't exist, so repositories pay no interpreter startup for any other hook. A hook name absent from the directory is fully inert — extension scripts and repo-local chaining for that name never run either, since dispatch is what invokes them.

## Installation

`gitflower githooks install [--system|--global|--repo]` sets `core.hooksPath` to the central directory at the chosen git config scope (default `--system`). If `core.hooksPath` at that scope already holds a different value, the command fails; `--force` overwrites. `gitflower githooks uninstall` unsets the key only when it points at the central directory.

## Dispatch

Acting as hook `<name>`, gitflower runs in order:

1. **Central commands** — the bundled actions and gates registered for `<name>`, each a no-op unless its configuration enables it (below).
2. **Site extensions** — every executable in `/etc/gitflower/githooks.d/<name>/`, lexicographically, then in each directory named by `gitflower.hooks.dir` (multi-valued git config; all scopes contribute), lexicographically per directory. Extension scripts conventionally carry numeric prefixes (`50-…`); gitflower claims no range.
3. **The repository's own `hooks/<name>`** — only when `gitflower.hooks.chain` is `true` for the repository. `core.hooksPath` shadows repo-local hooks, so without this key an installed framework disables them; deployments enable chaining wherever repo-local hooks are load-bearing.

Dispatch fails fast: the first stage exiting non-zero aborts the hook with that exit code. For hook kinds that receive per-ref lines on stdin, the payload is read once and replayed to every external script; hooks receive their usual arguments unchanged.

## Central commands and their configuration

All enablement is git config read in the acting repository — hooks depend on no external configuration at run time. The hosting layer (e.g. the cute-devops `repos` role, or gitflower's own repo management) declares policy and writes these keys per repository.

**Autopush** (`reference-transaction`). When the transaction state is `committed`, every changed branch or tag ref is pushed — deletions included — to each remote whose `remote.<name>.autopush` is `true`. Pushes run in the background; failures land in `autopush.log` in the git common directory. Without autopush-enabled remotes this is a no-op.

**Tree checks** (`pre-receive`, and standalone as `gitflower check-tree <tree-ish>`). A check validates an exported tree; `check-tree` exports the tree-ish to a temporary directory, runs every enabled check with the export as working directory and the tree-ish as argument, and reports all failures before exiting non-zero. Bundled checks are enabled per repository by `gitflower.check.<check>` (`gitflower.check.reuse` enables the REUSE compliance check); site checks are executables in `/etc/gitflower/check-tree.d/` and run whenever present. The `pre-receive` gate runs the enabled checks against every pushed branch tip and rejects the push on failure; with no checks enabled it is a no-op.

**Branch workflows** (`pre-push`, `pre-receive`, `update`). The branch router and protection workflows configured in the repository's `.gitflower/` config, as already implemented; repositories without gitflower configuration are untouched.

## Configuration key summary

- `remote.<name>.autopush` — push ref updates to this remote automatically.
- `gitflower.check.<check>` — enable bundled tree check `<check>` for this repository.
- `gitflower.hooks.chain` — run the repository's own `hooks/<name>` after dispatch.
- `gitflower.hooks.dir` — additional extension directory (repeatable, any scope).

# Considerations

## Why these six hook names

`reference-transaction`, `pre-receive`, `update`, `post-receive`, and `post-update` carry the framework's server-side commands and the commonly chained repo-local hooks (deploy triggers on `post-receive`); `pre-push` carries the client-side branch workflows. Frequently firing client-side hooks (`post-checkout`, `post-commit`, …) are deliberately absent so everyday git commands never touch Python. Growing the set is a package change, matching the rule that dispatch exists only where an entry point does.
