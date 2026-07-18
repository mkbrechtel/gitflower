---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# Global git hooks framework — design

gitflower provides the machine-wide git hooks framework with `.d` dispatch directories: a global hooks directory (set via `core.hooksPath`) where a generic dispatcher runs every executable in `<hook>.d/`, then chains to the repository's own `hooks/<hook>`. The framework currently lives as static files in the cute-devops `git_hooks` Ansible role; gitflower becomes its deployment-independent implementation, and deployments (Ansible or otherwise) install gitflower and invoke it. This issue records the idea and the questions to settle before speccing.

## Current state

**cute-devops `feature/global-git-hooks`** deploys `/etc/git/hooks` via `git config --system core.hooksPath`. One POSIX-sh dispatcher script is installed under every managed hook name; it derives the hook from its own basename, replays stdin payloads, runs `<hook>.d/*` lexicographically (fail fast), then chains to the repo-local `hooks/<hook>` that `core.hooksPath` would otherwise shadow. On top: `reference-transaction.d/50-autopush` (pushes ref updates to every remote with `remote.<name>.autopush=true`, no-op elsewhere) and `check-tree` + `check-tree.d/50-reuse` + `pre-receive.d/50-check-tree` for pluggable tree validation.

**gitflower** (`src/gitflower/hooks.py`) installs per-repo hooks in the old single-owner model: it writes `.git/hooks/pre-push` as a shim calling `gitflower hook pre-push`, refuses if a foreign hook exists, and overwrites with `--force`. The `.d` layout dissolves this ownership conflict: gitflower's workflow hook becomes one `pre-push.d/` entry among others instead of owning the hook file.

## Open questions

**Q1 — runtime dependency.** Does the hook runtime stay pure sh, with gitflower acting only as installer/manager of static scripts? The dispatcher and autopush currently run with zero gitflower dependency; gitflower's own branch-workflow policy would be one `.d` entry that no-ops in repos without `.gitflower/` config (the same config-gating autopush uses). Alternative: the dispatcher itself calls into gitflower, which centralizes logic but puts Python on the path of every hook invocation of every repo on the machine.

**Q2 — command surface.** What are the install commands and scopes? Something like `gitflower githooks install --system|--global|--repo` — and how does the existing per-repo `gitflower install` (pre-push shim) relate: reworked to write a `.d` entry, kept as-is, or folded into the new surface?

**Q3 — scope layering.** `core.hooksPath` is single-valued (local git config shadows global shadows system), and the dispatcher chains only to the repo-local `hooks/` directory. Should there be system → user → repo chaining, or is system + repo-local (as today) enough?

**Q4 — what ships in gitflower.** The dispatcher clearly moves. Autopush is generic and config-gated — a strong candidate. `check-tree` as a driver is generic; the REUSE check leans toward site policy. Which of these become gitflower-bundled (and are they installed by default, opt-in, or `gitflower githooks add <name>`)?

**Q5 — ordering convention.** `.d` entries carry numeric prefixes (`50-…`). What number ranges do gitflower-managed entries claim, and where do admin drop-ins go?

**Q6 — single writer.** Once gitflower owns the files, the Ansible role must delegate (install package, run the install command) rather than also copying the scripts — two writers over the same files would fight on every run. Do the installed files carry a marker so `gitflower githooks uninstall` removes only its own entries, as `hooks.py` does today?

**Q7 — spec home.** The `.d` layout and dispatcher semantics need a normative home. Presumably `docs/spec/` here, with the cute-devops pattern page referencing it — confirm the split.

# References

- cute-devops branch `feature/global-git-hooks`: `roles/git_hooks/` (dispatcher, autopush, check-tree, role tasks).
- [Pure Git Project Workflows](https://cute-devops.patterns.how/patterns/workflows/pure-git-project-workflows) — the repo as the platform; gitflower as a view/enforcement layer over git conventions.
- gitflower `src/gitflower/hooks.py`, `src/gitflower/workflows.py` — current per-repo hook install and branch workflows.

# Considerations

## Prior art

No maintained tool occupies this niche. husky, lefthook, and pre-commit all own the repo-local hook file and dispatch from their own config — per-repo, language-ecosystem-bound, and exactly the single-owner model whose conflicts the `.d` layout dissolves. The `.d` convention follows Debian's run-parts lineage. git upstream discussed native multi-hook support (config-based hooks, Emily Shaffer's series, ~2020–21) but it never landed; the framework should stay simple enough to map onto such a mechanism if git ever ships one.

## Why deployment-independent

The Ansible role manages plain file copies: untested, only reachable through a deployment run, and duplicated wherever the pattern is wanted without Ansible. In gitflower the dispatcher sits in a tested package (`test_hooks_e2e.py` already exercises hook flows), ships via apt, and one idempotent command replaces the role's file management.
