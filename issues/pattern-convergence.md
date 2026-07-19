---
id: 6f760bbe-d136-4f45-9ad1-3e77a40022de
status: open
---

# Convergence with the cute-devops workflow patterns

gitflower's design docs and the cute-devops pure-git workflow patterns describe the same system, and a comparison (2026-07-19) found them mostly aligned — the MR design and optimistic integration are converged and merged in `integration/workflows`. The review feature is the large remaining divergence and iterates in [review-approval](review-approval.md) on its own branch. This issue carries the smaller open items, each a decision one side (or both) still has to write down.

## Q1 — githooks spec still reads `.gitflower/` config

`docs/spec/githooks-framework.md` (on `integration/open-work`) says branch workflows come from "the repository's `.gitflower/` config, as already implemented". `docs/spec/repo-config.md` (on `work/docs/repo-config-in-git-config`) has since moved all per-repo policy into the bare repository's own git config and drops that file. Both branches are MR-marked; whichever lands second rebases its wording onto the other. Which goes first?

## Q2 — branch name shape: `work/` prefix or none

cute-devops `shared-worktrees.md` says the branch name is exactly `<category>/<branch>` — no prefix. The `pure-git-workflows` skill, `mr-commits.md`'s scope guidance and gitflower's own `CLAUDE.md` all prescribe `work/<category>/<branch>`. Integration branches are unprefixed in both repos. The `worktree-branch-shape` issue proposes a `pre-receive` hook rejecting off-shape refs, at which point the discrepancy stops being cosmetic. Pick one shape, then align both repos' docs and the planned hook.

## Q3 — stale pattern name in gitflower's `CLAUDE.md`

cute-devops renamed the pattern Worktree Treehouses → Worktree Workshops → Shared Worktrees; only the last name is current. gitflower's `CLAUDE.md` still links "Worktree Treehouses 🌳" and its old URL. Rename the reference and update the link.

## Q4 — frontmatter doctrine: advisory hints vs a load-bearing `id`

cute-devops `in-tree-issues.md` rules that frontmatter is advisory — "don't make tooling depend on them"; branch/MR state is authoritative. gitflower's issues-view makes the `id` field load-bearing and hook-enforced. Identity is not status, so the departure is sound — but neither document states it. Either the pattern carves out identity fields from the advisory rule, or `issues-view.md` records the deliberate divergence.

# Considerations

The review divergences — notes-ref vs tree-first storage, verdict event vs verdict commit, diff-range vs actual-merge target — are deliberately not items here; they are the subject of [review-approval](review-approval.md) and larger than a per-item Q. The optimistic-integration divergence from the same comparison resolved itself: gitflower's MR design records it as O8 and the `integration/workflows` basket practices it.
